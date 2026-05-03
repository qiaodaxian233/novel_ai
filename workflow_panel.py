# -*- coding: utf-8 -*-
"""
workflow_panel.py — 章节生成「工作流」可视化面板
=================================================

挂在 NovelAI MainWindow 上作为独立 Tab,做三件事:

  1. 可视化     — 把 workflow_pipeline.py 的 PRE_WRITE → POST_WRITE → POST_CHAIN
                  完整流水线用纵向卡片渲染出来
  2. 集中开关   — 每个 Step 一个 checkbox,聚合散落在 Canon / 对话记忆 / 生成控制
                  里的开关,改这里 = 改对应 Tab 的开关(双向同步)
  3. 运行时高亮 — 章节生成时正在跑的 Step 高亮闪烁,直观看到流水线进度

不修改 workflow_pipeline.py 和其它 Tab,纯加法。

接入(novel_ai.py 加 5 行,见 INTEGRATION 节末尾):

    # 顶部 import
    try:
        from workflow_panel import WorkflowPanel
        WORKFLOW_PANEL_AVAILABLE = True
    except ImportError:
        WORKFLOW_PANEL_AVAILABLE = False

    # MainWindow Tab 注册段
    if WORKFLOW_PANEL_AVAILABLE and self.workflow:
        self.tab_workflow = WorkflowPanel(mw=self)
        # 在「生成控制」前插入,作为流水线的"总开关面板"
    else:
        self.tab_workflow = None

依赖:
  - workflow_pipeline.py 已存在且 mw.workflow 已实例化
  - mw.tab_memory / mw.tab_canon / mw.tab_generation 已实例化
"""
from __future__ import annotations

from typing import Optional, Callable, Dict, List, Tuple
import functools

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPropertyAnimation, pyqtProperty
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QGroupBox,
    QPushButton, QFrame, QSizePolicy, QScrollArea, QGraphicsOpacityEffect,
)

# --------- 样式常量(对齐 lifespan_loops_panel / CanonGuard) ---------
TITLE_STYLE  = "font-size: 16px; font-weight: bold; color: #1a4480;"
INTRO_STYLE  = "color: #555; padding: 6px 0;"
HINT_STYLE   = "color: #888; font-size: 11px;"
PRIMARY_BTN  = (
    "background:#1a73e8;color:white;padding:6px 14px;"
    "font-weight:bold;border-radius:3px;"
)
GHOST_BTN    = (
    "background:#fff;color:#1a73e8;padding:5px 12px;"
    "border:1px solid #1a73e8;border-radius:3px;"
)
PHASE_COLOR  = {
    "pre_write":  "#1a73e8",   # 蓝
    "post_write": "#e37400",   # 琥珀
    "post_chain": "#137333",   # 绿
}
PHASE_LABEL  = {
    "pre_write":  "写前注入",
    "post_write": "写后校验",
    "post_chain": "通过后链",
}
COST_BADGE_INSTANT = ("即时",   "#5f6368", "#f1f3f4")
COST_BADGE_AI      = ("+1 AI", "#b3261e", "#fce8e6")
COST_BADGE_AUTO    = ("自动",   "#137333", "#e6f4ea")
COST_BADGE_RUNTIME = ("运行时", "#888",    "#f1f3f4")


