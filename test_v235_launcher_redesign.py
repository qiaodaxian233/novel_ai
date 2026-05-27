# -*- coding: utf-8 -*-
"""v2.23.5 启动器重写守护测试

测试:
1. _is_valid_project 过滤垃圾目录(autosave/migrated 等)
2. _count_project_stats 不崩
3. _format_time_ago 边界
4. ProjectLauncher 类签名兼容主程序调用
5. 模块导入正常
"""
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_01_module_imports():
    """模块导入(不引发异常)"""
    # 注意:必须先导入 Qt 才能 import launcher,sandbox 里可能 PyQt5 没装
    try:
        from PyQt5.QtCore import Qt
    except ImportError:
        # 跳过(沙箱里 PyQt5 没装)
        return
    from ui.project_launcher import (
        ProjectLauncher, ProjectCard, _is_valid_project,
        _count_project_stats, _format_time_ago, _get_app_version,
    )


def test_02_is_valid_project_filters_garbage():
    """_is_valid_project 过滤 autosave/migrated/_/. 等垃圾"""
    try:
        from PyQt5.QtCore import Qt
    except ImportError:
        return
    from ui.project_launcher import _is_valid_project

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # 垃圾目录
        for bad_name in ["autosave", "trash", "logs", "cache",
                          ".hidden", "_backup", "项目_backup",
                          "项目_migrated", "NovelAI_Projects"]:
            d = root / bad_name
            d.mkdir(exist_ok=True)
            (d / "chapters").mkdir(exist_ok=True)
            assert not _is_valid_project(d), f"{bad_name} 应该被过滤"

        # 有效项目
        good = root / "我的小说"
        good.mkdir()
        (good / "chapters").mkdir()
        assert _is_valid_project(good), "有效项目应该通过"


def test_03_is_valid_project_requires_marker():
    """_is_valid_project 要求有 chapters/meta.json/project.json"""
    try:
        from PyQt5.QtCore import Qt
    except ImportError:
        return
    from ui.project_launcher import _is_valid_project

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        empty = root / "空目录"
        empty.mkdir()
        # 没有 chapters/meta.json/project.json,即使名字合法也不算项目
        assert not _is_valid_project(empty), "空目录(无标志文件)不算项目"

        valid1 = root / "有 chapters"
        valid1.mkdir()
        (valid1 / "chapters").mkdir()
        assert _is_valid_project(valid1)

        valid2 = root / "有 meta"
        valid2.mkdir()
        (valid2 / "meta.json").write_text("{}")
        assert _is_valid_project(valid2)


def test_04_count_project_stats_no_crash():
    """_count_project_stats 不崩,对空/异常路径返回安全默认值"""
    try:
        from PyQt5.QtCore import Qt
    except ImportError:
        return
    from ui.project_launcher import _count_project_stats

    # 不存在的路径
    s = _count_project_stats(Path("/nonexistent/path/xxx"))
    assert s["chapters"] == 0
    # mtime 可能 None
    assert "mtime" in s

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "proj"
        p.mkdir()
        (p / "chapters").mkdir()
        (p / "chapters" / "第1章.txt").write_text("test")
        (p / "chapters" / "第2章.md").write_text("test")
        s = _count_project_stats(p)
        assert s["chapters"] == 2


def test_05_format_time_ago():
    """_format_time_ago 各种时间区间正常输出"""
    try:
        from PyQt5.QtCore import Qt
    except ImportError:
        return
    from ui.project_launcher import _format_time_ago

    now = datetime.now()
    # None 返回 ""
    assert _format_time_ago(None) == ""
    # 30 秒前
    s = _format_time_ago(now - timedelta(seconds=30))
    assert "刚刚" in s or "分钟" in s
    # 5 分钟前
    s = _format_time_ago(now - timedelta(minutes=5))
    assert "分钟" in s
    # 3 小时前
    s = _format_time_ago(now - timedelta(hours=3))
    assert "小时" in s
    # 3 天前
    s = _format_time_ago(now - timedelta(days=3))
    assert "天前" in s
    # 10 天前 → 日期
    s = _format_time_ago(now - timedelta(days=10))
    assert "-" in s  # 日期格式 YYYY-MM-DD


