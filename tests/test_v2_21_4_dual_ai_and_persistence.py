# -*- coding: utf-8 -*-
"""v2.21.4 守护测试

BUG-080:伏笔 Tab 数据完全没保存 — 重启程序伏笔全丢失
BUG-079:hero_state 全空字段不该注入 prompt
新功能:双 AI 分工(主 AI 写章节 + 副 AI 抽数据)
新功能:关系图分层布局
"""
import os
import sys
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # tests/ 的上一级 = 仓库根(测试搬迁修复)
NOVEL_AI = HERE / "novel_ai.py"
CHARLIB = HERE / "ui" / "tabs" / "character_library.py"
GENCTRL = HERE / "ui" / "tabs" / "generation_control.py"
RELGRAPH = HERE / "relation_graph.py"
CONSTS = HERE / "core" / "constants.py"
PROFILES = HERE / "core" / "site_profiles.py"


class TestBUG080ForeshadowPersistence(unittest.TestCase):
    """BUG-080:伏笔 Tab 数据必须能保存/加载/清空"""

    @classmethod
    def setUpClass(cls):
        cls.src = NOVEL_AI.read_text(encoding="utf-8")

    def test_autosave_includes_open_loops(self):
        """_autosave 必须保存 open_loops 字段"""
        m = re.search(r"def _autosave\(self\):.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn('"open_loops"', block,
            "BUG-080:_autosave 没保存 open_loops,重启丢失")
        self.assertIn("tab_foreshadow.sync_to_mw", block,
            "BUG-080:保存前没同步伏笔 UI → mw.open_loops")

    def test_save_project_includes_open_loops(self):
        """save_project 也要保存 open_loops"""
        m = re.search(r"def save_project\(self\):.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn('"open_loops"', block,
            "BUG-080:save_project 也没保存 open_loops")

    def test_load_payload_restores_open_loops(self):
        """_load_payload_into_ui 必须还原 open_loops"""
        m = re.search(r"def _load_payload_into_ui.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn('d.get("open_loops")', block,
            "BUG-080:加载时不读 open_loops")
        self.assertIn("tab_foreshadow", block,
            "BUG-080:加载时不刷新伏笔 UI")

    def test_reset_clears_open_loops(self):
        """_reset_ui_state 必须清 open_loops + 伏笔表"""
        m = re.search(r"def _reset_ui_state\(self\):.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn("self.open_loops = {}", block,
            "BUG-080:reset 没清空 open_loops")
        self.assertIn("tab_foreshadow", block,
            "BUG-080:reset 没清空伏笔 UI")


class TestBUG079HeroStateInjection(unittest.TestCase):
    """BUG-079:hero_state 全空字段不该注入"""

    @classmethod
    def setUpClass(cls):
        cls.src = CHARLIB.read_text(encoding="utf-8")

    def test_no_empty_field_injection(self):
        """新写法用条件 if + append,不再固定拼接"""
        # 老写法:f"修为 {self.hero_realm.text()}, 位置 ..." → 空字段也会拼出来
        # 新写法:_hs_parts.append + if _realm
        self.assertIn("_hs_parts", self.src,
            "BUG-079:没用 _hs_parts 条件拼接")
        self.assertIn("if _realm:", self.src,
            "BUG-079:hero_realm 没做空检查")