# ============================================================
# Step 绑定表 — 把每个 workflow Step 映射到 UI 与上游控件
# ============================================================
#
# 每条记录:
#   step_name        — 与 PipelineStep.name 一致
#   phase            — pre_write / post_write / post_chain
#   display_name     — 卡片标题
#   description      — 卡片副标题
#   cost             — instant / ai / auto / runtime(决定 badge 颜色)
#   upstream         — Callable(mw) → QCheckBox / None
#                      返回上游控件;None 表示无对应控件(运行时/自动)
#
def _STEP_BINDINGS() -> List[Dict]:
    return [
        # ---- PRE_WRITE ----
        dict(
            step_name="memory_inject", phase="pre_write",
            display_name="对话记忆注入",
            description="从「对话记忆」Tab 拉取角色档案 + 摘要 + 长期记忆,拼到 prompt 末尾",
            cost="instant",
            upstream=lambda mw: getattr(mw.tab_memory, "auto_inject", None),
        ),
        dict(
            step_name="canon_inject", phase="pre_write",
            display_name="Canon 约束注入",
            description="把 Canon 设定块作为硬约束写进 prompt(违反此章作废)",
            cost="instant",
            upstream=lambda mw: getattr(mw.tab_canon, "chk_inject", None),
        ),
        dict(
            step_name="critique_rules_inject", phase="pre_write",
            display_name="审稿清单注入",
            description="启用了节奏/人设打分时,自动注入「写完自查清单」让 AI 心里有数",
            cost="auto",
            upstream=lambda mw: None,   # 由下游开关派生,非独立控件
        ),
        # ---- POST_WRITE ----
        dict(
            step_name="word_count", phase="post_write",
            display_name="字数检查",
            description="差距 > 阈值 → 加入 issues,触发死磕重写",
            cost="instant",
            upstream=lambda mw: getattr(mw.tab_generation, "chk_crit_words", None),
        ),
        dict(
            step_name="hook_check", phase="post_write",
            display_name="章末钩子",
            description="正则启发式:章末必须有问号/省略号/转折词,否则视为追更动力不足",
            cost="instant",
            upstream=lambda mw: getattr(mw.tab_generation, "chk_crit_hook", None),
        ),
        dict(
            step_name="canon_audit", phase="post_write",
            display_name="Canon 稽核",
            description="AI 对比 Canon 表,high 严重度违反 → 死磕重写",
            cost="ai",
            upstream=lambda mw: getattr(mw.tab_generation, "chk_crit_canon", None),
        ),
        dict(
            step_name="rhythm_score", phase="post_write",
            display_name="节奏打分",
            description="AI 打分 1-10,< 7 触发重写。开了之后每章 +1 次 AI 调用",
            cost="ai",
            upstream=lambda mw: getattr(mw.tab_generation, "chk_crit_rhythm", None),
        ),
        dict(
            step_name="character_score", phase="post_write",
            display_name="人设打分",
            description="AI 对比角色档案打分 1-10,< 7 触发重写。开了之后每章 +1 次 AI 调用",
            cost="ai",
            upstream=lambda mw: getattr(mw.tab_generation, "chk_crit_char", None),
        ),
        # ---- POST_CHAIN ----
        dict(
            step_name="canon_extract", phase="post_chain",
            display_name="Canon 自动抽取",
            description="章节通过后,从正文里抓新设定追加到 Canon 表",
            cost="ai",
            upstream=lambda mw: getattr(mw.tab_canon, "chk_extract", None),
        ),
        dict(
            step_name="summary", phase="post_chain",
            display_name="生成章节摘要",
            description="AI 写一段 200 字摘要,供后续注入下下章 prompt",
            cost="ai",
            upstream=lambda mw: getattr(mw.tab_memory, "auto_summarize", None),
        ),
        dict(
            step_name="next_chapter", phase="post_chain",
            display_name="链式下一章",
            description="批量模式下自动开始下一章,由 _batch_remaining 与 _batch_paused 控制",
            cost="runtime",
            upstream=lambda mw: None,
        ),
    ]


# ============================================================
# StepCard — 单个 Step 的卡片
# ============================================================

