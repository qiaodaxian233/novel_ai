# -*- coding: utf-8 -*-
"""
寿元台账 + 长期伏笔检查
======================

按 v8 工作流的 PipelineStep 接入规范实现的插件式扩展模块。
专为修仙连载（如《借寿补天》）设计的两类硬约束：

1. 寿元台账（LifespanInjectStep + LifespanAuditStep）
   - PRE_WRITE: 把"剩余寿元"和"施术规则"注入到下一章 prompt
   - POST_WRITE: 从生成的章节中提取本章折寿数（先正则、再 AI、最后兜底）
                 自动累加到台账，剩余 ≤ 危急阈值时给 ctx.issues 加项

2. 长期伏笔检查（OpenLoopsCheckStep）
   - POST_WRITE: 扫一遍 open_loops 表，凡是 `last_seen_ch` 距当前章
                 ≥ warn_gap 的伏笔记入日志；≥ critical_gap 的加 ctx.issues
   - 同时自动检测本章正文是否触发了伏笔关键词，命中则刷新 last_seen_ch

接入方式（一行）：
    from lifespan_loops_steps import LifespanLoopsExtension
    LifespanLoopsExtension.install(self)   # self == MainWindow，在 __init__ 末尾

存档需要在 save_project 的 dict 里加：
    "lifespan_loops": LifespanLoopsExtension.serialize(self),
读档需要：
    if d.get("lifespan_loops"):
        LifespanLoopsExtension.deserialize(self, d["lifespan_loops"])
"""
from __future__ import annotations

import copy
import json
import re
from typing import Optional, Tuple

# ------------------------------------------------------------
# 软依赖：workflow_pipeline.PipelineStep
# 缺失时（脱机测试）提供最小存根，保证模块可独立 import
# ------------------------------------------------------------
try:
    from workflow_pipeline import PipelineStep  # type: ignore
    _HAS_WORKFLOW = True
except ImportError:
    _HAS_WORKFLOW = False

    class PipelineStep:  # type: ignore[no-redef]
        """脱机存根 —— 仅保证 import 不炸，真实运行时仍用 workflow_pipeline 的版本"""
        name: str = ""
        enabled: bool = True

        def __init__(self, mw=None):
            self.mw = mw

        def run(self, ctx, done):  # pragma: no cover
            raise NotImplementedError


# ============================================================
# 默认数据模型
# ============================================================

DEFAULT_LIFESPAN_LEDGER = {
    "enabled": False,            # 默认关，避免普通项目误触
    "total_days": 8760,          # 起始寿元（24 年）
    "used_days": 0,              # 已折寿
    "warn_threshold": 365,       # 剩余 ≤ 此值 → 日志升 warn
    "critical_threshold": 30,    # 剩余 ≤ 此值 → ctx.issues 加项
    "history": [],               # [{"ch":1,"days":1,"note":"日落被动"}]
    "auto_audit": True,          # 章末无标记时是否调 AI 入账（否则用兜底值）
    "default_per_chapter": 1,    # 兜底：每章默认折寿日数
}

DEFAULT_OPEN_LOOPS_CFG = {
    "enabled": False,
    "warn_gap": 80,              # ≥ 此值 → log warn
    "critical_gap": 150,         # ≥ 此值 → ctx.issues 加项
    "loops": [],
    # 单条 loop 字段:
    #   id          str  唯一编号（用户/系统给）
    #   desc        str  伏笔描述
    #   keyword     str  自动命中关键词（可选；为空则不自动刷新 last_seen）
    #   added_ch    int  抛坑章号
    #   last_seen_ch int 最近触及章号
    #   status      str  "open" | "closed"
}


# ============================================================
# Step 1 — LifespanInjectStep (PRE_WRITE)
# ============================================================

class LifespanInjectStep(PipelineStep):
    """把当前寿元台账注入下一章 prompt 末尾。"""
    name = "lifespan_inject"

    def __init__(self, mw):
        self.mw = mw

    def run(self, ctx, done):
        ledger = getattr(self.mw, "lifespan_ledger", None)
        if not ledger or not ledger.get("enabled"):
            done(); return

        total = int(ledger.get("total_days", 8760))
        used = int(ledger.get("used_days", 0))
        remaining = max(0, total - used)

        warn = int(ledger.get("warn_threshold", 365))
        critical = int(ledger.get("critical_threshold", 30))
        if remaining <= critical:
            tag = "🚨 危急"
        elif remaining <= warn:
            tag = "⚠️ 警戒"
        else:
            tag = "✅ 正常"

        years_total = total // 365
        years_left = remaining // 365
        days_left = remaining % 365

        block = (
            "\n【★ 寿元台账 — 修仙连载强约束 ★】\n"
            f"初始寿元: {total} 日（约 {years_total} 年）\n"
            f"已折寿: {used} 日   |   剩余: {remaining} 日"
            f"（约 {years_left} 年 {days_left} 日）   状态: {tag}\n"
            "\n施术规则（违反视为剧情漏洞）:\n"
            "1. 每日日落固定折寿 1 日（被动，无论是否施术）。\n"
            "2. 当日术式累计 ≥4 次时，第 4 次起每次额外折寿 3 日。\n"
            "3. 越阶术式额外折寿 7 日 ~ 90 日（按跨度）。\n"
            "4. 单次术式爆发上限 = 当前剩余寿元 ÷ 10。\n"
            "\n本章末尾必须出现如下结算行（用于自动入账）:\n"
            "  [寿元结算: 折寿 X 日 (说明：…)]\n"
            "若本章主角无主动施术，仍写 [寿元结算: 折寿 1 日 (日落被动)]。\n"
        )
        ctx.append_prompt(block)
        ctx.extras["lifespan_remaining_before"] = remaining
        ctx.extras["lifespan_injected"] = True
        done()


