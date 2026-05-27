# -*- coding: utf-8 -*-
"""v1.61 BUG-050 防回归 — 切项目时 UI 状态必须清干净"""
import ast
import re
from pathlib import Path


def _methods(cls_name):
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls_name:
            return [m.name for m in n.body if isinstance(m, ast.FunctionDef)]
    return []


def test_reset_ui_state_in_main_window():
    """_reset_ui_state 必须在 MainWindow"""
    methods = _methods("MainWindow")
    assert "_reset_ui_state" in methods, \
        "_reset_ui_state 不在 MainWindow(BUG-046 教训)"


def test_reset_not_in_other_classes():
    """不能 sed 错插到其他 class"""
    for cls in ["ChapterEditor", "ProjectHomeTab", "BookSplitterTab",
                "CreationSettings", "GenerationControl"]:
        methods = _methods(cls)
        assert "_reset_ui_state" not in methods, \
            f"_reset_ui_state 错插到 {cls}"


def test_load_payload_calls_reset():
    """_load_payload_into_ui 必须先调 _reset_ui_state"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _load_payload_into_ui.+?(?=\n    def )",
        src, re.DOTALL)
    assert m, "_load_payload_into_ui 没找到"
    body = m.group(0)
    # reset 必须在 chapters 赋值之前
    reset_idx = body.find("self._reset_ui_state()")
    chapters_idx = body.find('self.chapters = d.get("chapters"')
    assert reset_idx > 0, "_load_payload_into_ui 没调 _reset_ui_state"
    assert reset_idx < chapters_idx, "_reset_ui_state 必须在赋 chapters 之前"


def test_new_project_uses_reset():
    """new_project 必须用 _reset_ui_state"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    m = re.search(
        r"def new_project.+?(?=\n    def )",
        src, re.DOTALL)
    assert m
    body = m.group(0)
    assert "self._reset_ui_state()" in body, \
        "new_project 没用 _reset_ui_state"


def test_reset_clears_8_fields():
    """_reset_ui_state 必须涵盖之前 BUG 涉及的 8 个字段"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    m = re.search(
        r"def _reset_ui_state.+?(?=\n    def )",
        src, re.DOTALL)
    assert m
    body = m.group(0)
    # 8 个字段都得提到
    for keyword in [
        "tab_settings", "tab_outline", "tab_memory", "tab_canon",
        "tab_charlib", "tab_skills", "tab_generation", "tab_editor",
    ]:
        assert keyword in body, f"_reset_ui_state 漏处理 {keyword}"
    # critique 5 个 checkbox
    for cb in ["chk_crit_words", "chk_crit_hook", "chk_crit_canon",
               "chk_crit_rhythm", "chk_crit_char"]:
        assert cb in body, f"_reset_ui_state 漏 critique.{cb}"
