# -*- coding: utf-8 -*-
"""v1.32 BUG-044 测试 — 站点切换偏好绑定"""
import re
from pathlib import Path


def test_site_preferences_table_defined():
    """SITE_PREFERENCES 表必须含 ChatGPT镜像"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert "SITE_PREFERENCES" in src
    assert '"ChatGPT镜像"' in src
    # 必须含 3 个 key
    m = re.search(r'"ChatGPT镜像":\s*\{([^}]+)\}', src)
    assert m, "ChatGPT镜像 偏好块没找到"
    block = m.group(1)
    assert '"auto_save"' in block
    assert '"auto_grab"' in block
    assert '"use_attachment"' in block


def test_chatgpt_mirror_uses_attachment():
    """ChatGPT镜像 必须开附件(关键:绕过审核)"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    m = re.search(r'"ChatGPT镜像":\s*\{([^}]+)\}', src)
    block = m.group(1)
    # 找 use_attachment 那一行
    line_m = re.search(r'"use_attachment":\s*(True|False)', block)
    assert line_m, "use_attachment 行没找到"
    assert line_m.group(1) == "True", "ChatGPT镜像 必须开附件!"


def test_chatgpt_mirror_grabs():
    """ChatGPT镜像 必须开自动抓取回填(否则生成完没东西)"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    m = re.search(r'"ChatGPT镜像":\s*\{([^}]+)\}', src)
    block = m.group(1)
    line_m = re.search(r'"auto_grab":\s*(True|False)', block)
    assert line_m and line_m.group(1) == "True"


def test_on_site_changed_method_exists():
    """_on_site_changed 方法必须存在"""
    src = Path("novel_ai.py").read_text(encoding="utf-8")
    assert "def _on_site_changed(self, name):" in src
    # 必须在 _on_site_changed 里更新 URL
    m = re.search(r"def _on_site_changed.+?(?=\n    def )", src, re.DOTALL)
    assert m
    method_body = m.group(0)
    assert "AI_URLS" in method_body
    assert "SITE_PREFERENCES" in method_body
    assert "showMessage" in method_body   # 状态栏提示
