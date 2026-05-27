# -*- coding: utf-8 -*-
"""ui/emotion_curve.py - 情绪曲线可视化

显示全书各章的情绪走势（紧张/爽感/虐心/温馨），
一眼看出节奏是否平淡、高潮是否密集。
v2.13.8 新增。
"""
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPainterPath, QLinearGradient
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QToolTip, QSizePolicy,
)


# 四个情绪维度的颜色
DIMS = [
    ("tension",      "紧张", QColor("#e74c3c")),  # 红
    ("satisfaction",  "爽感", QColor("#f39c12")),  # 橙
    ("emotion",      "虐/感动", QColor("#3498db")),  # 蓝
    ("warmth",       "温馨", QColor("#2ecc71")),  # 绿
]


class EmotionChartWidget(QWidget):
    """纯 QPainter 绘制的情绪折线图"""

    PADDING_LEFT = 40
    PADDING_RIGHT = 20
    PADDING_TOP = 30
    PADDING_BOTTOM = 40
    POINT_RADIUS = 4
    MIN_COL_WIDTH = 50

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # list of (ch_num, {tension:7, satisfaction:8, ...})
        self._show = {d[0]: True for d in DIMS}
        self.setMouseTracking(True)
        self._hover_idx = -1
        self.setMinimumHeight(260)

    def set_data(self, data):
        """data: list of (ch_num, scores_dict)"""
        self._data = data or []
        w = max(400, self.PADDING_LEFT + self.PADDING_RIGHT +
                len(self._data) * self.MIN_COL_WIDTH)
        self.setMinimumWidth(w)
        self.update()

    def toggle_dim(self, key, visible):
        self._show[key] = visible
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        pl, pr, pt, pb = self.PADDING_LEFT, self.PADDING_RIGHT, self.PADDING_TOP, self.PADDING_BOTTOM
        chart_w = w - pl - pr
        chart_h = h - pt - pb
        n = len(self._data)
        if n < 1 or chart_w < 10 or chart_h < 10:
            return

        # 背景网格
        painter.setPen(QPen(QColor("#e0e0e0"), 1, Qt.DashLine))
        font_small = QFont("Microsoft YaHei", 8)
        painter.setFont(font_small)
        for score in range(0, 11, 2):
            y = pt + chart_h - (score / 10.0) * chart_h
            painter.drawLine(int(pl), int(y), int(w - pr), int(y))
            painter.setPen(QPen(QColor("#999"), 1))
            painter.drawText(2, int(y + 4), str(score))
            painter.setPen(QPen(QColor("#e0e0e0"), 1, Qt.DashLine))

        # X 轴标签
        painter.setPen(QPen(QColor("#666"), 1))
        step = max(1, n // 20)  # 最多显示20个标签
        for i, (ch_num, _) in enumerate(self._data):
            x = pl + (i / max(n - 1, 1)) * chart_w
            if i % step == 0 or i == n - 1:
                painter.drawText(int(x - 10), int(h - 5), f"第{ch_num}章")

        # 画每条曲线
        for dim_key, dim_name, dim_color in DIMS:
            if not self._show.get(dim_key, True):
                continue

            points = []
            for i, (ch_num, scores) in enumerate(self._data):
                val = scores.get(dim_key, 0)
                x = pl + (i / max(n - 1, 1)) * chart_w
                y = pt + chart_h - (val / 10.0) * chart_h
                points.append(QPointF(x, y))

            if not points:
                continue

            # 线条
            pen = QPen(dim_color, 2.5)
            painter.setPen(pen)
            path = QPainterPath()
            path.moveTo(points[0])
            for p in points[1:]:
                path.lineTo(p)
            painter.drawPath(path)

            # 填充渐变
            fill_path = QPainterPath(path)
            fill_path.lineTo(points[-1].x(), pt + chart_h)
            fill_path.lineTo(points[0].x(), pt + chart_h)
            fill_path.closeSubpath()
            grad = QLinearGradient(0, pt, 0, pt + chart_h)
            fill_color = QColor(dim_color)
            fill_color.setAlpha(30)
            grad.setColorAt(0, fill_color)
            fill_color.setAlpha(5)
            grad.setColorAt(1, fill_color)
            painter.setPen(Qt.NoPen)
            painter.setBrush(grad)
            painter.drawPath(fill_path)

            # 数据点
            painter.setPen(QPen(dim_color, 1))
            painter.setBrush(dim_color)
            for p in points:
                painter.drawEllipse(p, self.POINT_RADIUS, self.POINT_RADIUS)

        # hover 高亮列
        if 0 <= self._hover_idx < n:
            x = pl + (self._hover_idx / max(n - 1, 1)) * chart_w
            painter.setPen(QPen(QColor("#aaa"), 1, Qt.DashLine))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(int(x), int(pt), int(x), int(pt + chart_h))

        painter.end()

    def mouseMoveEvent(self, event):
        if not self._data:
            return
        n = len(self._data)
        pl, pr, pt = self.PADDING_LEFT, self.PADDING_RIGHT, self.PADDING_TOP
        chart_w = self.width() - pl - pr
        if chart_w <= 0 or n <= 1:
            return
        rel_x = event.x() - pl
        idx = round(rel_x / chart_w * (n - 1))
        idx = max(0, min(n - 1, idx))
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
            ch_num, scores = self._data[idx]
            summary = scores.get("summary", "")
            lines = [f"第{ch_num}章"]
            for dk, dn, dc in DIMS:
                v = scores.get(dk, 0)
                bar = "█" * v + "░" * (10 - v)
                lines.append(f"  {dn}: {bar} {v}")
            if summary:
                lines.append(f"  主调: {summary}")
            QToolTip.showText(event.globalPos(), "\n".join(lines), self)


class EmotionCurvePanel(QWidget):
    """完整的情绪曲线面板（含图例开关 + 滚动区）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 标题行
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("📊 情绪曲线(鼠标悬停查看详情)"))
        title_row.addStretch()

        # 图例开关
        self._toggles = {}
        for dk, dn, dc in DIMS:
            btn = QPushButton(f"● {dn}")
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setStyleSheet(
                f"QPushButton {{ color:{dc.name()}; border:1px solid {dc.name()};"
                f"padding:2px 8px; border-radius:3px; font-size:11px; }} "
                f"QPushButton:checked {{ background:{dc.name()}; color:white; }}")
            btn.toggled.connect(lambda checked, k=dk: self.chart.toggle_dim(k, checked))
            title_row.addWidget(btn)
            self._toggles[dk] = btn

        layout.addLayout(title_row)

        # 滚动区内的图表
        self.chart = EmotionChartWidget()
        scroll = QScrollArea()
        scroll.setWidget(self.chart)
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(280)
        layout.addWidget(scroll)

        # 底部说明
        hint = QLabel("💡 连续3章紧张度<4=节奏太平 | 连续3章爽感<3=缺爽点 | 四线全低=需要加戏")
        hint.setStyleSheet("color:#8fa3c4; font-size:11px;")
        layout.addWidget(hint)

    def load_from_chapters(self, chapters):
        """从章节数据加载情绪分数"""
        data = []
        for i, ch in enumerate(chapters):
            scores = ch.get("emotion_scores")
            if scores:
                ch_num = i + 1
                data.append((ch_num, scores))
        self.chart.set_data(data)

        # 检查连续平淡
        if len(data) >= 3:
            for i in range(len(data) - 2):
                t3 = [data[i+j][1].get("tension", 5) for j in range(3)]
                if all(v < 4 for v in t3):
                    ch_start = data[i][0]
                    return f"⚠ 第{ch_start}-{ch_start+2}章连续紧张度不足,建议加冲突"
        return None