# ============================================================
# Step 2 — LifespanAuditStep (POST_WRITE)
# ============================================================

class LifespanAuditStep(PipelineStep):
    """从本章正文里提取折寿数，更新台账。

    解析优先级：
      1. 正文末段的 `[寿元结算: 折寿 X 日 (...)]` 标记
      2. （可选）AI 抽取（auto_audit=True 时启用）
      3. 兜底：default_per_chapter 日
    """
    name = "lifespan_audit"
    # 正则：宽容空白、中英冒号、汉数字干扰
    _MARKER_RE = re.compile(
        r"\[\s*寿元结算\s*[::]\s*折寿\s*(\d+)\s*日"
    )

    def __init__(self, mw):
        self.mw = mw

    # ---- 入口 ----
    def run(self, ctx, done):
        ledger = getattr(self.mw, "lifespan_ledger", None)
        if not ledger or not ledger.get("enabled"):
            done(); return
        if not ctx.content:
            done(); return

        # 1) 正则
        marker_days = self._parse_marker(ctx.content)
        if marker_days is not None:
            self._apply(ctx, marker_days, "标记入账")
            done(); return

        # 2) AI 抽取（异步）
        if ledger.get("auto_audit") and hasattr(self.mw, "_send_to_ai"):
            self._ai_extract(ctx, done)
            return

        # 3) 兜底
        fallback = int(ledger.get("default_per_chapter", 1))
        self._apply(ctx, fallback, "兜底默认")
        done()

    # ---- 解析 ----
    def _parse_marker(self, content: str) -> Optional[int]:
        # 只看末段 2000 字，避免中段引用同款字串误判
        tail = content[-2000:] if len(content) > 2000 else content
        m = self._MARKER_RE.search(tail)
        if not m:
            return None
        try:
            v = int(m.group(1))
            return max(0, v)
        except (ValueError, TypeError):
            return None

    # ---- AI 抽取 ----
    def _ai_extract(self, ctx, done):
        prompt = (
            "你是修仙小说寿元台账记账员。请仅从给定章节中提取本章主角合计折寿日数。\n\n"
            "规则:\n"
            "1. 每日日落固定折寿 1 日（被动），无论是否施术。\n"
            "2. 当日术式累计 ≥4 次时，第 4 次起每次额外折寿 3 日。\n"
            "3. 越阶术式额外折寿 7 日 ~ 90 日（按跨度）。\n\n"
            "解析顺序:\n"
            "A. 若章末已有 [寿元结算: 折寿 X 日 ...] 标记，优先采信。\n"
            "B. 否则按规则估算。\n"
            "C. 如本章为纯回忆 / 对话 / 无任何施术描写，返回 1 日（仅日落被动）。\n\n"
            f"章节正文（第 {ctx.ch_num} 章）:\n{ctx.content[:5000]}\n\n"
            "请直接输出严格 JSON，不要任何前后缀，不要 markdown 代码块，格式:\n"
            '{"days": 1, "breakdown": "日落被动 1 日"}'
        )
        token = f"_cb_lifespan_audit_{ctx.ch_num}"
        cbs = getattr(self.mw, "_one_shot_callbacks", None)
        if cbs is None:
            cbs = {}
            self.mw._one_shot_callbacks = cbs

        def _handler(raw_content):
            days, note = self._parse_ai_json(raw_content)
            self._apply(ctx, days, f"AI 入账: {note}")
            done()

        cbs[token] = _handler
        try:
            self.mw._send_to_ai(prompt, f"寿元入账-第{ctx.ch_num}章", target=token)
        except Exception as e:
            # 发送失败 → 立刻兜底
            cbs.pop(token, None)
            self._apply(ctx, 1, f"AI 发送失败({e})，兜底 1 日")
            done()

    def _parse_ai_json(self, raw: str) -> Tuple[int, str]:
        try:
            extractor = getattr(self.mw, "_extract_json_blob", None)
            text = extractor(raw) if callable(extractor) else raw
            data = json.loads(text)
            days = int(data.get("days", 1))
            breakdown = str(data.get("breakdown", ""))[:120]
            return max(0, days), breakdown
        except Exception:
            return 1, "AI JSON 解析失败，按 1 日兜底"

    # ---- 入账 + 日志 + issue ----
    def _apply(self, ctx, days: int, source: str):
        ledger = self.mw.lifespan_ledger
        ledger["used_days"] = int(ledger.get("used_days", 0)) + int(days)
        ledger.setdefault("history", []).append({
            "ch": int(ctx.ch_num),
            "days": int(days),
            "note": source,
        })

        total = int(ledger.get("total_days", 8760))
        remaining = max(0, total - int(ledger["used_days"]))
        warn = int(ledger.get("warn_threshold", 365))
        critical = int(ledger.get("critical_threshold", 30))

        # 日志
        tab = getattr(self.mw, "tab_generation", None)
        if tab is not None and hasattr(tab, "log"):
            if remaining <= critical:
                icon, level = "🚨", "warn"
            elif remaining <= warn:
                icon, level = "⚠️", "warn"
            else:
                icon, level = "📜", "info"
            tab.log(
                f"{icon} 寿元台账 第{ctx.ch_num}章: -{days} 日 ({source})，剩余 {remaining} 日",
                level,
            )

        # ctx.issues
        if remaining <= critical:
            ctx.issues.append(
                f"主角剩余寿元仅 {remaining} 日（危急阈值 {critical} 日），"
                "请检查本章施术是否过量或主角是否需要立即获取回寿墨等资源。"
            )


