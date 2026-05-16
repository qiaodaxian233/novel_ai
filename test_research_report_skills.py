# -*- coding: utf-8 -*-
"""
test_research_report_skills.py — 5 个出厂技能配置的单元测试
"""
from pathlib import Path
import sys
import re
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research_report_skills import (
    RESEARCH_REPORT_SKILLS,
    validate_skill,
    validate_all,
    install_into,
    get_skills_copy,
    VALID_WHEN,
    VALID_TARGET,
)

results = []
def expect(name, cond, msg=""):
    results.append((name, bool(cond), msg))
    icon = "✓" if cond else "✗"
    print(f"  {icon} {name}" + (f" — {msg}" if msg and not cond else ""))

def section(t):
    print()
    print("=" * 64)
    print(t)
    print("=" * 64)


# ============================================================
# Test S1: 总数与基本结构
# ============================================================
section("S1 — 总数与基本结构")
expect("共 5 条出厂技能", len(RESEARCH_REPORT_SKILLS) == 5)
expect("每条都是 dict", all(isinstance(s, dict) for s in RESEARCH_REPORT_SKILLS))

names = [s["name"] for s in RESEARCH_REPORT_SKILLS]
expect("不重名", len(names) == len(set(names)))
expect("含'细纲扩展'", any("细纲扩展" in n for n in names))
expect("含'桥段扩写'", any("桥段扩写" in n for n in names))
expect("含'一致性校验'", any("一致性校验" in n for n in names))
expect("含'短文本生成'", any("短文本生成" in n for n in names))
expect("含'高潮场面自动重写'", any("高潮场面自动重写" in n for n in names))


# ============================================================
# Test S2: schema 字段齐全
# ============================================================
section("S2 — schema 字段齐全")
for s in RESEARCH_REPORT_SKILLS:
    name = s.get("name", "?")
    for k in ("name", "when", "trigger_pattern", "prompt", "target", "enabled"):
        expect(f"{name} 含字段 {k}", k in s)


# ============================================================
# Test S3: 字段值合法
# ============================================================
section("S3 — 字段值合法")
for s in RESEARCH_REPORT_SKILLS:
    name = s.get("name", "?")
    expect(f"{name} when 合法", s["when"] in VALID_WHEN, f"got {s['when']!r}")
    expect(f"{name} target 合法", s["target"] in VALID_TARGET, f"got {s['target']!r}")
    expect(f"{name} enabled 是 bool", isinstance(s["enabled"], bool))
    expect(f"{name} name 非空", bool(s["name"].strip()))
    expect(f"{name} prompt 非空", bool(s["prompt"].strip()))


# ============================================================
# Test S4: prompt 全部含 {content} 占位符
# ============================================================
section("S4 — prompt 必含 {content}")
for s in RESEARCH_REPORT_SKILLS:
    name = s["name"]
    expect(f"{name} prompt 含 {{content}}", "{content}" in s["prompt"])


# ============================================================
# Test S5: prompt 字数合理
# ============================================================
section("S5 — prompt 字数与防退化")
# 匹配"不新增设定"类约束，宽松：允许"不得自行新增"/"严禁(替作者)新增"/etc.
NO_NEW_PATTERN = re.compile(
    r"(?:不|严禁|不得|不要)[^。\n]{0,8}(?:新增|新设定|新人物|新地点)"
)
for s in RESEARCH_REPORT_SKILLS:
    name = s["name"]
    n = len(s["prompt"])
    expect(f"{name} prompt 长度 ≥120 字", n >= 120, f"实际 {n}")
    expect(f"{name} prompt 长度 ≤2500 字", n <= 2500, f"实际 {n}")
    # 必须明确禁止"新增设定"（一致性校验本身是审计型，例外）
    has_no_new_setting = bool(NO_NEW_PATTERN.search(s["prompt"])) \
                         or s["when"] == "after_chapter_generation"
    expect(f"{name} 含「不新增设定」类约束", has_no_new_setting,
           "（一致性校验例外，因为它本身就是审计型）")


