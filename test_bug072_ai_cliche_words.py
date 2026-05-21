"""
v1.98 BUG-072 测试 —— "AI 文风套话"禁用词类别
新增 6 词 + 【AI 文风防线】铁律段(无 L 编号,避开对话 13 法)

测试策略(参考 bug071):
- 静态断言:6 词同时在 docstring 类别清单、_FORBIDDEN_WORDS list、防线段示例
- 引擎层:PanguEngine._FORBIDDEN_WORDS 总数 = 123,6 词全在
- install_pangu 端到端:wrap 后的 PROMPTS 含【AI 文风防线】段(PANGU_CORE_RULES 注入路径打通)
- 路线纪律:v1.92-v1.97 既有功能保留
- APP_VERSION = "v1.98"
"""
from __future__ import annotations
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent
PANGU_SYS = ROOT / "pangu_system.py"
NOVEL_AI = ROOT / "novel_ai.py"
PANGU_SRC = PANGU_SYS.read_text(encoding="utf-8")
NOVEL_SRC = NOVEL_AI.read_text(encoding="utf-8")

NEW_WORDS = ["不禁", "不由自主", "油然而生", "涌上心头", "若有所思", "意味深长"]


# ───── 静态断言 — docstring + list + 防线段 三处同步 ─────────────


class TestSixWordsInDocstring(unittest.TestCase):
    """6 词必须在 pangu_system.py docstring 的禁用词类别清单"""

    def test_total_count_bumped_117_to_123(self):
        self.assertIn("共 123 个", PANGU_SRC)
        self.assertNotIn("共 117 个", PANGU_SRC)

    def test_new_category_exists(self):
        self.assertIn("AI 文风套话:", PANGU_SRC)

    def test_each_new_word_in_docstring_category(self):
        """6 词每个都出现在 'AI 文风套话:' 行后"""
        idx = PANGU_SRC.find("AI 文风套话:")
        self.assertGreater(idx, 0)
        line_end = PANGU_SRC.find("\n", idx)
        category_line = PANGU_SRC[idx:line_end]
        for w in NEW_WORDS:
            self.assertIn(w, category_line, f"'{w}' 不在 docstring 类别行")


class TestSixWordsInForbiddenList(unittest.TestCase):
    """6 词必须在 _FORBIDDEN_WORDS Python list"""

    def test_each_new_word_in_list_source(self):
        for w in NEW_WORDS:
            self.assertIn(f'"{w}"', PANGU_SRC, f"'{w}' 不在 _FORBIDDEN_WORDS list")

    def test_new_category_comment_exists(self):
        self.assertIn("AI 文风套话(v1.98 新增)", PANGU_SRC)


class TestAiCheFangXianSection(unittest.TestCase):
    """【AI 文风防线】段必须存在,在句式铁律后、对话铁律前,且不带 L 编号"""

    def test_section_header_exists(self):
        self.assertIn("【AI 文风防线】", PANGU_SRC)

    def test_section_no_l_numbering(self):
        """防线段不能带 L 编号(避开对话 13 法 L1-L13)"""
        # 用 \n【 切分段首(memory 纪律:不要用 find("【",start),段内引用会切短)
        sections = PANGU_SRC.split("\n【")
        fang_xian = [s for s in sections if s.startswith("AI 文风防线】")]
        self.assertEqual(len(fang_xian), 1, "找不到【AI 文风防线】段或重复")
        body = fang_xian[0]
        l_marks = re.findall(r"^\s*L\d+\s", body, re.MULTILINE)
        self.assertEqual(l_marks, [], f"防线段不应带 L 编号,发现:{l_marks}")

    def test_section_between_juchi_and_duihua(self):
        idx_juchi = PANGU_SRC.find("【句式铁律】")
        idx_fangxian = PANGU_SRC.find("【AI 文风防线】")
        idx_duihua = PANGU_SRC.find("【对话铁律")
        self.assertGreater(idx_juchi, 0)
        self.assertGreater(idx_fangxian, idx_juchi, "防线段应在句式铁律之后")
        self.assertGreater(idx_duihua, idx_fangxian, "防线段应在对话铁律之前")

    def test_section_mentions_all_new_words(self):
        """防线段示例文字必须覆盖 6 词"""
        sections = PANGU_SRC.split("\n【")
        body = [s for s in sections if s.startswith("AI 文风防线】")][0]
        for w in NEW_WORDS:
            self.assertIn(w, body, f"'{w}' 不在防线段示例")


