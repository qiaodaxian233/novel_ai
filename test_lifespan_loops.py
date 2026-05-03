# -*- coding: utf-8 -*-
"""
test_lifespan_loops.py — 寿元台账 + 长期伏笔检查 单元测试

不依赖 Qt / Selenium / 浏览器，跑这个文件能直接验证：
- LifespanInjectStep 注入与停用
- LifespanAuditStep 三层解析（正则 / AI / 兜底）
- LifespanAuditStep 危急阈值 → ctx.issues
- OpenLoopsCheckStep 关键词命中 → 自动刷新 last_seen_ch
- OpenLoopsCheckStep warn / critical 分级 → log + issue
- LifespanLoopsExtension.install() 注册到 fake workflow
- serialize / deserialize round-trip

跑法： python test_lifespan_loops.py
"""
from __future__ import annotations
import sys
import json

# 保证从 /home/claude 加载
sys.path.insert(0, "/home/claude")

from lifespan_loops_steps import (
    LifespanInjectStep,
    LifespanAuditStep,
    OpenLoopsCheckStep,
    LifespanLoopsExtension,
    DEFAULT_LIFESPAN_LEDGER,
    DEFAULT_OPEN_LOOPS_CFG,
)


# ================================================================
# 最小存根：模拟 PipelineContext / MainWindow / TabGeneration / Workflow
# ================================================================
class FakeCtx:
    """模拟 workflow_pipeline.PipelineContext 的最小子集。"""
    def __init__(self, ch_num=1, target_words=3000):
        self.ch_num = ch_num
        self.target_words = target_words
        self.min_words = int(target_words * 0.85)
        self.retry_left = 3
        self.original_prompt = "BASE"
        self.prompt = "BASE"
        self.content = ""
        self.issues = []
        self.extras = {}

    def append_prompt(self, text):
        self.prompt += text

    def has_issues(self):
        return bool(self.issues)


class FakeTab:
    def __init__(self):
        self.logs = []   # [(msg, level)]

    def log(self, msg, level="info"):
        self.logs.append((msg, level))


class FakeRegistry:
    """模拟 workflow_pipeline.StepRegistry 的最小子集。"""
    def __init__(self):
        self._items = {"pre_write": [], "post_write": [], "post_chain": []}

    def register(self, phase, step, priority=50):
        if phase not in self._items:
            raise ValueError(f"unknown phase: {phase}")
        self._items[phase].append((priority, step))
        self._items[phase].sort(key=lambda x: x[0])

    def get(self, phase):
        return [s for _p, s in self._items.get(phase, [])]


class FakeWorkflow:
    def __init__(self):
        self._registry = FakeRegistry()


class FakeMW:
    """模拟 MainWindow，暴露所需的属性 / 方法。"""
    def __init__(self):
        self.tab_generation = FakeTab()
        self.workflow = FakeWorkflow()
        self._one_shot_callbacks = {}
        self._sent_to_ai = []   # 记录 _send_to_ai 调用

        # 模拟 _send_to_ai：自动模拟 AI 回复
        # 由 test 单条预置：self._ai_reply = "..."
        self._ai_reply = None

    def _send_to_ai(self, prompt, label, target=None, **kw):
        self._sent_to_ai.append((label, target, prompt))
        if target and target.startswith("_cb_") and self._ai_reply is not None:
            cb = self._one_shot_callbacks.pop(target, None)
            if cb:
                cb(self._ai_reply)

    def _extract_json_blob(self, raw):
        """复刻 novel_ai.py 里的解析容错（最小版）。"""
        s = raw.strip()
        # 去掉 ```json...``` 或 ```...```
        if s.startswith("```"):
            lines = s.split("\n")
            if len(lines) >= 2:
                s = "\n".join(lines[1:])
            if s.endswith("```"):
                s = s[:s.rfind("```")]
        return s.strip()


# ================================================================
# 通用工具
# ================================================================
results = []  # (name, ok, msg)
def expect(name, cond, msg=""):
    results.append((name, bool(cond), msg))
    icon = "✓" if cond else "✗"
    print(f"  {icon} {name}" + (f" — {msg}" if msg and not cond else ""))


def section(title):
    print()
    print("=" * 64)
    print(title)
    print("=" * 64)


def done_marker():
    """生成一个 done() 函数，记录是否被调用。"""
    box = {"called": 0}
    def _done():
        box["called"] += 1
    _done.box = box
    return _done


