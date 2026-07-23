"""v1.75 Canon 自动抽取可见性 + 诊断测试

用户反馈:"每次结束也没有自动抽取最新章节" — Canon Tab 看不出 AI 自动抽取是否跑过。

v1.75 修法:
A) CanonGuard 加 lbl_last_extract label,顶部常驻可见
B) _post_chapter_chain 加诊断日志,显示 Canon 抽取开关状态
C) _on_canon_extract_response 加 isinstance(arr, list) 守(防 AI 输出对象)
D) 永远更新 lbl_last_extract(count>0/=0/解析失败 三种状态都更新)
"""
import os
import re
import ast
import sys
from tests_helpers import read_all_sources

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根(测试搬迁修复)
SRC = read_all_sources()  # v2.07:读全源


# ── 代码层 ──────────────────────────────────────────

def test_canonguard_has_lbl_last_extract():
    """CanonGuard 必须创建 lbl_last_extract"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CanonGuard":
            class_src = ast.unparse(node)
            assert "lbl_last_extract" in class_src, \
                "CanonGuard 没创建 lbl_last_extract"
            assert "尚未运行" in class_src, \
                "lbl_last_extract 初始文案没说'尚未运行'"
            return
    pytest.fail("找不到 CanonGuard 类")


def test_post_chapter_chain_has_diagnostic():
    """_post_chapter_chain 必须有 v1.75 诊断日志(打印 chk_extract 状态)"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_post_chapter_chain":
                    body_src = ast.unparse(m)
                    assert "post-chain v1.75" in body_src, \
                        "_post_chapter_chain 没加 v1.75 诊断 print"
                    assert "canon_extract=" in body_src, \
                        "诊断没打印 canon_extract 开关状态"
                    assert "Canon抽取" in body_src or "canon" in body_src.lower(), \
                        "log 没显示 Canon 抽取状态"
                    return
    pytest.fail("找不到 MainWindow._post_chapter_chain")


def test_run_canon_extract_has_send_log():
    """_run_canon_extract 必须有发送诊断日志"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_run_canon_extract":
                    body_src = ast.unparse(m)
                    assert "canon-extract v1.75" in body_src, \
                        "_run_canon_extract 没加发送日志"
                    return
    pytest.fail("找不到 MainWindow._run_canon_extract")


def test_on_canon_response_isinstance_list_guard():
    """_on_canon_extract_response 必须有 list 类型守 + label 兜底更新"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_on_canon_extract_response":
                    body_src = ast.unparse(m)
                    # 类型守
                    assert "isinstance(arr, list)" in body_src, \
                        "没有 arr 是 list 的检查"
                    # 三种 label 更新分支都要有
                    assert "lbl_last_extract" in body_src, \
                        "没更新 lbl_last_extract"
                    # 空数组也要更新 label("无新设定" 等字眼)
                    assert "空数组" in body_src or "无新设定" in body_src, \
                        "AI 返回空数组时没明确更新 label"
                    return
    pytest.fail("找不到 MainWindow._on_canon_extract_response")


def test_on_canon_response_logs_raw_content_on_failure():
    """解析失败时必须 print AI 原始回复(便于排障)"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_on_canon_extract_response":
                    body_src = ast.unparse(m)
                    # 失败 except 分支要打印原始内容
                    assert "原始" in body_src, "失败时没打印原始内容"
                    return
    pytest.fail("找不到 MainWindow._on_canon_extract_response")


# ── 行为层 ──────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def canon_guard(app):
    from novel_ai import CanonGuard
    return CanonGuard()


def test_canon_guard_lbl_init_text(canon_guard):
    """初始化时 lbl_last_extract 应该有'尚未运行'文案"""
    assert hasattr(canon_guard, "lbl_last_extract"), \
        "CanonGuard 没 lbl_last_extract 属性"
    assert "尚未运行" in canon_guard.lbl_last_extract.text()


def test_canon_guard_chk_extract_exists(canon_guard):
    """chk_extract 仍然存在(没破)"""
    assert hasattr(canon_guard, "chk_extract")
    assert canon_guard.chk_extract.isChecked()  # 默认 True


def test_canon_guard_add_item_still_works(canon_guard):
    """add_item 没破:数据写进 canon_edit"""
    canon_guard.add_item("角色.林远.身份", "无灵根凡人",
                         mode="locked", severity="high", ch=1)
    text = canon_guard.canon_edit.toPlainText()
    assert "林远.身份" in text
    assert "无灵根凡人" in text


# ── 版本守 ──────────────────────────────────────────

def test_app_version_at_least_v1_75():
    m = re.search(r'APP_VERSION\s*=\s*"v(\d+)\.(\d+)(?:\.\d+)?"', SRC)
    assert m, "找不到 APP_VERSION"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 75), \
        f"APP_VERSION = v{major}.{minor},应该 ≥ v1.75"
