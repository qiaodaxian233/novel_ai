# -*- coding: utf-8 -*-
"""
test_main_p2p3_integration.py — v2.10 主程序集成 P2/P3 hooks

验证 housekeeper 的 4 个 hook 真接到主程序 _accept_chapter_and_continue 里。
方法:静态扫描 novel_ai.py 源码,确认关键代码模式存在。

集成的 hook:
  1. set_rl_reward_callback + _on_hk_health_to_rl 方法(P3-#10)
  2. record_canon_locked_mismatch(finalize 前,P2-#6)
  3. verify_defenses(DEFENSE_FINGERPRINTS)(每 10 章,P3-#12)
  4. check_pacing_window(n=5)(finalize 后,每 5 章,P2-#7)

未集成(留待后续):
  - snapshot_for_recovery(本项目用 single json 文件,跟 project_root 概念不匹配)

也验证 DEFENSE_FINGERPRINTS 字典本身的完整性。
"""
import unittest
import re
import ast
from pathlib import Path


HERE = Path(__file__).resolve().parent
NOVEL_AI_PATH = HERE / "novel_ai.py"


def _load_source():
    return NOVEL_AI_PATH.read_text(encoding="utf-8")


class TestAppVersionBumped(unittest.TestCase):
    """APP_VERSION 升到 v2.10"""

    def test_version_at_least_v210(self):
        src = _load_source()
        m = re.search(r'APP_VERSION\s*=\s*["\']v(\d+)\.(\d+)(?:\.\d+)?["\']', src)
        self.assertIsNotNone(m)
        major, minor = int(m.group(1)), int(m.group(2))
        self.assertGreaterEqual((major, minor), (2, 10),
                                f"APP_VERSION 应 ≥ v2.10,实际 v{major}.{minor:02d}")


# ============================================================
# DEFENSE_FINGERPRINTS 字典
# ============================================================

class TestDefenseFingerprintsConstant(unittest.TestCase):
    """v2.10:模块级 DEFENSE_FINGERPRINTS 字典存在且格式正确"""

    def test_constant_defined(self):
        src = _load_source()
        self.assertIn("DEFENSE_FINGERPRINTS", src,
                      "novel_ai.py 缺 DEFENSE_FINGERPRINTS 模块级常量")

    def test_dict_structure_via_import(self):
        """实际 import 验证字典结构合法"""
        import sys
        sys.path.insert(0, str(HERE))
        # 用 ast 提取常量定义,避免触发完整 novel_ai 加载(那要 PyQt5)
        tree = ast.parse(_load_source())
        fps_value = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "DEFENSE_FINGERPRINTS":
                        # 用 ast.literal_eval 安全求值
                        try:
                            fps_value = ast.literal_eval(node.value)
                        except Exception as e:
                            self.fail(f"DEFENSE_FINGERPRINTS 不是 literal:{e}")
                        break
        self.assertIsNotNone(fps_value, "找不到 DEFENSE_FINGERPRINTS 赋值")
        self.assertIsInstance(fps_value, dict)
        self.assertGreaterEqual(len(fps_value), 5,
                                "至少应有 5 个 BUG 的指纹(实际可能更多)")
        # 每项必须是 list of str
        for bid, patterns in fps_value.items():
            self.assertIsInstance(bid, str, f"key 必须是字符串:{bid}")
            self.assertTrue(bid.startswith("BUG-"),
                            f"key 应该是 BUG-NNN 格式,实际 {bid}")
            self.assertIsInstance(patterns, list, f"{bid} 的 value 应是 list")
            self.assertGreater(len(patterns), 0, f"{bid} 的指纹 list 不能空")
            for p in patterns:
                self.assertIsInstance(p, str, f"{bid} 的指纹应该是 str:{p}")
                self.assertGreater(len(p), 0, f"{bid} 有空指纹")

    def test_all_fingerprints_real(self):
        """所有指纹真实存在于源码里 — 这是字典本身的自检"""
        import glob
        # 扫主程序 + 子包(模拟 main 集成里 verify_defenses 的扫描范围)
        files = (
            ["novel_ai.py"]
            + glob.glob(str(HERE / "ui/*.py"))
            + glob.glob(str(HERE / "ui/tabs/*.py"))
            + glob.glob(str(HERE / "core/*.py"))
        )
        blob_parts = []
        for f in files:
            try:
                blob_parts.append(Path(f).read_text(encoding="utf-8"))
            except Exception:
                pass
        blob = "\n".join(blob_parts)

        # 提取 DEFENSE_FINGERPRINTS
        tree = ast.parse(_load_source())
        fps = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "DEFENSE_FINGERPRINTS":
                        fps = ast.literal_eval(node.value)
        self.assertIsNotNone(fps)

        for bid, patterns in fps.items():
            for pat in patterns:
                self.assertIn(
                    pat, blob,
                    f"⚠️ 指纹 {bid!r} 的 {pat!r} 在源码里找不到 — "
                    "要么 BUG 已回退(防御消失),要么字典写错了"
                )


