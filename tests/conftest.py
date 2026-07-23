# -*- coding: utf-8 -*-
"""tests/ 目录级 conftest — 测试搬迁修复。

历史上所有 test_*.py 位于仓库根,可直接 `import novel_ai` / `import tests_helpers`。
搬入 tests/ 后:
  1. 仓库根不再在 sys.path 里 → import novel_ai 失败;
  2. pytest 从仓库根运行时 tests/ 不在 sys.path 里 → import tests_helpers 失败。
这里统一注入两个路径,任何调用方式(pytest 根目录/tests 目录/直接 python)都稳定。
"""
import os
import sys

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_TESTS_DIR)

for _p in (_REPO_ROOT, _TESTS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Qt 离屏渲染(CI/沙箱无显示器)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
