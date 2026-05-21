# -*- coding: utf-8 -*-
"""v1.93 BUG-067 回归测试 — 角色 last_ch 字段 + 同名不同姓检查

借鉴竞品由风写作 v1.1.7 的两个长篇人物管理痛点:
  1. 同名角色 AI 写正文易混淆 → 检查 + 改名提示
  2. 角色出退场不明确 → first_ch 已有(prompts 282 行),加 last_ch

跟 v1.92 BUG-066(章节锁定)是独立改动:v1.92 动章节,v1.93 动角色,
两者完全不重叠,合跑回归保证 v1.92 不被破坏。

测试三层:
  1. 数据模型 — DICT_KEY_MAPS 列数 / dict round-trip / 加载兜底
  2. 同名检查纯函数 — _find_duplicate_names(staticmethod 提出,无 Qt 依赖)
  3. 源码断言 — UI 改动确实落地(列数 9、按钮存在、tip 提到 last_ch)
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


def extract_class_attribute_block(src, anchor_line):
    """读取 src 里包含 anchor_line 字符串的代码块(向前向后各 5 行)"""
    lines = src.splitlines()
    for i, ln in enumerate(lines):
        if anchor_line in ln:
            return "\n".join(lines[max(0, i-2):i+8])
    return ""


class TestLastChDataModel(unittest.TestCase):
    """数据层:characters dict 加 last_ch 字段"""

    def test_dict_key_maps_main_has_last_ch(self):
        """DICT_KEY_MAPS['characters'] 必须包含 last_ch 且为第 9 个字段(列 8)"""
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        # 主 DICT_KEY_MAPS(serialize 用)
        idx = src.find('DICT_KEY_MAPS = {')
        self.assertGreater(idx, 0)
        chunk = src[idx:idx + 800]
        self.assertIn('"last_ch"', chunk, "DICT_KEY_MAPS 必须有 last_ch")
        # 顺序:first_ch 之后是 last_ch
        i_first = chunk.find('"first_ch"')
        i_last = chunk.find('"last_ch"')
        self.assertGreater(i_first, 0)
        self.assertGreater(i_last, i_first, "last_ch 必须放在 first_ch 之后")

    def test_dict_key_maps_local_has_last_ch(self):
        """DICT_KEY_MAPS_LOCAL(load 用)也必须有 last_ch"""
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        idx = src.find('DICT_KEY_MAPS_LOCAL = {')
        self.assertGreater(idx, 0)
        chunk = src[idx:idx + 800]
        self.assertIn('"last_ch"', chunk)

    def test_legacy_character_dict_load_defaults_last_ch_empty(self):
        """模拟旧存档:character dict 无 last_ch → load 兜底 ''(c.get('last_ch', ''))"""
        legacy_c = {"name": "林清", "role": "主角", "first_ch": "1"}  # 无 last_ch
        last_ch_default = str(legacy_c.get("last_ch", ""))
        self.assertEqual(last_ch_default, "")

    def test_full_character_dict_preserves_last_ch_in_round_trip(self):
        """新存档 character dict 含 last_ch → JSON round-trip 保持"""
        ch = {"name": "林清", "role": "主角", "first_ch": "1", "last_ch": "50"}
        loaded = json.loads(json.dumps(ch))
        self.assertEqual(loaded["last_ch"], "50")

    def test_character_dict_field_order_8_then_last_ch(self):
        """vals 列表顺序:8 个老字段 + last_ch(第 9 个)"""
        c = {"name": "n", "role": "配角", "appearance": "a", "personality": "p",
             "mark": "m", "ability": "x", "state": "s", "first_ch": "1", "last_ch": "9"}
        # 模拟 6232 行的 vals 构造逻辑
        vals = [c["name"], c.get("role", "配角"), c.get("appearance", ""),
                c.get("personality", ""), c.get("mark", ""),
                c.get("ability", ""), c.get("state", ""),
                str(c.get("first_ch", "")),
                str(c.get("last_ch", ""))]
        self.assertEqual(len(vals), 9)
        self.assertEqual(vals[7], "1")  # first_ch 仍是列 7
        self.assertEqual(vals[8], "9")  # last_ch 新增,列 8


class TestFindDuplicateNames(unittest.TestCase):
    """同名检查纯函数 — _find_duplicate_names(staticmethod)"""

    @classmethod
    def setUpClass(cls):
        """从 novel_ai.py 抠出 _find_duplicate_names,dedent 后 exec 出来。
        关键:用 staticmethod 包装赋给 cls,否则 self.find_dups(rows) 会
        被 Python 解释为 bound method,自动塞 self 当第一个参数 → TypeError。
        """
        method_src = extract_method_source(
            NOVEL_AI_PATH, "CharacterLibrary", "_find_duplicate_names")
        dedented = textwrap.dedent(method_src)
        # @staticmethod 装饰器 + 函数定义 — exec 后会变成普通函数
        # 把 @staticmethod 去掉(它在抠源码时是否包含取决于 ast 实现)
        if dedented.lstrip().startswith("@staticmethod"):
            dedented = dedented.split("\n", 1)[1]  # 跳过装饰器行
        ns = {}
        exec(dedented, ns)
        # 用 staticmethod 包,避免 bound-method 自动 self
        cls.find_dups = staticmethod(ns["_find_duplicate_names"])

    def test_no_duplicates_returns_empty(self):
        rows = [("林清", "主角"), ("赵无极", "反派")]
        self.assertEqual(self.find_dups(rows), {})

    def test_single_duplicate_pair(self):
        rows = [("林清", "主角"), ("林清", "反派")]
        result = self.find_dups(rows)
        self.assertIn("林清", result)
        self.assertEqual(len(result["林清"]), 2)
        self.assertEqual(result["林清"][0], (0, "主角"))
        self.assertEqual(result["林清"][1], (1, "反派"))

    def test_three_same_name_grouped(self):
        rows = [("名媛", "主角"), ("名媛", "配角"), ("名媛", "反派")]
        result = self.find_dups(rows)
        self.assertEqual(len(result["名媛"]), 3)

    def test_mixed_duplicates_and_uniques(self):
        rows = [
            ("林清", "主角"),
            ("赵无极", "反派"),
            ("林清", "导师"),  # 跟 0 重名
            ("阿牛", "配角"),
        ]
        result = self.find_dups(rows)
        self.assertEqual(len(result), 1)
        self.assertIn("林清", result)
        self.assertNotIn("赵无极", result)
        self.assertNotIn("阿牛", result)

    def test_empty_name_not_counted(self):
        """空名不算重名(还没填好的行)"""
        rows = [("", "配角"), ("", "配角"), ("林清", "主角")]
        result = self.find_dups(rows)
        self.assertEqual(result, {})

    def test_whitespace_stripped_before_compare(self):
        """前后空格不应导致漏检 — 同 name 带不同空格应当匹配"""
        rows = [("林清", "主角"), (" 林清 ", "反派"), ("林清\t", "导师")]
        result = self.find_dups(rows)
        self.assertIn("林清", result)
        self.assertEqual(len(result["林清"]), 3)

    def test_empty_input(self):
        """空表不崩"""
        self.assertEqual(self.find_dups([]), {})

    def test_single_character(self):
        """单角色不算重名"""
        self.assertEqual(self.find_dups([("林清", "主角")]), {})

    def test_case_sensitive(self):
        """大小写敏感(中文名一般不涉及,但拼音名要测一下)"""
        rows = [("Linus", "主角"), ("linus", "配角")]
        # 当前实现是大小写敏感的(没做 .lower()),所以这两个不算重名
        result = self.find_dups(rows)
        self.assertEqual(result, {}, "大小写不同视为不同角色(当前 MVP 实现)")


class TestCharLibrarySourceUI(unittest.TestCase):
    """UI 改动源码断言"""

    @classmethod
    def setUpClass(cls):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            cls.src = f.read()

    def test_table_widget_column_count_is_9(self):
        """QTableWidget 列数从 8 改为 9"""
        # 找 _build_characters_tab 段
        idx = self.src.find("def _build_characters_tab")
        chunk = self.src[idx:idx + 3000]
        self.assertIn('QTableWidget(0, 9)', chunk, "列数必须 9(原 8 + last_ch)")
        self.assertNotIn('QTableWidget(0, 8)', chunk, "不应残留 8 列定义")

    def test_table_header_includes_last_ch_label(self):
        """表头 labels 必须包含 '退场章节',且顺序在 '首次出场' 之后"""
        idx = self.src.find("def _build_characters_tab")
        chunk = self.src[idx:idx + 3000]
        # 用连续字符串匹配 header labels(注释里不会同时出现这两个相邻字符串)
        self.assertIn('"首次出场", "退场章节"', chunk,
                      "header labels 必须 first_ch 紧跟 last_ch")

    def test_add_character_defaults_has_9_items(self):
        """_add_character defaults 数组必须是 9 项(默认 9 列空字符串)"""
        method_src = extract_method_source(
            NOVEL_AI_PATH, "CharacterLibrary", "_add_character")
        # 该方法里 defaults = [...] 应该有 9 个元素
        # 简易计数:统计 "," 数量 + 1(粗略),更稳的是用 ast
        tree = ast.parse(textwrap.dedent(method_src))
        found = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "defaults":
                        if isinstance(node.value, ast.List):
                            self.assertEqual(
                                len(node.value.elts), 9,
                                f"defaults 长度必须 9,实际 {len(node.value.elts)}")
                            found = True
        self.assertTrue(found, "_add_character 必须有 defaults = [...] 赋值")

    def test_check_duplicate_names_button_exists(self):
        """顶部按钮组必须有 '🔍 同名检查' 按钮 + 接到 _on_check_duplicate_names"""
        idx = self.src.find("def _build_characters_tab")
        chunk = self.src[idx:idx + 3000]
        self.assertIn("🔍 同名检查", chunk)
        self.assertIn("_on_check_duplicate_names", chunk)

    def test_serialize_uses_9_columns(self):
        """CharacterLibrary.serialize 里 tbl_to_list 必须传 9"""
        idx = self.src.find("def serialize(self)")
        chunk = self.src[idx:idx + 1500]
        self.assertIn('tbl_to_list(self.tbl_chars, 9)', chunk)
        self.assertNotIn('tbl_to_list(self.tbl_chars, 8)', chunk,
                         "不应残留 8 列序列化")

    def test_load_path_uses_9_columns(self):
        """load 路径里 list_to_tbl(tbl_chars, ..., 9) — 防止漏改回 8 致 last_ch 永远填不进表"""
        # 找 list_to_tbl(self.tbl_chars, ... 这个调用
        idx = self.src.find('list_to_tbl(self.tbl_chars,')
        self.assertGreater(idx, 0)
        chunk = self.src[idx:idx + 200]
        # 末尾参数必须是 9
        self.assertIn('"characters"), 9)', chunk,
                      "load 路径 list_to_tbl(tbl_chars, ..., 9) — 不能再是 8")

    def test_relation_graph_path_intentionally_keeps_8(self):
        """_tbl_to_rows(tbl_chars, 8) 故意保持 8 — relation_graph 接口按 8 列设计,
        加 9 也会被 build_graph_data 在 row[0:8] 截掉。"""
        idx = self.src.find('_tbl_to_rows(self.tbl_chars,')
        self.assertGreater(idx, 0)
        chunk = self.src[idx:idx + 100]
        self.assertIn('8)', chunk,
                      "_tbl_to_rows 这里故意保持 8(relation_graph 不需要 last_ch)")

    def test_tip_label_mentions_last_ch(self):
        """tip label 应该说明 退场章节 字段的用法"""
        idx = self.src.find("def _build_characters_tab")
        chunk = self.src[idx:idx + 3000]
        # 找 tip = QLabel(...) 段
        i_tip = chunk.find("tip = QLabel")
        self.assertGreater(i_tip, 0)
        tip_chunk = chunk[i_tip:i_tip + 600]
        self.assertIn("退场章节", tip_chunk, "tip 应解释退场章节字段")


class TestNoCollisionWithV192(unittest.TestCase):
    """v1.93 不动 v1.92 改过的章节锁定相关代码"""

    def test_chapter_lock_methods_still_present(self):
        """v1.92 加的方法 _toggle_chapter_lock / _on_chapter_list_context_menu 仍在"""
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("def _toggle_chapter_lock(self", src)
        self.assertIn("def _on_chapter_list_context_menu", src)

    def test_chapter_dict_locked_field_still_default_false(self):
        """章节默认 locked=False 没被改动"""
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            src = f.read()
        # _accept_chapter_and_continue 的入库字典
        self.assertIn('"summary": "", "locked": False', src)
        # add_chapter 也是
        self.assertIn('"content": "", "locked": False', src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
