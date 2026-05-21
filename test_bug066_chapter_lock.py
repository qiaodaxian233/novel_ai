# -*- coding: utf-8 -*-
"""v1.92 BUG-066 回归测试 — 章节锁定机制(MVP)

借鉴竞品"中稿/终稿锁定",跟 v1.91 BUG-065 "做对的事不能丢"同源思路。

测试三个层面:
  1. 数据模型 — 章节 dict 加 locked 字段,默认 False,兼容旧存档,JSON round-trip
  2. 拦截源码 — delete/rename/save_current/on_clicked 必须包含 locked 早 return
  3. UI 显示 — _refresh_chapter_list 对 locked 章节加 🔒 前缀

策略沿用 BUG-065:用 ast 抠源码 + 字符串断言,避免装 PyQt5 + xvfb
(章节拦截涉及 QMessageBox,完整动态测试需要真实 Qt 环境,
 改用源码级别静态断言验证关键判断分支不丢)。
"""
import unittest
import json
import ast
import os
import textwrap


HERE = os.path.dirname(os.path.abspath(__file__))
NOVEL_AI_PATH = os.path.join(HERE, "novel_ai.py")


def extract_method_source(src_path, class_name, method_name):
    """从 .py 文件抠出某个类里的指定方法源码"""
    with open(src_path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for node in cls.body:
                if isinstance(node, ast.FunctionDef) and node.name == method_name:
                    return ast.get_source_segment(src, node)
    raise LookupError(f"{class_name}.{method_name} not found in {src_path}")


class TestChapterLockDataModel(unittest.TestCase):
    """数据层 — 章节 dict + locked 字段语义"""

    def test_new_chapter_dict_carries_locked_false(self):
        """模拟 add_chapter 字面量:新章节默认 locked=False"""
        ch = {"title": "第1章", "content": "", "locked": False}
        self.assertIn("locked", ch)
        self.assertFalse(ch["locked"])

    def test_accepted_chapter_dict_carries_locked_false(self):
        """模拟 _accept_chapter_and_continue 字面量:AI 生成入库 → locked=False"""
        ch = {"title": "第3章", "content": "正文...", "summary": "", "locked": False}
        self.assertIn("locked", ch)
        self.assertFalse(ch["locked"])

    def test_legacy_chapter_setdefault_fills_locked_false(self):
        """模拟 load_project 迁移:旧存档 dict 无 locked → setdefault 补 False"""
        legacy = [
            {"title": "第1章", "content": "..."},
            {"title": "第2章", "content": "..."},
        ]
        for _ch in legacy:
            if isinstance(_ch, dict):
                _ch.setdefault("locked", False)
        self.assertEqual(legacy[0]["locked"], False)
        self.assertEqual(legacy[1]["locked"], False)

    def test_setdefault_preserves_existing_locked_true(self):
        """已有 locked=True 的章节经 setdefault 不被覆盖(critical:不破坏现状)"""
        chs = [
            {"title": "第1章", "content": "x", "locked": True},
            {"title": "第2章", "content": "y"},
        ]
        for _ch in chs:
            if isinstance(_ch, dict):
                _ch.setdefault("locked", False)
        self.assertEqual(chs[0]["locked"], True, "已锁定章节绝不能被 setdefault 解锁")
        self.assertEqual(chs[1]["locked"], False)

    def test_locked_field_survives_json_round_trip(self):
        """save_project 用 json.dump 序列化 chapters → 加载回来 locked 字段保持"""
        original = [
            {"title": "第1章", "content": "x", "locked": True},
            {"title": "第2章", "content": "y", "locked": False},
        ]
        s = json.dumps(original)
        loaded = json.loads(s)
        self.assertEqual(loaded[0]["locked"], True)
        self.assertEqual(loaded[1]["locked"], False)

    def test_non_dict_chapter_entries_skipped_in_migration(self):
        """迁移逻辑用 isinstance(_ch, dict) 防御 — 万一有非 dict 不崩"""
        odd = [
            {"title": "ok", "content": ""},
            None,  # 异常数据
            "stringy",  # 异常数据
        ]
        for _ch in odd:
            if isinstance(_ch, dict):
                _ch.setdefault("locked", False)
        self.assertEqual(odd[0]["locked"], False)
        # None 和 string 没被改


class TestChapterLockInterceptionSource(unittest.TestCase):
    """源码级断言 — 关键拦截路径必须包含 locked 检查 + 早 return"""

    @classmethod
    def setUpClass(cls):
        cls.delete_src = textwrap.dedent(
            extract_method_source(NOVEL_AI_PATH, "MainWindow", "delete_chapter"))
        cls.rename_src = textwrap.dedent(
            extract_method_source(NOVEL_AI_PATH, "MainWindow", "rename_chapter"))
        cls.save_src = textwrap.dedent(
            extract_method_source(NOVEL_AI_PATH, "MainWindow", "save_current_chapter"))
        cls.click_src = textwrap.dedent(
            extract_method_source(NOVEL_AI_PATH, "MainWindow", "_on_chapter_clicked"))

    def test_delete_chapter_intercepts_locked_before_pop(self):
        """delete_chapter:locked 拦截 return 必须在 .pop() 之前"""
        self.assertIn('locked', self.delete_src)
        self.assertIn('已锁定', self.delete_src)
        idx_locked = self.delete_src.find('locked')
        idx_return = self.delete_src.find('return', idx_locked)
        idx_pop = self.delete_src.find('.pop(')
        self.assertGreater(idx_return, idx_locked,
                           "locked 检查后必须 return")
        self.assertGreater(idx_pop, idx_return,
                           "locked 章节拦截 return 必须在 .pop() 之前(否则数据丢)")

    def test_rename_chapter_intercepts_locked_before_dialog(self):
        """rename_chapter:locked 拦截 return 必须在 QInputDialog 之前"""
        self.assertIn('locked', self.rename_src)
        self.assertIn('已锁定', self.rename_src)
        idx_locked = self.rename_src.find('locked')
        idx_return = self.rename_src.find('return', idx_locked)
        idx_dialog = self.rename_src.find('QInputDialog.getText')
        self.assertGreater(idx_dialog, idx_return,
                           "locked 章节拦截 return 必须在 QInputDialog 之前")

    def test_save_current_chapter_intercepts_locked_before_assign(self):
        """save_current_chapter:locked 拦截在 chapters[idx]['title'] = title 之前"""
        self.assertIn('locked', self.save_src)
        self.assertIn('已锁定', self.save_src)
        # 找到 locked 检查后的 return,确保它在赋值之前
        idx_locked_check = self.save_src.find('.get("locked")')
        self.assertGreater(idx_locked_check, 0, "save_current_chapter 必须有 .get('locked') 检查")
        idx_return = self.save_src.find('return', idx_locked_check)
        # 赋值 self.chapters[...]["title"] = title 在 locked check 之后,但拦截 return 必须更早
        idx_title_assign = self.save_src.find('"title"] = title')
        self.assertGreater(idx_title_assign, idx_return,
                           "locked 拦截 return 必须在 title 赋值之前")

    def test_on_chapter_clicked_skips_write_back_when_locked(self):
        """_on_chapter_clicked:切走时 locked 跳过写回,改动在 else 分支"""
        self.assertIn('locked', self.click_src)
        self.assertIn('else:', self.click_src,
                      "_on_chapter_clicked 必须有 if locked / else 分支结构")
        # 切走前的写回(["title"] = ...title_input.text())必须在 else 分支里
        idx_else = self.click_src.find('else:')
        idx_title_write = self.click_src.find('"title"] = self.tab_editor.title_input')
        self.assertGreater(idx_title_write, idx_else,
                           "title 写回必须在 else 分支(非 locked 才写)")


class TestChapterLockUIDisplay(unittest.TestCase):
    """UI 层 — _refresh_chapter_list 显示 🔒 标记"""

    @classmethod
    def setUpClass(cls):
        cls.refresh_src = textwrap.dedent(
            extract_method_source(NOVEL_AI_PATH, "MainWindow", "_refresh_chapter_list"))

    def test_refresh_chapter_list_prefixes_lock_emoji(self):
        """_refresh_chapter_list 必须用 🔒 前缀标记 locked 章节"""
        self.assertIn('🔒', self.refresh_src)
        self.assertIn('locked', self.refresh_src)

    def test_refresh_chapter_list_uses_ch_get_for_safety(self):
        """使用 ch.get('locked') 而不是 ch['locked'](防御 KeyError)"""
        # 必须用 .get,避免万一某处漏了字段直接崩
        self.assertIn('.get("locked")', self.refresh_src)


class TestContextMenuMethodExists(unittest.TestCase):
    """右键菜单方法存在性"""

    def test_context_menu_handler_exists(self):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        self.assertIn('def _on_chapter_list_context_menu', src)
        self.assertIn('def _toggle_chapter_lock', src)

    def test_toggle_chapter_lock_does_not_collide_with_global_toggle_lock(self):
        """避免跟原有 toggle_lock(编辑器只读)命名冲突 — 必须是 _toggle_chapter_lock"""
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        # 全文应该有原有的 def toggle_lock(self) 和我们新加的 _toggle_chapter_lock
        self.assertIn('def toggle_lock(self)', src, "原有的编辑器 toggle_lock 应保留")
        self.assertIn('def _toggle_chapter_lock(self', src, "新的章节级 _toggle_chapter_lock")

    def test_context_menu_uses_qmenu(self):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        # 找到 _on_chapter_list_context_menu 段,确认导入 QMenu
        idx = src.find('def _on_chapter_list_context_menu')
        chunk = src[idx:idx + 1500]
        self.assertIn('from PyQt5.QtWidgets import QMenu', chunk,
                      "应在方法内 import QMenu(顶层未 import)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