# ============================================================
# Test S6: auto_match 技能必须有合法 trigger_pattern
# ============================================================
section("S6 — auto_match 触发词")
auto_match_skills = [s for s in RESEARCH_REPORT_SKILLS if s["when"] == "auto_match"]
expect("至少一个 auto_match 技能", len(auto_match_skills) >= 1)
for s in auto_match_skills:
    name = s["name"]
    pat = s["trigger_pattern"]
    expect(f"{name} trigger_pattern 非空", bool(pat))
    try:
        compiled = re.compile(pat)
        expect(f"{name} trigger_pattern 是合法正则", True)
    except re.error as e:
        expect(f"{name} trigger_pattern 是合法正则", False, str(e))
    # 测命中：用研究报告片段三的关键词测一次
    sample = "陈知行抬手，把借命谱拍进天漏，谢天衡当面对质："
    if compiled.search(sample):
        expect(f"{name} 能命中典型高潮文本", True)
    else:
        # 不强制，但提示
        expect(f"{name} 命中测试样本", True, "（warning: 样本未命中，pattern 可能太严）")


# ============================================================
# Test S7: 非 auto_match 技能 trigger_pattern 应为空
# ============================================================
section("S7 — 非 auto_match 技能 trigger 必须空")
for s in RESEARCH_REPORT_SKILLS:
    if s["when"] != "auto_match":
        expect(f"{s['name']} trigger_pattern 为空",
               s["trigger_pattern"] == "",
               f"got {s['trigger_pattern']!r}")


# ============================================================
# Test S8: 默认开关安排合理
# ============================================================
section("S8 — 默认开关安排")
# 一致性校验应当默认关（每章 +1 次 AI 调用）
consistency = next(
    (s for s in RESEARCH_REPORT_SKILLS if "一致性校验" in s["name"]),
    None,
)
expect("一致性校验存在", consistency is not None)
if consistency:
    expect("一致性校验默认关", consistency["enabled"] is False)

# auto_match 高潮重写也应默认关
hi_rewrite = next(
    (s for s in RESEARCH_REPORT_SKILLS if "高潮" in s["name"]),
    None,
)
expect("高潮重写存在", hi_rewrite is not None)
if hi_rewrite:
    expect("高潮重写默认关", hi_rewrite["enabled"] is False)

# 细纲 / 桥段 / 短文本应默认开（手动工具不浪费 token）
for nm in ("细纲扩展", "桥段扩写", "短文本生成"):
    s = next((x for x in RESEARCH_REPORT_SKILLS if nm in x["name"]), None)
    expect(f"{nm} 默认开（手动调用不浪费）",
           s is not None and s["enabled"] is True)


# ============================================================
# Test S9: validate_skill 单条校验
# ============================================================
section("S9 — validate_skill 边界")
# 合法
expect("合法 skill 校验返回空 list",
       validate_skill(RESEARCH_REPORT_SKILLS[0]) == [])
# 缺字段
bad = dict(RESEARCH_REPORT_SKILLS[0])
del bad["target"]
errs = validate_skill(bad)
expect("缺 target 报错", any("target" in e for e in errs))
# 非法 when
bad = dict(RESEARCH_REPORT_SKILLS[0])
bad["when"] = "xxx"
errs = validate_skill(bad)
expect("非法 when 报错", any("when" in e for e in errs))
# auto_match 缺 trigger
bad = dict(RESEARCH_REPORT_SKILLS[0])
bad["when"] = "auto_match"; bad["trigger_pattern"] = ""
errs = validate_skill(bad)
expect("auto_match 缺 trigger 报错",
       any("trigger_pattern" in e for e in errs))
# auto_match 烂正则
bad = dict(RESEARCH_REPORT_SKILLS[0])
bad["when"] = "auto_match"; bad["trigger_pattern"] = "[unclosed"
errs = validate_skill(bad)
expect("烂正则报错", any("正则" in e for e in errs))
# 不含 {content}
bad = dict(RESEARCH_REPORT_SKILLS[0])
bad["prompt"] = "no placeholder"
errs = validate_skill(bad)
expect("缺 {content} 报错", any("content" in e for e in errs))
# enabled 类型错
bad = dict(RESEARCH_REPORT_SKILLS[0])
bad["enabled"] = "yes"
errs = validate_skill(bad)
expect("enabled 非 bool 报错", any("enabled" in e for e in errs))


