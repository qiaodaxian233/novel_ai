# -*- coding: utf-8 -*-
"""v2.08 housekeeper P2 三扩展点测试(Task 3 — v1.90 留的 P2 扩展点全部实现)

扩展点 1:locked 字段一致性巡检 — record_canon_locked_mismatch
扩展点 2:跨章节奏雷达 — check_pacing_window
扩展点 3:自动备份快照 — snapshot_for_recovery
"""
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from housekeeper import (
    Housekeeper, HousekeeperReport,
    reset_housekeeper,
)


# ========== 扩展点 1:locked 字段一致性巡检 ==========

class TestLockedMismatch(unittest.TestCase):
    """P2-1:record_canon_locked_mismatch — Canon 锁定字段被本章正文改了的检测"""

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()
        self.hk.start_chapter(1)

    def test_record_one_mismatch(self):
        """记录一个 mismatch 后能查到"""
        self.hk.record_canon_locked_mismatch("主角姓名", "林晚晚", "林婉婉")
        r = self.hk.current_report
        self.assertEqual(len(r.locked_mismatches), 1)
        m = r.locked_mismatches[0]
        self.assertEqual(m["field"], "主角姓名")
        self.assertEqual(m["expected"], "林晚晚")
        self.assertEqual(m["actual"], "林婉婉")

    def test_record_multiple_mismatches(self):
        """多个 mismatches 累积"""
        self.hk.record_canon_locked_mismatch("主角姓名", "林晚晚", "林婉婉")
        self.hk.record_canon_locked_mismatch("主角性别", "女", "男")
        self.hk.record_canon_locked_mismatch("男主姓名", "顾砚深", "顾砚渊")
        r = self.hk.current_report
        self.assertEqual(len(r.locked_mismatches), 3)

    def test_truncate_long_values(self):
        """超长字段截断防爆"""
        long_field = "字段名" * 100  # 300 字
        long_val = "值" * 200
        self.hk.record_canon_locked_mismatch(long_field, long_val, long_val)
        m = self.hk.current_report.locked_mismatches[0]
        self.assertLessEqual(len(m["field"]), 30)
        self.assertLessEqual(len(m["expected"]), 60)
        self.assertLessEqual(len(m["actual"]), 60)

    def test_no_current_report_silent(self):
        """没 current_report 不该 crash"""
        hk = Housekeeper()  # 没 start_chapter
        # 不该抛
        hk.record_canon_locked_mismatch("a", "b", "c")

    def test_health_score_penalty(self):
        """每个 mismatch 扣 0.1 健康度,封顶 0.3"""
        # 基准
        r0 = self.hk.current_report
        for step in ["pangu_meta_parse", "body_clean_strip", "auto_save"]:
            r0.pipeline_ran[step] = True
        base_health = r0._compute_health()

        # 加 1 个
        self.hk.record_canon_locked_mismatch("姓名", "A", "B")
        h1 = r0._compute_health()
        self.assertAlmostEqual(base_health - h1, 0.1, places=2)

        # 加 5 个 → 总扣 0.5,但封顶 0.3
        for i in range(4):
            self.hk.record_canon_locked_mismatch(f"f{i}", "x", "y")
        h5 = r0._compute_health()
        self.assertAlmostEqual(base_health - h5, 0.3, places=2)

    def test_oneliner_shows_lock_mark(self):
        """oneliner 末尾显示 🔒 + 字段名"""
        self.hk.record_canon_locked_mismatch("主角姓名", "林晚晚", "林婉婉")
        self.hk.record_canon_locked_mismatch("男主姓名", "顾砚深", "顾砚渊")
        out = self.hk.current_report.render_oneliner()
        self.assertIn("🔒", out)
        self.assertIn("主角姓名", out)
        self.assertIn("男主姓名", out)

    def test_oneliner_truncates_at_2(self):
        """≥ 3 个 mismatches 只显示前 2 个 + (+N)"""
        for i in range(5):
            self.hk.record_canon_locked_mismatch(f"字段{i}", "x", "y")
        out = self.hk.current_report.render_oneliner()
        self.assertIn("🔒", out)
        self.assertIn("(+3)", out)  # 5 - 2 = 3 多余


# ========== 扩展点 2:跨章节奏雷达 ==========

