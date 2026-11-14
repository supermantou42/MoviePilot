"""验证 v2/v3 ELF 定位、幂等性和不支持架构的保护。"""

import importlib.util
import pathlib
import struct
import tempfile
import unittest


SOURCE = pathlib.Path(__file__).resolve().parents[1] / "patch/app/helper/_sites_unlock.py"
SPEC = importlib.util.spec_from_file_location("sites_unlock", SOURCE)
PATCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCHER)


def elf_fixture(symbol):
    """构造包含两个相邻指针加载与目标函数符号的最小 ELF64。"""
    data = bytearray(1024)
    data[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", data, 18, 62)
    struct.pack_into("<Q", data, 0x28, 64)
    struct.pack_into("<HH", data, 0x3A, 64, 4)
    # 节：空节、代码节、字符串表、符号表。
    for index, kind, address, offset, size, link, entsize in (
        (1, 1, 0x1000, 512, 14, 0, 0),
        (2, 3, 0, 600, len(symbol) + 2, 0, 0),
        (3, 2, 0, 800, 24, 2, 24),
    ):
        base = 64 + index * 64
        struct.pack_into("<I", data, base + 4, kind)
        struct.pack_into("<QQQ", data, base + 16, address, offset, size)
        struct.pack_into("<I", data, base + 40, link)
        struct.pack_into("<Q", data, base + 56, entsize)
    data[601:601 + len(symbol)] = symbol
    struct.pack_into("<I", data, 800, 1)
    struct.pack_into("<QQ", data, 808, 0x1000, 14)
    for offset, target in ((512, 0x2000), (519, 0x2008)):
        data[offset:offset + 3] = b"\x48\x8b\x05"
        struct.pack_into("<i", data, offset + 3, target - (0x1000 + offset - 512 + 7))
    return data


class PatchTests(unittest.TestCase):
    """验证二进制补丁可观测行为。"""

    def test_v2_and_v3_and_second_application(self):
        """两个模块路径均只改写预期加载，重复执行保持内容。"""
        for symbol in PATCHER._GET_AUTH_LEVEL_SYMS:
            with self.subTest(symbol=symbol):
                data = elf_fixture(symbol)
                before = data[:]
                self.assertTrue(PATCHER.patch_bytes(data).startswith("patched: 1"))
                self.assertEqual(data[:515], before[:515])
                self.assertEqual(data[519:], before[519:])
                self.assertEqual(struct.unpack_from("<i", data, 515)[0],
                                 struct.unpack_from("<i", before, 515)[0] + 8)
                after = data[:]
                self.assertFalse(PATCHER.patch_bytes(data).startswith("patched"))
                self.assertEqual(data, after)

    def test_reject_other_architecture_and_symbol(self):
        """不支持的机器类型或未知函数不能被修改。"""
        for machine, symbol in ((183, PATCHER._GET_AUTH_LEVEL_SYMS[1]), (62, b"unknown")):
            data = elf_fixture(symbol)
            struct.pack_into("<H", data, 18, machine)
            before = data[:]
            self.assertTrue(PATCHER.patch_bytes(data).startswith("skip"))
            self.assertEqual(data, before)

    def test_atomic_file_replacement_preserves_mode(self):
        """落盘修改保留文件权限且不留下临时文件。"""
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "sites.so"
            path.write_bytes(elf_fixture(PATCHER._GET_AUTH_LEVEL_SYMS[1]))
            mode = path.stat().st_mode
            self.assertTrue(PATCHER.patch_file(str(path)).startswith("patched"))
            self.assertEqual(path.stat().st_mode, mode)
            self.assertEqual(list(path.parent.iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
