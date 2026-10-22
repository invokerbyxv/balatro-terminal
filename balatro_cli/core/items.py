"""物品模型：小丑牌、消耗牌、卡包、优惠券。

对应 Lua card.lua 的 Card object 中非"扑克牌"的部分（ability、edition 等）。
"""
from __future__ import annotations
from copy import deepcopy
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
    # 标签带来的免费商品（Lua ability.couponed）：在商店内售价为 0
    couponed: bool = field(default=False)
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

    def copy(self, *, strip_edition: bool = False) -> "JokerItem":
        """复制一张小丑（对应 common_events.lua 的 ``copy_card``）。

        累进状态（``stat``）深拷贝，复制品与本体各自独立成长；贴纸同样随卡
        复制。``strip_edition`` 对应 ``copy_card`` 的第 5 个参数：隐形小丑
        复制负片小丑时会传 true，让复制品不带任何版本。
        """
        return JokerItem(
            key=self.key,
            edition=None if strip_edition else self.edition,
            eternal=self.eternal,
            perishable=self.perishable,
            rental=self.rental,
            perish_tally=self.perish_tally,
            debuffed=self.debuffed,
            stat=deepcopy(self.stat),
            sell_price=self.sell_price,
            buy_cost=self.buy_cost,
            couponed=self.couponed,
            disabled_round=self.disabled_round,
        )


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
class Tag:
    key: str
    skips: int = field(default=0)     # 生成时已跳过的盲注数