# ================================================================
# Test 1: 模块导入
# ================================================================
section("Test 1 — 模块导入")
expect("可 import LifespanInjectStep / LifespanAuditStep / OpenLoopsCheckStep",
       all([LifespanInjectStep, LifespanAuditStep, OpenLoopsCheckStep]))
expect("DEFAULT_LIFESPAN_LEDGER 含必需字段",
       all(k in DEFAULT_LIFESPAN_LEDGER for k in
           ["total_days", "used_days", "warn_threshold", "critical_threshold"]))
expect("DEFAULT_OPEN_LOOPS_CFG 含必需字段",
       all(k in DEFAULT_OPEN_LOOPS_CFG for k in
           ["warn_gap", "critical_gap", "loops"]))


# ================================================================
# Test 2: LifespanInjectStep — 关闭时不注入
# ================================================================
section("Test 2 — LifespanInjectStep 关闭态")
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=False)
ctx = FakeCtx(ch_num=5)
done = done_marker()
LifespanInjectStep(mw).run(ctx, done)
expect("关闭时 prompt 不变", ctx.prompt == "BASE",
       f"prompt 长度={len(ctx.prompt)}")
expect("关闭时 done() 仍被调用", done.box["called"] == 1)
expect("关闭时不动 extras", "lifespan_injected" not in ctx.extras)


# ================================================================
# Test 3: LifespanInjectStep — 开启时注入完整块
# ================================================================
section("Test 3 — LifespanInjectStep 开启态")
mw = FakeMW()
mw.lifespan_ledger = dict(
    DEFAULT_LIFESPAN_LEDGER,
    enabled=True, total_days=8760, used_days=142,
)
ctx = FakeCtx(ch_num=29)
done = done_marker()
LifespanInjectStep(mw).run(ctx, done)
expect("注入了寿元台账块", "寿元台账" in ctx.prompt)
expect("注入了剩余日数", "8618" in ctx.prompt)   # 8760 - 142
expect("注入了施术规则四条", "1." in ctx.prompt and "4." in ctx.prompt)
expect("注入了结算行格式提示", "[寿元结算" in ctx.prompt)
expect("正常状态标记", "✅ 正常" in ctx.prompt)
expect("extras 标记本次注入", ctx.extras.get("lifespan_injected") is True)
expect("extras 记录注入前剩余", ctx.extras.get("lifespan_remaining_before") == 8618)
expect("done() 调用一次", done.box["called"] == 1)


# ================================================================
# Test 4: LifespanInjectStep — 危急阈值标记
# ================================================================
section("Test 4 — LifespanInjectStep 危急/警戒标记")
# 警戒
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=True,
                          total_days=8760, used_days=8500,
                          warn_threshold=365, critical_threshold=30)
ctx = FakeCtx(ch_num=200)
LifespanInjectStep(mw).run(ctx, done_marker())
expect("警戒标记触发（剩余 260 ≤ 365）", "⚠️ 警戒" in ctx.prompt)

# 危急
mw.lifespan_ledger["used_days"] = 8755   # 剩 5 日
ctx = FakeCtx(ch_num=210)
LifespanInjectStep(mw).run(ctx, done_marker())
expect("危急标记触发（剩余 5 ≤ 30）", "🚨 危急" in ctx.prompt)


# ================================================================
# Test 5: LifespanAuditStep — 正则解析章末结算行
# ================================================================
section("Test 5 — LifespanAuditStep 正则解析")
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=True,
                          total_days=8760, used_days=10)
ctx = FakeCtx(ch_num=11)
ctx.content = (
    "陈知行抹掉嘴角的血。" * 50 +
    "\n\n[寿元结算: 折寿 5 日 (主动施术 1 次 + 日落被动 1 日 + 越阶 3 日)]"
)
done = done_marker()
LifespanAuditStep(mw).run(ctx, done)

expect("正则识别折寿 5 日", mw.lifespan_ledger["used_days"] == 15)
expect("history 记录本章", len(mw.lifespan_ledger["history"]) == 1
       and mw.lifespan_ledger["history"][-1]["ch"] == 11
       and mw.lifespan_ledger["history"][-1]["days"] == 5)
expect("done() 同步调用", done.box["called"] == 1)
expect("无危急 issue（剩余 8745）", not ctx.has_issues())


# ================================================================
# Test 6: LifespanAuditStep — 章末无标记 → AI 兜底
# ================================================================
section("Test 6 — LifespanAuditStep AI 兜底")
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=True,
                          total_days=8760, used_days=20, auto_audit=True)
