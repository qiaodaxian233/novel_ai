#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端集成测试:模拟真实 novel_ai.py 的完整 PROMPTS 字典,
验证盘古 patch 不会破坏现有代码的任何 format() 调用。

这个测试照搬了 novel_ai.py 里 PROMPTS 字典的全部 11 个键和它们的 {占位符}。
跑法:python test_e2e_novel_ai_integration.py
"""

import unittest


# 完全复制 novel_ai.py(master 分支)里的 PROMPTS 字典,一字未改
NOVEL_AI_PROMPTS_REAL = {
    "creative_inspiration": (
        "请为一部小说生成一个创意灵感,要求:\n"
        "题材:{genre}\n"
        "禁止抄袭。\n"
        "请直接输出一句话创意(20字以内),不要有其他内容。"
        "如果是恐怖,悬疑题材不能有能反光的物体看见自己 "
        "如镜子 手机屏幕的题材,不能影子题材,不能有另一个自己的题材,"
        "请直接在对话中回答,不要生成文档\n"
        "请勿包含任何血腥、暴力、色情、侮辱女性词语等违规内容。"
    ),
    "outline_full": (
        "请作为资深小说主编,根据以下所有基础信息,一次性生成一份连贯、"
        "无冲突、高度自洽的完整小说大纲。各个设定的内容必须相互关联和呼应。"
        "如果是恐怖,悬疑题材不能有能反光的物体看见自己 如镜子 手机屏幕的题材,"
        "不能影子题材,不能有另一个自己的题材,请直接在对话中回答,不要生成文档。\n\n"
        "【特别指示】总章节数为 {chapter_count} 章。"
        "请严格根据这个数字来规划【章节大纲】部分。\n\n"
        "【基础设定】\n"
        "题材:{genre}\n"
        "创意灵感:{inspiration}"
        "{extra}"
    ),
    "outline_part": (
        "请根据以下信息单独生成【{part_name}】部分的内容:\n"
        "题材:{genre}\n"
        "创意灵感:{inspiration}\n\n"
        "要求:内容详尽、自洽,与其他部分能够呼应,但不要生成其他部分。\n"
        "{extra}"
    ),
    "chapter": (
        "请作为资深网文作者,生成《{title}》第 {chapter_num} 章的小说正文。\n\n"
        "【题材】{genre}\n"
        "【整体世界观/结构】\n{outline}\n\n"
        "【本章大纲】\n{chapter_outline}\n\n"
        "【写作要求】\n"
        "1. 本章字数不少于 {min_words} 字,目标 {target_words} 字\n"
        "2. 与上一章衔接顺畅,人物性格一致\n"
        "3. 对话生动、描写细腻、情节有节奏感\n"
        "4. 严禁血腥、暴力、色情、侮辱女性等违规内容\n"
        "5. 直接输出章节正文,不要任何解释、不要章节标题\n"
    ),
    "golden_three": (
        "请作为资深网文作者,为《{title}》生成黄金三章(第1-3章)。\n"
        "题材:{genre}\n"
        "创意灵感:{inspiration}\n\n"
        "参考章节大纲:\n{ch_outline}\n\n"
        "要求:\n"
        "1. 第一章必须有强钩子,3000字内出现核心冲突\n"
        "2. 第二章深化矛盾,引出主线\n"
        "3. 第三章一个小高潮+悬念结尾\n"
        "4. 每章不少于 3000 字\n"
        "5. 章节之间用 ===第N章 标题=== 分隔\n"
        "6. 严禁违规内容,不要生成文档,直接在对话中输出"
    ),
    "title": (
        "请为一部 {genre} 题材的小说取一个吸引人的书名。\n"
        "创意灵感:{inspiration}\n"
        "适合平台:{platform}\n"
        "要求:8-15字,有网感、有钩子。只输出书名本身,不要任何解释。"
    ),
    "intro": (
        "请根据以下小说大纲,撰写一段 200-300 字的作品简介,"
        "用于平台发布,要有吸引力、突出卖点、点出核心冲突。\n\n"
        "故事种子:{seed}\n世界观:{worldview}\n故事结构:{structure}\n\n"
        "直接输出简介正文,不要其他说明。"
    ),
    "ai_optimize": (
        "请帮我润色以下小说章节,要求:\n"
        "1. 保持原意和情节走向不变\n"
        "2. 让对话更生动,描写更细腻\n"
        "3. 修复语病、错别字、不通顺的地方\n"
        "4. 直接输出润色后的全文,不要任何说明文字\n\n"
        "原文:\n{content}"
    ),
    "chapter_summary": (
        "请用一段话精炼总结以下章节的核心剧情(关键事件、人物状态变化、本章埋下的伏笔),"
        "字数严格控制在 {max_len} 字以内,直接输出摘要本身,不要任何前缀、不要分行。\n\n"
        "章节标题:{title}\n章节正文:\n{content}"
    ),
    "character_extract": (
        "请从以下小说章节中提取所有出场人物,生成简洁的角色档案。\n"
        "{existing}"
        "章节正文:\n{content}"
    ),
    "long_term_extract": (
        "请从以下章节中提取需要长期记忆的关键信息,以避免后续章节出现矛盾。\n"
        "如本章没有需要长期记忆的内容,直接回答\"无\"。只输出条目本身,不要前后缀。\n\n"
        "章节正文:\n{content}"
    ),
}


class TestE2EOnRealPrompts(unittest.TestCase):
    """跑在真实 novel_ai.py 的 PROMPTS 字典上"""

    def setUp(self):
        # 深拷贝一份,避免相互影响
        self.g = {"PROMPTS": dict(NOVEL_AI_PROMPTS_REAL)}

    def _install(self, **kw):
        from pangu_patch import install_pangu
        return install_pangu(self.g, **kw)

    def test_install_on_real_prompts(self):
        ok = self._install()
        self.assertTrue(ok)

    def test_chapter_format_works_after_patch(self):
        """关键回归测试:novel_ai.py 调 PROMPTS["chapter"].format(...) 必须仍然 work"""
        self._install()
        # 这正是 novel_ai.py 实际调用方式(来自 start_generation / write_chapter 等)
        formatted = self.g["PROMPTS"]["chapter"].format(
            title="测试书",
            chapter_num=42,
            genre="都市/言情",
            outline="主角林晚晚穿越后...",
            chapter_outline="本章揭穿继母身世",
            min_words=2125,
            target_words=2500,
        )
        # 占位符全部 OK
        self.assertIn("测试书", formatted)
        self.assertIn("第 42 章", formatted)
        self.assertIn("2500", formatted)
        self.assertIn("林晚晚穿越后", formatted)
        # 盘古铁律也都注入了
        self.assertIn("禁用词", formatted)
        self.assertIn("感官铁律", formatted)
        self.assertIn("断章钩子", formatted)
        # 字长合理(应在 2~5K 之间)
        self.assertGreater(len(formatted), 1500)
        self.assertLess(len(formatted), 5000)

    def test_outline_full_format_works(self):
        self._install()
        formatted = self.g["PROMPTS"]["outline_full"].format(
            chapter_count=120,
            genre="都市/赘婿",
            inspiration="35 岁程序员被裁后获得倒计时系统",
            extra="\n【完整设定】平台:番茄,主角:程序员",
        )
        self.assertIn("120", formatted)
        self.assertIn("35 岁程序员", formatted)
        self.assertIn("【完整设定】", formatted)
        # 盘古的螺旋大纲规范也在
        self.assertIn("矛盾螺旋", formatted)
        self.assertIn("人物弧光三阶段", formatted)
        self.assertIn("P1", formatted)

    def test_outline_part_format_works(self):
        self._install()
        formatted = self.g["PROMPTS"]["outline_part"].format(
            part_name="世界观",
            genre="仙侠",
            inspiration="废柴弟子被逐",
            extra="",
        )
        self.assertIn("世界观", formatted)
        self.assertIn("仙侠", formatted)
        self.assertIn("废柴弟子被逐", formatted)
        self.assertIn("矛盾螺旋", formatted)

    def test_golden_three_format_works(self):
        self._install()
        formatted = self.g["PROMPTS"]["golden_three"].format(
            title="重生之最强赘婿",
            genre="都市/赘婿",
            inspiration="重生归来",
            ch_outline="第1章被退婚,第2章觉醒,第3章打脸前妻",
        )
        self.assertIn("重生之最强赘婿", formatted)
        # 盘古黄金三章公式
        self.assertIn("黄金三章公式", formatted)
        self.assertIn("绝境+羞辱", formatted)
        self.assertIn("金手指激活", formatted)

    def test_title_format_unchanged(self):
        self._install()
        formatted = self.g["PROMPTS"]["title"].format(
            genre="都市",
            inspiration="程序员被裁",
            platform="番茄小说",
        )
        # title 应保持原样(不被盘古污染)
        self.assertNotIn("盘古", formatted)
        self.assertNotIn("禁用词", formatted)
        self.assertIn("8-15字", formatted)

    def test_intro_format_unchanged(self):
        self._install()
        formatted = self.g["PROMPTS"]["intro"].format(
            seed="种子",
            worldview="世界观",
            structure="结构",
        )
        self.assertNotIn("盘古", formatted)
        self.assertIn("200-300", formatted)

    def test_ai_optimize_uses_sculptor(self):
        self._install()
        formatted = self.g["PROMPTS"]["ai_optimize"].format(content="原文内容")
        self.assertIn("雕刻家", formatted)
        self.assertIn("原文内容", formatted)
        self.assertIn("先删", formatted)  # 雕刻家法则

    def test_inspiration_format_works(self):
        self._install()
        formatted = self.g["PROMPTS"]["creative_inspiration"].format(genre="悬疑")
        self.assertIn("悬疑", formatted)
        self.assertIn("反光", formatted)  # 原 prompt 的禁止反光约束
        # 应有盘古的轻量前缀
        self.assertIn("直给情绪", formatted)
        # 不应该有完整铁律(那是 chapter 用的)
        self.assertNotIn("禁用词强制过滤", formatted)

    def test_chapter_summary_unchanged(self):
        self._install()
        formatted = self.g["PROMPTS"]["chapter_summary"].format(
            max_len=80,
            title="第一章",
            content="主角去了酒会",
        )
        # 工具型 prompt 应保持原样
        self.assertNotIn("盘古", formatted)
        self.assertIn("80", formatted)
        self.assertIn("主角去了酒会", formatted)

    def test_character_extract_unchanged(self):
        self._install()
        formatted = self.g["PROMPTS"]["character_extract"].format(
            existing="已有档案:林晚晚",
            content="本章新增...",
        )
        self.assertNotIn("盘古", formatted)
        self.assertIn("林晚晚", formatted)

    def test_long_term_extract_unchanged(self):
        self._install()
        formatted = self.g["PROMPTS"]["long_term_extract"].format(
            content="玉佩传给了主角",
        )
        self.assertNotIn("盘古", formatted)
        self.assertIn("玉佩", formatted)

    def test_all_keys_preserved(self):
        """patch 不能丢键"""
        original_keys = set(NOVEL_AI_PROMPTS_REAL.keys())
        self._install()
        patched_keys = set(self.g["PROMPTS"].keys())
        self.assertEqual(original_keys, patched_keys)

    def test_prompt_size_reasonable(self):
        """加上盘古铁律后,每个 prompt 不应膨胀到 token 不够用"""
        self._install()
        for key, tpl in self.g["PROMPTS"].items():
            size = len(tpl)
            # 即使带盘古头+尾,也应在 6KB 以内
            self.assertLess(size, 6000,
                            f"{key} too long: {size} chars (might exceed AI token budget)")

    def test_uninstall_restores_real_prompts(self):
        from pangu_patch import uninstall_pangu
        self._install()
        uninstall_pangu(self.g)
        for k, v in NOVEL_AI_PROMPTS_REAL.items():
            self.assertEqual(self.g["PROMPTS"][k], v,
                           f"key {k} not restored after uninstall")


class TestNoBypassedKeysAccidentallyPatched(unittest.TestCase):
    """确认 character_extract / long_term_extract / chapter_summary 等
    工具型 prompt 永远不会被盘古污染"""

    def test_explicit_bypass_list(self):
        g = {"PROMPTS": dict(NOVEL_AI_PROMPTS_REAL)}
        from pangu_patch import install_pangu
        install_pangu(g)

        # 这些键的内容必须与原版完全相等
        bypass_keys = ["title", "intro", "chapter_summary",
                       "character_extract", "long_term_extract"]
        for k in bypass_keys:
            self.assertEqual(g["PROMPTS"][k], NOVEL_AI_PROMPTS_REAL[k],
                           f"{k} should be bypassed but was modified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
