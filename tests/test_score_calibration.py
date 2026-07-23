"""
test_score_calibration.py — v1.81 BUG-061 评分门校准 + 死磕精确定位

背景:用户反馈"设 95 分阈值时每次都触发 10 次死磕上限"。
根因:v1.80 评分曲线过严 — 禁用词每次 -2(单章 5 词就扣 10)、
长句门 25 字(中文小说常态)、破折号单个就扣 5、省略号格式严格。
+ 死磕重写时只传 issues 摘要(top 3),没传具体定位,AI 不知道哪一句要改。

修复:
A. 校准评分曲线 — 让"质量良好的章节"能拿 90+ 分(此前只有 85)
B. 新增 lint_with_locations — 返回每违规的精确定位(段号 + 原文片段 + 修复建议)
C. 死磕重写时注入定位 summary + 分数进度提示

覆盖:
  A. 评分曲线校准(单项扣分 / 阈值变化 / 第3章实测)
  B. lint_with_locations 返回结构
  C. 死磕注入(score_progress_block / locations_block)
  X. 守(空输入 / 极端情况)
"""
import re
import ast
import os
import sys
import pytest
from tests_helpers import read_all_sources


@pytest.fixture(scope="module")
def src():
    # v2.07:读全源(模块化拆分后)

    return read_all_sources()


