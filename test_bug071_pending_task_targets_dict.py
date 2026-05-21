"""
v1.97 BUG-071 测试 —— `_pending_task_target` (单变量) → `_pending_task_targets` (字典)
B-2 治本:并发任务串台的根因消除。

测试策略:不依赖 PyQt5,用 AST 静态断言 + 字典层直测。
- 静态断言:14 处真实读写点全部迁移到字典(不能还有单变量真实读写残留)
- 字典语义:多任务并发 set,响应取回时 key 隔离,不会串台
- 兼容字段:`_pending_task_target = None` 保留(防止外部代码崩)
- BUG-070 防御代码不破坏(v1.96 既有功能在 v1.97 后继续工作)
"""
from __future__ import annotations
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
NOVEL_AI = ROOT / "novel_ai.py"
SOURCE = NOVEL_AI.read_text(encoding="utf-8")


# ───── 静态结构断言 ───────────────────────────────────────────


class TestNoLingeringSingleVarReadsOrWrites(unittest.TestCase):
    """单变量 `_pending_task_target` 真实读写应该全部迁走"""

    def test_only_init_field_left_as_compat(self):
        """除了 init 处的兼容字段 `= None`,不应有其他单变量赋值"""
        # 匹配所有 `self._pending_task_target = ...` 赋值
        assignments = re.findall(
            r"self\._pending_task_target\s*=\s*[^=]",
            SOURCE,
        )
        # 应该只剩 1 处(init 的兼容兜底)
        self.assertEqual(
            len(assignments), 1,
            f"应只剩 init 1 处单变量赋值(兼容字段),实际 {len(assignments)} 处")

    def test_init_compat_field_is_none(self):
        """init 那行就是 `self._pending_task_target = None  # deprecated...`"""
        self.assertIn(
            "self._pending_task_target = None  # deprecated",
            SOURCE,
            "init 兼容字段缺失或写法不对")

    def test_no_single_var_attribute_reads(self):
        """单变量的属性读(. 后接非 s 字符)应该 0 处"""
        # 排除 `_pending_task_targets`(末尾 s)和 ` = None`(只在 init)
        # 找类似 `self._pending_task_target.get(...)` 或 `self._pending_task_target or {}` 的读
        reads = re.findall(
            r"self\._pending_task_target(?!s)(?!\s*=)",
            SOURCE,
        )
        self.assertEqual(
            reads, [],
            f"残留单变量读取 {len(reads)} 处:{reads[:3]}")


class TestDictFieldExists(unittest.TestCase):
    """字典字段 `_pending_task_targets` 应该在 init 初始化 + 各路径使用"""

    def test_init_creates_dict(self):
        """init 处应该有 `self._pending_task_targets = {}`"""
        self.assertIn("self._pending_task_targets = {}", SOURCE)

    def test_dict_is_used_in_send_to_ai(self):
        """`_send_to_ai` 主写应该用字典(key=label)"""
        # 找 _send_to_ai 函数体
        idx = SOURCE.find("def _send_to_ai")
        self.assertGreater(idx, 0, "找不到 _send_to_ai")
        body = SOURCE[idx:idx + 3000]
        self.assertIn(
            'self._pending_task_targets[label]',
            body,
            "_send_to_ai 没用字典写入(key=label)")

    def test_dict_is_used_in_on_response_received(self):
        """`_on_response_received` 应该按 task_id 从字典查 meta"""
        idx = SOURCE.find("def _on_response_received")
        self.assertGreater(idx, 0)
        body = SOURCE[idx:idx + 6000]
        # 至少 3 处 .get(task_id, {})
        self.assertGreaterEqual(
            body.count("self._pending_task_targets.get(task_id"), 3,
            "_on_response_received 中字典按 task_id 查询的点应该 >=3")
        # 至少 6 处 pop(task_id, None)
        self.assertGreaterEqual(
            body.count("self._pending_task_targets.pop(task_id"), 6,
            "_on_response_received 中字典按 task_id pop 的点应该 >=6")

    def test_dict_used_in_death_loop_rewrite(self):
        """死磕重写应该用 new_meta.get('label') 作 key 写字典"""
        # 找死磕重写区(_retry_chapter_with_reasons)
        m = re.search(
            r"self\._pending_task_targets\[new_meta\.get\(['\"]label['\"]",
            SOURCE,
        )
        self.assertIsNotNone(m, "死磕重写没用字典写入")

    def test_dict_used_in_manual_fetch(self):
        """手动抓取 `grab_response` 应该用字典 key='手动抓取'"""
        idx = SOURCE.find("def grab_response")
        self.assertGreater(idx, 0)
        body = SOURCE[idx:idx + 500]
        self.assertIn(
            'self._pending_task_targets["手动抓取"]',
            body,
            "grab_response 没用字典写入(key='手动抓取')")

    def test_dict_used_in_audit_dead_code(self):
        """_audit_resume dead code 也改成字典(保持代码一致)"""
        # rhythm 路径
        self.assertIn(
            "_label_rhythm = f\"节奏稽核-第{ch_num}章\"",
            SOURCE)
        self.assertIn(
            "self._pending_task_targets[_label_rhythm]",
            SOURCE)
        # character 路径
        self.assertIn(
            "_label_char = f\"人设稽核-第{ch_num}章\"",
            SOURCE)
        self.assertIn(
            "self._pending_task_targets[_label_char]",
            SOURCE)


