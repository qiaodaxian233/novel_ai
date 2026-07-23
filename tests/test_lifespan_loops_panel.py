# -*- coding: utf-8 -*-
"""
test_lifespan_loops_panel.py — UI 面板单元测试（无头 Qt）
"""
from pathlib import Path
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 仓库根

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

from lifespan_loops_steps import (
    LifespanLoopsExtension, DEFAULT_LIFESPAN_LEDGER, DEFAULT_OPEN_LOOPS_CFG,
)
from lifespan_loops_panel import LifespanLoopsPanel


# 全局 QApplication（必须）
_app = QApplication.instance() or QApplication(sys.argv)


# ============================================================
# 测试用 MW
# ============================================================
class FakeMW:
    def __init__(self):
        self.workflow = None
        self.lifespan_ledger = None
        self.open_loops = None
        self._one_shot_callbacks = {}
        self.chapters = []

    class _Tab:
        def __init__(self):
            self.logs = []
        def log(self, m, lv="info"):
            self.logs.append((m, lv))

    @property
    def tab_generation(self):
        if not hasattr(self, "_tab_gen"):
            self._tab_gen = FakeMW._Tab()
        return self._tab_gen


def make_mw_with_data():
    mw = FakeMW()
    LifespanLoopsExtension.install(mw)
    return mw


# ============================================================
# 简单测试框架
# ============================================================
results = []
def expect(name, cond, msg=""):
    results.append((name, bool(cond), msg))
    icon = "✓" if cond else "✗"
    suffix = f" — {msg}" if msg and not cond else ""
    print(f"  {icon} {name}{suffix}")

def section(t):
    print()
    print("=" * 64)
    print(t)
    print("=" * 64)


# ============================================================
# Test P1: 无 mw 实例化不崩
# ============================================================
section("P1 — 无 mw 实例化")
panel = LifespanLoopsPanel(mw=None)
expect("无 mw 时 panel 创建成功", panel is not None)
expect("UI 控件存在", hasattr(panel, "chk_lifespan_on"))  # tbl_loops 已迁至 foreshadow_tab
expect("默认未启用", not panel.chk_lifespan_on.isChecked())
expect("默认起始 8760", panel.spin_total_days.value() == 8760)


# ============================================================
# Test P2: 有 mw 实例化 + sync_from_mw
# ============================================================
section("P2 — sync_from_mw 把数据拉到 UI")
mw = make_mw_with_data()
mw.lifespan_ledger.update({
    "enabled": True,
    "total_days": 10000,
    "used_days": 250,
    "warn_threshold": 500,
    "critical_threshold": 50,
    "auto_audit": False,
    "default_per_chapter": 2,
})
mw.open_loops.update({
    "enabled": True,
    "warn_gap": 60,
    "critical_gap": 120,
})
LifespanLoopsExtension.add_loop(
    mw, loop_id="A", desc="父亲死因", added_ch=3, keyword="父亲",
)
LifespanLoopsExtension.add_loop(
    mw, loop_id="B", desc="妹妹咒斑", added_ch=5, keyword="咒斑",
)

panel = LifespanLoopsPanel(mw)
expect("启用复选框被勾上", panel.chk_lifespan_on.isChecked())
expect("auto_audit 反映关闭", not panel.chk_auto_audit.isChecked())
expect("起始日数同步", panel.spin_total_days.value() == 10000)
expect("warn 阈值同步", panel.spin_warn.value() == 500)
expect("critical 阈值同步", panel.spin_critical.value() == 50)
expect("兜底每章同步", panel.spin_default_per.value() == 2)
# [已摘除] 伏笔检查 UI 已迁至 ui/foreshadow_tab.py,数据层由 test_lifespan_loops.py 覆盖
expect("当前状态显示已折寿", "250" in panel.lbl_used.text())
expect("剩余 = 9750", "9750" in panel.lbl_remaining.text())
expect("正常档", "正常" in panel.lbl_status_tag.text())


# ============================================================
# Test P3: sync_to_mw 把 UI 写回 dict
# ============================================================
section("P3 — sync_to_mw 写回")
mw = make_mw_with_data()
panel = LifespanLoopsPanel(mw)

