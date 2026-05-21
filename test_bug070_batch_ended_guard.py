# -*- coding: utf-8 -*-
"""v1.96 BUG-070 回归测试 — 单章模式"批量已结束"误报防御

起因:v1.95 实战日志 15:26:02 出现"批量生成已结束",但用户跑的是单章模式
(_batch_remaining=1 启动,_accept_chapter_and_continue 末尾减到 0)。
正确行为应该是"安静结束",不该打"批量已结束"误导用户。

根因:_pending_task_target 是单变量,worker 队列里多任务并发提交时被覆盖,
Canon 抽取响应回来时拿到串台的 meta → 路由进 chapter_summary handler →
chain_to_next 标志可能错乱 → 触发 L12571 "批量已结束" 误报。

修法(治标):L12571 加 _batch_remaining > 0 守卫,即使 chain_to_next 错乱
也只在"真批量模式"才打"批量已结束";单章模式被错乱时打 warn(让下次实战可见)。

治本(留 B-2 v1.97):_pending_task_target 改 dict 映射(task_id → meta)
— 工程量大,涉及 8+ 处读写,跟 pangu/laodao 路由互动复杂,单独一轮。

本测试用源码级断言验证守卫逻辑落地,不依赖运行时(Qt + worker)。
"""
import unittest
import ast
import os
import textwrap


HERE = os.path.dirname(os.path.abspath(__file__))
NOVEL_AI_PATH = os.path.join(HERE, "novel_ai.py")


class TestBatchEndedGuardSource(unittest.TestCase):
    """源码级断言 — chapter_summary handler 的 3 档守卫"""

    @classmethod
    def setUpClass(cls):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            cls.src = f.read()

    def test_chapter_summary_handler_has_bug070_marker(self):
        """chapter_summary handler 必须有 BUG-070 注释,证明修复已落地"""
        # 找 chapter_summary handler 段
        idx = self.src.find('elif target == "chapter_summary"')
        self.assertGreater(idx, 0, "找不到 chapter_summary handler")
        # 取该段往后约 2000 字符
        chunk = self.src[idx:idx + 2500]
        self.assertIn("BUG-070", chunk,
                      "chapter_summary handler 必须有 BUG-070 修复标记")

    def test_three_tier_guard_structure(self):
        """守卫必须有三档:真批量触发下一章 / 真批量已结束 / 单章错乱诊断"""
        idx = self.src.find('elif target == "chapter_summary"')
        chunk = self.src[idx:idx + 2500]

        # 第 1 档:_batch_remaining > 0 and not _batch_paused → 触发下一章
        self.assertIn('_batch_remaining > 0 and not self._batch_paused', chunk,
                      "第 1 档:真批量触发下一章")

        # 第 2 档(新增):真批量被暂停 → 仍打"批量已结束"(保留原行为给暂停场景)
        self.assertIn('_batch_remaining > 0 or self._batch_paused', chunk,
                      "第 2 档:真批量(含暂停)才打'批量已结束'")

        # 第 3 档(新增):单章模式 chain_to_next 错乱 → warn 不打"批量已结束"
        self.assertIn('chain_to_next=True', chunk,
                      "第 3 档:单章模式 chain_to_next 异常诊断")

    def test_no_unconditional_batch_ended_log_in_summary(self):
        """chapter_summary handler 里不应该有 'chain_to_next 为真就无条件打批量已结束' 的代码

        即:`elif meta.get("chain_to_next"): log("批量生成已结束")` 这种裸 elif 必须消失。
        每个 elif chain_to_next 都必须带额外的 _batch_remaining / _batch_paused 守卫。
        """
        idx = self.src.find('elif target == "chapter_summary"')
        chunk = self.src[idx:idx + 2500]
        # 找所有"批量生成已结束"出现位置
        positions = []
        start = 0
        while True:
            p = chunk.find('"批量生成已结束"', start)
            if p < 0:
                break
            positions.append(p)
            start = p + 1
        # chapter_summary handler 内最多 1 处"批量生成已结束"(在第 2 档 elif 里)
        self.assertLessEqual(len(positions), 1,
                             f"chapter_summary handler 内'批量生成已结束'应该 ≤1 处,实际 {len(positions)}")
        # 如果有 1 处,它前面的 elif 必须包含 _batch_remaining 或 _batch_paused
        if positions:
            p = positions[0]
            # 前 500 字符看 elif 条件(中间可能有 4-5 行注释)
            preceding = chunk[max(0, p - 500):p]
            self.assertTrue(
                '_batch_remaining' in preceding or '_batch_paused' in preceding,
                f"'批量生成已结束' 前的 elif 必须有 _batch_remaining 或 _batch_paused 守卫;"
                f"preceding 末尾 300 字:{preceding[-300:]!r}")


class TestEndBatchStepUnaffected(unittest.TestCase):
    """L17922 end_batch step 的 'batch ended' log 不受 BUG-070 修改"""

    @classmethod
    def setUpClass(cls):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            cls.src = f.read()

    def test_end_batch_step_intact(self):
        """end_batch step 仍保留 — 它走的是 auto_summarize 关闭分支,
        独立于 BUG-070 修改的 chapter_summary handler"""
        self.assertIn('elif step[0] == "end_batch":', self.src)
        # end_batch step 里仍打"批量生成已结束"(这是合法批量结束)
        idx = self.src.find('elif step[0] == "end_batch":')
        chunk = self.src[idx:idx + 200]
        self.assertIn('"批量生成已结束"', chunk,
                      "end_batch step 的 log 保留,这是 auto_summarize 关闭分支的合法路径")


class TestNoCollisionWithPreviousMilestones(unittest.TestCase):
    """v1.96 不破坏 v1.91-v1.95"""

    @classmethod
    def setUpClass(cls):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            cls.src = f.read()

    def test_app_version_bumped(self):
        import re
        for line in self.src.splitlines():
            if line.startswith("APP_VERSION"):
                m = re.search(r'v(\d+)\.(\d+)', line)
                self.assertIsNotNone(m)
                major, minor = int(m.group(1)), int(m.group(2))
                self.assertGreaterEqual((major, minor), (1, 96))
                return
        self.fail("APP_VERSION not found")

    def test_v195_word_count_three_tier_intact(self):
        """v1.95 字数三档判定仍在(housekeeper.py 独立模块)"""
        hk_path = os.path.join(HERE, "housekeeper.py")
        with open(hk_path, encoding="utf-8") as f:
            hk_src = f.read()
        self.assertIn("word_count_long", hk_src)
        self.assertIn("BUG-069", hk_src)

    def test_v194_button_color_intact(self):
        # v2.03 P4: ChapterEditor 已外迁到 ui/tabs/chapter_editor.py
        chapter_editor_path = os.path.join(HERE, "ui", "tabs", "chapter_editor.py")
        with open(chapter_editor_path, encoding="utf-8") as f:
            ce_src = f.read()
        self.assertIn('color:#3a2a10', ce_src)

    def test_v193_char_fields_intact(self):
        self.assertIn('"last_ch"', self.src)
        self.assertIn('def _find_duplicate_names(rows_data)', self.src)

    def test_v192_chapter_lock_intact(self):
        self.assertIn('"locked": False', self.src)
        self.assertIn('def _toggle_chapter_lock', self.src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
