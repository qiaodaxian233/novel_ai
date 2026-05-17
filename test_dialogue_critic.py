# -*- coding: utf-8 -*-
"""dialogue_critic 单元测试"""
import dialogue_critic as dc


def test_say_density_normal():
    """正常密度章节不报错"""
    content = "林远走到门口。妹妹长大了,会拔剑了。" * 30   # 长 + 没"说"
    r = dc.DialogueCritic(content).static_scan()
    assert r.say_count == 0
    assert r.passed


def test_say_overload():
    """超标章节报红"""
    content = ("林远说:走。林悦说:不。赵乾说:留。" * 5)
    r = dc.DialogueCritic(content).static_scan()
    assert r.say_count >= 10
    assert not r.passed


def test_ban_word_detection():
    """套词命中红线"""
    content = "林远怒吼道:都给我滚!陈大娘喃喃道:孩子……"
    r = dc.DialogueCritic(content).static_scan()
    reds = [i for i in r.issues if i.kind == "ban_word"]
    assert len(reds) >= 2


def test_modifier_say():
    """修饰词+说命中"""
    content = "林远生气地说:你疯了。林悦担心地问:哥怎么了?"
    r = dc.DialogueCritic(content).static_scan()
    bans = [i for i in r.issues if i.kind == "ban_word"]
    assert any("生气地说" in i.msg for i in bans)


def test_consecutive_say():
    """连续 3 句 X 说"""
    content = "林说:走。陈说:好。赵说:留。"
    r = dc.DialogueCritic(content).static_scan()
    assert any(i.kind == "consecutive_say" for i in r.issues)


def test_clean_chapter_passes():
    """好章节不报红"""
    # 用 L1 动作卡位 + L6 标点替代 + L2 神态
    content = ("林远把血滴进凹槽。\n"
               "碑面黑得像一口棺材。\n\n"
               "「凡人。」山风灌进祠堂。\n"
               "他笑了。\n"
               "「赌赢了。」\n\n"
               "妹妹长大了,会拔剑了。") * 5
    r = dc.DialogueCritic(content).static_scan()
    assert r.passed
    reds = [i for i in r.issues if i.severity == "red"]
    assert len(reds) == 0


def test_ai_prompt_building():
    """AI prompt 构造完整"""
    content = "测试章节内容。" * 20
    critic = dc.DialogueCritic(content)
    prompt = critic.build_ai_prompt(deep=True, laodao=True)
    # 关键元素全在
    assert "13 法对话铁律" in prompt
    assert "L1 动作卡位" in prompt
    assert "L13 节奏开关" in prompt
    assert "JSON" in prompt
    assert "老刀" in prompt
    assert content in prompt


def test_parse_ai_response():
    """AI 返回 JSON 解析"""
    text = '''生成结果:```json
{"overall_score": 75, "L1": {"score": 8}, "verdict": "可以"}
```'''
    data = dc.parse_ai_response(text)
    assert data is not None
    assert data["overall_score"] == 75
    assert data["L1"]["score"] == 8


def test_format_report():
    """报告格式化"""
    static = dc.DialogueCritic("测试" * 100).static_scan()
    ai_data = {
        "overall_score": 80,
        "verdict": "整体不错",
        "best_3": ["L2", "L11"],
        "worst_3": ["L7", "L10"],
        "L1": {"score": 8, "evidence": "原文", "advice": "继续保持"},
    }
    report = dc.format_report(static, ai_data)
    assert "整体评分" in report
    assert "80/100" in report
    assert "L1" in report
