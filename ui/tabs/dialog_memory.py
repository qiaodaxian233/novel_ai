# -*- coding: utf-8 -*-
"""ui/tabs/dialog_memory.py - 对话记忆 Tab(203 行)

v2.03 P4 拆分:从 novel_ai.py 第 2466-2668 行整体搬运,内容零修改。
"""
import re

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)


class DialogMemory(QWidget):
    """
    对话记忆 - 让 AI 写到第 100 章也不忘第 1 章
    
    工作原理:
    1. 每章生成完毕,自动让 AI 用 80 字概括本章
    2. 在生成下一章前,把前面所有章节的摘要 + 最近 N 章正文尾段 + 角色档案 + 长期伏笔
       打包成「对话记忆」注入到提示词
    3. 这样 AI 看到的上下文虽然不是完整 N 章原文,但有足够的脉络保持人设/伏笔一致
    """
    
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        inner = QWidget(); scroll.setWidget(inner)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        title = QLabel("对话记忆 — 让 AI 写到第 100 章也不忘第 1 章")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #2a6dcd;")
        layout.addWidget(title)

        intro = QLabel(
            "每章生成完毕会自动总结成 80 字摘要,在生成下一章前自动把"
            "「角色档案 + 章节摘要 + 最近 N 章详细回顾 + 长期伏笔」打包注入到提示词,"
            "保证 AI 持续掌握剧情脉络,人设不崩、伏笔不断。"
        )
        intro.setStyleSheet("color: #6d7c95; padding: 4px;")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ---- 一键生成对话记忆(主入口) ----
        full_box = QGroupBox("一键生成对话记忆 (推荐)")
        full_box.setStyleSheet(
            "QGroupBox { border: 2px solid #cc3333; } "
            "QGroupBox::title { color: #cc3333; }")
        full_lay = QVBoxLayout(full_box)
        full_tip = QLabel(
            "基于当前所有章节,串行调用 AI 生成:补齐所有缺失摘要 → 提取角色档案 → 提取长期记忆。\n"
            "适合首次使用、导入旧项目、或长篇小说里手动整理记忆。"
        )
        full_tip.setWordWrap(True)
        full_tip.setStyleSheet("color: #6d7c95; padding: 4px;")
        full_lay.addWidget(full_tip)

        full_btn_row = QHBoxLayout()
        self.btn_gen_full_memory = QPushButton("✨ 一键生成完整对话记忆")
        self.btn_gen_full_memory.setStyleSheet(
            "QPushButton { background-color: #cc3333; color: white; "
            "padding: 12px 20px; font-size: 14px; font-weight: bold; }} "
            "QPushButton:hover { background-color: #e04444; }")
        self.btn_stop_full_memory = QPushButton("⏹ 中止")
        self.btn_stop_full_memory.setMaximumWidth(80)
        self.btn_stop_full_memory.setEnabled(False)
        full_btn_row.addWidget(self.btn_gen_full_memory, 1)
        full_btn_row.addWidget(self.btn_stop_full_memory)
        full_lay.addLayout(full_btn_row)

        self.full_memory_progress = QLabel("就绪")
        self.full_memory_progress.setStyleSheet(
            "padding: 6px 10px; background: #f4f4f4; border-radius: 3px; color: #7a7a7a;")
        full_lay.addWidget(self.full_memory_progress)
        layout.addWidget(full_box)

        # ---- 自动记忆策略 ----
        st_box = QGroupBox("自动记忆策略")
        sl = QVBoxLayout(st_box)
        self.auto_summarize = QCheckBox(
            "每章生成后自动总结(批量生成时,会在每章正文之后自动跑一次摘要任务)")
        self.auto_summarize.setChecked(True)
        self.auto_inject = QCheckBox(
            "发送下一章时自动把记忆块注入到提示词")
        self.auto_inject.setChecked(True)
        for cb in (self.auto_summarize, self.auto_inject):
            sl.addWidget(cb)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("最近"))
        self.recent_n = QSpinBox(); self.recent_n.setRange(0, 20); self.recent_n.setValue(3)
        srow.addWidget(self.recent_n)
        srow.addWidget(QLabel("章用详细尾段(每段约 300 字),其它章节只用摘要"))
        srow.addStretch()
        srow.addWidget(QLabel("每条摘要长度上限:"))
        self.summary_len = QSpinBox(); self.summary_len.setRange(30, 300); self.summary_len.setValue(80)
        srow.addWidget(self.summary_len); srow.addWidget(QLabel("字"))
        sl.addLayout(srow)
        layout.addWidget(st_box)

        # ---- 角色档案 ----
        cbox = QGroupBox("角色档案 (人设/状态/关系)")
        cl = QVBoxLayout(cbox)
        cbtns = QHBoxLayout()
        self.btn_extract_chars = QPushButton("✨ 从最新章节提取/更新角色")
        self.btn_clear_chars = QPushButton("清空")
        cbtns.addWidget(self.btn_extract_chars); cbtns.addWidget(self.btn_clear_chars)
        cbtns.addStretch()
        cl.addLayout(cbtns)
        self.chars_edit = QPlainTextEdit()
        self.chars_edit.setMinimumHeight(140)
        self.chars_edit.setPlaceholderText(
            "格式:【角色名】外貌:xxx;性格:xxx;当前状态:xxx;关系:xxx\n"
            "可手动编辑,也可点上面按钮 AI 自动提取。")
        cl.addWidget(self.chars_edit)
        layout.addWidget(cbox)

        # ---- 章节摘要 ----
        sbox = QGroupBox("章节摘要 (每章一行,自动随章节生成)")
        sml = QVBoxLayout(sbox)
        sbtns = QHBoxLayout()
        self.btn_gen_all_sum = QPushButton("✨ 一键补齐所有缺失摘要")
        self.btn_gen_cur_sum = QPushButton("只生成选中章节的摘要")
        self.btn_clear_sum = QPushButton("清空")
        for b in (self.btn_gen_all_sum, self.btn_gen_cur_sum, self.btn_clear_sum):
            sbtns.addWidget(b)
        sbtns.addStretch()
        sml.addLayout(sbtns)
        self.summaries_edit = QPlainTextEdit()
        self.summaries_edit.setMinimumHeight(180)
        self.summaries_edit.setPlaceholderText(
            "每章一行,格式:第N章 标题 :: 摘要内容\n"
            "AI 写完一章会自动追加一行。也可手动编辑。")
        self.summaries_edit.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 12px;")
        sml.addWidget(self.summaries_edit)
        layout.addWidget(sbox)

        # ---- 长期记忆 ----
        ltbox = QGroupBox("长期记忆 (伏笔 / 重要物品 / 关键关系 / 隐藏设定)")
        ll = QVBoxLayout(ltbox)
        ltbtns = QHBoxLayout()
        self.btn_extract_lt = QPushButton("✨ AI 从最新章节提取长期记忆")
        self.btn_clear_lt = QPushButton("清空")
        ltbtns.addWidget(self.btn_extract_lt); ltbtns.addWidget(self.btn_clear_lt)
        ltbtns.addStretch()
        ll.addLayout(ltbtns)
        self.long_term_edit = QPlainTextEdit()
        self.long_term_edit.setMinimumHeight(120)
        self.long_term_edit.setPlaceholderText(
            "每行一条。例如:\n"
            "- 玉佩:祖母传给男主(第3章)\n"
            "- 女主白天/夜晚双重身份未被识破(全文核心)\n"
            "- 苏小雨暗恋男主(第5章)")
        ll.addWidget(self.long_term_edit)
        layout.addWidget(ltbox)

        # ---- 注入预览 ----
        pvbox = QGroupBox("注入预览 (实际会随提示词一起发给 AI)")
        pvl = QVBoxLayout(pvbox)
        prow = QHBoxLayout()
        self.btn_preview = QPushButton("🔍 刷新预览")
        prow.addWidget(self.btn_preview); prow.addStretch()
        info = QLabel("(下次生成章节时会自动注入这段内容)")
        info.setStyleSheet("color: #6d7c95;")
        prow.addWidget(info)
        pvl.addLayout(prow)
        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setStyleSheet(
            "background: #f8f8f8; font-family: 'Microsoft YaHei'; font-size: 12px; color: #333;")
        self.preview_edit.setMinimumHeight(180)
        pvl.addWidget(self.preview_edit)
        layout.addWidget(pvbox)

        layout.addStretch()

    def update_progress(self, text, level="info"):
        """更新一键生成的进度显示"""
        colors = {
            "info": ("#666", "#f4f4f4"),
            "running": ("white", "#1a4480"),
            "success": ("white", "#28a745"),
            "error": ("white", "#cc3333"),
        }
        fg, bg = colors.get(level, colors["info"])
        self.full_memory_progress.setText(text)
        self.full_memory_progress.setStyleSheet(
            f"padding: 6px 10px; background: {bg}; color: {fg}; "
            f"border-radius: 3px; font-weight: bold;")

    def parse_summaries(self):
        """从 summaries_edit 解析出 {ch_num: summary} 字典"""
        result = {}
        for line in self.summaries_edit.toPlainText().splitlines():
            line = line.strip()
            if not line: continue
            # 匹配:第N章 任意标题 :: 摘要 ,或 第N章 :: 摘要
            m = re.match(r'^第\s*(\d+)\s*章[^:]*?::\s*(.+)$', line)
            if m:
                result[int(m.group(1))] = m.group(2).strip()
        return result

    def append_summary(self, ch_num, ch_title, summary):
        """追加或更新一章的摘要"""
        sums = self.parse_summaries()
        sums[ch_num] = summary.strip().replace('\n', ' ')
        # 重排序
        lines = []
        for n in sorted(sums.keys()):
            lines.append(f"第{n}章 :: {sums[n]}")
        self.summaries_edit.setPlainText("\n".join(lines))
