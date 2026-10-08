"""手牌判定与手牌等级。

对应 Lua 源码 functions/misc_functions.lua 的 evaluate_poker_hand / get_X_same /
get_flush / get_straight / get_highest，以及 game.lua 的手牌基础数值表。
"""
from __future__ import annotations
from typing import List, Optional, Tuple

from .card import Card, rank_id

# 手牌类型（按优先级从高到低）
HAND_ORDER = [
    "Flush Five", "Flush House", "Five of a Kind", "Straight Flush",
    "Four of a Kind", "Full House", "Flush", "Straight",
    "Three of a Kind", "Two Pair", "Pair", "High Card",
]

HAND_CN = {
    "Flush Five": "五张同花", "Flush House": "同花葫芦", "Five of a Kind": "五条",
    "Straight Flush": "同花顺", "Four of a Kind": "四条", "Full House": "葫芦",
    "Flush": "同花", "Straight": "顺子", "Three of a Kind": "三条",
    "Two Pair": "两对", "Pair": "对子", "High Card": "高牌",
}

# 基础数值表（level 1）：mult / chips / 每级增量 l_mult / l_chips
# 来源：game.lua G.GAME.hands（2002-2013），公式见 common_events.lua level_up_hand
HANDS_BASE = {
    "Flush Five":        {"mult": 16, "chips": 160, "l_mult": 3, "l_chips": 50},
    "Flush House":       {"mult": 14, "chips": 140, "l_mult": 4, "l_chips": 40},
    "Five of a Kind":    {"mult": 12, "chips": 120, "l_mult": 3, "l_chips": 35},
    "Straight Flush":    {"mult": 8,  "chips": 100, "l_mult": 4, "l_chips": 40},
    "Four of a Kind":    {"mult": 7,  "chips": 60,  "l_mult": 3, "l_chips": 30},
    "Full House":        {"mult": 4,  "chips": 40,  "l_mult": 2, "l_chips": 25},
    "Flush":             {"mult": 4,  "chips": 35,  "l_mult": 2, "l_chips": 15},
    "Straight":          {"mult": 4,  "chips": 30,  "l_mult": 3, "l_chips": 30},
    "Three of a Kind":   {"mult": 3,  "chips": 30,  "l_mult": 2, "l_chips": 20},
    "Two Pair":          {"mult": 2,  "chips": 20,  "l_mult": 1, "l_chips": 20},
    "Pair":              {"mult": 2,  "chips": 10,  "l_mult": 1, "l_chips": 15},
    "High Card":         {"mult": 1,  "chips": 5,   "l_mult": 1, "l_chips": 10},
}


def hand_level_stats(name: str, level: int) -> Tuple[int, int]:
    """给定手牌名称与等级，返回 (mult, chips)。

    公式：mult  = max(s_mult + l_mult*(level-1), 1)
          chips = max(s_chips + l_chips*(level-1), 0)
    """
    b = HANDS_BASE[name]
    mult = max(b["mult"] + b["l_mult"] * (level - 1), 1)
    chips = max(b["chips"] + b["l_chips"] * (level - 1), 0)
    return mult, chips


# ---------------------------------------------------------------------------
# 判定原语（忠实转录 Lua 算法）
# ---------------------------------------------------------------------------

def get_X_same(num: int, hand: List[Card]) -> List[List[Card]]:
    """按点数分组，返回恰好 num 张同点数的牌组列表，按 id 从大到小排序。"""
    groups: dict = {}
    for c in hand:
        i = c.get_id()
        if i <= 0:  # 石头牌 id 为负，天然排除
            continue
        groups.setdefault(i, []).append(c)
    out = []
    for i in sorted(groups, reverse=True):
        g = groups[i]
        if len(g) == num:
            out.append(g)
    return out


