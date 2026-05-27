# -*- coding: utf-8 -*-
"""book_splitter 单元测试 — 主要测各种章节标题变体"""
import tempfile
from pathlib import Path

import book_splitter as bs


def test_arabic_numbers():
    """阿拉伯数字章节"""
    text = "书名\n\n第1章 觉醒\n正文 A\n\n第2章 初战\n正文 B"
    meta = bs.split_book(text)
    assert meta.chapter_count == 2
    assert meta.chapters[0].title_clean == "觉醒"
    assert meta.chapters[1].title_clean == "初战"


def test_chinese_numbers():
    """中文数字章节"""
    text = "书名\n\n第一章 觉醒\n正文 A\n\n第二章 初战\n正文 B"
    meta = bs.split_book(text)
    assert meta.chapter_count == 2
    assert meta.chapters[0].title_clean == "觉醒"


def test_large_chinese_numbers():
    """大数字中文章节"""
    text = "书名\n\n第一千零八十三章 终章\n正文"
    meta = bs.split_book(text)
    assert meta.chapter_count == 1
    assert meta.chapters[0].title_clean == "终章"
    # 数字解析
    assert bs._cn_to_int("一千零八十三") == 1083
    assert bs._cn_to_int("两万") == 20000


def test_unit_variants():
    """章/节/回/卷/集/篇都该认"""
    text = "书名\n\n第一章 a\nA\n\n第二节 b\nB\n\n第三回 c\nC\n\n第四卷 d\nD\n\n第五集 e\nE\n\n第六篇 f\nF"
    meta = bs.split_book(text)
    assert meta.chapter_count == 6


def test_chapter_title_no_space():
    """第一章后面没空格也认 (第一章觉醒)"""
    text = "书名\n\n第1章觉醒\n正文 A\n\n第2章初战\n正文 B"
    meta = bs.split_book(text)
    assert meta.chapter_count == 2


def test_no_chapter_marker():
    """没有任何章节标记 → 整本变一章"""
    text = "随便的小说内容,没有章节标记。\n\n第二段正文。\n\n第三段。"
    meta = bs.split_book(text)
    assert meta.chapter_count == 1
    assert meta.chapters[0].title == "(全文)"


def test_chinese_num_conversion():
    """中文数字转换"""
    assert bs._cn_to_int("一") == 1
    assert bs._cn_to_int("十") == 10
    assert bs._cn_to_int("十一") == 11
    assert bs._cn_to_int("二十") == 20
    assert bs._cn_to_int("一百") == 100
    assert bs._cn_to_int("一百零三") == 103
    assert bs._cn_to_int("123") == 123
    assert bs._cn_to_int("") == -1


def test_word_count_accurate():
    """字数统计要对"""
    text = "书名\n\n第一章 测试\n这是正文,共十一个字。\n\n第二章 啊\n短"
    meta = bs.split_book(text)
    assert meta.chapters[0].word_count == len("这是正文,共十一个字。")
    assert meta.chapters[1].word_count == 1


def test_encoding_detect_utf8(tmp_path):
    """UTF-8 编码检测"""
    p = tmp_path / "book.txt"
    p.write_text("第一章 测试\n正文", encoding="utf-8")
    assert bs.detect_encoding(p) == "utf-8"


def test_encoding_detect_gbk(tmp_path):
    """GBK 编码(国内 txt 最常见)"""
    p = tmp_path / "book.txt"
    p.write_bytes("第一章 测试\n正文".encode("gbk"))
    assert bs.detect_encoding(p) in ("gbk", "gb18030", "gb2312")


def test_load_and_split_integration(tmp_path):
    """完整流程 — 加载 + 拆"""
    p = tmp_path / "测试小说.txt"
    content = "测试小说\n\n第一章 觉醒\nA 正文。\n\n第二章 战斗\nB 正文。"
    p.write_text(content, encoding="utf-8")
    meta = bs.load_and_split(p)
    assert meta.chapter_count == 2
    assert meta.title == "测试小说"
    assert meta.encoding == "utf-8"


def test_long_chapter_title_rejected():
    """超长行不该被认成章节标题"""
    text = "书名\n\n这是一段正文,虽然以'第一'开头但不是章节标题,长度超过限制是不会被认出来章节的,所以会和上面一起进入第一章里面。\n\n第一章 真正的章节\n这才是正文"
    meta = bs.split_book(text)
    assert meta.chapter_count == 1
    assert meta.chapters[0].title_clean == "真正的章节"
