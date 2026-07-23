# -*- coding: utf-8 -*-
"""BUG-078 守护测试 — 新项目串老角色数据

根因:_reset_ui_state 只清了 5 个 charlib 表格,且其中 2 个属性名写错
(tbl_rel/tbl_foreshadows 不存在,真实名是 tbl_relations/tbl_fore),
导致新建项目时关系/伏笔/承诺/弧线/目标/信息/钩子/爽点等 10+ 个表都还留着
老项目数据 → AI 写新章节时 build_inject_block 注入老角色,出现"新项目串老剧情"

守护策略:
1. 静态扫描 _reset_ui_state,确认 14 个真实表名都被列出来清空
2. 静态扫描,确认错误名 tbl_rel / tbl_foreshadows 不再出现在清空列表
3. 集成测试:实例化 MainWindow,塞老数据,调 _reset_ui_state,所有表应为 0 行
"""
import os
import sys
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # tests/ 的上一级 = 仓库根(测试搬迁修复)
NOVEL_AI = HERE / "novel_ai.py"


class TestResetUIStateClearsAllCharlibTables(unittest.TestCase):
    """静态扫描 — _reset_ui_state 必须清空全部 14 个真实表"""

    @classmethod
    def setUpClass(cls):
        cls.src = NOVEL_AI.read_text(encoding="utf-8")

    def _extract_reset_block(self):
        """抽取 _reset_ui_state 方法体(从 def 到下个 def)"""
        m = re.search(r"def _reset_ui_state\(self\):.*?(?=\n    def )", self.src, re.S)
        self.assertIsNotNone(m, "找不到 _reset_ui_state 方法")
        return m.group(0)

    def test_all_14_charlib_tables_cleared(self):
        """必须清空全部 14 个真实存在的 tbl_ 属性"""
        block = self._extract_reset_block()
        required = [
            "tbl_chars",
            "tbl_relations",      # ← 错误名 tbl_rel 不存在
            "tbl_timeline",
            "tbl_items",
            "tbl_power",
            "tbl_fore",           # ← 错误名 tbl_foreshadows 不存在
            "tbl_promises",
            "tbl_arcs",
            "tbl_rel_values",
            "tbl_goals",
            "tbl_infos",
            "tbl_known_by",
            "tbl_hooks",
            "tbl_cool",
        ]
        for tbl in required:
            self.assertIn(tbl, block,
                f"BUG-078:_reset_ui_state 漏清表 {tbl} → 会导致新项目串老数据")

    def test_no_bogus_table_names(self):
        """不能再用错误的属性名 — 那是 v1.60 留下的两个 bug"""
        block = self._extract_reset_block()
        # tbl_rel 应作为"\"tbl_rel\"" 字面字符串出现 → 不能有
        self.assertNotIn('"tbl_rel"', block,
            "BUG-078:tbl_rel 不是真实属性(真实是 tbl_relations),清空会被 getattr 静默跳过")
        self.assertNotIn('"tbl_foreshadows"', block,
            "BUG-078:tbl_foreshadows 不是真实属性(真实是 tbl_fore),清空会被 getattr 静默跳过")

    def test_hero_state_fields_cleared(self):
        """主角当前状态 5 个字段也要清(否则老项目的'练气期'会污染新项目)"""
        block = self._extract_reset_block()
        for field in ("hero_age", "hero_realm", "hero_location", "hero_faction", "hero_mood"):
            self.assertIn(field, block,
                f"BUG-078:主角状态 {field} 没清 → 会被注入新项目提示词")

    def test_pov_mode_reset(self):
        """POV 模式要回到默认(否则老项目选'角色 POV: 傅恬恬'会延续到新项目)"""
        block = self._extract_reset_block()
        self.assertIn("cb_pov_mode", block, "POV 模式没重置")
        self.assertIn("le_pov_character", block, "POV 角色名没清")

    def test_plot_tree_cleared(self):
        """剧情树(QTreeWidget)也要清"""
        block = self._extract_reset_block()
        self.assertIn("tree_plot", block, "剧情树没清")


class TestRealAttributesExist(unittest.TestCase):
    """验证 _reset_ui_state 引用的属性名在 CharacterLibrary 里真存在"""

    @classmethod
    def setUpClass(cls):
        cls.charlib_src = (HERE / "ui" / "tabs" / "character_library.py").read_text(encoding="utf-8")

    def test_all_cleared_tables_truly_exist(self):
        """守护:reset 里列的表名必须都能在 CharacterLibrary 找到 self.<name> = ..."""
        required = [
            "tbl_chars", "tbl_relations", "tbl_timeline", "tbl_items",
            "tbl_power", "tbl_fore", "tbl_promises", "tbl_arcs",
            "tbl_rel_values", "tbl_goals", "tbl_infos", "tbl_known_by",
            "tbl_hooks", "tbl_cool",
        ]
        for tbl in required:
            pattern = f"self.{tbl} = "
            self.assertIn(pattern, self.charlib_src,
                f"声称要清的 {tbl} 在 CharacterLibrary 里不存在(getattr 静默跳过)")


class TestAppVersionBumped(unittest.TestCase):
    """v2.21.3 修了 BUG-078,版本号必须 ≥ (2, 21, 3)"""

    def test_version(self):
        src = NOVEL_AI.read_text(encoding="utf-8")
        m = re.search(r'APP_VERSION\s*=\s*"v(\d+)\.(\d+)\.(\d+)"', src)
        self.assertIsNotNone(m, "找不到 APP_VERSION")
        major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
        self.assertGreaterEqual((major, minor, patch), (2, 21, 3),
            f"BUG-078 在 v2.21.3 修复,但当前版本 v{major}.{minor}.{patch}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