class StepCard(QFrame):
    """单个 Step 的可视化卡片(含 checkbox + 描述 + 运行时高亮)"""

    toggled = pyqtSignal(str, bool)  # (step_name, new_state)

    def __init__(self, binding: dict, mw, parent=None):
        super().__init__(parent)
        self.binding = binding
        self.mw = mw
        self.step_name = binding["step_name"]
        self.phase = binding["phase"]
        self._upstream_cb: Optional[QCheckBox] = None
        self._is_running = False

        self.setObjectName("StepCard")
        self._apply_default_style()

        self._build_ui()
        self._sync_from_upstream()

    # -------- 样式 --------
    def _apply_default_style(self):
        self.setStyleSheet("""
            #StepCard {
                background: #fff;
                border: 1px solid #e0e0e0;
                border-radius: 5px;
            }
            #StepCard[running="true"] {
                background: #fffbe6;
                border: 2px solid #f9ab00;
            }
            #StepCard[disabled_state="true"] {
                background: #fafafa;
            }
        """)
        self.setProperty("running", False)
        self.setProperty("disabled_state", False)

    def _refresh_style(self):
        # 强制重绘以让 property selector 生效
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    # -------- 构建 --------
    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(10)

        # 左侧:运行指示灯
        self.led = QLabel("●")
        self.led.setFixedWidth(14)
        self.led.setStyleSheet("color:#dadce0;font-size:14px;")
        self.led.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.led)

        # 中部:复选框 + 名称 + 描述
        mid = QVBoxLayout()
        mid.setSpacing(2)

        head = QHBoxLayout()
        head.setSpacing(8)

        self.checkbox = QCheckBox(self.binding["display_name"])
        self.checkbox.setStyleSheet("font-weight:bold;font-size:13px;")
        self.checkbox.toggled.connect(self._on_checkbox_toggled)
        head.addWidget(self.checkbox)

        # phase 徽章
        phase_label = self._make_badge(
            PHASE_LABEL[self.phase],
            "white", PHASE_COLOR[self.phase])
        head.addWidget(phase_label)

        # cost 徽章
        cost = self.binding["cost"]
        if cost == "instant":
            text, fg, bg = COST_BADGE_INSTANT
        elif cost == "ai":
            text, fg, bg = COST_BADGE_AI
        elif cost == "auto":
            text, fg, bg = COST_BADGE_AUTO
        else:
            text, fg, bg = COST_BADGE_RUNTIME
        cost_label = self._make_badge(text, fg, bg)
        head.addWidget(cost_label)

        head.addStretch()
        mid.addLayout(head)

        desc = QLabel(self.binding["description"])
        desc.setStyleSheet("color:#5f6368;font-size:11px;")
        desc.setWordWrap(True)
        mid.addWidget(desc)

        outer.addLayout(mid, 1)

        # 右侧:状态文字
        self.status_text = QLabel("待命")
        self.status_text.setStyleSheet("color:#9aa0a6;font-size:11px;")
        self.status_text.setFixedWidth(60)
        self.status_text.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        outer.addWidget(self.status_text)

        # 处理无上游的特殊 Step
        if self.binding["cost"] in ("auto", "runtime"):
            self.checkbox.setEnabled(False)
            tip = {
                "auto":    "开关由「节奏打分」/「人设打分」自动决定",
                "runtime": "由批量生成的运行时状态决定,无开关",
            }[self.binding["cost"]]
            self.checkbox.setToolTip(tip)

    @staticmethod
    def _make_badge(text: str, fg: str, bg: str) -> QLabel:
        b = QLabel(text)
        b.setStyleSheet(
            f"color:{fg};background:{bg};"
            f"padding:1px 6px;border-radius:8px;font-size:10px;"
            f"font-weight:bold;"
        )
        return b

    # -------- 与上游 checkbox 双向同步 --------
    def bind_upstream(self):
        """初始化时调一次。subsequent reads 在 _sync_from_upstream() 里。"""
        if self.mw is None:
            return
        try:
            upstream = self.binding["upstream"](self.mw)
        except Exception:
            upstream = None
        if isinstance(upstream, QCheckBox):
            self._upstream_cb = upstream
            # 上游变化 → 同步到这边(避免循环)
            upstream.toggled.connect(self._on_upstream_toggled)

    def _sync_from_upstream(self):
        """从上游 checkbox 拉一次状态"""
        if self.mw is None:
            return
        if self._upstream_cb is None:
            # 派生 / 运行时步骤 — 从 workflow 实例读 enabled
            try:
                step = self._find_step()
                if step is not None:
                    self.checkbox.blockSignals(True)
                    self.checkbox.setChecked(bool(step.enabled))
                    self.checkbox.blockSignals(False)
            except Exception:
                pass
        else:
            self.checkbox.blockSignals(True)
            self.checkbox.setChecked(self._upstream_cb.isChecked())
            self.checkbox.blockSignals(False)
        self._update_disabled_appearance()

    def _on_upstream_toggled(self, checked: bool):
        if self.checkbox.isChecked() == checked:
            return
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(checked)
        self.checkbox.blockSignals(False)
        self._update_disabled_appearance()

    def _on_checkbox_toggled(self, checked: bool):
        # 反向写到上游
        if self._upstream_cb is not None:
            if self._upstream_cb.isChecked() != checked:
                # blockSignals 避免回环
                self._upstream_cb.blockSignals(True)
                self._upstream_cb.setChecked(checked)
                self._upstream_cb.blockSignals(False)
                # 但还得手动通知上游的 toggled,因为 blockSignals 会阻止
                # 上游 Tab 内部依赖的连接(如有)
                self._upstream_cb.toggled.emit(checked)
        self._update_disabled_appearance()
        self.toggled.emit(self.step_name, checked)

    def _update_disabled_appearance(self):
        on = self.checkbox.isChecked()
        self.setProperty("disabled_state", not on)
        self._refresh_style()

    def _find_step(self):
        """从 mw.workflow._registry 里找到对应 Step 实例"""
        wf = getattr(self.mw, "workflow", None)
        if wf is None:
            return None
        reg = getattr(wf, "_registry", None)
        if reg is None:
            return None
        for steps in reg._steps.values():
            for _prio, step in steps:
                if step.name == self.step_name:
                    return step
        return None

    # -------- 运行时高亮 --------
    def set_running(self, running: bool):
        self._is_running = running
        self.setProperty("running", running)
        self._refresh_style()
        if running:
            self.led.setStyleSheet("color:#f9ab00;font-size:14px;")
            self.status_text.setText("正在跑")
            self.status_text.setStyleSheet("color:#f9ab00;font-size:11px;font-weight:bold;")
        else:
            self.led.setStyleSheet("color:#dadce0;font-size:14px;")
            self.status_text.setText("待命")
            self.status_text.setStyleSheet("color:#9aa0a6;font-size:11px;")

    def mark_done(self, success: bool = True):
        """跑完一次后短暂显示完成状态"""
        self._is_running = False
        self.setProperty("running", False)
        self._refresh_style()
        if success:
            self.led.setStyleSheet("color:#34a853;font-size:14px;")
            self.status_text.setText("✓ 完成")
            self.status_text.setStyleSheet("color:#34a853;font-size:11px;")
        else:
            self.led.setStyleSheet("color:#ea4335;font-size:14px;")
            self.status_text.setText("✗ 失败")
            self.status_text.setStyleSheet("color:#ea4335;font-size:11px;")
        # 1.5 秒后回到待命
        QTimer.singleShot(1500, self._reset_indicator)

    def _reset_indicator(self):
        if self._is_running:
            return
        self.led.setStyleSheet("color:#dadce0;font-size:14px;")
        self.status_text.setText("待命")
        self.status_text.setStyleSheet("color:#9aa0a6;font-size:11px;")


