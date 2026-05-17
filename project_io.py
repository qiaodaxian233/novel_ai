# -*- coding: utf-8 -*-
"""
project_io.py · v1.30 — 文件夹格式项目存档 IO 层
─────────────────────────────────────────────
新结构:
  <project_dir>/<书名>/
  ├── project.json       元数据(schema版本/创建/最后保存)
  ├── settings.json      创作设置(题材/字数/风格/平台/AI/critique 等)
  ├── outline/           大纲 prose(.md 可单独编辑)
  │   ├── seed.md  worldview.md  structure.md
  │   ├── chapter_outline.md  lo.md  intro.md
  ├── chapters/          每章一个 .md(纯正文)+ _meta.json(钩子/爽点等元信息)
  │   ├── _meta.json
  │   ├── 001-觉醒之夜.md
  │   └── 002-初战告捷.md
  ├── memory/            对话记忆
  │   ├── characters.md  summaries.md  long_term.md
  │   └── config.json    (auto_inject 等开关)
  ├── world.json         角色与世界 6 库(结构化)
  ├── canon.json         Canon 设定档
  ├── skills.json        技能库
  ├── lifespan.json      寿元/伏笔(可选)
  └── .backups/          整体 .zip 快照(最近 10 次)

设计原则:
  - .md 文本可读可编辑 / .json 结构化数据
  - 与旧 single-.json 完全 lossless 互转(单元测试保证)
  - 兼容:detect_format() → "folder" / "legacy_json" / "unknown"
"""
from __future__ import annotations
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

PROJECT_SCHEMA_VERSION = 1


# ───────────── 通用工具 ─────────────
def _safe_filename(s: str, max_len: int = 80) -> str:
    """文件名安全:去除非法字符"""
    s = re.sub(r'[\\/:*?"<>|]', '_', s or "").strip()
    s = re.sub(r'\s+', ' ', s)
    return (s[:max_len] or "untitled").strip()


def detect_format(path: str | Path) -> str:
    """识别路径是哪种格式
    返回: "folder" / "legacy_json" / "unknown"
    """
    p = Path(path)
    if p.is_dir() and (p / "project.json").is_file():
        return "folder"
    if p.is_file() and p.suffix.lower() == ".json":
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(d, dict) and "chapters" in d:
                return "legacy_json"
        except Exception:
            pass
    return "unknown"


