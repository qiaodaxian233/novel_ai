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


# ============================================================
# v2.23.1: 全榜矩阵扫描(MVP)
# ============================================================
# v2.23.0 只扫单一榜单 URL,v2.23.1 扩成 74 榜单矩阵(男频 38 + 女频 36)。
#
# 关键发现(2026-05-26 实测):
# - 榜单页 /rank/{g}_{t}_{cat_id} 用了字体反爬,直接抓 HTML 文本拿到的
#   书名/简介/标签都是混淆乱码,无法用。
# - 但 URL 里的 book_id (/page/{book_id}) 和 cat_id 是干净的,
#   "在读:XX万" 字段也是干净的(数字 + "万")。
# - 详情页 /page/{book_id} 文字干净,但 740 本逐一抓详情会需要 18 分钟。
#
# MVP 策略(v2.23.1):
# - 只扫 74 榜单,每榜抓 Top10 的 book_id + 在读数 + 题材(URL 派生)
# - 不抓详情页 (留给 v2.23.2)
# - prompt 喂 AI 用 3 个反爬无关的统计:
#     1) 74 个分类各自 Top10 的题材分布(URL 派生,完全可靠)
#     2) 每个分类的在读数中位数(数字,完全可靠)
#     3) 全榜唯一书数(去重后,反映"榜单饱和度")
# - 24 小时缓存
# - 早退机制:用户在进度对话框点"用部分数据生成"提前结束扫描

V231_RANK_BASE = "https://fanqienovel.com/rank"

# v2.23.1 MVP 缓存有效期(24 小时,番茄下午 3 点更新)
V231_CACHE_TTL_SEC = 24 * 3600

# 真实 cat_id 映射(2026-05-26 从 https://fanqienovel.com/rank?enter_from=menu 实测抓取)
# 注意:cat_id 是非连续的真实 ID,不是 1-19 顺序号
V231_MALE_CATEGORIES = [
    ("西方奇幻", "1141"), ("东方仙侠", "1140"), ("科幻末世", "8"),
    ("都市日常", "261"), ("都市修真", "124"), ("都市高武", "1014"),
    ("历史古代", "273"), ("战神赘婿", "27"), ("都市种田", "263"),
    ("传统玄幻", "258"), ("历史脑洞", "272"), ("悬疑脑洞", "539"),
    ("都市脑洞", "262"), ("玄幻脑洞", "257"), ("悬疑灵异", "751"),
    ("抗战谍战", "504"), ("游戏体育", "746"), ("动漫衍生", "718"),
    ("男频衍生", "1016"),
]

V231_FEMALE_CATEGORIES = [
    ("古风世情", "1139"), ("科幻末世", "8"), ("游戏体育", "746"),
    ("女频衍生", "1015"), ("玄幻言情", "248"), ("种田", "23"),
    ("年代", "79"), ("现言脑洞", "267"), ("宫斗宅斗", "246"),
    ("悬疑脑洞", "539"), ("古言脑洞", "253"), ("快穿", "24"),
    ("青春甜宠", "749"), ("星光璀璨", "745"), ("女频悬疑", "747"),
    ("职场婚恋", "750"), ("豪门总裁", "748"), ("民国言情", "1017"),
]


def get_all_rank_urls() -> List[Dict]:
    """
    返回所有 74 个榜单的 URL 列表

    每个元素:{
        "url": "https://fanqienovel.com/rank/1_2_1141",
        "label": "男频阅读榜·西方奇幻",
        "gender": "男频",
        "type": "阅读榜",
        "category": "西方奇幻",
        "cat_id": "1141",
    }

    顺序:男频阅读榜 19 → 男频新书榜 19 → 女频阅读榜 18 → 女频新书榜 18
    总数:74(男频 38 + 女频 36)
    """
    out = []
    for type_label, type_id in [("阅读榜", "2"), ("新书榜", "1")]:
        for cat_name, cat_id in V231_MALE_CATEGORIES:
            out.append({
                "url": f"{V231_RANK_BASE}/1_{type_id}_{cat_id}",
                "label": f"男频{type_label}·{cat_name}",
                "gender": "男频", "type": type_label,
                "category": cat_name, "cat_id": cat_id,
            })
    for type_label, type_id in [("阅读榜", "2"), ("新书榜", "1")]:
        for cat_name, cat_id in V231_FEMALE_CATEGORIES:
            out.append({
                "url": f"{V231_RANK_BASE}/0_{type_id}_{cat_id}",
                "label": f"女频{type_label}·{cat_name}",
                "gender": "女频", "type": type_label,
                "category": cat_name, "cat_id": cat_id,
            })
    return out


