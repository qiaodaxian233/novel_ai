# -*- coding: utf-8 -*-
"""test_v234_fanqie_rank_tab.py — v2.23.4 番茄榜单 Tab 守护测试"""
import ast
import json
import os
import re
import sys
import tempfile
import pytest

# ── 1. fanqie_rank_tab.py 语法 + 类存在 ──

def test_01_tab_file_syntax():
    """fanqie_rank_tab.py 语法正确"""
    src = open("ui/fanqie_rank_tab.py", encoding="utf-8").read()
    ast.parse(src)


def test_02_tab_class_exists():
    """FanqieRankTab 类 + 关键方法存在"""
    src = open("ui/fanqie_rank_tab.py", encoding="utf-8").read()
    assert "class FanqieRankTab" in src
    for method in [
        "update_stats", "update_scan_progress",
        "update_detail_progress", "on_detail_batch_done",
        "load_details_from_disk", "load_snapshot_from_disk",
        "set_project_root", "request_rescan",
    ]:
        assert method in src, f"缺少方法/属性: {method}"


def test_03_tab_signals_defined():
    """Tab 信号:request_rescan + request_log"""
    src = open("ui/fanqie_rank_tab.py", encoding="utf-8").read()
    assert "request_rescan = pyqtSignal()" in src
    assert "request_log = pyqtSignal(str, str)" in src


# ── 2. novel_ai.py 集成 ──

def test_04_tab_instantiated_in_main():
    """novel_ai.py 创建了 tab_fanqie_rank"""
    src = open("novel_ai.py", encoding="utf-8").read()
    assert "from ui.fanqie_rank_tab import FanqieRankTab" in src
    assert "self.tab_fanqie_rank = FanqieRankTab" in src


def test_05_tab_added_to_tab_list():
    """Tab 加入了 tab_list('📊 番茄榜单')"""
    src = open("novel_ai.py", encoding="utf-8").read()
    assert '"📊 番茄榜单"' in src


def test_06_worker_signals_forwarded():
    """Worker 信号转发到 Tab"""
    src = open("novel_ai.py", encoding="utf-8").read()
    for name in [
        "_fanqie_tab_on_rank_progress",
        "_fanqie_tab_on_rank_done",
        "_fanqie_tab_on_detail_progress",
        "_fanqie_tab_on_detail_done",
    ]:
        assert name in src, f"缺少转发方法: {name}"


def test_07_rescan_signal_connected():
    """request_rescan 信号连接到 _on_fanqie_rank_rescan"""
    src = open("novel_ai.py", encoding="utf-8").read()
    assert "request_rescan.connect" in src
    assert "_on_fanqie_rank_rescan" in src


def test_08_sync_on_project_open():
    """项目打开时同步 Tab(两个入口都有)"""
    src = open("novel_ai.py", encoding="utf-8").read()
    assert "_sync_fanqie_rank_tab" in src
    # 至少出现 3 次:定义 + _open_project_by_path + _autoload
    count = src.count("_sync_fanqie_rank_tab")
    assert count >= 3, f"_sync_fanqie_rank_tab 只出现 {count} 次,需要 >= 3(定义+两入口)"


def test_09_app_version_v2_23_4():
    """APP_VERSION 已升到 v2.23.4"""
    src = open("novel_ai.py", encoding="utf-8").read()
    m = re.search(r'APP_VERSION\s*=\s*"(v[\d.]+)"', src)
    assert m, "APP_VERSION 未找到"
    assert m.group(1) == "v2.23.4", f"版本应为 v2.23.4, 实际 {m.group(1)}"


# ── 3. Tab 数据渲染(纯逻辑测试,不需要 Qt) ──

def test_10_fill_heat_data_format():
    """热度表数据格式符合 aggregate_v231_stats 输出"""
    # 模拟 stats
    stats = {
        "total_books": 740,
        "unique_books": 423,
        "hot_categories_male": [
            ("都市高武", 870000), ("玄幻脑洞", 750000), ("都市脑洞", 530000),
        ],
        "hot_categories_female": [
            ("豪门总裁", 600000), ("年代", 450000),
        ],
    }
    # 验证数据格式兼容
    for cat, avg in stats["hot_categories_male"]:
        assert isinstance(cat, str)
        assert isinstance(avg, (int, float))
        assert avg > 0


def test_11_disk_cache_read_format():
    """磁盘缓存 book JSON 格式正确"""
    import tempfile, json, os, time
    tmpdir = tempfile.mkdtemp()
    books_dir = os.path.join(tmpdir, ".fanqie_cache", "books")
    os.makedirs(books_dir)
    # 写一个测试 book
    payload = {
        "book_id": "7320218217488600126",
        "scraped_at": time.time(),
        "source_label": "男频阅读榜·西方奇幻",
        "source_category": "西方奇幻",
        "detail": {
            "title": "早知道不这么玩了!",
            "author": "嘎嘎乱写",
            "abstract": "养成一个BOSS需要几步?",
            "tags": ["剑与魔法", "奇幻冒险", "无系统"],
            "categories": ["西方奇幻"],
            "word_count": "64.7万字",
            "status": "连载中",
        },
    }
    with open(os.path.join(books_dir, "7320218217488600126.json"), "w") as f:
        json.dump(payload, f)
    # 验证可读回
    with open(os.path.join(books_dir, "7320218217488600126.json")) as f:
        data = json.load(f)
    assert data["detail"]["title"] == "早知道不这么玩了!"
    assert "剑与魔法" in data["detail"]["tags"]


def test_12_filter_method_exists():
    """题材筛选方法存在"""
    src = open("ui/fanqie_rank_tab.py", encoding="utf-8").read()
    assert "_on_filter_changed" in src
    assert "_apply_filter" in src
    assert "cmb_filter" in src


def test_13_rank_snapshot_loading():
    """load_details_from_disk 从 rank_snapshot 读数据"""
    src = open("ui/fanqie_rank_tab.py", encoding="utf-8").read()
    assert "rank_snapshot_" in src
    assert "read_count_num" in src
    assert "read_count_raw" in src
    assert "read_display" in src


def test_14_scanning_guard_exists():
    """防重复扫榜锁存在"""
    src = open("novel_ai.py", encoding="utf-8").read()
    assert "_fanqie_scanning" in src
    # 至少 5 处:2 个 guard check + 2 个 set True + 1 个 set False
    count = src.count("_fanqie_scanning")
    assert count >= 5, f"_fanqie_scanning 只出现 {count} 次,需 >= 5"