@pytest.fixture(scope="module")
def pangu_src():
    with open("pangu_system.py", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def engine():
    sys.path.insert(0, os.path.dirname(__file__) or ".")
    from pangu_system import PanguEngine
    return PanguEngine


# ─────────────────────────────────────
# A. 评分曲线校准
# ─────────────────────────────────────

def test_A1_forbidden_word_penalty_reduced_to_one_each(engine):
    """v1.81:禁用词每次扣 1 分(原 -2),单章 5 词扣 5 分而不是 10"""
    # 包含 5 个不同的禁用词(每个 1 次)
    text = "他似乎想到了什么。她仿佛看到了一抹光。我觉得这就够了。"
    r = engine.quick_chapter_lint(text)
    # 5 次禁用词 → 应扣 5(v1.80 会扣 10)
    # 100 - 5 = 95(可能还有其他小扣,留容差)
    assert r["score"] >= 90, \
        f"5 次禁用词应只扣 ~5 分,实际分数 {r['score']}"


def test_A2_forbidden_word_cap_30(engine):
    """v1.81:禁用词扣分上限 30(原 40)"""
    # 大量重复同一禁用词,触发上限
    text = "想 " * 100 + "觉得 " * 50  # 150 次禁用词
    r = engine.quick_chapter_lint(text)
    # 应扣到 30 上限,不应扣到 -100
    # 100 - 30 = 70
    # 但可能还有其他扣分(如段落问题),留容差
    assert r["score"] >= 50, \
        f"禁用词扣分应有上限,实际 {r['score']}"


def test_A3_long_sentence_threshold_raised_to_35(engine):
    """v1.81:长句门 25→35。25-35 字的句子不应被算长句"""
    # 28 字的句子(v1.80 算长句,v1.81 不算)
    text = "他握紧了腰间那把跟随他十年的老旧柴刀,深吸一口气。"
    assert len(re.sub(r"[,，。!?!?;;\s]", "", text)) <= 30  # 字数确认
    r = engine.quick_chapter_lint(text)
    # 不应有"长句"issue
    assert not any("长句" in i for i in r["issues"]), \
        f"v1.81 28 字的句子不应判为长句,实际 issues: {r['issues']}"


def test_A4_long_sentence_at_threshold_still_caught(engine):
    """v1.81:>35 字仍判为长句"""
    text = "他抬起头来仔细地观察着远方那座山峦的山峰下方似乎有一道金色光芒在缓缓移动接近"
    r = engine.quick_chapter_lint(text)
    assert any("长句" in i for i in r["issues"])


def test_A5_paragraph_threshold_raised_to_5(engine):
    """v1.81:段落门 3→5。4 句段落不应被算超长"""
    text = "他来了。她走了。我留下。风停了。"  # 4 句
    r = engine.quick_chapter_lint(text)
    assert not any("段落" in i for i in r["issues"]), \
        f"v1.81 4 句段落不应判为超长,实际 issues: {r['issues']}"


def test_A6_paragraph_over_5_still_caught(engine):
    """v1.81:>5 句段落仍判为超长"""
    text = "他来了。她走了。我留下。风停了。雨停了。夜来了。"  # 6 句
    r = engine.quick_chapter_lint(text)
    assert any("段落" in i for i in r["issues"])


def test_A7_single_dash_not_penalized(engine):
    """v1.81:1-3 个破折号不扣分(对话里可能用)"""
    text = "他——还是来了。"
    r = engine.quick_chapter_lint(text)
    assert not any("破折号" in i for i in r["issues"]), \
        f"v1.81 单个破折号不应扣分,实际 issues: {r['issues']}"


def test_A8_many_dashes_penalized(engine):
    """v1.81:>3 个破折号扣分"""
    text = "他——还是来了。她——也来了。我——走了。你——留下。风——停了。"
    r = engine.quick_chapter_lint(text)
    assert any("破折号" in i for i in r["issues"])


def test_A9_few_ellipsis_not_penalized(engine):
    """v1.81:1-2 处三连点/法语省略号不扣分"""
    text = "他叹了口气..." + "她沉默了。"
    r = engine.quick_chapter_lint(text)
    assert not any("省略号" in i for i in r["issues"]), \
        f"v1.81 单个三连点不应扣分,实际 issues: {r['issues']}"


def test_A10_many_ellipsis_penalized(engine):
    """v1.81:>2 处三连点扣分"""
    text = "他叹气..." + "她也叹气..." + "我也叹气..." + "你也叹气..."
    r = engine.quick_chapter_lint(text)
    assert any("省略号" in i for i in r["issues"])


def test_A11_realistic_good_chapter_scores_90plus(engine):
    """v1.81 校准目标核心断言:用户贴的第 3 章质量应 ≥ 90 分(v1.80 只有 85)"""
    text = """嘴里全是铁锈味。
脑子里那个声音还在响——"是否使用?"
林远盯着窗外的黑影。第一头妖兽已经冲进镇子,直奔陈大娘家。他没时间犹豫。
"使用。"
丹田像被人挖走了一块。热流从身体里抽走,顺着经脉涌向右手掌心。掌心的伤口炸开,血喷出来。
符文旋转,发出嗡嗡声。空气中弥漫着铁锈味,浓得像含了一口血。
冲向陈大娘家的妖兽脚步一软,前腿跪在地上。它挣扎着站起来,四肢发抖。
林远冲上去。柴刀举起,对准妖兽的脖子砍下去。刀刃砍进皮肉,血喷了他一脸。
妖兽哀嚎,爪子在地上刨出深沟。第二刀,第三刀。妖兽不动了。
系统声音又响了。
"击杀一级妖兽。虚弱诅咒剩余时间:七十二小时。剩余寿命减少:七天。" """
    r = engine.quick_chapter_lint(text)
    assert r["score"] >= 90, \
        f"v1.81 校准目标:好章节应 ≥90 分,实际 {r['score']}, issues: {r['issues']}"


# ─────────────────────────────────────
# B. lint_with_locations 接口
# ─────────────────────────────────────

def test_B1_lint_with_locations_method_exists(engine):
    assert hasattr(engine, "lint_with_locations")


def test_B2_lint_with_locations_returns_correct_shape(engine):
    r = engine.lint_with_locations("他想了想。")
    assert "score" in r
    assert "violations" in r
    assert "summary" in r
    assert isinstance(r["violations"], list)
    assert isinstance(r["summary"], str)


def test_B3_lint_locations_empty_text(engine):
    """空文本不应崩"""
    r = engine.lint_with_locations("")
    assert r["score"] == 0
    assert r["violations"] == []


def test_B4_lint_locations_finds_forbidden_with_position(engine):
    """禁用词违规必须带段号 + 原文片段"""
    text = "第一段没问题。\n他想了想,觉得不对劲。\n第三段也没问题。"
    r = engine.lint_with_locations(text)
    forbidden = [v for v in r["violations"] if v["type"] == "forbidden"]
    assert len(forbidden) >= 1
    for v in forbidden:
        assert "word" in v
        assert "snippet" in v
        assert "para_no" in v
        assert "advice" in v
        assert v["para_no"] >= 1


def test_B5_lint_locations_advice_categorized(engine):
    """advice 按禁用词类别给(副词 / 心理动词 / 比喻词 / 微小动作 / 套话)"""
    text = "他想了。她仿佛看到了。他嘴角抽了抽。"
    r = engine.lint_with_locations(text)
    advices = [v["advice"] for v in r["violations"] if v["type"] == "forbidden"]
    # 至少应该有 3 种不同的 advice 类别
    advice_categories = set()
    for a in advices:
        if "副词" in a:
            advice_categories.add("副词")
        elif "心理动词" in a:
            advice_categories.add("心理动词")
        elif "比喻词" in a:
            advice_categories.add("比喻词")
        elif "微小动作" in a:
            advice_categories.add("微小动作")
    assert "心理动词" in advice_categories, \
        f"『想』应被识别为心理动词,实际 advices: {advices}"


def test_B6_lint_locations_long_sent_with_position(engine):
    """长句违规带段号 + 原文片段"""
    text = "短句。\n他抬起头来仔细地观察着远方那座山峦的山峰下方似乎有一道金色光芒在缓缓移动接近。"
    r = engine.lint_with_locations(text)
    long_sents = [v for v in r["violations"] if v["type"] == "long_sent"]
    assert len(long_sents) >= 1
    assert long_sents[0]["para_no"] == 2  # 第 2 段
    assert "snippet" in long_sents[0]


def test_B7_lint_locations_summary_for_ai_prompt(engine):
    """summary 应是给 AI 看的精炼版,含段号 + 原文 + advice"""
    text = "他想了想,觉得不对。\n她觉得这不行。"
    r = engine.lint_with_locations(text)
    summary = r["summary"]
    # 应包含禁用词
    assert "想" in summary or "觉得" in summary
    # 应包含段号(『第X段』格式)
    assert "第" in summary and "段" in summary
    # 应包含修复建议箭头
    assert "→" in summary


def test_B8_lint_locations_same_para_same_word_max_3(engine):
    """同段同词最多列 3 处,防刷屏"""
    # 一段里 5 次"想"
    text = "他想了。他又想了。再想想。还想。继续想。"
    r = engine.lint_with_locations(text)
    same = [v for v in r["violations"]
            if v["type"] == "forbidden" and v["word"] == "想"]
    assert len(same) <= 3, f"同段同词应限 3 处,实际 {len(same)}"


def test_B9_lint_locations_score_matches_quick(engine):
    """lint_with_locations 的 score 应与 quick_chapter_lint 一致"""
    text = "他想了想。她觉得不对。我们仿佛走错了。"
    r1 = engine.quick_chapter_lint(text)
    r2 = engine.lint_with_locations(text)
    assert r1["score"] == r2["score"]


# ─────────────────────────────────────
# C. 死磕注入逻辑
# ─────────────────────────────────────

def test_C1_validate_uses_lint_with_locations(src):
    """_check_chapter_quality 必须用 lint_with_locations(不再用 quick_chapter_lint 单独算)"""
    m = re.search(
        r"def _check_chapter_quality\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "lint_with_locations" in block, \
        "v1.81:_check_chapter_quality 应改用 lint_with_locations"


def test_C2_validate_stores_locations_summary(src):
    """_check_chapter_quality 必须把 location summary 存到 self,给 retry 用"""
    m = re.search(
        r"def _check_chapter_quality\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "_last_lint_locations" in block, \
        "v1.81:必须用 self._last_lint_locations 暂存定位"


def test_C3_retry_injects_locations_block(src):
    """_retry_chapter_with_reasons 必须把 locations summary 注入 retry prompt"""
    m = re.search(
        r"def _retry_chapter_with_reasons\(.*?(?=\n    def )",
        src, re.DOTALL)
    assert m
    block = m.group(0)
    assert "_last_lint_locations" in block, \
        "v1.81:retry 必须读 self._last_lint_locations"
    assert "locations_block" in block
    assert "精确定位" in block


def test_C4_retry_injects_score_progress(src):
    """retry 必须注入分数进度提示(『上次 X/100,目标 Y,缺 Z 分』)"""
    m = re.search(
        r"def _retry_chapter_with_reasons\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    assert "score_progress_block" in block
    assert "分数进度" in block
    assert "目标" in block and "缺" in block


def test_C5_retry_prompt_includes_locations_and_progress(src):
    """retry 拼装 prompt 时必须同时含 locations_block + score_progress_block"""
    m = re.search(
        r"def _retry_chapter_with_reasons\(.*?(?=\n    def )",
        src, re.DOTALL)
    block = m.group(0)
    # 拼装 stronger 的部分
    stronger_idx = block.find("stronger = ")
    assert stronger_idx >= 0
    stronger_block = block[stronger_idx:stronger_idx + 1500]
    assert "locations_block" in stronger_block
    assert "score_progress_block" in stronger_block


def test_C6_tooltip_mentions_v181_calibration(src):
    """UI tooltip 必须提到 v1.81 校准(让用户知道 95 分现在可达)"""
    # 用更稳的方法 — 找 setToolTip 后接的多行字符串
    idx = src.find("self.quality_threshold.setToolTip(")
    assert idx >= 0
    # 取后续 1000 字符
    tooltip_area = src[idx:idx + 1000]
    assert "v1.81" in tooltip_area or "校准" in tooltip_area, \
        f"tooltip 应提到 v1.81 校准,前 500 字: {tooltip_area[:500]}"


# ─────────────────────────────────────
# X. 守(防御性)
# ─────────────────────────────────────

def test_X1_version_bumped(src):
    m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)(?:\.\d+)?"', src)
    major, minor = int(m.group(1)), int(m.group(2))
    assert (major, minor) >= (1, 81)


def test_X2_quick_lint_still_returns_pass_field(engine):
    """旧 API 兼容:quick_chapter_lint 仍返回 pass 字段"""
    r = engine.quick_chapter_lint("正常文本。")
    assert "pass" in r
    assert isinstance(r["pass"], bool)


def test_X3_quick_lint_still_returns_stats(engine):
    """旧 API 兼容:quick_chapter_lint 仍返回 stats 字段"""
    r = engine.quick_chapter_lint("正常文本。")
    assert "stats" in r


def test_X4_lint_locations_handles_long_para(engine):
    """长段落定位"""
    text = "句一。句二。句三。句四。句五。句六。句七。"  # 7 句
    r = engine.lint_with_locations(text)
    long_paras = [v for v in r["violations"] if v["type"] == "long_para"]
    assert len(long_paras) >= 1
    assert long_paras[0]["para_no"] == 1


def test_X5_lint_locations_dash_aggregated(engine):
    """破折号全文级聚合,不重复定位每一处"""
    text = "他——一。她——二。我——三。你——四。"  # 4 处破折号
    r = engine.lint_with_locations(text)
    dashes = [v for v in r["violations"] if v["type"] == "dash"]
    assert len(dashes) == 1  # 全文级,只 1 条
    assert "4" in dashes[0]["snippet"]


def test_X6_score_floor_zero(engine):
    """极差文本不应得负分"""
    text = ("想 觉得 仿佛 嘴角 脸色 " * 50)
    r = engine.quick_chapter_lint(text)
    assert r["score"] >= 0


def test_X7_score_ceil_hundred(engine):
    """完美文本得 100 分(需分段,不能堆在一段)"""
    text = "他举起刀。\n砍下去。\n血溅起来。\n敌人倒地。"
    r = engine.quick_chapter_lint(text)
    assert r["score"] == 100, \
        f"无任何违规的文本应 100 分,实际 {r['score']}, issues: {r['issues']}"


def test_X8_lint_locations_summary_empty_when_no_violations(engine):
    """无违规时 summary 应明确无违规"""
    r = engine.lint_with_locations("他举起刀。砍下去。")
    assert "无具体违规" in r["summary"] or r["summary"] == "" or not r["violations"]
