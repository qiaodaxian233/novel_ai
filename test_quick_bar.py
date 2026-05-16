# -*- coding: utf-8 -*-
"""快速验证生成控制顶部浏览器操作行 + 双向同步

⚠️ 注意:此测试针对的是历史"快速操作栏"(ai_quick/btn_launch_quick 等)功能。
该功能已在 UI 重构中被合并到 tab_generation 主面板,本测试期望的控件已不存在。
2026-05-16 起,本文件标记为废弃,跳过执行。
如需重新启用快速操作栏功能,请同步实现 GenerationControl 里的:
  - ai_quick / btn_launch_quick / btn_close_quick / btn_grab_quick / status_quick
  - 与 tab_settings.ai_group 的双向同步
"""
import sys
print("⊘ test_quick_bar.py 已废弃(快速操作栏功能已合并到主面板),跳过执行。")
sys.exit(0)

# ---- 以下原测试代码保留作为历史参考,实际不会执行 ----
from pathlib import Path
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
import novel_ai

mw = novel_ai.MainWindow()
gen = mw.tab_generation
ts = mw.tab_settings

print("=" * 64)
print("生成控制顶部浏览器操作行 — 验证")
print("=" * 64)

assert hasattr(gen, "ai_quick"), "ai_quick 未挂上"
print(f"✓ ai_quick 存在,默认值 = {gen.ai_quick.currentText()!r}")
print(f"✓ ai_quick 选项 = {[gen.ai_quick.itemText(i) for i in range(gen.ai_quick.count())]}")

assert hasattr(gen, "btn_launch_quick"), "btn_launch_quick 未挂上"
print(f"✓ btn_launch_quick 存在,文字 = {gen.btn_launch_quick.text()!r}")

assert hasattr(gen, "btn_close_quick"), "btn_close_quick 未挂上"
print(f"✓ btn_close_quick 存在,默认 disabled = {not gen.btn_close_quick.isEnabled()}")

assert hasattr(gen, "btn_grab_quick"), "btn_grab_quick 未挂上"
print(f"✓ btn_grab_quick 存在,文字 = {gen.btn_grab_quick.text()!r}")

assert hasattr(gen, "status_quick"), "status_quick 未挂上"
print(f"✓ status_quick 存在,文字 = {gen.status_quick.text()!r}")

# 同步测试 1:从 ai_quick 改 → tab_settings.ai_group 跟着变
print("\n--- 双向同步测试 ---")
gen.ai_quick.setCurrentText("豆包")
app.processEvents()
selected_btn = ts.ai_group.checkedButton()
print(f"ai_quick → 豆包 后,创作设置 ai_group 选中:{selected_btn.text() if selected_btn else None!r}")
assert selected_btn is not None and selected_btn.text() == "豆包", \
    f"同步失败:期望豆包,实际 {selected_btn.text() if selected_btn else None}"
print("✓ ai_quick → ai_group 同步成功")

# 同步测试 2:从 tab_settings.ai_group 改 → ai_quick 跟着变
btn_yb = next(b for b in ts.ai_group.buttons() if b.text() == "元宝")
btn_yb.setChecked(True)
ts.ai_group.buttonClicked.emit(btn_yb)
app.processEvents()
print(f"ai_group → 元宝 后,生成控制 ai_quick:{gen.ai_quick.currentText()!r}")
assert gen.ai_quick.currentText() == "元宝", \
    f"反向同步失败:期望元宝,实际 {gen.ai_quick.currentText()}"
print("✓ ai_group → ai_quick 反向同步成功")

# 状态联动测试:update_browser_status 同时更新两个 Tab 的状态显示
print("\n--- 状态联动测试 ---")
mw.update_browser_status("idle")
app.processEvents()
print(f"update_browser_status('idle') 后:")
print(f"  生成控制 status_quick = {gen.status_quick.text()!r}")
print(f"  主窗口 status_indicator = {mw._status_indicator.text()!r}")
print(f"  生成控制 btn_close_quick.enabled = {gen.btn_close_quick.isEnabled()}")
print(f"  创作设置 btn_close.enabled = {ts.btn_close.isEnabled()}")
assert "空闲" in gen.status_quick.text()
assert gen.btn_close_quick.isEnabled() is True
assert ts.btn_close.isEnabled() is True
print("✓ 状态同时同步到两个 Tab")

mw.update_browser_status("stopped")
app.processEvents()
assert gen.btn_close_quick.isEnabled() is False
assert ts.btn_close.isEnabled() is False
print("✓ stopped 时两个 close 按钮一起 disabled")

# btn_launch_quick 应该绑定到 prelogin_ai
print("\n--- 按钮绑定验证 ---")
# 检查 receivers — Qt5 拿不到具体函数,但能数到至少一个连接
print(f"✓ btn_launch_quick 已绑定 (receivers = {gen.btn_launch_quick.receivers(gen.btn_launch_quick.clicked.signal)})")
print(f"✓ btn_grab_quick   已绑定 (receivers = {gen.btn_grab_quick.receivers(gen.btn_grab_quick.clicked.signal)})")

print()
print("=" * 64)
print("✅ 全部通过 — 浏览器操作行可正常使用")
print("=" * 64)