def test_06_get_app_version_reads_from_main():
    """_get_app_version 从 novel_ai.py 读最新版本号(避免漂移)"""
    try:
        from PyQt5.QtCore import Qt
    except ImportError:
        return
    from ui.project_launcher import _get_app_version
    v = _get_app_version()
    assert v.startswith("v2."), f"版本格式异常:{v}"
    # 至少 v2.23.5
    parts = [int(x) for x in v[1:].split(".")]
    assert parts[0] >= 2 and parts[1] >= 23 and parts[2] >= 5, \
        f"从 novel_ai.py 读到的版本应至少 v2.23.5,实际 {v}"


def test_07_launcher_api_compat():
    """ProjectLauncher 类签名跟主程序调用方式兼容"""
    # 静态检查源码 — 不需要真实例化(沙箱 PyQt5 可能问题)
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(root, "ui", "project_launcher.py")):
        root = os.path.dirname(root)
    with open(os.path.join(root, "ui", "project_launcher.py"),
              encoding="utf-8") as f:
        src = f.read()
    # 必须有 ProjectLauncher 类
    assert "class ProjectLauncher" in src
    # 必须接受 project_dir 参数
    assert "def __init__(self, project_dir" in src
    # 必须有 selected_path 属性(主程序读取)
    assert "self.selected_path" in src
    # 必须有 accept()(继承 QDialog)
    assert "self.accept()" in src
    # ProjectCard 也得在
    assert "class ProjectCard" in src


def test_08_no_marketing_feature_cards():
    """v2.23.5 重写:不再有那 6 个营销卡片(AI辅助创作/盘古世界观系统等)"""
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(root, "ui", "project_launcher.py")):
        root = os.path.dirname(root)
    with open(os.path.join(root, "ui", "project_launcher.py"),
              encoding="utf-8") as f:
        src = f.read()
    # 旧 FeatureCard 不再出现
    assert "class FeatureCard" not in src, \
        "v2.23.5 不该再有 FeatureCard(营销卡片已去除)"
    # 旧"核心功能亮点"标题不再出现
    assert "核心功能亮点" not in src
    # 旧"盘古超级写作助手"营销描述不再出现
    assert "盘古超级写作助手" not in src


def test_09_app_version_constant_matches():
    """模块顶部 APP_VERSION 常量至少 v2.23.5"""
    import re
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(root, "ui", "project_launcher.py")):
        root = os.path.dirname(root)
    with open(os.path.join(root, "ui", "project_launcher.py"),
              encoding="utf-8") as f:
        src = f.read()
    m = re.search(r'^APP_VERSION\s*=\s*"(v[\d.]+)"', src, re.MULTILINE)
    assert m, "找不到 APP_VERSION 常量"
    v = m.group(1)
    parts = [int(x) for x in v[1:].split(".")]
    assert parts[0] >= 2 and parts[1] >= 23 and parts[2] >= 5, \
        f"APP_VERSION 应至少 v2.23.5,实际 {v}"


def test_10_project_card_has_path_attr():
    """ProjectCard 必须有 self.path 属性(用于双击打开)"""
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        return
    # 不实际创建(Qt 沙箱可能问题),只静态检查
    root = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(root, "ui", "project_launcher.py")):
        root = os.path.dirname(root)
    with open(os.path.join(root, "ui", "project_launcher.py"),
              encoding="utf-8") as f:
        src = f.read()
    assert "self.path = path" in src
    # 双击事件
    assert "mouseDoubleClickEvent" in src


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed.append(t.__name__)
    print(f"\n{passed}/{len(tests)} passed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
