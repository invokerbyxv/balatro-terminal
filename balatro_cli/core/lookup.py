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


def roll_prob(game, denom: float, label: str = "") -> bool:
    """1/denom 概率；持有六六大顺时概率翻倍（对应 G.GAME.probabilities）。

    原版判定是 ``pseudorandom < G.GAME.probabilities.normal / odds``，
    六六大顺把 ``normal`` 从 1 提到 2，因此 1/5 → 2/5、1/7 → 2/7。
    注意不能写成 ``denom // 2``：奇数分母下那会把 1/7 变成 1/3。
    """
    normal = 2.0 if game.any_joker("j_oops") else 1.0
    return game.rng.roll(label) < normal / denom


def guaranteed_edition(game, label: str = "edition") -> str:
    """附上一个必定生效的随机版本：箔片 50% / 全息 35% / 彩绘 15%。

    镜像 common_events.lua 的 ``poll_edition`` 在 ``_guaranteed = true``、
    ``_no_neg = true`` 时的分支（2058-2067）：负片那一档（``> 0.925``）因为
    ``_no_neg`` 被跳过、顺延给彩绘，往后依次是 0.85 / 0.5 两道阈值，于是命中
    后的分布是彩绘 15%、全息 35%、箔片 50%。命运之轮与灵光都用这组参数调用
    原版函数，负片版本不会出现（负片只来自灵质 / 负片标签等固定来源）。
    """
    x = game.rng.roll(label)
    if x > 0.85:
        return "polychrome"
    if x > 0.5:
        return "holo"
    return "foil"