panel.chk_lifespan_on.setChecked(True)
panel.spin_total_days.setValue(20000)
panel.spin_warn.setValue(700)
panel.spin_critical.setValue(60)
panel.spin_default_per.setValue(3)
panel.chk_auto_audit.setChecked(False)

panel.sync_to_mw()
expect("ledger.enabled 写回", mw.lifespan_ledger["enabled"] is True)
expect("ledger.total_days 写回", mw.lifespan_ledger["total_days"] == 20000)
expect("ledger.warn_threshold 写回", mw.lifespan_ledger["warn_threshold"] == 700)
expect("ledger.critical_threshold 写回", mw.lifespan_ledger["critical_threshold"] == 60)
expect("ledger.default_per_chapter 写回", mw.lifespan_ledger["default_per_chapter"] == 3)
expect("ledger.auto_audit 写回 False", mw.lifespan_ledger["auto_audit"] is False)


# ============================================================
# Test P4: 状态档位（正常 / 警戒 / 危急）
# ============================================================
section("P4 — refresh_status 三档")
mw = make_mw_with_data()
panel = LifespanLoopsPanel(mw)

# 正常
mw.lifespan_ledger.update({"total_days": 100, "used_days": 10,
                            "warn_threshold": 30, "critical_threshold": 5})
panel.refresh_status()
expect("剩余 90 → 正常", "正常" in panel.lbl_status_tag.text())

# 警戒
mw.lifespan_ledger["used_days"] = 75   # 剩 25 ≤ 30
panel.refresh_status()
expect("剩余 25 → 警戒", "警戒" in panel.lbl_status_tag.text())

# 危急
mw.lifespan_ledger["used_days"] = 97  # 剩 3 ≤ 5
panel.refresh_status()
expect("剩余 3 → 危急", "危急" in panel.lbl_status_tag.text())


# ============================================================
# [已摘除] 伏笔检查 UI 已迁至 ui/foreshadow_tab.py,数据层由 test_lifespan_loops.py 覆盖

# ============================================================
# Test P8: 重置寿元（绕开确认）
# ============================================================
section("P8 — 重置寿元台账")
mw = make_mw_with_data()
mw.lifespan_ledger.update({
    "total_days": 100, "used_days": 50,
    "history": [{"ch": 1, "days": 1, "note": "测"}],
})
panel = LifespanLoopsPanel(mw)
panel.spin_total_days.setValue(20000)

_orig_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
panel._on_reset_lifespan()
QMessageBox.question = _orig_q

expect("total_days 重置为 spinbox 值", mw.lifespan_ledger["total_days"] == 20000)
expect("used_days 清零", mw.lifespan_ledger["used_days"] == 0)
expect("history 清空", mw.lifespan_ledger["history"] == [])


# ============================================================
# Test P9: 取消重置（QMessageBox 返回 No）
# ============================================================
section("P9 — 取消重置应不动数据")
mw = make_mw_with_data()
mw.lifespan_ledger.update({"used_days": 99, "history": [{"ch":1,"days":1,"note":"x"}]})
panel = LifespanLoopsPanel(mw)

_orig_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.No)
panel._on_reset_lifespan()
QMessageBox.question = _orig_q

expect("取消时 used_days 不变", mw.lifespan_ledger["used_days"] == 99)
expect("取消时 history 不变", len(mw.lifespan_ledger["history"]) == 1)


# ============================================================
# Test P10: serialize_for_save / load_from_dict 接口
# ============================================================
section("P10 — serialize / load 接口")
mw = make_mw_with_data()
mw.lifespan_ledger.update({"enabled": True, "total_days": 5000, "used_days": 100})
LifespanLoopsExtension.add_loop(mw, loop_id="P10", desc="测试坑", added_ch=4)
mw.open_loops["enabled"] = True

panel = LifespanLoopsPanel(mw)
data = panel.serialize_for_save()
expect("serialize 返回 dict", isinstance(data, dict))
expect("含 lifespan_ledger", "lifespan_ledger" in data)
expect("含 open_loops", "open_loops" in data)
expect("loops 1 条", len(data["open_loops"]["loops"]) == 1)

