# -*- coding: utf-8 -*-
"""v1.34 BUG-046 教训防回归测试 — 验证新加的 13 法重写 handler 真在 MainWindow"""
import ast
from pathlib import Path


def _find_class_methods(class_name):
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
    return []


def test_autofix_request_in_mainwindow():
    """_on_dialogue_critic_autofix_request 必须在 MainWindow"""
    methods = _find_class_methods("MainWindow")
    assert "_on_dialogue_critic_autofix_request" in methods, \
        "_on_dialogue_critic_autofix_request 不在 MainWindow,会启动崩!"


def test_autofix_response_in_mainwindow():
    """_on_dialogue_critic_autofix_response 必须在 MainWindow"""
    methods = _find_class_methods("MainWindow")
    assert "_on_dialogue_critic_autofix_response" in methods, \
        "_on_dialogue_critic_autofix_response 不在 MainWindow,会 dispatch 崩!"


def test_autofix_request_not_in_chapter_editor():
    """ChapterEditor 不应该有 autofix handler(BUG-046 教训)"""
    methods = _find_class_methods("ChapterEditor")
    assert "_on_dialogue_critic_autofix_request" not in methods
    assert "_on_dialogue_critic_autofix_response" not in methods


def test_dispatch_routes_autofix_target():
    """dispatch 路由必须含 'dialogue_critic_autofix' target"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert 'target == "dialogue_critic_autofix"' in src, \
        "dispatch 路由没接 dialogue_critic_autofix target,AI 返回会失败"
    assert "_on_dialogue_critic_autofix_response" in src


def test_received_handler_has_button():
    """_on_dialogue_critic_received 必须有'🔧 按 13 法建议重写'按钮"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    # 找 _on_dialogue_critic_received 范围
    import re
    m = re.search(
        r"def _on_dialogue_critic_received.+?(?=\n    def )",
        src, re.DOTALL)
    assert m, "_on_dialogue_critic_received 没找到"
    body = m.group(0)
    assert "13 法建议重写" in body or "13 法建议重写本章" in body, \
        "诊断对话框没有'按 13 法建议重写'按钮"
    assert "_on_dialogue_critic_autofix_request" in body, \
        "按钮没绑到 autofix_request handler"