class TestDualAIRouting(unittest.TestCase):
    """v2.21.4 新功能:双 AI 分工"""

    @classmethod
    def setUpClass(cls):
        cls.src = NOVEL_AI.read_text(encoding="utf-8")
        cls.gen_src = GENCTRL.read_text(encoding="utf-8")
        cls.consts_src = CONSTS.read_text(encoding="utf-8")
        cls.profiles_src = PROFILES.read_text(encoding="utf-8")

    def test_qwen_in_ai_urls(self):
        """AI_URLS 必须包含 Qwen"""
        self.assertIn('"Qwen"', self.consts_src, "AI_URLS 缺 Qwen 入口")
        self.assertIn("chat.qwen.ai", self.consts_src, "Qwen URL 不对")

    def test_qwen_in_site_profiles(self):
        """SITE_PROFILES 必须包含 Qwen 站点档案"""
        self.assertIn('"chat.qwen.ai"', self.profiles_src,
            "SITE_PROFILES 缺 chat.qwen.ai 档案")

    def test_secondary_targets_defined(self):
        """SECONDARY_AI_TARGETS 必须定义,且含关键数据任务"""
        self.assertIn("SECONDARY_AI_TARGETS", self.src,
            "缺 SECONDARY_AI_TARGETS 常量")
        # 关键数据任务必须在内
        for t in ("canon_extract", "character_extract", "chapter_summary",
                  "critique_rhythm", "critique_character"):
            self.assertIn(f'"{t}"', self.src,
                f"SECONDARY_AI_TARGETS 漏关键任务 {t}")

    def test_creative_targets_not_in_secondary(self):
        """创作类 target 不应路由到副 AI"""
        # 从 SECONDARY_AI_TARGETS 提取实际内容
        m = re.search(r"SECONDARY_AI_TARGETS\s*=\s*\{(.*?)\}",
                      self.src, re.S)
        self.assertIsNotNone(m)
        sec_block = m.group(1)
        # 这些是写作类,不该在副 AI 列表里
        for creative in ("chapter", "golden_three", "optimize",
                          "outline_full", "intro", "inspiration",
                          "ab_compare", "alt_version"):
            self.assertNotIn(f'"{creative}"', sec_block,
                f"创作类 {creative} 不该路由到副 AI(会丢叙事能力)")

    def test_ui_has_aux_controls(self):
        """生成控制 Tab 必须有副 AI 控件"""
        for ctrl in ("chk_aux_ai", "aux_site_combo", "aux_url_input",
                     "aux_status_label"):
            self.assertIn(f"self.{ctrl}", self.gen_src,
                f"生成控制缺副 AI 控件 {ctrl}")

    def test_send_to_ai_has_routing(self):
        """_send_to_ai 必须有副 AI 路由逻辑"""
        m = re.search(r"def _send_to_ai\(.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m)
        block = m.group(0)
        self.assertIn("chk_aux_ai", block, "_send_to_ai 没检查副 AI 开关")
        self.assertIn("SECONDARY_AI_TARGETS", block,
            "_send_to_ai 没检查 target 是否属于副 AI 类")
        self.assertIn("aux_url_input", block, "_send_to_ai 没用副 AI URL")


class TestRelationGraphLayering(unittest.TestCase):
    """关系图节点分层 + 度数 size — 真正解决排版问题"""

    @classmethod
    def setUpClass(cls):
        cls.src = RELGRAPH.read_text(encoding="utf-8")

    def test_role_layer_function_exists(self):
        """_role_layer 函数必须存在"""
        self.assertIn("def _role_layer(", self.src)

    def test_layer_mapping(self):
        """主角/女主→0,反派/导师→1,配角→2,路人→3"""
        sys.path.insert(0, str(HERE))
        from relation_graph import _role_layer
        self.assertEqual(_role_layer("主角"), 0)
        self.assertEqual(_role_layer("女主"), 0)
        self.assertEqual(_role_layer("男主"), 0)
        self.assertEqual(_role_layer("反派"), 1)
        self.assertEqual(_role_layer("导师"), 1)
        self.assertEqual(_role_layer("配角"), 2)
        self.assertEqual(_role_layer("路人甲"), 3)
        self.assertEqual(_role_layer(""), 3)  # 空也算路人

    def test_node_size_by_degree(self):
        """节点 size 应按 degree 动态计算"""
        sys.path.insert(0, str(HERE))
        from relation_graph import build_graph_data
        # A 是主角,有 5 个不同朋友;C 只跟 A 一个人有关
        chars = [["A", "主角", "", "", "", "", "", "1"],
                 ["B", "配角", "", "", "", "", "", "1"],
                 ["C", "配角", "", "", "", "", "", "1"],
                 ["D", "配角", "", "", "", "", "", "1"],
                 ["E", "配角", "", "", "", "", "", "1"],
                 ["F", "配角", "", "", "", "", "", "1"]]
        rels = [["A", "朋友", "B", ""],
                ["A", "朋友", "C", ""],
                ["A", "朋友", "D", ""],
                ["A", "朋友", "E", ""],
                ["A", "朋友", "F", ""]]
        g = build_graph_data(chars, rels)
        a_node = next(n for n in g["nodes"] if n["id"] == "A")  # degree=5
        c_node = next(n for n in g["nodes"] if n["id"] == "C")  # degree=1
        self.assertGreater(a_node["size"], c_node["size"],
            f"主角(度数5)size={a_node['size']} 应大于配角(度数1)size={c_node['size']}")

    def test_barneshut_physics(self):
        """物理引擎应换到 barnesHut + 强斥力 + avoidOverlap"""
        self.assertIn("barnesHut", self.src, "没换到 barnesHut")
        self.assertIn("avoidOverlap", self.src, "缺 avoidOverlap")
        # 斥力应至少 -1000(原 -45 弱爆)
        m = re.search(r"gravitationalConstant:\s*(-\d+)", self.src)
        self.assertIsNotNone(m, "找不到 gravitationalConstant")
        self.assertLess(int(m.group(1)), -1000,
            f"斥力太弱:{m.group(1)}")

    def test_initial_positions_function(self):
        """JS 端必须有 assignInitialPositions 函数(分圈布局)"""
        self.assertIn("assignInitialPositions", self.src,
            "缺 assignInitialPositions 分圈布局函数")

    def test_toolbar_buttons(self):
        """必须有 3 个工具按钮"""
        for btn in ("relayout", "spread", "cluster"):
            self.assertIn(f"function {btn}(", self.src,
                f"缺 JS 工具按钮 {btn}")


class TestAppVersionBumped(unittest.TestCase):
    """v2.21.4 必须升版本号"""

    def test_version(self):
        src = NOVEL_AI.read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*"v(\d+)\.(\d+)\.(\d+)"', src)
        self.assertIsNotNone(m)
        ver = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        self.assertGreaterEqual(ver, (2, 21, 4),
            f"BUG-079/080 + 双 AI 在 v2.21.4 修,当前 v{m.group(1)}.{m.group(2)}.{m.group(3)}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