def get_flush(hand: List[Card], four_fingers: bool = False, smeared: bool = False) -> List[Card]:
    """同花：要求手牌数恰为 5（四根手指时 4~5）。按 S/H/C/D 顺序返回第一组满足的。"""
    if len(hand) > 5 or len(hand) < (4 if four_fingers else 5):
        return []
    need = 4 if four_fingers else 5
    for suit in ("S", "H", "C", "D"):
        cards = [c for c in hand if c.is_suit(suit, flush_calc=True, smeared=smeared)]
        if len(cards) >= need:
            return cards
    return []


def get_straight(hand: List[Card], four_fingers: bool = False, shortcut: bool = False) -> List[Card]:
    """顺子：Ace 可作 1 或 14。shortcut=小丑牌 Shortcut（允许跳一个点数）。"""
    if len(hand) > 5 or len(hand) < (4 if four_fingers else 5):
        return []
    ids: dict = {}
    for c in hand:
        i = c.get_id()
        if 1 < i < 15:  # 石头牌负数被过滤
            ids.setdefault(i, []).append(c)
    straight_length = 0
    straight = False
    skipped = False
    t: List[Card] = []
    for j in range(1, 15):
        rank = 14 if j == 1 else j
        if rank in ids:
            straight_length += 1
            skipped = False
            t.extend(ids[rank])
        elif shortcut and not skipped and j != 14:
            skipped = True
        else:
            straight_length = 0
            skipped = False
            if not straight:
                t = []
            else:
                break
        if straight_length >= (4 if four_fingers else 5):
            straight = True
    return t if straight else []


def get_highest(hand: List[Card]) -> List[Card]:
    """最高牌：取 nominal 最大的 1 张。"""
    if not hand:
        return []
    best = max(hand, key=lambda c: c.get_nominal())
    return [best]


def evaluate_poker_hand(hand: List[Card], four_fingers: bool = False,
                        shortcut: bool = False, smeared: bool = False) -> Tuple[str, List[Card]]:
    """判定最佳手牌，返回 (手牌名称, 记分手)。

    记分手：Flush House/Full House = 三条组+对子组；Straight Flush = 同花∪顺子去重；
    Two Pair = 两对（或 三条+一对，防御分支）。
    """
    _5 = get_X_same(5, hand)
    _4 = get_X_same(4, hand)
    _3 = get_X_same(3, hand)
    _2 = get_X_same(2, hand)
    # 派生链：5oak→4oak→3oak→pair（5 张 A 时 get_X_same(2/3/4) 为空）
    if _5:
        _4 = [_5[0][:4]]
    if _4:
        _3 = [_4[0][:3]]
    if _3:
        _2 = [_3[0][:2]]

    _flush = get_flush(hand, four_fingers, smeared)
    _straight = get_straight(hand, four_fingers, shortcut)
    _highest = get_highest(hand)

    if _5 and _flush:
        return "Flush Five", _5[0]
    if _3 and _2 and _flush:
        return "Flush House", _3[0] + _2[0]
    if _5:
        return "Five of a Kind", _5[0]
    if _flush and _straight:
        # 并集去重（保持原有顺序：先 flush 后 straight）
        seen = set()
        scoring = [c for c in _flush + _straight
                   if not (c in seen or seen.add(c))]
        return "Straight Flush", scoring
    if _4:
        return "Four of a Kind", _4[0]
    if _3 and _2:
        return "Full House", _3[0] + _2[0]
    if _flush:
        return "Flush", _flush
    if _straight:
        return "Straight", _straight
    if _3:
        return "Three of a Kind", _3[0]
    if len(_2) == 2 or (len(_3) == 1 and len(_2) == 1):
        if len(_2) >= 2:
            return "Two Pair", _2[0] + _2[1]
        return "Two Pair", _2[0] + _3[0]
    if _2:
        return "Pair", _2[0]
    return "High Card", _highest


def is_royal_flush(name: str, scoring_hand: List[Card]) -> bool:
    """同花顺是否皇家同花顺（显示用，数值与同花顺相同）。"""
    if name != "Straight Flush":
        return False
    ids = sorted(c.get_id() for c in scoring_hand)
    return ids[0] >= 10 and len(ids) >= 5