# ============================================================
# Step 3 — OpenLoopsCheckStep (POST_WRITE)
# ============================================================

class OpenLoopsCheckStep(PipelineStep):
    """长期伏笔冻结检查 + 关键词自动刷新 last_seen_ch。"""
    name = "open_loops_check"

    def __init__(self, mw):
        self.mw = mw

    def run(self, ctx, done):
        cfg = getattr(self.mw, "open_loops", None)
        if not cfg or not cfg.get("enabled"):
            done(); return
        loops = cfg.get("loops") or []
        if not loops:
            done(); return

        warn_gap = int(cfg.get("warn_gap", 80))
        crit_gap = int(cfg.get("critical_gap", 150))
        content = ctx.content or ""

        # 1) 自动刷新 last_seen_ch（关键词命中）
        for loop in loops:
            if loop.get("status") != "open":
                continue
            kw = (loop.get("keyword") or "").strip()
            if kw and kw in content:
                loop["last_seen_ch"] = int(ctx.ch_num)

        # 2) 计算冻结情况
        frozen = []   # warn 级
        critical = [] # critical 级
        for loop in loops:
            if loop.get("status") != "open":
                continue
            last = int(loop.get("last_seen_ch", loop.get("added_ch", 0)))
            gap = int(ctx.ch_num) - last
            if gap >= crit_gap:
                critical.append((loop, gap))
            elif gap >= warn_gap:
                frozen.append((loop, gap))

        # 3) 日志 + issues
        tab = getattr(self.mw, "tab_generation", None)
        for loop, gap in frozen:
            if tab is not None and hasattr(tab, "log"):
                tab.log(
                    f"⚠️ 长期冻结伏笔（{gap} 章未触及）: "
                    f"{loop.get('desc', '')[:40]}",
                    "warn",
                )
        for loop, gap in critical:
            if tab is not None and hasattr(tab, "log"):
                tab.log(
                    f"🚨 重度冻结伏笔（{gap} 章未触及）: "
                    f"{loop.get('desc', '')[:40]}",
                    "warn",
                )
            ctx.issues.append(
                f"伏笔「{loop.get('desc', '')[:30]}」已 {gap} 章未触及"
                f"（critical_gap={crit_gap}），请尽快回收或显式延期。"
            )
        done()


# ============================================================
# 安装器 —— 统一入口
# ============================================================

