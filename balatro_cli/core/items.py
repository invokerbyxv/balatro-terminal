"""物品模型：小丑牌、消耗牌、卡包、优惠券。

对应 Lua card.lua 的 Card object 中非"扑克牌"的部分（ability、edition 等）。
价格严格按 ``Card:set_cost``（card.lua 369-385）：

    extra_cost  = inflation + 版本加价(foil 2 / holo 3 / poly 5 / neg 5)
    cost        = max(1, floor((base_cost + extra_cost + 0.5) * (100 - discount) / 100))
    sell_cost   = max(1, floor(cost / 2)) + extra_value

因此卖价是「含版本/通胀/折扣的总价」的一半，而不是基础卖价再加版本值。
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

#: 版本加价（对应 card.lua 372-373 的 edition 分支）
EDITION_PRICE = {"foil": 2, "holo": 3, "polychrome": 5, "negative": 5}


def edition_extra(edition: Optional[str]) -> int:
    return EDITION_PRICE.get(edition or "", 0)


def shop_cost(base_cost: int, inflation: int = 0, discount_percent: int = 0,
              edition: Optional[str] = None) -> int:
    """商店价（对应 Card:set_cost）。"""
    return max(1, int((base_cost + inflation + edition_extra(edition) + 0.5)
                      * (100 - discount_percent) / 100))


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
    #: 卡面基础价（对应 Lua 的 ``base_cost``）
    buy_cost: int = field(default=0)
    #: 卖出时在「总价一半」之外另加的金额（鸡蛋 / 礼品卡，Lua 的 extra_value）
    extra_value: int = field(default=0)
    # 标签带来的免费商品（Lua ability.couponed）：在商店内售价为 0
    couponed: bool = field(default=False)
    # 标签临时禁用（深红之心）
    disabled_round: bool = field(default=False)
    # 翻转（琥珀橡果）：只影响显示，效果照常生效；卖价与原版一样显示为 ?
    face_down: bool = field(default=False)

    def __post_init__(self):
        if not self.buy_cost:
            # 延迟导入：data 层不依赖 core，运行时再取目录价即可
            from ..data import centers as centers_data
            self.buy_cost = centers_data.joker_price(self.key)

    @property
    def negative(self) -> bool:
        """负片版本：由 edition 派生（负片编辑 = 负片版本，无独立字段）。"""
        return self.edition == "negative"

    def cost(self, inflation: int = 0, discount_percent: int = 0) -> int:
        return shop_cost(self.buy_cost, inflation, discount_percent, self.edition)

    def sell_value(self, inflation: int = 0, discount_percent: int = 0) -> int:
        return max(1, self.cost(inflation, discount_percent) // 2) + self.extra_value

    def copy(self, *, strip_edition: bool = False) -> "JokerItem":
        """复制一张小丑（对应 common_events.lua 的 ``copy_card``）。

        累进状态（``stat``）深拷贝，复制品与本体各自独立成长；贴纸同样随卡
        复制。``strip_edition`` 对应 ``copy_card`` 的第 5 个参数：隐形小丑
        复制负片小丑时会传 true，让复制品不带任何版本。

        翻转状态（``face_down``）不复制：原版 ``copy_card`` 不复制 ``facing``，
        复制品总是正面朝上。
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
            buy_cost=self.buy_cost,
            extra_value=self.extra_value,
            couponed=self.couponed,
            disabled_round=self.disabled_round,
        )


@dataclass
class ConsumableItem:
    key: str                          # 如 'c_fool'
    edition: Optional[str] = None
    buy_cost: int = field(default=0)
    extra_value: int = field(default=0)

    def __post_init__(self):
        if not self.buy_cost:
            from ..data import consumables as consumable_data
            cfg = consumable_data.ALL_CONSUMABLES.get(self.key)
            if cfg:
                self.buy_cost = cfg["cost"]

    @property
    def negative(self) -> bool:
        return self.edition == "negative"

    def cost(self, inflation: int = 0, discount_percent: int = 0) -> int:
        return shop_cost(self.buy_cost, inflation, discount_percent, self.edition)

    def sell_value(self, inflation: int = 0, discount_percent: int = 0) -> int:
        return max(1, self.cost(inflation, discount_percent) // 2) + self.extra_value


@dataclass
class BoosterPack:
    key: str                          # 如 'p_arcana_normal'
    cost: int = field(default=0)
    buy_cost: int = field(default=0)
    couponed: bool = field(default=False)


@dataclass
class Tag:
    key: str
    skips: int = field(default=0)     # 生成时已跳过的盲注数
