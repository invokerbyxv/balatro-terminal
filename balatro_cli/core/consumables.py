"""商店 / 卡包 / 消耗品 / 标签：Game 的功能切片。

通过 mixin 组合进 :class:`balatro_cli.core.game.Game`，方法仍以 ``self`` 访问
同一份游戏状态，外部调用方式不变。拆分的目的是让 game.py 只保留主状态机。
"""
from __future__ import annotations

from typing import List

from .items import ConsumableItem
from .effects import finish_consumable_target, use_consumable
from ..data import consumables as consumable_data


class ConsumableMixin:
    """见模块文档。"""

    def use_consumable(self, index: int):
        if 0 <= index < len(self.consumeables):
            c = self.consumeables[index]
            return use_consumable(self, c)
        return None

    def finish_consumable_target(self, indices: List[int]) -> str:
        """CLI 选择完目标牌后调用。indices 为手牌下标。"""
        cards = [self.hand[i] for i in indices if 0 <= i < len(self.hand)]
        result = finish_consumable_target(self, cards)
        self.sort_hand()
        return result

    def gain_random_consumable_of(self, kind: str):
        if kind == "tarot":
            pool = consumable_data.TAROTS
        elif kind == "planet":
            pool = consumable_data.PLANETS
        elif kind == "spectral":
            pool = consumable_data.SPECTRALS
        else:
            pool = consumable_data.ALL_CONSUMABLES
        key = self.rng.choice(list(pool))
        if len(self.consumeables) >= self.consumable_slots:
            self.say("消耗品栏已满")
            return
        self.gain_consumable(key)
        self.say(f"生成消耗牌：{consumable_data.get_consumable_cn(key)}")

    def gain_consumable(self, key: str):
        if len(self.consumeables) >= self.consumable_slots:
            self.say("消耗品栏位已满")
            return
        cfg = consumable_data.ALL_CONSUMABLES[key]
        self.consumeables.append(ConsumableItem(key=key, buy_cost=cfg["cost"],
                                                sell_price=max(1, cfg["cost"] // 2)))

    def _gain_random_tarot(self):
        key = self.rng.choice(list(consumable_data.TAROTS))
        self.gain_consumable(key)
        self.say(f"紫色蜡封生成塔罗牌：{consumable_data.get_consumable_cn(key)}")

    def _apply_tag(self, tag: Tag):
        apply_tag(self, tag)
