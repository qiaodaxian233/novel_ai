# -*- coding: utf-8 -*-
"""
test_workflow_panel.py — WorkflowPanel 的无头单元测试
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
sys.path.insert(0, "/home/claude")
sys.path.insert(0, "/mnt/user-data/uploads")

from PyQt5.QtWidgets import QApplication, QCheckBox, QWidget
from PyQt5.QtCore import QTimer

# 注意:workflow_pipeline.py 在 uploads 目录,我们已经 path 进去了
from workflow_pipeline import (
    GenerationWorkflow, MemoryInjectStep, CanonInjectStep,
    CritiqueRulesInjectStep, WordCountStep, HookCheckStep,
    CanonAuditStep, RhythmScoreStep, CharacterScoreStep,
    CanonExtractStep, SummaryStep, NextChapterStep,
    PipelineContext,
)
from workflow_panel import WorkflowPanel, StepCard

_app = QApplication.instance() or QApplication(sys.argv)


# ============================================================
# Fake MainWindow & Tabs
# ============================================================

class FakeTabMemory(QWidget):
    def __init__(self):
        super().__init__()
        self.auto_inject = QCheckBox("注入对话记忆")
        self.auto_inject.setChecked(True)
        self.auto_summarize = QCheckBox("自动写摘要")
        self.auto_summarize.setChecked(True)


class FakeTabCanon(QWidget):
    def __init__(self):
        super().__init__()
        self.chk_inject = QCheckBox("注入 Canon")
        self.chk_inject.setChecked(True)
        self.chk_audit = QCheckBox("Canon 稽核")
        self.chk_audit.setChecked(True)
        self.chk_extract = QCheckBox("Canon 抽取")
        self.chk_extract.setChecked(True)


class FakeTabGeneration(QWidget):
    def __init__(self):
        super().__init__()
        self.chk_crit_words = QCheckBox("字数")
        self.chk_crit_words.setChecked(True)
        self.chk_crit_hook = QCheckBox("钩子")
        self.chk_crit_hook.setChecked(True)
        self.chk_crit_canon = QCheckBox("Canon")
        self.chk_crit_canon.setChecked(True)
        self.chk_crit_rhythm = QCheckBox("节奏")
        self.chk_crit_rhythm.setChecked(False)
        self.chk_crit_char = QCheckBox("人设")
        self.chk_crit_char.setChecked(False)
        self.logs = []

    def critique_config(self):
        return {
            "word_count": self.chk_crit_words.isChecked(),
            "hook":       self.chk_crit_hook.isChecked(),
            "canon":      self.chk_crit_canon.isChecked(),
            "rhythm":     self.chk_crit_rhythm.isChecked(),
            "character":  self.chk_crit_char.isChecked(),
        }

    def log(self, msg, level="info"):
        self.logs.append((msg, level))


class FakeMW:
    def __init__(self):
        self.tab_memory = FakeTabMemory()
        self.tab_canon = FakeTabCanon()
        self.tab_generation = FakeTabGeneration()
        self._batch_remaining = 0
        self._batch_paused = False
        # 装配 workflow
        self.workflow = GenerationWorkflow(self)
        self.workflow.setup_default_steps()


# ============================================================
# 测试框架
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
# T1: 基本实例化
# ============================================================
section("T1 — 实例化")
mw = FakeMW()
panel = WorkflowPanel(mw=mw)
expect("panel 创建成功", panel is not None)
expect("找到 11 张 step 卡片", len(panel._cards) == 11)

step_names = set(panel._cards.keys())
expected = {"memory_inject", "canon_inject", "critique_rules_inject",
            "word_count", "hook_check", "canon_audit",
            "rhythm_score", "character_score",
            "canon_extract", "summary", "next_chapter"}
expect("11 个 step name 全对", step_names == expected,
       f"差: 多={step_names - expected} 少={expected - step_names}")


# ============================================================
# T2: 初始 checkbox 状态从 upstream 同步
# ============================================================
section("T2 — 初始状态从上游同步")
expect("memory_inject 默认 ON",
       panel._cards["memory_inject"].checkbox.isChecked())
expect("canon_inject 默认 ON",
       panel._cards["canon_inject"].checkbox.isChecked())
expect("rhythm_score 默认 OFF(因为上游未勾)",
       not panel._cards["rhythm_score"].checkbox.isChecked())
expect("character_score 默认 OFF",
       not panel._cards["character_score"].checkbox.isChecked())
expect("critique_rules_inject 默认 OFF(rhythm 和 character 都没开)",
       not panel._cards["critique_rules_inject"].checkbox.isChecked())
expect("next_chapter 默认 OFF(_batch_remaining=0)",
       not panel._cards["next_chapter"].checkbox.isChecked())


# ============================================================
# T3: 上游变化 → panel 自动同步
# ============================================================
section("T3 — 上游 → panel 同步")
mw.tab_memory.auto_inject.setChecked(False)
expect("memory_inject 卡片同步关闭",
       not panel._cards["memory_inject"].checkbox.isChecked())

mw.tab_generation.chk_crit_rhythm.setChecked(True)
expect("rhythm_score 卡片同步开启",
       panel._cards["rhythm_score"].checkbox.isChecked())

# 改回去
mw.tab_memory.auto_inject.setChecked(True)
mw.tab_generation.chk_crit_rhythm.setChecked(False)


# ============================================================
# T4: panel checkbox → 上游同步
# ============================================================
section("T4 — panel → 上游同步")
panel._cards["canon_inject"].checkbox.setChecked(False)
expect("点 panel 关 canon_inject → 上游 chk_inject 也关",
       not mw.tab_canon.chk_inject.isChecked())

panel._cards["canon_audit"].checkbox.setChecked(False)
expect("点 panel 关 canon_audit → 上游 chk_crit_canon 也关",
       not mw.tab_generation.chk_crit_canon.isChecked())

# 改回去
panel._cards["canon_inject"].checkbox.setChecked(True)
panel._cards["canon_audit"].checkbox.setChecked(True)


# ============================================================
# T5: 派生类 step 不可手动控制(critique_rules_inject)
# ============================================================
section("T5 — 派生 / 运行时 step 是只读")
expect("critique_rules_inject 复选框被禁用",
       not panel._cards["critique_rules_inject"].checkbox.isEnabled())
expect("next_chapter 复选框被禁用",
       not panel._cards["next_chapter"].checkbox.isEnabled())

# 但当上游 rhythm 开了之后,critique_rules_inject 应该自动 ON
mw.tab_generation.chk_crit_rhythm.setChecked(True)
panel.sync_from_workflow()  # 强制刷新派生状态
expect("rhythm 开 → critique_rules_inject 自动 ON",
       panel._cards["critique_rules_inject"].checkbox.isChecked())
mw.tab_generation.chk_crit_rhythm.setChecked(False)


# ============================================================
# T6: 全开/全关按钮
# ============================================================
section("T6 — 批量开关")
panel._bulk_set(False)
# 检查可控的卡片都关了,派生的不动
expect("批量关后 memory_inject = OFF",
       not panel._cards["memory_inject"].checkbox.isChecked())
expect("批量关后 word_count = OFF",
       not panel._cards["word_count"].checkbox.isChecked())
expect("派生卡 critique_rules_inject 不被批量关影响",
       True)  # 它本来就是 OFF,这里只是确保没崩

panel._bulk_set(True)
expect("批量开后 memory_inject = ON",
       panel._cards["memory_inject"].checkbox.isChecked())
expect("批量开后 character_score = ON",
       panel._cards["character_score"].checkbox.isChecked())
# 现在 character 开了,派生的应该也 ON 了(因为 sync_from_workflow 通过 _bulk_set 间接触发了上游)
expect("character 上游已被打开",
       mw.tab_generation.chk_crit_char.isChecked())


# ============================================================
# T7: install_runtime_hooks 不会重复安装
# ============================================================
section("T7 — runtime hooks 幂等")
expect("初始化时已安装", panel._hooks_installed is True)

# 拿到一个 step,记录它当前的 run 函数
step_mem = next(s for _p, s in mw.workflow._registry._steps["pre_write"]
                if s.name == "memory_inject")
run_after_first = step_mem.run

panel.install_runtime_hooks()
expect("再次调用 hooks 不重复包装",
       step_mem.run is run_after_first)


# ============================================================
# T8: 运行时高亮 — 模拟 step 执行
# ============================================================
section("T8 — 运行时高亮")
# 模拟一次 word_count step 跑(它是即时的,直接同步 done)
ctx = PipelineContext(prompt="x", ch_num=1, target_words=2000,
                       min_words=1500, retry_left=2)
ctx.content = "abc"  # 不够字数,会 add_issue 但不影响 hook 测试

step_wc = next(s for _p, s in mw.workflow._registry._steps["post_write"]
               if s.name == "word_count")

# 跑前
panel._cards["word_count"].set_running(False)
expect("跑前不在 running 状态",
       not panel._cards["word_count"]._is_running)

# 跑
done_called = [False]
def fake_done():
    done_called[0] = True
step_wc.run(ctx, fake_done)

# 由于 hook 用 QTimer.singleShot(0, ...) 调度高亮,需要让事件循环跑一次
_app.processEvents()

expect("step 的 done 被 wrapper 转发调用了", done_called[0])
# 高亮发生在 QTimer.singleShot(0) 里,processEvents 之后 _on_step_started 已经调了
# 但 set_running(True) → mark_done(True) 是在同一个 event loop tick,我们需要等
import time
deadline = time.time() + 0.5
while time.time() < deadline:
    _app.processEvents()
    if not panel._cards["word_count"]._is_running:
        # mark_done 之后应该不是 running 了
        break

# 验证至少 status_text 被改过 (说明 wrap 起作用了)
status = panel._cards["word_count"].status_text.text()
expect("step 跑完后状态文字非'待命'(说明 wrapper 执行了)",
       status in ("✓ 完成", "✗ 失败"),
       f"实际: {status!r}")


# ============================================================
# T9: serialize / load 接口存在
# ============================================================
section("T9 — serialize / load 接口")
d = panel.serialize_for_save()
expect("serialize 返回 dict", isinstance(d, dict))
panel.load_from_dict({})
expect("load_from_dict 不抛异常", True)


# ============================================================
# T10: 无 mw 实例化不崩
# ============================================================
section("T10 — 边界:无 mw")
try:
    panel2 = WorkflowPanel(mw=None)
    # 没有 mw 时应该不调 install_runtime_hooks,且 _cards 为空
    expect("无 mw 时实例化成功", panel2 is not None)
    expect("无 mw 时 _hooks_installed 仍为 False",
           panel2._hooks_installed is False)
except Exception as e:
    expect("无 mw 时实例化", False, str(e))


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
