# -*- coding: utf-8 -*-
"""
test_housekeeper_p3.py — v2.09 Housekeeper P3 两扩展点

P3-#10: RL 反馈联动 — set_rl_reward_callback
P3-#12: 二道闸巡查 — verify_defenses(fingerprints, source_paths)

设计原则验证:
  - housekeeper 不 import flow_rl(零依赖)
  - 失败容错(callback 抛异常 / 文件读不到 / 空指纹)
  - HousekeeperReport.missing_defenses 字段 + 健康度 defense_penalty
  - oneliner 末尾 🛡️ 标记 + 不跟 ⚠ 区重复
  - 不破坏 P1 / v1.95 / P2 既有功能
"""
import os
import sys
import unittest
import tempfile
from pathlib import Path

# 确保能 import housekeeper
sys.path.insert(0, str(Path(__file__).resolve().parent))

from housekeeper import Housekeeper, HousekeeperReport, get_housekeeper, reset_housekeeper


# ============================================================
# HousekeeperReport 新字段
# ============================================================

class TestMissingDefensesField(unittest.TestCase):
    """P3 v2.09:HousekeeperReport 加 missing_defenses 字段"""

    def test_default_empty(self):
        r = HousekeeperReport(chapter_num=1)
        self.assertEqual(r.missing_defenses, [])

    def test_to_dict_includes_field(self):
        from dataclasses import asdict
        r = HousekeeperReport(chapter_num=1)
        d = asdict(r)
        self.assertIn("missing_defenses", d)
        self.assertEqual(d["missing_defenses"], [])


# ============================================================
# 健康度 defense_penalty
# ============================================================

class TestDefensePenalty(unittest.TestCase):
    """P3 v2.09:_compute_health 加 defense_penalty"""

    def test_no_missing_no_penalty(self):
        r = HousekeeperReport(chapter_num=1)
        # 把 pipeline 填满,baseline 健康度
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save", "dialogue_critic_scan",
                     "post_chapter_chain", "canon_extract", "summary_generate"]:
            r.pipeline_ran[step] = True
        baseline = r._compute_health()
        self.assertGreaterEqual(baseline, 0.85)

    def test_one_missing_minus_0_15(self):
        r = HousekeeperReport(chapter_num=1)
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save", "dialogue_critic_scan",
                     "post_chapter_chain", "canon_extract", "summary_generate"]:
            r.pipeline_ran[step] = True
        baseline = r._compute_health()
        r.missing_defenses = ["BUG-028"]
        with_one = r._compute_health()
        # 差应该是 0.15
        self.assertAlmostEqual(baseline - with_one, 0.15, places=2)

    def test_three_missing_minus_0_4_capped(self):
        """3 条 × 0.15 = 0.45,封顶 0.4"""
        r = HousekeeperReport(chapter_num=1)
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save", "dialogue_critic_scan",
                     "post_chapter_chain", "canon_extract", "summary_generate"]:
            r.pipeline_ran[step] = True
        baseline = r._compute_health()
        r.missing_defenses = ["BUG-001", "BUG-002", "BUG-003"]
        capped = r._compute_health()
        self.assertAlmostEqual(baseline - capped, 0.4, places=2)

    def test_five_missing_still_capped_at_0_4(self):
        """5 条仍封顶 0.4(不是 0.75)"""
        r = HousekeeperReport(chapter_num=1)
        for step in ["pangu_meta_parse", "body_clean_strip", "seeds_sync_lifespan",
                     "hook_cool_sync", "auto_save", "dialogue_critic_scan",
                     "post_chapter_chain", "canon_extract", "summary_generate"]:
            r.pipeline_ran[step] = True
        baseline = r._compute_health()
        r.missing_defenses = ["B1", "B2", "B3", "B4", "B5"]
        capped = r._compute_health()
        self.assertAlmostEqual(baseline - capped, 0.4, places=2)

    def test_defense_more_severe_than_warning(self):
        """defense_penalty 比 warn_penalty 严厉:1 个 defense = 3 个 warn"""
        r1 = HousekeeperReport(chapter_num=1)
        r2 = HousekeeperReport(chapter_num=2)
        # r1: 1 个 missing_defense (扣 0.15)
        r1.missing_defenses = ["BUG-001"]
        # r2: 3 个 warning (扣 0.15)
        r2.warnings = ["a", "b", "c"]
        # 两者扣分相同
        self.assertAlmostEqual(r1._compute_health(), r2._compute_health(), places=2)


