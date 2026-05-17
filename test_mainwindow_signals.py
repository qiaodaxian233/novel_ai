# -*- coding: utf-8 -*-
"""v1.32 BUG-046 回归测试:
确保 ChapterEditor 的所有信号 handler 都在 MainWindow 内
(防止再发生"方法被插错类导致启动 AttributeError")
"""
import ast
import re
from pathlib import Path


def get_class_method_names(source: str, class_name: str) -> set[str]:
    """用 ast 抽出某个 class 内定义的所有方法名"""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {n.name for n in node.body if isinstance(n, ast.FunctionDef)}
    return set()


def get_signal_connections(source: str) -> list[tuple[str, str, str]]:
    """grep 找所有 self.tab_editor.XXX.connect(self._YYY) 类的连接
    返回 [(signal_path, target_handler, full_line), ...]"""
    pattern = re.compile(
        r'self\.tab_editor\.(\w+)\.connect\(self\.(_?\w+)\)')
    results = []
    for line_no, line in enumerate(source.splitlines(), 1):
        m = pattern.search(line)
        if m:
            results.append((m.group(1), m.group(2), line.strip()))
    return results


def test_chapter_editor_signals_handled_in_mainwindow():
    """所有 self.tab_editor.XXX.connect(self._YYY) 中的 _YYY 必须真在 MainWindow 内"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    mw_methods = get_class_method_names(src, "MainWindow")
    assert mw_methods, "MainWindow 类没找到或没方法"
    
    connections = get_signal_connections(src)
    assert connections, "tab_editor 信号连接没找到"
    
    missing = []
    for sig, handler, line in connections:
        if handler not in mw_methods:
            missing.append(f"  · {sig} → self.{handler}() ← MainWindow 里没这个方法!\n    line: {line}")
    
    if missing:
        raise AssertionError(
            "以下 ChapterEditor 信号连接的目标 handler 不在 MainWindow 内"
            "(启动时会 AttributeError):\n" + "\n".join(missing)
        )


def test_dialogue_critic_handler_specifically():
    """专门针对 BUG-046 — _on_dialogue_critic 必须在 MainWindow 而非 ChapterEditor"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    mw_methods = get_class_method_names(src, "MainWindow")
    ce_methods = get_class_method_names(src, "ChapterEditor")
    
    assert "_on_dialogue_critic" in mw_methods, \
        "BUG-046 回归:_on_dialogue_critic 必须定义在 MainWindow 内"
    assert "_on_dialogue_critic_received" in mw_methods, \
        "BUG-046 回归:_on_dialogue_critic_received 必须定义在 MainWindow 内"
    assert "_on_dialogue_critic" not in ce_methods, \
        "BUG-046 回归:_on_dialogue_critic 不该在 ChapterEditor 里"


def test_mainwindow_has_send_to_ai():
    """_on_dialogue_critic 调用 self._send_to_ai,确保 MainWindow 有这个方法"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    mw_methods = get_class_method_names(src, "MainWindow")
    assert "_send_to_ai" in mw_methods, \
        "MainWindow 没有 _send_to_ai 方法"
