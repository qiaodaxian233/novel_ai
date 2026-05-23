"""
workflow_pipeline.py — NovelAI 模块化生成流水线
================================================
把"生成章节"的完整生命周期拆成可插拔的 Step,
主控类 GenerationWorkflow 负责按阶段串联调用。

架构总览
--------
                ┌─────────────────────────────────┐
  generate() → │  Phase 1: PRE_WRITE              │  prompt 注入块(纯同步)
                │  MemoryInjectStep                │
                │  CanonInjectStep                 │
                │  CritiqueRulesInjectStep         │
                └──────────────┬──────────────────┘
                               ↓
                ┌─────────────────────────────────┐
                │  Phase 2: AI_GENERATE            │  发给浏览器(异步)
                │  BrowserSendStep                 │
                └──────────────┬──────────────────┘
                               ↓
                ┌─────────────────────────────────┐
                │  Phase 3: POST_WRITE (校验)      │  逐步消费 remaining
                │  WordCountStep   (即时)          │
                │  HookCheckStep   (即时)          │
                │  CanonAuditStep  (AI)            │
                │  RhythmScoreStep (AI)            │
                │  CharacterScoreStep (AI)         │
                └──────────────┬──────────────────┘
                               ↓
                       ┌───────┴──────┐
                    失败:issues        通过
                    _retry()           ↓
                       ↑     ┌─────────────────────────────────┐
                       └───  │  Phase 4: POST_CHAIN            │
                             │  CanonExtractStep               │
                             │  SkillAfterStep(s)              │
                             │  SummaryStep                    │
                             │  NextChapterStep / EndBatchStep │
                             └─────────────────────────────────┘

使用方式
--------
在 MainWindow.__init__ 里:

    self.workflow = GenerationWorkflow(self)

替换 _send_next_chapter 末尾的 _send_to_ai 调用:

    self.workflow.start(
        prompt=prompt,
        ch_num=ch_num,
        target_words=target_with_offset,
        min_words=min_words,
        retry_left=self.tab_generation.retry_count.value(),
    )

替换 _on_response_received 里 target == "chapter" 的分支:

    elif target == "chapter":
        self.workflow.on_ai_content(content, meta)

所有中间流程(稽核 / retry / post-chain)内部闭环,
MainWindow 不再需要手动拼 _audit_state / _post_chapter_pipeline。
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable, List, Optional, Any
from PyQt5.QtCore import QTimer
import re

if TYPE_CHECKING:
    # 避免循环 import;运行时通过 __init__ 参数传入
    pass


# ======================================================================
# 1.  PipelineContext — 单次章节生命周期的共享状态
# ======================================================================

class PipelineContext:
    """
    贯穿整条流水线的可变上下文。
    各 Step 可以读取 / 修改它;不允许替换对象本身。
    """

    def __init__(self, prompt: str, ch_num: int,
                 target_words: int, min_words: int,
                 retry_left: int, original_prompt: str = ""):
        # ---- 写前 ----
        self.prompt: str = prompt                    # 各注入步可在末尾追加
        self.ch_num: int = ch_num
        self.target_words: int = target_words
        self.min_words: int = min_words
        self.retry_left: int = retry_left
        self.original_prompt: str = original_prompt or prompt

        # ---- 写后 ----
        self.content: str = ""                        # AI 生成正文
        self.issues: List[str] = []                   # 校验问题汇总

        # ---- 内部流水线游标 ----
        self._post_write_remaining: List[str] = []    # 待跑的 POST_WRITE step 名
        self._post_chain_remaining: List[Any] = []    # 待跑的 POST_CHAIN step

        # ---- 附加数据(供 Step 之间传递零散数据)----
        self.extras: dict = {}

    def append_prompt(self, block: str, label: str = "", log_fn=None):
        """在 prompt 末尾追加一段,并可选写日志"""
        if not block:
            return
        self.prompt += f"\n\n{block}"
        if log_fn and label:
            log_fn(f"已注入 {label}({len(block)} 字符)到第 {self.ch_num} 章提示词", "info")

    def add_issue(self, msg: str):
        self.issues.append(msg)

    def has_issues(self) -> bool:
        return bool(self.issues)


# ======================================================================
# 2.  PipelineStep — 所有 Step 的基类
# ======================================================================

class PipelineStep:
    """
    Step 接口约定：
      - name:  唯一标识字符串
      - enabled: 可运行时切换
      - run(ctx, done):
          * ctx  — PipelineContext
          * done — 完成后必须调用的回调 done()
                   同步步骤直接 done(); 异步步骤在回调里 done()
    """

    name: str = "base_step"
    enabled: bool = True

    def run(self, ctx: PipelineContext, done: Callable[[], None]):
        done()


# ======================================================================
# 3.  Phase 1: PRE_WRITE Steps — prompt 注入
# ======================================================================

class MemoryInjectStep(PipelineStep):
    """注入对话记忆块"""
    name = "memory_inject"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_memory.auto_inject.isChecked()

    def run(self, ctx: PipelineContext, done):
        block = self._mw._build_memory_block()
        ctx.append_prompt(block, "对话记忆", self._mw.tab_generation.log)
        done()


class CanonInjectStep(PipelineStep):
    """注入 Canon 约束块"""
    name = "canon_inject"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_canon.chk_inject.isChecked()

    def run(self, ctx: PipelineContext, done):
        block = self._mw._build_canon_block()
        ctx.append_prompt(block, "Canon 约束", self._mw.tab_generation.log)
        done()


class CritiqueRulesInjectStep(PipelineStep):
    """
    注入 Critique 规则说明块(让 AI 写作时就意识到要被打分的维度)
    文案来自 PROMPTS 字典或 inline 常量。
    """
    name = "critique_rules_inject"

    _RULES_TEMPLATE = (
        "【自我审稿清单 — 写完后对照检查】\n"
        "{rules}\n"
        "以上每条都须达标,否则本章视为不合格需重写。"
    )

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        cfg = self._mw.tab_generation.critique_config()
        # 只要启用了任一 AI 评分维度就注入说明,让 AI 写时有意识
        return cfg.get("rhythm") or cfg.get("character")

    def run(self, ctx: PipelineContext, done):
        cfg = self._mw.tab_generation.critique_config()
        rules = []
        if cfg.get("hook"):
            rules.append("· 章末必须留悬念/转折钩子(问号/省略号/转折词结尾)")
        if cfg.get("rhythm"):
            rules.append("· 节奏打分目标 ≥ 7/10:张弛有序,高潮段落前有铺垫")
        if cfg.get("character"):
            rules.append("· 人设打分目标 ≥ 7/10:人物行为与档案设定一致")
        if rules:
            block = self._RULES_TEMPLATE.format(rules="\n".join(rules))
            ctx.append_prompt(block, "Critique 规则提示", self._mw.tab_generation.log)
        done()


class CharLibInjectStep(PipelineStep):
    """v1.23 BUG-041:注入角色与世界 6 库(角色档案/关系/物品/伏笔/钩子/爽点)

    数据源:tab_charlib(CharacterLibrary)的 build_inject_block 方法
    跟旧路径(if not workflow)里的 charlib_block 注入完全等价

    之前 workflow 完全跳过 6 库注入 —— 用户开了 ✨ 自动抽取也白搭,
    AI 永远看不到角色与世界的结构化数据,人物语气和设定全凭运气。
    """
    name = "charlib_inject"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return (hasattr(self._mw, "tab_charlib") and
                hasattr(self._mw.tab_charlib, "chk_inject") and
                self._mw.tab_charlib.chk_inject.isChecked())

    def run(self, ctx: PipelineContext, done):
        try:
            block = self._mw.tab_charlib.build_inject_block(
                current_chapter=ctx.ch_num)
            if block:
                ctx.append_prompt(
                    block, "角色与世界 6 库", self._mw.tab_generation.log)
        except Exception as e:
            try:
                self._mw.tab_generation.log(
                    f"⚠ CharLibInjectStep 注入失败: {e}", "warn")
            except Exception:
                pass
        done()


# ======================================================================
# 4.  Phase 3: POST_WRITE Steps — 校验
# ======================================================================

class WordCountStep(PipelineStep):
    """即时字数校验"""
    name = "word_count"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("word_count", True)

    def run(self, ctx: PipelineContext, done):
        actual = len(re.sub(r'\s', '', ctx.content))
        if actual < ctx.min_words:
            ctx.add_issue(
                f"字数不达标:目标 {ctx.target_words} 字,"
                f"实际 {actual} 字(差 {ctx.min_words - actual} 字)")
        done()


class HookCheckStep(PipelineStep):
    """即时章末钩子启发式检查 (v1.73: 源头统一到 pangu_system.PanguEngine.HOOK_MARKERS)"""
    name = "hook_check"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("hook", True)

    def run(self, ctx: PipelineContext, done):
        try:
            from pangu_system import PanguEngine as _PE
            has_hook = _PE.check_chapter_has_hook(ctx.content)
        except Exception:
            has_hook = True  # 兜底:pangu 不可用就放行
        if not has_hook:
            ctx.add_issue(
                "章末缺少钩子:末段无悬念/转折/留白/反差元素,"
                "读者追更欲不足。请在结尾留一个新悬念、决断、神秘人或场景切换")
        done()


class CanonAuditStep(PipelineStep):
    """AI Canon 稽核(high 违反 → 加入 issues)"""
    name = "canon_audit"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("canon", True)

    def run(self, ctx: PipelineContext, done):
        def on_violations(violations):
            for v in violations:
                if v.get("severity") == "high":
                    ctx.add_issue("Canon 违反(严重):" + v.get("desc", "")[:120])
            done()

        self._mw._run_canon_audit(ctx.content, ctx.ch_num, on_violations)


class RhythmScoreStep(PipelineStep):
    """AI 节奏打分(< 阈值 → 加入 issues)"""
    name = "rhythm_score"
    threshold = 7

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("rhythm", False)

    def run(self, ctx: PipelineContext, done):
        from novel_ai import PROMPTS  # 延迟导入避免循环
        prompt = PROMPTS["critique_rhythm"].format(content=ctx.content[:6000])

        def on_response(content_resp):
            score, reason = self._parse_score(content_resp)
            ctx.extras[f"rhythm_score"] = score
            if score < self.threshold:
                ctx.add_issue(
                    f"节奏评分 {score}/10 低于阈值 {self.threshold}:{reason[:80]}")
            done()

        self._mw._send_to_ai_with_callback(
            prompt, f"节奏稽核-第{ctx.ch_num}章", on_response)

    @staticmethod
    def _parse_score(text: str):
        """
        解析 AI 评分返回。优先级:
        1. JSON 格式 {"score":8,"reason":"..."} (含 markdown code block 包裹的)
        2. 旧格式 "8/10,reason"
        3. 兜底返回 (10.0, "[parse 失败,跳过]") — 不让 parser 故障变成"评分不足"
           误判触发死磕。对齐 _on_critique_score_response 旧路径的"parse 失败
           只 log,不计 issue"行为(BUG-062)。
        """
        import json as _json
        raw = (text or "").strip()
        # 去掉 markdown 代码块包裹
        raw_unwrapped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.M).strip()
        # 尝试找 JSON 对象(可能有前后文)
        jm = re.search(r"\{[\s\S]*?\}", raw_unwrapped)
        if jm:
            try:
                data = _json.loads(jm.group(0))
                if isinstance(data, dict) and "score" in data:
                    score = float(data.get("score", 5.0))
                    reason = str(data.get("reason", "")).strip()[:200]
                    return score, reason
            except Exception:
                pass
        # 兜底:旧的 8/10 格式
        m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', raw)
        if m:
            score = float(m.group(1))
            reason = re.sub(r'.*?\d+\s*/\s*10\s*[,，。\n]?', '', raw, count=1).strip()[:200]
            return score, reason
        # 全失败:返回 10.0(高于任何阈值)让上层跳过此维度,
        # 而不是返回 5.0(恒 < 阈值 7)让 parser 故障直接触发死磕。
        return 10.0, "[parse 失败,跳过本维度评分]"


class CharacterScoreStep(PipelineStep):
    """AI 人设打分(< 阈值 → 加入 issues)"""
    name = "character_score"
    threshold = 7

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("character", False)

    def run(self, ctx: PipelineContext, done):
        from novel_ai import PROMPTS
        chars = self._mw.get_unified_chars_summary() or "(暂无)"
        prompt = PROMPTS["critique_character"].format(
            characters=chars, content=ctx.content[:6000])

        def on_response(content_resp):
            score, reason = RhythmScoreStep._parse_score(content_resp)
            ctx.extras["character_score"] = score
            if score < self.threshold:
                ctx.add_issue(
                    f"人设评分 {score}/10 低于阈值 {self.threshold}:{reason[:80]}")
            done()

        self._mw._send_to_ai_with_callback(
            prompt, f"人设稽核-第{ctx.ch_num}章", on_response)


class AIStyleScoreStep(PipelineStep):
    """AI 文风巡检(< 阈值 → 加入 issues,触发死磕重写)"""
    name = "ai_style_score"
    threshold = 7

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("ai_style", False)

    def run(self, ctx: PipelineContext, done):
        from novel_ai import PROMPTS
        prompt = PROMPTS["critique_ai_style"].format(content=ctx.content[:6000])

        def on_response(content_resp):
            score, reason = RhythmScoreStep._parse_score(content_resp)
            ctx.extras["ai_style_score"] = score
            self._mw.tab_generation.log(
                f"🔍 AI文风巡检: {score}/10 — {reason[:100]}", "info")
            if score < self.threshold:
                ctx.add_issue(
                    f"AI文风评分 {score}/10 低于阈值 {self.threshold}:{reason[:80]}")
            done()

        self._mw._send_to_ai_with_callback(
            prompt, f"AI文风巡检-第{ctx.ch_num}章", on_response)


# ======================================================================
# 5.  Phase 4: POST_CHAIN Steps — 通过后链式
# ======================================================================

class CanonExtractStep(PipelineStep):
    """自动从章节提取 Canon 条目"""
    name = "canon_extract"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_canon.chk_extract.isChecked()

    def run(self, ctx: PipelineContext, done):
        self._mw._run_canon_extract(ctx.content, ctx.ch_num)
        # canon_extract 自己有回调链,post_chain 不等它;直接继续
        done()


class EmotionScoreStep(PipelineStep):
    """情绪维度评分(紧张/爽感/虐心/温馨),写入章节数据供可视化"""
    name = "emotion_score"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return True  # 始终执行,不占用质检配额

    def run(self, ctx: PipelineContext, done):
        from novel_ai import PROMPTS
        prompt = PROMPTS["emotion_score"].format(content=ctx.content[:6000])

        def on_response(content_resp):
            import json as _json
            raw = (content_resp or "").strip()
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.M).strip()
            jm = re.search(r"\{[\s\S]*?\}", raw)
            if jm:
                try:
                    data = _json.loads(jm.group(0))
                    scores = {
                        "tension": int(data.get("tension", 5)),
                        "satisfaction": int(data.get("satisfaction", 5)),
                        "emotion": int(data.get("emotion", 5)),
                        "warmth": int(data.get("warmth", 5)),
                        "summary": str(data.get("summary", ""))[:100],
                    }
                    # 写入章节数据
                    ch_idx = ctx.ch_num - 1
                    if 0 <= ch_idx < len(self._mw.chapters):
                        self._mw.chapters[ch_idx]["emotion_scores"] = scores
                    self._mw.tab_generation.log(
                        f"📊 情绪评分: 紧张{scores['tension']} 爽感{scores['satisfaction']} "
                        f"虐心{scores['emotion']} 温馨{scores['warmth']} — {scores['summary']}",
                        "info")
                except Exception:
                    pass
            done()

        self._mw._send_to_ai_with_callback(
            prompt, f"情绪评分-第{ctx.ch_num}章", on_response)


class SkillAfterStep(PipelineStep):
    """运行单个 after_chapter_generation 技能"""
    name = "skill_after"

    def __init__(self, main_window, skill: dict):
        self._mw = main_window
        self.skill = skill

    @property
    def enabled(self) -> bool:
        return True  # 加入 pipeline 时已确认触发条件

    def run(self, ctx: PipelineContext, done):
        self._mw._run_skill_on_chapter(
            self.skill, ctx.ch_num,
            chain_post=True,           # 完成后推进外层流水线
            _done_cb=done,             # 新增 kwarg,见下方 _run_skill_on_chapter 改造说明
        )


class SummaryStep(PipelineStep):
    """生成章节摘要"""
    name = "summary"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_memory.auto_summarize.isChecked()

    def run(self, ctx: PipelineContext, done):
        # chain_to_next=False:下一章由 NextChapterStep 负责
        self._mw._submit_summary_task(
            ctx.ch_num,
            chain_to_next=False,
            _done_cb=done,   # 改造后的 _submit_summary_task 支持此回调
        )


class NextChapterStep(PipelineStep):
    """触发下一章生成"""
    name = "next_chapter"

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        mw = self._mw
        return mw._batch_remaining > 0 and not mw._batch_paused

    def run(self, ctx: PipelineContext, done):
        QTimer.singleShot(800, self._mw._send_next_chapter)
        done()  # 本步同步完成,下一章独立走自己的 workflow


class EndBatchStep(PipelineStep):
    """批量结束"""
    name = "end_batch"

    def __init__(self, main_window):
        self._mw = main_window

    def run(self, ctx: PipelineContext, done):
        self._mw.tab_generation.log("批量生成已结束", "info")
        done()


# ======================================================================
# 6.  StepRegistry — 步骤注册表(方便外部扩展)
# ======================================================================

class StepRegistry:
    """
    用于注册自定义 Step,实现"插件化"扩展。
    用法:
        registry = StepRegistry()
        registry.register("pre_write", MyCustomInjectStep(mw))
        workflow = GenerationWorkflow(mw, registry=registry)
    """

    def __init__(self):
        # phase → list of (priority, step)
        self._steps: dict[str, list] = {
            "pre_write":   [],
            "post_write":  [],
            "post_chain":  [],
        }

    def register(self, phase: str, step: PipelineStep, priority: int = 50):
        """注册 step 到指定阶段。priority 小的先执行(默认 50)。"""
        if phase not in self._steps:
            raise ValueError(f"未知 phase: {phase}. 可选: {list(self._steps)}")
        self._steps[phase].append((priority, step))
        self._steps[phase].sort(key=lambda x: x[0])

    def get(self, phase: str) -> List[PipelineStep]:
        return [s for _, s in self._steps[phase]]


# ======================================================================
# 7.  GenerationWorkflow — 主控类
# ======================================================================

class GenerationWorkflow:
    """
    单次章节生成的完整生命周期控制器。
    
    设计原则:
    - 所有 Step 通过 enabled 属性动态开关,无需修改 workflow 代码
    - 每个阶段是一条 step 列表,逐步串行消费
    - retry 时复用同一个 ctx,只重置 content 和 issues
    - MainWindow 只需调用 start() 和 on_ai_content()
    """

    def __init__(self, main_window, registry: Optional[StepRegistry] = None):
        self._mw = main_window
        self._registry = registry or StepRegistry()
        self._ctx: Optional[PipelineContext] = None

        # 在 MainWindow 里调用 setup_default_steps() 完成默认装配
        self._pre_write_steps: List[PipelineStep] = []
        self._post_write_steps: List[PipelineStep] = []
        self._post_chain_factory: Optional[Callable] = None  # 每章重建,见 _build_post_chain

    # ------------------------------------------------------------------
    # 7-A. 装配默认 Steps
    # ------------------------------------------------------------------

    def setup_default_steps(self):
        """
        注册框架默认的所有 Step。
        在 MainWindow.__init__ 末尾调用一次即可。
        """
        mw = self._mw

        # --- PRE_WRITE ---
        self._registry.register("pre_write", MemoryInjectStep(mw),        priority=10)
        self._registry.register("pre_write", CanonInjectStep(mw),         priority=20)
        # v1.23 BUG-041:补 6 库注入(之前 workflow 路径完全漏注入这块)
        self._registry.register("pre_write", CharLibInjectStep(mw),       priority=25)
        self._registry.register("pre_write", CritiqueRulesInjectStep(mw), priority=30)

        # --- POST_WRITE ---
        self._registry.register("post_write", WordCountStep(mw),       priority=10)
        self._registry.register("post_write", HookCheckStep(mw),       priority=20)
        self._registry.register("post_write", CanonAuditStep(mw),      priority=30)
        self._registry.register("post_write", RhythmScoreStep(mw),     priority=40)
        self._registry.register("post_write", CharacterScoreStep(mw),  priority=50)
        self._registry.register("post_write", AIStyleScoreStep(mw),    priority=55)

        # POST_CHAIN 每章动态构建(因为 skill 列表可变),由 _build_post_chain() 处理

    # ------------------------------------------------------------------
    # 7-B. 入口:开始一章生成
    # ------------------------------------------------------------------

    def start(self, prompt: str, ch_num: int,
              target_words: int, min_words: int, retry_left: int):
        """
        启动章节生成流水线。
        调用方:_send_next_chapter() 末尾。
        """
        ctx = PipelineContext(
            prompt=prompt,
            ch_num=ch_num,
            target_words=target_words,
            min_words=min_words,
            retry_left=retry_left,
        )
        self._ctx = ctx
        self._run_pre_write(ctx)

    # ------------------------------------------------------------------
    # 7-C. Phase 1: PRE_WRITE
    # ------------------------------------------------------------------

    def _run_pre_write(self, ctx: PipelineContext):
        """串行跑所有 pre_write 步,全部完成后发送给浏览器"""
        if hasattr(self._mw, '_update_task_monitor'):
            self._mw._update_task_monitor(f"第{ctx.ch_num}章", "📤 写前注入")
        steps = [s for s in self._registry.get("pre_write") if s.enabled]
        self._run_step_list(steps, ctx, self._after_pre_write)

    def _after_pre_write(self, ctx: PipelineContext):
        """PRE_WRITE 全部完成 → 发给 AI"""
        mw = self._mw
        mw.tab_generation.log(
            f"写前注入完成,发送第 {ctx.ch_num} 章({len(ctx.prompt)} 字符)", "info")
        mw._send_to_ai(
            ctx.prompt, f"第 {ctx.ch_num} 章",
            target="chapter",
            ch_num=ctx.ch_num,
            target_words=ctx.target_words,
            min_words=ctx.min_words,
            retry_left=ctx.retry_left,
            original_prompt=ctx.original_prompt,
            _workflow_ctx=ctx,          # 把 ctx 挂到 meta,供回调取回
        )

    # ------------------------------------------------------------------
    # 7-D. Phase 2 回调:AI 内容到达
    # ------------------------------------------------------------------

    def on_ai_content(self, content: str, meta: dict):
        """
        由 _on_response_received 在 target == "chapter" 时调用。
        替代原来的 _handle_chapter_response。
        """
        # 如果 meta 里有 _workflow_ctx 就复用,否则(兼容老路径)新建
        ctx: PipelineContext = meta.get("_workflow_ctx") or self._ctx
        if ctx is None:
            # 兼容:直接用 meta 重建 ctx
            ctx = PipelineContext(
                prompt=meta.get("original_prompt", ""),
                ch_num=meta.get("ch_num", 1),
                target_words=meta.get("target_words", 3000),
                min_words=meta.get("min_words", 2550),
                retry_left=meta.get("retry_left", 0),
            )
            self._ctx = ctx

        if not content:
            self._mw._batch_remaining = 0
            return

        # ★ BUG-062 防御(对齐旧路径 _handle_chapter_response 的 BUG-027 哨兵):
        #   DeepSeek 串行任务有时回复抓取错位 → 抓到的不是章节,
        #   是上一轮 JSON 稽核的残留 / 短回复 / "输入内容并非小说章节正文" 之类提示。
        #   如果章节正文 < 500 字 且 retry_left > 0,认定 AI 没听懂指令 / 抓串了,
        #   直接重发原指令,不进入校验流程(不然短回复会被节奏稽核 AI 当不及格
        #   再触发死磕,死磕完又拿到下一个串错位,雪崩)。
        if meta.get("target") != "golden_three":
            ck_len = len(content.strip())
            if ck_len < 500 and ctx.retry_left > 0:
                self._mw.tab_generation.log(
                    f"⚠ 收到异常短的'章节回复'({ck_len} 字),疑似抓取错位/AI 误解指令,"
                    f"重发(剩余 {ctx.retry_left} 次)",
                    "warn")
                ctx.content = ""
                ctx.issues = ["内容明显异常(疑似抓取错位),重发"]
                self._retry(ctx)
                return

        ctx.content = content
        ctx.issues = []  # 每次(含 retry)重置 issues

        # golden_three 特殊路径:不走校验
        if meta.get("target") == "golden_three":
            self._accept(ctx)
            return

        self._run_post_write(ctx)

    # ------------------------------------------------------------------
    # 7-E. Phase 3: POST_WRITE
    # ------------------------------------------------------------------

    def _run_post_write(self, ctx: PipelineContext):
        if hasattr(self._mw, '_update_task_monitor'):
            self._mw._update_task_monitor(f"第{ctx.ch_num}章", "🔍 写后校验")
        steps = [s for s in self._registry.get("post_write") if s.enabled]
        self._run_step_list(steps, ctx, self._after_post_write)

    def _after_post_write(self, ctx: PipelineContext):
        if ctx.has_issues():
            self._retry(ctx)
        else:
            self._accept(ctx)

    # ------------------------------------------------------------------
    # 7-F. Retry
    # ------------------------------------------------------------------

    def _retry(self, ctx: PipelineContext):
        mw = self._mw
        if hasattr(mw, '_update_task_monitor'):
            mw._update_task_monitor(f"第{ctx.ch_num}章",
                f"🔄 重试(剩{ctx.retry_left}次)")
        if ctx.retry_left <= 0:
            # ★ BUG-062 硬下限:死磕用尽 + 内容异常短(<800 字)→ 拒绝入库,
            #   防止 JSON 评分残留 / 抓取错位的废话当成章节进 chapters[],
            #   下一章 prompt 又把这串废话当"上一章正文"喂给 AI → 雪崩。
            ck_len = len(ctx.content.strip()) if ctx.content else 0
            if ck_len < 800 and ctx.extras.get("_target_golden_three") is not True:
                mw.tab_generation.log(
                    f"✗ 死磕次数用尽,且内容异常({ck_len} 字 < 800)— "
                    f"拒绝入库,本章标记 FAILED。请检查 AI 站点状态后手动重写,"
                    f"避免污染下一章上下文", "error")
                # 不调 _accept,不进 chapters[],不触发后置链。
                # 仅减 batch_remaining,让批量循环能继续(若用户在另一会话继续)。
                mw._batch_remaining = max(0, getattr(mw, "_batch_remaining", 0) - 1)
                return
            mw.tab_generation.log("✗ 死磕次数用尽,接受这章(质量不达标)", "warn")
            self._accept(ctx)
            return

        ctx.retry_left -= 1
        reason_block = "\n".join(f"  · {r}" for r in ctx.issues)
        stronger = (
            ctx.original_prompt
            + "\n\n【上次问题清单(必须修正)】\n" + reason_block
            + "\n\n请重写本章,严格规避以上所有问题。"
        )
        mw.tab_generation.log(
            f"⚠ 章节校验未通过 ({len(ctx.issues)} 个问题),"
            f"死磕重写...剩余 {ctx.retry_left} 次", "warn")
        for r in ctx.issues:
            mw.tab_generation.log(f"  · {r}", "warn")

        # 重置 issues,等待下次 on_ai_content
        ctx.issues = []
        mw.worker.submit({
            "action": "send_prompt",
            "prompt": stronger,
            "task_id": f"第{ctx.ch_num}章(retry剩余{ctx.retry_left})",
            "url": mw.tab_generation.url_input.text().strip(),
            "type_delay_ms": 5,
        })
        # pending 里保留 _workflow_ctx,on_response_received 下次会再调 on_ai_content
        # BUG-077 根因修复:必须写 _pending_task_targets[task_id](复数 dict)
        _retry_label = f"第{ctx.ch_num}章(retry剩余{ctx.retry_left})"
        mw._pending_task_targets[_retry_label] = {
            "target": "chapter",
            "ch_num": ctx.ch_num,
            "target_words": ctx.target_words,
            "min_words": ctx.min_words,
            "retry_left": ctx.retry_left,
            "original_prompt": ctx.original_prompt,
            "_workflow_ctx": ctx,
        }

    # ------------------------------------------------------------------
    # 7-G. Accept → POST_CHAIN
    # ------------------------------------------------------------------

    def _accept(self, ctx: PipelineContext):
        mw = self._mw
        if hasattr(mw, '_update_task_monitor'):
            wc = len(ctx.content.strip()) if ctx.content else 0
            mw._update_task_monitor(f"第{ctx.ch_num}章", f"✅ 入库({wc}字)")

        # 📋 管家:章节流程开始(workflow 路径)
        try:
            import housekeeper as _hk_mod
            _hk = _hk_mod.get_housekeeper()
            _hk.start_chapter(ctx.ch_num, path_tag="workflow")
        except Exception:
            pass

        # 入库
        if ctx.extras.get("_target_golden_three"):
            mw._split_and_save_golden_three(ctx.content)
            ch_num = len(mw.chapters)
        else:
            # ★ BUG-062:对齐 _accept_chapter_and_continue 的入库数据形态。
            #   之前 workflow 路径只调 _strip_chapter_title 就 append,
            #   完全跳过了 parse_chapter_meta / 伏笔自动同步 / 钩子爽点同步,
            #   导致两条路径产出的 chapter dict 字段不一致 + lifespan_loops
            #   不更新 + 角色与世界 6 库的钩子编年/爽点编年不更新。
            pangu_meta = None
            body_for_title = ctx.content
            try:
                from pangu_system import parse_chapter_meta as _pangu_parse
                pangu_meta = _pangu_parse(ctx.content)
                body_for_title = pangu_meta.get("body") or ctx.content
                # 📋 管家:记录内容长度 + 元信息
                try:
                    import housekeeper as _hk_mod
                    _hk = _hk_mod.get_housekeeper()
                    _hk.record_content(ctx.content, body_for_title)
                    _hk.record_pangu_meta(pangu_meta)
                except Exception:
                    pass
                _stripped = len(ctx.content) - len(body_for_title)
                if _stripped > 0:
                    mw.tab_generation.log(
                        f"✓ 已剥离章节尾部元信息 {_stripped} 字 → 切到【章节编辑器】"
                        f"Tab,字数下方📌米色面板可看钩子/爽点/伏笔/下一章选项",
                        "info")
                elif ("本章完" in ctx.content or "【断章钩子】" in ctx.content
                      or "断章钩子" in ctx.content or "下一章选项" in ctx.content):
                    mw.tab_generation.log(
                        "⚠️ 检测到元信息标记但剥离失败(parse_chapter_meta 没匹配)。"
                        "请把这段章节末尾 30 行复制发给开发者,以便加新匹配规则",
                        "warn")
                    try:
                        import housekeeper as _hk_mod
                        _hk_mod.get_housekeeper().warn("元信息剥离失败")
                    except Exception:
                        pass
            except ImportError:
                pass
            except Exception as _pm_e:
                mw.tab_generation.log(
                    f"盘古元信息解析失败(降级保留原文):{_pm_e}", "warn")
                try:
                    import housekeeper as _hk_mod
                    _hk_mod.get_housekeeper().record_pangu_meta_failed(str(_pm_e))
                except Exception:
                    pass

            ch_title = mw._extract_chapter_title(body_for_title) or f"第{ctx.ch_num}章"
            ch_body = mw._strip_chapter_title(body_for_title)
            chapter = {"title": ch_title, "content": ch_body, "summary": ""}

            # 元信息字段挂到 chapter dict
            if pangu_meta:
                if pangu_meta.get("hook"):
                    chapter["hook"] = pangu_meta["hook"]
                if pangu_meta.get("cool_points"):
                    chapter["cool_points"] = pangu_meta["cool_points"]
                if pangu_meta.get("next_options"):
                    chapter["next_options"] = pangu_meta["next_options"]
                _sp = len(pangu_meta.get("seeds_planted", []))
                _pd = len(pangu_meta.get("seeds_paid", []))
                if _sp or _pd:
                    parts = []
                    if _sp: parts.append(f"埋雷 {_sp} 条")
                    if _pd: parts.append(f"收雷 {_pd} 条")
                    chapter["_pangu_seeds_summary"] = " / ".join(parts)

            mw.chapters.append(chapter)

            # 6 库同步(BUG-014 / v1.23 BUG-041 引入的旧路径功能,workflow 之前漏)
            if pangu_meta:
                try:
                    mw._sync_pangu_seeds_to_lifespan(pangu_meta, ctx.ch_num)
                    try:
                        import housekeeper as _hk_mod
                        _hk_mod.get_housekeeper().record_step("seeds_sync_lifespan", True)
                    except Exception:
                        pass
                except Exception as _e_l:
                    mw.tab_generation.log(f"伏笔同步失败:{_e_l}", "warn")
                try:
                    mw._sync_hook_and_cool_to_charlib(pangu_meta, ctx.ch_num)
                    try:
                        import housekeeper as _hk_mod
                        _hk_mod.get_housekeeper().record_step("hook_cool_sync", True)
                    except Exception:
                        pass
                except Exception as _e_h:
                    mw.tab_generation.log(f"钩子/爽点同步失败:{_e_h}", "warn")

            mw._refresh_chapter_list()
            if mw.tab_generation.auto_save.isChecked():
                mw._save_chapter_to_disk(mw.chapters[-1])
                try:
                    import housekeeper as _hk_mod
                    _hk_mod.get_housekeeper().record_step("auto_save", True)
                except Exception:
                    pass
            actual = len(re.sub(r'\s', '', ch_body))
            # 📋 管家:字数门
            try:
                import housekeeper as _hk_mod
                _hk = _hk_mod.get_housekeeper()
                _target = getattr(mw, "_batch_target_words", 0) or 0
                _hk.record_word_count(int(_target or 0), actual)
            except Exception:
                pass
            mw.tab_generation.log(
                f"✓ 第 {ctx.ch_num} 章生成成功!字数:{actual} 字", "success")
            ch_num = ctx.ch_num

        mw._batch_remaining -= 1
        ctx.ch_num = ch_num  # golden_three 后修正

        QTimer.singleShot(300, lambda: self._run_post_chain(ctx))

        # 📋 管家:章节流程结束(workflow 路径)
        try:
            import housekeeper as _hk_mod
            _hk = _hk_mod.get_housekeeper()
            _hk.record_step("post_chapter_chain", True)
            _final = _hk.finalize_chapter()
            if _final:
                mw.tab_generation.log(_final.render_oneliner(), "info")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 7-H. Phase 4: POST_CHAIN
    # ------------------------------------------------------------------

    def _build_post_chain_steps(self, ctx: PipelineContext) -> List[PipelineStep]:
        """每章动态构建 post_chain 步骤列表"""
        mw = self._mw
        steps: List[PipelineStep] = []

        # 1. Canon 抽取
        s = CanonExtractStep(mw)
        if s.enabled:
            steps.append(s)

        # 1.5 情绪评分(供可视化)
        steps.append(EmotionScoreStep(mw))

        # 2a. after_chapter_generation 技能(固定自动触发)
        for skill in mw.tab_skills.get_after_chapter_skills():
            steps.append(SkillAfterStep(mw, skill))

        # 2b. auto_match 技能(根据章节内容正则匹配触发)
        for skill in mw.tab_skills.get_auto_match_skills(ctx.content):
            mw.tab_generation.log(
                f"🎯 auto_match 技能「{skill['name']}」命中(第{ctx.ch_num}章)", "info")
            steps.append(SkillAfterStep(mw, skill))

        # 3. 摘要 or 跳过
        summary_step = SummaryStep(mw)
        if summary_step.enabled:
            steps.append(summary_step)

        # 4. 下一章 / 结束
        next_step = NextChapterStep(mw)
        if next_step.enabled:
            steps.append(next_step)
        else:
            steps.append(EndBatchStep(mw))

        # 合并外部注册的 post_chain 步骤(插件扩展)
        for ext_step in self._registry.get("post_chain"):
            if ext_step.enabled:
                steps.append(ext_step)

        return steps

    def _run_post_chain(self, ctx: PipelineContext):
        steps = self._build_post_chain_steps(ctx)
        self._run_step_list(steps, ctx, lambda _: None)  # 最后一步结束即可

    # ------------------------------------------------------------------
    # 7-I. 通用:串行消费 step 列表
    # ------------------------------------------------------------------

    def _run_step_list(self, steps: List[PipelineStep],
                       ctx: PipelineContext,
                       on_complete: Callable[[PipelineContext], None]):
        """
        把 steps 串行跑完后调用 on_complete(ctx)。
        每个 step 完成后用 QTimer.singleShot(0, ...) 让 Qt 事件循环有机会处理。
        """
        remaining = list(steps)  # 副本,不影响原列表

        def _next():
            if not remaining:
                on_complete(ctx)
                return
            step = remaining.pop(0)
            # 用 lambda 捕获 step,避免闭包引用问题
            step.run(ctx, lambda s=step: _after_step(s))

        def _after_step(step):
            QTimer.singleShot(0, _next)

        _next()


# ======================================================================
# 8.  _send_to_ai_with_callback — 对 MainWindow 的辅助扩展
#     将此方法 monkey-patch 到 MainWindow,或在类里添加
# ======================================================================

_CALLBACK_TARGET_PREFIX = "_cb_"

def _patch_main_window(main_window_cls):
    """
    为 MainWindow 添加 _send_to_ai_with_callback 方法。
    在 novel_ai.py 末尾调用:
        from workflow_pipeline import _patch_main_window
        _patch_main_window(MainWindow)
    """

    def _send_to_ai_with_callback(self, prompt: str, label: str,
                                   on_response: Callable[[str], None]):
        """
        发送给 AI 并在回复时调用 on_response(content)。
        此方法供 workflow_pipeline 的 AI 稽核 Step 内部使用。
        """
        import uuid
        cb_key = _CALLBACK_TARGET_PREFIX + uuid.uuid4().hex[:8]
        # 注册一次性回调
        if not hasattr(self, "_one_shot_callbacks"):
            self._one_shot_callbacks = {}
        self._one_shot_callbacks[cb_key] = on_response

        # BUG-077 根因修复:必须写 _pending_task_targets(复数 dict),
        # 不能写 _pending_task_target(单数,已废弃)
        self._pending_task_targets[label] = {
            "target": cb_key,
            "label": label,
        }
        url = self.tab_generation.url_input.text().strip()
        self.worker.submit({
            "action": "send_prompt",
            "prompt": prompt,
            "task_id": label,
            "url": url,
            "type_delay_ms": 5,
        })

    main_window_cls._send_to_ai_with_callback = _send_to_ai_with_callback

    # 在 _on_response_received 末尾分支里添加对 _cb_ 前缀的处理
    # (见 novel_ai.py 修改说明 §10)
