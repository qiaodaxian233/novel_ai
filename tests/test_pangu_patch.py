#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试:pangu_patch 模块
================================
跑法:python -m unittest test_pangu_patch.py -v
"""

import unittest
from pangu_patch import install_pangu, uninstall_pangu, is_installed


# 与真实 novel_ai.py 的 PROMPTS 字典结构等价的最小复刻
def make_fake_globals():
    return {
        "PROMPTS": {
            "creative_inspiration": "请生成创意,题材:{genre}",
            "outline_full": "请生成大纲,题材:{genre},创意:{inspiration},章节{chapter_count}{extra}",
            "outline_part": "请生成{part_name},题材{genre},创意{inspiration}{extra}",
            "chapter": (
                "请作为资深网文作者,生成《{title}》第 {chapter_num} 章的小说正文。"
                "题材{genre},整体世界观{outline},本章大纲{chapter_outline},"
                "目标 {target_words} 字,最少 {min_words} 字。"
            ),
            "golden_three": "请生成黄金三章,题材{genre},创意{inspiration},参考{ch_outline}",
            "title": "请取书名,题材{genre},创意{inspiration},平台{platform}",
            "intro": "请写简介。种子{seed},世界观{worldview},结构{structure}",
            "ai_optimize": "请润色:{content}",
            "chapter_summary": "请总结。标题{title}章节内容{content}最长{max_len}",
            "canon_audit": "审稿:{canon_locked}/{canon_evolving}/{content}",
        }
    }


class TestInstallPangu(unittest.TestCase):

    def setUp(self):
        self.g = make_fake_globals()
        self.original_chapter = self.g["PROMPTS"]["chapter"]
        self.original_title = self.g["PROMPTS"]["title"]

    def test_install_succeeds(self):
        ok = install_pangu(self.g)
        self.assertTrue(ok)
        self.assertTrue(is_installed(self.g))

    def test_chapter_prompt_wrapped(self):
        install_pangu(self.g)
        ch = self.g["PROMPTS"]["chapter"]
        self.assertIn("盘古", ch)
        self.assertIn("禁用词", ch)
        self.assertIn("本章完", ch)
        self.assertIn(self.original_chapter, ch)

    def test_chapter_placeholders_survived(self):
        """关键测试:patch 不能破坏原 {占位符},format() 必须能正常工作"""
        install_pangu(self.g)
        formatted = self.g["PROMPTS"]["chapter"].format(
            title="测试书",
            chapter_num=7,
            genre="都市",
            outline="测试大纲",
            chapter_outline="本章大纲",
            target_words=2500,
            min_words=2125,
        )
        self.assertIn("测试书", formatted)
        self.assertIn("第 7 章", formatted)
        self.assertIn("2500", formatted)
        self.assertIn("盘古", formatted)

    def test_outline_full_placeholders_survived(self):
        install_pangu(self.g)
        formatted = self.g["PROMPTS"]["outline_full"].format(
            genre="都市/言情",
            inspiration="35 岁程序员被裁",
            chapter_count=120,
            extra="\n额外设定块",
        )
        self.assertIn("120", formatted)
        self.assertIn("35 岁程序员", formatted)
        self.assertIn("矛盾螺旋", formatted)  # Pangu outline 尾

    def test_golden_three_has_formula(self):
        install_pangu(self.g)
        gt = self.g["PROMPTS"]["golden_three"]
        self.assertIn("黄金三章公式", gt)
        self.assertIn("绝境+羞辱", gt)
        self.assertIn("循环爽点", gt)

    def test_optimize_uses_sculptor(self):
        install_pangu(self.g)
        op = self.g["PROMPTS"]["ai_optimize"]
        self.assertIn("雕刻家", op)
        self.assertIn("{content}", op)  # 占位符保留

    def test_inspiration_lightweight_not_full_rules(self):
        install_pangu(self.g)
        insp = self.g["PROMPTS"]["creative_inspiration"]
        # 不应该带完整禁用词表(那是 PANGU_CORE_RULES)
        self.assertNotIn("禁用词强制过滤", insp)
        self.assertIn("反光", insp)
        self.assertIn("{genre}", insp)

    def test_title_intro_canon_audit_untouched(self):
        install_pangu(self.g)
        # 工具型 prompt 应保持原样
        self.assertEqual(self.g["PROMPTS"]["title"], self.original_title)
        self.assertEqual(self.g["PROMPTS"]["intro"], "请写简介。种子{seed},世界观{worldview},结构{structure}")
        self.assertEqual(self.g["PROMPTS"]["chapter_summary"],
                        "请总结。标题{title}章节内容{content}最长{max_len}")
        self.assertEqual(self.g["PROMPTS"]["canon_audit"],
                        "审稿:{canon_locked}/{canon_evolving}/{content}")

    def test_install_disabled_noop(self):
        install_pangu(self.g, enabled=False)
        self.assertFalse(is_installed(self.g))
        self.assertEqual(self.g["PROMPTS"]["chapter"], self.original_chapter)

    def test_uninstall_restores_originals(self):
        install_pangu(self.g)
        self.assertNotEqual(self.g["PROMPTS"]["chapter"], self.original_chapter)
        ok = uninstall_pangu(self.g)
        self.assertTrue(ok)
        self.assertEqual(self.g["PROMPTS"]["chapter"], self.original_chapter)
        self.assertFalse(is_installed(self.g))

    def test_double_install_safe(self):
        install_pangu(self.g)
        first = self.g["PROMPTS"]["chapter"]
        # 第二次 install 不应该再次套头(避免叠加)
        uninstall_pangu(self.g)
        install_pangu(self.g)
        second = self.g["PROMPTS"]["chapter"]
        self.assertEqual(first, second)

    def test_show_options_false(self):
        install_pangu(self.g, show_options_in_chapter=False)
        ch = self.g["PROMPTS"]["chapter"]
        self.assertIn("本章完", ch)
        self.assertNotIn("下一章选项", ch)

    def test_custom_keys(self):
        install_pangu(self.g, keys={"chapter"})
        self.assertIn("盘古", self.g["PROMPTS"]["chapter"])
        # golden_three 不应被 patch
        self.assertEqual(self.g["PROMPTS"]["golden_three"],
                        "请生成黄金三章,题材{genre},创意{inspiration},参考{ch_outline}")

    def test_missing_prompts_raises(self):
        with self.assertRaises(RuntimeError):
            install_pangu({"no_prompts_here": True})


class TestIntegration(unittest.TestCase):
    """模拟一次完整的 install → format → uninstall 流程"""

    def test_full_cycle(self):
        g = make_fake_globals()
        # 1. 安装
        install_pangu(g)

        # 2. 跑一个完整的 chapter format(像 novel_ai.py 实际做的那样)
        ch_text = g["PROMPTS"]["chapter"].format(
            title="重生之最强赘婿",
            chapter_num=42,
            genre="都市/赘婿",
            outline="主角林天被退婚...",
            chapter_outline="本章主角去酒会打脸前妻",
            target_words=2500,
            min_words=2125,
        )
        # 包含原模板信息
        self.assertIn("第 42 章", ch_text)
        self.assertIn("重生之最强赘婿", ch_text)
        # 包含盘古铁律
        self.assertIn("禁用词", ch_text)
        self.assertIn("感官铁律", ch_text)
        # 包含输出格式尾
        self.assertIn("断章钩子", ch_text)

        # 3. 关掉,验证回到原版
        uninstall_pangu(g)
        ch_text_orig = g["PROMPTS"]["chapter"].format(
            title="重生之最强赘婿",
            chapter_num=42,
            genre="都市/赘婿",
            outline="主角林天被退婚...",
            chapter_outline="本章主角去酒会打脸前妻",
            target_words=2500,
            min_words=2125,
        )
        self.assertNotIn("禁用词", ch_text_orig)
        self.assertNotIn("断章钩子", ch_text_orig)
        self.assertIn("第 42 章", ch_text_orig)


if __name__ == "__main__":
    unittest.main(verbosity=2)
