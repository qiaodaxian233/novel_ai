# -*- coding: utf-8 -*-
"""v1.95 BUG-069 回归测试 — 字数三档判定(✓ / ⚠ / ✗)

起因:v1.94 实战日志里第 4 章字数 3088 / 目标 2300 = 1.34 倍,
housekeeper 判 ✗ 让用户疑惑("章节质量没问题,只是字数偏多,为什么判失败?")。

新语义:
  - actual < 0.8 * target → ok=False  ✗ 不够(原行为保留)
  - 0.8 ≤ actual/target ≤ 1.5 → ok=True, long=False  ✓ 合理
  - actual > 1.5 * target → ok=True, long=True  ⚠ 超长(不扣健康度)

关键不变量:
  - 既有 19 条 test_housekeeper 测试不破坏(完美兼容)
  - 健康度评分逻辑只看 word_count_ok,不看 long(超长不扣分)
  - oneliner 显示三档 emoji 区分
"""
import unittest
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import housekeeper
from housekeeper import Housekeeper, HousekeeperReport


class TestThreeTierWordCount(unittest.TestCase):
    """v1.95 BUG-069:字数三档判定"""

    def setUp(self):
        housekeeper.reset_housekeeper()
        self.hk = housekeeper.get_housekeeper()
        self.hk.start_chapter(1)

    def test_below_lower_bound(self):
        """实际 < 0.8x target → ok=False(不够)"""
        self.hk.record_word_count(target=2500, actual=1800)
        r = self.hk.current_report
        self.assertFalse(r.word_count_ok)
        self.assertFalse(r.word_count_long, "不够时不算超长")

    def test_within_normal_range(self):
        """实际在 0.8x - 1.5x 之间 → ok=True, long=False(合理)"""
        self.hk.record_word_count(target=2500, actual=2400)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok)
        self.assertFalse(r.word_count_long, "正常范围不算超长")

    def test_above_upper_bound_overlong(self):
        """实际 > 1.5x target → ok=True, long=True(超长 ⚠)"""
        self.hk.record_word_count(target=2000, actual=3500)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok, "超长仍算下限达标")
        self.assertTrue(r.word_count_long)

    def test_real_world_3088_over_2300(self):
        """实战数字:3088 / 2300 = 1.34x → 应该 ✓,不再判 ✗"""
        self.hk.record_word_count(target=2300, actual=3088)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok, "3088 是 2300 的 1.34 倍,在合理范围")
        self.assertFalse(r.word_count_long, "1.34 < 1.5,不算超长")

    def test_exact_lower_boundary(self):
        """实际 = 0.8x target → ok=True(边界包含)"""
        self.hk.record_word_count(target=2500, actual=2000)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok, "0.8x 边界算达标")
        self.assertFalse(r.word_count_long)

    def test_exact_upper_boundary(self):
        """实际 = 1.5x target → ok=True, long=False(边界不算超长)"""
        self.hk.record_word_count(target=2000, actual=3000)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok)
        self.assertFalse(r.word_count_long, "1.5x 边界不算超长(用 >,不是 >=)")

    def test_just_above_upper_boundary(self):
        """实际 = 1.5x target + 1 → ok=True, long=True(刚过线)"""
        self.hk.record_word_count(target=2000, actual=3001)
        r = self.hk.current_report
        self.assertTrue(r.word_count_ok)
        self.assertTrue(r.word_count_long)

    def test_no_target_returns_none(self):
        """target = 0 → ok=None, long=False(未检)"""
        self.hk.record_word_count(target=0, actual=1500)
        r = self.hk.current_report
        self.assertIsNone(r.word_count_ok)
        self.assertFalse(r.word_count_long)

    def test_word_count_long_default_false(self):
        """新增字段默认 False(向后兼容老报告 dict)"""
        r = HousekeeperReport(chapter_num=1)
        self.assertFalse(r.word_count_long)


