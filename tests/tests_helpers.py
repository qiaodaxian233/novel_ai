# -*- coding: utf-8 -*-
"""测试辅助模块 — 统一源代码加载器

v2.07 适配模块化拆分后的静态扫描:
v2.00~v2.05 的 P1~P6 把 novel_ai.py 中的大量代码外迁到 core/ + ui/ + ui/tabs/
导致原来 `open("novel_ai.py").read()` 的扫描方式找不到那些迁走的符号。

这个 helper 提供 read_all_sources() 把所有源文件 concat 起来,
供静态扫描使用,等价于"扫整个项目的代码"。

不影响真实模块导入(测试用 `import novel_ai` 时仍走正常 Python import,
get 到的是分散在多文件的类/函数 — 行为没变,只是扫描视角统一了)。
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # tests/ 的上一级 = 仓库根(测试搬迁修复)
def read_all_sources():
    """返回 novel_ai.py + 所有 ui/ + core/ 子模块 concat 起来的源文本
    
    用法:
        from tests_helpers import read_all_sources
        src = read_all_sources()
        # 现在 src 包含主程序 + PROMPTS / SITE_PROFILES / CharacterLibrary / 
        # BrowserWorker / 8 个 Tab / 等所有外迁内容
    """
    parts = []
    parts.append((ROOT / "novel_ai.py").read_text(encoding="utf-8"))
    for sub in ("core", "ui", "ui/tabs"):
        d = ROOT / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name == "__init__.py":
                continue
            parts.append(f.read_text(encoding="utf-8"))
    return "\n\n# ============ FILE BOUNDARY ============\n\n".join(parts)


def read_source(*module_paths):
    """读指定的源文件(相对仓库根),返回 concat 文本
    
    用法:
        # 只读主程序 + creation_settings
        src = read_source("novel_ai.py", "ui/tabs/creation_settings.py")
    """
    parts = []
    for p in module_paths:
        full = ROOT / p
        if full.exists():
            parts.append(full.read_text(encoding="utf-8"))
    return "\n\n# ============ FILE BOUNDARY ============\n\n".join(parts)