mw._ai_reply = '{"days": 4, "breakdown": "日落 1 + 越阶术 3"}'

ctx = FakeCtx(ch_num=12)
ctx.content = "正文里没有任何结算标记的一段普通战斗描写。" * 30
done = done_marker()
LifespanAuditStep(mw).run(ctx, done)

expect("调用了 _send_to_ai 一次", len(mw._sent_to_ai) == 1)
expect("AI target 以 _cb_ 开头",
       mw._sent_to_ai[0][1] and mw._sent_to_ai[0][1].startswith("_cb_lifespan_audit_"))
expect("AI 返回的 days=4 已入账", mw.lifespan_ledger["used_days"] == 24)
expect("done() 在 AI 回复后调用", done.box["called"] == 1)


# ================================================================
# Test 7: LifespanAuditStep — auto_audit=False + 无标记 → 默认兜底
# ================================================================
section("Test 7 — LifespanAuditStep 关 AI 时走默认兜底")
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=True,
                          total_days=8760, used_days=0,
                          auto_audit=False, default_per_chapter=2)
ctx = FakeCtx(ch_num=1)
ctx.content = "纯回忆章节，无任何施术，也无结算标记。" * 30
done = done_marker()
LifespanAuditStep(mw).run(ctx, done)

expect("默认兜底每章 2 日", mw.lifespan_ledger["used_days"] == 2)
expect("没有触发 AI 调用", len(mw._sent_to_ai) == 0)
expect("done() 同步调用", done.box["called"] == 1)


# ================================================================
# Test 8: LifespanAuditStep — 触及危急阈值 → ctx.issues
# ================================================================
section("Test 8 — LifespanAuditStep 危急阈值")
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=True,
                          total_days=100, used_days=70,
                          critical_threshold=30, auto_audit=False)
ctx = FakeCtx(ch_num=50)
ctx.content = "正文." * 100 + "\n[寿元结算: 折寿 25 日 (说明：连发越阶大术)]"
done = done_marker()
LifespanAuditStep(mw).run(ctx, done)

remaining = 100 - mw.lifespan_ledger["used_days"]
expect(f"扣完后剩余 {remaining} ≤ 危急阈值 30", remaining <= 30)
expect("ctx.issues 非空", ctx.has_issues())
expect("issue 文本含'危急'/'寿元'",
       any("寿元" in s for s in ctx.issues))


# ================================================================
# Test 9: LifespanAuditStep — 关闭时不动
# ================================================================
section("Test 9 — LifespanAuditStep 关闭态")
mw = FakeMW()
mw.lifespan_ledger = dict(DEFAULT_LIFESPAN_LEDGER, enabled=False, used_days=0)
ctx = FakeCtx(ch_num=1)
ctx.content = "[寿元结算: 折寿 100 日 (这条不应被处理)]"
done = done_marker()
LifespanAuditStep(mw).run(ctx, done)
expect("关闭时 used_days 不变", mw.lifespan_ledger["used_days"] == 0)
expect("done() 仍调用", done.box["called"] == 1)


# ================================================================
# Test 10: OpenLoopsCheckStep — 关闭/无伏笔
# ================================================================
section("Test 10 — OpenLoopsCheckStep 早退")
mw = FakeMW()
mw.open_loops = dict(DEFAULT_OPEN_LOOPS_CFG, enabled=False)
ctx = FakeCtx(ch_num=100)
ctx.content = "随便一段."
done = done_marker()
OpenLoopsCheckStep(mw).run(ctx, done)
expect("关闭时 done() 调用", done.box["called"] == 1)
expect("关闭时无 issue", not ctx.has_issues())

mw.open_loops = dict(DEFAULT_OPEN_LOOPS_CFG, enabled=True, loops=[])
ctx2 = FakeCtx(ch_num=100)
done2 = done_marker()
OpenLoopsCheckStep(mw).run(ctx2, done2)
expect("无伏笔时 done() 调用", done2.box["called"] == 1)
expect("无伏笔时无 issue", not ctx2.has_issues())


# ================================================================
# Test 11: OpenLoopsCheckStep — 关键词命中刷新 last_seen
# ================================================================
section("Test 11 — OpenLoopsCheckStep 关键词命中")
mw = FakeMW()
import copy as _c
mw.open_loops = _c.deepcopy(DEFAULT_OPEN_LOOPS_CFG)
mw.open_loops.update(enabled=True, warn_gap=80, critical_gap=150)
LifespanLoopsExtension.add_loop(
    mw, loop_id="f001", desc="父亲真正死因",
    added_ch=3, keyword="父亲",
)
loop = mw.open_loops["loops"][0]
expect("初始 last_seen_ch == added_ch", loop["last_seen_ch"] == 3)