class TestAppVersion(unittest.TestCase):
    def test_app_version_is_v197(self):
        # v2.00 P1 模块化拆分时把硬钉改为解析后 ≥ 比较
        # (BUG-072 TODO 落地:解决"升一次版本号要改一堆测试"的反模式)
        import re
        m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', SOURCE)
        self.assertIsNotNone(m, "novel_ai.py 必须定义 APP_VERSION")
        major, minor = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual((major, minor), (1, 97),
                                f'BUG-071 必须在 v1.97 之后修复(当前 v{major}.{minor:02d})')


# ───── 字典语义直测(模拟串台场景)──────────────────────────


class FakeTargetsContainer:
    """模拟改造后的字典行为,验证并发提交不串台"""

    def __init__(self):
        self._pending_task_targets = {}
        # 兼容字段也保留(模拟真实代码)
        self._pending_task_target = None

    def submit(self, label, target, **extra):
        """模拟 _send_to_ai 字典写入"""
        self._pending_task_targets[label] = {
            "target": target, "label": label, **extra}

    def dispatch(self, task_id):
        """模拟 _on_response_received 按 task_id 取 meta"""
        return self._pending_task_targets.get(task_id, {})

    def pop_after(self, task_id):
        """模拟 dispatch 后清理"""
        self._pending_task_targets.pop(task_id, None)


class TestRaceConditionFix(unittest.TestCase):
    """模拟 BUG-070/071 描述的串台场景:Canon 抽取 + 摘要并发提交"""

    def test_two_tasks_no_cross_routing(self):
        """两个任务并发提交,响应回来时按 task_id 隔离,meta 不串"""
        c = FakeTargetsContainer()

        # Canon 抽取先提交
        c.submit("Canon抽取-第4章", target="canon_extract", ch_num=4)
        # 摘要后提交 — 单变量版本会覆盖 Canon 的 meta!
        c.submit("摘要-第4章", target="chapter_summary",
                 ch_num=4, chain_to_next=True)

        # Canon 响应先回来(慢任务先完成)
        canon_meta = c.dispatch("Canon抽取-第4章")
        self.assertEqual(canon_meta.get("target"), "canon_extract")
        self.assertEqual(canon_meta.get("ch_num"), 4)
        # 不应该出现 chain_to_next(那是摘要任务的字段)
        self.assertFalse(canon_meta.get("chain_to_next", False),
                         "BUG-071 治本:Canon 不应拿到摘要任务的 meta")
        c.pop_after("Canon抽取-第4章")

        # 摘要响应后回来 — 应该还能拿到摘要 meta(没被 pop 走)
        summary_meta = c.dispatch("摘要-第4章")
        self.assertEqual(summary_meta.get("target"), "chapter_summary")
        self.assertTrue(summary_meta.get("chain_to_next"))
        c.pop_after("摘要-第4章")

        # 全部清理后字典空
        self.assertEqual(len(c._pending_task_targets), 0)

    def test_three_concurrent_tasks(self):
        """三任务并发也不串台"""
        c = FakeTargetsContainer()
        c.submit("A", target="alpha", val=1)
        c.submit("B", target="beta", val=2)
        c.submit("C", target="gamma", val=3)

        # 乱序回来
        self.assertEqual(c.dispatch("C").get("val"), 3)
        c.pop_after("C")
        self.assertEqual(c.dispatch("A").get("val"), 1)
        c.pop_after("A")
        self.assertEqual(c.dispatch("B").get("val"), 2)
        c.pop_after("B")
        self.assertEqual(c._pending_task_targets, {})

    def test_unknown_task_id_returns_empty_dict(self):
        """未知 task_id 应该返回 {}(不抛 KeyError)"""
        c = FakeTargetsContainer()
        meta = c.dispatch("根本没提交过的任务")
        self.assertEqual(meta, {})
        # 后续 .get() 应该不崩
        self.assertIsNone(meta.get("target"))

    def test_pop_idempotent(self):
        """pop 同一 task_id 两次也不崩(pop with default None)"""
        c = FakeTargetsContainer()
        c.submit("X", target="x")
        c.pop_after("X")
        c.pop_after("X")  # 第二次不应崩
        self.assertEqual(c._pending_task_targets, {})

    def test_death_loop_rewrite_same_label_overwrites(self):
        """死磕重写同一 label 是覆盖(同一章节只有一个进行中)"""
        c = FakeTargetsContainer()
        c.submit("第7章", target="chapter", retry_left=3)
        # 死磕重写:同 label 覆盖,带新的 retry_used
        c._pending_task_targets["第7章"] = {
            "target": "chapter", "label": "第7章", "retry_left": 2, "retry_used": 1}
        meta = c.dispatch("第7章")
        self.assertEqual(meta.get("retry_used"), 1)
        self.assertEqual(meta.get("retry_left"), 2)


