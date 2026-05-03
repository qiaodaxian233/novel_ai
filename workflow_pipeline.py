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
    """即时章末钩子启发式检查"""
    name = "hook_check"

    _MARKERS = (
        '?', '?', '...', '……',
        '突然', '却见', '只是', '可是', '然而', '没想到',
        '但下一秒', '正当', '就在', '直到',
    )

    def __init__(self, main_window):
        self._mw = main_window

    @property
    def enabled(self) -> bool:
        return self._mw.tab_generation.critique_config().get("hook", True)

    def run(self, ctx: PipelineContext, done):
        tail = ctx.content[-200:].strip()
        if not any(m in tail for m in self._MARKERS):
            ctx.add_issue(
                "章末缺少钩子:最后一段没有问号/省略号/转折词,"
                "读者追更欲不足。请在结尾留一个新悬念或反转")
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
        m = re.search(r'(\d+(?:\.\d+)?)\s*/\s*10', text)
        score = float(m.group(1)) if m else 5.0
        # 取评分后的第一句话作为原因
        reason = re.sub(r'.*?\d+\s*/\s*10\s*[,，。\n]?', '', text, count=1).strip()[:200]
        return score, reason


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
        chars = self._mw.tab_memory.chars_edit.toPlainText().strip() or "(暂无)"
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
        self._registry.register("pre_write", CritiqueRulesInjectStep(mw), priority=30)

        # --- POST_WRITE ---
        self._registry.register("post_write", WordCountStep(mw),       priority=10)
        self._registry.register("post_write", HookCheckStep(mw),       priority=20)
        self._registry.register("post_write", CanonAuditStep(mw),      priority=30)
        self._registry.register("post_write", RhythmScoreStep(mw),     priority=40)
        self._registry.register("post_write", CharacterScoreStep(mw),  priority=50)

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
        if ctx.retry_left <= 0:
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
        mw._pending_task_target = {
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

        # 入库
        if ctx.extras.get("_target_golden_three"):
            mw._split_and_save_golden_three(ctx.content)
            ch_num = len(mw.chapters)
        else:
            ch_title = mw._extract_chapter_title(ctx.content) or f"第{ctx.ch_num}章"
            ch_body = mw._strip_chapter_title(ctx.content)
            mw.chapters.append({"title": ch_title, "content": ch_body, "summary": ""})
            mw._refresh_chapter_list()
            if mw.tab_generation.auto_save.isChecked():
                mw._save_chapter_to_disk(mw.chapters[-1])
            actual = len(re.sub(r'\s', '', ctx.content))
            mw.tab_generation.log(
                f"✓ 第 {ctx.ch_num} 章生成成功!字数:{actual} 字", "success")
            ch_num = ctx.ch_num

        mw._batch_remaining -= 1
        ctx.ch_num = ch_num  # golden_three 后修正

        QTimer.singleShot(300, lambda: self._run_post_chain(ctx))

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

        self._pending_task_target = {
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
