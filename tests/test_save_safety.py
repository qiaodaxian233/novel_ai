# -*- coding: utf-8 -*-
"""保存链路安全性守护(v2.23.7)

背景:此前 save_project_folder 是"先删光全部章节 .md 再逐个重写",
单文件原子写救不了整体操作 — 删除与写完之间崩溃/断电 = 章节永久
丢失,而最高频的 60s 定时 autosave 恰好走这条路且无 zip 备份兜底。

本文件锁住修复后的三个性质:
  1. 先写后删:保存中途任意一步失败,磁盘上不缺任何一章(可能有
     新旧混合,但绝不空缺)
  2. 残留清理:删章/改名后,成功保存会清掉不在新集合里的旧文件
  3. 比对写:内容未变的文件不产生任何写入(mtime 不动)
另附 novel_ai._autosave 的静态守护:脏哈希短路与 .json 原子写必须在。
"""
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

import project_io  # noqa: E402


def _payload(chapters):
    return {
        "title": "测试书", "inspiration": "", "advanced": {},
        "memory": {"characters": "角色卡", "summaries": "", "long_term": ""},
        "chapters": chapters,
        "seed": "种子", "worldview": "", "structure": "",
        "chapter_outline": "", "lo": "", "intro": "",
    }


def _chapter_files(folder):
    return sorted(p.name for p in (Path(folder) / "chapters").glob("*.md"))


def test_write_first_delete_later(tmp_path, monkeypatch):
    """保存中途崩溃:磁盘上不缺任何一章(旧内容仍在,而非被预删)"""
    folder = tmp_path / "proj"
    chs = [{"title": f"第{i}章", "content": f"旧内容{i}"} for i in (1, 2, 3)]
    project_io.save_project_folder(folder, _payload(chs))
    before = _chapter_files(folder)
    assert len(before) == 3

    # 全部章节改动 → 三个文件都需要重写;让第 2 次原子写爆炸,
    # 模拟"写到一半断电"
    for i, ch in enumerate(chs, 1):
        ch["content"] = f"新内容{i}"
    calls = {"n": 0}
    real = project_io._atomic_write

    def bomb(path, data, *a, **kw):
        if "chapters" in str(path):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise OSError("模拟磁盘满/断电")
        return real(path, data, *a, **kw)

    monkeypatch.setattr(project_io, "_atomic_write", bomb)
    with pytest.raises(OSError):
        project_io.save_project_folder(folder, _payload(chs))
    monkeypatch.setattr(project_io, "_atomic_write", real)

    after = _chapter_files(folder)
    assert after == before, "崩溃后章节文件不得缺失(先写后删性质)"
    texts = {p.name: p.read_text(encoding="utf-8")
             for p in (folder / "chapters").glob("*.md")}
    # 第 1 章已写新,第 2/3 章保留旧 — 新旧混合可接受,空缺不可接受
    assert texts[before[1]] == "旧内容2"
    assert texts[before[2]] == "旧内容3"


def test_stale_files_cleaned_on_success(tmp_path):
    """删章 + 改名:成功保存后旧文件名不残留(避免幽灵章节)"""
    folder = tmp_path / "proj"
    chs = [{"title": f"第{i}章", "content": f"c{i}"} for i in (1, 2, 3)]
    project_io.save_project_folder(folder, _payload(chs))
    # 删掉第 3 章,第 1 章改名
    chs2 = [{"title": "开天辟地", "content": "c1"},
            {"title": "第2章", "content": "c2"}]
    project_io.save_project_folder(folder, _payload(chs2))
    names = _chapter_files(folder)
    assert names == ["001-开天辟地.md", "002-第2章.md"]


def test_unchanged_content_zero_write(tmp_path):
    """内容未变的第二次保存:章节与 settings 的 mtime 分毫不动"""
    folder = tmp_path / "proj"
    chs = [{"title": f"第{i}章", "content": f"c{i}"} for i in (1, 2)]
    project_io.save_project_folder(folder, _payload(chs))
    watch = list((folder / "chapters").glob("*.md")) + [folder / "settings.json"]
    stamps = {p: p.stat().st_mtime_ns for p in watch}
    project_io.save_project_folder(folder, _payload(chs))
    for p, old in stamps.items():
        assert p.stat().st_mtime_ns == old, f"{p.name} 被无谓重写"


def test_roundtrip_after_rewrite(tmp_path):
    """改造后读写往返仍无损"""
    folder = tmp_path / "proj"
    chs = [{"title": "第1章", "content": "正文A", "score": 88},
           {"title": "第2章", "content": "正文B"}]
    project_io.save_project_folder(folder, _payload(chs))
    back = project_io.load_project_folder(folder)
    assert [c["content"] for c in back["chapters"]] == ["正文A", "正文B"]
    assert back["chapters"][0].get("score") == 88
    assert back["memory"]["characters"] == "角色卡"
    assert back["seed"] == "种子"


def test_autosave_source_guards():
    """novel_ai._autosave 静态守护:脏哈希短路 + .json 原子写必须存在"""
    src = (_REPO / "novel_ai.py").read_text(encoding="utf-8")
    i = src.find("def _autosave(self):")
    assert i > 0
    body = src[i:i + 9000]
    assert "_last_autosave_hash" in body, "脏哈希短路被移除:静止时 60s 定时器会恢复全量重写"
    assert "os.replace(" in body, ".json 回退路径的原子写被移除:截断写会在崩溃时毁档"