# ============================================================
# Hook 1: RL 反馈联动
# ============================================================

class TestRLCallbackHook(unittest.TestCase):
    """v2.10 P3-#10 集成验证:set_rl_reward_callback 被注册"""

    def test_init_registers_callback(self):
        """MainWindow.__init__ 末尾应调用 set_rl_reward_callback"""
        src = _load_source()
        # 关键模式必须存在
        self.assertIn("set_rl_reward_callback", src)
        self.assertIn("self._on_hk_health_to_rl", src)

    def test_callback_method_exists(self):
        """新方法 _on_hk_health_to_rl 应定义在 MainWindow"""
        src = _load_source()
        self.assertIn("def _on_hk_health_to_rl(self", src)

    def test_callback_has_failure_tolerance(self):
        """callback 方法体内必须有 try/except(失败容错)"""
        src = _load_source()
        # 找方法定义起点
        idx = src.find("def _on_hk_health_to_rl(self")
        self.assertGreater(idx, 0)
        # 取方法体前 2000 字符(足够覆盖一般方法体)
        body = src[idx:idx + 2000]
        # 至少有一个 try: 和一个 except Exception
        self.assertIn("try:", body)
        self.assertIn("except Exception", body)


# ============================================================
# Hook 2: Canon locked 一致性巡检
# ============================================================

class TestCanonLockedHook(unittest.TestCase):
    """v2.10 P2-#6 集成验证:record_canon_locked_mismatch 在 finalize 前调"""

    def test_locked_check_called(self):
        src = _load_source()
        self.assertIn("record_canon_locked_mismatch", src)

    def test_uses_tab_canon_parse(self):
        """实现用 tab_canon.parse() 获取结构化 locked 项"""
        src = _load_source()
        # 集成代码必须读 tab_canon.parse()
        self.assertIn("self.tab_canon", src)
        # 集成段附近应该有 "locked" 和 "severity" / "high"
        idx = src.find("record_canon_locked_mismatch")
        # 找到主程序内的实际集成位置(不是 housekeeper.py 里的方法定义)
        # 主程序集成应在 _accept_chapter_and_continue 末尾的 finalize 块内
        # 验证集成段附近有 'high' 严重度检查
        # (housekeeper.py 也包含这个名字,但这里我们扫的是 novel_ai.py)
        # 用更宽松的判定:主程序里这个调用应至少出现一次,且 finalize 之前
        finalize_idx = src.find("_hk.finalize_chapter()")
        self.assertGreater(finalize_idx, 0, "finalize_chapter 调用必须在")
        # locked 一致性巡检必须在 finalize 之前
        # 至少有一处 record_canon_locked_mismatch 调用位置 < finalize_idx
        positions = []
        start = 0
        while True:
            i = src.find("record_canon_locked_mismatch", start)
            if i < 0:
                break
            positions.append(i)
            start = i + 1
        self.assertGreater(len(positions), 0)
        before_finalize = [p for p in positions if p < finalize_idx]
        self.assertGreater(
            len(before_finalize), 0,
            "至少一处 record_canon_locked_mismatch 应在 finalize_chapter 之前"
        )


# ============================================================
# Hook 3: 二道闸巡查
# ============================================================