class TestPacingRadar(unittest.TestCase):
    """P2-2:check_pacing_window — 扫最近 N 章 hook/cool 单调"""

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()

    def _add_chapter(self, ch_num, hook_set=False, cool_count=0):
        """模拟一章已 finalize"""
        r = self.hk.start_chapter(ch_num)
        r.hook_set = hook_set
        r.cool_points_count = cool_count
        self.hk.finalize_chapter()

    def test_not_enough_chapters(self):
        """历史 < N 章,返回 None(不够样本)"""
        for ch in range(1, 4):  # 只 3 章
            self._add_chapter(ch, hook_set=False, cool_count=0)
        result = self.hk.check_pacing_window(n=5)
        self.assertIsNone(result)

    def test_all_healthy_returns_empty(self):
        """5 章都有钩子和爽点 → 节奏正常,返回 {}"""
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=True, cool_count=3)
        result = self.hk.check_pacing_window(n=5)
        self.assertEqual(result, {})

    def test_flat_hooks_only(self):
        """连续 5 章无钩子但有爽点 → flat_hooks=True"""
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=False, cool_count=2)
        result = self.hk.check_pacing_window(n=5)
        self.assertIsNotNone(result)
        self.assertTrue(result["flat_hooks"])
        self.assertFalse(result["flat_cools"])
        self.assertIn("无章末钩子", result["msg"])

    def test_flat_cools_only(self):
        """连续 5 章无爽点但有钩子 → flat_cools=True"""
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=True, cool_count=0)
        result = self.hk.check_pacing_window(n=5)
        self.assertIsNotNone(result)
        self.assertTrue(result["flat_cools"])
        self.assertFalse(result["flat_hooks"])
        self.assertIn("无爽点", result["msg"])

    def test_both_flat(self):
        """连续 5 章既无钩子又无爽点 → 双 flat"""
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=False, cool_count=0)
        result = self.hk.check_pacing_window(n=5)
        self.assertIsNotNone(result)
        self.assertTrue(result["flat_hooks"])
        self.assertTrue(result["flat_cools"])

    def test_warns_get_appended(self):
        """检测到疲软后,自动追加 warn"""
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=False, cool_count=0)
        self.hk.check_pacing_window(n=5)
        # 最后一章应该有 warn
        last = self.hk.history[-1]
        self.assertTrue(any("节奏疲软" in w for w in last.warnings))

    def test_window_only_looks_at_recent(self):
        """节奏判定只看最近 N 章,早期章节不影响"""
        # 前 5 章都疲软
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=False, cool_count=0)
        # 最近 5 章都健康
        for ch in range(6, 11):
            self._add_chapter(ch, hook_set=True, cool_count=2)
        # 此时 N=5 应该 OK
        result = self.hk.check_pacing_window(n=5)
        self.assertEqual(result, {})

    def test_default_window_5(self):
        """默认窗口 N=5"""
        for ch in range(1, 6):
            self._add_chapter(ch, hook_set=False, cool_count=0)
        # 不传 n,默认 5
        result = self.hk.check_pacing_window()
        self.assertIsNotNone(result)
        self.assertEqual(result["window"], 5)


# ========== 扩展点 3:自动备份快照 ==========

