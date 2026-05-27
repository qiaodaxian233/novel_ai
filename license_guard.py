#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
license_guard.py — AI 写作工作台 授权验证客户端
"""

import sys
import os
import json
import time
import uuid
import socket
import hashlib
import hmac
import platform
import threading
import webbrowser
from pathlib import Path
from datetime import datetime

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QFrame, QApplication, QSplashScreen, QMessageBox,
    QProgressBar, QWidget, QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QRect,
)
from PyQt5.QtGui import (
    QFont, QColor, QPixmap, QPainter, QLinearGradient,
    QBrush, QPen, QIcon,
)

SERVER_BASE   = "https://upd.qiaodaxian233.cloud"
APP_SECRET    = "a8f3k2m9x7q1w6e4r5t0y2u8i3o9p7l1a8f3k2m9x7q1w6e4r5t0y2u8i3o9p7"
APP_VERSION   = "7.1.0"
APP_NAME      = "AI 写作工作台"
LICENSE_FILE  = Path.home() / "NovelAI_Projects" / ".license"
LAST_KEY_FILE = Path.home() / "NovelAI_Projects" / ".lastkey"
TIMEOUT       = 10
HEARTBEAT_SEC = 1800

# ──────────────────────────────────────────────────────────
#  开发模式开关: 通过环境变量控制，不写死在源码里
#  当前: 测试阶段默认跳过激活验证(default="1")
#  正式上线前: 把下面 "1" 改回 "0"，激活验证即自动启用
#  强制关闭验证: export NOVEL_AI_DEV_MODE=1
#  强制启用验证: export NOVEL_AI_DEV_MODE=0
# ──────────────────────────────────────────────────────────
import os as _os
DEV_MODE = _os.getenv("NOVEL_AI_DEV_MODE", "1") == "1"  # TODO: 上线前改 "1" → "0"


# ─────────────────────────────────────────────────────────
#  机器指纹
# ─────────────────────────────────────────────────────────
def get_machine_id() -> str:
    """生成稳定的机器唯一标识(SHA-256)"""
    parts = []
    # Windows: 注册表 MachineGuid
    if sys.platform == "win32":
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                               r"SOFTWARE\Microsoft\Cryptography")
            parts.append(winreg.QueryValueEx(k, "MachineGuid")[0])
        except Exception:
            pass
    # macOS: IOPlatformUUID
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                timeout=5, text=True)
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    parts.append(line.split('"')[-2])
                    break
        except Exception:
            pass
    # 通用兜底:hostname + username + MAC
    parts.append(socket.gethostname())
    parts.append(os.getenv("USERNAME") or os.getenv("USER") or "")
    try:
        parts.append(str(uuid.getnode()))
    except Exception:
        pass

    raw = "|".join(parts) or "fallback"
    return hashlib.sha256(raw.encode()).hexdigest()


def get_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def get_os_info() -> str:
    try:
        return f"{platform.system()} {platform.release()}"
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────
#  HMAC 签名
# ─────────────────────────────────────────────────────────
def make_sig(payload: dict) -> str:
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hmac.new(APP_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()


# ─────────────────────────────────────────────────────────
#  本地存储(加密)
# ─────────────────────────────────────────────────────────
def _obfuscate(s: str) -> str:
    """简单 XOR 混淆,防止明文存储"""
    key = APP_SECRET[:16].encode()
    data = s.encode()
    out = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
    return out.hex()

def _deobfuscate(h: str) -> str:
    try:
        data = bytes.fromhex(h)
        key = APP_SECRET[:16].encode()
        out = bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))
        return out.decode()
    except Exception:
        return ""

def save_license(license_key: str, machine_id: str, token: str, lic_type: str, expire_at: str) -> None:
    LICENSE_FILE.parent.mkdir(exist_ok=True)
    data = {"k": license_key, "m": machine_id, "t": token, "tp": lic_type,
            "e": expire_at or "", "ts": int(time.time())}
    encrypted = _obfuscate(json.dumps(data))
    LICENSE_FILE.write_text(encrypted, encoding="utf-8")

def load_license() -> dict | None:
    try:
        raw = LICENSE_FILE.read_text(encoding="utf-8").strip()
        data = json.loads(_deobfuscate(raw))
        return data
    except Exception:
        return None

def clear_license() -> None:
    try:
        LICENSE_FILE.unlink(missing_ok=True)
    except Exception:
        pass

def save_last_key(key: str) -> None:
    """保存用户最后输入的授权码(明文,仅用于预填充)"""
    try:
        LAST_KEY_FILE.parent.mkdir(exist_ok=True)
        LAST_KEY_FILE.write_text(key, encoding="utf-8")
    except Exception:
        pass

def load_last_key() -> str:
    """读取上次输入的授权码"""
    try:
        return LAST_KEY_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────
#  网络验证线程
# ─────────────────────────────────────────────────────────
class VerifyThread(QThread):
    done     = pyqtSignal(bool, dict)  # ok, data
    progress = pyqtSignal(str)

    def __init__(self, license_key: str):
        super().__init__()
        self.license_key = license_key

    def run(self):
        if not REQUESTS_OK:
            self.done.emit(False, {"msg": "缺少 requests 库,请运行: pip install requests"})
            return

        mid = get_machine_id()
        payload = {
            "license_key": self.license_key,
            "machine_id":  mid,
            "hostname":    get_hostname(),
            "os_info":     get_os_info(),
            "app_version": APP_VERSION,
        }
        payload["sig"] = make_sig({k: payload[k] for k in
                                   ["license_key","machine_id","app_version"]})
        self.progress.emit("正在连接验证服务器…")
        try:
            resp = requests.post(
                f"{SERVER_BASE}/api/verify.php",
                json=payload, timeout=TIMEOUT,
                headers={"Content-Type": "application/json; charset=utf-8"}
            )
            # 先检查响应内容是否为 JSON
            raw_text = resp.text.strip()
            try:
                data = resp.json()
            except Exception:
                # 服务器返回非 JSON（如 IP 白名单拦截、CDN 错误页等）
                if "allowlist" in raw_text.lower() or "whitelist" in raw_text.lower():
                    self.done.emit(False, {"msg": (
                        "验证服务器拒绝了本机IP连接\n"
                        "请联系作者将您的IP加入白名单，\n"
                        f"或使用授权服务器允许的网络环境。\n"
                        f"(服务器返回: {raw_text[:80]})"
                    )})
                elif resp.status_code == 403:
                    self.done.emit(False, {"msg": (
                        f"验证服务器返回 403 拒绝访问\n"
                        f"可能原因：IP未授权 / 请求被拦截\n"
                        f"(服务器返回: {raw_text[:80]})"
                    )})
                else:
                    self.done.emit(False, {"msg": (
                        f"验证服务器响应异常 (HTTP {resp.status_code})\n"
                        f"返回内容: {raw_text[:120]}\n"
                        f"提示: 可能是IP未加入服务器白名单，请联系作者。"
                    )})
                return
            if data.get("ok"):
                d = data.get("data", {})
                save_license(
                    self.license_key, mid,
                    d.get("token",""), d.get("type",""),
                    d.get("expire_at","")
                )
                self.done.emit(True, d)
            else:
                self.done.emit(False, {"msg": data.get("msg","验证失败")})
        except requests.exceptions.ConnectionError:
            self.done.emit(False, {"msg": "无法连接验证服务器\n请检查网络连接"})
        except requests.exceptions.Timeout:
            self.done.emit(False, {"msg": "验证超时,请稍后重试"})
        except Exception as e:
            self.done.emit(False, {"msg": f"验证出错: {e}"})


# ─────────────────────────────────────────────────────────
#  心跳线程(后台静默运行)
# ─────────────────────────────────────────────────────────
class HeartbeatThread(QThread):
    lost_license = pyqtSignal(str)  # 授权失效信号

    def __init__(self, license_key: str, machine_id: str):
        super().__init__()
        self.license_key = license_key
        self.machine_id  = machine_id
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.wait(HEARTBEAT_SEC):
            if not REQUESTS_OK:
                continue
            try:
                resp = requests.post(
                    f"{SERVER_BASE}/api/heartbeat.php",
                    json={"license_key": self.license_key,
                          "machine_id": self.machine_id},
                    timeout=TIMEOUT
                )
                data = resp.json()
                if not data.get("ok"):
                    self.lost_license.emit(data.get("msg","授权验证失败"))
            except Exception:
                pass  # 网络抖动不报警


# ─────────────────────────────────────────────────────────
#  版本更新检查
# ─────────────────────────────────────────────────────────
class UpdateChecker(QThread):
    update_found = pyqtSignal(dict)

    def run(self):
        if not REQUESTS_OK:
            return
        try:
            resp = requests.get(
                f"{SERVER_BASE}/api/version.php",
                params={"current": APP_VERSION, "channel": "stable"},
                timeout=TIMEOUT
            )
            data = resp.json()
            if data.get("ok") and data.get("data", {}).get("has_update"):
                self.update_found.emit(data["data"])
        except Exception:
            pass


# ─────────────────────────────────────────────────────────
#  闪屏
# ─────────────────────────────────────────────────────────
class SplashWindow(QSplashScreen):
    def __init__(self):
        px = self._make_pixmap()
        super().__init__(px, Qt.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.FramelessWindowHint)

    def _make_pixmap(self) -> QPixmap:
        W, H = 520, 300
        px = QPixmap(W, H)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)

        # 背景渐变
        grad = QLinearGradient(0, 0, W, H)
        grad.setColorAt(0.0, QColor("#0f0e17"))
        grad.setColorAt(1.0, QColor("#1a1a2e"))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, W, H, 16, 16)

        # 紫色光晕
        glow = QLinearGradient(0, 0, W//2, H//2)
        glow.setColorAt(0, QColor(108, 99, 255, 40))
        glow.setColorAt(1, QColor(108, 99, 255, 0))
        p.setBrush(QBrush(glow))
        p.drawEllipse(-40, -40, 300, 240)

        # 边框
        p.setPen(QPen(QColor(255, 255, 255, 20), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(1, 1, W-2, H-2, 15, 15)

        # 图标
        p.setFont(QFont("Segoe UI", 32))
        p.setPen(QColor("#a78bfa"))
        p.drawText(QRect(0, 60, W, 50), Qt.AlignCenter, "✍")

        # 标题
        p.setFont(QFont("Segoe UI", 20, QFont.Bold))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(0, 120, W, 40), Qt.AlignCenter, APP_NAME)

        # 副标题
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(QColor("#6b7280"))
        p.drawText(QRect(0, 162, W, 24), Qt.AlignCenter, f"v{APP_VERSION}  ·  智能长篇小说创作系统")

        # 进度条底色
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 15))
        p.drawRoundedRect(60, 230, W-120, 4, 2, 2)

        p.end()
        return px

    def set_progress(self, pct: int, text: str = ""):
        """外部更新进度(重绘)"""
        pass  # 闪屏用 showMessage 即可

    def mousePressEvent(self, ev):
        pass  # 禁止点击关闭


# ─────────────────────────────────────────────────────────
#  激活对话框
# ─────────────────────────────────────────────────────────
DARK_STYLE = """
QDialog { background: #13131f; }
QLabel  { color: #e0e0e0; }
QLineEdit {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px;
    color: #e0e0e0;
    padding: 10px 14px;
    font-size: 14px;
    letter-spacing: 2px;
}
QLineEdit:focus { border-color: #6c63ff; }
QPushButton#btnActivate {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #6c63ff, stop:1 #f64f59);
    border: none;
    border-radius: 8px;
    color: white;
    font-size: 14px;
    font-weight: bold;
    padding: 12px;
}
QPushButton#btnActivate:hover { opacity: 0.85; }
QPushButton#btnActivate:disabled { background: #333; color: #666; }
QPushButton#btnBuy {
    background: transparent;
    border: 1px solid rgba(108,99,255,0.4);
    border-radius: 8px;
    color: #a78bfa;
    font-size: 13px;
    padding: 10px;
}
QPushButton#btnBuy:hover { background: rgba(108,99,255,0.15); }
QLabel#lblError { color: #fca5a5; font-size: 12px; }
QLabel#lblSuccess { color: #6ee7b7; font-size: 12px; }
QProgressBar {
    border: none; background: rgba(255,255,255,0.08);
    border-radius: 3px; height: 4px;
}
QProgressBar::chunk { background: #6c63ff; border-radius: 3px; }
"""

class ActivationDialog(QDialog):
    """授权激活对话框"""

    def __init__(self, parent=None, prefill_key: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — 授权激活")
        self.setFixedSize(460, 480)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        self.setStyleSheet(DARK_STYLE)
        self.verified_data = None
        self._thread = None
        self._build_ui(prefill_key)

    def _build_ui(self, prefill_key: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 28)
        layout.setSpacing(0)

        # ── 顶部图标+标题 ──────────────────────────
        icon_lbl = QLabel("✍")
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setFont(QFont("Segoe UI", 28))
        icon_lbl.setStyleSheet("color: #a78bfa; margin-bottom: 4px")
        layout.addWidget(icon_lbl)

        title = QLabel(APP_NAME)
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Segoe UI", 17, QFont.Bold))
        title.setStyleSheet("color: white; margin-bottom: 2px")
        layout.addWidget(title)

        sub = QLabel(f"v{APP_VERSION}  ·  请输入授权码以继续使用")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #6b7280; font-size: 12px; margin-bottom: 28px")
        layout.addWidget(sub)

        # ── 授权码输入 ─────────────────────────────
        lbl = QLabel("授权码")
        lbl.setStyleSheet("color: #9ca3af; font-size: 12px; margin-bottom: 6px")
        layout.addWidget(lbl)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("XXXXX-XXXXX-XXXXX-XXXXX")
        self.key_input.setAlignment(Qt.AlignCenter)
        self.key_input.setMaxLength(23)
        if prefill_key:
            self.key_input.setText(prefill_key)
        self.key_input.returnPressed.connect(self._do_verify)
        layout.addWidget(self.key_input)
        layout.addSpacing(6)

        # ── 提示文字 ───────────────────────────────
        self.lbl_status = QLabel("")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setObjectName("lblError")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setMinimumHeight(36)
        layout.addWidget(self.lbl_status)

        # ── 进度条 ─────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # 不确定模式
        self.progress.setVisible(False)
        self.progress.setFixedHeight(4)
        layout.addWidget(self.progress)
        layout.addSpacing(16)

        # ── 激活按钮 ───────────────────────────────
        self.btn_activate = QPushButton("🔓  激活软件")
        self.btn_activate.setObjectName("btnActivate")
        self.btn_activate.setFixedHeight(46)
        self.btn_activate.clicked.connect(self._do_verify)
        layout.addWidget(self.btn_activate)
        layout.addSpacing(10)

        # ── 购买链接 ───────────────────────────────
        self.btn_buy = QPushButton("没有授权码?前往官网购买")
        self.btn_buy.setObjectName("btnBuy")
        self.btn_buy.setFixedHeight(40)
        self.btn_buy.clicked.connect(lambda: webbrowser.open(SERVER_BASE))
        layout.addWidget(self.btn_buy)

        layout.addStretch()

        # ── 版权 ───────────────────────────────────
        footer = QLabel(f"© {datetime.now().year} {APP_NAME} · 软件受授权协议保护")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #374151; font-size: 11px")
        layout.addWidget(footer)

    def _do_verify(self):
        key = self.key_input.text().strip().upper()
        # 格式预检(5+1)*4-1=23
        if len(key) < 5:
            self._set_status("请输入正确格式的授权码", error=True)
            return

        save_last_key(key)  # 立即保存，下次自动预填充
        self._set_busy(True)
        self._thread = VerifyThread(key)
        self._thread.progress.connect(lambda s: self._set_status(s, False))
        self._thread.done.connect(self._on_verify_done)
        self._thread.start()

    def _on_verify_done(self, ok: bool, data: dict):
        self._set_busy(False)
        if ok:
            self.verified_data = data
            self._set_status("✅ 授权验证成功!正在启动…", error=False)
            self.lbl_status.setObjectName("lblSuccess")
            self.lbl_status.setStyleSheet("color: #6ee7b7; font-size: 12px")
            QTimer.singleShot(1200, self.accept)
        else:
            self._set_status(data.get("msg", "验证失败"), error=True)

    def _set_busy(self, busy: bool):
        self.btn_activate.setEnabled(not busy)
        self.key_input.setEnabled(not busy)
        self.progress.setVisible(busy)

    def _set_status(self, text: str, error: bool = True):
        self.lbl_status.setText(text)
        color = "#fca5a5" if error else "#9ca3af"
        self.lbl_status.setStyleSheet(f"color: {color}; font-size: 12px")


# ─────────────────────────────────────────────────────────
#  推送消息弹窗
# ─────────────────────────────────────────────────────────
TYPE_STYLES = {
    "info":    ("#06b6d4", "#0e7490", "ℹ️"),
    "success": ("#10b981", "#065f46", "✅"),
    "warning": ("#f59e0b", "#92400e", "⚠️"),
    "danger":  ("#ef4444", "#7f1d1d", "🚨"),
}

class PushMessageDialog(QDialog):
    def __init__(self, messages: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — 系统通知")
        self.setFixedWidth(420)
        self.setStyleSheet("QDialog{background:#13131f} QLabel{color:#e0e0e0}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)

        for m in messages[:3]:
            mtype = m.get("type","info")
            color, _, icon = TYPE_STYLES.get(mtype, TYPE_STYLES["info"])

            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{background: rgba(255,255,255,.04);
                         border:1px solid {color}44;border-radius:12px;padding:14px}}
            """)
            cl = QVBoxLayout(card)
            cl.setSpacing(6)

            h = QLabel(f"{icon}  {m.get('title','')}")
            h.setFont(QFont("Segoe UI", 11, QFont.Bold))
            h.setStyleSheet(f"color:{color};border:none;background:transparent")
            cl.addWidget(h)

            body = QLabel(m.get("content",""))
            body.setWordWrap(True)
            body.setStyleSheet("color:#d1d5db;font-size:12px;border:none;background:transparent")
            cl.addWidget(body)

            layout.addWidget(card)

        btn = QPushButton("我已知晓")
        btn.setStyleSheet("""
            QPushButton{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);
            border-radius:8px;color:#fff;padding:10px;font-size:13px}
            QPushButton:hover{background:rgba(255,255,255,.15)}
        """)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


# ─────────────────────────────────────────────────────────
#  更新通知弹窗
# ─────────────────────────────────────────────────────────
class UpdateDialog(QDialog):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.download_url = data.get("download_url","")
        self.setWindowTitle("发现新版本")
        self.setFixedWidth(400)
        self.setStyleSheet("QDialog{background:#13131f} QLabel{color:#e0e0e0}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28,24,28,24)
        layout.setSpacing(14)

        badge = QLabel(f"🎉  {data.get('title','发现新版本')}")
        badge.setFont(QFont("Segoe UI",13,QFont.Bold))
        badge.setStyleSheet("color:#a78bfa")
        layout.addWidget(badge)

        ver_lbl = QLabel(f"新版本: v{data.get('version','')}   当前: v{APP_VERSION}")
        ver_lbl.setStyleSheet("color:#6b7280;font-size:12px")
        layout.addWidget(ver_lbl)

        log_box = QFrame()
        log_box.setStyleSheet("QFrame{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.07);border-radius:10px}")
        ll = QVBoxLayout(log_box)
        log_lbl = QLabel(data.get("changelog",""))
        log_lbl.setWordWrap(True)
        log_lbl.setStyleSheet("color:#9ca3af;font-size:12px;white-space:pre-wrap")
        ll.addWidget(log_lbl)
        layout.addWidget(log_box)

        if data.get("force_update"):
            force = QLabel("⚠️ 此版本需强制升级,请下载后重新运行")
            force.setStyleSheet("color:#fca5a5;font-size:12px")
            layout.addWidget(force)

        btns = QHBoxLayout()
        if self.download_url:
            dl = QPushButton("立即下载")
            dl.setStyleSheet("background:linear-gradient(135deg,#6c63ff,#f64f59);border:none;border-radius:8px;color:#fff;padding:10px 20px;font-weight:bold")
            dl.clicked.connect(self._download)
            btns.addWidget(dl)

        if not data.get("force_update"):
            skip = QPushButton("稍后更新")
            skip.setStyleSheet("background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:8px;color:#9ca3af;padding:10px 20px")
            skip.clicked.connect(self.reject)
            btns.addWidget(skip)

        layout.addLayout(btns)

    def _download(self):
        if self.download_url:
            webbrowser.open(self.download_url)
        self.accept()


# ─────────────────────────────────────────────────────────
#  主入口:LicenseGuard
# ─────────────────────────────────────────────────────────
class LicenseGuard:
    """
    在 main() 里使用:
        guard = LicenseGuard(app)
        if not guard.check():
            sys.exit(0)
    验证通过后调用 guard.start_heartbeat() 开启后台心跳。
    """

    def __init__(self, app: QApplication):
        self.app = app
        self._heartbeat: HeartbeatThread | None = None
        self._verified_data: dict = {}

    # ── 主检测入口 ─────────────────────────────────────────
    def check(self) -> bool:
        # ── 开发模式：跳过所有验证 ──────────────────────
        if DEV_MODE:
            return True
        # ─────────────────────────────────────────────────
        # 1. 闪屏
        splash = SplashWindow()
        splash.show()
        splash.showMessage("正在初始化…",
                           Qt.AlignBottom | Qt.AlignHCenter, QColor("#6b7280"))
        self.app.processEvents()
        time.sleep(0.4)

        # 2. 尝试读取缓存授权
        cached = load_license()
        if cached:
            splash.showMessage("正在验证授权…",
                               Qt.AlignBottom | Qt.AlignHCenter, QColor("#6b7280"))
            self.app.processEvents()
            # 快速重验(后台线程,闪屏期间等待最多5秒)
            ok, data = self._quick_verify(cached.get("k",""), cached.get("m",""))
            if ok:
                self._verified_data = data
                splash.showMessage("授权验证成功,正在启动…",
                                   Qt.AlignBottom | Qt.AlignHCenter, QColor("#10b981"))
                self.app.processEvents()
                time.sleep(0.6)
                splash.finish(None)
                self._show_messages(data.get("messages",[]))
                self._check_update(data.get("latest_ver"))
                return True

        splash.finish(None)

        # 3. 弹出激活窗口
        prefill = cached.get("k","") if cached else load_last_key()
        dlg = ActivationDialog(prefill_key=prefill)
        if dlg.exec_() == QDialog.Accepted:
            self._verified_data = dlg.verified_data or {}
            self._show_messages(self._verified_data.get("messages",[]))
            self._check_update(self._verified_data.get("latest_ver"))
            return True
        return False

    def start_heartbeat(self, main_window=None):
        """验证通过后调用,启动后台心跳"""
        cached = load_license()
        if not cached:
            return
        self._heartbeat = HeartbeatThread(cached["k"], cached["m"])
        if main_window:
            self._heartbeat.lost_license.connect(
                lambda msg: self._on_license_lost(msg, main_window)
            )
        self._heartbeat.start()

    def stop_heartbeat(self):
        if self._heartbeat:
            self._heartbeat.stop()
            self._heartbeat.wait(3000)

    # ── 内部方法 ──────────────────────────────────────────
    def _quick_verify(self, key: str, machine_id: str, timeout: int = 6) -> tuple[bool, dict]:
        """同步快速验证(阻塞最多 timeout 秒)"""
        if not REQUESTS_OK or not key:
            return False, {}
        payload = {"license_key": key, "machine_id": machine_id,
                   "hostname": get_hostname(), "os_info": get_os_info(),
                   "app_version": APP_VERSION}
        payload["sig"] = make_sig({k: payload[k] for k in ["license_key","machine_id","app_version"]})
        try:
            resp = requests.post(f"{SERVER_BASE}/api/verify.php",
                                 json=payload, timeout=timeout)
            try:
                data = resp.json()
            except Exception:
                return False, {"msg": f"服务器响应异常: {resp.text.strip()[:80]}"}
            return data.get("ok", False), data.get("data", {})
        except Exception:
            return False, {}

    def _show_messages(self, messages: list):
        if not messages:
            return
        dlg = PushMessageDialog(messages)
        dlg.exec_()

    def _check_update(self, latest_ver: dict | None):
        # 延迟1.5秒再检查，避免和主窗口启动撞在一起弹双窗口
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._do_check_update(latest_ver))

    def _do_check_update(self, latest_ver: dict | None):
        if not latest_ver or not latest_ver.get("has_update"):
            # 后台异步检查
            self._checker = UpdateChecker()
            self._checker.update_found.connect(self._on_update_found)
            self._checker.start()
            return
        if latest_ver.get("has_update"):
            dlg = UpdateDialog(latest_ver)
            dlg.exec_()

    def _on_update_found(self, data: dict):
        dlg = UpdateDialog(data)
        dlg.exec_()

    def _on_license_lost(self, msg: str, window):
        QMessageBox.critical(window, "授权验证失败",
                             f"{msg}\n\n软件将关闭,请重新激活。")
        clear_license()
        self.stop_heartbeat()
        window.close()

    @property
    def license_type(self) -> str:
        return self._verified_data.get("type", "unknown")

    @property
    def expire_at(self) -> str:
        return self._verified_data.get("expire_at", "")


# ─────────────────────────────────────────────────────────
#  集成补丁:修改 novel_ai.py 的 main() 函数
# ─────────────────────────────────────────────────────────
PATCH_CODE = '''
# ═══════════ 在 novel_ai.py 底部 main() 中添加如下代码 ═══════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # ── 授权验证(新增) ──────────────────────────────────
    from license_guard import LicenseGuard
    guard = LicenseGuard(app)
    if not guard.check():
        sys.exit(0)
    # ────────────────────────────────────────────────────

    win = MainWindow()
    win.show()

    # 启动心跳(新增)
    guard.start_heartbeat(win)
    app.aboutToQuit.connect(guard.stop_heartbeat)

    sys.exit(app.exec_())
'''

if __name__ == "__main__":
    print("license_guard.py — 独立测试模式")
    print(PATCH_CODE)
    # 快速 UI 测试
    _app = QApplication(sys.argv)
    guard = LicenseGuard(_app)
    result = guard.check()
    print("验证结果:", result)
    if result:
        print("授权类型:", guard.license_type)
