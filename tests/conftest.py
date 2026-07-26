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

# QSettings 隔离:重定向到每会话独立的临时目录。
# 部分控件(CharLib 等)在 __init__ 从 QSettings 恢复状态、析构时写回,
# 不隔离的话一次 pytest 运行写入 ~/.config/NovelAI/*.conf,
# 下一次运行"全新"实例就带着上次的 POV/主角状态出生
# (实证:test_pov_mode 跑过一次后,test_plot_progress D30/D31 与
#  test_info_isolation D23/D24 因 POV=林悦 过滤而跨进程失败)。
# 必须在任何 QSettings 实例化之前设置 — conftest 的 import 时机满足。
import tempfile

_QSETTINGS_DIR = tempfile.mkdtemp(prefix="novel_ai_test_qsettings_")
os.environ["XDG_CONFIG_HOME"] = _QSETTINGS_DIR

# HOME 隔离:MainWindow 的 project_dir = Path.home()/"NovelAI_Projects" 是
# 固定家目录路径,closeEvent → _autosave() 会把测试造的章节写进真实用户的
# 项目目录;下一次运行 _autoload 又把它们恢复进"全新"主窗口
# (实证:一次带 teardown 的运行后 ~/NovelAI_Projects/autosave 出现 3 章残留,
#  test_full_integration 的"self.chapters 为空"守护跨进程失败)。
# 与 QSettings 同类,双向隔离:测试不读真实项目、也不写坏真实项目。
_HOME_DIR = tempfile.mkdtemp(prefix="novel_ai_test_home_")
os.environ["HOME"] = _HOME_DIR


# ── 模块间 QSettings 隔离 ──────────────────────────────────────
# 上面的 XDG 重定向解决了"跨 pytest 进程"的污染;进程内还有一个方向:
# 某模块的控件析构时把 POV/主角状态写进(临时)QSettings,同一会话里
# 后跑的模块实例化"干净"控件时又把它恢复出来。字母序批跑恰好安全
# (info_isolation < plot_progress < pov_mode),但显式指定顺序就会踩雷。
# 每个测试模块开始前用 Qt 自己的 API 清空 NovelAI 组织下的所有应用配置
# (必须走 QSettings.clear() 而非直接删文件 — Qt 有 QConfFile 内存缓存,
# 外部删文件不保证失效)。模块内部的保存→恢复语义不受影响。
import pytest


@pytest.fixture(autouse=True, scope="module")
def _fresh_novelai_qsettings_per_module():
    try:
        from PyQt5.QtCore import QSettings
        import glob as _glob
        conf_dir = os.path.join(os.environ["XDG_CONFIG_HOME"], "NovelAI")
        for conf in _glob.glob(os.path.join(conf_dir, "*.conf")):
            app_name = os.path.splitext(os.path.basename(conf))[0]
            s = QSettings("NovelAI", app_name)
            s.clear()
            s.sync()
    except Exception:
        pass  # PyQt5 不可用的纯逻辑测试模块无需隔离
    yield
