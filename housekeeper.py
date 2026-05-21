# -*- coding: utf-8 -*-
"""
📋 管家(Housekeeper)— 章级元监督

P1 职能:
  1. 聚合现有自动化信号(meta 解析 / 同步 / 抽取 / 13 法扫 / 校验)成"章节健康卡片"
  2. Pipeline 健康度自检:每章应跑的步骤,实际跑了哪些,有没有漂移
  3. 防丢双检:content 长度合理性、元信息剥离前后字数、入库前后是否有断裂
  4. 章末一行日志总结 + Session 汇总面板

P2 职能(v2.08 加,Task 3):
  5. locked 字段一致性巡检 — record_canon_locked_mismatch(field, expected, actual)
       关键 Canon 字段(主角姓名/性别/伴侣等被用户锁定的字段)在章节正文里被
       AI 改了/写错了,管家记录到 mismatches[],oneliner 末尾显示 🔒 警告
  6. 跨章节奏雷达 — check_pacing_window(N=5)
       扫最近 N 章 hook_set / cool_points_count,如果连续 N 章都是 hook=False
       或 cool_points_count=0,提示"节奏疲软,可能套路化",写入 session warnings
  7. 自动备份快照 — snapshot_for_recovery(project_root, ch_num)
       finalize_chapter 时打 zip 快照,扔到 project_root/.backups/snapshot_chXXX_YYYYMMDD_HHMMSS.zip
       默认保留最近 10 份,旧的自动清

P3 职能(v2.09 加,Task 3 接续):
  8. RL 反馈联动 — set_rl_reward_callback(callback)
       注册健康度回调,finalize_chapter 末尾自动 emit health_score 给外部
       (典型用法:用户写 closure 把 score 转成 flow_rl.reward())。
       housekeeper 不 import flow_rl,完全解耦
  9. 二道闸巡查 — verify_defenses(fingerprints, source_paths)
       传入 {bug_id: [code_pattern, ...]} 指纹字典 + 源码路径列表,
       grep 检测每个指纹是否仍在源码里。任何指纹缺失 → hk.warn 提醒,
       并把缺失 BUG 记到 current_report.missing_defenses[]

设计原则:
  - 不替代现有防御代码,只观测和聚合
  - record_xxx 全部 try/except 容错,失败不影响主流程
  - 单测友好:不依赖 PyQt5,纯数据结构
  - P2/P3 全部扩展点"可关"(主程序调用方决定接不接),housekeeper 提供能力不强制
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any, Callable


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
    word_count_ok: Optional[bool] = None     # None = 未检;True = 下限达标(>= 0.8x target);False = 不够
    # v1.95 BUG-069:超长但质量没问题(actual > 1.5x target)— 仍算 ok=True 不扣健康度,
    # oneliner 显示 ⚠ 提醒用户"内容多了"。区分于 ok=False(真不达标)。
    word_count_long: bool = False
    dialogue_critic_reds: int = 0
    dialogue_critic_say_count: int = 0
    dialogue_critic_say_allowed: int = 0

    # 异常/告警
    warnings: List[str] = field(default_factory=list)

    # P2 v2.08:Canon locked 字段不一致(每元素:{"field": "主角姓名", "expected": "...", "actual": "..."})
    locked_mismatches: List[Dict[str, str]] = field(default_factory=list)

    # P3 v2.09:二道闸巡查中检测到的"防御消失"的 BUG ID(每元素 "BUG-027" 等字符串)
    missing_defenses: List[str] = field(default_factory=list)

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

        # P2 v2.08:Canon locked 字段不一致是严重问题(改了用户锁定的设定),每条扣 0.1,封顶 0.3
        lock_penalty = min(0.3, 0.1 * len(self.locked_mismatches))

        # P3 v2.09:历史 BUG 防御消失是高优先级警报,每个扣 0.15,封顶 0.4
        # 比 lock_penalty 重:locked 是数据写错,defense 消失意味着工程级回归(更难发现)
        defense_penalty = min(0.4, 0.15 * len(self.missing_defenses))

        score = 0.6 * pipeline_ratio + 0.4 * hard_ratio - warn_penalty - lock_penalty - defense_penalty
        return max(0.0, min(1.0, score))

    def render_oneliner(self) -> str:
        """章末一行日志总结(给 _accept_chapter_and_continue 输出)"""
        self.health_score = self._compute_health()

        bits = []
        # 字数门(v1.95 BUG-069:三档显示)
        if self.word_count_actual > 0:
            if not self.word_count_ok:
                wc_mark = "✗"        # 不够(< 0.8x target)
            elif self.word_count_long:
                wc_mark = "⚠"        # 超长但达标(> 1.5x target,不扣健康度)
            else:
                wc_mark = "✓"        # 合理(0.8x - 1.5x)
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

        # P2 v2.08:Canon locked 字段不一致(只显示前 2 个字段名)
        if self.locked_mismatches:
            mn = len(self.locked_mismatches)
            field_names = [m.get("field", "?") for m in self.locked_mismatches[:2]]
            shown = "/".join(field_names)
            if mn > 2:
                shown += f" (+{mn - 2})"
            bits.append(f"🔒 锁定字段被改:{shown}")

        # P3 v2.09:二道闸巡查发现的"防御消失"BUG(只显示前 2 个 BUG ID)
        if self.missing_defenses:
            dn = len(self.missing_defenses)
            shown = "/".join(self.missing_defenses[:2])
            if dn > 2:
                shown += f" (+{dn - 2})"
            bits.append(f"🛡️ 防御消失:{shown}")

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
        # P3 v2.09:RL 反馈联动 — 回调钩子(None = 关闭),解耦 flow_rl
        self.rl_reward_callback: Optional[Callable[[float, Dict[str, Any]], None]] = None

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

        # P3 v2.09:RL 反馈联动 — 章末 emit health_score 给注册的回调
        # 失败容错:任何异常吞掉,绝不影响主流程(housekeeper 是观测层)
        try:
            if self.rl_reward_callback is not None:
                self.rl_reward_callback(report.health_score, report.to_dict())
        except Exception:
            pass

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
        """记录字数门校验。
        v1.95 BUG-069 后语义:
          - actual < 0.8 * target → ok=False(真不达标)
          - 0.8 <= actual / target <= 1.5 → ok=True, long=False(合理)
          - actual > 1.5 * target → ok=True, long=True(超长警告 ⚠ 但不扣健康度)
        """
        try:
            if not self.current_report: return
            self.current_report.word_count_target = target
            self.current_report.word_count_actual = actual
            if target > 0:
                lower = int(target * 0.8)
                upper = int(target * 1.5)
                self.current_report.word_count_ok = (actual >= lower)
                # 超长仅在 ok=True 的基础上叠加 ⚠ 标记(超长且达标才有意义;
                # 字数 ok=False 时主要矛盾是不够,不再额外标 long)
                self.current_report.word_count_long = (
                    self.current_report.word_count_ok and actual > upper)
            else:
                self.current_report.word_count_ok = None
                self.current_report.word_count_long = False
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

    # —— P2 v2.08:扩展点 1 — Canon locked 字段一致性巡检 —— #

    def record_canon_locked_mismatch(self, field_name: str, expected: str, actual: str):
        """记录一个 Canon locked 字段被本章正文改了 / 写错了

        典型用法(调用方在 _accept_chapter_and_continue 里):
            for lk in canon_locked_fields:
                if expected != actual_in_chapter:
                    hk.record_canon_locked_mismatch("主角姓名", expected, actual_in_chapter)

        效果:
          - 计入 current_report.locked_mismatches
          - 健康度每条扣 0.1(封顶 0.3)
          - oneliner 末尾显示 🔒
        """
        try:
            if not self.current_report:
                return
            # 截断防爆字段
            self.current_report.locked_mismatches.append({
                "field": str(field_name)[:30],
                "expected": str(expected)[:60],
                "actual": str(actual)[:60],
            })
        except Exception:
            pass

    # —— P2 v2.08:扩展点 2 — 跨章节奏雷达 —— #

    def check_pacing_window(self, n: int = 5) -> Optional[Dict[str, Any]]:
        """扫最近 N 章 hook_set / cool_points_count,检测节奏疲软

        返回:
          None — 历史 < N 章,不够判定
          {} — 节奏正常(hook / cool 至少一个有活力)
          {"flat_hooks": True/False, "flat_cools": True/False, "msg": "..."} — 检测到疲软

        副作用:
          如果检测到疲软,自动 hk.warn() 一条提醒,进 oneliner / session_summary
        """
        try:
            all_reports = list(self.history)
            if len(all_reports) < n:
                return None  # 不够样本
            recent = all_reports[-n:]
            flat_hooks = all(not r.hook_set for r in recent)
            flat_cools = all(r.cool_points_count == 0 for r in recent)
            if not (flat_hooks or flat_cools):
                return {}
            # 节奏雷达检测到疲软
            msgs = []
            if flat_hooks:
                msgs.append(f"连续 {n} 章无章末钩子")
            if flat_cools:
                msgs.append(f"连续 {n} 章无爽点")
            full_msg = "节奏疲软:" + " + ".join(msgs)
            # 不直接进 current_report.warnings(可能没有 current)
            # 改成 session 级:存到 history 末尾 report 的 warnings
            if self.current_report:
                self.current_report.warnings.append(full_msg[:80])
            elif self.history:
                self.history[-1].warnings.append(full_msg[:80])
            return {
                "flat_hooks": flat_hooks,
                "flat_cools": flat_cools,
                "msg": full_msg,
                "window": n,
            }
        except Exception:
            return None

    # —— P2 v2.08:扩展点 3 — 自动备份快照 —— #

    def snapshot_for_recovery(
        self,
        project_root: str,
        ch_num: int,
        keep_last: int = 10,
    ) -> Optional[str]:
        """章节完成时打项目目录的 zip 快照,扔到 project_root/.backups/

        参数:
          project_root: 项目根目录(包含 project.json 和 chapters/ 的那个)
          ch_num:      当前章节号(用于命名)
          keep_last:   保留最近 N 份,旧的自动清(默认 10)

        返回:
          快照文件绝对路径 — 成功
          None — 失败(目录不存在 / zip 写失败 / 等)

        命名:.backups/snapshot_ch{NNN}_{YYYYMMDD_HHMMSS}.zip

        失败容错:任何异常不抛,返回 None。调用方可选择 hk.warn() 提示用户。
        """
        try:
            import os
            import zipfile
            from datetime import datetime
            from pathlib import Path

            root = Path(project_root)
            if not root.is_dir():
                return None
            backup_dir = root / ".backups"
            backup_dir.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"snapshot_ch{ch_num:03d}_{ts}.zip"
            zip_path = backup_dir / zip_name

            # 打包除 .backups/ 本身外的所有内容
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in root.rglob("*"):
                    if not f.is_file():
                        continue
                    # 跳过 .backups/ 子目录本身,避免无限套娃
                    try:
                        rel = f.relative_to(root)
                    except ValueError:
                        continue
                    parts = rel.parts
                    if parts and parts[0] == ".backups":
                        continue
                    zf.write(f, arcname=str(rel))

            # 清理旧快照(只保留最近 keep_last 份)
            try:
                snaps = sorted(
                    backup_dir.glob("snapshot_ch*.zip"),
                    key=lambda p: p.stat().st_mtime,
                )
                while len(snaps) > keep_last:
                    old = snaps.pop(0)
                    try:
                        old.unlink()
                    except Exception:
                        pass
            except Exception:
                pass

            return str(zip_path)
        except Exception:
            return None

    # —— P3 v2.09:扩展点 1 — RL 反馈联动 —— #

    def set_rl_reward_callback(
        self,
        callback: Optional[Callable[[float, Dict[str, Any]], None]],
    ):
        """注册健康度反馈回调,finalize_chapter 末尾自动 emit

        Args:
            callback: 函数,签名 (health_score: float, report_dict: dict) -> None
                      None = 关闭回调

        典型用法(调用方在 MainWindow 初始化时连接 flow_rl):
            def health_to_rl(score, report):
                from flow_rl import FlowRL
                rl = self.flow_rl  # MainWindow 持有的 FlowRL 实例
                # 把健康度转成 reward 值(0.0-1.0 → -20 to +20)
                reward_value = (score - 0.5) * 40
                # 注:具体 state/action 由调用方决定 — housekeeper 不知道
                rl.reward(last_state, last_action, reward_value,
                          reason=f"章末健康度 {score:.2f}")
            hk.set_rl_reward_callback(health_to_rl)

        设计原则:
          - housekeeper 不 import flow_rl(零依赖)
          - 调用方负责"健康度 → 奖励值"的转换公式
          - 调用方负责绑定到具体的 RL state/action(housekeeper 不知道)
          - finalize 末尾 emit 失败完全吞掉,绝不影响主流程
        """
        try:
            # 允许 None(关闭回调)或 callable(注册)
            if callback is not None and not callable(callback):
                return  # 静默拒绝非 callable,符合 housekeeper "失败容错"风格
            self.rl_reward_callback = callback
        except Exception:
            pass

    # —— P3 v2.09:扩展点 2 — 二道闸巡查 —— #

    def verify_defenses(
        self,
        fingerprints: Dict[str, List[str]],
        source_paths: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """验证关键历史 BUG 修复的"代码指纹"是否仍存在于源码里

        典型用法:在 _accept_chapter_and_continue 末尾 + 每 N 章触发一次扫描:
            FINGERPRINTS = {
                "BUG-028": ["_chapter_fingerprint", "已生成过该指纹"],
                "BUG-065": ["CRITICAL_TARGETS", "_build_degraded_content"],
                "BUG-071": ["_pending_task_targets", "dict 路由"],
            }
            result = hk.verify_defenses(FINGERPRINTS, ["novel_ai.py"])
            # result = {"BUG-028": True, "BUG-065": True, "BUG-071": False}
            # 失配的 BUG ID 自动进 current_report.missing_defenses + hk.warn()

        Args:
            fingerprints: {bug_id: [code_pattern1, code_pattern2, ...]}
                          每个 pattern 必须是非空字符串,要求全部出现才算"防御完好"
                          (any 缺失就算"防御消失")
            source_paths: 要扫的源码文件路径列表,默认仅 ["novel_ai.py"]
                          典型扩展:["novel_ai.py", "ui/browser_worker.py", ...]

        Returns:
            {bug_id: bool} — True = 该 BUG 的所有指纹都还在(防御完好)
                            False = 至少一个指纹缺失(防御消失)
                            读不到文件 → 视作 False(保守)

        副作用:
          - 失配的 BUG ID 加到 current_report.missing_defenses(去重)
          - hk.warn(f"⚠ {bug_id} 防御消失") 进 oneliner 末尾
          - oneliner 显示 🛡️ + 失配 BUG ID 列表
          - 健康度按 missing_defenses 数量扣分(每条 0.15,封顶 0.4)

        失败容错:文件读不到 / 任何异常 → 返回保守结果(全 False)不抛
        """
        result: Dict[str, bool] = {}
        try:
            if not fingerprints:
                return result

            # 默认扫主程序
            paths = source_paths if source_paths else ["novel_ai.py"]

            # 一次性读所有源码 concat(避免每个 bug 都重读文件)
            from pathlib import Path
            blob_parts: List[str] = []
            for p in paths:
                try:
                    blob_parts.append(Path(p).read_text(encoding="utf-8"))
                except Exception:
                    # 单个文件读失败不影响其他,但少了一份源 → 后续 in 检测会更保守
                    pass
            blob = "\n".join(blob_parts)

            if not blob:
                # 所有文件都读不到 → 全部 BUG 标 False(保守:防御视作消失)
                for bid in fingerprints:
                    result[bid] = False
                    self._record_missing_defense(bid)
                return result

            # 对每个 BUG,验证所有指纹都出现
            for bid, patterns in fingerprints.items():
                try:
                    if not patterns:
                        result[bid] = False
                        self._record_missing_defense(bid)
                        continue
                    # 必须全部 pattern 都在 blob 里
                    all_present = all(
                        isinstance(pat, str) and pat and (pat in blob)
                        for pat in patterns
                    )
                    result[bid] = all_present
                    if not all_present:
                        self._record_missing_defense(bid)
                except Exception:
                    result[bid] = False
                    self._record_missing_defense(bid)
            return result
        except Exception:
            return result

    def _record_missing_defense(self, bug_id: str):
        """私有:把失配 BUG 记到 current_report.missing_defenses(去重)

        注:不再发 warning — missing_defenses 在 oneliner 末尾用 🛡️ 显示已足够醒目,
        且健康度 defense_penalty(0.15/条)远比 warn_penalty(0.05/条)严厉。
        发 warning 会让 oneliner 出现"⚠ XXX 防御消失 | 🛡️ XXX"重复显示。
        """
        try:
            if not self.current_report:
                return
            bid = str(bug_id)[:30]
            if bid not in self.current_report.missing_defenses:
                self.current_report.missing_defenses.append(bid)
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