def parse_rank_page_minimal(html: str, max_books: int = 10) -> List[Dict]:
    """
    MVP 解析:只从榜单页提取**反爬无关字段**

    返回每本书的 dict,字段:
    - book_id: 详情页 ID(URL 里的数字,完全干净)
    - read_count_raw: 在读数原始字符串(例如 "66.4万"),完全干净
    - read_count_num: 解析成数字(单位:本),用于统计

    不抓:书名、作者、简介、标签(榜单页这些全是字体反爬乱码)
    """
    if not html:
        return []

    out = []
    chunks = re.split(r"#\s*0?\d{1,2}\s", html)
    if len(chunks) <= 1:
        chunks = [html]

    for chunk in chunks[1:max_books + 1]:
        m_id = re.search(r"/page/(\d{10,})", chunk)
        if not m_id:
            continue
        book_id = m_id.group(1)

        m_read = re.search(r"(\d+(?:\.\d+)?)\s*万", chunk)
        read_raw = ""
        read_num = 0
        if m_read:
            read_raw = m_read.group(0)
            try:
                read_num = int(float(m_read.group(1)) * 10000)
            except (ValueError, TypeError):
                read_num = 0

        out.append({
            "book_id": book_id,
            "read_count_raw": read_raw,
            "read_count_num": read_num,
        })

    return out


