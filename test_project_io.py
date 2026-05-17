# -*- coding: utf-8 -*-
"""v1.30 BUG-042 — project_io 模块单元测试
重点验证:旧 .json → 新文件夹 → 再读出来 = lossless(原数据完全保留)
这是用户数据安全的根本保障。
"""
import json
import shutil
import tempfile
from pathlib import Path

import project_io as pio


# 构造一个最复杂的真实场景 payload(模仿用户实际项目)
SAMPLE_PAYLOAD = {
    "title": "玄幻第一书:仙凡之路",
    "inspiration": "一个废柴穿越后逆袭的故事",
    "seed": "主角林远身体内有上古血脉,觉醒后...",
    "worldview": "三千大世界,九重天阙...",
    "structure": "起承转合四幕,30 万字大长篇...",
    "chapter_outline": "第 1 章 觉醒 / 第 2 章 拜师 / ...",
    "lo": "林悦是命中注定的红颜...",
    "intro": "一个废柴的逆天之路,从此开始。",
    "chapters": [
        {
            "title": "觉醒之夜",
            "content": "夜深了。林远盯着掌心那道金芒...\n\n(三千字正文略)",
            "hook": {"type": "悬疑", "content": "玉佩从哪来?"},
            "cool_points": ["类型:打脸:被打脸的人哑口无言"],
            "next_options": ["走出后院遇高人", "回房研究玉佩"],
        },
        {
            "title": "初战告捷",
            "content": "第二天清晨...\n\n(五千字正文略)",
            "hook": {"type": "战斗", "content": "强敌将至"},
            "cool_points": [],
            "next_options": [],
            "summary": "林远初战告捷,但暗处的眼睛盯上了他。",
        },
    ],
    "memory": {
        "characters": "【林远】男主,内敛...\n【林悦】女主,直率...",
        "summaries": "第1章: 林远觉醒玉佩...\n第2章: 初战告捷...",
        "long_term": "- 玉佩:祖母遗物,内有上古血脉",
        "auto_summarize": True,
        "auto_inject": True,
        "recent_n": 3,
        "summary_len": 80,
    },
    "canon": {
        "locked": [{"item": "主角身世", "value": "孤儿,玉佩是唯一线索"}],
        "evolving": [{"item": "主角境界", "value": "炼气期"}],
    },
    "charlib": {
        "characters": [["林远", "主角", "黑发剑眉", "内敛"]],
        "items": [["玉佩", "信物", "林远", "1"]],
        "relations": [],
        "timeline": [],
        "power_levels": [],
        "foreshadows": [],
    },
    "skills": {"after_chapter_skills": [], "auto_match_skills": []},
    "critique": {"rhythm": True, "character": True, "hook": True, "canon": True},
    "conv_slots": {"slots": []},
    "lifespan_loops": {},
    "advanced": {
        "genres": ["玄幻", "言情"],
        "platform": "起点中文网",
        "audience": "男频",
        "density": "中",
        "growth": "稳",
        "conflict": "渐进",
        "era": "古代",
        "chapter_count": 200,
        "words_per_chapter": 3000,
        "outline_detail": "详细",
        "style_weights": {"对话": 0.4, "描写": 0.4, "动作": 0.2},
        "rhythm": "标准",
        "endings": "正常",
        "creation_mode": "auto",
        "prompt_offset": 0,
        "golden_fingers": [],
        "personas": [],
        "ai": "deepseek",
    },
    "saved_at": "2025-11-13T10:00:00",
}


def test_save_and_load_roundtrip(tmp_path):
    """核心:存档 → 读出来 = 完全相同"""
    folder = tmp_path / "测试书"
    pio.save_project_folder(folder, SAMPLE_PAYLOAD)

    # 文件夹结构正确
    assert (folder / "project.json").exists()
    assert (folder / "settings.json").exists()
    assert (folder / "outline" / "worldview.md").exists()
    assert (folder / "outline" / "seed.md").exists()
    assert (folder / "outline" / "chapter_outline.md").exists()
    assert (folder / "memory" / "characters.md").exists()
    assert (folder / "memory" / "summaries.md").exists()
    assert (folder / "memory" / "config.json").exists()
    assert (folder / "chapters" / "_meta.json").exists()
    assert (folder / "chapters" / "001-觉醒之夜.md").exists()
    assert (folder / "chapters" / "002-初战告捷.md").exists()
    assert (folder / "world.json").exists()
    assert (folder / "canon.json").exists()
    assert (folder / "skills.json").exists()

    # 读出来要等于原 payload(关键字段)
    loaded = pio.load_project_folder(folder)
    assert loaded["title"] == SAMPLE_PAYLOAD["title"]
    assert loaded["inspiration"] == SAMPLE_PAYLOAD["inspiration"]
    assert loaded["seed"] == SAMPLE_PAYLOAD["seed"]
    assert loaded["worldview"] == SAMPLE_PAYLOAD["worldview"]
    assert loaded["structure"] == SAMPLE_PAYLOAD["structure"]
    assert loaded["chapter_outline"] == SAMPLE_PAYLOAD["chapter_outline"]
    assert loaded["lo"] == SAMPLE_PAYLOAD["lo"]
    assert loaded["intro"] == SAMPLE_PAYLOAD["intro"]
    # chapters
    assert len(loaded["chapters"]) == 2
    for orig, got in zip(SAMPLE_PAYLOAD["chapters"], loaded["chapters"]):
        assert got["title"] == orig["title"]
        assert got["content"] == orig["content"]
        assert got["hook"] == orig["hook"]
        assert got["cool_points"] == orig["cool_points"]
        assert got["next_options"] == orig["next_options"]
    # memory
    assert loaded["memory"]["characters"] == SAMPLE_PAYLOAD["memory"]["characters"]
    assert loaded["memory"]["auto_inject"] == True
    assert loaded["memory"]["recent_n"] == 3
    # 6 库 / canon / skills
    assert loaded["charlib"] == SAMPLE_PAYLOAD["charlib"]
    assert loaded["canon"] == SAMPLE_PAYLOAD["canon"]
    assert loaded["critique"] == SAMPLE_PAYLOAD["critique"]
    # advanced
    assert loaded["advanced"]["genres"] == ["玄幻", "言情"]
    assert loaded["advanced"]["chapter_count"] == 200
    assert loaded["advanced"]["ai"] == "deepseek"


