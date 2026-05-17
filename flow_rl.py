# -*- coding: utf-8 -*-
"""
盘古流程强化学习管理器 (Contextual Bandit + Q-learning 简化版)

设计原则:
- 小样本友好 (用 ε-greedy 探索, 不需要神经网络)
- 实时学习 (每次决策 → 立即反馈打分)
- 持久化 (Q 表存 QSettings, 程序重启后继续学习)
- 零依赖 (纯 Python + PyQt5 QSettings, 不依赖 numpy/torch)

奖励规则:
- 任务成功完成: +10
- 章节字数达标: +5
- 章节字数严重不足 (<500 字, 抓取错位): -15
- 死磕重写一次: -3
- AI 误点停止按钮: -20
- 程序卡死/死循环: -30
- 一次性写出合格章节(无死磕): +20

状态 (state) = (task_type, ai_provider, attempt_num)
动作 (action) = 一组离散决策:
- send_wait: Enter 后等多久 (1.5s/3s/5s)
- stable_threshold: 内容稳定判定阈值 (0.9s/1.5s/4s)
- post_emit_wait: emit 前 AI 空闲连续确认次数 (1/3/5)
- use_strategy_b: 失败时是否走策略 B 兜底 (是/否)

用法:
    from flow_rl import FlowRL
    rl = FlowRL()
    
    # 决策
    action = rl.choose_action(state=("chapter", "deepseek", 0))
    wait_secs = action["send_wait"]
    
    # 反馈
    rl.reward(state, action, +10, reason="章节生成成功")
    
    # 查看学习状态
    print(rl.summary())
"""
import json
import random
import time
from collections import defaultdict
from typing import Dict, Tuple, Any, Optional, List


# 动作空间定义
ACTION_SPACE = {
    "send_wait": [1.5, 3.0, 5.0],          # Enter 后等多久检测发送
    "stable_threshold": [0.9, 1.5, 4.0],   # 内容稳定判定阈值
    "post_emit_wait": [1, 3, 5],           # emit 前 AI 空闲连续确认次数
    "use_strategy_b": [True, False],       # 失败时是否走策略 B
}

# 默认动作(冷启动用)
DEFAULT_ACTION = {
    "send_wait": 3.0,
    "stable_threshold": 1.5,
    "post_emit_wait": 3,
    "use_strategy_b": False,
}


def action_to_key(action: Dict[str, Any]) -> str:
    """动作字典 → 字符串 key(用于 Q 表索引)"""
    parts = []
    for k in sorted(action.keys()):
        v = action[k]
        parts.append(f"{k}={v}")
    return "|".join(parts)


