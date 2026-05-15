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
        # 单句超 25 字
        long = "他抬起头来仔细地观察着远方的山峦那里似乎有着不同寻常的光芒"
        r = self.engine.quick_chapter_lint(long)
        self.assertTrue(any("长句" in i for i in r["issues"]))

    def test_lint_catches_dash(self):
        bad = "他——还是来了。"
        r = self.engine.quick_chapter_lint(bad)
        self.assertTrue(any("破折号" in i for i in r["issues"]))

    def test_lint_catches_ellipsis_three_dots(self):
        bad = "他叹了口气。"  + "..."  # 三点而非六点
        r = self.engine.quick_chapter_lint(bad)
        self.assertTrue(any("省略号" in i for i in r["issues"]))

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
        self.assertIn("30 项质检", p)
        self.assertIn("章节正文示例", p)
        self.assertIn("JSON", p)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