class TestOnelinerEmojis(unittest.TestCase):
    """oneliner 显示三档 emoji"""

    def setUp(self):
        housekeeper.reset_housekeeper()
        self.hk = housekeeper.get_housekeeper()
        self.hk.start_chapter(7)

    def test_normal_shows_check_mark(self):
        self.hk.record_word_count(2300, 2500)
        line = self.hk.current_report.render_oneliner()
        self.assertIn("字数✓2500", line)
        self.assertNotIn("⚠", line[:line.index("|") if "|" in line else len(line)])

    def test_overlong_shows_warning(self):
        """超长应该出 ⚠"""
        self.hk.record_word_count(2000, 3500)  # 1.75x
        line = self.hk.current_report.render_oneliner()
        self.assertIn("字数⚠3500", line)

    def test_insufficient_shows_x(self):
        """不够应该出 ✗"""
        self.hk.record_word_count(2500, 1500)  # 0.6x
        line = self.hk.current_report.render_oneliner()
        self.assertIn("字数✗1500", line)

    def test_real_world_3088_shows_check(self):
        """实战日志数字 3088/2300 应该出 ✓(之前是 ✗)"""
        self.hk.record_word_count(2300, 3088)
        line = self.hk.current_report.render_oneliner()
        self.assertIn("字数✓3088", line)
        self.assertNotIn("字数✗", line, "实战数字不应再被判 ✗")
        self.assertNotIn("字数⚠", line, "1.34x 不该算超长")


class TestHealthScoreUnaffectedByOverlong(unittest.TestCase):
    """超长 ⚠ 不影响健康度评分"""

    def setUp(self):
        housekeeper.reset_housekeeper()
        self.hk = housekeeper.get_housekeeper()

    def test_normal_vs_overlong_same_health(self):
        """合理范围 vs 超长,健康度应该一样(其他因素一致)"""
        # Case A:合理范围
        self.hk.start_chapter(1)
        self.hk.record_word_count(2000, 2500)  # 1.25x → ✓
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save"]:
            self.hk.record_step(step, True)
        score_a = self.hk.current_report._compute_health()
        self.hk.finalize_chapter()

        # Case B:超长
        self.hk.start_chapter(2)
        self.hk.record_word_count(2000, 3500)  # 1.75x → ⚠
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save"]:
            self.hk.record_step(step, True)
        score_b = self.hk.current_report._compute_health()
        self.hk.finalize_chapter()

        self.assertEqual(score_a, score_b, "超长不应扣健康度,跟合理范围同分")

    def test_insufficient_still_drops_health(self):
        """不够仍要扣健康度(原行为)"""
        self.hk.start_chapter(1)
        self.hk.record_word_count(2500, 1500)  # 不够
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save"]:
            self.hk.record_step(step, True)
        score = self.hk.current_report._compute_health()
        # 字数不够扣 0.3 * 0.4 = 0.12,所以 < 1.0
        self.assertLess(score, 1.0, "字数不够仍要扣健康度")


class TestNoCollisionWithPreviousMilestones(unittest.TestCase):
    """v1.95 不破坏 v1.91-v1.94"""

    def test_app_version_bumped(self):
        novel_ai_path = os.path.join(HERE, "novel_ai.py")
        import re
        with open(novel_ai_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("APP_VERSION"):
                    m = re.search(r'v(\d+)\.(\d+)', line)
                    major, minor = int(m.group(1)), int(m.group(2))
                    self.assertGreaterEqual((major, minor), (1, 95))
                    return
        self.fail("APP_VERSION not found")

    def test_v194_button_color_intact(self):
        # v2.03 P4: ChapterEditor 已外迁到 ui/tabs/chapter_editor.py
        chapter_editor_path = os.path.join(HERE, "ui", "tabs", "chapter_editor.py")
        with open(chapter_editor_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('color:#3a2a10', src, "v1.94 按钮深棕色仍在(P4 后在 ui/tabs/chapter_editor.py)")

    def test_v193_char_fields_intact(self):
        # v2.04 P5: CharacterLibrary 已外迁到 ui/tabs/character_library.py
        charlib_path = os.path.join(HERE, "ui", "tabs", "character_library.py")
        with open(charlib_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"last_ch"', src, "v1.93 last_ch 字段仍在(P5 后在 ui/tabs/character_library.py)")
        self.assertIn('def _find_duplicate_names(rows_data)', src)

    def test_v192_chapter_lock_intact(self):
        novel_ai_path = os.path.join(HERE, "novel_ai.py")
        with open(novel_ai_path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"locked": False', src)
        self.assertIn('def _toggle_chapter_lock', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
