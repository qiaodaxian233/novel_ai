# -*- coding: utf-8 -*-
"""core/fanqie_genre_provider.py - v2.23.5

题材选择数据源:
- 把番茄扫到的 37 个真实分类作为主要题材池
- 提供 (男频 / 女频 / 通用) 三组分类
- 兼容老 GENRES (作为 fallback)
- 提供"用户题材 → 番茄分类"的智能匹配(给灵感采样用)

设计原则:
1. 番茄真实分类 = 一手数据 = 主要题材池
2. 老 GENRES 仍可用,作为"通用补充"
3. 智能匹配让用户输入的题材("玄幻")能匹配到番茄的多个分类
   ("传统玄幻"/"玄幻脑洞"/"玄幻言情")
"""
from typing import Dict, List, Tuple


# 番茄男频 19 个分类(来自 fanqie_rank_scraper.V231_MALE_CATEGORIES)
FANQIE_MALE_CATEGORIES = [
    "西方奇幻", "东方仙侠", "科幻末世", "都市日常", "都市修真",
    "都市高武", "历史古代", "战神赘婿", "都市种田", "传统玄幻",
    "历史脑洞", "悬疑脑洞", "都市脑洞", "玄幻脑洞", "悬疑灵异",
    "抗战谍战", "游戏体育", "动漫衍生", "男频衍生",
]

# 番茄女频 18 个分类
FANQIE_FEMALE_CATEGORIES = [
    "古风世情", "玄幻言情", "种田", "年代", "现言脑洞",
    "宫斗宅斗", "古言脑洞", "快穿", "青春甜宠", "星光璀璨",
    "女频悬疑", "职场婚恋", "豪门总裁", "民国言情",
    # 跨性别(科幻末世 / 游戏体育 已在男频列出,这里只放女频独有)
    "女频衍生",
]

# 通用补充(老 GENRES 里有但番茄分类没明确覆盖的:这类放"通用"组)
GENERIC_EXTRA = [
    "无限流", "武侠", "恐怖", "系统流", "轮回流", "规则怪谈",
    "惊悚游戏", "模拟器", "全民副本", "升级流", "扮猪吃虎",
    "逆袭流",
]


def get_genre_groups() -> List[Tuple[str, List[str]]]:
    """
    返回题材分组,UI 用来构建左侧题材选择区
    
    返回:
        [
            ("男频题材(番茄)", ["西方奇幻", "东方仙侠", ...]),
            ("女频题材(番茄)", ["古风世情", "玄幻言情", ...]),
            ("通用题材", ["无限流", "武侠", ...]),
        ]
    """
    return [
        ("男频题材(番茄)", list(FANQIE_MALE_CATEGORIES)),
        ("女频题材(番茄)", list(FANQIE_FEMALE_CATEGORIES)),
        ("通用题材", list(GENERIC_EXTRA)),
    ]


def get_all_genres_flat() -> List[str]:
    """返回所有可选题材的扁平列表(去重)"""
    seen = set()
    out = []
    for _, items in get_genre_groups():
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
    return out


# 智能匹配:用户题材 → 番茄真实分类
# 关键词包含规则 + 别名映射
GENRE_ALIASES = {
    # 老 GENRES 词 → 应该匹配到的番茄真实分类列表
    "玄幻": ["传统玄幻", "玄幻脑洞", "玄幻言情", "都市高武"],
    "仙侠": ["东方仙侠", "都市修真"],
    "都市": ["都市日常", "都市修真", "都市高武", "都市种田", "都市脑洞"],
    "言情": ["玄幻言情", "古风世情", "宫斗宅斗", "青春甜宠", "豪门总裁",
              "现言脑洞", "古言脑洞", "民国言情", "职场婚恋"],
    "奇幻": ["西方奇幻"],
    "末世": ["科幻末世"],
    "科幻": ["科幻末世"],
    "历史": ["历史古代", "历史脑洞"],
    "悬疑": ["悬疑脑洞", "悬疑灵异", "女频悬疑"],
    "脑洞": ["历史脑洞", "悬疑脑洞", "都市脑洞", "玄幻脑洞",
              "现言脑洞", "古言脑洞"],
    "种田": ["种田", "都市种田"],
    "重生": ["年代", "宫斗宅斗"],  # 重生流常见于年代和宫斗
    "穿越": ["快穿", "古风世情", "宫斗宅斗"],
    "古风": ["古风世情", "古言脑洞", "宫斗宅斗"],
    "甜宠": ["青春甜宠", "豪门总裁"],
    "总裁": ["豪门总裁", "职场婚恋"],
}


def match_user_genre_to_fanqie(user_genre: str) -> List[str]:
    """
    把用户输入的一个题材词,匹配到番茄真实分类列表
    
    匹配优先级:
        1. 精确匹配(用户输入 == 番茄分类名)
        2. 别名映射(GENRE_ALIASES)
        3. 包含匹配(用户词包含在番茄分类名中 / 番茄分类包含用户词)
    
    例:
        match_user_genre_to_fanqie("玄幻") 
        → ["传统玄幻", "玄幻脑洞", "玄幻言情", "都市高武"]
        
        match_user_genre_to_fanqie("豪门总裁")
        → ["豪门总裁"]
    """
    if not user_genre:
        return []
    
    user = user_genre.strip()
    user_lower = user.lower()
    all_fanqie = FANQIE_MALE_CATEGORIES + FANQIE_FEMALE_CATEGORIES
    
    # 1. 精确匹配
    if user in all_fanqie:
        return [user]
    
    # 2. 别名映射
    if user in GENRE_ALIASES:
        return list(GENRE_ALIASES[user])
    
    # 3. 包含匹配
    matched = []
    for cat in all_fanqie:
        if user_lower in cat.lower() or cat.lower() in user_lower:
            matched.append(cat)
    return matched


def match_user_genres_to_fanqie(user_genres: List[str]) -> List[str]:
    """
    批量版:用户多选题材 → 番茄真实分类去重列表
    
    例:
        match_user_genres_to_fanqie(["玄幻", "都市"])
        → ["传统玄幻", "玄幻脑洞", "玄幻言情", "都市高武",
            "都市日常", "都市修真", "都市种田", "都市脑洞"]
    """
    seen = set()
    out = []
    for ug in (user_genres or []):
        for cat in match_user_genre_to_fanqie(ug):
            if cat not in seen:
                seen.add(cat)
                out.append(cat)
    return out


def get_gender_for_fanqie_category(cat: str) -> str:
    """返回番茄分类属于男频还是女频。返回 '男频' / '女频' / '通用'"""
    if cat in FANQIE_MALE_CATEGORIES:
        return "男频"
    if cat in FANQIE_FEMALE_CATEGORIES:
        return "女频"
    return "通用"
