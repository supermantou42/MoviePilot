#!/usr/bin/env bash
# 将站点认证解锁补丁叠加到一个上游 MoviePilot 源码检出目录上。
#
# 用法: scripts/apply_patch.sh [上游检出根目录]   (默认当前目录)
#
# 做两件事，均幂等：
#   1) 复制自愈补丁模块 _sites_unlock.py 到 app/helper/
#   2) 确保 app/helper/__init__.py 在包导入时调用 _sites_unlock.install()
#      （保留上游 __init__.py 原有内容，仅在缺失时追加我们的调用）
set -euo pipefail

ROOT="${1:-.}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$ROOT/app/helper"

if [ ! -d "$HELPER" ]; then
  echo "ERROR: $HELPER 不存在——参数应为上游 MoviePilot 源码检出根目录" >&2
  exit 1
fi

# 1) 放入自愈补丁模块
cp -f "$SCRIPT_DIR/../patch/app/helper/_sites_unlock.py" "$HELPER/_sites_unlock.py"

# 2) 在包 __init__ 中挂载调用（追加式，保留上游内容）
INIT="$HELPER/__init__.py"
touch "$INIT"
MARKER="_sites_unlock.install()"
if ! grep -qF "$MARKER" "$INIT"; then
  cat >> "$INIT" <<'PY'

# 站点认证解锁补丁（本地自用 / 学习研究）：包导入时就地修补编译扩展 sites.*.so，
# 使其内部 get_auth_level 恒返回等级 2，解锁站点搜索/索引。必须早于编译模块
# app.helper.sites 首次加载执行（包 __init__ 先于子模块导入）。自愈、幂等、失败安全。
from app.helper import _sites_unlock  # noqa: E402
_sites_unlock.install()
PY
  echo "apply_patch: __init__.py 已挂载补丁调用"
else
  echo "apply_patch: __init__.py 已包含补丁调用，跳过"
fi

echo "apply_patch: 补丁已应用到 $ROOT"
