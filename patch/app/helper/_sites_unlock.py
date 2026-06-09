"""站点认证解锁补丁（自用 / 学习研究）——二进制自愈版。

MoviePilot 的「用户认证」门槛位于 Cython 编译扩展 ``app/helper/sites.*.so``：
``BByvbqGwZwqoYFxE.get_auth_level`` 返回两个缓存整数之一——内部校验通过时返回
``number_tab[2]``（已认证，等级 2），否则返回 ``number_tab[1]``（未认证，等级 1）。
``SitesHelper.get_indexers`` 在 C 层直接读取该等级（``if auth_level < 2: return []``），
因此仅在 Python 层覆盖 ``auth_level`` 属性无效。

本模块在 ``app.helper`` 包导入时（早于编译模块 ``app.helper.sites`` 首次加载）就地改写
磁盘上的 ``.so``：把 ``get_auth_level`` 未认证返回路径重定向到已认证返回值，使其恒返回
等级 2。补丁是「自愈」的——即便资源更新重新下载了未打补丁的 ``.so``，下次启动会再次自动
打上；并且与偏移无关（通过 ELF 符号表定位函数，再在函数体内找到指向 ``number_tab`` 相邻
8 字节两项的 ``mov rax,[rip+disp32]`` 加载，将未认证项重指向已认证项）。幂等、失败安全：
结构不符合预期时不做任何改动。
"""
from __future__ import annotations

import glob
import logging
import os
import struct

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))
_GET_AUTH_LEVEL_SYM = b"__pyx_pw_3app_6helper_5sites_16BByvbqGwZwqoYFxE_15get_auth_level"

_log = logging.getLogger(__name__)


def _iter_section_headers(data):
    e_shoff = struct.unpack_from("<Q", data, 0x28)[0]
    e_shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3C)[0]
    for i in range(e_shnum):
        base = e_shoff + i * e_shentsize
        yield dict(
            type=struct.unpack_from("<I", data, base + 0x04)[0],
            addr=struct.unpack_from("<Q", data, base + 0x10)[0],
            offset=struct.unpack_from("<Q", data, base + 0x18)[0],
            size=struct.unpack_from("<Q", data, base + 0x20)[0],
            link=struct.unpack_from("<I", data, base + 0x28)[0],
            entsize=struct.unpack_from("<Q", data, base + 0x38)[0],
        )


def _va_to_off(secs, va):
    for s in secs:
        if s["addr"] and s["addr"] <= va < s["addr"] + s["size"]:
            return s["offset"] + (va - s["addr"])
    return None


def _find_symbol(data, secs, name):
    for symtype in (2, 11):  # .symtab, .dynsym
        for s in secs:
            if s["type"] != symtype or s["entsize"] == 0:
                continue
            stroff = secs[s["link"]]["offset"]
            for i in range(s["size"] // s["entsize"]):
                e = s["offset"] + i * s["entsize"]
                st_name = struct.unpack_from("<I", data, e + 0x00)[0]
                end = data.find(b"\x00", stroff + st_name)
                if data[stroff + st_name:end] == name:
                    return (struct.unpack_from("<Q", data, e + 0x08)[0],
                            struct.unpack_from("<Q", data, e + 0x10)[0])
    return None, None


def patch_bytes(data: bytearray) -> str:
    """就地修补 ELF ``.so`` 字节，返回状态字符串。"""
    if data[:4] != b"\x7fELF":
        return "skip: not ELF"
    secs = list(_iter_section_headers(data))
    va, size = _find_symbol(data, secs, _GET_AUTH_LEVEL_SYM)
    if va is None or not size:
        return "skip: get_auth_level symbol not found"
    foff = _va_to_off(secs, va)
    if foff is None:
        return "skip: cannot map function VA"

    # 收集函数体内所有 `mov rax,[rip+disp32]`(48 8B 05 ..) 及其目标地址
    loads = []
    body = data[foff:foff + size]
    i = 0
    while i + 7 <= len(body):
        if body[i] == 0x48 and body[i + 1] == 0x8B and body[i + 2] == 0x05:
            disp = struct.unpack_from("<i", body, i + 3)[0]
            loads.append((foff + i + 3, va + i + 7 + disp))  # (disp文件偏移, 目标VA)
            i += 7
            continue
        i += 1

    targets = {t for _, t in loads}
    pairs = [(lo, lo + 8) for lo in targets if (lo + 8) in targets]
    if len(pairs) != 1:  # 已打补丁(两者相等)或结构异常 -> 不动
        return f"noop: {len(pairs)} candidate pair(s) (likely already patched)"
    lo_target, _ = pairs[0]

    changed = 0
    for off, target in loads:
        if target == lo_target:  # 未认证返回项 +8 重指向已认证项
            disp = struct.unpack_from("<i", data, off)[0]
            struct.pack_into("<i", data, off, disp + 8)
            changed += 1
    return f"patched: {changed} load(s) at get_auth_level (VA {hex(va)})"


def patch_file(path: str) -> str:
    with open(path, "rb") as f:
        data = bytearray(f.read())
    status = patch_bytes(data)
    if status.startswith("patched"):
        with open(path, "wb") as f:
            f.write(data)
    return status


def install() -> None:
    """在 ``app.helper.sites`` 首次加载前，就地修补同目录下的 ``sites.*.so``（幂等）。"""
    try:
        sos = glob.glob(os.path.join(_PKG_DIR, "sites.*.so")) + \
              glob.glob(os.path.join(_PKG_DIR, "sites.*.pyd"))
        for so in sos:
            try:
                status = patch_file(so)
                _log.info("站点认证解锁补丁 %s: %s", os.path.basename(so), status)
            except Exception as e:  # 单个文件失败不影响启动
                _log.warning("站点认证解锁补丁应用失败 %s: %r", so, e)
    except Exception as e:
        _log.warning("站点认证解锁补丁安装失败: %r", e)


if __name__ == "__main__":
    import sys
    print(patch_file(sys.argv[1]))
