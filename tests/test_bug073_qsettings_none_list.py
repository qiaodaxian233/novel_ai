# -*- coding: utf-8 -*-
"""v2.06 BUG-073 回归测试

起因:
P1 模块化拆分时,沙箱 offscreen 跑 test_v6.py 暴露这个 pre-existing bug:
  ui/tabs/creation_settings.py 的 load_settings() 方法,4 处:
    genres = s.value("genres", [])
    endings = s.value("endings", [])
    gfs = s.value("golden_fingers", [])
    ps = s.value("personas", [])
  Linux PyQt5 + offscreen 下,QSettings 无存档时返回 None 而非 [],
  导致后面 `for n, cb in ...: cb.setChecked(n in gfs)` 抛 TypeError。
  Windows 因为 QSettings 序列化方式差异不触发。

修法(v2.06):
  把 4 处的 `s.value("xxx", [])` 改成 `s.value("xxx", []) or []`,
  None 兜底成 []。最小改动,不影响 Windows 行为。

保障:
  1. 静态扫描:4 处都有 `or []`
  2. APP_VERSION ≥ v2.06
"""
import os
import re
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 仓库根(测试搬迁修复)
NOVEL_AI_PATH = os.path.join(HERE, "novel_ai.py")
CREATION_SETTINGS_PATH = os.path.join(HERE, "ui", "tabs", "creation_settings.py")


class TestQSettingsNoneTolerance(unittest.TestCase):
    """4 处 list 类 QSettings 读取必须有 None 兜底"""

    @classmethod
    def setUpClass(cls):
        with open(CREATION_SETTINGS_PATH, encoding="utf-8") as f:
            cls.src = f.read()

    def test_genres_has_none_fallback(self):
        self.assertRegex(
            self.src,
            r'genres\s*=\s*s\.value\("genres",\s*\[\]\)\s*or\s*\[\]',
            "BUG-073: genres 读取必须有 `or []` 兜底,避免 Linux PyQt5 None 时崩"
        )

    def test_endings_has_none_fallback(self):
        self.assertRegex(
            self.src,
            r'endings\s*=\s*s\.value\("endings",\s*\[\]\)\s*or\s*\[\]',
            "BUG-073: endings 读取必须有 `or []` 兜底"
        )

    def test_golden_fingers_has_none_fallback(self):
        self.assertRegex(
            self.src,
            r'gfs\s*=\s*s\.value\("golden_fingers",\s*\[\]\)\s*or\s*\[\]',
            "BUG-073: golden_fingers 读取必须有 `or []` 兜底"
        )

    def test_personas_has_none_fallback(self):
        self.assertRegex(
            self.src,
            r'ps\s*=\s*s\.value\("personas",\s*\[\]\)\s*or\s*\[\]',
            "BUG-073: personas 读取必须有 `or []` 兜底"
        )

    def test_no_raw_pattern_remaining(self):
        """确保没有遗漏的同模式裸读取(防止后续重新引入)"""
        # 找所有 `xxx = s.value("yyy", [])` 不带 or [] 的
        risky = re.findall(
            r'(\w+)\s*=\s*s\.value\("(\w+)",\s*\[\]\)(?!\s*or)',
            self.src
        )
        # 这里允许 style_sliders, _custom_xxx 等 dict 默认值;只检查跟 cb.setChecked 配对的 list
        risky_for_in = []
        for var, key in risky:
            # 看后面有没有 `n in var` 模式(典型用法)
            if re.search(rf'\bn\s+in\s+{re.escape(var)}\b', self.src):
                risky_for_in.append((var, key))
        self.assertEqual(
            risky_for_in, [],
            f"BUG-073 回归:发现新的裸 `s.value(?, [])` 读取后面被用作 `n in ?`,会在 Linux PyQt5 None 时崩:{risky_for_in}"
        )


class TestAppVersionBumped(unittest.TestCase):
    """v2.06 修了 BUG-073 → APP_VERSION 必须 ≥ v2.06"""

    def test_version_bumped(self):
        with open(NOVEL_AI_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("APP_VERSION"):
                    m = re.search(r'v(\d+)\.(\d+)', line)
                    self.assertIsNotNone(m, "APP_VERSION 应该匹配 vX.YZ 格式")
                    major, minor = int(m.group(1)), int(m.group(2))
                    self.assertGreaterEqual(
                        (major, minor), (2, 6),
                        f"BUG-073 修复后 APP_VERSION 必须 ≥ v2.06,当前 {line.strip()}"
                    )
                    return
        self.fail("没找到 APP_VERSION 行")


if __name__ == "__main__":
    unittest.main(verbosity=2)