# ============================================================
# render_oneliner 🛡️ 标记
# ============================================================

class TestOnelinerShieldMark(unittest.TestCase):
    """P3 v2.09:oneliner 显示 🛡️ + 不跟 ⚠ 重复"""

    def test_no_missing_no_mark(self):
        r = HousekeeperReport(chapter_num=1)
        r.word_count_actual = 2000
        r.word_count_target = 2000
        r.word_count_ok = True
        line = r.render_oneliner()
        self.assertNotIn("🛡️", line)

    def test_one_missing_shows_mark(self):
        r = HousekeeperReport(chapter_num=1)
        r.word_count_actual = 2000
        r.word_count_target = 2000
        r.word_count_ok = True
        r.missing_defenses = ["BUG-028"]
        line = r.render_oneliner()
        self.assertIn("🛡️", line)
        self.assertIn("BUG-028", line)

    def test_three_missing_shows_first_two_plus_count(self):
        r = HousekeeperReport(chapter_num=1)
        r.missing_defenses = ["BUG-A", "BUG-B", "BUG-C"]
        line = r.render_oneliner()
        self.assertIn("BUG-A", line)
        self.assertIn("BUG-B", line)
        self.assertIn("(+1)", line)
        # BUG-C 不直接显示(只在 count 里)
        self.assertNotIn("BUG-C", line)

    def test_no_duplicate_warning_section(self):
        """🛡️ 区显示了就不该在 ⚠ 区重复(_record_missing_defense 不发 warning)"""
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.py"
            src.write_text("dummy content")
            hk = Housekeeper()
            hk.start_chapter(1)
            hk.verify_defenses({"BUG-XYZ": ["不存在的指纹"]}, [str(src)])
            line = hk.current_report.render_oneliner()
            # 应该只有一个 BUG-XYZ 出现
            self.assertEqual(line.count("BUG-XYZ"), 1, f"重复出现:{line}")
            # 应该在 🛡️ 后,不在 ⚠ 后
            self.assertIn("🛡️", line)
            # 不应该有 "⚠ BUG-XYZ" 这种组合
            # 因为 warnings 列表保持空了
            self.assertEqual(hk.current_report.warnings, [])


# ============================================================
# P3-#10: RL 反馈联动
# ============================================================