# ============================================================
# WorkflowPanel — 主面板
# ============================================================

class WorkflowPanel(QWidget):
    """章节生成工作流可视化 + 集中开关 + 运行时高亮"""

    request_log = pyqtSignal(str, str)

    def __init__(self, mw=None, parent=None):
        super().__init__(parent)
        self.mw = mw
        self._cards: Dict[str, StepCard] = {}
        self._hooks_installed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # ---- 标题 + 简介 ----
        title = QLabel("章节生成工作流")
        title.setStyleSheet(TITLE_STYLE)
        layout.addWidget(title)

        intro = QLabel(
            "把整条章节生成流水线摆出来一目了然。每个步骤一张卡片,"
            "可单独开关 — 改这里 = 改对应 Tab 的开关(双向同步)。\n"
            "    · 蓝色 = 写章节前 / 琥珀 = 写完校验 / 绿色 = 通过后链式\n"
            "    · 「即时」= 不耗 token / 「+1 AI」= 每章多调一次大模型\n"
            "    · 章节生成时,正在跑的步骤会高亮闪烁。"
        )
        intro.setStyleSheet(INTRO_STYLE)
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ---- 顶部状态条 ----
        status_row = QHBoxLayout()
        self.lbl_pipeline_state = QLabel("● 流水线就绪")
        self.lbl_pipeline_state.setStyleSheet("color:#137333;font-weight:bold;")
        status_row.addWidget(self.lbl_pipeline_state)
        status_row.addStretch()

        btn_refresh = QPushButton("🔄 同步状态")
        btn_refresh.setStyleSheet(GHOST_BTN)
        btn_refresh.setToolTip("从其他 Tab 重新拉一次开关状态(如果被外部改了)")
        btn_refresh.clicked.connect(self.sync_from_workflow)
        status_row.addWidget(btn_refresh)

        btn_all_on = QPushButton("全开")
        btn_all_on.setStyleSheet(GHOST_BTN)
        btn_all_on.clicked.connect(lambda: self._bulk_set(True))
        status_row.addWidget(btn_all_on)

        btn_all_off = QPushButton("全关")
        btn_all_off.setStyleSheet(GHOST_BTN)
        btn_all_off.clicked.connect(lambda: self._bulk_set(False))
        status_row.addWidget(btn_all_off)

        layout.addLayout(status_row)

        # ---- 滚动容器(避免小屏 step 太多挤压) ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 8, 0)
        inner_layout.setSpacing(8)

        # ---- 三个阶段 GroupBox ----
        bindings = _STEP_BINDINGS()
        for phase in ("pre_write", "post_write", "post_chain"):
            phase_bindings = [b for b in bindings if b["phase"] == phase]
            if not phase_bindings:
                continue
            box = self._build_phase_box(phase, phase_bindings)
            inner_layout.addWidget(box)

        # ---- 阶段间箭头 ----
        # (插入箭头并非严格必要,GroupBox 的视觉分隔已足够,这里加个轻量提示)
        inner_layout.addStretch()

        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

        # ---- 底部图例 ----
        legend = QLabel(
            "图例:●待命  ●正在跑  ●完成  ●失败 · "
            "卡片背景灰=该步骤被关闭,黄=正在执行"
        )
        legend.setStyleSheet(HINT_STYLE)
        layout.addWidget(legend)

        # 装运行时钩子
        if self.mw is not None and getattr(self.mw, "workflow", None):
            self.install_runtime_hooks()

    # -------- 构建一个阶段 GroupBox --------
    def _build_phase_box(self, phase: str, bindings: List[dict]) -> QGroupBox:
        title = {
            "pre_write":  "Phase 1 — 写章节前(注入 prompt)",
            "post_write": "Phase 2 — 写完后校验(失败 → 死磕重写)",
            "post_chain": "Phase 3 — 通过后链式(摘要 / Canon 抽取 / 下一章)",
        }[phase]
        box = QGroupBox(title)
        color = PHASE_COLOR[phase]
        box.setStyleSheet(f"""
            QGroupBox {{
                font-weight: bold;
                font-size: 13px;
                color: {color};
                border: 1.5px solid {color};
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background: white;
            }}
        """)
        v = QVBoxLayout(box)
        v.setContentsMargins(10, 16, 10, 10)
        v.setSpacing(6)
        for b in bindings:
            card = StepCard(b, self.mw)
            card.bind_upstream()
            self._cards[b["step_name"]] = card
            v.addWidget(card)
        return v.parent() if False else box   # 保持类型 QGroupBox

    # -------- 公共方法 --------
    def sync_from_workflow(self):
        """从上游/workflow 重新拉一次所有 Step 的状态"""
        for card in self._cards.values():
            card._sync_from_upstream()
        self.request_log.emit("工作流状态已同步", "info")

    def _bulk_set(self, on: bool):
        n_changed = 0
        for card in self._cards.values():
            if card.binding["cost"] in ("auto", "runtime"):
                continue
            if card.checkbox.isEnabled() and card.checkbox.isChecked() != on:
                card.checkbox.setChecked(on)
                n_changed += 1
        action = "开启" if on else "关闭"
        self.request_log.emit(f"批量{action} {n_changed} 个步骤", "info")

    # -------- 运行时钩子(monkey-patch step.run) --------
    def install_runtime_hooks(self):
        """
        给 mw.workflow 里所有 Step 的 run() 套一层 wrapper,
        在 run 前后切换对应 StepCard 的高亮状态。

        不修改 workflow_pipeline.py 本身,纯 monkey-patch。
        """
        if self._hooks_installed:
            return
        wf = self.mw.workflow
        reg = getattr(wf, "_registry", None)
        if reg is None:
            return

        for steps in reg._steps.values():
            for _prio, step in steps:
                self._wrap_step_run(step)
        self._hooks_installed = True

    def _wrap_step_run(self, step):
        original_run = step.run
        step_name = step.name
        panel = self

        @functools.wraps(original_run)
        def wrapped(ctx, done):
            # 进入 → 高亮
            QTimer.singleShot(0, lambda: panel._on_step_started(step_name))

            def _done_wrapped():
                # 退出 → 标记完成
                # 失败判断:POST_WRITE 步骤可能往 ctx.issues 里塞东西,但
                # 单步是否"成功"很难界定。这里只做最朴素的 ✓,失败由
                # 整批 retry 流程通过 lbl_pipeline_state 表达
                QTimer.singleShot(0, lambda: panel._on_step_finished(step_name, True))
                done()

            try:
                original_run(ctx, _done_wrapped)
            except Exception as e:
                QTimer.singleShot(0, lambda: panel._on_step_finished(step_name, False))
                raise

        step.run = wrapped

    def _on_step_started(self, step_name: str):
        card = self._cards.get(step_name)
        if card:
            card.set_running(True)
        self.lbl_pipeline_state.setText(f"● 正在执行:{step_name}")
        self.lbl_pipeline_state.setStyleSheet("color:#f9ab00;font-weight:bold;")

    def _on_step_finished(self, step_name: str, success: bool):
        card = self._cards.get(step_name)
        if card:
            card.mark_done(success)
        # 整体状态短暂回到就绪(下一个 step 起会再覆盖)
        QTimer.singleShot(200, self._maybe_reset_pipeline_state)

    def _maybe_reset_pipeline_state(self):
        # 没有任何卡片在 running → 回到就绪
        if not any(c._is_running for c in self._cards.values()):
            self.lbl_pipeline_state.setText("● 流水线就绪")
            self.lbl_pipeline_state.setStyleSheet("color:#137333;font-weight:bold;")

    # -------- 持久化(暂时无独立配置,所有状态都在上游 Tab 里) --------
    def serialize_for_save(self) -> dict:
        """所有开关状态都属于上游 Tab,这里返回空。保留接口以备扩展。"""
        return {}

    def load_from_dict(self, d: dict):
        """同上,无需加载"""
        pass


# ============================================================
# 公开 API
# ============================================================

__all__ = ["WorkflowPanel", "StepCard"]
