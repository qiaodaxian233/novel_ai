# -*- coding: utf-8 -*-
"""
import_continuation.py · v1.51 — 导入外部小说续写功能
─────────────────────────────────────────────────
功能:
  1. 用户选 TXT(外部写的前 N 章)
  2. 拆章预览
  3. 用户选导入模式:
     A) 导入到当前项目(章节追加)
     B) 新建项目(独立的书)
  4. (可选)勾选「让 AI 提取设定」 → 浏览器在线检查 → 提示开启
  5. 走 AI 提取角色/世界观/伏笔/大纲 → 填充对应字段

这个文件只装 UI dialog + prompt 构造,
真正的 AI 调用由 MainWindow 调度(走现有 worker)。
"""
from __future__ import annotations
import json
from pathlib import Path
from dataclasses import dataclass

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QCheckBox, QListWidget, QListWidgetItem,
    QGroupBox, QPlainTextEdit, QSpinBox, QMessageBox,
)

import book_splitter


# ───────────── 主对话框 ─────────────
class ImportContinuationDialog(QDialog):
    """导入外部小说续写 — 主对话框
    返回 (mode, with_ai_extract, max_extract_chapters) 给 MainWindow 处理
    mode: "current" / "new"
    """

    def __init__(self, parent=None, book_meta=None):
        super().__init__(parent)
        self.book_meta = book_meta   # BookMeta from book_splitter
        self.setWindowTitle("📥 导入外部小说续写")
        self.resize(800, 650)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        # ── 顶部:小说信息 ──
        info_box = QGroupBox("📖 待导入的小说")
        info_lay = QVBoxLayout(info_box)
        if self.book_meta:
            info_lay.addWidget(QLabel(
                f"<b>📕 书名:</b> {self.book_meta.title}<br>"
                f"<b>📊 章节:</b> {self.book_meta.chapter_count} 章 / "
                f"<b>共字数:</b> {self.book_meta.total_words:,} 字 / "
                f"<b>编码:</b> {self.book_meta.encoding}"))
        else:
            info_lay.addWidget(QLabel("(未加载)"))
        # 章节预览
        self.list_preview = QListWidget()
        self.list_preview.setMaximumHeight(180)
        if self.book_meta:
            for ch in self.book_meta.chapters[:20]:   # 预览前 20 章
                self.list_preview.addItem(
                    f"  第 {ch.index} 章:{ch.title_clean or '(无标题)'} "
                    f"({ch.word_count:,} 字)")
            if self.book_meta.chapter_count > 20:
                it = QListWidgetItem(
                    f"  ... 还有 {self.book_meta.chapter_count - 20} 章未显示")
                it.setForeground(Qt.gray)
                self.list_preview.addItem(it)
        info_lay.addWidget(self.list_preview)
        lay.addWidget(info_box)

        # ── 模式选择 ──
        mode_box = QGroupBox("📥 导入模式")
        mode_lay = QVBoxLayout(mode_box)
        self.btn_group_mode = QButtonGroup()

        self.rb_current = QRadioButton(
            "导入到当前项目 — 追加到现有章节后面(继续同一本书)")
        self.rb_current.setStyleSheet("padding:6px;")
        self.btn_group_mode.addButton(self.rb_current, 0)
        mode_lay.addWidget(self.rb_current)
        hint_current = QLabel(
            "  ℹ 复用当前项目的设定/大纲/6 库,把这本 TXT 当作\"后续章节\"加进来。\n"
            "    适合:你之前在别处写过几章,想接着用盘古往下写。")
        hint_current.setStyleSheet("color:#888; font-size:11px; padding-left:24px;")
        mode_lay.addWidget(hint_current)

        self.rb_new = QRadioButton(
            "新建独立项目 — 这本 TXT 当作完整的书,从最后一章接着写")
        self.rb_new.setStyleSheet("padding:6px;")
        self.btn_group_mode.addButton(self.rb_new, 1)
        mode_lay.addWidget(self.rb_new)
        hint_new = QLabel(
            "  ℹ 新建一个项目文件夹,把这本 TXT 当作前 N 章。\n"
            "    适合:导入别人写到一半的书,你接着续写;或者自己之前的旧稿重启。")
        hint_new.setStyleSheet("color:#888; font-size:11px; padding-left:24px;")
        mode_lay.addWidget(hint_new)

        self.rb_current.setChecked(True)
        lay.addWidget(mode_box)

        # ── AI 提取设定(可选) ──
        ai_box = QGroupBox("🤖 AI 自动提取设定(可选,默认关)")
        ai_lay = QVBoxLayout(ai_box)
        self.chk_ai_extract = QCheckBox(
            "✨ 让 AI 读前 N 章,自动提取:角色档案 / 世界观 / 伏笔 / 后续大纲")
        self.chk_ai_extract.setStyleSheet("font-weight:bold;")
        self.chk_ai_extract.setChecked(False)
        ai_lay.addWidget(self.chk_ai_extract)

        ai_hint = QLabel(
            "  ⚠ 需要浏览器在线(就是你写章节时用的那个 AI 浏览器)\n"
            "  ⚠ 费 token,大约 1-3 万字章节 = 1 次 AI 调用费用\n"
            "  ✓ 提取结果会填到对应字段:角色 → 6 库 / 世界观 → 故事大纲 / 伏笔 → Canon")
        ai_hint.setStyleSheet("color:#888; font-size:11px; padding-left:24px;")
        ai_lay.addWidget(ai_hint)

        # AI 提取的章节数(避免太长爆 token)
        n_row = QHBoxLayout()
        n_row.addWidget(QLabel("  让 AI 读前"))
        self.sp_extract_n = QSpinBox()
        self.sp_extract_n.setRange(1, 30)
        self.sp_extract_n.setValue(min(5, self.book_meta.chapter_count if self.book_meta else 5))
        self.sp_extract_n.setSuffix(" 章")
        self.sp_extract_n.setEnabled(False)
        n_row.addWidget(self.sp_extract_n)
        n_row.addWidget(QLabel("提取设定(建议 5-10 章,避免太长)"))
        n_row.addStretch()
        ai_lay.addLayout(n_row)
        self.chk_ai_extract.toggled.connect(self.sp_extract_n.setEnabled)

        # 高级选项:标记导入来源
        adv_row = QHBoxLayout()
        self.chk_mark_imported = QCheckBox(
            "🏷 (高级)在章节元数据里标记「从 XXX.txt 导入」")
        self.chk_mark_imported.setChecked(False)
        self.chk_mark_imported.setStyleSheet("color:#888;")
        self.chk_mark_imported.setToolTip(
            "默认不开。开启后导入的章节会在 _meta.json 里带 is_imported=true,\n"
            "便于以后区分来源(自己写的 vs 导入的)。")
        adv_row.addWidget(self.chk_mark_imported)
        adv_row.addStretch()
        ai_lay.addLayout(adv_row)

        lay.addWidget(ai_box)

        # ── 底部按钮 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setMinimumWidth(100)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_ok = QPushButton("✓ 开始导入")
        self.btn_ok.setMinimumWidth(140)
        self.btn_ok.setStyleSheet(
            "QPushButton { background:#27ae60; color:white; padding:8px 16px; "
            "border-radius:3px; font-weight:bold; }} "
            "QPushButton:hover { background:#1e8449; }")
        self.btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_ok)
        lay.addLayout(btn_row)

    def get_result(self) -> dict:
        """对话框确认后,获取用户选择"""
        return {
            "mode": "new" if self.rb_new.isChecked() else "current",
            "ai_extract": self.chk_ai_extract.isChecked(),
            "extract_n": self.sp_extract_n.value(),
            "mark_imported": self.chk_mark_imported.isChecked(),
        }


