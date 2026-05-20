# -*- coding: utf-8 -*-
"""
📋 管家(Housekeeper)— 章级元监督

P1 职能:
  1. 聚合现有自动化信号(meta 解析 / 同步 / 抽取 / 13 法扫 / 校验)成"章节健康卡片"
  2. Pipeline 健康度自检:每章应跑的步骤,实际跑了哪些,有没有漂移
  3. 防丢双检:content 长度合理性、元信息剥离前后字数、入库前后是否有断裂
  4. 章末一行日志总结 + Session 汇总面板

设计原则:
  - 不替代现有防御代码,只观测和聚合
  - record_xxx 全部 try/except 容错,失败不影响主流程
  - 单测友好:不依赖 PyQt5,纯数据结构

P2/P3 留扩展点:
  - record_canon_locked_mismatch(字段, 期望值, 实际值)— 一致性巡检
  - check_pacing_window(最近N章)— 节奏雷达
  - snapshot_for_recovery() — 全量备份钩子
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any


# ====== 已知 pipeline 步骤(对应 _accept_chapter_and_continue 各 sync) ======
PIPELINE_STEPS = [
    "pangu_meta_parse",      # 解析章节尾部元信息
    "body_clean_strip",      # 元信息剥离
    "seeds_sync_lifespan",   # 伏笔 → lifespan_loops
    "hook_cool_sync",        # 钩子+爽点 → 角色与世界
    "auto_save",             # 自动保存到 disk
    "dialogue_critic_scan",  # 13 法静态扫描
    "post_chapter_chain",    # 后置链(canon 抽取 / 摘要 / 技能)
    "canon_extract",         # 6 库自动抽取
    "summary_generate",      # 章摘要生成
]


@dataclass
class HousekeeperReport:
    """单章管家审计报告"""
    chapter_num: int
    timestamp: float = field(default_factory=time.time)
    path_tag: str = "main"   # "main"(老路径) or "workflow"(新路径)

    # Pipeline 健康度
    pipeline_ran: Dict[str, bool] = field(default_factory=dict)

    # 内容防丢
    content_len_raw: int = 0          # AI 抓取原文长度
    content_len_normalized: int = 0   # 去空白后正文长度
    pangu_meta_stripped_chars: int = 0  # 剥离了多少字元信息

    # 元信息(钩子/爽点/伏笔/选项)
    hook_set: bool = False
    cool_points_count: int = 0
    seeds_planted: int = 0
    seeds_closed: int = 0
    next_options_count: int = 0

    # 6 库抽取(填充自 canon_extract 链)
    extracts: Dict[str, int] = field(default_factory=dict)

    # 硬性条件
    word_count_target: int = 0
    word_count_actual: int = 0
    word_count_ok: Optional[bool] = None     # None = 未检
    dialogue_critic_reds: int = 0
    dialogue_critic_say_count: int = 0
    dialogue_critic_say_allowed: int = 0

    # 异常/告警
    warnings: List[str] = field(default_factory=list)

    # 健康度评分(0.0-1.0)
    health_score: float = 0.0

    # —— 工具方法 —— #

    def _compute_health(self) -> float:
        """0.0 - 1.0,综合 pipeline 完成度 + 硬性条件 + 异常数"""
        pipeline_total = max(1, len(PIPELINE_STEPS))
        pipeline_ok = sum(1 for v in self.pipeline_ran.values() if v)
        # 不强求所有步骤都跑(比如 auto_save 用户关了),但记录占比
        pipeline_ratio = pipeline_ok / pipeline_total

        hard_ratio = 1.0
        if self.word_count_ok is False:
            hard_ratio -= 0.3
        if self.dialogue_critic_reds > 5:
            hard_ratio -= 0.2
        elif self.dialogue_critic_reds > 0:
            hard_ratio -= 0.1
        hard_ratio = max(0.0, hard_ratio)

        warn_penalty = min(0.3, 0.05 * len(self.warnings))

        score = 0.6 * pipeline_ratio + 0.4 * hard_ratio - warn_penalty
        return max(0.0, min(1.0, score))

    def render_oneliner(self) -> str:
        """章末一行日志总结(给 _accept_chapter_and_continue 输出)"""
        self.health_score = self._compute_health()

        bits = []
        # 字数门
        if self.word_count_actual > 0:
            wc_mark = "✓" if self.word_count_ok else "✗"
            bits.append(f"字数{wc_mark}{self.word_count_actual}")

        # 元信息
        meta_bits = []
        if self.hook_set: meta_bits.append("钩")
        if self.cool_points_count > 0: meta_bits.append(f"爽×{self.cool_points_count}")
        if self.seeds_planted > 0: meta_bits.append(f"埋{self.seeds_planted}")
        if self.seeds_closed > 0: meta_bits.append(f"收{self.seeds_closed}")
        if self.next_options_count > 0: meta_bits.append(f"选×{self.next_options_count}")
        if meta_bits: bits.append("/".join(meta_bits))

        # 6 库
        if self.extracts:
            ext_bits = [f"+{k}×{v}" for k, v in self.extracts.items() if v > 0]
            if ext_bits: bits.append(" ".join(ext_bits))

        # 13 法
        if self.dialogue_critic_say_count > 0 or self.dialogue_critic_say_allowed > 0:
            mark = "✓" if self.dialogue_critic_reds == 0 else f"✗×{self.dialogue_critic_reds}"
            bits.append(
                f"13法{mark}(说/道 {self.dialogue_critic_say_count}/{self.dialogue_critic_say_allowed})"
            )

        # Pipeline 健康度
        pipeline_total = sum(1 for v in self.pipeline_ran.values())
        pipeline_ok = sum(1 for v in self.pipeline_ran.values() if v)
        if pipeline_total > 0:
            pipe_pct = int(100 * pipeline_ok / pipeline_total)
            bits.append(f"pipe {pipeline_ok}/{pipeline_total}({pipe_pct}%)")

        # 告警(只显示前 2 条避免刷屏)
        if self.warnings:
            wn = len(self.warnings)
            shown = " · ".join(self.warnings[:2])
            if wn > 2:
                shown += f" (+{wn - 2})"
            bits.append(f"⚠ {shown}")

        # 健康度
        health_mark = "🟢" if self.health_score >= 0.85 else \
                      "🟡" if self.health_score >= 0.65 else "🔴"
        bits.append(f"{health_mark}{int(self.health_score * 100)}%")

        return f"🛎 第{self.chapter_num}章管家:" + " | ".join(bits)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class Housekeeper:
    """章级管家 — 聚合 pipeline 信号,生成日报"""

    def __init__(self):
        self.current_report: Optional[HousekeeperReport] = None
        self.history: List[HousekeeperReport] = []
        self.session_start = time.time()

    # —— 章节生命周期 —— #

    def start_chapter(self, ch_num: int, path_tag: str = "main") -> HousekeeperReport:
        """章节开始生成时调用。返回的 report 会被填充直到 finalize。"""
        # 防御:如果上一个 report 没 finalize 就开新章,先收尾(常见于死磕重写场景)
        if self.current_report and self.current_report.chapter_num == ch_num:
            # 同章覆盖(retry 情况)— 不新建,继续填充
            return self.current_report
        if self.current_report:
            self.current_report.warnings.append("上一章未正常 finalize")
            self._archive_current()
        self.current_report = HousekeeperReport(
            chapter_num=ch_num, path_tag=path_tag)
        return self.current_report

    def finalize_chapter(self) -> Optional[HousekeeperReport]:
        """章节流程结束时调用。返回最终报告。"""
        if not self.current_report:
            return None
        self.current_report.health_score = self.current_report._compute_health()
        report = self.current_report
        self._archive_current()
        return report

    def _archive_current(self):
        if self.current_report:
            self.history.append(self.current_report)
            self.current_report = None

    # —— record 接口(失败容错,不影响主流程)—— #

    def record_content(self, raw: str, body_clean: str = None):
        """记录原文长度 + 剥离元信息后长度"""
        try:
            if not self.current_report: return
            self.current_report.content_len_raw = len(raw or "")
            cb = body_clean if body_clean is not None else raw or ""
            self.current_report.content_len_normalized = len(cb)
            self.current_report.pangu_meta_stripped_chars = max(
                0, len(raw or "") - len(cb))
            self.record_step("body_clean_strip", True)
        except Exception:
            pass

    def record_pangu_meta(self, meta: Dict[str, Any]):
        """记录从 pangu meta 解析出的钩子/爽点/伏笔等"""
        try:
            if not self.current_report or not meta: return
            self.current_report.hook_set = bool(meta.get("hook"))
            self.current_report.cool_points_count = len(meta.get("cool_points") or [])
            self.current_report.seeds_planted = len(meta.get("seeds_planted") or [])
            self.current_report.seeds_closed = len(meta.get("seeds_paid") or [])
            self.current_report.next_options_count = len(meta.get("next_options") or [])
            self.record_step("pangu_meta_parse", True)
        except Exception:
            pass

    def record_pangu_meta_failed(self, reason: str = ""):
        """元信息解析失败"""
        try:
            if not self.current_report: return
            self.record_step("pangu_meta_parse", False)
            if reason:
                self.current_report.warnings.append(f"元信息解析失败:{reason}")
        except Exception:
            pass

    def record_step(self, step_name: str, ok: bool):
        """记录某 pipeline 步骤是否跑了"""
        try:
            if not self.current_report: return
            self.current_report.pipeline_ran[step_name] = bool(ok)
        except Exception:
            pass

    def record_extract(self, table: str, count: int):
        """记录 6 库抽取新增条数。table: 'chars'/'rels'/'timeline'/'items'/'power'/'seeds'"""
        try:
            if not self.current_report: return
            if count > 0:
                self.current_report.extracts[table] = (
                    self.current_report.extracts.get(table, 0) + count)
        except Exception:
            pass

    def record_word_count(self, target: int, actual: int):
        """记录字数门校验"""
        try:
            if not self.current_report: return
            self.current_report.word_count_target = target
            self.current_report.word_count_actual = actual
            # 字数下限:target 的 80% 起跳(用户偏好可改)
            self.current_report.word_count_ok = (
                actual >= int(target * 0.8) if target > 0 else None)
        except Exception:
            pass

    def record_dialogue_critic(self, reds: int, say_count: int, say_allowed: int):
        """记录 13 法静态扫描结果"""
        try:
            if not self.current_report: return
            self.current_report.dialogue_critic_reds = reds
            self.current_report.dialogue_critic_say_count = say_count
            self.current_report.dialogue_critic_say_allowed = say_allowed
            self.record_step("dialogue_critic_scan", True)
        except Exception:
            pass

    def warn(self, msg: str):
        """记录告警(走 oneliner 末尾)"""
        try:
            if not self.current_report:
                return
            self.current_report.warnings.append(str(msg)[:80])
        except Exception:
            pass

    # —— Session 汇总 —— #

    def session_summary(self) -> Dict[str, Any]:
        """全 session 累计"""
        all_reports = list(self.history)
        if self.current_report:
            all_reports.append(self.current_report)
        if not all_reports:
            return {
                "chapters": 0,
                "session_minutes": (time.time() - self.session_start) / 60,
            }

        # 平均健康度
        scores = [r._compute_health() for r in all_reports]
        avg_health = sum(scores) / len(scores)

        # 累计统计
        total_extracts = {}
        for r in all_reports:
            for k, v in r.extracts.items():
                total_extracts[k] = total_extracts.get(k, 0) + v

        total_seeds_p = sum(r.seeds_planted for r in all_reports)
        total_seeds_c = sum(r.seeds_closed for r in all_reports)
        total_warns = sum(len(r.warnings) for r in all_reports)

        # 失败/红线章节
        failed = [r.chapter_num for r in all_reports
                  if r._compute_health() < 0.65]

        return {
            "chapters": len(all_reports),
            "session_minutes": round((time.time() - self.session_start) / 60, 1),
            "avg_health": round(avg_health, 3),
            "extracts": total_extracts,
            "seeds_planted": total_seeds_p,
            "seeds_closed": total_seeds_c,
            "warnings_total": total_warns,
            "weak_chapters": failed,
        }

    def render_session_summary(self) -> str:
        """文本化 session 汇总,给 UI / log 用"""
        s = self.session_summary()
        if s["chapters"] == 0:
            return "📋 管家:本次会话还没生成任何章节"

        health_pct = int(s["avg_health"] * 100)
        health_mark = "🟢" if s["avg_health"] >= 0.85 else \
                      "🟡" if s["avg_health"] >= 0.65 else "🔴"

        lines = [
            f"📋 管家 · 本次会话汇总({s['session_minutes']} 分钟)",
            f"  章节产出:{s['chapters']} 章 · 平均健康度 {health_mark} {health_pct}%",
        ]

        if s["seeds_planted"] or s["seeds_closed"]:
            lines.append(
                f"  伏笔:埋 {s['seeds_planted']} 收 {s['seeds_closed']} "
                f"({'闭环良好' if s['seeds_closed'] >= s['seeds_planted'] * 0.7 else '收雷较慢,留意超期'})"
            )

        if s["extracts"]:
            ext_bits = [f"{k}+{v}" for k, v in s["extracts"].items()]
            lines.append(f"  6 库累计抽取:{' '.join(ext_bits)}")

        if s["warnings_total"]:
            lines.append(f"  ⚠ 累计告警 {s['warnings_total']} 条")

        if s["weak_chapters"]:
            ch_list = ",".join(f"第{n}章" for n in s["weak_chapters"][:5])
            more = f" 等 {len(s['weak_chapters'])} 章" if len(s["weak_chapters"]) > 5 else ""
            lines.append(f"  🔴 健康度偏低章节:{ch_list}{more}")

        return "\n".join(lines)


# 单例(供 novel_ai.py 直接 import 使用)
_default_instance: Optional[Housekeeper] = None


def get_housekeeper() -> Housekeeper:
    """获取默认管家实例(单例)"""
    global _default_instance
    if _default_instance is None:
        _default_instance = Housekeeper()
    return _default_instance


def reset_housekeeper():
    """重置(主要给测试用)"""
    global _default_instance
    _default_instance = None