class TestVerifyDefensesHook(unittest.TestCase):
    """v2.10 P3-#12 集成验证:verify_defenses(DEFENSE_FINGERPRINTS) 每 10 章触发"""

    def test_verify_defenses_called_with_constant(self):
        src = _load_source()
        # verify_defenses 被调用,且第一个参数是 DEFENSE_FINGERPRINTS
        self.assertIn("verify_defenses(DEFENSE_FINGERPRINTS", src)

    def test_triggered_periodically(self):
        """触发条件 % 10 == 0(每 10 章)"""
        src = _load_source()
        # 集成段附近应有 "% 10" 或 "%10"
        idx = src.find("verify_defenses(DEFENSE_FINGERPRINTS")
        self.assertGreater(idx, 0)
        # 在调用前 500 字符内应有 "% 10" 条件
        before = src[max(0, idx - 500):idx]
        self.assertTrue("% 10" in before or "%10" in before,
                        f"verify_defenses 调用前应有 % 10 的频率控制\n附近代码:{before[-200:]}")

    def test_scans_multiple_paths(self):
        """扫的不只是 novel_ai.py,也扫 ui/ 子包(P3~P6 模块化拆分后)"""
        src = _load_source()
        idx = src.find("verify_defenses(DEFENSE_FINGERPRINTS")
        # 调用上下文应有 ui/*.py 或类似的多文件扫描
        ctx = src[max(0, idx - 500):idx + 500]
        self.assertTrue(
            "ui/*.py" in ctx or "ui/tabs/*.py" in ctx or 'ui/' in ctx,
            f"verify_defenses 应扫多个路径(包括 ui/),实际:{ctx[-300:]}"
        )


# ============================================================
# Hook 4: 跨章节奏雷达
# ============================================================

class TestPacingWindowHook(unittest.TestCase):
    """v2.10 P2-#7 集成验证:check_pacing_window(n=5) 每 5 章 finalize 后调"""

    def test_check_pacing_window_called(self):
        src = _load_source()
        # 调用且 n=5
        self.assertIn("check_pacing_window(n=5)", src)

    def test_called_after_finalize(self):
        """check_pacing_window 应在 finalize 之后调(它读 history)"""
        src = _load_source()
        finalize_idx = src.find("_hk.finalize_chapter()")
        pacing_idx = src.find("check_pacing_window(n=5)")
        self.assertGreater(finalize_idx, 0)
        self.assertGreater(pacing_idx, 0)
        # check_pacing_window 必须在 finalize 之后
        self.assertGreater(pacing_idx, finalize_idx,
                           "check_pacing_window(n=5) 必须在 finalize_chapter 之后调")

    def test_triggered_every_5_chapters(self):
        """触发条件 >= 5 and % 5 == 0"""
        src = _load_source()
        idx = src.find("check_pacing_window(n=5)")
        before = src[max(0, idx - 500):idx]
        self.assertTrue("% 5" in before or "%5" in before,
                        f"check_pacing_window 应有 % 5 频率,附近:{before[-200:]}")


# ============================================================
# 不破坏既有功能
# ============================================================

class TestNoRegressionOnPreviousMilestones(unittest.TestCase):
    """v2.10 主程序集成不破坏 v2.09 housekeeper API 和既有功能"""

    def test_housekeeper_module_still_imported(self):
        src = _load_source()
        self.assertIn("import housekeeper", src)
        self.assertIn("HOUSEKEEPER_AVAILABLE", src)

    def test_existing_hk_calls_still_exist(self):
        """v1.90 P1 时的 hk record 调用都还在(start_chapter / record_step 等)"""
        src = _load_source()
        for call in ("start_chapter", "record_content", "record_pangu_meta",
                     "record_step", "record_word_count", "record_dialogue_critic",
                     "finalize_chapter"):
            self.assertIn(call, src, f"既有 hk.{call} 调用消失了")

    def test_v209_methods_in_housekeeper_still_present(self):
        """housekeeper.py 的 P3 方法仍在(v2.09 不被回退)"""
        hk_path = HERE / "housekeeper.py"
        if not hk_path.exists():
            self.skipTest("housekeeper.py not present")
        src = hk_path.read_text(encoding="utf-8")
        self.assertIn("def set_rl_reward_callback", src)
        self.assertIn("def verify_defenses", src)

    def test_flow_rl_still_initialized(self):
        """flow_rl 初始化代码仍在 init(v2.10 没破坏)"""
        src = _load_source()
        self.assertIn("FlowRL(", src)
        self.assertIn("self.flow_rl", src)


# ============================================================
# 顶部 docstring 应该提到 v2.10
# ============================================================

class TestDocstringMentionsV210(unittest.TestCase):
    """v2.10 注释里至少出现一次 'v2.10' 标识符,方便 grep 历史"""

    def test_v210_marker_present(self):
        src = _load_source()
        self.assertIn("v2.10", src,
                      "novel_ai.py 应至少有一处 v2.10 注释标识(便于追溯改动)")


if __name__ == "__main__":
    unittest.main()