# round-trip
mw2 = make_mw_with_data()
panel2 = LifespanLoopsPanel(mw2)
panel2.load_from_dict(data)
expect("load 后 enabled 还原", panel2.chk_lifespan_on.isChecked())
expect("load 后 total_days 还原", panel2.spin_total_days.value() == 5000)


# ============================================================
# Test P11: _refresh_total_hint 边界
# ============================================================
section("P11 — 起始寿元提示文本")
mw = make_mw_with_data()
panel = LifespanLoopsPanel(mw)
panel.spin_total_days.setValue(365)
panel._refresh_total_hint()
expect("365 日 → 1 年", "1 年" in panel.lbl_total_days_hint.text() and
       "日" not in panel.lbl_total_days_hint.text().split("年")[1].strip().rstrip(")"))
panel.spin_total_days.setValue(366)
panel._refresh_total_hint()
expect("366 日 → 1 年 1 日", "1 年 1 日" in panel.lbl_total_days_hint.text())
panel.spin_total_days.setValue(8760)
panel._refresh_total_hint()
expect("8760 日 → 24 年", "24 年" in panel.lbl_total_days_hint.text())


# ============================================================
# Test P12: 保存按钮触发 sync_to_mw + log
# ============================================================
section("P12 — 保存按钮 + 信号")
mw = make_mw_with_data()
panel = LifespanLoopsPanel(mw)

logs = []
panel.request_log.connect(lambda m, lv: logs.append((m, lv)))
save_count = [0]
panel.request_save.connect(lambda: save_count.__setitem__(0, save_count[0] + 1))

panel.chk_lifespan_on.setChecked(True)
panel.spin_total_days.setValue(7777)
panel._on_save_all_clicked()

expect("ledger 启用写回", mw.lifespan_ledger["enabled"] is True)
expect("ledger.total_days 写回 7777", mw.lifespan_ledger["total_days"] == 7777)
expect("发出 request_log 信号", len(logs) >= 1)
expect("发出 request_save 信号", save_count[0] == 1)


# ============================================================
# Test P13: 入账历史按钮（无历史 / 有历史）
# ============================================================
section("P13 — 入账历史弹窗")
mw = make_mw_with_data()
panel = LifespanLoopsPanel(mw)

# 拦截 information
infos = []
_orig_i = QMessageBox.information
QMessageBox.information = staticmethod(lambda *a, **k: infos.append(a) or QMessageBox.Ok)

panel._on_show_history()
expect("空历史时也弹窗（标题/正文 含'空'）", any("空" in str(a) for a in infos))

# 加入历史
mw.lifespan_ledger["history"] = [
    {"ch": 1, "days": 1, "note": "日落"},
    {"ch": 2, "days": 3, "note": "越阶"},
]
infos.clear()
panel._on_show_history()
QMessageBox.information = _orig_i

expect("有历史时弹窗触发", len(infos) == 1)


# ============================================================
# 汇总
# ============================================================
print()
print("=" * 64)
total = len(results)
passed = sum(1 for _n, ok, _ in results if ok)
failed = total - passed
print(f"测试总数: {total}   通过: {passed}   失败: {failed}")
print("=" * 64)


if __name__ == "__main__":
    if failed:
        print("失败明细：")
        for n, ok, msg in results:
            if not ok:
                print(f"  ✗ {n}" + (f" — {msg}" if msg else ""))
        sys.exit(1)
    else:
        print("✅ 全部通过")
        sys.exit(0)


# ---- pytest 适配(测试搬迁修复) ----
# 本文件是脚本式测试:import 即执行,结果存入模块级 results 列表,
# 但失败只在 __main__ 分支检查 → pytest 下失败会被静默吞掉。
# 这个包装函数把 results 暴露给 pytest,保证失败可见。
def test_all_expectations_pass():
    bad = [(n, msg) for n, ok, msg in results if not ok]
    assert not bad, "脚本式断言失败: " + "; ".join(
        f"{n}({msg})" if msg else n for n, msg in bad)
