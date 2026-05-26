# -*- coding: utf-8 -*-
"""
v2.23.0 番茄小说榜单扫描器
================================

`gen_inspiration`(生成创意灵感)流程:
  原流程:点"生成灵感" → 拼通用 prompt 给 AI → AI 凭训练数据估算"应该爆"的套路
  新流程:点"生成灵感" → 浏览器打开 https://fanqienovel.com/rank?enter_from=menu
         → 抓榜单 → 按用户题材过滤 → 拼增强 prompt → AI 基于真实当下榜单出创意

本模块只负责"扫到的榜单数据 → 增强 prompt"的纯逻辑部分,**不依赖 Qt / Selenium**,
可以独立单测。浏览器侧的 navigate + DOM 抓取在 `ui/browser_worker.py` 里。

# 设计取舍(跟用户敲定的)

1. **扫榜失败兜底**:扫到 0 条 / 浏览器没开 / 番茄改 DOM → fallback 到旧通用 prompt,
   不打断用户体验。日志里报警让用户知道。
2. **30 分钟缓存**:同 platform + genre 组合 30 分钟内复用结果,避免每次点都开新页面。
3. **抓 Top 50 + 按题材过滤**:番茄首页榜单页 30-50 本,按用户选的题材 hard match;
   不够 10 条放宽到题材相近,日志说明匹配情况。
4. **不传具体书名给 AI**:只传"题材组合 + 卖点共性",防 AI 学样抄袭。Prompt 里加
   铁律:"以下是题材趋势数据,你不能直接复制书名或情节,只能借鉴**题材组合规律**"。
5. **番茄站点 profile 简化**:不是 AI 聊天站点,只要 navigate + wait_after_load +
   抓取 selector 几个字段。

# 数据流

    点"生成灵感"
       ↓ (genres=['玄幻','重生'], platform='番茄小说')
    FanqieRankCache.get_or_scrape()
       ↓ 缓存命中 → 直接用
       ↓ 缓存未命中 → browser_worker.scrape_fanqie_rank() 抓 50 本 → 缓存
    filter_by_genres(books, ['玄幻','重生'])
       ↓ 优先 hard match,不够 10 条放宽
    build_enhanced_inspiration_prompt(filtered, base_prompt)
       ↓ 拼"以下是真实榜单题材趋势 ..."
    AI 出 5 个创意

# 守护测试在 test_bug086_v23_scrape_rank_hook_relax.py
"""
import re
import time
from typing import List, Dict, Optional, Tuple


# ============================================================
# 常量
# ============================================================

# 番茄榜单 URL(用户敲定:扫这个页面)
FANQIE_RANK_URL = "https://fanqienovel.com/rank?enter_from=menu"

# 单次抓取目标数量上限
SCRAPE_TARGET_TOPK = 50

# 题材匹配最小条数门槛(低于此数放宽到"相近题材")
MIN_MATCHES_BEFORE_RELAX = 10

# 缓存有效期(秒,30 分钟)
CACHE_TTL_SEC = 30 * 60


# 番茄站点抓取 selector(profile 简化,不放进 SITE_PROFILES,因为不是 AI 聊天站点)
FANQIE_SCRAPER_PROFILE = {
    "rank_url": FANQIE_RANK_URL,
    "wait_after_load_sec": 3.5,        # 页面加载后等多久再抓
    "scroll_steps": 3,                  # 向下滚动几次让懒加载内容出现
    "scroll_pause_sec": 0.6,           # 每次滚动后等多久
    # 候选 selector(番茄改 DOM 时只要 selector 调一次就行)
    "book_card_selectors": [
        ".rank-list .rank-item",         # 主选
        ".bookshelf-item",                # 备选 1
        "[class*='rank'] [class*='item']",  # 备选 2(模糊)
    ],
    "title_selectors": [".rank-name", ".book-name", "[class*='title']"],
    "category_selectors": [".rank-category", ".book-category", "[class*='category']"],
    "abstract_selectors": [".rank-abstract", ".book-desc", "[class*='abstract']"],
    "read_count_selectors": [".rank-read", "[class*='read-count']", "[class*='popular']"],
}


