# -*- coding: utf-8 -*-
"""
LoginMirrorDialog — 扫码镜像登录对话框(v2.25.0)

目的:浏览器全程屏外隐藏,防止生成提示词露屏被抄。
登录需要人眼看二维码,所以把隐藏浏览器的画面以截图流方式镜像到本对话框:

  worker 每 1.5s 截一帧(mirror_shot 任务)→ mirror_frame 信号 → update_frame()
  用户在画面上点击 → 坐标换算回页面 CSS 坐标 → click_requested 信号
  → 主窗口 submit mirror_click 任务 → worker 用 CDP 派发真实点击

坐标换算要点:截图像素尺寸受系统 DPR 缩放影响,不能直接用;
worker 随帧附带 window.innerWidth/Height(CSS 坐标系),点击按比例映射。

线程纪律:本文件只碰 Qt,绝不碰 driver(核心架构规则 1:Worker 独占浏览器)。
"""
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout)


class _MirrorLabel(QLabel):
    """显示镜像帧并把点击换算回页面坐标的画布"""
    page_clicked = pyqtSignal(float, float)

    def __init__(self):
        super().__init__("等待第一帧画面…\n(浏览器保持隐藏)")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(480, 620)
        self.setStyleSheet("background:#1c1c1c; color:#888;")
        self._pix = None          # 原始帧
        self._css_w = 0           # 页面 CSS 宽高(点击坐标系)
        self._css_h = 0
        self._draw_rect = None    # 帧在 label 里的实际显示区域 (x, y, w, h)

    def set_frame(self, png_bytes, css_w, css_h):
        img = QImage.fromData(png_bytes)
        if img.isNull():
            return
        self._pix = QPixmap.fromImage(img)
        self._css_w = css_w or img.width()
        self._css_h = css_h or img.height()
        self._render()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._render()

    def _render(self):
        if not self._pix:
            return
        scaled = self._pix.scaled(
            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        # 居中显示;记录实际显示区域,点击换算要用
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        self._draw_rect = (x, y, scaled.width(), scaled.height())
        self.setPixmap(scaled)

    def map_to_page(self, pos: QPoint):
        """label 坐标 → 页面 CSS 坐标;点在帧外返回 None"""
        if not self._pix or not self._draw_rect:
            return None
        x0, y0, dw, dh = self._draw_rect
        rx, ry = pos.x() - x0, pos.y() - y0
        if not (0 <= rx < dw and 0 <= ry < dh):
            return None
        return (rx / dw * self._css_w, ry / dh * self._css_h)

    def mousePressEvent(self, e):
        pt = self.map_to_page(e.pos())
        if pt:
            self.page_clicked.emit(pt[0], pt[1])
        super().mousePressEvent(e)


class LoginMirrorDialog(QDialog):
    """扫码镜像登录:实时截图 + 点击转发,浏览器窗口全程不露面"""
    click_requested = pyqtSignal(float, float)   # 页面 CSS 坐标

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 扫码镜像登录(浏览器保持隐藏)")
        lay = QVBoxLayout(self)
        hint = QLabel(
            "下方是隐藏浏览器的实时镜像(约 1.5 秒刷新一帧)。\n"
            "直接在画面上点击可切换登录方式,手机扫画面里的二维码即可。\n"
            "登录成功后点「完成」,浏览器继续在后台隐身运行。")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.canvas = _MirrorLabel()
        self.canvas.page_clicked.connect(self.click_requested.emit)
        lay.addWidget(self.canvas, 1)
        brow = QHBoxLayout()
        brow.addStretch()
        btn_done = QPushButton("✅ 完成")
        btn_done.clicked.connect(self.accept)
        brow.addWidget(btn_done)
        lay.addLayout(brow)
        self.resize(560, 780)

    def update_frame(self, png_bytes, css_w, css_h):
        self.canvas.set_frame(png_bytes, css_w, css_h)