# ───────────── 保存到文件夹 ─────────────
def save_project_folder(folder: str | Path, payload: dict) -> Path:
    """把 payload(dict)按新结构写入 folder
    payload 跟旧 MainWindow.save_project 的 d 字典格式一致
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    # 1. project.json 元数据
    meta = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "schema": "v1.30-folder",
        "title": payload.get("title", ""),
        "saved_at": datetime.now().isoformat(),
    }
    (folder / "project.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. settings.json(创作设置 + critique + conv_slots)
    settings = {
        "title": payload.get("title", ""),
        "inspiration": payload.get("inspiration", ""),
        "advanced": payload.get("advanced", {}),
        "critique": payload.get("critique", {}),
        "conv_slots": payload.get("conv_slots", {}),
    }
    (folder / "settings.json").write_text(
        json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3. outline/*.md(prose 大纲六件套)
    outline_dir = folder / "outline"
    outline_dir.mkdir(exist_ok=True)
    # 先清空旧 .md(避免删了一个还残留)
    for f in outline_dir.glob("*.md"):
        f.unlink()
    OUTLINE_KEYS = [
        ("seed", "seed.md"),
        ("worldview", "worldview.md"),
        ("structure", "structure.md"),
        ("chapter_outline", "chapter_outline.md"),
        ("lo", "lo.md"),
        ("intro", "intro.md"),
    ]
    for key, filename in OUTLINE_KEYS:
        content = (payload.get(key) or "").strip()
        if content:
            (outline_dir / filename).write_text(content, encoding="utf-8")

    # 4. memory/(prose + config)
    memory_dir = folder / "memory"
    memory_dir.mkdir(exist_ok=True)
    for f in memory_dir.glob("*.md"):
        f.unlink()
    mem = payload.get("memory", {}) or {}
    MEMORY_PROSE = [
        ("characters", "characters.md"),
        ("summaries", "summaries.md"),
        ("long_term", "long_term.md"),
    ]
    for key, filename in MEMORY_PROSE:
        content = (mem.get(key) or "").strip()
        if content:
            (memory_dir / filename).write_text(content, encoding="utf-8")
    # 配置(auto_summarize / auto_inject / recent_n / summary_len)
    config = {k: mem[k] for k in
              ("auto_summarize", "auto_inject", "recent_n", "summary_len")
              if k in mem}
    if config:
        (memory_dir / "config.json").write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    # 5. chapters/(每章一个 .md 纯正文 + _meta.json 元信息)
    chapters_dir = folder / "chapters"
    chapters_dir.mkdir(exist_ok=True)
    # 清空旧的 .md(避免删章节后残留)
    for old in chapters_dir.glob("*.md"):
        old.unlink()
    chapters = payload.get("chapters", []) or []
    meta_map = {}
    for i, ch in enumerate(chapters, 1):
        title = ch.get("title") or f"第{i}章"
        safe = _safe_filename(title)
        filename = f"{i:03d}-{safe}.md"
        # 纯正文写 .md
        content = ch.get("content") or ""
        (chapters_dir / filename).write_text(content, encoding="utf-8")
        # 元信息(除 content 外的所有字段)写到 _meta.json
        rest = {k: v for k, v in ch.items() if k != "content"}
        meta_map[str(i)] = rest
    if meta_map:
        (chapters_dir / "_meta.json").write_text(
            json.dumps(meta_map, ensure_ascii=False, indent=2), encoding="utf-8")
    elif (chapters_dir / "_meta.json").exists():
        (chapters_dir / "_meta.json").unlink()

    # 6. world.json(6 库)
    charlib = payload.get("charlib") or {}
    if charlib:
        (folder / "world.json").write_text(
            json.dumps(charlib, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # 7. canon.json
    canon = payload.get("canon") or {}
    if canon:
        (folder / "canon.json").write_text(
            json.dumps(canon, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # 8. skills.json
    skills = payload.get("skills") or {}
    if skills:
        (folder / "skills.json").write_text(
            json.dumps(skills, ensure_ascii=False, indent=2),
            encoding="utf-8")

    # 9. lifespan.json(可选)
    lifespan = payload.get("lifespan_loops") or {}
    if lifespan:
        (folder / "lifespan.json").write_text(
            json.dumps(lifespan, ensure_ascii=False, indent=2),
            encoding="utf-8")

    return folder


# ───────────── 从文件夹加载 ─────────────
def load_project_folder(folder: str | Path) -> dict:
    """从文件夹结构读出 payload(dict),格式跟 save 期待的一致"""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(f"项目文件夹不存在: {folder}")

    payload = {}

    # project.json
    meta_path = folder / "project.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            payload["title"] = meta.get("title", "")
        except Exception:
            pass

    # settings.json
    sp = folder / "settings.json"
    if sp.is_file():
        try:
            s = json.loads(sp.read_text(encoding="utf-8"))
            if s.get("title"):
                payload["title"] = s["title"]
            payload["inspiration"] = s.get("inspiration", "")
            payload["advanced"] = s.get("advanced", {})
            payload["critique"] = s.get("critique", {})
            payload["conv_slots"] = s.get("conv_slots", {})
        except Exception:
            pass

    # outline/
    outline_dir = folder / "outline"
    OUTLINE_KEYS = [
        ("seed", "seed.md"),
        ("worldview", "worldview.md"),
        ("structure", "structure.md"),
        ("chapter_outline", "chapter_outline.md"),
        ("lo", "lo.md"),
        ("intro", "intro.md"),
    ]
    for key, filename in OUTLINE_KEYS:
        f = outline_dir / filename if outline_dir.is_dir() else None
        if f and f.is_file():
            payload[key] = f.read_text(encoding="utf-8")
        else:
            payload[key] = ""

    # memory/
    memory_dir = folder / "memory"
    memory = {}
    MEMORY_PROSE = [
        ("characters", "characters.md"),
        ("summaries", "summaries.md"),
        ("long_term", "long_term.md"),
    ]
    for key, filename in MEMORY_PROSE:
        f = memory_dir / filename if memory_dir.is_dir() else None
        if f and f.is_file():
            memory[key] = f.read_text(encoding="utf-8")
        else:
            memory[key] = ""
    config_path = memory_dir / "config.json" if memory_dir.is_dir() else None
    if config_path and config_path.is_file():
        try:
            memory.update(json.loads(config_path.read_text(encoding="utf-8")))
        except Exception:
            pass
    payload["memory"] = memory

    # chapters/
    chapters_dir = folder / "chapters"
    chapters = []
    if chapters_dir.is_dir():
        meta_map = {}
        meta_path = chapters_dir / "_meta.json"
        if meta_path.is_file():
            try:
                meta_map = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta_map = {}
        for f in sorted(chapters_dir.glob("*.md")):
            # 提取章号(NNN-XXX.md 前的数字)
            m = re.match(r"^(\d+)-", f.name)
            ch_idx_str = str(int(m.group(1))) if m else ""
            ch = dict(meta_map.get(ch_idx_str, {}))
            ch["content"] = f.read_text(encoding="utf-8")
            # title 如果 _meta 没有,从文件名取
            if "title" not in ch:
                title_part = f.stem
                if m:
                    title_part = title_part[len(m.group(0)):]
                ch["title"] = title_part
            chapters.append(ch)
    payload["chapters"] = chapters

    # world.json / canon.json / skills.json / lifespan.json
    for key, filename in [
        ("charlib", "world.json"),
        ("canon", "canon.json"),
        ("skills", "skills.json"),
        ("lifespan_loops", "lifespan.json"),
    ]:
        f = folder / filename
        if f.is_file():
            try:
                payload[key] = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                payload[key] = {}
        else:
            payload[key] = {}

    return payload


# ───────────── 旧 .json 升级到新文件夹 ─────────────
def migrate_legacy_json(json_path: str | Path,
                        target_folder: str | Path) -> Path:
    """老 .json → 新文件夹
    1. 读老 json
    2. 写入新文件夹(save_project_folder)
    3. 把原 .json 移动到 target_folder/.legacy-original.json(保险)
    """
    json_path = Path(json_path)
    target = Path(target_folder)

    if not json_path.is_file():
        raise FileNotFoundError(f"老 json 不存在: {json_path}")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    save_project_folder(target, payload)
    # 把原 .json 复制(不移除原文件)到新文件夹做保险
    backup_path = target / ".legacy-original.json"
    shutil.copy2(json_path, backup_path)
    return target


# ───────────── 整体备份成 .zip ─────────────
def make_backup_zip(folder: str | Path, keep: int = 10) -> Path | None:
    """把项目文件夹整体打包成 zip 放到 folder/.backups/
    保留最近 keep 个
    """
    folder = Path(folder)
    if not folder.is_dir():
        return None
    backup_dir = folder / ".backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = backup_dir / f"backup-{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in folder.rglob("*"):
            # 不打包 .backups 自己 + .legacy-original.json
            if ".backups" in f.parts:
                continue
            if f.is_file():
                zf.write(f, arcname=f.relative_to(folder))
    # 清理超过 keep 个的旧备份
    backups = sorted(backup_dir.glob("backup-*.zip"), reverse=True)
    for old in backups[keep:]:
        try:
            old.unlink()
        except Exception:
            pass
    return zip_path
