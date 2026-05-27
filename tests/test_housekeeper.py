# -*- coding: utf-8 -*-
"""管家模块单元测试"""

import unittest
from housekeeper import (
    Housekeeper, HousekeeperReport, PIPELINE_STEPS,
    get_housekeeper, reset_housekeeper,
)


class TestHousekeeperBasic(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()

    def test_empty_session_summary(self):
        """空 session 不该 crash"""
        s = self.hk.session_summary()
        self.assertEqual(s["chapters"], 0)
        out = self.hk.render_session_summary()
        self.assertIn("还没生成", out)

    def test_start_finalize_basic(self):
        """开始-结束 流程完整"""
        r = self.hk.start_chapter(1)
        self.assertEqual(r.chapter_num, 1)
        self.assertIsNotNone(self.hk.current_report)
        final = self.hk.finalize_chapter()
        self.assertIsNotNone(final)
        self.assertEqual(final.chapter_num, 1)
        self.assertIsNone(self.hk.current_report)
        self.assertEqual(len(self.hk.history), 1)

    def test_retry_does_not_create_new_report(self):
        """同章 retry 不该新建 report"""
        r1 = self.hk.start_chapter(1)
        r1.pipeline_ran["test_step"] = True
        r2 = self.hk.start_chapter(1)   # retry 同章
        # 应该返回同一个 report
        self.assertIs(r1, r2)
        self.assertTrue(r2.pipeline_ran.get("test_step"))


class TestRecordContent(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()
        self.hk.start_chapter(1)

    def test_content_normal(self):
        raw = "正文内容" + "啊" * 1000 + "【本章完】"
        body = "正文内容" + "啊" * 1000
        self.hk.record_content(raw, body)
        r = self.hk.current_report
        self.assertEqual(r.content_len_raw, len(raw))
        self.assertEqual(r.content_len_normalized, len(body))
        self.assertEqual(r.pangu_meta_stripped_chars, len("【本章完】"))
        self.assertTrue(r.pipeline_ran.get("body_clean_strip"))

    def test_content_none_safe(self):
        self.hk.record_content(None, None)  # 不该 crash
        self.assertEqual(self.hk.current_report.content_len_raw, 0)


class TestRecordPanguMeta(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()
        self.hk.start_chapter(1)

    def test_full_meta(self):
        meta = {
            "hook": "悬念句",
            "cool_points": ["爽1", "爽2"],
            "seeds_planted": [{"desc": "种子1"}, {"desc": "种子2"}, {"desc": "种子3"}],
            "seeds_paid": [{"desc": "回收1"}],
            "next_options": ["A", "B"],
        }
        self.hk.record_pangu_meta(meta)
        r = self.hk.current_report
        self.assertTrue(r.hook_set)
        self.assertEqual(r.cool_points_count, 2)
        self.assertEqual(r.seeds_planted, 3)
        self.assertEqual(r.seeds_closed, 1)
        self.assertEqual(r.next_options_count, 2)
        self.assertTrue(r.pipeline_ran.get("pangu_meta_parse"))

    def test_empty_meta(self):
        self.hk.record_pangu_meta({})  # 空 meta
        r = self.hk.current_report
        self.assertFalse(r.hook_set)
        self.assertEqual(r.seeds_planted, 0)

    def test_meta_failed_records_warning(self):
        self.hk.record_pangu_meta_failed("正则不匹配")
        r = self.hk.current_report
        self.assertFalse(r.pipeline_ran.get("pangu_meta_parse"))
        self.assertEqual(len(r.warnings), 1)
        self.assertIn("正则不匹配", r.warnings[0])


class TestWordCount(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()
        self.hk.start_chapter(1)

    def test_within_target(self):
        self.hk.record_word_count(target=2500, actual=2400)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok)

    def test_below_80_percent(self):
        # 2500 的 80% = 2000, 1800 应该不及格
        self.hk.record_word_count(target=2500, actual=1800)
        r = self.hk.current_report
        self.assertFalse(r.word_count_ok)

    def test_no_target(self):
        self.hk.record_word_count(target=0, actual=1500)
        r = self.hk.current_report
        self.assertIsNone(r.word_count_ok)


class TestHealthScore(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()

    def test_all_clean_high_health(self):
        r = self.hk.start_chapter(1)
        # 所有 pipeline 跑了
        for step in PIPELINE_STEPS:
            r.pipeline_ran[step] = True
        r.word_count_actual = 2500
        r.word_count_target = 2500
        r.word_count_ok = True
        r.dialogue_critic_reds = 0
        final = self.hk.finalize_chapter()
        self.assertGreaterEqual(final.health_score, 0.85)

    def test_word_count_fail_drops(self):
        r = self.hk.start_chapter(1)
        for step in PIPELINE_STEPS:
            r.pipeline_ran[step] = True
        r.word_count_ok = False
        final = self.hk.finalize_chapter()
        # 字数不达标 → 比"全 100%"低一截,但 pipeline 全过所以仍在 🟡 段
        self.assertLess(final.health_score, 1.0)
        self.assertGreater(final.health_score, 0.65)

    def test_many_warnings_drops_health(self):
        r = self.hk.start_chapter(1)
        for step in PIPELINE_STEPS:
            r.pipeline_ran[step] = True
        for i in range(8):
            self.hk.warn(f"问题{i}")
        final = self.hk.finalize_chapter()
        # 8 个告警 → -0.3 上限触顶
        self.assertLess(final.health_score, 0.85)


class TestOneliner(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()

    def test_oneliner_includes_key_signals(self):
        r = self.hk.start_chapter(1)
        for step in PIPELINE_STEPS:
            r.pipeline_ran[step] = True
        self.hk.record_word_count(2500, 2400)
        self.hk.record_pangu_meta({
            "hook": "悬念",
            "cool_points": ["a", "b"],
            "seeds_planted": [{"desc": "x"}],
            "seeds_paid": [],
            "next_options": ["A"],
        })
        self.hk.record_extract("chars", 2)
        self.hk.record_extract("rels", 1)
        self.hk.record_dialogue_critic(reds=0, say_count=2, say_allowed=5)

        line = r.render_oneliner()
        self.assertIn("第1章管家", line)
        self.assertIn("钩", line)
        self.assertIn("爽×2", line)
        self.assertIn("埋1", line)
        self.assertIn("13法", line)
        self.assertIn("chars×2", line)

    def test_oneliner_low_health_red_mark(self):
        r = self.hk.start_chapter(1)
        # 不跑任何 pipeline + 字数不达标
        self.hk.record_word_count(2500, 800)
        self.hk.warn("某警告")
        line = r.render_oneliner()
        self.assertIn("🔴", line)  # 低健康度红灯


class TestSessionSummary(unittest.TestCase):

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()

    def test_multi_chapter_summary(self):
        # 3 章,差异化
        for ch in [1, 2, 3]:
            r = self.hk.start_chapter(ch)
            for step in PIPELINE_STEPS:
                r.pipeline_ran[step] = True
            self.hk.record_word_count(2500, 2400)
            self.hk.record_pangu_meta({
                "hook": "h",
                "seeds_planted": [{"desc": f"s{ch}"}] * 2,
                "seeds_paid": [{"desc": "p"}] if ch >= 2 else [],
            })
            self.hk.record_extract("chars", 1)
            self.hk.finalize_chapter()

        s = self.hk.session_summary()
        self.assertEqual(s["chapters"], 3)
        self.assertEqual(s["seeds_planted"], 6)  # 3 * 2
        self.assertEqual(s["seeds_closed"], 2)   # ch2 + ch3
        self.assertEqual(s["extracts"]["chars"], 3)

        text = self.hk.render_session_summary()
        self.assertIn("3 章", text)
        self.assertIn("伏笔", text)


class TestSingleton(unittest.TestCase):

    def test_get_housekeeper_returns_same_instance(self):
        reset_housekeeper()
        hk1 = get_housekeeper()
        hk2 = get_housekeeper()
        self.assertIs(hk1, hk2)

    def test_reset_creates_new(self):
        reset_housekeeper()
        hk1 = get_housekeeper()
        reset_housekeeper()
        hk2 = get_housekeeper()
        self.assertIsNot(hk1, hk2)


if __name__ == "__main__":
    unittest.main()
