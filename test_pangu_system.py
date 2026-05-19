#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试:pangu_system 模块
===============================
跑法:  python -m unittest test_pangu_system.py -v
或:    python test_pangu_system.py
"""

import unittest
from pangu_system import (
    PanguEngine,
    PANGU_CORE_RULES,
    STYLE_MAPPING,
    GOLDEN_THREE_FORMULA,
    SPIRAL_OUTLINE_SPEC,
    MODE_PROMPTS,
    FIRST_ACTIVATION_BANNER,
    chapter_output_format,
    get_default_engine,
    wrap,
)


class TestPanguCore(unittest.TestCase):

    def setUp(self):
        self.engine = PanguEngine(enabled=True)
        self.engine_off = PanguEngine(enabled=False)

    # ---- wrap_prompt ----

    def test_wrap_chapter_includes_core_rules(self):
        out = self.engine.wrap_prompt("写第一章", scenario="chapter",
                                     ctx={"chapter_num": 1})
        self.assertIn("盘古", out)
        self.assertIn("禁用词强制过滤", out)
        self.assertIn("感官铁律", out)
        self.assertIn("写第一章", out)
        self.assertIn("本章完", out)  # 输出格式尾

    def test_wrap_chapter_includes_platform_hint_fanqie(self):
        out = self.engine.wrap_prompt("写正文", scenario="chapter",
                                     ctx={"platform": "番茄小说"})
        self.assertIn("番茄", out)
        self.assertIn("2000-2500", out)

    def test_wrap_chapter_includes_platform_hint_qidian(self):
        out = self.engine.wrap_prompt("写正文", scenario="chapter",
                                     ctx={"platform": "起点中文网"})
        self.assertIn("起点", out)
        self.assertIn("2500-3000", out)

    def test_wrap_bypass_when_disabled(self):
        original = "原始提示词不变"
        out = self.engine_off.wrap_prompt(original, scenario="chapter")
        self.assertEqual(out, original)

    def test_wrap_golden_three(self):
        out = self.engine.wrap_prompt("写黄金三章", scenario="golden_three")
        self.assertIn("黄金三章公式", out)
        self.assertIn("绝境+羞辱", out)
        self.assertIn("循环爽点单元", out)

    def test_wrap_outline_has_spiral(self):
        out = self.engine.wrap_prompt("写大纲", scenario="outline")
        self.assertIn("矛盾螺旋", out)
        self.assertIn("人物弧光三阶段", out)
        self.assertIn("P1", out)

    def test_wrap_title_bypassed(self):
        original = "请取书名"
        out = self.engine.wrap_prompt(original, scenario="title")
        self.assertEqual(out, original)

    def test_wrap_intro_bypassed(self):
        original = "请写简介"
        out = self.engine.wrap_prompt(original, scenario="intro")
        self.assertEqual(out, original)

    def test_wrap_inspiration_lightweight(self):
        out = self.engine.wrap_prompt("生成创意", scenario="inspiration")
        # 灵感不该带完整铁律(2000+字),应该很短
        self.assertLess(len(out), 500)
        self.assertIn("反光", out)  # 安全约束
        self.assertIn("生成创意", out)

    def test_wrap_optimize_uses_sculptor_mode(self):
        out = self.engine.wrap_prompt("润色这段", scenario="optimize")
        self.assertIn("雕刻家", out)
        self.assertIn("先删", out)

    # ---- style matching ----

    def test_style_match_zhanshen_zhuixu(self):
        matches = self.engine.match_style("退婚 战神 都市")
        self.assertGreater(len(matches), 0)
        # 至少一条命中"战神/赘婿"
        names = " ".join(m["main"] + m["sub"] for m in matches)
        self.assertIn("战神", names)

    def test_style_match_unmatched(self):
        matches = self.engine.match_style("完全不存在的题材关键词zzzzz")
        self.assertEqual(matches, [])

    def test_style_match_topk(self):
        matches = self.engine.match_style("都市 仙侠 悬疑 末世 黑帮", topk=2)
        self.assertLessEqual(len(matches), 2)

    def test_style_report_format(self):
        report = self.engine.build_style_report("退婚 战神")
        self.assertIn("风格匹配报告", report)
        self.assertIn("主风格", report)

    def test_style_report_no_match(self):
        report = self.engine.build_style_report("xyz12345abc")
        self.assertIn("未匹配到", report)

    # ---- forbidden words ----

    def test_detect_forbidden_words(self):
        text = "他顿时眼神深邃,似乎心下了然。"
        hits = self.engine.detect_forbidden_words(text)
        self.assertGreaterEqual(len(hits), 3)
        words = {w for w, _ in hits}
        self.assertIn("顿时", words)
        self.assertIn("似乎", words)

    def test_detect_forbidden_empty(self):
        self.assertEqual(self.engine.detect_forbidden_words(""), [])
        self.assertEqual(self.engine.detect_forbidden_words(None), [])

    def test_detect_forbidden_clean_text(self):
        clean = "她抓起馒头,咬了一口。馒头干硬。"
        self.assertEqual(self.engine.detect_forbidden_words(clean), [])

    # ---- quick_chapter_lint ----

    def test_lint_clean_passes(self):
        clean = "她抓起馒头。\n咬了一口。\n馒头干硬。"
        r = self.engine.quick_chapter_lint(clean)
        self.assertEqual(r["score"], 100)
        self.assertTrue(r["pass"])
        self.assertEqual(r["issues"], [])

    def test_lint_catches_forbidden(self):
        bad = "他顿时眼神深邃,似乎心下了然。"
        r = self.engine.quick_chapter_lint(bad)
        self.assertLess(r["score"], 100)
        self.assertTrue(any("禁用词" in i for i in r["issues"]))

    def test_lint_catches_long_sentence(self):
        # v1.81:门槛 35 字。这里给一个 40+ 字的长句
        long = "他抬起头来仔细地观察着远方那座山峦的山峰下方似乎有着一道不同寻常的金色光芒在闪动而且看起来还在缓缓移动接近"
        r = self.engine.quick_chapter_lint(long)
        self.assertTrue(any("长句" in i for i in r["issues"]),
                        f"应检测到长句,实际 issues: {r['issues']}")

    def test_lint_catches_dash(self):
        # v1.81:>3 处破折号才扣分(避免对话偶尔用一次就扣)
        bad = "他——还是来了。她——也跟着来了。他——叹了口气。她——也叹气。"
        r = self.engine.quick_chapter_lint(bad)
        self.assertTrue(any("破折号" in i for i in r["issues"]),
                        f"应检测到破折号,实际 issues: {r['issues']}")

    def test_lint_catches_ellipsis_three_dots(self):
        # v1.81:>2 处非六连点才扣
        bad = "他叹了口气..." + "她也叹气..." + "我也叹气..."  # 3 处三连点
        r = self.engine.quick_chapter_lint(bad)
        self.assertTrue(any("省略号" in i for i in r["issues"]),
                        f"应检测到省略号,实际 issues: {r['issues']}")

    def test_lint_empty(self):
        r = self.engine.quick_chapter_lint("")
        self.assertEqual(r["score"], 0)

    # ---- mode switch ----

    def test_mode_switch_chinese_alias(self):
        for name in ("建筑师", "造梦师", "炼金术士", "雕刻家"):
            out = self.engine.build_mode_switch_prompt(name)
            self.assertIn(name, out)

    def test_mode_switch_english(self):
        out = self.engine.build_mode_switch_prompt("architect")
        self.assertIn("建筑师", out)

    def test_mode_switch_slash_prefix(self):
        out = self.engine.build_mode_switch_prompt("/雕刻家")
        self.assertIn("雕刻家", out)

    def test_mode_switch_invalid_raises(self):
        with self.assertRaises(ValueError):
            self.engine.build_mode_switch_prompt("不存在的模式")

    # ---- diagnostic prompts ----

    def test_quality_check_prompt(self):
        p = self.engine.build_quality_check_prompt("章节正文示例")
        # v1.33:升级到 38 项(30 原 + 8 大坑)
        self.assertIn("38 项智能质检", p)
        self.assertIn("八大坑专项", p)
        self.assertIn("K1 视角统一", p)
        self.assertIn("K8 市场意识", p)
        self.assertIn("K_scores", p)   # 新 JSON 字段
        self.assertIn("章节正文示例", p)
        self.assertIn("JSON", p)
        # 第 19 项已修(原"只用说"错误指引去掉,改 13 法)
        self.assertNotIn('只用"说"', p)
        self.assertIn("13 法", p)

    def test_spiral_diagnose_prompt(self):
        p = self.engine.build_spiral_diagnose_prompt("章节内容")
        self.assertIn("P1", p)
        self.assertIn("P4 质变爆发", p)
        self.assertIn("章节内容", p)

    # ---- banner & spec loading ----

    def test_banner(self):
        b = self.engine.get_first_activation_banner()
        self.assertIn("盘古", b)
        self.assertIn("V1.0", b)
        self.assertIn("29", b)

    def test_full_spec_loading(self):
        # 假设 pangu_full_spec.md 与 pangu_system.py 同目录(本仓库结构)
        spec = self.engine.get_full_spec()
        if spec:  # 如果存在则验证内容
            self.assertIn("盘古", spec)
            self.assertGreater(len(spec), 1000)


class TestFactory(unittest.TestCase):

    def test_singleton(self):
        a = get_default_engine()
        b = get_default_engine()
        self.assertIs(a, b)

    def test_wrap_helper(self):
        out = wrap("快捷写章节", scenario="chapter", platform="番茄小说")
        self.assertIn("盘古", out)
        self.assertIn("快捷写章节", out)


class TestConstants(unittest.TestCase):

    def test_core_rules_self_contained(self):
        # 关键词应都在 PANGU_CORE_RULES 中
        for kw in ("禁用词", "感官铁律", "结构铁律", "智商防火墙",
                   "视角铁律", "压爆震"):
            self.assertIn(kw, PANGU_CORE_RULES, f"missing: {kw}")

    def test_style_mapping_well_formed(self):
        required = {"kw", "main", "sub", "accent", "female", "platform"}
        for i, row in enumerate(STYLE_MAPPING):
            self.assertTrue(required.issubset(row.keys()),
                          f"row {i} missing keys: {required - row.keys()}")
            self.assertTrue("|" in row["kw"] or len(row["kw"]) > 0)

    def test_mode_prompts_complete(self):
        for k in ("architect", "dreamweaver", "alchemist", "sculptor"):
            self.assertIn(k, MODE_PROMPTS)
            self.assertGreater(len(MODE_PROMPTS[k]), 50)

    def test_chapter_output_format(self):
        f1 = chapter_output_format(chapter_num=1, show_options=True)
        self.assertIn("本章完", f1)
        self.assertIn("断章钩子", f1)
        self.assertIn("下一章选项", f1)

        f2 = chapter_output_format(chapter_num=1, show_options=False)
        self.assertNotIn("下一章选项", f2)


class TestChapterMetaParse(unittest.TestCase):
    """剥离 + 解析【断章钩子】【本章爽点】【伏笔状态】【下一章选项】"""

    SAMPLE = """第一章 觉醒