class TestSetRlRewardCallback(unittest.TestCase):
    """P3-#10:set_rl_reward_callback API"""

    def test_default_callback_is_none(self):
        hk = Housekeeper()
        self.assertIsNone(hk.rl_reward_callback)

    def test_register_callback(self):
        hk = Housekeeper()
        def cb(score, report):
            pass
        hk.set_rl_reward_callback(cb)
        self.assertIs(hk.rl_reward_callback, cb)

    def test_unregister_with_none(self):
        hk = Housekeeper()
        hk.set_rl_reward_callback(lambda s, r: None)
        hk.set_rl_reward_callback(None)
        self.assertIsNone(hk.rl_reward_callback)

    def test_non_callable_silently_rejected(self):
        """非 callable 静默拒绝,符合 housekeeper 失败容错风格"""
        hk = Housekeeper()
        original = lambda s, r: None
        hk.set_rl_reward_callback(original)
        hk.set_rl_reward_callback("not_callable")
        # 原 callback 保留(没被覆盖)
        self.assertIs(hk.rl_reward_callback, original)

    def test_finalize_invokes_callback(self):
        """finalize_chapter 末尾自动 emit health_score 给 callback"""
        hk = Housekeeper()
        captured = []

        def cb(score, report_dict):
            captured.append((score, report_dict["chapter_num"]))

        hk.set_rl_reward_callback(cb)
        hk.start_chapter(7)
        hk.record_word_count(2000, 2000)
        report = hk.finalize_chapter()

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][1], 7)
        self.assertAlmostEqual(captured[0][0], report.health_score, places=3)

    def test_callback_receives_full_report_dict(self):
        """callback 收到完整 report_dict(可以读 metadata)"""
        hk = Housekeeper()
        captured = []

        def cb(score, report_dict):
            captured.append(report_dict)

        hk.set_rl_reward_callback(cb)
        hk.start_chapter(3)
        hk.record_word_count(2000, 2500)
        hk.record_pangu_meta({"hook": "钩子", "cool_points": ["爽1", "爽2"]})
        hk.finalize_chapter()

        d = captured[0]
        self.assertEqual(d["chapter_num"], 3)
        self.assertEqual(d["word_count_actual"], 2500)
        self.assertEqual(d["cool_points_count"], 2)
        self.assertTrue(d["hook_set"])

    def test_callback_exception_doesnt_break_finalize(self):
        """callback 抛异常不影响 finalize 返回正常 report"""
        hk = Housekeeper()

        def bad_cb(score, report):
            raise RuntimeError("故意挂的 RL 回调")

        hk.set_rl_reward_callback(bad_cb)
        hk.start_chapter(1)
        hk.record_word_count(2000, 2200)
        report = hk.finalize_chapter()

        # finalize 仍正常返回 report,health_score 已算出
        self.assertIsNotNone(report)
        self.assertGreater(report.health_score, 0)
        self.assertEqual(report.chapter_num, 1)

    def test_no_callback_no_emit_no_error(self):
        """不注册 callback 时 finalize 不崩"""
        hk = Housekeeper()
        hk.start_chapter(1)
        hk.record_word_count(2000, 2000)
        # 没注册 callback
        report = hk.finalize_chapter()
        self.assertIsNotNone(report)

    def test_callback_called_per_chapter(self):
        """每章 finalize 都触发一次 callback"""
        hk = Housekeeper()
        scores = []
        hk.set_rl_reward_callback(lambda s, r: scores.append(s))

        for ch in range(1, 4):
            hk.start_chapter(ch)
            hk.record_word_count(2000, 2000)
            hk.finalize_chapter()

        self.assertEqual(len(scores), 3)

    def test_housekeeper_does_not_import_flow_rl(self):
        """关键:housekeeper.py 不 import flow_rl(完全解耦)

        用 AST 检查真实 import 语句,绕开 docstring 里的 'from flow_rl import' 代码示例
        """
        import ast
        src = Path(__file__).parent.joinpath("housekeeper.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name, "flow_rl",
                                        f"housekeeper.py 在 line {node.lineno} 真的 import flow_rl 了")
            elif isinstance(node, ast.ImportFrom):
                self.assertNotEqual(node.module, "flow_rl",
                                    f"housekeeper.py 在 line {node.lineno} 真的 from flow_rl import 了")


# ============================================================
# P3-#12: verify_defenses 基础
# ============================================================