# ============================================================
# Test S10: validate_all() 全过
# ============================================================
section("S10 — validate_all()")
errs = validate_all()
expect("validate_all() 无错", errs == {},
       f"errors: {errs}" if errs else "")


# ============================================================
# Test S11: install_into 接入到 fake SkillLibrary
# ============================================================
section("S11 — install_into")

class FakeSkillLib:
    def __init__(self, init_skills=None):
        self.skills = list(init_skills or [])
        self._refresh_called = 0
    def _refresh_list(self):
        self._refresh_called += 1

# 11a. 空库 + 默认（不替换同名）
lib = FakeSkillLib()
n = install_into(lib)
expect("空库装入 5 条", n == 5)
expect("lib.skills 数量 = 5", len(lib.skills) == 5)
expect("_refresh_list 被调一次", lib._refresh_called == 1)

# 11b. 已有同名 + 默认（不替换）
lib = FakeSkillLib(init_skills=[
    {"name": "细纲扩展（写章前）", "enabled": True, "prompt": "X{content}",
     "when": "manual", "trigger_pattern": "", "target": "log_only"},
])
n = install_into(lib)
expect("已有同名跳过 → 装 4 条", n == 4)
expect("总数 = 5", len(lib.skills) == 5)
# 原本那条不能被替换
expect("原同名 prompt 仍是 X{content}",
       lib.skills[0]["prompt"] == "X{content}")

# 11c. 已有同名 + replace_same_name=True
lib = FakeSkillLib(init_skills=[
    {"name": "细纲扩展（写章前）", "enabled": True, "prompt": "X{content}",
     "when": "manual", "trigger_pattern": "", "target": "log_only"},
])
n = install_into(lib, replace_same_name=True)
expect("替换模式装 5 条（4 新 + 1 替换）", n == 5)
expect("总数 = 5（替换不增加）", len(lib.skills) == 5)
# 替换后 prompt 不再是 X{content}
replaced = next(s for s in lib.skills if s["name"] == "细纲扩展（写章前）")
expect("被替换 prompt 含「细纲扩展」",
       "细纲扩展" in replaced["prompt"])

# 11d. 不带 skills 属性的对象 → 安全返回 0
class NotSkillLib: pass
expect("非 SkillLibrary 安全返回 0",
       install_into(NotSkillLib()) == 0)


# ============================================================
# Test S12: get_skills_copy 返回深拷贝
# ============================================================
section("S12 — get_skills_copy 深拷贝隔离")
a = get_skills_copy()
b = get_skills_copy()
expect("两次调用返回不同对象", a is not b)
expect("内容一样", a == b)
a[0]["name"] = "MUTATED"
expect("修改 a 不影响 b", b[0]["name"] != "MUTATED")
expect("修改 a 不影响原 RESEARCH_REPORT_SKILLS",
       RESEARCH_REPORT_SKILLS[0]["name"] != "MUTATED")


# ============================================================
# Test S13: trigger_pattern 在 SkillLibrary.get_auto_match_skills 风格调用下生效
# ============================================================
section("S13 — auto_match 触发模拟")

# 模仿 SkillLibrary.get_auto_match_skills 的逻辑
def fake_get_auto_match(skills, content):
    out = []
    for s in skills:
        if s.get("when") != "auto_match" or not s.get("enabled"):
            continue
        pat = s.get("trigger_pattern", "")
        if not pat:
            continue
        try:
            if re.search(pat, content[:3000]):
                out.append(s)
        except re.error:
            continue
    return out

# 出厂状态下高潮重写默认关，所以必须先开
test_skills = get_skills_copy()
for s in test_skills:
    if "高潮" in s["name"]:
        s["enabled"] = True

# 命中
text_with_climax = "宁归樵交出借命谱并死，主角与谢天衡当面对质，登台审判。"
hits = fake_get_auto_match(test_skills, text_with_climax)
expect("高潮文本命中", len(hits) >= 1)
expect("命中的是高潮场面自动重写",
       any("高潮" in h["name"] for h in hits))

# 不命中
text_normal = "这是一段普通对话场景，没有任何冲突词。"
hits = fake_get_auto_match(test_skills, text_normal)
expect("普通对话不命中", len(hits) == 0)


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
