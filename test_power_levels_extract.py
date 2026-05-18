"""v1.74 战力体系自动抽取测试

覆盖:
- world_extract prompt 包含 power_levels 字段说明 + 规则
- _on_world_extract_received 的 all_empty 检测也算 power_levels
- _merge_into_charlib 加 power 合并(MainWindow)
- CharacterLibrary.merge_dicts 加 power 合并 + DICT_KEY_MAPS_LOCAL 加 power_levels
- 去重 key=realm+level 工作正确
- APP_VERSION >= v1.74
"""
import os
import sys
import re
import ast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(__file__)
SRC = open(os.path.join(HERE, "novel_ai.py"), encoding="utf-8").read()


# ── prompt 层 ──────────────────────────────────────────

def test_world_extract_prompt_has_power_levels_field():
    """prompt 必须告诉 AI 输出 power_levels 数组"""
    # 找 world_extract 部分
    m = re.search(r'"world_extract":\s*\((.+?)\),\s*\n\s+"long_term', SRC, re.S)
    assert m, "找不到 world_extract prompt"
    body = m.group(1)
    assert '"power_levels"' in body, "prompt 没声明 power_levels 字段"
    assert '"realm"' in body and '"level"' in body, "power_levels 子字段缺失"


def test_world_extract_prompt_has_power_rule():
    """prompt 提取规则必须明确 power_levels 抽什么"""
    m = re.search(r'"world_extract":\s*\((.+?)\),\s*\n\s+"long_term', SRC, re.S)
    body = m.group(1)
    # 规则 7 应该提到 power_levels
    assert "power_levels" in body and "修炼层级" in body, \
        "提取规则没说明 power_levels 该抽什么"


def test_world_extract_prompt_hero_state_is_snapshot():
    """v1.74:hero_state 必须是快照模式,不是 diff(根因修复)"""
    m = re.search(r'"world_extract":\s*\((.+?)\),\s*\n\s+"long_term', SRC, re.S)
    body = m.group(1)
    # 不能再有"无变化填空字符串"这种 diff 语义
    assert "本章无变化的字段填" not in body, \
        "prompt 规则 7 还是 diff 模式(根因没修)"
    # 必须明确说快照
    assert "快照" in body, "prompt 没说 hero_state 是快照"


# ── 代码集成层 ──────────────────────────────────────────

def test_all_empty_check_includes_power_levels():
    """_on_world_extract_received 的 all_empty 检测要把 power_levels 算上,
    否则 AI 只返回战力时会被误判为'全空'触发重试"""
    # 找 all_empty 这一段
    m = re.search(
        r"all_empty\s*=\s*not\s+any\(\s*.+?for\s+k\s+in\s*\n?\s*\(([^)]+)\)",
        SRC, re.S)
    assert m, "找不到 all_empty 检测"
    keys_text = m.group(1)
    assert '"power_levels"' in keys_text, \
        f"all_empty 检测漏算 power_levels: {keys_text}"


def test_merge_into_charlib_has_power_section():
    """_merge_into_charlib 必须有 power_levels 合并代码段"""
    # 找 _merge_into_charlib 方法
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "_merge_into_charlib":
                    body_src = ast.unparse(m)
                    assert "power_levels" in body_src, \
                        "_merge_into_charlib 没处理 power_levels"
                    assert "tbl_power" in body_src, \
                        "_merge_into_charlib 没操作 tbl_power"
                    assert "added['pw']" in body_src or 'added["pw"]' in body_src, \
                        "_merge_into_charlib 没累加 pw 计数"
                    return
    pytest.fail("找不到 MainWindow._merge_into_charlib")


def test_merge_dicts_has_power_in_dict_key_maps():
    """CharacterLibrary.merge_dicts 的 DICT_KEY_MAPS_LOCAL 必须包含 power_levels,
    否则用户导入外部 JSON 时战力体系会被忽略"""
    tree = ast.parse(SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "CharacterLibrary":
            for m in node.body:
                if isinstance(m, ast.FunctionDef) and m.name == "merge_dicts":
                    body_src = ast.unparse(m)
                    assert "power_levels" in body_src, \
                        "CharacterLibrary.merge_dicts 没处理 power_levels"
                    assert "tbl_power" in body_src, \
                        "CharacterLibrary.merge_dicts 没操作 tbl_power"
                    return
    pytest.fail("找不到 CharacterLibrary.merge_dicts")


def test_log_message_shows_power_count():
    """_on_world_extract_received 的成功日志必须显示战力 +N"""
    m = re.search(r"def _on_world_extract_received.*?(?=\n    def )", SRC, re.S)
    assert m, "找不到 _on_world_extract_received"
    body = m.group(0)
    assert 'pw_n' in body or '"pw"' in body, "成功日志没拿 pw 计数"
    assert "战力" in body, "成功日志没显示'战力'"


# ── 行为层(用真 PyQt 跑) ─────────────────────────────

@pytest.fixture(scope="module")
def app():
    """单例 QApplication,用于实例化 CharacterLibrary"""
    from PyQt5.QtWidgets import QApplication
    a = QApplication.instance() or QApplication(sys.argv)
    return a


@pytest.fixture()
def char_lib(app):
    from novel_ai import CharacterLibrary
    return CharacterLibrary()


def test_merge_dicts_inserts_power_rows(char_lib):
    """新增 power 条目能写入表格"""
    data = {
        "power_levels": [
            {"realm": "练气期", "level": "一层", "power": "凡人之上",
             "note": "灵气入体"},
            {"realm": "练气期", "level": "九层", "power": "可破筑基初期",
             "note": "灵气大圆满"},
        ]
    }
    n_before = char_lib.tbl_power.rowCount()
    added = char_lib.merge_dicts(data)
    assert added["pw"] == 2
    assert char_lib.tbl_power.rowCount() == n_before + 2


def test_merge_dicts_dedupe_power(char_lib):
    """同样的 realm+level 不重复插入"""
    data = {
        "power_levels": [
            {"realm": "金丹期", "level": "中期", "power": "X", "note": ""},
        ]
    }
    char_lib.merge_dicts(data)
    # 再合并一次
    added2 = char_lib.merge_dicts(data)
    assert added2["pw"] == 0, "重复条目应该被去重"


def test_merge_dicts_skips_empty_realm(char_lib):
    """没大段(realm)的条目应该被跳过"""
    data = {
        "power_levels": [
            {"realm": "", "level": "中期", "power": "X"},
        ]
    }
    added = char_lib.merge_dicts(data)
    assert added["pw"] == 0


def test_merge_dicts_tolerates_list_of_list(char_lib):
    """list-of-list 也能正确合并(铁律 6)"""
    data = {
        "power_levels": [
            ["元婴期", "初期", "横扫金丹", "凝丹成婴"],
        ]
    }
    added = char_lib.merge_dicts(data)
    assert added["pw"] == 1
    last_row = char_lib.tbl_power.rowCount() - 1
    assert char_lib.tbl_power.item(last_row, 0).text() == "元婴期"
    assert char_lib.tbl_power.item(last_row, 1).text() == "初期"


# ── 版本守 ──────────────────────────────────────────

def test_app_version_at_least_v1_74():
    """APP_VERSION 至少升到 v1.74"""
    m = re.search(r'APP_VERSION\s*=\s*"v(\d+)\.(\d+)"', SRC)
    assert m, "找不到 APP_VERSION"
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 74), \
        f"APP_VERSION = v{major}.{minor},应该 ≥ v1.74"