# ───────────── AI 提取设定 prompt ─────────────
def build_extract_prompt(chapters: list, max_chars: int = 30000) -> str:
    """构造 AI 提取设定的 prompt
    chapters: list of BookChapter
    返回 prompt 字符串
    """
    # 截取前 N 章内容,总字数控制在 max_chars
    pieces = []
    total = 0
    for ch in chapters:
        body = ch.content
        if total + len(body) > max_chars:
            body = body[: max(0, max_chars - total)]
            pieces.append(f"=== 第 {ch.index} 章 {ch.title_clean} ===\n{body}")
            break
        pieces.append(f"=== 第 {ch.index} 章 {ch.title_clean} ===\n{body}")
        total += len(body)

    combined = "\n\n".join(pieces)

    return f"""你是网文设定提取师。下面是一本小说的前 {len(pieces)} 章正文,请提取出完整的设定信息,
便于在另一个写作工具里【续写】这本书。

【你要做的】
1. **角色档案**:识别所有出场角色(主角/配角/反派),对每个角色填:
   - name 姓名
   - role 定位(如「主角」「师父」「反派老大」)
   - appearance 外貌(身高/容貌/标志)
   - personality 性格
   - ability 能力/职业
   - state 当前状态(本章末尾时所处的境地)

2. **世界观**:概括核心设定(种族/职业体系/地理/历史)— 300 字以内

3. **故事种子**:核心冲突 1 句话(主角想干啥 / 阻碍是啥)

4. **已埋伏笔**:列出明显未解的伏笔(每条:chapter 章号 + content 内容)

5. **后续大纲建议**:根据现有节奏,推测后续 5-10 章可能的走向(每章一两句话)

【输出格式】严格 JSON,**只输出 JSON,无 markdown 包裹,无解释**:
```json
{{
  "characters": [
    {{
      "name": "林远",
      "role": "主角",
      "appearance": "黑发剑眉,常穿青布袍",
      "personality": "内敛、算计",
      "ability": "咒血者(以血为媒)",
      "state": "天剑宗外门杂役"
    }}
  ],
  "worldview": "三千大世界,九重天阙...",
  "seed": "废柴主角偷学咒血者心法,赌一把改命",
  "foreshadows": [
    {{"chapter": 1, "content": "玉佩来自哪里?"}},
    {{"chapter": 3, "content": "藏经阁三层有人想见林远 — 谁?"}}
  ],
  "outline_next": [
    "第 N+1 章:跟赵乾进天剑宗,初见藏经阁三层的人",
    "第 N+2 章:..."
  ]
}}
```

【已有正文】(共 {total:,} 字)
{combined}
"""


def parse_extract_response(text: str) -> dict | None:
    """解析 AI 返回的 JSON,失败返回 None"""
    import re
    if not text:
        return None
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None
