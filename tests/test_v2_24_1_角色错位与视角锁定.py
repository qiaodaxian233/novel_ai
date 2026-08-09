# -*- coding: utf-8 -*-
"""v2.24.1 角色三层错位 + 情境视角锁定 守护测试

来源:用户写作理论笔记
- 角色问题:嘴上说的/心里想的/手上做的要都不一样,这样才塑造讨喜角色
- 情绪视角:一个情境下不要频繁切换视角,保证情感不脱节
"""
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return io.open(ROOT / rel, encoding="utf-8").read()


# ---------- 1. 写作端 ----------

def test_core_rules_contain_mismatch_rule():
    import pangu_system
    rules = pangu_system.PANGU_CORE_RULES
    assert "【角色铁律·三层错位】" in rules
    assert "嘴上说的、心里想的、手上做的" in rules
    # 三个关键约束:有因/不点破/路人豁免
    assert "错位要有因" in rules
    assert "不准替读者点破" in rules
    assert "路人和功能性角色不需要错位" in rules


def test_pov_rule_has_scene_lock():
    import pangu_system
    rules = pangu_system.PANGU_CORE_RULES
    assert "情境内锁定" in rules
    assert "转场才允许换" in rules


# ---------- 2. 质检端 ----------

def test_new_prompts_exist_and_render():
    from core.prompts import PROMPTS
    for key, kws in {
        "critique_mismatch": ("心口如一", "错位无因", "直给拆穿", "错位泛滥"),
        "critique_pov_lock": ("场景内跳视角", "上帝视角乱入", "无标记转场"),
    }.items():
        assert key in PROMPTS
        rendered = PROMPTS[key].format(content="测试正文ABC")
        assert "测试正文ABC" in rendered
        assert '"score"' in rendered
        for kw in kws:
            assert kw in rendered, f"{key} 缺维度: {kw}"


def test_character_critic_no_longer_punishes_subtext():
    """人设稽核与三层错位不能打架:潜台词式不一致不算 OOC"""
    from core.prompts import PROMPTS
    rendered = PROMPTS["critique_character"].format(characters="C", content="X")
    assert "不算 OOC" in rendered
    assert "核心动机" in rendered


# ---------- 3. 接线端(源码文本断言) ----------

def test_novel_ai_wiring():
    src = _read("novel_ai.py")
    for kw in (
        'cfg.get("mismatch")', 'cfg.get("pov_lock")',
        'next_kind == "mismatch"', 'next_kind == "pov_lock"',
        'PROMPTS["critique_mismatch"]', 'PROMPTS["critique_pov_lock"]',
        'target="critique_mismatch"', 'target="critique_pov_lock"',
        '"mismatch": "三层错位"', '"pov_lock": "视角锁定"',
        'target == "critique_mismatch"', 'target == "critique_pov_lock"',
        '"错位稽核" in _tid', '"视角稽核" in _tid',
    ):
        assert kw in src, f"novel_ai.py 缺接线: {kw}"
    wl = src.split("SECONDARY_AI_TARGETS")[1][:800]
    assert '"critique_mismatch"' in wl and '"critique_pov_lock"' in wl


def test_generation_control_wiring():
    src = _read("ui/tabs/generation_control.py")
    for kw in ("chk_crit_mismatch", "chk_crit_pov",
               '"crit.mismatch"', '"crit.pov"',
               '"mismatch":', '"pov_lock":'):
        assert kw in src, f"generation_control.py 缺接线: {kw}"