# 题材相近表(放宽匹配用)
# 用户选"玄幻",玄幻不够 10 条时,可以补充"奇幻 / 修真 / 仙侠"
GENRE_RELAX_MAP = {
    "玄幻":   ["奇幻", "修真", "仙侠", "玄幻奇幻"],
    "都市":   ["现实", "都市生活", "都市言情"],
    "言情":   ["现代言情", "言情都市", "古代言情", "甜宠"],
    "悬疑":   ["悬疑推理", "推理", "灵异", "恐怖"],
    "科幻":   ["科幻", "未来世界", "末世"],
    "历史":   ["历史", "架空历史", "历史军事"],
    "军事":   ["军事", "战争"],
    "游戏":   ["游戏", "电竞", "网游"],
    "竞技":   ["竞技", "体育"],
    "西方奇幻": ["奇幻", "玄幻"],
    "穿越":   ["穿越", "古代言情", "古代", "重生"],
    "重生":   ["重生", "穿越", "系统流"],
    "系统":   ["系统流", "无限流", "重生"],
}


# ============================================================
# 数据结构
# ============================================================

class Book:
    """扫到的一本书的最简数据结构(只存 prompt 需要的字段)"""
    __slots__ = ("title", "category", "abstract", "read_count", "raw")

    def __init__(self, title: str = "", category: str = "",
                 abstract: str = "", read_count: str = "", raw: Optional[Dict] = None):
        self.title = (title or "").strip()
        self.category = (category or "").strip()
        self.abstract = (abstract or "").strip()
        self.read_count = (read_count or "").strip()
        self.raw = raw or {}

    def is_valid(self) -> bool:
        """有标题或题材就算有效(防全空脏数据)"""
        return bool(self.title or self.category)

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "category": self.category,
            "abstract": self.abstract,
            "read_count": self.read_count,
        }


# ============================================================
# 缓存
# ============================================================

class FanqieRankCache:
    """
    简单的内存缓存:`platform + tuple(genres) → (books, scraped_at)`

    实例化一份放在主进程里,所有 gen_inspiration 调用走它。
    """
    def __init__(self, ttl_sec: int = CACHE_TTL_SEC):
        self._cache: Dict[Tuple[str, Tuple[str, ...]], Tuple[List[Book], float]] = {}
        self._ttl = ttl_sec

    def _key(self, platform: str, genres: List[str]) -> Tuple[str, Tuple[str, ...]]:
        return (platform or "", tuple(sorted(genres or [])))

    def get(self, platform: str, genres: List[str]) -> Optional[List[Book]]:
        """缓存未过期就返回,否则 None"""
        k = self._key(platform, genres)
        if k not in self._cache:
            return None
        books, scraped_at = self._cache[k]
        if time.time() - scraped_at > self._ttl:
            # 过期清掉
            self._cache.pop(k, None)
            return None
        return books

    def put(self, platform: str, genres: List[str], books: List[Book]):
        k = self._key(platform, genres)
        self._cache[k] = (list(books), time.time())

    def clear(self):
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


# ============================================================
# 题材匹配
# ============================================================

