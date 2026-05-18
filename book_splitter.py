# -*- coding: utf-8 -*-
"""
book_splitter.py · v1.38 — TXT 小说自动拆章节模块
─────────────────────────────────────────────
功能:
  1. 从 .txt 文件按"第 X 章 / 第 X 节"等模式拆章
  2. 处理多种章节标记变体(阿拉伯数字/中文数字/大写中文/罗马数字)
  3. 自动猜测编码(utf-8/gbk/gb2312)
  4. 给每章生成 BookChapter dataclass(title/content/word_count/index)

不做的事:
  - AI 分析(由 novel_ai.py 调度 dialogue_critic + 38项质检)
  - UI 渲染(由 BookSplitterTab 处理)
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path


# ───────────── 章节标题正则(从严到松) ─────────────
# 命中位置:行首,可能前面有少量空格
CHAPTER_PATTERNS = [
    # 1. 第 X 章 / 第X章 — 最常见
    # 包括"第1章"/"第一章"/"第一千零八十三章"/"第 1 章"
    r'^[\u3000\s]*第\s*[一二三四五六七八九十百千万零\d两壹贰叁肆伍陆柒捌玖拾佰仟]{1,10}\s*[章节回卷集篇]\s*[^\n]{0,80}$',

    # 2. "Chapter 1" / "Chapter One" — 英文(罕见但有)
    r'^[\u3000\s]*[Cc]hapter\s+[\d\w]+[^\n]{0,80}$',

    # 3. 纯数字章节("1." / "01" / "1、")— 谨慎用,容易误命中正文里的列表
    # 这条放最后,且要求后面紧跟一个章节标题(中文 ≥ 2 字符)
    # r'^[\u3000\s]*\d+[、.\s][\u4e00-\u9fa5]{2,30}$',  # 默认不开,容易误判
]


# 中文数字 → 阿拉伯数字(用于显示规整)
CN_NUM = {
    '零':0, '一':1, '二':2, '三':3, '四':4, '五':5, '六':6, '七':7, '八':8, '九':9,
    '十':10, '百':100, '千':1000, '万':10000, '两':2,
    '壹':1, '贰':2, '叁':3, '肆':4, '伍':5, '陆':6, '柒':7, '捌':8, '玖':9,
    '拾':10, '佰':100, '仟':1000,
}


def _cn_to_int(s: str) -> int:
    """把中文数字字符串转成 int,失败返回 -1"""
    if not s:
        return -1
    # 全阿拉伯数字
    if s.isdigit():
        try:
            return int(s)
        except Exception:
            return -1
    # 中文数字解析(简单实现,够用)
    total = 0
    current = 0
    for c in s:
        if c.isdigit():
            current = current * 10 + int(c)
        elif c in CN_NUM:
            v = CN_NUM[c]
            if v >= 10:
                # 单位字(十/百/千/万)
                if current == 0:
                    current = 1
                if v == 10000:
                    total += current * v
                    current = 0
                else:
                    total += current * v
                    current = 0
            else:
                current = current * 10 + v if current else v
    return total + current if (total + current) > 0 else -1


@dataclass
class BookChapter:
    """单章信息"""
    index: int           # 第 N 章(用户视角,从 1 开始)
    title: str           # 完整标题(如 "第一章 觉醒")
    title_clean: str     # 标题中"章"后面的部分(如 "觉醒")
    content: str         # 正文
    word_count: int = 0
    start_line: int = 0
    end_line: int = 0
    # AI 分析结果(可选,后填)
    analysis: dict = field(default_factory=dict)


@dataclass
class BookMeta:
    """整书元数据"""
    title: str = ""               # 书名(从文件名或首行猜)
    total_words: int = 0          # 总字数
    chapter_count: int = 0
    encoding: str = ""            # 检测到的编码
    chapters: list = field(default_factory=list)


# ───────────── 编码检测 ─────────────
def detect_encoding(path: Path) -> str:
    """检测 txt 编码,返回 utf-8/gbk/gb2312/utf-16 之一"""
    raw = path.read_bytes()[:8192]   # 只看前 8K 加速
    # BOM 检测
    if raw.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        return 'utf-16'
    # 尝试 utf-8(严格)
    try:
        raw.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    # 尝试 GBK 系列(国内 txt 网最常见)
    for enc in ('gbk', 'gb18030', 'gb2312'):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    # 最后兜底
    return 'utf-8'


# ───────────── 主拆章函数 ─────────────
def split_book(text: str, book_title: str = "") -> BookMeta:
    """把整本 txt 文本拆成章节列表"""
    lines = text.splitlines()
    if not book_title:
        # 猜书名:第一行非空且不像章节标题
        for line in lines[:5]:
            line = line.strip()
            if line and not _is_chapter_line(line):
                book_title = line[:50]
                break

    # 找所有章节起始行
    chapter_starts = []   # [(line_idx, title, raw_num)]
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_chapter_line(stripped):
            # 提取章节号(用于显示)
            num = _extract_chapter_num(stripped)
            chapter_starts.append((i, stripped, num))

    # 没找到任何章节 → 整体当一章
    if not chapter_starts:
        meta = BookMeta(
            title=book_title or "未命名",
            total_words=len(text),
            chapter_count=1,
        )
        meta.chapters.append(BookChapter(
            index=1,
            title="(全文)",
            title_clean="(全文)",
            content=text,
            word_count=len(text),
        ))
        return meta

    # 切分章节
    chapters = []
    for idx, (start_line, title, num) in enumerate(chapter_starts):
        # 内容从下一行开始,到下一个章节起始行之前
        end_line = (chapter_starts[idx + 1][0]
                    if idx + 1 < len(chapter_starts)
                    else len(lines))
        content_lines = lines[start_line + 1: end_line]
        content = "\n".join(content_lines).strip()

        # 章节内 title_clean = "章"后面的部分
        title_clean = _extract_title_clean(title)

        chapters.append(BookChapter(
            index=idx + 1,
            title=title,
            title_clean=title_clean,
            content=content,
            word_count=len(content),
            start_line=start_line,
            end_line=end_line,
        ))

    meta = BookMeta(
        title=book_title or "未命名",
        total_words=len(text),
        chapter_count=len(chapters),
        chapters=chapters,
    )
    return meta


def _is_chapter_line(line: str) -> bool:
    """判断一行是不是章节标题"""
    if len(line) > 100:   # 章节标题不会太长
        return False
    for pat in CHAPTER_PATTERNS:
        if re.match(pat, line):
            return True
    return False


def _extract_chapter_num(line: str) -> int:
    """从章节行提取数字部分(用于显示),失败返回 -1"""
    m = re.match(
        r'^[\u3000\s]*第\s*([一二三四五六七八九十百千万零\d两壹贰叁肆伍陆柒捌玖拾佰仟]{1,10})',
        line)
    if m:
        return _cn_to_int(m.group(1))
    m = re.match(r'^[\u3000\s]*[Cc]hapter\s+(\d+)', line)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return -1


def _extract_title_clean(line: str) -> str:
    """提取章节标题去掉'第X章'后的部分"""
    m = re.match(
        r'^[\u3000\s]*第\s*[一二三四五六七八九十百千万零\d两壹贰叁肆伍陆柒捌玖拾佰仟]{1,10}\s*[章节回卷集篇]\s*(.+)$',
        line)
    if m:
        return m.group(1).strip()
    # 英文 Chapter 1: xxx
    m = re.match(r'^[\u3000\s]*[Cc]hapter\s+\S+\s+(.+)$', line)
    if m:
        return m.group(1).strip()
    return ""


# ───────────── 顶层接口 ─────────────
def load_and_split(path: str | Path) -> BookMeta:
    """从文件路径加载 txt 并拆章"""
    path = Path(path)
    enc = detect_encoding(path)
    try:
        text = path.read_text(encoding=enc, errors='replace')
    except Exception as e:
        raise IOError(f"读取 {path} 失败({enc}): {e}")

    # 书名用文件名(去后缀)
    book_title = path.stem

    meta = split_book(text, book_title=book_title)
    meta.encoding = enc
    return meta