# ───── 引擎层直测 ─────────────────────────────────────────────


class TestPanguEngineForbiddenWords(unittest.TestCase):
    """PanguEngine._FORBIDDEN_WORDS 总数 = 123,6 词全在"""

    def test_total_count_123(self):
        from pangu_system import PanguEngine
        self.assertEqual(
            len(PanguEngine._FORBIDDEN_WORDS), 123,
            f"_FORBIDDEN_WORDS 总数应 123,实际 {len(PanguEngine._FORBIDDEN_WORDS)}")

    def test_six_new_words_in_list(self):
        from pangu_system import PanguEngine
        for w in NEW_WORDS:
            self.assertIn(w, PanguEngine._FORBIDDEN_WORDS, f"'{w}' 不在 list")


# ───── install_pangu 端到端 ──────────────────────────────────


class TestInstallPanguWrapsCorrectly(unittest.TestCase):
    """install_pangu wrap 后 PROMPTS 字典内容应含【AI 文风防线】段"""

    def test_wrap_chapter_prompt_contains_fang_xian(self):
        from pangu_patch import install_pangu, DEFAULT_SCENARIO_MAP

        chapter_key = next(
            (k for k, sc in DEFAULT_SCENARIO_MAP.items() if sc == "chapter"), None)
        self.assertIsNotNone(chapter_key, "DEFAULT_SCENARIO_MAP 没 chapter scenario")

        fake_globals = {"PROMPTS": {chapter_key: "原始章节提示词"}}
        ok = install_pangu(fake_globals)
        self.assertTrue(ok, "install_pangu 应返回 True")

        wrapped = fake_globals["PROMPTS"][chapter_key]
        self.assertIn("【AI 文风防线】", wrapped, "wrap 后没有【AI 文风防线】段")
        for w in NEW_WORDS:
            self.assertIn(w, wrapped, f"wrap 后没有 '{w}'")
        self.assertIn("原始章节提示词", wrapped, "原文丢失")


# ───── APP_VERSION + 路线纪律 ──────────────────────────────────


class TestAppVersion(unittest.TestCase):
    def test_app_version_v198(self):
        # v2.00 P1 模块化拆分时把硬钉改为解析后 ≥ 比较
        # (BUG-072 留下的 TODO 落地:升一次版本号不要再改一堆测试)
        import re
        m = re.search(r'APP_VERSION = "v(\d+)\.(\d+)"', NOVEL_SRC)
        self.assertIsNotNone(m, "novel_ai.py 必须定义 APP_VERSION")
        major, minor = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual((major, minor), (1, 98),
                                f'BUG-072 必须在 v1.98 之后修复(当前 v{major}.{minor:02d})')


class TestNoRegressionToEarlierVersions(unittest.TestCase):
    """v1.92-v1.97 既有功能保留 — 跟 bug071 同款纪律段"""

    def test_v192_chapter_lock_intact(self):
        self.assertIn("def _toggle_chapter_lock", NOVEL_SRC)

    def test_v193_charlib_intact(self):
        self.assertIn("_find_duplicate_names", NOVEL_SRC)

    def test_v194_button_color_intact(self):
        self.assertIn("#3a2a10", NOVEL_SRC)

    def test_v195_word_count_long_intact(self):
        self.assertNotIn("# v1.98: 删除 word_count_long", NOVEL_SRC)

    def test_v96_bug070_defense_intact(self):
        self.assertIn("BUG-070 防御", NOVEL_SRC)

    def test_v97_bug071_dict_intact(self):
        self.assertIn("self._pending_task_targets = {}", NOVEL_SRC)


class TestPanguExistingSectionsIntact(unittest.TestCase):
    """pangu_system.py 既有铁律段保留 — 防线段不破坏其他段"""

    def test_emotion_iron_law_intact(self):
        self.assertIn("【情绪铁律】", PANGU_SRC)

    def test_action_iron_law_intact(self):
        self.assertIn("【动作铁律】", PANGU_SRC)

    def test_environment_iron_law_intact(self):
        self.assertIn("【环境铁律】", PANGU_SRC)

    def test_juchi_iron_law_intact(self):
        self.assertIn("【句式铁律】", PANGU_SRC)

    def test_duihua_13_methods_intact(self):
        self.assertIn("【对话铁律 · 13 法】", PANGU_SRC)
        for i in range(1, 14):
            self.assertIn(f"L{i}", PANGU_SRC, f"对话 13 法 L{i} 缺失")


if __name__ == "__main__":
    unittest.main(verbosity=2)