def filter_by_genres(books: List[Book], genres: List[str],
                     min_matches: int = MIN_MATCHES_BEFORE_RELAX
                     ) -> Tuple[List[Book], int, int]:
    """
    按题材过滤,优先 hard match,不够 min_matches 条放宽到"相近题材"。

    返回 (筛选后的书列表, hard_match_count, relax_match_count)
        hard_match_count: 严格匹配命中数
        relax_match_count: 放宽匹配(GENRE_RELAX_MAP)补充的数量

    没有 genres 或 books 为空 → 返回原列表 + (0, 0)。
    """
    if not books:
        return [], 0, 0
    if not genres:
        # 用户没选题材,全部放行
        return list(books), len(books), 0

    norm_genres = [g.strip() for g in genres if g and g.strip()]
    if not norm_genres:
        return list(books), len(books), 0

    # Hard match: 书的 category 包含任一用户选的 genre(双向 substring,兼容
    # "玄幻奇幻" / "奇幻玄幻" / "玄幻·东方" 等格式)
    hard = []
    for b in books:
        if not b.is_valid():
            continue
        cat = b.category
        for g in norm_genres:
            if g in cat or cat in g:
                hard.append(b)
                break

    if len(hard) >= min_matches:
        return hard, len(hard), 0

    # 放宽:对每个用户选的 genre,取 GENRE_RELAX_MAP 里的相近词
    relax_keywords = set()
    for g in norm_genres:
        for relaxed in GENRE_RELAX_MAP.get(g, []):
            relax_keywords.add(relaxed)
    # 去掉已经在 norm_genres 里的(避免重复)
    relax_keywords -= set(norm_genres)

    if not relax_keywords:
        return hard, len(hard), 0

    # 找不在 hard 里的、category 命中放宽关键词的书
    already_titles = {b.title for b in hard}
    relax = []
    for b in books:
        if not b.is_valid() or b.title in already_titles:
            continue
        cat = b.category
        for kw in relax_keywords:
            if kw in cat or cat in kw:
                relax.append(b)
                break

    merged = hard + relax
    return merged, len(hard), len(relax)


# ============================================================
# 卖点提炼
# ============================================================

def extract_genre_combinations(books: List[Book], topk: int = 10) -> List[Tuple[str, int]]:
    """
    从书的 category 字段统计"题材组合"出现频次

    番茄的 category 常长这样:"玄幻 · 重生", "都市 · 系统", "言情 · 穿越"
    我们按分隔符切开,然后**两两组合**统计共现次数。

    返回 [(组合字符串, 出现次数), ...] 按次数降序,最多 topk 条。
    """
    if not books:
        return []
    from collections import Counter
    # 分隔符:· 、 / · | 空格
    splitters = re.compile(r'[·、\s/|・]+')
    pairs = Counter()
    singles = Counter()
    for b in books:
        if not b.category:
            continue
        tags = [t.strip() for t in splitters.split(b.category) if t.strip()]
        # 去重 + 排序保证组合稳定("玄幻+重生" 跟 "重生+玄幻" 合并)
        tags = sorted(set(tags))
        if not tags:
            continue
        if len(tags) == 1:
            singles[tags[0]] += 1
        else:
            # 两两组合
            for i in range(len(tags)):
                for j in range(i + 1, len(tags)):
                    pairs[f"{tags[i]} + {tags[j]}"] += 1
            # 单标签也计入(单标签书不少)
            for t in tags:
                singles[t] += 1
    # 优先组合,组合不够 topk 时补单标签
    result = pairs.most_common(topk)
    if len(result) < topk:
        for t, c in singles.most_common(topk):
            if len(result) >= topk:
                break
            # 别重复(组合里已经有的单标签可以保留,显示成"重生 [单独]")
            result.append((f"{t} [单独]", c))
    return result[:topk]


def extract_abstract_keywords(books: List[Book], topk: int = 15) -> List[Tuple[str, int]]:
    """
    从书的 abstract 提炼高频"卖点关键词"

    简单实现:中文 2-3 字短语 + 黑名单过滤。
    返回 [(关键词, 频次), ...] 按频次降序。

    这是粗糙的卖点提炼 — 真正的 NER / 主题模型超出本模块范围。
    """
    if not books:
        return []
    from collections import Counter
    # 网文常见"卖点"词汇白名单(权重高)
    HOT_HOOKS = (
        # 重生穿越类
        "重生", "穿越", "穿书", "重活", "回到", "前世",
        # 系统类
        "系统", "签到", "金手指", "外挂", "无敌",
        # 打脸类
        "退婚", "打脸", "逆袭", "翻盘", "崛起", "反转",
        # 身份类
        "马甲", "假千金", "真千金", "弃妇", "弃女", "庶女", "嫡女",
        "战神", "总裁", "霸总", "boss",
        # 甜虐类
        "甜宠", "虐恋", "虐渣", "宠妻", "撒糖",
        # 玄幻类
        "天才", "废柴", "妖孽", "无敌", "至尊", "凡尘", "修仙", "修真",
        # 都市类
        "豪门", "神豪", "神医", "兵王",
        # 异能类
        "异能", "超能力", "灵气", "灵魂",
        # 末世类
        "末世", "丧尸", "灾难", "求生",
        # 群像类
        "宿主", "宿命", "命运", "诅咒", "因果",
    )
    counter = Counter()
    for b in books:
        text = (b.abstract or "") + " " + (b.title or "")
        for hk in HOT_HOOKS:
            if hk in text:
                counter[hk] += 1
    return counter.most_common(topk)


