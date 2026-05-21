# -*- coding: utf-8 -*-
"""v1.38 BookSplitterTab UI 集成防回归测试(吸取 BUG-046 教训)"""
import ast
from pathlib import Path
from tests_helpers import read_all_sources


def _find_class_methods(cls_name):
    src = read_all_sources()  # v2.07
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls_name:
            return [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
    return []


def test_booksplittertab_class_exists():
    """BookSplitterTab class 必须存在"""
    methods = _find_class_methods("BookSplitterTab")
    assert methods, "BookSplitterTab class 不存在"
    for m in ["_build_ui", "_on_load_file", "_on_chapter_selected",
              "_on_analyze_current", "receive_analysis_result"]:
        assert m in methods, f"BookSplitterTab 缺方法 {m}"


def test_main_window_has_book_handlers():
    """MainWindow 必须有 _on_book_chapter_analyze 和 _on_book_chapter_analysis_received"""
    methods = _find_class_methods("MainWindow")
    assert "_on_book_chapter_analyze" in methods, \
        "_on_book_chapter_analyze 不在 MainWindow,会启动崩"
    assert "_on_book_chapter_analysis_received" in methods


def test_book_handlers_not_in_chapter_editor():
    """ChapterEditor 不应该有 book handler(BUG-046 教训)"""
    methods = _find_class_methods("ChapterEditor")
    assert "_on_book_chapter_analyze" not in methods
    assert "_on_book_chapter_analysis_received" not in methods


def test_dispatch_routes_book_target():
    """dispatch 路由必须含 'book_chapter_analysis' target"""
    src = read_all_sources()  # v2.07
    assert 'target == "book_chapter_analysis"' in src
    assert "_on_book_chapter_analysis_received" in src


def test_tab_registered():
    """📚 拆书学习 必须在 tab_list 注册"""
    src = read_all_sources()  # v2.07
    assert "self.tab_book_splitter = BookSplitterTab()" in src
    assert "📚 拆书学习" in src
