"""商店 / 卡包 / 消耗品 / 标签：Game 的功能切片。

通过 mixin 组合进 :class:`balatro_cli.core.game.Game`，方法仍以 ``self`` 访问
同一份游戏状态，外部调用方式不变。拆分的目的是让 game.py 只保留主状态机。
"""
from __future__ import annotations

from typing import List

from .card import Card, ENHANCED, RANKS, SUITS
from .items import JokerItem, ConsumableItem, BoosterPack
from ..data import boosters as booster_data
from ..data import consumables as consumable_data
from ..data import centers as centers_data


class PackMixin:
    """见模块文档。"""

    def _open_pack(self, bp: BoosterPack):
        self._open_pack_now(bp.key, free=False)

    def _open_pack_now(self, pk: str, free: bool = True):
        cfg = booster_data.BOOSTERS[pk]
        items = self._generate_pack_contents(pk)
        self.pending_pack = {"key": pk, "cfg": cfg, "items": items,
                             "choose": cfg["choose"], "free": free,
                             "next": None}

    def _generate_pack_contents(self, pk: str) -> list:
        cfg = booster_data.BOOSTERS[pk]
        kind = cfg["kind"]
        n = cfg["pack_size"]
        items = []
        if kind == "tarot":
            for _ in range(n):
                items.append(ConsumableItem(key=self.rng.choice(list(consumable_data.TAROTS))))
        elif kind == "planet":
            for _ in range(n):
                items.append(ConsumableItem(key=self.rng.choice(list(consumable_data.PLANETS))))
        elif kind == "spectral":
            for _ in range(n):
                items.append(ConsumableItem(key=self.rng.choice(list(consumable_data.SPECTRALS))))
        elif kind == "buffoon":
            for _ in range(n):
                key = centers_data.random_joker_key(self)
                j = JokerItem(key=key)
                cfgj = centers_data.joker_cfg(key)
                j.buy_cost = cfgj["cost"]
                j.sell_price = max(1, cfgj["cost"] // 2)
                items.append(j)
        elif kind == "standard":
            for _ in range(n):
                items.append(self._random_standard_card())
        return items

    def _random_standard_card(self) -> Card:
        c = Card(rank=self.rng.choice(RANKS), suit=self.rng.choice(SUITS), uid=0)
        if self.rng.chance(8, "std_enh"):
            c.enhanced = self.rng.choice(ENHANCED)   # card.py 的无 m_ 前缀键
        if self.rng.chance(20, "std_ed"):
            c.edition = self.rng.choice(["foil", "holo", "polychrome"])
        if self.rng.chance(15, "std_seal"):
            c.seal = self.rng.choice(["gold", "red", "blue", "purple"])
        return c

    def pack_choose(self, indices: List[int]) -> str:
        """卡包中挑选。indices 为待选卡包内的下标；必须一次选满 choose 张。"""
        if not self.pending_pack:
            return "none"
        pp = self.pending_pack
        choose = pp["choose"]
        unique = []
        for i in indices:
            if 0 <= i < len(pp["items"]) and i not in unique:
                unique.append(i)
        if len(unique) != choose:
            self.say(f"该卡包需要选择 {choose} 张牌")
            return "needs_more"
        chosen = [pp["items"][i] for i in unique]
        kind = pp["cfg"]["kind"]
        for item in chosen:
            if kind == "tarot":
                if len(self.consumeables) < self.consumable_slots:
                    self.consumeables.append(item)
                else:
                    self.say("消耗品栏已满，丢弃")
            elif kind == "planet":
                if len(self.consumeables) < self.consumable_slots:
                    self.consumeables.append(item)
                else:
                    self.say("消耗品栏已满，丢弃")
            elif kind == "spectral":
                if len(self.consumeables) < self.consumable_slots:
                    self.consumeables.append(item)
                else:
                    self.say("消耗品栏已满，丢弃")
            elif kind == "buffoon":
                if len(self.jokers) < self.joker_slots or item.negative:
                    self.jokers.append(item)
                else:
                    # 小丑栏已满：暂存，稍后由玩家出售现有小丑腾出空位，或放弃
                    pp.setdefault("sells", []).append(item)
            elif kind == "standard":
                self.hologram_count += 1
        if kind == "standard":
            self.say(f"标准包：{len(chosen)} 张牌加入牌组")
            for item in chosen:
                self.deck.add(item)
                if len(self.hand) < self.hand_size:
                    self.hand.append(self.deck.cards.pop())
            self.sort_hand()
        if pp.get("sells"):
            self.say(f"小丑栏已满：{len(pp['sells'])} 张小丑待放入，请先出售一张现有小丑腾出空位")
            return "needs_sell"
        self.pending_pack = None
        return "done"

    def skip_pack(self):
        """跳过当前卡包选择。"""
        self.pending_pack = None

    def pack_sell_for_waiting(self, index: int) -> bool:
        """小丑栏满时的补救：出售一张现有小丑（index），随即放入一张待选小丑。

        出售成功并放入则返回 True；放完最后一张待选小丑后清空 pending_pack。
        出售失败（如永恒小丑）或 index 无效返回 False。
        """
        if not self.pending_pack or not self.pending_pack.get("sells"):
            return False
        if not self.sell_joker(index):
            return False
        item = self.pending_pack["sells"].pop(0)
        self.jokers.append(item)
        self.say(f"放入小丑：{centers_data.joker_cfg(item.key)['cn']}")
        if not self.pending_pack["sells"]:
            self.pending_pack = None
        return True

    def pack_discard_waiting(self) -> bool:
        """放弃放入待选小丑（直接丢弃），并结束当前卡包。"""
        if not self.pending_pack or not self.pending_pack.get("sells"):
            return False
        n = len(self.pending_pack["sells"])
        self.pending_pack = None
        self.say(f"放弃 {n} 张待放入的小丑")
        return True
