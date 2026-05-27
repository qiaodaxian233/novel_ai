# -*- coding: utf-8 -*-
"""
scripts/pre_push_check.py - 推送前冒烟测试

检查内容:
  1. 所有主要模块能 import（无语法错误、无缺失依赖）
  2. ThemeManager 每个主题都能生成 QSS
  3. FanqieRankTab 能正常实例化（UI 构建不报错）
  4. novel_ai.py 语法正确

用法:
  QT_QPA_PLATFORM=offscreen python scripts/pre_push_check.py
"""
import ast
import importlib
import sys
import os

# 切到仓库根目录，并把根目录加入 sys.path
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_root)
if _root not in sys.path:
    sys.path.insert(0, _root)

errors = []

# ── 1. 模块 import ──
MODULES = [
    "core.constants", "core.stylesheet", "core.site_profiles",
    "core.fanqie_rank_scraper", "core.fanqie_genre_provider",
    "core.prompts", "core.default_skills",
    "housekeeper", "dialogue_critic", "flow_rl",
    "pangu_system", "pangu_patch", "project_io",
    "relation_graph", "tts_backend", "license_guard",
    "lifespan_loops_steps", "workflow_pipeline",
    "ui.browser_worker", "ui.fanqie_rank_tab",
    "ui.foreshadow_tab", "ui.project_launcher",
    "ui.ai_toolbox_tab", "ui.theme",
    "ui.tabs.chapter_editor", "ui.tabs.character_library",
    "ui.tabs.creation_settings", "ui.tabs.generation_control",
]
for m in MODULES:
    try:
        importlib.import_module(m)
    except Exception as e:
        errors.append(f"import {m}: {e}")

# ── 2. ThemeManager QSS 生成 ──
try:
    from ui.theme import ThemeManager, _build_modern_qss
    for name, theme in ThemeManager.THEMES.items():
        args = theme.get("qss_args", {})
        assert args, f"主题 {name} qss_args 为空"
        qss = _build_modern_qss(**args)
        assert len(qss) > 100, f"主题 {name} QSS 太短"
except Exception as e:
    errors.append(f"ThemeManager: {e}")

# ── 3. FanqieRankTab 实例化 ──
try:
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.fanqie_rank_tab import FanqieRankTab
    tab = FanqieRankTab()
except Exception as e:
    errors.append(f"FanqieRankTab 实例化: {e}")

# ── 4. novel_ai.py 语法 ──
try:
    with open("novel_ai.py", encoding="utf-8") as f:
        ast.parse(f.read())
except SyntaxError as e:
    errors.append(f"novel_ai.py 语法错误: {e}")

# ── 结果 ──
if errors:
    print("❌ 推送前检查失败，请修复后再推：")
    for e in errors:
        print(f"   • {e}")
    sys.exit(1)
else:
    print("✅ 推送前检查全部通过")
    sys.exit(0)
