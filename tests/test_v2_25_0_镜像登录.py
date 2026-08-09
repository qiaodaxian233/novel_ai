# -*- coding: utf-8 -*-
"""v2.25.0 扫码镜像登录 守护测试

核心风险点:
1. 坐标换算错 → 点击派发到错误位置,登录点不中 → 真跑 Qt offscreen 验证
2. worker/主窗口/按钮三处接线漏一处 → 功能整体失效 → 源码文本断言
"""
import io
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent


def _read(rel):
    return io.open(ROOT / rel, encoding="utf-8").read()


def _make_png(w, h):
    """生成 w×h 纯色 PNG bytes(模拟 worker 截图帧)"""
    from PyQt5.QtGui import QImage
    from PyQt5.QtCore import QBuffer, QByteArray
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(0xFFCC3333)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


_APP = None


def _app():
    """QApplication 必须持有引用,否则返回值被 GC 回收后
    创建任何 QWidget 都会直接 Aborted(实测踩坑)"""
    global _APP
    from PyQt5.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication([])
    return _APP


# ---------- 1. 坐标换算(真跑) ----------

def test_mirror_label_maps_click_to_css_coords():
    """截图帧 100×200(可能是 DPR 放大后的像素尺寸),页面 CSS 500×1000。
    label 480×620 居中显示 → 帧缩放为 310×620,左侧留白 85。
    点显示区中心 → 应映射为页面中心 (250, 500)。"""
    _app()
    from PyQt5.QtCore import QPoint
    from ui.login_mirror import _MirrorLabel
    lbl = _MirrorLabel()
    lbl.resize(480, 620)
    lbl.set_frame(_make_png(100, 200), 500, 1000)
    pt = lbl.map_to_page(QPoint(85 + 155, 310))
    assert pt is not None
    assert abs(pt[0] - 250) < 3, pt
    assert abs(pt[1] - 500) < 3, pt
    # 帧外(左侧留白区)点击必须被丢弃,不能派发出错误坐标
    assert lbl.map_to_page(QPoint(10, 310)) is None
    # 没有帧时点击也必须被丢弃
    lbl2 = _MirrorLabel()
    lbl2.resize(480, 620)
    assert lbl2.map_to_page(QPoint(240, 310)) is None


def test_dialog_forwards_click_signal():
    _app()
    from PyQt5.QtCore import QPoint
    from ui.login_mirror import LoginMirrorDialog
    dlg = LoginMirrorDialog()
    dlg.resize(560, 780)
    dlg.canvas.resize(480, 620)
    dlg.update_frame(_make_png(100, 200), 500, 1000)
    got = []
    dlg.click_requested.connect(lambda x, y: got.append((x, y)))
    dlg.canvas.page_clicked.emit(*dlg.canvas.map_to_page(QPoint(85 + 155, 310)))
    assert got and abs(got[0][0] - 250) < 3


def test_bad_png_does_not_crash():
    _app()
    from ui.login_mirror import _MirrorLabel
    lbl = _MirrorLabel()
    lbl.set_frame(b"not a png", 500, 1000)   # 坏帧静默丢弃
    assert lbl._pix is None


# ---------- 2. 接线端(源码文本断言) ----------

def test_browser_worker_wiring():
    src = _read("ui/browser_worker.py")
    for kw in (
        "mirror_frame = pyqtSignal(object, int, int)",
        'action == "mirror_shot"', 'action == "mirror_click"',
        "def _mirror_shot", "def _mirror_click",
        "Input.dispatchMouseEvent",         # CDP 点击
        "elementFromPoint",                 # JS 兜底
        "window.innerWidth",                # CSS 坐标系来源
        '_quiet = action in ("mirror_shot", "mirror_click")',
    ):
        assert kw in src, f"browser_worker.py 缺: {kw}"


def test_novel_ai_wiring():
    src = _read("novel_ai.py")
    for kw in (
        "def _open_login_mirror", "def _on_mirror_frame",
        "def _close_login_mirror",
        "mirror_frame.connect(self._on_mirror_frame)",
        'btn_mirror_login.clicked.connect',
        '"action": "mirror_click"', '{"action": "mirror_shot"}',
        "LoginMirrorDialog",
    ):
        assert kw in src, f"novel_ai.py 缺: {kw}"


def test_generation_control_has_button():
    src = _read("ui/tabs/generation_control.py")
    assert "btn_mirror_login" in src
    assert "b1.addWidget(self.btn_mirror_login)" in src