ctx = FakeCtx(ch_num=70)
ctx.content = "他想起父亲临终那夜的一句话，整间义庄都在下雨。" * 5
done = done_marker()
OpenLoopsCheckStep(mw).run(ctx, done)
expect("正文出现关键词后 last_seen_ch 被刷新到 70",
       loop["last_seen_ch"] == 70)
expect("没有 issue（70-3=67 < 80）", not ctx.has_issues())


# ================================================================
# Test 12: OpenLoopsCheckStep — warn / critical 分级
# ================================================================
section("Test 12 — OpenLoopsCheckStep 冻结分级")
mw = FakeMW()
mw.open_loops = _c.deepcopy(DEFAULT_OPEN_LOOPS_CFG)
mw.open_loops.update(enabled=True, warn_gap=80, critical_gap=150)
LifespanLoopsExtension.add_loop(mw, loop_id="A", desc="妹妹咒斑来源",
                                added_ch=10, last_seen_ch=10, keyword="无关词")
LifespanLoopsExtension.add_loop(mw, loop_id="B", desc="补天文书出处",
                                added_ch=20, last_seen_ch=20, keyword="无关词")
LifespanLoopsExtension.add_loop(mw, loop_id="C", desc="天听铃源头",
                                added_ch=30, last_seen_ch=30, keyword="无关词")

# A: 100-10 = 90  → warn
# B: 100-20 = 80  → warn (=80 算 warn)
# C: 100-30 = 70  → 不动
ctx = FakeCtx(ch_num=100)
ctx.content = "本章正文与上述关键词都不相关。" * 50
OpenLoopsCheckStep(mw).run(ctx, done_marker())
warn_logs = [m for m, lv in mw.tab_generation.logs if "长期冻结" in m]
expect("两条 warn 日志（A 90 章 / B 80 章）", len(warn_logs) == 2,
       f"实际 {len(warn_logs)} 条: {warn_logs}")
expect("warn 阶段不进 issues", not ctx.has_issues())

# 进一步推到 critical
mw.tab_generation.logs.clear()
ctx2 = FakeCtx(ch_num=200)   # 与 A 差 190 ≥ 150
ctx2.content = "继续不相关的内容。" * 50
OpenLoopsCheckStep(mw).run(ctx2, done_marker())
crit_logs = [m for m, lv in mw.tab_generation.logs if "重度冻结" in m]
expect("3 条 critical 日志（全部 ≥ 150）", len(crit_logs) == 3,
       f"实际 {len(crit_logs)} 条")
expect("3 个 critical issue", len(ctx2.issues) == 3)


# ================================================================
# Test 13: OpenLoopsCheckStep — closed 状态被跳过
# ================================================================
section("Test 13 — OpenLoopsCheckStep closed 状态")
mw = FakeMW()
mw.open_loops = _c.deepcopy(DEFAULT_OPEN_LOOPS_CFG)
mw.open_loops["enabled"] = True
LifespanLoopsExtension.add_loop(mw, loop_id="X", desc="已经收的坑",
                                added_ch=1, last_seen_ch=1, keyword="x")
LifespanLoopsExtension.close_loop(mw, "X", ch_num=50)

ctx = FakeCtx(ch_num=300)
ctx.content = "无关内容." * 30
OpenLoopsCheckStep(mw).run(ctx, done_marker())
expect("closed 伏笔不出现在日志里",
       not any("已经收的坑" in m for m, _ in mw.tab_generation.logs))
expect("closed 伏笔不进 issues",
       not any("已经收的坑" in s for s in ctx.issues))


# ================================================================
# Test 14: LifespanLoopsExtension.install — 注册三步至 workflow
# ================================================================
section("Test 14 — install() 注册到 workflow")
mw = FakeMW()
ok = LifespanLoopsExtension.install(mw)
expect("install 返回 True", ok is True)
expect("mw.lifespan_ledger 已初始化", isinstance(mw.lifespan_ledger, dict))
expect("mw.open_loops 已初始化", isinstance(mw.open_loops, dict))

pre_steps = mw.workflow._registry.get("pre_write")
post_steps = mw.workflow._registry.get("post_write")
pre_names = [s.name for s in pre_steps]
post_names = [s.name for s in post_steps]
expect("pre_write 含 lifespan_inject", "lifespan_inject" in pre_names)
expect("post_write 含 lifespan_audit", "lifespan_audit" in post_names)
expect("post_write 含 open_loops_check", "open_loops_check" in post_names)


