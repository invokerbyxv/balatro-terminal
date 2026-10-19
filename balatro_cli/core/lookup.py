"""跨模块共用的小工具：名称查表与概率判定。

放在独立模块是为了让 effects / joker_fx 都能引用，避免两者互相 import。
"""
from __future__ import annotations

from ..data import centers as centers_data
from ..data import consumables as consumable_data


def joker_cn(key: str) -> str:
    """小丑 / 消耗牌的中文名；未知键原样返回。"""
    if key in centers_data.JOKERS:
        return centers_data.JOKERS[key]["cn"]
    if key in consumable_data.ALL_CONSUMABLES:
        return consumable_data.ALL_CONSUMABLES[key]["cn"]
    return key


def roll_prob(game, denom: int, label: str = "") -> bool:
    """1/denom 概率；持有六六大顺时概率翻倍（对应 G.GAME.probabilities）。"""
    if game.any_joker("j_oops"):
        denom = max(1, denom // 2)
    return game.rng.chance(denom, label)