class TestVerifyDefensesBasic(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self.tmp.name
        self.src_path = Path(self.tmpdir) / "src.py"
        self.src_path.write_text(
            "def foo():\n"
            "    return _chapter_fingerprint  # BUG-028 防御\n"
            "def bar():\n"
            "    CRITICAL_TARGETS = ['summary']  # BUG-065 防御\n"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_present(self):
        hk = Housekeeper()
        hk.start_chapter(1)
        fps = {
            "BUG-028": ["_chapter_fingerprint"],
            "BUG-065": ["CRITICAL_TARGETS"],
        }
        result = hk.verify_defenses(fps, [str(self.src_path)])
        self.assertEqual(result, {"BUG-028": True, "BUG-065": True})
        self.assertEqual(hk.current_report.missing_defenses, [])

    def test_one_missing(self):
        hk = Housekeeper()
        hk.start_chapter(1)
        fps = {
            "BUG-028": ["_chapter_fingerprint"],
            "BUG-099": ["不存在的方法名"],
        }
        result = hk.verify_defenses(fps, [str(self.src_path)])
        self.assertTrue(result["BUG-028"])
        self.assertFalse(result["BUG-099"])
        self.assertEqual(hk.current_report.missing_defenses, ["BUG-099"])

    def test_multiple_patterns_all_required(self):
        """单个 BUG 的所有 pattern 都必须出现"""
        hk = Housekeeper()
        hk.start_chapter(1)
        fps = {
            "BUG-X": ["_chapter_fingerprint", "CRITICAL_TARGETS"],  # 两个都在
            "BUG-Y": ["_chapter_fingerprint", "完全不在的字符串"],  # 一个不在
        }
        result = hk.verify_defenses(fps, [str(self.src_path)])
        self.assertTrue(result["BUG-X"])
        self.assertFalse(result["BUG-Y"])

    def test_default_source_path_is_novel_ai(self):
        """source_paths 不传时,默认扫 novel_ai.py"""
        hk = Housekeeper()
        hk.start_chapter(1)
        # 真实 novel_ai.py 里有"chapter"字符串
        fps = {"REAL": ["chapter"]}
        result = hk.verify_defenses(fps)  # 不传 source_paths
        # 应该能扫到 novel_ai.py 里的 "chapter"
        # 注意:此测试假定项目根有 novel_ai.py
        novel_ai_path = Path(__file__).parent / "novel_ai.py"
        if novel_ai_path.exists():
            self.assertTrue(result["REAL"])
        else:
            # 如果 novel_ai.py 没装(测试容器),容忍 False
            self.assertIn("REAL", result)

    def test_returns_dict(self):
        hk = Housekeeper()
        hk.start_chapter(1)
        result = hk.verify_defenses({"X": ["foo"]}, [str(self.src_path)])
        self.assertIsInstance(result, dict)


class TestVerifyDefensesEdgeCases(unittest.TestCase):

    def test_empty_fingerprints_returns_empty(self):
        hk = Housekeeper()
        hk.start_chapter(1)
        self.assertEqual(hk.verify_defenses({}, ["x.py"]), {})

    def test_all_files_unreadable_returns_all_false(self):
        """所有文件读不到 → 保守视作"防御全消失" """
        hk = Housekeeper()
        hk.start_chapter(1)
        result = hk.verify_defenses(
            {"BUG-A": ["x"], "BUG-B": ["y"]},
            ["/nonexistent/a.py", "/nonexistent/b.py"],
        )
        self.assertEqual(result, {"BUG-A": False, "BUG-B": False})
        # missing_defenses 应该包含两个
        self.assertIn("BUG-A", hk.current_report.missing_defenses)
        self.assertIn("BUG-B", hk.current_report.missing_defenses)

    def test_empty_pattern_list_treated_as_missing(self):
        """空 pattern list 视作 missing(没有指纹 = 没法验证)"""
        hk = Housekeeper()
        hk.start_chapter(1)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.py"
            src.write_text("hello")
            result = hk.verify_defenses({"BUG-A": []}, [str(src)])
            self.assertFalse(result["BUG-A"])

    def test_partial_file_failure_uses_remaining(self):
        """部分文件读不到时,用剩下能读的"""
        with tempfile.TemporaryDirectory() as d:
            good = Path(d) / "good.py"
            good.write_text("def foo(): return 'magic_string_xyz'")
            bad = "/nonexistent/bad.py"

            hk = Housekeeper()
            hk.start_chapter(1)
            result = hk.verify_defenses(
                {"BUG-A": ["magic_string_xyz"]},
                [str(good), bad],
            )
            # good 里有这个字符串 → BUG-A 防御完好
            self.assertTrue(result["BUG-A"])

    def test_no_current_report_doesnt_crash(self):
        """没 start_chapter 直接调 verify_defenses 不崩"""
        hk = Housekeeper()  # 没 start_chapter
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.py"
            src.write_text("hello")
            result = hk.verify_defenses({"BUG-A": ["不存在"]}, [str(src)])
            # 不崩,返回 False
            self.assertFalse(result["BUG-A"])
            # current_report 仍为 None
            self.assertIsNone(hk.current_report)

    def test_duplicate_missing_not_added_twice(self):
        """同一 BUG 验证两次都失败,missing_defenses 不重复"""
        hk = Housekeeper()
        hk.start_chapter(1)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.py"
            src.write_text("hello")
            hk.verify_defenses({"BUG-A": ["不存在"]}, [str(src)])
            hk.verify_defenses({"BUG-A": ["不存在"]}, [str(src)])
            self.assertEqual(hk.current_report.missing_defenses.count("BUG-A"), 1)

    def test_non_string_pattern_treated_as_invalid(self):
        """pattern 不是 str → 视作 missing,不抛"""
        hk = Housekeeper()
        hk.start_chapter(1)
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "x.py"
            src.write_text("hello world")
            # 这是个边界场景:用户 fingerprints 写错了类型
            result = hk.verify_defenses(
                {"BUG-A": [None, 123, "world"]},  # mixed types
                [str(src)],
            )
            # None/123 都不是字符串 → all_present = False
            self.assertFalse(result["BUG-A"])


# ============================================================
# 不破坏既有功能
# ============================================================

class TestNoRegressionOnPreviousMilestones(unittest.TestCase):
    """v2.09 P3 不破坏 P1 / P2 / v1.95 既有功能"""

    def test_p1_record_methods_still_work(self):
        hk = Housekeeper()
        hk.start_chapter(1)
        hk.record_content("原文 100 字", "正文")
        hk.record_pangu_meta({"hook": "k", "cool_points": ["1"]})
        hk.record_step("auto_save", True)
        hk.record_extract("chars", 2)
        hk.record_word_count(2000, 2100)
        hk.record_dialogue_critic(0, 5, 10)
        hk.warn("test")
        # 没崩 + 字段填了
        self.assertEqual(hk.current_report.cool_points_count, 1)
        self.assertEqual(hk.current_report.dialogue_critic_say_count, 5)

    def test_p2_record_canon_locked_mismatch_still_works(self):
        hk = Housekeeper()
        hk.start_chapter(1)
        hk.record_canon_locked_mismatch("主角姓名", "李四", "张三")
        self.assertEqual(len(hk.current_report.locked_mismatches), 1)
        self.assertEqual(hk.current_report.locked_mismatches[0]["field"], "主角姓名")

    def test_p2_check_pacing_window_still_works(self):
        hk = Housekeeper()
        for ch in range(1, 6):
            hk.start_chapter(ch)
            # 故意不调 record_pangu_meta → hook_set=False, cool_points_count=0
            hk.finalize_chapter()
        # 第 6 章 check_pacing_window 应检测到双 flat
        result = hk.check_pacing_window(n=5)
        self.assertIsNotNone(result)
        self.assertTrue(result.get("flat_hooks"))
        self.assertTrue(result.get("flat_cools"))

    def test_p2_snapshot_for_recovery_still_works(self):
        with tempfile.TemporaryDirectory() as d:
            # 准备假项目目录
            proj = Path(d) / "project"
            proj.mkdir()
            (proj / "project.json").write_text('{"x":1}')

            hk = Housekeeper()
            hk.start_chapter(1)
            zip_path = hk.snapshot_for_recovery(str(proj), 1, keep_last=3)
            self.assertIsNotNone(zip_path)
            self.assertTrue(Path(zip_path).exists())

    def test_singleton_get_housekeeper(self):
        reset_housekeeper()
        hk1 = get_housekeeper()
        hk2 = get_housekeeper()
        self.assertIs(hk1, hk2)
        reset_housekeeper()


# ============================================================
# APP_VERSION
# ============================================================

class TestAppVersionBumped(unittest.TestCase):

    def test_version_at_least_v209(self):
        novel_ai_path = Path(__file__).parent / "novel_ai.py"
        if not novel_ai_path.exists():
            self.skipTest("novel_ai.py not present in test environment")
        src = novel_ai_path.read_text(encoding="utf-8")
        import re
        m = re.search(r'APP_VERSION\s*=\s*["\']v(\d+)\.(\d+)["\']', src)
        self.assertIsNotNone(m, "APP_VERSION not found in novel_ai.py")
        major, minor = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual(
            (major, minor), (2, 9),
            f"APP_VERSION 应 ≥ v2.09,实际 v{major}.{minor:02d}"
        )


if __name__ == "__main__":
    unittest.main()