# ================================================================
# Test 15: install — 选择性注册（只装伏笔检查）
# ================================================================
section("Test 15 — install 选择性注册")
mw = FakeMW()
LifespanLoopsExtension.install(mw, lifespan=False, open_loops=True)
post_names = [s.name for s in mw.workflow._registry.get("post_write")]
expect("不含 lifespan_audit", "lifespan_audit" not in post_names)
expect("含 open_loops_check", "open_loops_check" in post_names)


# ================================================================
# Test 16: install — workflow 不存在时返回 False
# ================================================================
section("Test 16 — install 无 workflow 时优雅降级")
mw = FakeMW()
mw.workflow = None
ok = LifespanLoopsExtension.install(mw)
expect("install 返回 False", ok is False)
# 数据初始化仍然成功（即使没注册）
expect("数据初始化仍然完成", isinstance(mw.lifespan_ledger, dict))


# ================================================================
# Test 17: serialize / deserialize round-trip
# ================================================================
section("Test 17 — 存档 round-trip")
mw = FakeMW()
LifespanLoopsExtension.install(mw)
mw.lifespan_ledger.update({
    "enabled": True, "total_days": 10000, "used_days": 250,
    "history": [{"ch": 1, "days": 1, "note": "日落"},
                {"ch": 2, "days": 5, "note": "越阶"}],
})
LifespanLoopsExtension.add_loop(mw, loop_id="P", desc="天漏由谁维持",
                                added_ch=2, last_seen_ch=2, keyword="天漏")
mw.open_loops["enabled"] = True

# round-trip 模拟存档
data = LifespanLoopsExtension.serialize(mw)
text = json.dumps(data, ensure_ascii=False)
restored = json.loads(text)

mw2 = FakeMW()
LifespanLoopsExtension.install(mw2)
LifespanLoopsExtension.deserialize(mw2, restored)

expect("total_days 还原", mw2.lifespan_ledger["total_days"] == 10000)
expect("used_days 还原", mw2.lifespan_ledger["used_days"] == 250)
expect("history 长度还原", len(mw2.lifespan_ledger["history"]) == 2)
expect("history[1] 内容还原",
       mw2.lifespan_ledger["history"][1]["days"] == 5)
expect("open_loops.enabled 还原", mw2.open_loops["enabled"] is True)
expect("loop 数量还原", len(mw2.open_loops["loops"]) == 1)
expect("loop 字段补全（status / keyword）",
       mw2.open_loops["loops"][0].get("status") == "open"
       and mw2.open_loops["loops"][0].get("keyword") == "天漏")


# ================================================================
# Test 18: reset_lifespan / close_loop 操作
# ================================================================
section("Test 18 — reset_lifespan / close_loop")
mw = FakeMW()
LifespanLoopsExtension.install(mw)
mw.lifespan_ledger["used_days"] = 100
mw.lifespan_ledger["history"] = [{"ch": 1, "days": 100, "note": "测"}]
LifespanLoopsExtension.reset_lifespan(mw, total_days=20000)
expect("reset 后 total_days = 20000", mw.lifespan_ledger["total_days"] == 20000)
expect("reset 后 used_days = 0", mw.lifespan_ledger["used_days"] == 0)
expect("reset 后 history 清空", mw.lifespan_ledger["history"] == [])

LifespanLoopsExtension.add_loop(mw, loop_id="Q", desc="谁是上宗", added_ch=10)
ok = LifespanLoopsExtension.close_loop(mw, "Q", ch_num=99)
expect("close_loop 返回 True", ok)
expect("closed 状态写入", mw.open_loops["loops"][0]["status"] == "closed")
expect("close_loop 不存在 ID 时返回 False",
       LifespanLoopsExtension.close_loop(mw, "NOT_EXIST", 1) is False)


# ================================================================
# 汇总
# ================================================================
print()
print("=" * 64)
total = len(results)
passed = sum(1 for _n, ok, _ in results if ok)
failed = total - passed
print(f"测试总数: {total}   通过: {passed}   失败: {failed}")
print("=" * 64)

if failed:
    print("失败明细：")
    for n, ok, msg in results:
        if not ok:
            print(f"  ✗ {n}" + (f" — {msg}" if msg else ""))
    sys.exit(1)
else:
    print("✅ 全部通过")
    sys.exit(0)