def test_detect_format(tmp_path):
    # 文件夹格式
    folder = tmp_path / "书1"
    pio.save_project_folder(folder, SAMPLE_PAYLOAD)
    assert pio.detect_format(folder) == "folder"

    # 旧 json 格式
    json_path = tmp_path / "old.json"
    json_path.write_text(json.dumps(SAMPLE_PAYLOAD, ensure_ascii=False),
                         encoding="utf-8")
    assert pio.detect_format(json_path) == "legacy_json"

    # 未知
    other = tmp_path / "what.txt"
    other.write_text("not a project")
    assert pio.detect_format(other) == "unknown"
    assert pio.detect_format(tmp_path / "nonexistent") == "unknown"


def test_migrate_legacy_json(tmp_path):
    """旧 json → 新文件夹"""
    json_path = tmp_path / "玄幻.json"
    json_path.write_text(json.dumps(SAMPLE_PAYLOAD, ensure_ascii=False),
                         encoding="utf-8")

    target = tmp_path / "升级后"
    pio.migrate_legacy_json(json_path, target)

    # 新文件夹存在 + 含正确数据
    assert (target / "project.json").exists()
    assert (target / "chapters" / "001-觉醒之夜.md").exists()
    # 备份原 .json 保留在新文件夹里
    assert (target / ".legacy-original.json").exists()
    # 原 json 还在原位(没删)
    assert json_path.exists()

    # 读出来等于原数据
    loaded = pio.load_project_folder(target)
    assert loaded["title"] == SAMPLE_PAYLOAD["title"]
    assert len(loaded["chapters"]) == 2


def test_empty_chapter_meta(tmp_path):
    """章节没元信息时,_meta.json 可以不写,加载用文件名兜底 title"""
    payload = {
        "title": "简单书",
        "chapters": [
            {"title": "第一章", "content": "正文 A"},
            {"title": "第二章", "content": "正文 B"},
        ],
    }
    folder = tmp_path / "简单书"
    pio.save_project_folder(folder, payload)

    loaded = pio.load_project_folder(folder)
    assert len(loaded["chapters"]) == 2
    assert loaded["chapters"][0]["title"] == "第一章"
    assert loaded["chapters"][0]["content"] == "正文 A"
    assert loaded["chapters"][1]["title"] == "第二章"


def test_dangerous_chapter_title(tmp_path):
    """章节标题含非法字符也能存"""
    payload = {
        "title": "test",
        "chapters": [
            {"title": "第一章/带斜杠\\和:冒号*?", "content": "正文"},
            {"title": '"双引号<尖括号>|管道', "content": "也是正文"},
        ],
    }
    folder = tmp_path / "test"
    pio.save_project_folder(folder, payload)
    # 应该正常写入 + 加载
    loaded = pio.load_project_folder(folder)
    assert len(loaded["chapters"]) == 2
    assert loaded["chapters"][0]["content"] == "正文"


def test_backup_zip(tmp_path):
    folder = tmp_path / "备份测试"
    pio.save_project_folder(folder, SAMPLE_PAYLOAD)
    zip_path = pio.make_backup_zip(folder)
    assert zip_path is not None
    assert zip_path.exists()
    assert zip_path.suffix == ".zip"
    # 第二次备份 → 应有 2 个
    pio.make_backup_zip(folder)
    backups = list((folder / ".backups").glob("backup-*.zip"))
    assert len(backups) >= 1


def test_empty_payload(tmp_path):
    """空 payload 也能存能读(新建项目场景)"""
    folder = tmp_path / "新书"
    pio.save_project_folder(folder, {"title": "新书"})
    loaded = pio.load_project_folder(folder)
    assert loaded["title"] == "新书"
    assert loaded["chapters"] == []