林远把砍柴刀握得发白,刀刃上还沾着昨夜未干的血。
他十八岁,父亲三年前死于妖兽袭击,留给他一本《混元功》。

林悦跑得气喘吁吁:"哥哥,我饿。"

本章完

【断章钩子】
类型:对话没说完
强度:★★★★★
内容:林悦追上来质问，话没说完就被打断

【本章爽点】
打脸王屠户:林远直接要债，王屠户理亏词穷
越级杀怪:林远用虚弱诅咒杀死妖兽，完成首杀

【伏笔状态】
本章埋雷:天剑宗搜捕诅咒者(计划第8-10章收)
本章收雷:王屠户欠债(第1章所埋)

【下一章选项】
1. 林悦冲上来抱住林远
2. 赵师兄赶到，强行带走
3. 林远让林悦快跑
"""

    def test_strip_keeps_body_drops_meta(self):
        from pangu_system import strip_chapter_meta
        body = strip_chapter_meta(self.SAMPLE)
        self.assertIn("林远把砍柴刀", body)          # 正文在
        self.assertIn('"哥哥,我饿。"', body)          # 正文最后一段在
        self.assertNotIn("本章完", body)             # 标记切掉
        self.assertNotIn("断章钩子", body)
        self.assertNotIn("本章爽点", body)
        self.assertNotIn("伏笔状态", body)
        self.assertNotIn("下一章选项", body)

    def test_parse_hook(self):
        from pangu_system import parse_chapter_meta
        m = parse_chapter_meta(self.SAMPLE)
        self.assertIsNotNone(m["hook"])
        self.assertEqual(m["hook"]["type"], "对话没说完")
        self.assertEqual(m["hook"]["intensity"], "★★★★★")
        self.assertIn("林悦", m["hook"]["content"])

    def test_parse_cool_points(self):
        from pangu_system import parse_chapter_meta
        m = parse_chapter_meta(self.SAMPLE)
        self.assertEqual(len(m["cool_points"]), 2)
        self.assertTrue(any("打脸王屠户" in c for c in m["cool_points"]))
        self.assertTrue(any("越级杀怪" in c for c in m["cool_points"]))

    def test_parse_seeds_planted_with_range(self):
        from pangu_system import parse_chapter_meta
        m = parse_chapter_meta(self.SAMPLE)
        self.assertEqual(len(m["seeds_planted"]), 1)
        seed = m["seeds_planted"][0]
        self.assertEqual(seed["desc"], "天剑宗搜捕诅咒者")  # 不带括号尾巴
        self.assertEqual(seed["plan_pay_at"], 8)         # 范围数字取首

    def test_parse_seeds_paid(self):
        from pangu_system import parse_chapter_meta
        m = parse_chapter_meta(self.SAMPLE)
        self.assertEqual(len(m["seeds_paid"]), 1)
        paid = m["seeds_paid"][0]
        self.assertEqual(paid["desc"], "王屠户欠债")
        self.assertEqual(paid["planted_at"], 1)

    def test_parse_next_options(self):
        from pangu_system import parse_chapter_meta
        m = parse_chapter_meta(self.SAMPLE)
        self.assertEqual(len(m["next_options"]), 3)
        self.assertIn("抱住林远", m["next_options"][0])
        self.assertIn("强行带走", m["next_options"][1])

    def test_seeds_filter_wu(self):
        """伏笔写 '无' 不应该误存进库"""
        from pangu_system import parse_chapter_meta
        sample = "本章完\n\n【伏笔状态】\n本章埋雷:无\n本章收雷:无\n"
        m = parse_chapter_meta(sample)
        self.assertEqual(m["seeds_planted"], [])
        self.assertEqual(m["seeds_paid"], [])

    def test_no_meta_returns_clean(self):
        """章节没附元信息(AI 偶尔会漏),应该原文返回不出错"""
        from pangu_system import parse_chapter_meta, strip_chapter_meta
        sample = "第一章 觉醒\n\n这是干净的章节正文,没有任何元信息标记。"
        m = parse_chapter_meta(sample)
        self.assertEqual(m["hook"], None)
        self.assertEqual(m["cool_points"], [])
        self.assertEqual(m["seeds_planted"], [])
        self.assertEqual(m["next_options"], [])
        self.assertEqual(strip_chapter_meta(sample), sample.rstrip())

    def test_empty_input(self):
        from pangu_system import parse_chapter_meta, strip_chapter_meta
        self.assertEqual(strip_chapter_meta(""), "")
        self.assertEqual(strip_chapter_meta(None or ""), "")
        m = parse_chapter_meta("")
        self.assertEqual(m["body"], "")
        self.assertEqual(m["next_options"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