class TestSnapshotForRecovery(unittest.TestCase):
    """P2-3:snapshot_for_recovery — 章节完成时打项目目录 zip 快照"""

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()
        # 临时项目目录,模拟用户实际项目结构
        self.tmp = tempfile.mkdtemp(prefix="hk_snap_test_")
        self.root = Path(self.tmp)
        (self.root / "project.json").write_text('{"title": "test"}', encoding="utf-8")
        (self.root / "chapters").mkdir()
        (self.root / "chapters" / "ch001.txt").write_text("第一章内容", encoding="utf-8")
        (self.root / "chapters" / "ch002.txt").write_text("第二章内容", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_creates_zip(self):
        """成功打 zip,文件存在"""
        path = self.hk.snapshot_for_recovery(self.tmp, ch_num=2)
        self.assertIsNotNone(path)
        self.assertTrue(Path(path).is_file())
        self.assertTrue(Path(path).name.startswith("snapshot_ch002_"))
        self.assertTrue(Path(path).name.endswith(".zip"))

    def test_snapshot_contains_all_files(self):
        """zip 包含 project.json + chapters/* 全部文件"""
        path = self.hk.snapshot_for_recovery(self.tmp, ch_num=2)
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
        self.assertIn("project.json", names)
        self.assertIn("chapters/ch001.txt", names)
        self.assertIn("chapters/ch002.txt", names)

    def test_snapshot_in_backups_subdir(self):
        """zip 扔到 .backups/ 子目录"""
        path = self.hk.snapshot_for_recovery(self.tmp, ch_num=2)
        self.assertIn(".backups", path)
        self.assertTrue((self.root / ".backups").is_dir())

    def test_invalid_root_returns_none(self):
        """目录不存在 → 返回 None 不崩"""
        result = self.hk.snapshot_for_recovery("/nonexistent_path_xyz", ch_num=1)
        self.assertIsNone(result)

    def test_keep_last_cleans_old(self):
        """超过 keep_last 数量后,旧的自动删"""
        import time
        # 打 5 个 snapshot,keep_last=3
        for ch in range(1, 6):
            self.hk.snapshot_for_recovery(self.tmp, ch_num=ch, keep_last=3)
            time.sleep(0.01)  # 防 mtime 重复(同秒)
        # 应该只剩 3 个
        snaps = list((self.root / ".backups").glob("snapshot_ch*.zip"))
        self.assertEqual(len(snaps), 3)

    def test_excludes_backups_dir_itself(self):
        """打 zip 时不能把 .backups/ 套娃打进去"""
        # 先打 1 个,产生 .backups/
        self.hk.snapshot_for_recovery(self.tmp, ch_num=1)
        # 再打第 2 个 — 这次 .backups 已经存在,但不能进 zip
        path = self.hk.snapshot_for_recovery(self.tmp, ch_num=2)
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
        for n in names:
            self.assertFalse(
                n.startswith(".backups"),
                f"快照 zip 不该包含 .backups/ 套娃: {n}"
            )

    def test_keep_last_default_10(self):
        """默认保留 10 份"""
        import time
        for ch in range(1, 13):  # 12 个 > 10
            self.hk.snapshot_for_recovery(self.tmp, ch_num=ch)
            time.sleep(0.01)
        snaps = list((self.root / ".backups").glob("snapshot_ch*.zip"))
        self.assertEqual(len(snaps), 10)


# ========== 集成:三个扩展点协同 ==========

class TestP2IntegrationFlow(unittest.TestCase):
    """模拟真实章末流水线:三个 P2 扩展点协同使用"""

    def setUp(self):
        reset_housekeeper()
        self.hk = Housekeeper()
        self.tmp = tempfile.mkdtemp(prefix="hk_p2_int_")
        self.root = Path(self.tmp)
        (self.root / "project.json").write_text('{}', encoding="utf-8")
        (self.root / "chapters").mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_chapter_pipeline(self):
        """章末完整流程:start → 记 mismatch → 打 snapshot → finalize → 检查节奏"""
        # 第 1 章
        for ch in range(1, 6):
            r = self.hk.start_chapter(ch)
            r.hook_set = False  # 都是疲软章节
            r.cool_points_count = 0
            if ch == 5:
                # 第 5 章发现 locked 字段被改了
                self.hk.record_canon_locked_mismatch("主角姓名", "林晚晚", "林婉婉")
                # 打 snapshot
                snap = self.hk.snapshot_for_recovery(str(self.root), ch_num=ch)
                self.assertIsNotNone(snap)
            self.hk.finalize_chapter()

        # 节奏雷达检测疲软
        radar = self.hk.check_pacing_window(n=5)
        self.assertIsNotNone(radar)
        self.assertTrue(radar["flat_hooks"])
        self.assertTrue(radar["flat_cools"])

        # 第 5 章 oneliner 应有 🔒
        last_oneliner = self.hk.history[-1].render_oneliner()
        self.assertIn("🔒", last_oneliner)

        # 健康度因 mismatch 降低
        last_health = self.hk.history[-1]._compute_health()
        # 第 1~4 章没 mismatch
        first_health = self.hk.history[0]._compute_health()
        self.assertLess(last_health, first_health)


if __name__ == "__main__":
    unittest.main(verbosity=2)