def aggregate_v231_stats(scraped: List[Dict]) -> Dict:
    """
    把扫到的 74 榜数据聚合成 prompt 用的统计字典

    输入 scraped 格式:
        [
          {"label": "男频阅读榜·西方奇幻", "gender": "男频",
           "type": "阅读榜", "category": "西方奇幻",
           "books": [{"book_id": "...", "read_count_num": 664000}, ...]},
          ...
        ]
    """
    stats = {
        "total_boards_scanned": len(scraped),
        "total_books": 0,
        "unique_books": 0,
        "by_gender": {"男频": {"boards": 0, "books": 0}, "女频": {"boards": 0, "books": 0}},
        "category_distribution": {},
        "hot_categories_male": [],
        "hot_categories_female": [],
    }

    all_book_ids = set()
    male_cat_median = {}
    female_cat_median = {}

    for board in scraped:
        books = board.get("books") or []
        gender = board.get("gender", "")
        cat = board.get("category", "")
        type_label = board.get("type", "")
        label = board.get("label", "")

        stats["total_books"] += len(books)
        if gender in stats["by_gender"]:
            stats["by_gender"][gender]["boards"] += 1
            stats["by_gender"][gender]["books"] += len(books)

        for b in books:
            bid = b.get("book_id", "")
            if bid:
                all_book_ids.add(bid)

        reads = sorted([b.get("read_count_num", 0) for b in books if b.get("read_count_num", 0) > 0])
        median_read = reads[len(reads) // 2] if reads else 0
        top_read = max(reads) if reads else 0

        stats["category_distribution"][label] = {
            "count": len(books),
            "median_read": median_read,
            "top_read": top_read,
        }

        if type_label == "阅读榜" and median_read > 0:
            if gender == "男频":
                male_cat_median.setdefault(cat, []).append(median_read)
            elif gender == "女频":
                female_cat_median.setdefault(cat, []).append(median_read)

    stats["unique_books"] = len(all_book_ids)

    def _flatten(d):
        out = []
        for cat, reads in d.items():
            avg = sum(reads) // len(reads) if reads else 0
            out.append((cat, avg))
        return sorted(out, key=lambda x: -x[1])

    stats["hot_categories_male"] = _flatten(male_cat_median)
    stats["hot_categories_female"] = _flatten(female_cat_median)

    return stats


def build_v231_full_rank_prompt(stats: Dict, user_genres: List[str],
                                 base_prompt: str = "") -> str:
    """
    v2.23.1 增强 prompt 拼装(基于全榜统计)

    - 输入是聚合统计 stats(不是 Book 列表)
    - 数据更"宏观":告诉 AI 整个番茄当前的题材热度图
    - 仍然遵守:**绝不传具体书名/作者/简介**,只传分类 + 数字
    """
    if not stats or stats.get("total_books", 0) == 0:
        return base_prompt or ""

    parts = []
    parts.append(f"【番茄小说全榜真实数据(扫描 {stats.get('total_boards_scanned', 0)} 个榜单·下午 3 点更新)】")
    parts.append("")

    total = stats.get("total_books", 0)
    unique = stats.get("unique_books", 0)
    parts.append(f"📊 总样本:{total} 本(去重后 {unique} 本独立作品)")
    by_g = stats.get("by_gender", {})
    parts.append(f"   男频 {by_g.get('男频', {}).get('boards', 0)} 榜 = {by_g.get('男频', {}).get('books', 0)} 本")
    parts.append(f"   女频 {by_g.get('女频', {}).get('boards', 0)} 榜 = {by_g.get('女频', {}).get('books', 0)} 本")
    parts.append("")

    male_hot = stats.get("hot_categories_male", [])[:10]
    if male_hot:
        parts.append("🔥 男频题材热度 Top10(按 Top10 平均在读数):")
        for i, (cat, avg) in enumerate(male_hot, 1):
            wan = avg // 10000
            parts.append(f"  {i}. {cat}({wan} 万在读)")
        parts.append("")

    female_hot = stats.get("hot_categories_female", [])[:10]
    if female_hot:
        parts.append("💃 女频题材热度 Top10(按 Top10 平均在读数):")
        for i, (cat, avg) in enumerate(female_hot, 1):
            wan = avg // 10000
            parts.append(f"  {i}. {cat}({wan} 万在读)")
        parts.append("")

    if user_genres:
        parts.append(f"✏️ 用户选择题材:{' / '.join(user_genres)}")
        matched_ranks = []
        for g in user_genres:
            for cat, avg in male_hot + female_hot:
                if g in cat or cat in g:
                    matched_ranks.append(f"{g}→{cat}({avg // 10000}万)")
                    break
        if matched_ranks:
            parts.append(f"   匹配榜单题材:{' / '.join(matched_ranks)}")
        parts.append("")

    parts.append("【硬性约束】")
    parts.append("1. 你必须基于上述真实榜单题材分布出 5 个差异化创意")
    parts.append("2. 绝不直接复制书名或情节(数据来源是公开榜单,不是让你抄)")
    parts.append("3. 每个创意要给:【题材组合】【主角设定】【核心钩子】【差异化卖点】四要素")
    parts.append("4. 优先在用户选择题材里出创意,但可以借鉴其它热门题材的钩子手法")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(base_prompt or "请基于以上榜单数据,生成 5 个差异化的小说创意。")

    return "\n".join(parts)


# ============================================================
# v2.23.3: 详情页深度抓取 + 磁盘缓存
# ============================================================
# v2.23.1 只抓榜单页(book_id + 在读数),AI prompt 信息量薄。
# v2.23.3 加详情抓取:每本 book_id → /page/{book_id} 拿干净的:
#   - 真书名(榜单页是字体反爬乱码)
#   - 作者
#   - 完整简介(从 <meta name="description">,纯文本干净)
#   - 标签(【XXX】格式)
#   - 题材分类(本书自带的)
#   - 字数 / 状态(连载中 / 已完结)
#
# 范围:每榜 Top5 × 74 榜 = 370 个 book_id(去重后 200-300 本)
# 后台时机:程序启动 30 秒后开始,礼让 AI 任务
# 磁盘缓存:<项目目录>/.fanqie_cache/ + INDEX.md(用户能直接打开看)
# TTL:7 天

V233_DETAIL_TOPK = 5  # 每榜抓 Top5 详情(用户敲定)
V233_DISK_CACHE_TTL_SEC = 7 * 24 * 3600  # 详情磁盘缓存 7 天
V233_BG_DELAY_SEC = 30  # 程序启动后多久才开始后台抓


import json
import os
import time as _time
from typing import Set


def get_t5_book_ids_from_scraped(scraped: List[Dict]) -> List[Tuple[str, str, str]]:
    """
    从扫榜结果里提取需要抓详情的 Top5 book_id 列表

    输入 scraped 格式(rank_all_scraped 信号 emit 给主进程的):
        [{"label": ..., "books": [{"book_id": ..., ...}, ...]}, ...]

    输出:[(book_id, source_label, source_category), ...] 去重后
    """
    seen = set()
    out = []
    for board in scraped:
        books = board.get("books") or []
        label = board.get("label", "")
        category = board.get("category", "")
        for b in books[:V233_DETAIL_TOPK]:
            bid = b.get("book_id", "")
            if not bid or bid in seen:
                continue
            seen.add(bid)
            out.append((bid, label, category))
    return out


def parse_detail_page_html(html: str) -> Dict:
    """
    从详情页 HTML 提取干净字段

    番茄详情页 head 里有:
      <title>书名完整版在线免费阅读_书名小说_番茄小说官网</title>
      <meta name="description" content="番茄小说提供书名完整版在线免费阅读,...
            【标签1】【标签2】简介文本...">
      <meta name="keywords" content="书名,书名免费阅读,...,作者名书名,...">
      <link rel="canonical" href="https://fanqienovel.com/page/123">

    body 里有(渲染前是 React #root):
      <h1 / .book-title>真书名</h1>
      <span>题材分类</span><span>奇幻仙侠</span><span>玄幻</span>
      <span>X 万字</span>
      <a href="/author-page/...">作者</a>
    """
    if not html:
        return {}

    out = {
        "title": "",
        "author": "",
        "abstract": "",
        "tags": [],
        "categories": [],
        "word_count": "",
        "status": "",  # 连载中 / 已完结
    }

    # 1. 从 <title> 抓书名(最稳)
    m_title = re.search(
        r"<title>([^<]+?)完整版在线免费阅读_", html, re.IGNORECASE)
    if m_title:
        out["title"] = m_title.group(1).strip()

    # 2. 从 <meta name="description"> 抓简介(干净文本,字体反爬不动 meta)
    m_desc = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m_desc:
        desc = m_desc.group(1)
        # 去掉"番茄小说提供 X完整版在线免费阅读,精彩小说尽在番茄小说网。"前缀
        desc = re.sub(
            r"^番茄小说提供[^。]+。\s*", "", desc, flags=re.IGNORECASE)
        out["abstract"] = desc.strip()

    # 3. 从简介里抽标签【XXX】
    if out["abstract"]:
        tags = re.findall(r"【([^】]+?)】", out["abstract"])
        out["tags"] = [t.strip() for t in tags if t.strip()]

    # 4. 从 <meta name="keywords"> 抓作者(格式:..., 作者名书名, ...)
    m_kw = re.search(
        r'<meta\s+name=["\']keywords["\']\s+content=["\']([^"\']+)["\']',
        html, re.IGNORECASE)
    if m_kw and out["title"]:
        # keywords 格式:"书名,书名免费阅读,...,作者书名,书名全本免费下载"
        kw = m_kw.group(1)
        # 找包含书名的段:"作者书名" 在书名前的部分就是作者
        parts = [p.strip() for p in kw.split(",")]
        for p in parts:
            if p.endswith(out["title"]) and p != out["title"]:
                author = p[:-len(out["title"])].strip()
                if author and 1 <= len(author) <= 20:
                    out["author"] = author
                    break

    return out


def _cache_dir(project_root: str) -> str:
    """缓存目录路径:<项目根>/.fanqie_cache/"""
    return os.path.join(project_root or ".", ".fanqie_cache")


def _cache_books_dir(project_root: str) -> str:
    return os.path.join(_cache_dir(project_root), "books")


def ensure_cache_dirs(project_root: str):
    """确保缓存目录存在"""
    os.makedirs(_cache_books_dir(project_root), exist_ok=True)


def save_book_detail(project_root: str, book_id: str, detail: Dict,
                     source_label: str = "", source_category: str = ""):
    """
    把一本书的详情写到磁盘
    路径:<项目>/.fanqie_cache/books/{book_id}.json
    """
    ensure_cache_dirs(project_root)
    path = os.path.join(_cache_books_dir(project_root), f"{book_id}.json")
    payload = {
        "book_id": book_id,
        "scraped_at": _time.time(),
        "source_label": source_label,
        "source_category": source_category,
        "detail": detail,
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def load_book_detail(project_root: str, book_id: str) -> Optional[Dict]:
    """
    读磁盘的一本书详情。过期(> 7 天)返回 None。
    返回 dict 含 detail / source_label / source_category / scraped_at,或 None。
    """
    path = os.path.join(_cache_books_dir(project_root), f"{book_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    age = _time.time() - float(data.get("scraped_at", 0))
    if age > V233_DISK_CACHE_TTL_SEC:
        return None
    return data


def list_cached_book_ids(project_root: str) -> Set[str]:
    """返回磁盘上已有的(且未过期)的 book_id 集合"""
    out = set()
    bdir = _cache_books_dir(project_root)
    if not os.path.exists(bdir):
        return out
    try:
        for name in os.listdir(bdir):
            if not name.endswith(".json"):
                continue
            bid = name[:-5]
            if load_book_detail(project_root, bid):
                out.add(bid)
    except Exception:
        pass
    return out


def save_rank_snapshot(project_root: str, scraped: List[Dict], stats: Dict):
    """保存当天的扫榜快照(给 INDEX.md 用)"""
    ensure_cache_dirs(project_root)
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(_cache_dir(project_root),
                         f"rank_snapshot_{today}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "scraped_at": _time.time(),
                "stats": stats,
                "scraped": scraped,
            }, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def write_index_md(project_root: str, stats: Dict,
                    scraped: List[Dict], details_progress: Tuple[int, int]):
    """
    写人类可读的 INDEX.md,用户能用 VSCode/记事本打开看

    details_progress: (已抓本数, 总目标本数)
    """
    ensure_cache_dirs(project_root)
    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    done, total = details_progress
    lines = [
        f"# 番茄榜单缓存(最后更新:{now})",
        "",
        "## 扫榜统计",
        f"- 总扫描:{stats.get('total_boards_scanned', 0)} 榜单",
        f"- 总抓取:{stats.get('total_books', 0)} 本(去重 {stats.get('unique_books', 0)} 本)",
        f"- 已抓详情:**{done} / {total} 本**({(done * 100 // total) if total else 0}% — 后台慢慢抓)",
        "",
        "## 男频题材热度 Top10",
    ]
    for i, (cat, avg) in enumerate(stats.get("hot_categories_male", [])[:10], 1):
        lines.append(f"{i}. {cat}({avg // 10000} 万在读)")
    lines.append("")
    lines.append("## 女频题材热度 Top10")
    for i, (cat, avg) in enumerate(stats.get("hot_categories_female", [])[:10], 1):
        lines.append(f"{i}. {cat}({avg // 10000} 万在读)")

    # 已抓的详情列表
    cached_ids = list_cached_book_ids(project_root)
    if cached_ids:
        lines.append("")
        lines.append(f"## 已抓详情样本({len(cached_ids)} 本,点 .json 看)")
        # 显示前 20 个
        for bid in list(cached_ids)[:20]:
            data = load_book_detail(project_root, bid)
            if not data:
                continue
            d = data.get("detail", {})
            title = d.get("title", "?")
            cat = data.get("source_category", "")
            author = d.get("author", "")
            wc = d.get("word_count", "")
            lines.append(
                f"- [{title}](books/{bid}.json) - {cat} - "
                f"{author} - {wc}")
        if len(cached_ids) > 20:
            lines.append(f"- ... 其他 {len(cached_ids) - 20} 本省略")

    path = os.path.join(_cache_dir(project_root), "INDEX.md")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return True
    except Exception:
        return False


def build_v233_enriched_prompt(stats: Dict, user_genres: List[str],
                                project_root: str,
                                base_prompt: str = "") -> str:
    """
    v2.23.3 增强 prompt:用磁盘缓存的详情数据补充统计

    跟 v2.23.1 的区别:
    - 统计部分保留(男女频 Top10 题材热度)
    - 加"已抓样本(用户题材相关)"段:列 5-10 个真实爆款的 [标签组合 + 简介一句话]
    - 仍然不传具体书名(防 AI 抄)
    """
    if not stats or stats.get("total_books", 0) == 0:
        return base_prompt or ""

    # 复用 v2.23.1 prompt 基础
    parts = []
    parts.append(f"【番茄小说全榜真实数据(扫描 {stats.get('total_boards_scanned', 0)} 个榜单·下午 3 点更新)】")
    parts.append("")

    total = stats.get("total_books", 0)
    unique = stats.get("unique_books", 0)
    parts.append(f"📊 总样本:{total} 本(去重后 {unique} 本独立作品)")
    by_g = stats.get("by_gender", {})
    parts.append(f"   男频 {by_g.get('男频', {}).get('boards', 0)} 榜 = {by_g.get('男频', {}).get('books', 0)} 本")
    parts.append(f"   女频 {by_g.get('女频', {}).get('boards', 0)} 榜 = {by_g.get('女频', {}).get('books', 0)} 本")
    parts.append("")

    male_hot = stats.get("hot_categories_male", [])[:10]
    if male_hot:
        parts.append("🔥 男频题材热度 Top10:")
        for i, (cat, avg) in enumerate(male_hot, 1):
            parts.append(f"  {i}. {cat}({avg // 10000} 万在读)")
        parts.append("")

    female_hot = stats.get("hot_categories_female", [])[:10]
    if female_hot:
        parts.append("💃 女频题材热度 Top10:")
        for i, (cat, avg) in enumerate(female_hot, 1):
            parts.append(f"  {i}. {cat}({avg // 10000} 万在读)")
        parts.append("")

    # v2.23.3 新增:用户题材相关的爆款样本(详情数据)
    matched = _gather_matched_samples(project_root, user_genres, max_samples=8)
    if matched:
        parts.append(f"📚 已扫到的真实爆款样本({len(matched)} 本,与你题材相关):")
        for i, sample in enumerate(matched, 1):
            tags_str = "+".join(sample.get("tags", [])[:5]) or "(无标签)"
            abstract = sample.get("abstract", "")[:80]
            cat = sample.get("source_category", "")
            parts.append(f"  样本{i} [{cat}] 标签组合:{tags_str}")
            if abstract:
                parts.append(f"    简介摘要:{abstract}...")
        parts.append("")
        parts.append("  ↑ 这些是当前在榜的爆款,请观察它们的 **标签组合规律** 和 **钩子手法**,")
        parts.append("    但**绝不直接复制简介内容**,你的创意要差异化。")
        parts.append("")

    if user_genres:
        parts.append(f"✏️ 用户选择题材:{' / '.join(user_genres)}")
        parts.append("")

    parts.append("【硬性约束】")
    parts.append("1. 基于上述真实榜单数据出 5 个差异化创意")
    parts.append("2. 绝不复制书名或简介,只借鉴标签组合规律")
    parts.append("3. **每个创意必须用 AI 自己想的具体卖点词当标签**,例如:")
    parts.append("   ✓ 正确:`1. 【厨子修仙】主角拿菜刀斩妖,一身锅气压魂魄...`")
    parts.append("   ✗ 错误:`1. 【一句话卖点】xxx`(不要复制'一句话卖点'这五个字!)")
    parts.append("4. 4 要素:【题材组合】【主角设定】【核心钩子】【差异化卖点】")
    parts.append("5. 优先用户选择题材,但可借鉴其它热门题材手法")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(base_prompt or "请基于以上数据生成 5 个差异化的小说创意。")

    return "\n".join(parts)


def _gather_matched_samples(project_root: str, user_genres: List[str],
                             max_samples: int = 8) -> List[Dict]:
    """从磁盘缓存里挑跟用户题材相关的爆款样本"""
    out = []
    cached_ids = list_cached_book_ids(project_root)
    user_genre_set = set(g.lower() for g in (user_genres or []))

    # 第一轮:source_category hard match
    for bid in cached_ids:
        if len(out) >= max_samples:
            break
        data = load_book_detail(project_root, bid)
        if not data:
            continue
        cat = (data.get("source_category", "") or "").lower()
        detail = data.get("detail", {})
        # hard match:用户题材跟分类相互包含
        if any(g in cat or cat in g for g in user_genre_set):
            out.append({
                "source_category": data.get("source_category", ""),
                "abstract": detail.get("abstract", ""),
                "tags": detail.get("tags", []),
            })

    # 第二轮:不够 max_samples 时补充任意爆款
    if len(out) < max_samples:
        for bid in cached_ids:
            if len(out) >= max_samples:
                break
            data = load_book_detail(project_root, bid)
            if not data:
                continue
            cat = data.get("source_category", "")
            already = any(s["source_category"] == cat for s in out)
            if already:
                continue
            detail = data.get("detail", {})
            out.append({
                "source_category": cat,
                "abstract": detail.get("abstract", ""),
                "tags": detail.get("tags", []),
            })

    return out