class LifespanLoopsExtension:
    """寿元台账 + 长期伏笔扩展的安装 / 存档接口。"""

    @staticmethod
    def install(
        mw,
        *,
        lifespan: bool = True,
        open_loops: bool = True,
        priority_pre_inject: int = 15,
        priority_post_audit: int = 35,
        priority_post_loops: int = 40,
    ) -> bool:
        """把扩展装进 MainWindow。返回 True 表示注册成功。

        priority 说明（数字越小越早跑）:
          - pre_write 默认有 memory_inject(=10) / canon_inject(=20)，
            寿元注入放在 15 — 在 Canon 之前，让 Canon 看到完整 prompt。
          - post_write 默认有 word_count(=10) / hook_check(=20) /
            canon_audit(=30)，寿元入账(=35) 在 Canon 后；
            伏笔检查(=40) 最后跑。
        """
        # 1) 数据初始化（不覆盖已有数据）
        if not hasattr(mw, "lifespan_ledger") or mw.lifespan_ledger is None:
            mw.lifespan_ledger = copy.deepcopy(DEFAULT_LIFESPAN_LEDGER)
        if not hasattr(mw, "open_loops") or mw.open_loops is None:
            mw.open_loops = copy.deepcopy(DEFAULT_OPEN_LOOPS_CFG)
        if not hasattr(mw, "_one_shot_callbacks") or mw._one_shot_callbacks is None:
            mw._one_shot_callbacks = {}

        # 2) workflow 必须存在（与 v7+ 工具链一致）
        wf = getattr(mw, "workflow", None)
        if wf is None or not hasattr(wf, "_registry"):
            return False

        # 3) 注册
        if lifespan:
            wf._registry.register(
                "pre_write",
                LifespanInjectStep(mw),
                priority=priority_pre_inject,
            )
            wf._registry.register(
                "post_write",
                LifespanAuditStep(mw),
                priority=priority_post_audit,
            )
        if open_loops:
            wf._registry.register(
                "post_write",
                OpenLoopsCheckStep(mw),
                priority=priority_post_loops,
            )
        return True

    # -------- 存档 / 读档 --------
    @staticmethod
    def serialize(mw) -> dict:
        return {
            "lifespan_ledger": getattr(mw, "lifespan_ledger", None) or {},
            "open_loops": getattr(mw, "open_loops", None) or {},
        }

    @staticmethod
    def deserialize(mw, data: dict) -> None:
        if not data:
            return
        if "lifespan_ledger" in data and isinstance(data["lifespan_ledger"], dict):
            merged = copy.deepcopy(DEFAULT_LIFESPAN_LEDGER)
            merged.update(data["lifespan_ledger"])
            mw.lifespan_ledger = merged
        if "open_loops" in data and isinstance(data["open_loops"], dict):
            merged = copy.deepcopy(DEFAULT_OPEN_LOOPS_CFG)
            merged.update(data["open_loops"])
            # 单条 loop 也补全字段
            for loop in merged.get("loops", []):
                loop.setdefault("status", "open")
                loop.setdefault("last_seen_ch", loop.get("added_ch", 0))
                loop.setdefault("keyword", "")
            mw.open_loops = merged

    # -------- 主动操作（供 UI / 控制台调用）--------
    @staticmethod
    def add_loop(mw, *, loop_id: str, desc: str, added_ch: int,
                 keyword: str = "", last_seen_ch: Optional[int] = None) -> dict:
        """添加一条伏笔。"""
        if not hasattr(mw, "open_loops") or mw.open_loops is None:
            mw.open_loops = copy.deepcopy(DEFAULT_OPEN_LOOPS_CFG)
        # 防御：避免共享 DEFAULT_OPEN_LOOPS_CFG["loops"] 的同一个 list
        if "loops" not in mw.open_loops or \
                mw.open_loops["loops"] is DEFAULT_OPEN_LOOPS_CFG.get("loops"):
            mw.open_loops["loops"] = []
        loop = {
            "id": loop_id,
            "desc": desc,
            "added_ch": int(added_ch),
            "last_seen_ch": int(last_seen_ch if last_seen_ch is not None else added_ch),
            "keyword": keyword,
            "status": "open",
        }
        mw.open_loops["loops"].append(loop)
        return loop

    @staticmethod
    def close_loop(mw, loop_id: str, ch_num: int) -> bool:
        """把伏笔标记为 closed。"""
        for loop in (mw.open_loops or {}).get("loops", []):
            if loop.get("id") == loop_id:
                loop["status"] = "closed"
                loop["last_seen_ch"] = int(ch_num)
                return True
        return False

    @staticmethod
    def reset_lifespan(mw, total_days: int) -> None:
        """重置寿元台账起始值（开新书或剧情设定调整时用）。"""
        if not hasattr(mw, "lifespan_ledger") or mw.lifespan_ledger is None:
            mw.lifespan_ledger = copy.deepcopy(DEFAULT_LIFESPAN_LEDGER)
        mw.lifespan_ledger["total_days"] = int(total_days)
        mw.lifespan_ledger["used_days"] = 0
        mw.lifespan_ledger["history"] = []


# ------------------------------------------------------------
# 导出
# ------------------------------------------------------------
__all__ = [
    "DEFAULT_LIFESPAN_LEDGER",
    "DEFAULT_OPEN_LOOPS_CFG",
    "LifespanInjectStep",
    "LifespanAuditStep",
    "OpenLoopsCheckStep",
    "LifespanLoopsExtension",
]
