# -*- mode: python ; coding: utf-8 -*-
"""盘古写作引擎 PyInstaller 打包配置(文件夹模式,非单文件)。

用法(推荐直接双击 打包EXE.bat):
    python -m PyInstaller -y --clean 盘古写作引擎.spec

产物:dist/盘古写作引擎/
    盘古写作引擎.exe      ← 双击运行,免 Python 环境
    _internal/            ← 依赖库与资源(assets 图标在里面)
    pangu_full_spec.md    ← 由 bat 拷到 exe 旁(代码按当前目录相对路径读它)

设计说明:
- 文件夹模式(onedir):启动快、杀软误报少、可增量替换文件;
  单文件模式每次启动要解压到临时目录,大型 PyQt5 应用体验差。
- 可选依赖动态检测:edge-tts / pygame / gradio_client / selenium /
  webdriver_manager / PyQtWebEngine 哪个装了就打包哪个,没装就跳过 —
  与程序运行时的 try/except 优雅降级一一对应,打包机不必凑齐全部依赖。
"""
import importlib.util
from PyInstaller.utils.hooks import collect_submodules

APP_NAME = "盘古写作引擎"


def _optional(*mods):
    """返回打包机上实际存在的可选模块(含全部子模块)"""
    out = []
    for m in mods:
        try:
            if importlib.util.find_spec(m) is not None:
                out += collect_submodules(m)
                print(f"[spec] 可选依赖已检测到,将打包: {m}")
            else:
                print(f"[spec] 可选依赖未安装,跳过: {m}(对应功能运行时自动降级)")
        except Exception:
            print(f"[spec] 可选依赖检测异常,跳过: {m}")
    return out


hiddenimports = _optional(
    "selenium",            # 浏览器自动化(AI 网站对接)
    "webdriver_manager",   # chromedriver 兜底下载
    "edge_tts",            # TTS 默认后端
    "pygame",              # TTS 音频播放
    "gradio_client",       # 本地 Index-TTS(可选)
    "requests",
)

datas = [
    ("assets", "assets"),                    # 图标/闪屏:代码按 __file__ 相对定位
    ("pangu_full_spec.md", "."),             # 兜底一份;主副本由 bat 拷到 exe 旁
]

a = Analysis(
    ["novel_ai.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["packaging/rthook_qt_cjk_path.py"],  # 中文路径兼容(qt.conf Latin-1 问题)
    excludes=[
        "tests", "pytest", "tkinter", "matplotlib",
        "IPython", "jupyter", "notebook",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,     # ← 文件夹模式的关键:二进制不并入 exe
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX 压缩易触发杀软误报,关闭
    console=False,             # 无黑窗口
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
