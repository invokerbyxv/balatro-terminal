"""物品模型：小丑牌、消耗牌、卡包、优惠券。

对应 Lua card.lua 的 Card object 中非"扑克牌"的部分（ability、edition 等）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JokerItem:
    key: str                          # 如 'j_joker'
    edition: Optional[str] = None     # foil/holo/poly/negative
    eternal: bool = False
    perishable: bool = False
    rental: bool = False
    # 运行状态
    perish_tally: int = field(default=5)
    debuffed: bool = field(default=False)
    # 数值型小丑的积累状态（可变，由效果引擎读写）
    stat: dict = field(default_factory=dict)
    sell_price: int = field(default=0)
    buy_cost: int = field(default=0)
    # 标签临时禁用（深红之心）
    disabled_round: bool = field(default=False)

    @property
    def negative(self) -> bool:
        """负片版本：由 edition 派生（负片编辑 = 负片版本，无独立字段）。"""
        return self.edition == "negative"

    def sell_value(self) -> int:
        v = self.sell_price
        if self.edition == "polychrome":
            v += 2
        if self.negative:
            v += 5
        if self.rental:
            v = max(1, v - 1)
        return max(1, v)


@dataclass
class ConsumableItem:
    key: str                          # 如 'c_fool'
    edition: Optional[str] = None
    sell_price: int = field(default=0)
    buy_cost: int = field(default=0)

    @property
    def negative(self) -> bool:
        return self.edition == "negative"

    def sell_value(self) -> int:
        v = self.sell_price
        if self.edition == "polychrome":
            v += 2
        if self.negative:
            v += 5
        return max(1, v)


@dataclass
class BoosterPack:
    key: str                          # 如 'p_arcana_normal'
    cost: int = field(default=0)
    buy_cost: int = field(default=0)


@dataclass
class VoucherSlot:
    """商店中展示的优惠券。redeem 后立即生效，不保留。"""
    key: str
    cost: int = 10


@dataclass
class Tag:
    key: str
    skips: int = field(default=0)     # 生成时已跳过的盲注数
