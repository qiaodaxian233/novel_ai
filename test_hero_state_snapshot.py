"""v1.74 hero_state 自动同步根因修复测试

核心问题:用户反馈"第二章生成后主角状态没变化",根因是:
1. prompt 规则 7 写"无变化填空字符串" → AI 大多数章节返回全空 5 字段
2. apply_hero_state_dict 跳过空值 → n_filled=0
3. _merge_into_charlib 只在 n>0 时更新 label → UI 永远"未同步"

v1.74 修法:
A) prompt 改快照模式(每次输出本章末完整状态,不输出 diff)
B) n=0 时也更新 label,显示"已同步但本章无变化"
C) 加诊断日志,方便排查 AI 实际返回了啥
"""
import os
import re
import ast
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(__file__)
SRC = open(os.path.join(HERE, "novel_ai.py"), encoding="utf-8").read()


def test_prompt_hero_state_snapshot_wording():
    """A 修:prompt 规则 7 必须明确说快照,移除 diff 语义"""
    m = re.search(r'"world_extract":\s*\((.+?)\),\s*\n\s+"long_term', SRC, re.S)
    body = m.group(1)
    
    # 不能再写 diff 语义
    assert "无变化的字段填" not in body and "无变化填" not in body, \
        "prompt 还在让 AI 填空字符串(diff 模式),v1.74 应该改快照"
    
    # 必须明确说"快照"
    assert "快照" in body, "prompt 规则 7 没出现'快照'字样"


def test_prompt_hero_state_age_field_no_longer_says_无变化():
    """v1.73 prompt 里 age 字段描述带'如有变更,无变化填空',v1.74 应该删掉"""
    m = re.search(r'"world_extract":\s*\((.+?)\),\s*\n\s+"long_term', SRC, re.S)
    body = m.group(1)
    
    # 找 hero_state 字段那一行
    hero_line_m = re.search(r'"hero_state":\s*\{\{[^}]+\}\}', body)
    assert hero_line_m, "找不到 hero_state 字段描述"
    hero_line = hero_line_m.group(0)
    
    # age 字段描述里不应再写 diff 语义
    assert "无变化" not in hero_line, \
        f"hero_state 字段描述还有 diff 字眼: {hero_line[:200]}"


def test_merge_into_charlib_updates_label_when_n_is_zero():
    """B 修:n_filled=0(AI 返回了 hero_state 但 5 字段全空)时,
    label 也要更新为'已同步但本章无变化',不能永远显示'未同步'"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_merge_into_charlib":
                    body_src = ast.unparse(m)
                    # 必须能处理 n=0 / else 分支
                    assert "本章" in body_src and "无变化" in body_src, \
                        "n=0 时没有'本章无变化'的 label 文案"
                    # 必须有 else 分支处理 n=0 的情况
                    assert "lbl_hero_source" in body_src, \
                        "_merge_into_charlib 没操作 lbl_hero_source"
                    return
    pytest.fail("找不到 MainWindow._merge_into_charlib")


def test_merge_into_charlib_has_diagnostic_log():
    """C 修:必须有诊断日志,记录 AI 实际返回的 hero_state 内容"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_merge_into_charlib":
                    body_src = ast.unparse(m)
                    # 必须有日志打印 AI 实际返回内容
                    assert ("hero_state v1.74" in body_src 
                            or "hero_state]" in body_src), \
                        "_merge_into_charlib 没加 hero_state 诊断日志"
                    # 日志要打印 5 字段内容
                    assert "age" in body_src and "realm" in body_src, \
                        "诊断日志没打印 5 字段实际值"
                    return
    pytest.fail("找不到 MainWindow._merge_into_charlib")


# ── 行为层 ──────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture()
def char_lib(app):
    from novel_ai import CharacterLibrary
    return CharacterLibrary()


def test_apply_hero_state_dict_fills_nonempty(char_lib):
    """5 字段都给非空值时,n_filled=5"""
    hs = {
        "age": "19",
        "realm": "筑基初期",
        "location": "天剑宗",
        "faction": "天剑宗内门",
        "mood": "决绝",
    }
    n = char_lib.apply_hero_state_dict(hs)
    assert n == 5
    assert char_lib.hero_age.text() == "19"
    assert char_lib.hero_realm.text() == "筑基初期"
    assert char_lib.hero_mood.text() == "决绝"


def test_apply_hero_state_dict_skips_empty(char_lib):
    """空字符串值会被跳过(只算非空)"""
    # 先填一个基线
    char_lib.hero_realm.setText("练气期一层")
    
    hs = {"age": "20", "realm": "", "location": "", "faction": "", "mood": ""}
    n = char_lib.apply_hero_state_dict(hs)
    assert n == 1  # 只有 age 非空
    assert char_lib.hero_age.text() == "20"
    # realm 没动
    assert char_lib.hero_realm.text() == "练气期一层"


def test_apply_hero_state_dict_returns_zero_for_empty_dict(char_lib):
    """空 dict / 全空字符串 → n_filled=0(触发 v1.74 的 label fallback)"""
    n = char_lib.apply_hero_state_dict({})
    assert n == 0
    
    n2 = char_lib.apply_hero_state_dict(
        {"age": "", "realm": "", "location": "", "faction": "", "mood": ""})
    assert n2 == 0
