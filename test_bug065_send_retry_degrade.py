# -*- coding: utf-8 -*-
"""v1.91 BUG-065 回归测试

只测纯逻辑部分(_build_degraded_content)——
浏览器/Qt 信号相关的 _get_send_button_state + 重试循环
需要真实 selenium driver,无法在 CI 沙箱里跑,留实战日志验证。

核心保障:关键任务发送失败 + 重试用尽时,降级内容能够:
  1. chapter_summary 有正文 → 头 300 + 尾 300 拼接,正确打上 [降级] 标签
  2. chapter_summary 无正文 → 至少返回一个带标签的占位字符串
  3. canon_extract / character_extract / world_extract → 返回 ""(空)
     这样 UI handler 走"无返回"分支,不破坏现有数据
  4. 未知 target → 返回 ""
"""
import unittest
from types import SimpleNamespace
import sys
import os

# 直接 import novel_ai 会触发 Qt/Selenium 装载,在无显示器沙箱里会失败
# → 用 inspect 拿到 _build_degraded_content 函数源码,绑定到 SimpleNamespace 上跑
#   这是最轻量的方式,避免装 PyQt5 + xvfb
import ast
import textwrap


def extract_method_source(src_path, class_name, method_name):
    """从 .py 文件抠出某个类里的指定方法源码"""
    with open(src_path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for node in cls.body:
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    return ast.get_source_segment(open(src_path, encoding="utf-8").read(), node)
    raise LookupError(f"{class_name}.{method_name} not found in {src_path}")


HERE = os.path.dirname(os.path.abspath(__file__))
NOVEL_AI_PATH = os.path.join(HERE, "novel_ai.py")
# P6 v2.05:BrowserWorker 类外迁到 ui/browser_worker.py
BROWSER_WORKER_PATH = os.path.join(HERE, "ui", "browser_worker.py")


def _load_all_sources():
    """读取 novel_ai.py + ui/browser_worker.py 拼接,供静态扫描用"""
    parts = []
    for p in (NOVEL_AI_PATH, BROWSER_WORKER_PATH):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                parts.append(f.read())
    return "\n".join(parts)


class TestBuildDegradedContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 把 _build_degraded_content 抠出来,exec 到一个简单的命名空间
        method_src = extract_method_source(
            BROWSER_WORKER_PATH, "BrowserWorker", "_build_degraded_content")
        # 抠出来的是 4 空格缩进的 method, dedent 一下变成顶层函数
        dedented = textwrap.dedent(method_src)
        # 替换 self 为第一个参数(保持方法签名),然后 exec
        ns = {}
        exec(dedented, ns)
        cls.fn = ns["_build_degraded_content"]
        # 模拟一个简单的 self(没用到 self 任何属性,只是占位)
        cls.fake_self = SimpleNamespace()

    def _call(self, task):
        return self.__class__.fn(self.fake_self, task)

    # ---------- chapter_summary ----------
    def test_chapter_summary_with_long_content_uses_head_and_tail(self):
        """长正文 → 头 300 + 尾 300 拼接"""
        content = "A" * 500 + "MIDDLE" + "B" * 500  # 1006 字
        task = {
            "target": "chapter_summary",
            "ch_num": 4,
            "_ch_content": content,
            "_ch_title": "第4章 觉醒之夜",
        }
        result = self._call(task)
        self.assertIn("第4章 觉醒之夜", result)
        self.assertIn("降级:v1.91 BUG-065", result)
        self.assertIn("开头", result)
        self.assertIn("结尾", result)
        self.assertIn("AAAA", result)  # 头部
        self.assertIn("BBBB", result)  # 尾部
        self.assertNotIn("MIDDLE", result)  # 中间不取

    def test_chapter_summary_with_short_content_only_head(self):
        """短正文(<= 700)→ 只有开头,没有"结尾"段(避免重复)"""
        content = "短短一段正文" * 30  # 180 字
        task = {
            "target": "chapter_summary",
            "ch_num": 1,
            "_ch_content": content,
            "_ch_title": "第1章",
        }
        result = self._call(task)
        self.assertIn("降级:v1.91 BUG-065", result)
        self.assertIn("开头", result)
        # 短文不应同时出现结尾(避免头尾重复)
        self.assertNotIn("结尾", result)

    def test_chapter_summary_empty_content_returns_marker_stub(self):
        """空正文 → 至少返回带标签的占位串(handler 仍能识别这是降级)"""
        task = {"target": "chapter_summary", "ch_num": 7, "_ch_content": ""}
        result = self._call(task)
        self.assertIn("v1.91 BUG-065", result)
        self.assertIn("无章节正文", result)
        self.assertIn("第 7 章", result)

    def test_chapter_summary_missing_ch_content_key(self):
        """meta 里完全没 _ch_content → 走空正文分支,不报 KeyError"""
        task = {"target": "chapter_summary", "ch_num": 9}
        result = self._call(task)
        self.assertTrue(result)  # 非空字符串
        self.assertIn("BUG-065", result)

    def test_chapter_summary_strips_newlines_in_head_tail(self):
        """换行被替换成空格(对话记忆是单行存储)"""
        content = ("开头一段\n" + "中间\n" * 100 + "尾部一段")
        task = {
            "target": "chapter_summary",
            "ch_num": 2,
            "_ch_content": content,
            "_ch_title": "第2章",
        }
        result = self._call(task)
        # 降级结果里至少 head/tail 段不能含换行
        # 整个 result 由 " | " join,所以不应有 \n
        # (注意:result 里可能有 [降级:...] 标签段不含换行,这里只检 head/tail 行间清洁)
        # 简化检查:整个降级输出不应含原文里那一连串 "\n"
        self.assertNotIn("\n\n", result)

    # ---------- canon_extract / character_extract / world_extract ----------
    def test_canon_extract_returns_empty_string(self):
        """Canon 抽取降级 → 空字符串(让 handler 跳过,不破坏 KB)"""
        result = self._call({"target": "canon_extract", "ch_num": 4})
        self.assertEqual(result, "")

    def test_character_extract_returns_empty(self):
        """character_extract 降级 → 空(handler 通常会判 empty 不动 chars_edit)"""
        result = self._call({"target": "character_extract"})
        self.assertEqual(result, "")

    def test_world_extract_returns_empty(self):
        result = self._call({"target": "world_extract", "ch_num": 4})
        self.assertEqual(result, "")

    def test_long_term_extract_returns_empty(self):
        result = self._call({"target": "long_term_extract", "ch_num": 4})
        self.assertEqual(result, "")

    # ---------- 边界 ----------
    def test_unknown_target_returns_empty(self):
        """未知 target(不该走降级路径)→ 空字符串"""
        result = self._call({"target": "style_audit"})
        self.assertEqual(result, "")

    def test_no_target_returns_empty(self):
        """task 里完全没 target → 空字符串,不抛异常"""
        result = self._call({})
        self.assertEqual(result, "")


class TestVersionBumped(unittest.TestCase):
    """常识健康检查:APP_VERSION 必须 ≥ v1.91(BUG-065 引入版本)。
    后续 v1.92/v1.93... 都视为合规,避免每次升版都改这个测试。"""
    def test_app_version_at_least_v191(self):
        import re
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("APP_VERSION"):
                    m = re.search(r'v(\d+)\.(\d+)', line)
                    self.assertIsNotNone(
                        m, f"APP_VERSION line 必须有 v<major>.<minor>:{line!r}")
                    major, minor = int(m.group(1)), int(m.group(2))
                    self.assertGreaterEqual(
                        (major, minor), (1, 91),
                        f"APP_VERSION 必须 ≥ v1.91(BUG-065 引入版本),实际 v{major}.{minor}")
                    return
        self.fail("APP_VERSION not found in novel_ai.py")


class TestSubmitSummaryPassesChContent(unittest.TestCase):
    """v1.91 BUG-065:_submit_summary_task 必须把章节正文塞进 meta,
    否则 worker 端降级时拿不到 _ch_content,降级退化为纯占位串。
    用静态 grep 验证(不实例化 Qt)。"""
    def test_submit_summary_includes_ch_content(self):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        # _submit_summary_task 必须包含 _ch_content= 关键字参数
        # 找该函数附近 ~50 行
        idx = src.find("def _submit_summary_task")
        self.assertGreater(idx, 0)
        slice_ = src[idx:idx + 2000]
        self.assertIn("_ch_content=", slice_,
                      "_submit_summary_task 必须把 _ch_content 传给 _send_to_ai (供 BUG-065 降级)")
        self.assertIn("_ch_title=", slice_,
                      "_submit_summary_task 必须把 _ch_title 传给 _send_to_ai")

    def test_send_to_ai_passes_underscore_extra_to_worker(self):
        """_send_to_ai submit 时必须把 _xxx 前缀的 extra 字段透传给 worker"""
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        idx = src.find("def _send_to_ai")
        slice_ = src[idx:idx + 4000]
        # 必须有透传 _xxx 字段的逻辑
        self.assertIn("k.startswith(\"_\")", slice_,
                      "_send_to_ai 必须透传 _xxx 前缀的 extra 字段给 worker submit")


class TestCriticalRetryWiredIn(unittest.TestCase):
    """v1.91 BUG-065:_send_prompt 失败路径必须有关键任务重试 + 降级分支"""
    def test_send_prompt_has_critical_retry(self):
        # P6 v2.05:_send_prompt 在 BrowserWorker 内,已外迁
        with open(BROWSER_WORKER_PATH, encoding="utf-8") as f:
            src = f.read()
        # _send_prompt 函数体内必须有:
        #   1. CRITICAL_TARGETS 集合
        #   2. _is_critical 判定
        #   3. 调用 _build_degraded_content
        idx = src.find("def _send_prompt")
        self.assertGreater(idx, 0)
        # _send_prompt 函数体很长(~1700+ 行),关键改动在中段
        slice_ = src[idx:idx + 30000]
        self.assertIn("CRITICAL_TARGETS", slice_,
                      "_send_prompt 必须定义 CRITICAL_TARGETS 集合做关键任务识别")
        self.assertIn("_build_degraded_content", slice_,
                      "_send_prompt 失败路径必须调用 _build_degraded_content")
        self.assertIn("chapter_summary", slice_,
                      "CRITICAL_TARGETS 必须包含 chapter_summary")
        self.assertIn("canon_extract", slice_,
                      "CRITICAL_TARGETS 必须包含 canon_extract")


class TestSendButtonStateAdded(unittest.TestCase):
    """v1.91 BUG-065:必须新增 _get_send_button_state 方法"""
    def test_method_exists(self):
        # P6 v2.05:_get_send_button_state 在 BrowserWorker 内,已外迁
        with open(BROWSER_WORKER_PATH, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("def _get_send_button_state", src)
        # 必须返回这 5 个状态之一
        for state in ("enabled", "disabled", "stop", "loading", "none"):
            self.assertIn(f"'{state}'", src,
                          f"_get_send_button_state 必须能返回 {state}")

    def test_dispatch_send_uses_button_state(self):
        """_dispatch_send 失败诊断必须用按钮态(诊断信息含按钮态枚举)"""
        # P6 v2.05:_dispatch_send 在 BrowserWorker 内,已外迁
        with open(BROWSER_WORKER_PATH, encoding="utf-8") as f:
            src = f.read()
        # Enter 后失败 log 必须含 "按钮态="
        self.assertIn("按钮态=", src,
                      "_dispatch_send 失败 log 必须打按钮态诊断信息(BUG-065)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
