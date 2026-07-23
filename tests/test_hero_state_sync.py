"""测试 v1.64 主角状态自动同步:
  A) 从时间线 state_change 一键同步(本地正则)
  B) world_extract 的 hero_state 字段 → apply_hero_state_dict
  D) UI 只读 / 手动改切换 / 来源 label
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
from PyQt5.QtWidgets import QApplication, QTableWidgetItem


@pytest.fixture(scope="module")
def app():
    a = QApplication.instance() or QApplication(sys.argv)
    yield a


@pytest.fixture
def charlib(app):
    from novel_ai import CharacterLibrary
    return CharacterLibrary()


def _set_timeline(charlib, rows):
    """快速给 timeline 表填数据"""
    charlib.tbl_timeline.setRowCount(0)
    for row in rows:
        r = charlib.tbl_timeline.rowCount()
        charlib.tbl_timeline.insertRow(r)
        for c, v in enumerate(row):
            charlib.tbl_timeline.setItem(r, c, QTableWidgetItem(str(v)))


# ────── D:UI 状态切换 ──────

def test_hero_fields_default_readonly(charlib):
    """5 个字段默认只读"""
    for ed in charlib._hero_edits:
        assert ed.isReadOnly(), f"{ed.objectName() or '某字段'} 不是只读"


def test_unlock_button_toggles_readonly(charlib):
    """点解锁按钮 → 可编辑;再点 → 只读"""
    charlib.btn_unlock_hero.setChecked(True)
    for ed in charlib._hero_edits:
        assert not ed.isReadOnly()
    
    charlib.btn_unlock_hero.setChecked(False)
    for ed in charlib._hero_edits:
        assert ed.isReadOnly()


def test_unlock_changes_source_label(charlib):
    """切手动模式时 label 文本变化"""
    text_before = charlib.lbl_hero_source.text()
    charlib.btn_unlock_hero.setChecked(True)
    text_after = charlib.lbl_hero_source.text()
    assert text_before != text_after
    assert "手动" in text_after
    charlib.btn_unlock_hero.setChecked(False)


# ────── A:_extract_hero_from_timeline ──────

def test_extract_realm_simple(charlib):
    rows = [("5", "破境之战", "晋升金丹中期")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "realm" in result
    assert "金丹中期" in result["realm"][0]
    assert result["realm"][1] == 5


def test_extract_location(charlib):
    rows = [("3", "南下", "抵达青云山")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "location" in result
    assert "青云山" in result["location"][0]


def test_extract_faction(charlib):
    rows = [("7", "拜师", "加入天剑宗")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "faction" in result
    assert "天剑宗" in result["faction"][0]


def test_extract_age(charlib):
    rows = [("10", "成年", "年龄 22 岁")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "age" in result
    assert result["age"][0] == "22"


def test_extract_mood(charlib):
    rows = [("4", "灭门", "心境 决绝")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "mood" in result
    assert "决绝" in result["mood"][0]


def test_extract_takes_latest_chapter(charlib):
    """多章命中 → 取章节号最大的(最新)"""
    rows = [
        ("2", "初见", "晋升练气三层"),
        ("10", "突破", "晋升金丹初期"),
        ("5", "中段", "晋升筑基后期"),
    ]
    result = charlib._extract_hero_from_timeline(rows)
    assert result["realm"][0].startswith("金丹") or "金丹" in result["realm"][0]
    assert result["realm"][1] == 10


def test_extract_all_five_fields(charlib):
    """5 字段都能同时识别"""
    rows = [
        ("8", "终战", "晋升元婴期"),
        ("7", "南下", "抵达雪山秘境"),
        ("6", "拜师", "加入云隐门"),
        ("9", "庆功", "年龄 25 岁"),
        ("10", "结尾", "心境 平静"),
    ]
    result = charlib._extract_hero_from_timeline(rows)
    assert set(result.keys()) == {"realm", "location", "faction", "age", "mood"}


def test_extract_empty_timeline(charlib):
    """空时间线 → 空 dict"""
    assert charlib._extract_hero_from_timeline([]) == {}


def test_extract_no_state_change(charlib):
    """state_change 列为空 → 不命中"""
    rows = [("1", "事件 A", ""), ("2", "事件 B", "")]
    result = charlib._extract_hero_from_timeline(rows)
    assert result == {}


def test_extract_irrelevant_text_safe(charlib):
    """随便写的 state_change 不会乱命中"""
    rows = [("1", "事件", "这只是普通的句子,没有关键词")]
    result = charlib._extract_hero_from_timeline(rows)
    # 没修为/位置/势力关键词,应该 ≤1 个命中(可能 mood 误命中,可接受)
    assert "realm" not in result
    assert "location" not in result
    assert "faction" not in result


def test_extract_xinjing_not_match_realm(charlib):
    """v1.64 bug:'心境 决绝' 不能被 realm 误命中为'心境'"""
    rows = [("10", "决战", "心境 决绝")]
    result = charlib._extract_hero_from_timeline(rows)
    # realm 不该命中(因为'心境'不是修仙体系关键词)
    if "realm" in result:
        assert result["realm"][0] != "心境", \
            f"误把'心境'识别为修为:{result['realm']}"
    # mood 应该命中
    assert "mood" in result
    assert "决绝" in result["mood"][0]


def test_extract_realm_whitelist(charlib):
    """主流修仙体系都能识别 + 独立词模式"""
    rows = [("5", "突破", "金丹中期")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "realm" in result
    assert "金丹" in result["realm"][0]
    
    rows = [("8", "破境", "元婴初期")]
    result = charlib._extract_hero_from_timeline(rows)
    assert "realm" in result
    assert "元婴" in result["realm"][0]


# ────── A:_sync_hero_from_timeline(按钮触发)──────

def test_sync_fills_fields(charlib, monkeypatch):
    """同步后字段被填,只读状态保持"""
    _set_timeline(charlib, [
        ("5", "破境", "晋升金丹中期"),
        ("3", "迁徙", "抵达青云山"),
    ])
    # 拦截 QMessageBox(避免阻塞)— 用 monkeypatch,测试结束自动还原,
    # 直接赋值会把污染留给同进程后续所有测试
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: 0))
    
    charlib._sync_hero_from_timeline()
    
    # 字段被填
    assert "金丹中期" in charlib.hero_realm.text()
    assert "青云山" in charlib.hero_location.text()
    # 只读保持
    assert charlib.hero_realm.isReadOnly()


def test_sync_updates_source_label(charlib, monkeypatch):
    """同步后 label 显示来源章节"""
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: 0))
    _set_timeline(charlib, [("5", "破境", "晋升金丹中期")])
    charlib._sync_hero_from_timeline()
    text = charlib.lbl_hero_source.text()
    assert "5" in text
    assert "时间线" in text or "同步" in text


def test_sync_preserves_existing_fields_when_not_matched(charlib, monkeypatch):
    """未命中的字段保留原值"""
    from PyQt5.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information",
                        staticmethod(lambda *a, **k: 0))
    # 提前手填一个值
    charlib.btn_unlock_hero.setChecked(True)
    charlib.hero_faction.setText("已存在势力")
    charlib.btn_unlock_hero.setChecked(False)
    
    # 同步只命中 realm(没 faction 关键词)
    _set_timeline(charlib, [("5", "事件", "晋升金丹中期")])
    charlib._sync_hero_from_timeline()
    
    assert "金丹中期" in charlib.hero_realm.text()
    assert charlib.hero_faction.text() == "已存在势力"


# ────── B:apply_hero_state_dict ──────

def test_apply_hero_state_basic(charlib):
    n = charlib.apply_hero_state_dict({
        "age": "20",
        "realm": "金丹后期",
        "location": "天剑宗",
        "faction": "天剑宗",
        "mood": "坚定",
    })
    assert n == 5
    assert charlib.hero_age.text() == "20"
    assert charlib.hero_realm.text() == "金丹后期"
    assert charlib.hero_location.text() == "天剑宗"
    assert charlib.hero_faction.text() == "天剑宗"
    assert charlib.hero_mood.text() == "坚定"


def test_apply_hero_state_skips_empty(charlib):
    """空字符串不覆盖"""
    charlib.btn_unlock_hero.setChecked(True)
    charlib.hero_realm.setText("旧修为")
    charlib.btn_unlock_hero.setChecked(False)
    
    n = charlib.apply_hero_state_dict({"realm": "", "age": "30"})
    assert n == 1  # 只填了 age,realm 是空字符串被跳过
    assert charlib.hero_realm.text() == "旧修为"


def test_apply_hero_state_in_manual_mode_skipped(charlib):
    """手动模式时 AI 自动同步被跳过,保护用户手填值"""
    charlib.btn_unlock_hero.setChecked(True)
    charlib.hero_realm.setText("用户手填的特殊修为")
    
    n = charlib.apply_hero_state_dict({"realm": "AI 想填的修为"})
    assert n == 0   # 手动模式跳过
    assert charlib.hero_realm.text() == "用户手填的特殊修为"
    
    charlib.btn_unlock_hero.setChecked(False)


def test_apply_hero_state_preserves_readonly(charlib):
    """填完后字段保持只读"""
    assert charlib.hero_realm.isReadOnly()  # 默认
    charlib.apply_hero_state_dict({"realm": "测试修为"})
    assert charlib.hero_realm.isReadOnly()  # 填完仍只读


def test_apply_hero_state_empty_dict_safe(charlib):
    n = charlib.apply_hero_state_dict({})
    assert n == 0


def test_apply_hero_state_none_safe(charlib):
    n = charlib.apply_hero_state_dict(None)
    assert n == 0


# ────── world_extract prompt 含 hero_state 字段 ──────

def test_world_extract_prompt_has_hero_state():
    """v1.64 prompt 模板新增 hero_state 顶层字段"""
    from novel_ai import PROMPTS
    tpl = PROMPTS["world_extract"]
    assert "hero_state" in tpl
    assert "age" in tpl and "realm" in tpl and "mood" in tpl