# ============================================================
# 增强 prompt 构造
# ============================================================

def build_enhanced_inspiration_prompt(filtered_books: List[Book],
                                       genres: List[str],
                                       platform: str = "番茄小说") -> Optional[str]:
    """
    根据扫到的真实榜单数据,构造增强版灵感生成 prompt

    扫到 0 条 → 返回 None,让上层走旧 fallback prompt。
    扫到正常 → 返回完整 prompt 文本,直接喂给 AI。

    设计要点:
    - 不传具体书名(防 AI 学样)
    - 只传 Top10 题材组合 + Top15 卖点关键词
    - 明示 prompt 里有铁律:"不能复制书名/情节,只能借鉴题材组合规律"
    """
    if not filtered_books:
        return None
    combos = extract_genre_combinations(filtered_books, topk=10)
    keywords = extract_abstract_keywords(filtered_books, topk=15)
    if not combos and not keywords:
        return None

    genre_str = "/".join(genres) if genres else "网文"
    total = len(filtered_books)
    combo_lines = "\n".join(f"  - {c} (Top榜出现 {n} 次)" for c, n in combos) if combos else "  (无显著组合)"
    kw_lines = "、".join(f"{w}({n})" for w, n in keywords[:10]) if keywords else "(无显著热词)"

    return (
        f"你是网文市场分析师+创意策划。以下是【{platform}】当前 **真实** {genre_str} 类"
        f"榜单数据(扫到 {total} 本爆款),请基于这些数据生成 5 个差异化创意:\n\n"
        f"【Top题材组合】(出现频次代表当前读者偏好的'套路融合'):\n"
        f"{combo_lines}\n\n"
        f"【高频卖点关键词】:\n"
        f"  {kw_lines}\n\n"
        f"【创意生成铁律】\n"
        f"- 这些数据是市场趋势参考,**不要直接复制任何具体作品或情节**\n"
        f"- 但要借鉴**题材组合规律**(比如'玄幻+重生'是当前 Top 趋势,可以考虑融入)\n"
        f"- 5 个创意要差异化,不能都用同一种组合\n"
        f"- 每个创意要有'金手指'(主角的独特优势)和'核心冲突'\n"
        f"- 融入当下读者最爱的元素,但要有新意,不撞车\n"
        f"- 禁止血腥暴力色情违规内容\n\n"
        f"【输出格式】每个创意一行,格式:\n"
        f"1. 【一句话卖点】详细说明(50字内)\n"
        f"2. ...\n\n"
        f"请直接输出 5 个创意,不要其他内容。"
    )


# ============================================================
# 抓取结果解析(浏览器侧调用)
# ============================================================

def parse_scraped_books(raw_data: List[Dict]) -> List[Book]:
    """
    把浏览器抓回来的 dict 列表转成 Book 对象,顺便去重 + 过滤无效

    raw_data 例:
        [{"title": "斗破苍穹", "category": "玄幻", "abstract": "...", "read_count": "100w"}, ...]
    """
    if not raw_data:
        return []
    out = []
    seen_titles = set()
    for raw in raw_data:
        if not isinstance(raw, dict):
            continue
        b = Book(
            title=str(raw.get("title", "")),
            category=str(raw.get("category", "")),
            abstract=str(raw.get("abstract", "")),
            read_count=str(raw.get("read_count", "")),
            raw=raw,
        )
        if not b.is_valid():
            continue
        # 同标题去重
        key = b.title or b.category[:20]
        if key in seen_titles:
            continue
        seen_titles.add(key)
        out.append(b)
        if len(out) >= SCRAPE_TARGET_TOPK:
            break
    return out
