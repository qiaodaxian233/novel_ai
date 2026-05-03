"""离线 mock 测试:实例化所有 Tab,模拟 Worker,跑一遍核心流程"""
import os, sys
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '/home/claude')

import importlib.util
spec = importlib.util.spec_from_file_location('novel_ai_v6', '/home/claude/novel_ai_v6.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
import json, re

app = QApplication.instance() or QApplication(sys.argv)

# ============ Test 1: instantiate MainWindow ============
print("=" * 60)
print("Test 1: 实例化整个 MainWindow")
print("=" * 60)
mw = mod.MainWindow()
print(f"✓ MainWindow ok, tabs count: {mw.tabs.count()}")
for i in range(mw.tabs.count()):
    print(f"   Tab {i}: {mw.tabs.tabText(i)}")
expected_tabs = ['创作设置', '故事大纲', '对话记忆', 'Canon 设定', '技能库', '生成控制', '章节编辑器', '小说封面生成']
actual_tabs = [mw.tabs.tabText(i) for i in range(mw.tabs.count())]
assert actual_tabs == expected_tabs, f"Tab 顺序错误: {actual_tabs}"
print("✓ Tab 顺序正确")

# ============ Test 2: Canon 解析/序列化 ============
print()
print("=" * 60)
print("Test 2: Canon 解析 / 序列化")
print("=" * 60)
mw.tab_canon.canon_edit.setPlainText(
    "[L][H] 林晚晚.年龄 = 25 (ch1)\n"
    "[L][H] 玉佩 = 男主祖母传给男主 (ch3)\n"
    "[E][M] 顾砚深.修为 = 金丹中期 (ch7)\n"
    "[L][H] 女主双重身份 = 未被识破 (ch1)\n"
    "# 这是注释,会被忽略\n"
    "garbled line that doesn't match\n"
)
items = mw.tab_canon.parse()
print(f"✓ 解析出 {len(items)} 条")
assert len(items) == 4, f"应该是 4 条,实际 {len(items)}"
for it in items:
    print(f"  - [{it['mode'][:1]}/{it['severity'][:1]}] {it['key']} = {it['value']} (ch{it['ch']})")

locked = mw.tab_canon.serialize_locked()
evolving = mw.tab_canon.serialize_evolving()
print(f"✓ locked 序列化:{len(locked)} 字符")
print(f"✓ evolving 序列化:{len(evolving)} 字符")
assert "林晚晚.年龄" in locked
assert "顾砚深.修为" in evolving

# add_item 自动去重
mw.tab_canon.add_item("林晚晚.年龄", "26", mode="locked", severity="high", ch=50)
items2 = mw.tab_canon.parse()
assert len(items2) == 4, "add_item 应该更新而不是新增"
new_age = next(it for it in items2 if it["key"] == "林晚晚.年龄")
assert new_age["value"] == "26", f"年龄应该被更新到 26,实际 {new_age['value']}"
print("✓ add_item 去重 OK(键相同→更新)")

# 添加新条目
mw.tab_canon.add_item("林晚晚.姐姐", "林初晚", mode="locked", severity="high", ch=12)
items3 = mw.tab_canon.parse()
assert len(items3) == 5
print(f"✓ 添加新键 → 共 {len(items3)} 条")

# 序列化 → 反序列化 round-trip
saved = mw.tab_canon.serialize_for_save()
new_canon = mod.CanonGuard()
new_canon.load_from_dict(saved)
restored = new_canon.parse()
assert len(restored) == len(items3), f"round-trip 失败:{len(restored)} vs {len(items3)}"
print("✓ Canon round-trip(序列化 → 反序列化)OK")

# ============ Test 3: _build_canon_block 注入块 ============
print()
print("=" * 60)
print("Test 3: _build_canon_block 注入块")
print("=" * 60)
block = mw._build_canon_block()
assert "Canon" in block
assert "锁定项" in block
assert "演化项" in block
assert "林晚晚.年龄" in block
print(f"✓ 生成的注入块({len(block)} 字符):")
for line in block.split("\n")[:10]:
    print(f"   {line}")
print("   ...")

# 关闭注入开关 → 注入块为空
mw.tab_canon.chk_inject.setChecked(False)
# Note: chk_inject 是给 _send_next_chapter 看的,不影响 _build_canon_block 本身
# 这里测试的是 _build_canon_block 在 canon 内容被清空时返回空字符串
mw.tab_canon.canon_edit.clear()
empty_block = mw._build_canon_block()
assert empty_block == "", f"空设定档应返回空字符串,实际 '{empty_block}'"
print("✓ 空 Canon → 注入块为空")

# 恢复
mw.tab_canon.chk_inject.setChecked(True)
mw.tab_canon.canon_edit.setPlainText(
    "[L][H] 林晚晚.年龄 = 25 (ch1)\n"
    "[L][H] 女主双重身份 = 未被识破 (ch1)\n"
)

# ============ Test 4: _check_chapter_quality(无 AI 调用部分)============
print()
print("=" * 60)
print("Test 4: _check_chapter_quality (字数 + 章末钩子)")
print("=" * 60)
mw.tab_generation.chk_crit_words.setChecked(True)
mw.tab_generation.chk_crit_hook.setChecked(True)
# 关掉 AI 维度,这样 need_ai_audit 才是 False
mw.tab_generation.chk_crit_canon.setChecked(False)
mw.tab_generation.chk_crit_rhythm.setChecked(False)
mw.tab_generation.chk_crit_char.setChecked(False)

# 4a. 字数不达标
short = "短章节" * 100  # 约 300 字
issues, need_ai = mw._check_chapter_quality(short, target_words=3000, min_words=2550)
print(f"  字数=300, 目标=3000, min=2550 → issues={len(issues)} need_ai={need_ai}")
assert any("字数" in i for i in issues)
assert any("钩子" in i for i in issues)  # 也没钩子
print(f"  ✓ 检测到字数 + 钩子两个问题")

# 4b. 字数达标但无钩子
no_hook = "这" * 3000
issues, _ = mw._check_chapter_quality(no_hook, target_words=3000, min_words=2550)
assert not any("字数" in i for i in issues), f"字数应通过: {issues}"
assert any("钩子" in i for i in issues), f"应检出钩子缺失: {issues}"
print(f"  ✓ 字数达标但无钩子 → 仅 1 个问题")

# 4c. 字数 + 钩子都达标
good = "这" * 2999 + "?"
issues, _ = mw._check_chapter_quality(good, target_words=3000, min_words=2550)
print(f"  字数 3000 + 末尾问号 → issues={issues}")
assert len(issues) == 0, f"应零问题: {issues}"
print(f"  ✓ 双达标 → 零问题")

# 4d. 包含「然而」转折词在尾段
twist = "这" * 2999 + "然而事情没那么简单"
issues, _ = mw._check_chapter_quality(twist, target_words=3000, min_words=2550)
assert len(issues) == 0, f"应通过: {issues}"
print(f"  ✓ 末尾「然而」转折词 → 通过钩子检测")

# 4e. 关闭字数维度 → 只看钩子
mw.tab_generation.chk_crit_words.setChecked(False)
issues, _ = mw._check_chapter_quality(short, target_words=3000, min_words=2550)
assert not any("字数" in i for i in issues)
assert any("钩子" in i for i in issues)
print(f"  ✓ 关闭字数维度 → 只检章末钩子")
mw.tab_generation.chk_crit_words.setChecked(True)

# ============ Test 5: _extract_json_blob ============
print()
print("=" * 60)
print("Test 5: _extract_json_blob (AI 回复 JSON 提取)")
print("=" * 60)

cases = [
    ('好的,我已分析:\n```json\n{"violated": false, "items": []}\n```\n这章没问题。',
     {"violated": False, "items": []}),
    ('{"violated": true, "items": [{"severity":"high","desc":"年龄矛盾"}]}',
     {"violated": True, "items": [{"severity": "high", "desc": "年龄矛盾"}]}),
    ('稽核结果:```\n{"score": 7, "reason": "节奏适中"}\n```',
     {"score": 7, "reason": "节奏适中"}),
    ('[{"key":"林晚晚.年龄","value":"25","mode":"locked","ch":1}]',
     [{"key": "林晚晚.年龄", "value": "25", "mode": "locked", "ch": 1}]),
    ('我提取到以下:\n[{"key":"X","value":"Y","mode":"evolving"}]\n以上。',
     [{"key": "X", "value": "Y", "mode": "evolving"}]),
]
for raw, expected in cases:
    extracted = mw._extract_json_blob(raw)
    parsed = json.loads(extracted)
    assert parsed == expected, f"提取错误!\n输入: {raw}\n提取: {extracted}\n期望: {expected}"
    print(f"  ✓ 提取 OK: {extracted[:60]}...")

# ============ Test 6: 模拟一次完整的章节生成流程(mock worker)============
print()
print("=" * 60)
print("Test 6: 完整章节生成流程(mock worker)")
print("=" * 60)

# Mock 掉 worker.submit 和 worker.is_ready,捕获所有任务投递
submitted_tasks = []
mw.worker.submit = lambda t: submitted_tasks.append(t)
mw.worker.is_ready = lambda: True
# Mock QTimer.singleShot 为同步调用,这样链式触发立刻发生
QTimer.singleShot = staticmethod(lambda ms, fn: fn())
# 关掉自动保存 TXT(避免在测试中真写文件)
mw.tab_generation.auto_save.setChecked(False)
# 关掉所有需要 AI 的稽核维度,简化路径
mw.tab_generation.chk_crit_canon.setChecked(False)
mw.tab_generation.chk_crit_rhythm.setChecked(False)
mw.tab_generation.chk_crit_char.setChecked(False)
# 关掉摘要,简化路径
mw.tab_memory.auto_summarize.setChecked(False)
# 关掉 canon 抽取,简化路径
mw.tab_canon.chk_extract.setChecked(False)

# 模拟:用户开始生成 1 章
mw._batch_remaining = 1
mw._batch_paused = False
mw._batch_target = 1

# 直接 mock 一个 chapter 任务回应
meta = {
    "target": "chapter",
    "ch_num": 1,
    "target_words": 3000,
    "min_words": 2550,
    "retry_left": 3,
    "label": "第 1 章",
    "original_prompt": "原始提示词",
}
mw._pending_task_target = meta

# 6a. 先发一个字数达标 + 末尾有钩子的内容 → 应该接受 + 入库
print(f"\n  6a. 字数达标 + 钩子达标 → 应该入库")
chapter_count_before = len(mw.chapters)
good_chapter = "第1章 烤串西施\n\n" + ("这" * 3000) + "?"
mw._on_response_received("test-1", good_chapter)
assert len(mw.chapters) == chapter_count_before + 1, f"应该 +1 章,现在 {len(mw.chapters)}"
ch = mw.chapters[-1]
print(f"  ✓ 已入库:{ch['title']!r},字数 {len(ch['content'])}")

# 6b. 字数不达标 → 应该死磕重写(submit 再来一次)
print(f"\n  6b. 字数不达标 → 应该死磕重写,任务被重新 submit")
submitted_tasks.clear()
mw._batch_remaining = 1
mw._pending_task_target = {
    "target": "chapter",
    "ch_num": 2,
    "target_words": 3000,
    "min_words": 2550,
    "retry_left": 2,
    "label": "第 2 章",
    "original_prompt": "原始提示词",
}
short_chapter = "第2章 短\n\n" + ("这" * 100) + "?"
chapter_count_before = len(mw.chapters)
mw._on_response_received("test-2", short_chapter)
assert len(mw.chapters) == chapter_count_before, f"不应入库,现在 {len(mw.chapters)}"
assert len(submitted_tasks) == 1, f"应该死磕重写一次,实际 submit 了 {len(submitted_tasks)} 次"
retry_prompt = submitted_tasks[0].get("prompt", "")
assert "上次问题清单" in retry_prompt, f"重写 prompt 应含问题清单"
assert "字数" in retry_prompt, "重写 prompt 应含字数问题"
print(f"  ✓ 死磕重写已 submit,prompt 含强化要求({len(retry_prompt)} 字符)")
print(f"  ✓ retry_left 剩余: {mw._pending_task_target.get('retry_left')}")

# 6c. 死磕用尽 → 接受垃圾内容
print(f"\n  6c. 死磕用尽 → 接受不达标内容")
submitted_tasks.clear()
mw._batch_remaining = 1
mw._pending_task_target = {
    "target": "chapter",
    "ch_num": 3,
    "target_words": 3000,
    "min_words": 2550,
    "retry_left": 0,  # 死磕用尽
    "label": "第 3 章",
    "original_prompt": "原始提示词",
}
chapter_count_before = len(mw.chapters)
mw._on_response_received("test-3", short_chapter)
# retry_left=0 时应入库,不再 submit
assert len(mw.chapters) == chapter_count_before + 1, f"应入库,现在 {len(mw.chapters)}"
assert len(submitted_tasks) == 0, "死磕用尽时不应再 submit"
print(f"  ✓ 死磕用尽 → 接受并入库")

# ============ Test 7: 技能解析 ============
print()
print("=" * 60)
print("Test 7: 技能配置 + 出厂技能")
print("=" * 60)
print(f"✓ 出厂技能数量: {len(mw.tab_skills.skills)}")
for s in mw.tab_skills.skills:
    print(f"  - {s['name']:8} | when={s['when']:30} | target={s['target']:25} | enabled={s['enabled']}")

manual = mw.tab_skills.get_manual_skills()
after = mw.tab_skills.get_after_chapter_skills()
print(f"✓ manual 技能: {[s['name'] for s in manual]}")
print(f"✓ after_chapter 技能: {[s['name'] for s in after]}")

# ============ Test 8: 项目 JSON 序列化 round-trip ============
print()
print("=" * 60)
print("Test 8: 项目 JSON save/load round-trip")
print("=" * 60)

# 准备一些数据
mw.tab_settings.title_input.setText("测试小说")
mw.tab_canon.canon_edit.setPlainText(
    "[L][H] 林晚晚.年龄 = 25 (ch1)\n"
    "[E][M] 顾砚深.修为 = 金丹中期 (ch7)\n"
)
# 给 skill 加一条
mw.tab_skills.skills.append({
    "name": "自定义技能",
    "when": "manual",
    "trigger_pattern": "",
    "prompt": "测试 prompt {content}",
    "target": "log_only",
    "enabled": True,
})

# Mock save_project 直接序列化(不弹文件框)
import io
saved_dict = {
    "title": mw.tab_settings.get_title(),
    "chapters": mw.chapters,
    "memory": {
        "characters": mw.tab_memory.chars_edit.toPlainText(),
        "summaries": mw.tab_memory.summaries_edit.toPlainText(),
        "long_term": mw.tab_memory.long_term_edit.toPlainText(),
        "auto_summarize": mw.tab_memory.auto_summarize.isChecked(),
        "auto_inject": mw.tab_memory.auto_inject.isChecked(),
        "recent_n": mw.tab_memory.recent_n.value(),
        "summary_len": mw.tab_memory.summary_len.value(),
    },
    "canon": mw.tab_canon.serialize_for_save(),
    "skills": mw.tab_skills.serialize_for_save(),
    "critique": mw.tab_generation.critique_config(),
}
print(f"✓ 序列化完成,共 {len(json.dumps(saved_dict, ensure_ascii=False))} 字符")
print(f"   canon items: {len(saved_dict['canon']['items'])}")
print(f"   skills count: {len(saved_dict['skills']['skills'])}")
print(f"   critique config: {saved_dict['critique']}")

# 反序列化到新 MainWindow
mw2 = mod.MainWindow()
mw2.tab_canon.load_from_dict(saved_dict["canon"])
mw2.tab_skills.load_from_dict(saved_dict["skills"])
crit = saved_dict["critique"]
mw2.tab_generation.chk_crit_words.setChecked(crit.get("word_count", True))
mw2.tab_generation.chk_crit_hook.setChecked(crit.get("hook", True))
mw2.tab_generation.chk_crit_canon.setChecked(crit.get("canon", True))
mw2.tab_generation.chk_crit_rhythm.setChecked(crit.get("rhythm", False))
mw2.tab_generation.chk_crit_char.setChecked(crit.get("character", False))

# 验证
restored_canon = mw2.tab_canon.parse()
assert len(restored_canon) == 2, f"canon 还原失败:{len(restored_canon)} 条"
print(f"✓ canon 还原:{len(restored_canon)} 条")
restored_skills = mw2.tab_skills.skills
assert any(s["name"] == "自定义技能" for s in restored_skills), "自定义技能丢失"
print(f"✓ skills 还原:{len(restored_skills)} 个,含自定义技能")
restored_crit = mw2.tab_generation.critique_config()
assert restored_crit == crit, f"critique 配置错位:{restored_crit} vs {crit}"
print(f"✓ critique 配置还原:{restored_crit}")

print()
print("=" * 60)
print("✅ 所有 8 项测试全部通过")
print("=" * 60)

# ============================================================
# Test 9: auto_match 技能触发
# ============================================================
print()
print("=" * 60)
print("Test 9: auto_match 技能触发逻辑")
print("=" * 60)

# 添加一个 auto_match 技能
mw.tab_skills.skills.append({
    "name": "战斗检测",
    "when": "auto_match",
    "trigger_pattern": "战斗|出招|厮杀",
    "prompt": "扩写战斗: {content}",
    "target": "log_only",
    "enabled": True,
})
mw.tab_skills.skills.append({
    "name": "情感检测",
    "when": "auto_match",
    "trigger_pattern": "泪水|哭泣|心痛",
    "prompt": "扩写情感: {content}",
    "target": "log_only",
    "enabled": True,
})
mw.tab_skills.skills.append({
    "name": "坏正则",
    "when": "auto_match",
    "trigger_pattern": "[坏正则(",  # 故意写错
    "prompt": "xxx {content}",
    "target": "log_only",
    "enabled": True,
})

# 9a. 命中一个
content_battle = "两人在旷野上展开了激烈的战斗,招招见血,不死不休。"
matched = mw.tab_skills.get_auto_match_skills(content_battle)
assert len(matched) == 1, f"应命中 1 个战斗技能,实际 {len(matched)}"
assert matched[0]["name"] == "战斗检测"
print(f"  ✓ 战斗内容命中 1 个技能:「{matched[0]['name']}」")

# 9b. 命中另一个
content_emotion = "她的泪水滑落,心痛难耐。"
matched2 = mw.tab_skills.get_auto_match_skills(content_emotion)
assert len(matched2) == 1 and matched2[0]["name"] == "情感检测"
print(f"  ✓ 情感内容命中 1 个技能:「{matched2[0]['name']}」")

# 9c. 两个都命中
content_both = "泪水模糊了她的双眼,他却已出招,一场战斗就此开始。"
matched3 = mw.tab_skills.get_auto_match_skills(content_both)
assert len(matched3) == 2
print(f"  ✓ 复合内容命中 2 个技能:{[s['name'] for s in matched3]}")

# 9d. 都不命中
content_none = "她静静地坐在窗前,看着远处的山。"
matched4 = mw.tab_skills.get_auto_match_skills(content_none)
assert len(matched4) == 0
print(f"  ✓ 无战斗/情感 → 命中 0 个")

# 9e. 坏正则不崩溃
try:
    result = mw.tab_skills.get_auto_match_skills("随便什么内容")
    print(f"  ✓ 坏正则不崩溃,正常返回 {len(result)} 个结果")
except Exception as e:
    assert False, f"坏正则导致崩溃:{e}"

# 9f. trigger_pattern 为空的 auto_match 技能不触发
mw.tab_skills.skills.append({
    "name": "空触发词",
    "when": "auto_match",
    "trigger_pattern": "",  # 空 → 不应触发
    "prompt": "xxx {content}",
    "target": "log_only",
    "enabled": True,
})
matched5 = mw.tab_skills.get_auto_match_skills("任何内容都不应触发这个")
names5 = [s["name"] for s in matched5]
assert "空触发词" not in names5
print(f"  ✓ trigger_pattern 为空的技能不自动触发")

# 9g. disabled 技能不触发
mw.tab_skills.skills.append({
    "name": "已禁用战斗",
    "when": "auto_match",
    "trigger_pattern": "战斗",
    "prompt": "xxx {content}",
    "target": "log_only",
    "enabled": False,  # 禁用
})
matched6 = mw.tab_skills.get_auto_match_skills("战斗开始了")
names6 = [s["name"] for s in matched6]
assert "已禁用战斗" not in names6
print(f"  ✓ disabled 技能不触发")

# ============================================================
# Test 10: workflow_pipeline PipelineContext + Step 单元测试
# ============================================================
print()
print("=" * 60)
print("Test 10: workflow_pipeline 模块单元测试")
print("=" * 60)

from workflow_pipeline import (
    PipelineContext, WordCountStep, HookCheckStep,
    StepRegistry, PipelineStep, GenerationWorkflow,
)

# 10a. PipelineContext.append_prompt 追加不改 original_prompt
ctx = PipelineContext("base_prompt", ch_num=1, target_words=3000,
                      min_words=2550, retry_left=3)
ctx.append_prompt("【记忆块】角色A")
ctx.append_prompt("【Canon约束】锁定项X")
assert "【记忆块】" in ctx.prompt
assert "【Canon约束】" in ctx.prompt
assert ctx.original_prompt == "base_prompt"  # 不能被污染
print("  ✓ append_prompt 追加正确,original_prompt 不变")

# 10b. WordCountStep — 字数不足
class _FakeMW_words:
    class tab_generation:
        @staticmethod
        def critique_config(): return {"word_count": True}

ctx2 = PipelineContext("p", 1, 3000, 2550, 3)
ctx2.content = "字" * 100  # 100字,低于2550
step_wc = WordCountStep(_FakeMW_words())
done_called = []
step_wc.run(ctx2, lambda: done_called.append(1))
assert len(done_called) == 1, "done() 必须被调用"
assert ctx2.has_issues()
assert "字数不达标" in ctx2.issues[0]
print("  ✓ WordCountStep:字数不足 → issues 非空,done() 被调用")

# 10c. WordCountStep — 字数达标
ctx3 = PipelineContext("p", 1, 3000, 2550, 3)
ctx3.content = "达标内容" * 700  # ~2800字
step_wc2 = WordCountStep(_FakeMW_words())
step_wc2.run(ctx3, lambda: None)
assert not ctx3.has_issues()
print("  ✓ WordCountStep:字数达标 → issues 为空")

# 10d. HookCheckStep — 有钩子通过
class _FakeMW_hook:
    class tab_generation:
        @staticmethod
        def critique_config(): return {"hook": True}

ctx4 = PipelineContext("p", 1, 3000, 2550, 3)
ctx4.content = "正文" * 200 + "他突然意识到了什么……"
step_hk = HookCheckStep(_FakeMW_hook())
step_hk.run(ctx4, lambda: None)
assert not ctx4.has_issues(), f"有钩子不应有 issues: {ctx4.issues}"
print("  ✓ HookCheckStep:含省略号 → 通过")

# 10e. HookCheckStep — 无钩子失败
ctx5 = PipelineContext("p", 1, 3000, 2550, 3)
ctx5.content = "平淡的结尾,没有任何悬念。" * 50
step_hk2 = HookCheckStep(_FakeMW_hook())
step_hk2.run(ctx5, lambda: None)
assert ctx5.has_issues()
assert "章末缺少钩子" in ctx5.issues[0]
print("  ✓ HookCheckStep:无钩子 → issues 非空")

# 10f. StepRegistry 按 priority 排序
registry = StepRegistry()
class StepA(PipelineStep):
    name = "a"
class StepB(PipelineStep):
    name = "b"
class StepC(PipelineStep):
    name = "c"
registry.register("post_write", StepC(), priority=30)
registry.register("post_write", StepA(), priority=10)
registry.register("post_write", StepB(), priority=20)
names = [s.name for s in registry.get("post_write")]
assert names == ["a", "b", "c"], f"排序错误:{names}"
print("  ✓ StepRegistry:priority 排序正确 (a=10 b=20 c=30)")

# 10g. StepRegistry 未知 phase 报错
try:
    registry.register("nonexistent_phase", StepA())
    assert False, "应抛出 ValueError"
except ValueError:
    print("  ✓ StepRegistry:未知 phase 正确抛出 ValueError")

# 10h. workflow 被实例化且 setup_default_steps 注册了步骤
assert mw.workflow is not None, "workflow 应已实例化"
pre = mw.workflow._registry.get("pre_write")
post = mw.workflow._registry.get("post_write")
assert len(pre) >= 3, f"pre_write 步骤不足:{len(pre)}"
assert len(post) >= 5, f"post_write 步骤不足:{len(post)}"
pre_names = [s.name for s in pre]
post_names = [s.name for s in post]
assert "memory_inject" in pre_names
assert "canon_inject" in pre_names
assert "word_count" in post_names
assert "hook_check" in post_names
assert "canon_audit" in post_names
print(f"  ✓ workflow.setup_default_steps(): pre={pre_names} post={post_names}")

# 10i. 自定义 Step 可动态注册
class TestCustomStep(PipelineStep):
    name = "custom_test"
    fired = False
    def run(self, ctx, done):
        TestCustomStep.fired = True
        done()

custom = TestCustomStep()
mw.workflow._registry.register("post_write", custom, priority=99)
post_after = mw.workflow._registry.get("post_write")
assert any(s.name == "custom_test" for s in post_after)
print(f"  ✓ 动态注册自定义 Step 成功,post_write 现共 {len(post_after)} 步")

print()
print("=" * 60)
print("✅ 所有 10 项测试全部通过")
print("=" * 60)

# ============================================================
# Test 11: 对话槽管理 + 记忆恢复提示词
# ============================================================
print()
print("=" * 60)
print("Test 11: 对话槽管理 + 记忆恢复提示词")
print("=" * 60)

sw = mw.tab_generation.conv_switcher

# 11a. 添加槽
idx1 = sw.add_slot("DeepSeek主线#1",
                   "https://chat.deepseek.com/a/chat/s001",
                   ai_site="DeepSeek", chapter_at=10)
idx2 = sw.add_slot("豆包备用",
                   "https://www.doubao.com/chat/c002",
                   ai_site="豆包", chapter_at=10)
assert len(sw.slots) == 2
print(f"  ✓ 添加 2 个槽,共 {len(sw.slots)} 个")

# 11b. 同名更新
sw.add_slot("DeepSeek主线#1",
            "https://chat.deepseek.com/a/chat/s001_new",
            ai_site="DeepSeek", chapter_at=11)
assert len(sw.slots) == 2
assert sw.slots[0]["url"].endswith("s001_new")
print(f"  ✓ 同名槽更新 URL,总数不变")

# 11c. 设置活跃槽
sw.set_active(0)
assert sw._active_slot_idx == 0
assert "DeepSeek主线#1" in sw.active_label.text()
print(f"  ✓ set_active(0) → active_label=「{sw.active_label.text()}」")

# 11d. get_selected_slot 返回当前选中
sw.slot_list.setCurrentRow(1)
sel = sw.get_selected_slot()
assert sel is not None and sel["name"] == "豆包备用"
print(f"  ✓ get_selected_slot → 「{sel['name']}」")

# 11e. 删除槽
sw.slot_list.setCurrentRow(1)
sw._on_del()
assert len(sw.slots) == 1
print(f"  ✓ 删除槽后剩 {len(sw.slots)} 个")

# 11f. 序列化 round-trip
sw.add_slot("新槽B", "https://example.com/chat/b", chapter_at=20)
saved = sw.serialize_for_save()
sw2 = mw2.tab_generation.conv_switcher
sw2.load_from_dict(saved)
assert len(sw2.slots) == len(sw.slots)
assert sw2.slots[0]["name"] == sw.slots[0]["name"]
print(f"  ✓ 对话槽 round-trip:还原 {len(sw2.slots)} 个槽")

# 11g. _build_context_restore_prompt 包含书名/进度/角色/摘要
mw.tab_settings.title_input.setText("测试书名")
mw.tab_memory.chars_edit.setPlainText("【林晚晚】25岁,主角,双重身份")
mw.tab_memory.summaries_edit.setPlainText(
    "第1章 :: 开局相遇\n第2章 :: 初次冲突")
mw.tab_memory.long_term_edit.setPlainText("玉佩:祖母传给男主")
prompt = mw._build_context_restore_prompt()
assert "测试书名" in prompt, "书名应在恢复提示词里"
assert "林晚晚" in prompt, "角色档案应在恢复提示词里"
assert "第1章" in prompt or "第2章" in prompt, "章节摘要应在恢复提示词里"
assert "玉佩" in prompt, "长期记忆应在恢复提示词里"
assert "已了解" in prompt, "恢复提示词末尾应有确认请求"
print(f"  ✓ _build_context_restore_prompt 生成正常 ({len(prompt)} 字符)")
print(f"    包含:书名 ✓  角色 ✓  摘要 ✓  长期记忆 ✓  确认请求 ✓")

print()
print("=" * 60)
print("✅ 所有 11 项测试全部通过")
print("=" * 60)
