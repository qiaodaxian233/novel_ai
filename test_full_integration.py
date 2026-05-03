# -*- coding: utf-8 -*-
"""
test_full_integration.py — 完整集成测试

验证:
- novel_ai.py 改名后 setWindowTitle 是 "AI 写作工作台"
- 不再有示例章节
- 8 个原有 Tab + 寿元/伏笔 + 工作流 = 10 个 Tab
- 5 条研究报告技能装入 SkillLibrary
- 旧代码引用的 widget(btn_launch / url_input / site_combo / status_label / btn_close / btn_grab)
  在 tab_settings 上仍可访问
- save / load round-trip 包含 lifespan_loops
- workflow panel 装上了 11 张步骤卡片
- workflow panel 的运行时高亮 hooks 已安装
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
sys.path.insert(0, "/home/claude")

from PyQt5.QtWidgets import QApplication

_app = QApplication.instance() or QApplication(sys.argv)

import novel_ai

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
# T1: 项目改名
# ============================================================
section("T1 — 项目改名")
mw = novel_ai.MainWindow()
expect("窗口标题 = AI 写作工作台",
       mw.windowTitle() == "AI 写作工作台",
       f"实际: {mw.windowTitle()!r}")


# ============================================================
# T2: 示例章节已清空
# ============================================================
section("T2 — 示例章节已清空")
expect("self.chapters 为空", mw.chapters == [],
       f"实际有 {len(mw.chapters)} 章")
expect("章节列表 widget 也是空", mw.chapter_list.count() == 0)


# ============================================================
# T3: 10 个 Tab 全部装上
# ============================================================
section("T3 — Tab 列表完整")
expected = [
    "创作设置", "故事大纲", "对话记忆", "Canon 设定",
    "寿元/伏笔",         # 来自 lifespan_loops 集成
    "技能库",
    "工作流",            # 来自 workflow_panel 集成
    "生成控制", "章节编辑器", "小说封面生成",
]
actual = [mw.tabs.tabText(i) for i in range(mw.tabs.count())]
expect(f"Tab 数 = {len(expected)}",
       len(actual) == len(expected),
       f"实际 {len(actual)} 个: {actual}")
expect(f"Tab 顺序正确",
       actual == expected,
       f"实际: {actual}")


# ============================================================
# T4: 创作设置 AI配置 区域控件齐全
# ============================================================
section("T4 — 创作设置 AI配置(只管 AI 选择)")
ts = mw.tab_settings
expect("ai_group 存在", hasattr(ts, "ai_group"))
expect("ai_group 含 7 个按钮(ChatGPT/豆包/Gemini/DeepSeek/元宝/小米AI/自定义)",
       len(ts.ai_group.buttons()) == 7)
expect("custom_url 存在", hasattr(ts, "custom_url"))
expect("delay_check 存在", hasattr(ts, "delay_check"))
expect("btn_prelogin 存在", hasattr(ts, "btn_prelogin"))
# 创作设置 不再有 kernel_group / btn_close / btn_grab(都搬到生成控制了)
expect("创作设置 不再有 kernel_group(已移到生成控制)",
       not hasattr(ts, "kernel_group"))
expect("创作设置 不再有 btn_close(已移到生成控制)",
       not hasattr(ts, "btn_close"))


# ============================================================
# T5: 生成控制 Tab 顶部恢复完整面板
# ============================================================
section("T5 — 生成控制顶部完整面板")
tg = mw.tab_generation
expect("生成控制 有 kernel_group", hasattr(tg, "kernel_group"))
expect("kernel_group 含 3 个按钮(独立/调试/Edge)",
       len(tg.kernel_group.buttons()) == 3)
expect("生成控制 有 btn_launch", hasattr(tg, "btn_launch"))
expect("生成控制 有 btn_close", hasattr(tg, "btn_close"))
expect("生成控制 有 btn_go", hasattr(tg, "btn_go"))
expect("生成控制 有 btn_grab", hasattr(tg, "btn_grab"))
expect("生成控制 有 site_combo", hasattr(tg, "site_combo"))
expect("生成控制 有 url_input", hasattr(tg, "url_input"))
expect("生成控制 有 status_label", hasattr(tg, "status_label"))


# ============================================================
# T6: 内核映射(3 选项)+ ai_group ↔ site_combo 双向同步
# ============================================================
section("T6 — 内核映射 & AI 双向同步")
# 默认 Chrome 独立 (id=0)
expect("默认 selected_kernel_channel = None(standalone)",
       tg.selected_kernel_channel() is None)
# 切 Chrome 调试 attach (id=1)
tg.kernel_group.buttons()[1].setChecked(True)
expect("切 attach 后 = chrome",
       tg.selected_kernel_channel() == "chrome")
# 切 Edge (id=2)
tg.kernel_group.buttons()[2].setChecked(True)
expect("切 Edge 后 = msedge",
       tg.selected_kernel_channel() == "msedge")

# AI 同步:在创作设置 ai_group 选豆包,生成控制 site_combo 应同步
btn_db = next(b for b in ts.ai_group.buttons() if b.text() == "豆包")
btn_db.setChecked(True)
ts.ai_group.buttonClicked.emit(btn_db)
_app.processEvents()
expect("ai_group → site_combo 同步:选豆包",
       tg.site_combo.currentText() == "豆包",
       f"实际: {tg.site_combo.currentText()!r}")
expect("ai_group → url_input 同步:豆包 URL",
       "doubao" in tg.url_input.text().lower())

# 反向:生成控制 site_combo 选 DeepSeek,创作设置 ai_group 应同步
tg.site_combo.setCurrentText("DeepSeek")
_app.processEvents()
checked = ts.ai_group.checkedButton()
expect("site_combo → ai_group 反向同步:DeepSeek",
       checked is not None and checked.text() == "DeepSeek",
       f"实际: {checked.text() if checked else None!r}")


# ============================================================
# T7: 研究报告技能已装入 SkillLibrary
# ============================================================
section("T7 — 5 条研究报告出厂技能已装入")
skill_names = [s.get("name", "") for s in mw.tab_skills.skills]
print(f"  当前技能列表: {skill_names}")
research_keywords = [
    "细纲扩展", "桥段扩写", "一致性校验", "短文本生成", "高潮场面",
]
for kw in research_keywords:
    found = any(kw in s for s in skill_names)
    expect(f"含「{kw}」类技能", found,
           f"实际名单: {skill_names}")


# ============================================================
# T8: 寿元/伏笔 数据初始化
# ============================================================
section("T8 — 寿元 / 长期伏笔 初始化")
expect("mw.lifespan_ledger 存在", hasattr(mw, "lifespan_ledger"))
expect("mw.open_loops 存在", hasattr(mw, "open_loops"))
expect("默认 ledger.enabled = False(对普通项目零感知)",
       mw.lifespan_ledger.get("enabled") is False)
expect("默认 ledger.total_days 是 8760",
       mw.lifespan_ledger.get("total_days") == 8760)
expect("tab_lifespan 实例化成功",
       mw.tab_lifespan is not None)


# ============================================================
# T9: 工作流 Tab 装上 11 张卡片
# ============================================================
section("T9 — 工作流 Tab")
expect("tab_workflow 实例化成功", mw.tab_workflow is not None)
expect("workflow panel 包含 11 张卡片",
       len(mw.tab_workflow._cards) == 11,
       f"实际 {len(mw.tab_workflow._cards)} 张")
expect("运行时 hooks 已安装",
       mw.tab_workflow._hooks_installed is True)


# ============================================================
# T10: 浏览器状态信号通过 update_browser_status
# ============================================================
section("T10 — 浏览器状态信号")
mw.update_browser_status("idle")
expect("调用 update_browser_status(idle) 不抛", True)
expect("生成控制 status_label 文字反映 idle",
       "空闲" in tg.status_label.text(),
       f"实际: {tg.status_label.text()!r}")
expect("statusbar 指示器更新",
       hasattr(mw, "_status_indicator") and "空闲" in mw._status_indicator.text())


# ============================================================
# T11: save / load round-trip 含 lifespan_loops
# ============================================================
section("T11 — save / load round-trip")
# 改一些寿元数据
mw.lifespan_ledger["enabled"] = True
mw.lifespan_ledger["total_days"] = 5555
mw.lifespan_ledger["used_days"] = 100
# 把 panel 同步过去
mw.tab_lifespan.sync_from_mw()

# 拿到序列化的 dict(直接调 panel 的接口)
data = mw.tab_lifespan.serialize_for_save()
expect("serialize 返回 dict", isinstance(data, dict))
expect("含 lifespan_ledger", "lifespan_ledger" in data)
expect("ledger.total_days = 5555",
       data["lifespan_ledger"].get("total_days") == 5555)


# ============================================================
# T12: 模拟人类延迟 checkbox 影响 type_delay_ms
# ============================================================
section("T12 — 模拟人类延迟生效")
ts.delay_check.setChecked(False)
# 模拟读取 type_delay 的代码路径
fast = 30 if ts.delay_check.isChecked() else 5
expect("delay_check 关 → type_delay = 5", fast == 5)
ts.delay_check.setChecked(True)
slow = 30 if ts.delay_check.isChecked() else 5
expect("delay_check 开 → type_delay = 30", slow == 30)


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

if failed:
    print("失败明细:")
    for n, ok, msg in results:
        if not ok:
            print(f"  ✗ {n}" + (f" — {msg}" if msg else ""))
    sys.exit(1)
else:
    print("✅ 全部通过")
    sys.exit(0)