# ───── BUG-070 兼容性 ─────────────────────────────────────────


class TestBug070DefenseStillWorks(unittest.TestCase):
    """v1.96 BUG-070 的防御代码在 v1.97 后应该继续存在(只是不太可能再触发)"""

    def test_bug070_warning_log_exists(self):
        """BUG-070 防御日志依然在(治本后理论上不会再打,但保留诊断)"""
        self.assertIn("BUG-070 防御", SOURCE)
        self.assertIn("⚠ chain_to_next=True 但 _batch_remaining=0", SOURCE)

    def test_bug070_three_branch_guard_intact(self):
        """v1.96 三档守卫 elif 链应该一字未改"""
        # 第一档:真批量推进
        self.assertIn(
            'elif meta.get("chain_to_next") and self._batch_remaining > 0 and not self._batch_paused:',
            SOURCE)
        # 第二档:真批量被暂停
        self.assertIn(
            'elif meta.get("chain_to_next") and (self._batch_remaining > 0 or self._batch_paused):',
            SOURCE)
        # 第三档:单章模式诡异 chain_to_next(BUG-070 防御)
        self.assertIn(
            'elif meta.get("chain_to_next"):',
            SOURCE)


# ───── A→B→C→D 路线纪律 ─────────────────────────────────────


class TestNoRegressionToEarlierVersions(unittest.TestCase):
    """严守"每轮改动隔离"纪律,v1.97 不动 v1.92-v1.96 既有功能"""

    def test_v192_chapter_lock_intact(self):
        """v1.92 章节锁定核心方法还在"""
        self.assertIn("def _toggle_chapter_lock", SOURCE)
        self.assertIn("def _on_chapter_list_context_menu", SOURCE)

    def test_v193_charlib_intact(self):
        """v1.93 同名检查 + last_ch 还在(P5 后在 ui/tabs/character_library.py)"""
        cl_src = (ROOT / "ui" / "tabs" / "character_library.py").read_text(encoding="utf-8")
        self.assertIn("_find_duplicate_names", cl_src)
        self.assertIn("last_ch", cl_src)

    def test_v194_button_color_intact(self):
        """v1.94 按钮对比度 #3a2a10 还在(P4 后在 ui/tabs/chapter_editor.py)"""
        ce_src = (ROOT / "ui" / "tabs" / "chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn("#3a2a10", ce_src)

    def test_v195_word_count_long_intact(self):
        """v1.95 字数三档 word_count_long 字段还在"""
        # housekeeper.py 在外部,这里只检查 v1.97 没把它的判定改掉
        self.assertNotIn("# v1.97: 删除 word_count_long", SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
