# -*- coding: utf-8 -*-
"""
dialogue_critic.py · v1.32 — 13 法对话诊断器
─────────────────────────────────────────────
两层诊断:
  1. 本地静态扫描(免费/秒出):统计"说/道"密度 + 检测套词 + 找原文片段
  2. AI 深度评分(可选,发 AI):13 法逐条评分 + 改写建议 + 老刀风格毒舌点评

使用:
  critic = DialogueCritic(content)
  static_report = critic.static_scan()      # 本地
  ai_prompt = critic.build_ai_prompt(深度=True, 老刀=True)  # 拿去发 AI
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field


# 稚嫩指标定义
SAY_TOKENS = ["说", "道", "喊", "吼", "问"]   # 高频提示词
BAN_PATTERNS = [
    # 老套提示语
    r"怒吼道", r"喃喃道", r"喝道", r"低声道", r"淡淡道", r"缓缓道",
    r"冷冷道", r"幽幽道", r"幽幽地说", r"森然道", r"凛然道",
    r"忍不住道", r"忍不住说",
    # 修饰词修饰对话
    r"生气地说", r"担心地问", r"高兴地说", r"愤怒地说", r"伤心地说",
    r"惊讶地说", r"开心地说", r"难过地说",
]


@dataclass
class DialogueIssue:
    """单条问题"""
    kind: str         # "say_density" / "ban_word" / "consecutive_say" / "modifier_say"
    severity: str     # "red" / "yellow" / "info"
    location: int     # 字符位置
    snippet: str      # 原文片段
    msg: str          # 描述
    suggestion: str = ""   # 改写建议


@dataclass
class StaticReport:
    word_count: int = 0
    say_count: int = 0
    say_density: float = 0.0      # 每 1000 字"说"出现次数
    say_allowed: int = 0          # 允许的最大次数(word_count/600)
    issues: list[DialogueIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.say_count <= self.say_allowed and \
               not any(i.severity == "red" for i in self.issues)

    def summary(self) -> str:
        lines = []
        lines.append(f"📊 字数: {self.word_count}  /  说/道 用了: {self.say_count} 次")
        lines.append(f"   允许上限(字数/600): {self.say_allowed} 次 → "
                     f"{'✓ 通过' if self.say_count <= self.say_allowed else '✗ 超标'}")
        lines.append(f"   密度: {self.say_density:.2f} 次/千字")
        reds = [i for i in self.issues if i.severity == "red"]
        yellows = [i for i in self.issues if i.severity == "yellow"]
        if reds:
            lines.append(f"\n🚨 红线违反({len(reds)} 处):")
            for i in reds[:10]:
                lines.append(f"   · 位置 {i.location}: 「{i.snippet}」")
                lines.append(f"     → {i.msg}")
        if yellows:
            lines.append(f"\n⚠ 警告({len(yellows)} 处):")
            for i in yellows[:10]:
                lines.append(f"   · 「{i.snippet}」 — {i.msg}")
        if not reds and not yellows:
            lines.append("\n✓ 静态扫描通过,没有发现稚嫩信号")
        return "\n".join(lines)


class DialogueCritic:
    """13 法对话诊断器"""

    def __init__(self, content: str):
        self.content = content or ""

    # ────────────── 静态扫描(本地,免费)──────────────
    def static_scan(self) -> StaticReport:
        r = StaticReport()
        r.word_count = len(self.content)
        if r.word_count == 0:
            return r
        r.say_allowed = max(3, r.word_count // 600)

        # 1. 统计"X 说/道/喊/吼"频率(只匹配:汉字 + 单字提示词,且后紧跟标点/引号)
        say_pattern = re.compile(
            r"[\u4e00-\u9fa5]([说道喊吼问])(?=[::,,「『\"\s\n]|$)")
        say_matches = list(say_pattern.finditer(self.content))
        r.say_count = len(say_matches)
        r.say_density = r.say_count * 1000.0 / r.word_count

        # 2. 套词检测
        for pat in BAN_PATTERNS:
            for m in re.finditer(pat, self.content):
                start = max(0, m.start() - 8)
                end = min(len(self.content), m.end() + 5)
                snippet = self.content[start:end]
                r.issues.append(DialogueIssue(
                    kind="ban_word",
                    severity="red",
                    location=m.start(),
                    snippet=snippet,
                    msg=f"老套提示语「{m.group(0)}」— 用动作/神态替代",
                    suggestion=f"删除「{m.group(0)}」,前接角色动作/神态",
                ))

        # 3. 连续 3 句对话都用"X 说/道"
        if r.say_count >= 3:
            # 找连续 3 个 say_match,字符距离 < 80
            for i in range(len(say_matches) - 2):
                a = say_matches[i]
                b = say_matches[i + 1]
                c = say_matches[i + 2]
                if (b.start() - a.start() < 80 and
                        c.start() - b.start() < 80):
                    start = max(0, a.start() - 3)
                    end = min(len(self.content), c.end() + 5)
                    snippet = self.content[start:end].replace("\n", " ")[:100]
                    r.issues.append(DialogueIssue(
                        kind="consecutive_say",
                        severity="red",
                        location=a.start(),
                        snippet=snippet,
                        msg="连续 3 句对话都用「X 说/道」",
                        suggestion="改 L1 动作卡位 / L2 神态神韵 / L6 标点替代",
                    ))
                    break   # 同一段只报一次

        # 4. 超标本身红线
        if r.say_count > r.say_allowed:
            r.issues.append(DialogueIssue(
                kind="say_density",
                severity="red",
                location=0,
                snippet=f"{r.say_count}/{r.say_allowed}",
                msg=f"「说/道」用了 {r.say_count} 次,超标(上限 {r.say_allowed})",
                suggestion="替换为 L1-L13 任一手法",
            ))

        return r

    # ────────────── AI 深度诊断 prompt ──────────────
    def build_ai_prompt(self, deep: bool = True, laodao: bool = False) -> str:
        """构造发给 AI 的诊断 prompt"""
        static = self.static_scan()

        sections = []
        sections.append(
            "你是网文对话风格专业诊断师,使用「13 法对话铁律」体系给章节打分。\n"
            "**只看对话写法,不评价剧情。**")

        sections.append(
            "\n【13 法对话铁律】\n"
            "L1 动作卡位:用动作替代「X 说」(如:她攥紧剑柄。「过来。」)\n"
            "L2 神态神韵:专属微动作前置(如:嘴角压不住。「赌赢了。」)\n"
            "L3 情境穿插:对话间插环境/物/天气\n"
            "L4 语感辨识:角色专属语气/口头禅\n"
            "L5 语义衔接:对话直接回应前句的物/事,跳过提示语\n"
            "L6 标点替代:短促交锋用换行+标点\n"
            "L7 内心独白回切:对话后接主角预判反应\n"
            "L8 群体反应衬托:用反应阵列定位说话人\n"
            "L9 重复词锚定:角色刻意重复词/句式(全章 ≥ 2 次)\n"
            "L10 空格断句:对话顶格 + 空行\n"
            "L11 通感法:用甲感官写乙感官(如「嘴里全是铁锈味」写疲惫)\n"
            "L12 信息差:读者与角色信息不对称的张力\n"
            "L13 节奏开关:急-慢-急-慢脉冲,不能全急/全慢")

        sections.append(
            f"\n【本地静态扫描结果(供 AI 参考)】\n"
            f"字数 {static.word_count}  /  「说/道」共 {static.say_count} 次"
            f"(上限 {static.say_allowed})  /  密度 {static.say_density:.2f} 千字\n"
            f"红线违反: {sum(1 for i in static.issues if i.severity == 'red')} 处\n")

        if deep:
            sections.append(
                "\n【深度评分要求】\n"
                "对每一法(L1-L13)逐条评分:\n"
                "  - 评分: 0/2/5/8/10 分(0=完全没用 / 2=偶尔 / 5=合格 / 8=熟练 / 10=精彩)\n"
                "  - 找原文片段: 引用 1-2 处具体的原文(用「」包起来)\n"
                "  - 改写建议: 如果分数低,给一个具体的改写示例(原文 → 改后)\n"
                "\n输出格式严格按以下 JSON(只输出 JSON,无其他):\n"
                "{\n"
                '  "overall_score": 78,   // 整体分,0-100\n'
                '  "L1": {"score": 8, "evidence": "原文片段", "advice": "..."},\n'
                '  "L2": {"score": 5, "evidence": "...", "advice": "..."},\n'
                '  ...\n'
                '  "L13": {"score": 6, "evidence": "...", "advice": "..."},\n'
                '  "worst_3": ["L7", "L10", "L9"],   // 最弱的 3 法\n'
                '  "best_3": ["L2", "L11", "L1"],     // 最强的 3 法\n'
                '  "say_count": 5,\n'
                '  "verdict": "整体评价(1-2 句)"\n'
                "}")
        else:
            sections.append(
                "\n【快速评分要求】\n"
                "给整体打分(0-100)+ 找出最弱的 1-2 法,各给 1 句改写建议。\n"
                "输出 JSON 同上,但 L1-L13 可省略,只要 overall_score / worst_3 / verdict")

        if laodao:
            sections.append(
                "\n【老刀毒舌附加要求】\n"
                "在 verdict 字段里用「老刀」语气写:\n"
                "- 直接、毒舌、不绕弯,但不人身攻击\n"
                "- 看到稚嫩写法说『这段写得稚嫩,X 说 Y 说 Z 说连三句,删了重写』\n"
                "- 看到好的也要承认『L11 通感这处「嘴里全是铁锈味」一击毙命,这是顶级网文笔法』\n"
                "- 不能客套话")

        sections.append("\n【待诊断章节正文】\n" + self.content)

        return "\n".join(sections)


# ────────────── 工具函数:解析 AI 返回的 JSON ──────────────
def parse_ai_response(text: str) -> dict | None:
    """解析 AI 返回(可能裹着 ```json),失败返回 None"""
    if not text:
        return None
    # 抽出 JSON
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    import json
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def format_report(static: StaticReport, ai_data: dict | None) -> str:
    """整合静态 + AI 结果,输出最终给用户看的报告"""
    lines = []
    lines.append("═" * 50)
    lines.append("🔬 13 法对话风格诊断")
    lines.append("═" * 50)
    lines.append("\n【一、本地静态扫描】")
    lines.append(static.summary())

    if ai_data is None:
        lines.append("\n【二、AI 深度诊断】未运行或解析失败")
        return "\n".join(lines)

    lines.append("\n【二、AI 深度诊断】")
    overall = ai_data.get("overall_score", "?")
    lines.append(f"📈 整体评分: {overall}/100")
    if ai_data.get("verdict"):
        lines.append(f"💬 评价: {ai_data['verdict']}")
    if ai_data.get("best_3"):
        lines.append(f"🌟 最强 3 法: {', '.join(ai_data['best_3'])}")
    if ai_data.get("worst_3"):
        lines.append(f"⚠ 最弱 3 法: {', '.join(ai_data['worst_3'])}")

    lines.append("\n【三、13 法逐条评分】")
    LAW_NAMES = {
        "L1": "动作卡位", "L2": "神态神韵", "L3": "情境穿插",
        "L4": "语感辨识", "L5": "语义衔接", "L6": "标点替代",
        "L7": "内心独白回切", "L8": "群体反应衬托",
        "L9": "重复词锚定", "L10": "空格断句", "L11": "通感法",
        "L12": "信息差技巧", "L13": "节奏开关",
    }
    for key, name in LAW_NAMES.items():
        item = ai_data.get(key)
        if not item:
            continue
        score = item.get("score", "?")
        bar = "█" * (int(score) if isinstance(score, int) else 0)
        bar += "░" * max(0, 10 - len(bar))
        lines.append(f"\n{key} {name}: {bar} {score}/10")
        ev = item.get("evidence", "")
        if ev:
            lines.append(f"  原文: 「{ev[:80]}」")
        adv = item.get("advice", "")
        if adv:
            lines.append(f"  建议: {adv}")
    return "\n".join(lines)
