# -*- coding: utf-8 -*-
"""v1.94 BUG-068 回归测试 — 下一章选项按钮对比度修复

用户截图反馈 "下面按钮看不清" — 三个"下一章选项"按钮文字几乎不可见。
根因:行 2062-2065 setStyleSheet 漏写 `color` 字段,Qt 默认前景色
在某些主题下跟米色背景 #fff8ea 对比度极低。

修法:setStyleSheet 加 `color:#3a2a10`(深棕)+ hover `color:#000`。

这条测试用静态字符串断言防回归 — 任何人改样式如果再次漏写 color,
测试立刻挂。比 UI 截图肉眼检查可靠。

跟 v1.92 / v1.93 完全独立(只动 ChapterEditor._set_pangu_meta_display
里的一处 setStyleSheet)。
"""
import unittest
import ast
import os
import textwrap


HERE = os.path.dirname(os.path.abspath(__file__))
NOVEL_AI_PATH = os.path.join(HERE, "novel_ai.py")


def _load_all_sources():
    """v2.03 P4 后:Tab/UI/常量被外移到 ui/tabs/、ui/、core/ —
    静态字符串扫描需要把所有外迁文件 concat 起来当成"逻辑上的主程序"。
    """
    parts = [open(NOVEL_AI_PATH, encoding="utf-8").read()]
    for sub in ("ui/tabs", "ui", "core"):
        d = os.path.join(HERE, sub)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".py"):
                    parts.append(open(os.path.join(d, fn), encoding="utf-8").read())
    return "\n".join(parts)


class TestNextOptionButtonContrast(unittest.TestCase):
    """下一章选项按钮 setStyleSheet 必须显式指定 color"""

    @classmethod
    def setUpClass(cls):
        # v2.03 P4: 扩源扫描
        cls.src = _load_all_sources()

    def test_next_option_button_setstylesheet_has_explicit_color(self):
        """按钮样式必须显式 color 字段(根因:漏写就是 bug)"""
        # 找 _set_pangu_meta_display 方法
        idx = self.src.find('def _set_pangu_meta_display')
        self.assertGreater(idx, 0, "找不到 _set_pangu_meta_display 方法")
        chunk = self.src[idx:idx + 4000]
        # 找下一章选项按钮的样式定义段
        # 关键标志:背景色 #fff8ea(米色)+ QPushButton 选择器
        i_bg = chunk.find('#fff8ea')
        self.assertGreater(i_bg, 0, "找不到下一章选项按钮的米色背景")
        # 向前后扩 300 字符,看完整 setStyleSheet
        local = chunk[max(0, i_bg - 400):i_bg + 400]
        # 必须包含 color: 字段
        self.assertIn('color:', local,
                      "按钮 setStyleSheet 必须显式 color 字段 — "
                      "不然默认前景色配米色背景会看不清(BUG-068)")

    def test_normal_state_uses_dark_brown(self):
        """正常态文字色应该是深色,确保对比度足够"""
        idx = self.src.find('def _set_pangu_meta_display')
        chunk = self.src[idx:idx + 4000]
        # 寻找 BUG-068 区块,确认深棕色 #3a2a10 出现
        i_marker = chunk.find('BUG-068')
        self.assertGreater(i_marker, 0,
                           "BUG-068 修复注释必须在 _set_pangu_meta_display 里出现")
        # 深棕在米色背景上对比度 > 7:1(WCAG AAA)
        local = chunk[i_marker:i_marker + 800]
        self.assertIn('#3a2a10', local,
                      "正常态文字色应为 #3a2a10(深棕,配米色背景对比 >7:1)")

    def test_hover_state_uses_black(self):
        """hover 态文字色应该比正常态更深(纯黑),给出明确点击反馈"""
        idx = self.src.find('def _set_pangu_meta_display')
        chunk = self.src[idx:idx + 4000]
        i_hover = chunk.find('QPushButton:hover')
        self.assertGreater(i_hover, 0, "按钮必须有 hover 状态")
        # hover 段(从 :hover 到下一个 } )必须包含 color
        local = chunk[i_hover:i_hover + 200]
        i_close = local.find('}')
        self.assertGreater(i_close, 0)
        hover_block = local[:i_close]
        self.assertIn('color:', hover_block,
                      "hover 状态也必须显式 color,确保点击时反馈明显")

    def test_panel_labels_already_have_color(self):
        """元信息 panel 内其他 label(钩子/爽点/伏笔/tip)早就显式 color,
        说明 panel 设计语义本来就要求显式 color — 按钮漏写是真 bug,不是风格选择"""
        # 找 pangu_hook_label / pangu_cool_label / pangu_seeds_label 的样式
        for label_name in ["pangu_hook_label", "pangu_cool_label", "pangu_seeds_label"]:
            idx = self.src.find(f"self.{label_name}.setStyleSheet")
            self.assertGreater(idx, 0, f"{label_name} 必须有 setStyleSheet")
            local = self.src[idx:idx + 200]
            self.assertIn('color:', local,
                          f"{label_name} 的 stylesheet 应该有 color(panel 设计语义)")


class TestNoCollisionWithPreviousMilestones(unittest.TestCase):
    """v1.94 不动 v1.92(章节锁定)/ v1.93(角色字段)的代码"""

    @classmethod
    def setUpClass(cls):
        # v2.03 P4: 扩源扫描
        cls.src = _load_all_sources()

    def test_v192_chapter_lock_intact(self):
        """v1.92 章节锁定方法仍在"""
        self.assertIn("def _toggle_chapter_lock(self", self.src)
        self.assertIn("def _on_chapter_list_context_menu", self.src)
        self.assertIn('"summary": "", "locked": False', self.src)

    def test_v193_char_fields_intact(self):
        """v1.93 角色 last_ch + 同名检查仍在"""
        self.assertIn("def _find_duplicate_names(rows_data)", self.src)
        self.assertIn("def _on_check_duplicate_names", self.src)
        self.assertIn('"last_ch"', self.src)
        # tbl_chars 列数仍是 9
        self.assertIn('QTableWidget(0, 10)', self.src)


class TestAppVersionBumped(unittest.TestCase):
    """版本号校验 — APP_VERSION 必须 ≥ v1.94"""

    def test_app_version_at_least_v194(self):
        import re
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("APP_VERSION"):
                    m = re.search(r'v(\d+)\.(\d+)', line)
                    self.assertIsNotNone(m)
                    major, minor = int(m.group(1)), int(m.group(2))
                    self.assertGreaterEqual((major, minor), (1, 94),
                                            f"APP_VERSION 必须 ≥ v1.94,实际 v{major}.{minor}")
                    return
        self.fail("APP_VERSION not found")


if __name__ == "__main__":
    unittest.main(verbosity=2)
