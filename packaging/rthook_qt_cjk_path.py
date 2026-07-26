# -*- coding: utf-8 -*-
"""PyInstaller 运行时钩子:PyQt5 中文(非 Latin-1)安装路径兼容。

问题:Qt5 的 QSettings 按 Latin-1 解码 qt.conf,PyInstaller 标准钩子
(pyi_rth_pyqt5)把安装前缀写进内嵌 qt.conf 时,遇到中文路径直接
UnicodeEncodeError,应用起不来。中文用户名 / 中文目录是重灾区。

策略(自定义 runtime hook 先于标准钩子执行):
  1. 前缀可 Latin-1 编码 → 不干预,交给标准钩子;
  2. Windows:取 8.3 短路径(纯 ASCII),用它预注册内嵌 qt.conf,
     标准钩子检测到 qt.conf 已存在会自动跳过;
  3. 短路径不可用(非系统盘常禁用 8.3)或非 Windows → 退回环境变量
     QT_PLUGIN_PATH / QT_QPA_PLATFORM_PLUGIN_PATH(系统原生编码,
     中文安全),保住平台插件加载这条命脉。
"""
import os
import sys


def _qt5_prefix():
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    for rel in (("PyQt5", "Qt5"), ("PyQt5", "Qt")):
        p = os.path.join(base, *rel)
        if os.path.isdir(p):
            return p
    return None


def _register_qt_conf(prefix_ascii):
    """用给定的 ASCII 前缀预注册内嵌 qt.conf(复用官方helper)"""
    from _pyi_rth_utils import qt as _rth_qt  # PyInstaller 内置
    _rth_qt.create_embedded_qt_conf("PyQt5", prefix_ascii)


def _win_short_path(path):
    import ctypes
    GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
    GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                  ctypes.c_uint]
    buf = ctypes.create_unicode_buffer(1024)
    if GetShortPathNameW(path, buf, 1024):
        return buf.value
    return None


def _main():
    if not getattr(sys, "frozen", False):
        return
    prefix = _qt5_prefix()
    if prefix is None:
        return
    try:
        prefix.encode("latin-1")
        return  # 纯 Latin-1 路径:标准钩子自己能行
    except UnicodeEncodeError:
        pass

    # 2) Windows 8.3 短路径
    if sys.platform == "win32":
        short = _win_short_path(prefix)
        if short:
            try:
                short.encode("latin-1")
                _register_qt_conf(short.replace(os.sep, "/"))
                return
            except (UnicodeEncodeError, Exception):
                pass

    # 3) 环境变量兜底(系统原生编码传递,中文安全)——
    #    即 PyInstaller 6 之前的经典方案。同时必须把标准钩子的
    #    qt.conf 写入猴补成空操作,否则它仍会带着中文前缀去
    #    encode("latin-1") 然后炸掉整个启动。
    plugins = os.path.join(prefix, "plugins")
    if os.path.isdir(plugins):
        os.environ.setdefault("QT_PLUGIN_PATH", plugins)
        platforms = os.path.join(plugins, "platforms")
        if os.path.isdir(platforms):
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", platforms)
    try:
        from _pyi_rth_utils import qt as _rth_qt
        _rth_qt.create_embedded_qt_conf = lambda *a, **k: None
    except Exception:
        pass


try:
    _main()
except Exception:
    # 兜底钩子自身绝不能弄崩启动
    pass