def key_to_action(key: str) -> Dict[str, Any]:
    """反序列化"""
    action = {}
    for part in key.split("|"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        # 类型推断
        if v in ("True", "False"):
            action[k] = (v == "True")
        else:
            try:
                action[k] = float(v) if "." in v else int(v)
            except ValueError:
                action[k] = v
    return action


def state_to_key(state: Tuple) -> str:
    """状态元组 → 字符串"""
    return "|".join(str(x) for x in state)


def enumerate_all_actions() -> List[Dict[str, Any]]:
    """枚举所有动作组合(状态空间小,可以全枚举)"""
    keys = list(ACTION_SPACE.keys())
    values_lists = [ACTION_SPACE[k] for k in keys]
    actions = []

    def _rec(idx, current):
        if idx == len(keys):
            actions.append(dict(current))
            return
        for v in values_lists[idx]:
            current[keys[idx]] = v
            _rec(idx + 1, current)
            del current[keys[idx]]

    _rec(0, {})
    return actions


class FlowRL:
    """Contextual Bandit + Q-Learning 简化版

    Q[state][action] = 累积平均奖励
    用 ε-greedy 平衡探索(随机试)和利用(选历史最好的)。
    """

    def __init__(self, epsilon: float = 0.15, learning_rate: float = 0.3,
                 persist_settings=None):
        """
        epsilon: 探索率(0-1),0.15 = 15% 随机探索, 85% 选最优
        learning_rate: 学习率(Q 值更新速度), 0.3 = 中等速度
        persist_settings: 可选的 QSettings 实例,用于持久化
        """
        self.epsilon = epsilon
        self.lr = learning_rate
        # Q[state_key][action_key] = (avg_reward, count)
        self.q_table: Dict[str, Dict[str, Tuple[float, int]]] = defaultdict(dict)
        self.persist = persist_settings
        self.all_actions = enumerate_all_actions()
        # 历史记录(最近 100 条决策)
        self.history: List[Dict] = []
        self._load()

    # ---------- 决策 ----------
    def choose_action(self, state: Tuple,
                      task_label: str = "") -> Dict[str, Any]:
        """根据当前状态选择动作

        策略:
        - 该 state 没历史 → 用 DEFAULT_ACTION(冷启动)
        - 探索(随机): 概率 epsilon
        - 利用: 选 Q 值最高的动作
        """
        s_key = state_to_key(state)
        q_for_state = self.q_table.get(s_key, {})

        # 冷启动:state 完全没经验
        if not q_for_state:
            chosen = dict(DEFAULT_ACTION)
            reason = "cold_start"
        elif random.random() < self.epsilon:
            # 探索
            chosen = random.choice(self.all_actions)
            reason = "explore"
        else:
            # 利用:选 Q 值最高的
            best_key = max(q_for_state.keys(),
                           key=lambda k: q_for_state[k][0])
            chosen = key_to_action(best_key)
            reason = f"exploit(Q={q_for_state[best_key][0]:.1f})"

        # 记录到历史
        self.history.append({
            "ts": time.time(),
            "state": s_key,
            "action": action_to_key(chosen),
            "reason": reason,
            "task_label": task_label,
            "reward": None,  # 待 reward() 填
        })
        if len(self.history) > 200:
            self.history = self.history[-200:]
        return chosen

    # ---------- 反馈(奖励/惩罚)----------
    def reward(self, state: Tuple, action: Dict[str, Any],
               value: float, reason: str = ""):
        """给某个 (state, action) 反馈奖励/惩罚

        Q 值更新公式(增量平均):
            Q_new = Q_old + lr * (reward - Q_old)
        """
        s_key = state_to_key(state)
        a_key = action_to_key(action)
        old_q, count = self.q_table[s_key].get(a_key, (0.0, 0))
        new_q = old_q + self.lr * (value - old_q)
        self.q_table[s_key][a_key] = (new_q, count + 1)

        # 回填到最近一条 history
        for h in reversed(self.history):
            if (h["state"] == s_key and h["action"] == a_key
                    and h["reward"] is None):
                h["reward"] = value
                h["reward_reason"] = reason
                break

        self._save()

    # ---------- 学习状态总结 ----------
    def summary(self) -> str:
        """返回学习状态摘要,用于在 UI 上显示"""
        # 已反馈的决策(写进 Q 表的)
        rewarded_decisions = sum(
            sum(c for _, c in actions.values())
            for actions in self.q_table.values())
        # 已发生的决策(包括还没反馈的)
        total_history = len(self.history)
        # 等待反馈中的决策(决策了但还没 reward)
        pending_feedback = sum(
            1 for h in self.history if h.get("reward") is None)
        total_states = len(self.q_table)
        recent = self.history[-20:]
        total_reward = sum(
            h["reward"] for h in self.history if h["reward"] is not None)
        avg_recent = (
            sum(h["reward"] for h in recent if h["reward"] is not None)
            / max(1, sum(1 for h in recent if h["reward"] is not None))
        ) if recent else 0.0

        # 最近几次决策详情(看 RL 在干什么)
        recent_lines = []
        for h in self.history[-5:]:
            r = h.get("reward")
            r_str = f"奖励={r:+.0f}" if r is not None else "(待反馈)"
            label = h.get("task_label", "") or h.get("state", "")
            recent_lines.append(
                f"  · [{h.get('reason', '?')}] {label[:30]} → {r_str}")

        # 各 state 当前最优动作
        best_actions_per_state = []
        for s_key, actions in self.q_table.items():
            if not actions:
                continue
            best_a = max(actions.keys(), key=lambda k: actions[k][0])
            best_q, best_n = actions[best_a]
            best_actions_per_state.append(
                f"  {s_key}:  动作=[{best_a}], Q={best_q:.1f}, n={best_n}")

        diagnosis = ""
        if total_history == 0 and rewarded_decisions == 0:
            diagnosis = (
                "\n⚠ 诊断:RL 完全没被触发\n"
                "可能原因:\n"
                "  1. self.worker.flow_rl 没设置上 → 重启程序\n"
                "  2. _send_prompt 走了不查 RL 的路径\n"
                "  3. 没用到章节生成功能(只测了别的)\n")
        elif total_history > 0 and rewarded_decisions == 0:
            diagnosis = (
                f"\n⚠ 诊断:决策有({total_history} 次)但反馈没接上\n"
                "可能原因:\n"
                "  1. 章节生成没走 _accept_chapter_and_continue\n"
                "  2. 任务被中断(stop)没正常完成\n"
                "  3. reward() 调用时异常被吞了\n")

        return (
            f"📊 流程 RL 学习状态\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"已发生的决策: {total_history}\n"
            f"  · 等待反馈中: {pending_feedback}\n"
            f"  · 已学习(进 Q 表): {rewarded_decisions}\n"
            f"已学习的 state 数: {total_states}\n"
            f"累计奖励: {total_reward:+.1f}\n"
            f"最近 20 次平均奖励: {avg_recent:+.2f}\n"
            + diagnosis
            + (f"\n最近决策:\n" + "\n".join(recent_lines) if recent_lines else "")
            + f"\n\n各 state 最优动作:\n"
            + ("\n".join(best_actions_per_state[:10]) or "  (尚无)")
            + ("\n  ...(更多省略)" if len(best_actions_per_state) > 10 else "")
        )

    def reset(self):
        """清空所有学习成果(慎用)"""
        self.q_table.clear()
        self.history.clear()
        self._save()

    # ---------- 持久化 ----------
    def _save(self):
        if self.persist is None:
            return
        try:
            # 序列化 Q 表(转成普通 dict)
            q_serial = {}
            for s, actions in self.q_table.items():
                q_serial[s] = {a: list(v) for a, v in actions.items()}
            self.persist.setValue(
                "flow_rl_q_table", json.dumps(q_serial))
            self.persist.setValue(
                "flow_rl_history", json.dumps(self.history[-100:]))
        except Exception as e:
            print(f"[FlowRL] 保存失败: {e}")

    def _load(self):
        if self.persist is None:
            return
        try:
            q_str = self.persist.value("flow_rl_q_table", "", type=str)
            if q_str:
                data = json.loads(q_str)
                for s, actions in data.items():
                    self.q_table[s] = {a: tuple(v) for a, v in actions.items()}
            h_str = self.persist.value("flow_rl_history", "", type=str)
            if h_str:
                self.history = json.loads(h_str)
        except Exception as e:
            print(f"[FlowRL] 加载失败,从头开始: {e}")


# ---------- 奖励常量(主程序用)----------
REWARDS = {
    "chapter_success_first_try":  +25,  # 一次性写出合格章节(无死磕)
    "chapter_success_after_retry": +10,  # 死磕后才合格
    "chapter_word_count_ok":       +5,  # 字数达标
    "chapter_word_count_short":   -15,  # 字数严重不足(<500 字, 疑似抓取错位)
    "retry_needed":                -3,  # 死磕重写一次
    "task_send_success":           +2,  # 任务发送成功
    "task_send_failed":            -8,  # 任务发送失败(走兜底)
    "stop_button_pressed":        -20,  # 误点停止按钮
    "ai_idle_timeout":             -5,  # AI 空闲等待超时
    "continue_gen_clicked_ok":     +3,  # 继续生成点击成功
    "continue_gen_failed":         -8,  # 继续生成连续 3 次都点不动
    "stuck_dead_loop":            -30,  # 死循环卡死
    "json_task_success":           +5,  # JSON 短任务(节奏/人设稽核)成功
}


# ---------- 单元测试 ----------
def _self_test():
    """自测:不依赖 QSettings,验证 RL 基本逻辑"""
    print("=== FlowRL 自测 ===")
    rl = FlowRL(epsilon=0.0)  # 关闭探索,纯利用

    # 测试 1:冷启动用 DEFAULT_ACTION
    s = ("chapter", "deepseek", 0)
    a1 = rl.choose_action(s, "测试章节 1")
    assert a1 == DEFAULT_ACTION, f"冷启动应该用默认,实际 {a1}"
    print("✓ 冷启动用默认动作")

    # 测试 2:给一次正反馈,Q 值变化
    rl.reward(s, a1, +10, "章节成功")
    s_key = state_to_key(s)
    a_key = action_to_key(a1)
    assert s_key in rl.q_table
    assert a_key in rl.q_table[s_key]
    q_value, n = rl.q_table[s_key][a_key]
    assert q_value > 0, f"正反馈后 Q 应该 > 0,实际 {q_value}"
    print(f"✓ 正反馈后 Q={q_value:.2f},计数={n}")

    # 测试 3:同 state 第二次选最优动作
    a2 = rl.choose_action(s, "测试章节 2")
    assert a2 == a1, f"第二次应选已知最优,实际 {a2}"
    print("✓ 第二次选已学到的最优动作")

    # 测试 4:负反馈降低 Q
    rl.reward(s, a2, -5, "失败")
    new_q, _ = rl.q_table[s_key][a_key]
    assert new_q < q_value, f"负反馈应降低 Q,旧={q_value:.2f} 新={new_q:.2f}"
    print(f"✓ 负反馈后 Q={new_q:.2f}(从 {q_value:.2f} 降下来)")

    # 测试 5:动作空间枚举
    all_a = enumerate_all_actions()
    expected = 1
    for v in ACTION_SPACE.values():
        expected *= len(v)
    assert len(all_a) == expected, f"动作数 {len(all_a)} != {expected}"
    print(f"✓ 动作空间 {len(all_a)} 个组合")

    # 测试 6:序列化往返
    a = {"send_wait": 1.5, "use_strategy_b": True, "post_emit_wait": 3}
    k = action_to_key(a)
    a2 = key_to_action(k)
    assert a == a2, f"序列化往返失败:{a} != {a2}"
    print(f"✓ 序列化往返 OK: {k} → {a2}")

    print("\n📊 学习状态:")
    print(rl.summary())
    print("\n=== 全部测试通过 ✓ ===")


if __name__ == "__main__":
    _self_test()
