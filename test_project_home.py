# -*- coding: utf-8 -*-
"""v1.41 ProjectHomeTab UI 集成防回归(吸取 BUG-046 教训)"""
import ast
from pathlib import Path


def _methods(cls_name):
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef) and n.name == cls_name:
            return [m.name for m in n.body if isinstance(m, ast.FunctionDef)]
    return []


def test_project_home_tab_class_exists():
    methods = _methods("ProjectHomeTab")
    assert methods, "ProjectHomeTab class 不存在"
    for m in ["_build_ui", "refresh", "refresh_recent_list",
              "_on_recent_dblclick", "_on_open_recent", "_on_remove_recent"]:
        assert m in methods, f"ProjectHomeTab 缺方法 {m}"


def test_main_window_has_recent_handlers():
    methods = _methods("MainWindow")
    for m in ["_refresh_recent_menu", "_open_project_by_path",
              "_push_to_recent", "_remove_from_recent",
              "_clear_recent_projects"]:
        assert m in methods, f"MainWindow 缺方法 {m}(BUG-046 教训)"


def test_recent_methods_not_in_other_classes():
    """BUG-046 教训:确保 _push_to_recent 等不被 sed 误插到其他 class"""
    for cls in ["ChapterEditor", "ProjectHomeTab", "BookSplitterTab",
                "GenerationControl", "CreationSettings"]:
        methods = _methods(cls)
        for m in ["_push_to_recent", "_open_project_by_path",
                  "_refresh_recent_menu"]:
            assert m not in methods, \
                f"{m} 不应在 {cls},应该在 MainWindow"


def test_tab_home_registered():
    """🏠 项目主页 必须在 tab_list 中第一个"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert "self.tab_home = ProjectHomeTab()" in src
    assert '"🏠 项目主页"' in src


def test_signals_connected():
    """ProjectHomeTab 4 个信号必须接到 MainWindow handlers"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert "self.tab_home.request_open_project.connect" in src
    assert "self.tab_home.request_new_project.connect" in src
    assert "self.tab_home.request_open_recent.connect" in src
    assert "self.tab_home.request_restore_backup.connect" in src


def test_recent_menu_in_file_menu():
    """文件菜单必须有 __RECENT__ 占位 + 动态构造"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert '"__RECENT__"' in src
    assert "self.recent_menu" in src
    assert 'if slot == "__RECENT__":' in src


def test_push_to_recent_called_after_load():
    """open_project / save_project / _autoload 成功后必须 push 到 recent"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    # 至少 3 处调用 _push_to_recent
    count = src.count("self._push_to_recent(")
    assert count >= 3, f"_push_to_recent 调用次数 {count} < 3"
