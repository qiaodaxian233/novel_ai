# -*- coding: utf-8 -*-
"""v2.24.0 代入感(MRU)稽核 守护测试

覆盖三层:
1. 写作端:PANGU_CORE_RULES 含【代入感铁律】,且与情绪铁律/六戒⑤不再矛盾
2. 质检端:PROMPTS['critique_mru'] 存在、可渲染、输出严格 JSON 指令
3. 接线端:novel_ai.py / generation_control.py 源码含 mru 稽核链全部挂点
   (源码文本断言,避免在无 PyQt5 环境 import GUI 模块)
"""
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return io.open(ROOT / rel, encoding="utf-8").read()


# ---------- 1. 写作端 ----------

def test_core_rules_contain_mru_rule():
    import pangu_system
    rules = pangu_system.PANGU_CORE_RULES
    assert "【代入感铁律】" in rules
    assert "刺激→感受→反应" in rules
    assert "先动作,后语言" in rules
    assert "无源反应" in rules
    # 要素可缺省但顺序不可乱
    assert "顺序绝不可颠倒" in rules


def test_emotion_rule_no_longer_conflicts_with_jie5():
    """旧版矛盾:情绪铁律要求'直给情绪词',六戒⑤禁止'直接贴标签'。
    新版裁决:短直给合法,放大词/多句渲染违规。两处都要有裁决痕迹。"""
    import pangu_system
    rules = pangu_system.PANGU_CORE_RULES
    # 情绪铁律改版:不再鼓励用标签替代身体细节
    assert "她的手指无意识地绞着衣角" not in rules
    assert "禁长句渲染和放大词" in rules
    # 六戒⑤补充裁决线
    assert "不算贴标签" in rules


# ---------- 2. 质检端 ----------

def test_critique_mru_prompt_exists_and_renders():
    from core.prompts import PROMPTS
    assert "critique_mru" in PROMPTS
    rendered = PROMPTS["critique_mru"].format(content="测试正文ABC")
    assert "测试正文ABC" in rendered
    assert "严格 JSON" in rendered
    assert '"score"' in rendered
    # 四个扣分维度齐全
    for kw in ("无源反应", "顺序颠倒", "刺激模糊", "感受拖沓"):
        assert kw in rendered, f"缺扣分维度: {kw}"


# ---------- 3. 接线端(源码文本断言) ----------

def test_novel_ai_wiring():
    src = _read("novel_ai.py")
    # 稽核链入口
    assert 'cfg.get("mru")' in src
    assert '"remaining"].append("mru")' in src.replace("audit_state[", "")
    # 分支派发
    assert 'next_kind == "mru"' in src
    assert 'PROMPTS["critique_mru"]' in src
    assert 'target="critique_mru"' in src
    # 打分回调 label
    assert '"mru": "代入感"' in src
    # dispatch 兜底
    assert 'target == "critique_mru"' in src
    # BUG-077 覆写安全网
    assert '"代入感稽核" in _tid' in src
    # 副 AI 白名单
    assert '"critique_mru"' in src.split("SECONDARY_AI_TARGETS")[1][:600]


def test_generation_control_wiring():
    src = _read("ui/tabs/generation_control.py")
    assert "chk_crit_mru" in src
    assert '"crit.mru"' in src          # 持久化
    assert '"mru":' in src               # critique_config 键
