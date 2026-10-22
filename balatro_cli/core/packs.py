"""卡包：Game 的功能切片。

通过 mixin 组合进 :class:`balatro_cli.core.game.Game`，方法仍以 ``self`` 访问
同一份游戏状态，外部调用方式不变。

取牌规则对齐原版（card.lua ``Card:open`` 的 ``G.GAME.pack_choices`` 与
functions/button_callbacks.lua 的 ``can_select_card`` / ``skip_booster``）：

* ``choose`` 是**上限**而非配额：取不满也能结束，已取走的牌保留；
* 每张牌选中即结算并从卡包移除，选满后卡包自动关闭；
* 小丑栏已满时不能取走小丑，需先在卡包界面里出售一张现有小丑。
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
        self.pending_pack = {"key": pk, "cfg": cfg,
                             "items": self._generate_pack_contents(pk),
                             "choose": cfg["choose"], "picked": 0,
                             "free": free}

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

    # ------------------------------------------------------------------
    # 卡包选择
    # ------------------------------------------------------------------
    def pack_choices_left(self) -> int:
        """当前卡包还能选几张（对应原版 G.GAME.pack_choices）。"""
        if not self.pending_pack:
            return 0
        pp = self.pending_pack
        return max(0, pp["choose"] - pp["picked"])

    def pack_joker_fits(self, item: JokerItem) -> bool:
        """这张卡包小丑现在能不能取走（原版 can_select_card：栏满只放行负片）。"""
        return item.negative or len(self.jokers) < self.joker_slots

    def pack_choose(self, indices: List[int]) -> str:
        """从打开的卡包中取牌，逐张结算，最多取 ``choose`` 张。

        ``indices`` 为卡包内下标（按输入顺序结算）。返回：

        * ``none`` —— 没有打开的卡包；
        * ``empty`` —— 没有合法序号；
        * ``no_space`` —— 选中的小丑都因栏位已满没取到（卡包保持打开）；
        * ``more`` —— 已取到牌，还能继续选；
        * ``done`` —— 已取到牌且选择次数用尽，卡包已关闭。
        """
        pp = self.pending_pack
        if not pp or pp["picked"] >= pp["choose"]:
            return "none"
        kind = pp["cfg"]["kind"]
        todo: List[int] = []
        for i in indices:
            if 0 <= i < len(pp["items"]) and i not in todo:
                todo.append(i)
        if not todo:
            return "empty"
        left = pp["choose"] - pp["picked"]
        if len(todo) > left:
            self.say(f"该卡包还能选 {left} 张，多余的序号已忽略")
            todo = todo[:left]

        taken: List[int] = []
        for i in todo:
            item = pp["items"][i]
            # 逐张取走：先取的已进栏，后一张按最新栏位判断，不会一起挤进一个空位
            if kind == "buffoon" and not self.pack_joker_fits(item):
                name = centers_data.joker_cfg(item.key)["cn"]
                self.say(f"{name}：小丑栏已满，请先出售一张小丑再选")
                continue
            self._take_pack_item(item, kind)
            taken.append(i)
        if not taken:
            return "no_space"

        done = set(taken)
        pp["items"] = [it for i, it in enumerate(pp["items"]) if i not in done]
        pp["picked"] += len(taken)
        if kind == "standard":
            self.sort_hand()
        if pp["picked"] >= pp["choose"] or not pp["items"]:
            self.pending_pack = None
            return "done"
        return "more"

    def _take_pack_item(self, item, kind: str):
        """把一张卡包牌结算进牌组 / 小丑栏 / 消耗品栏。"""
        if kind == "buffoon":
            self.jokers.append(item)
            self.say(f"获得小丑：{centers_data.joker_cfg(item.key)['cn']}")
        elif kind == "standard":
            # 与原版一致：直接进牌组，手牌有空位则顺手抓一张
            self.deck.add(item)
            if len(self.hand) < self.hand_size:
                self.hand.append(self.deck.cards.pop())
            self.hologram_count += 1
            self.say(f"标准包：{item.display()} 加入牌组")
        elif len(self.consumeables) < self.consumable_slots:
            self.consumeables.append(item)
            self.say(f"获得消耗牌：{consumable_data.get_consumable_cn(item.key)}")
        else:
            self.say(f"消耗品栏已满，丢弃 {consumable_data.get_consumable_cn(item.key)}")

    def skip_pack(self):
        """结束当前卡包，已经取走的牌保留（对应原版 skip_booster）。"""
        pp = self.pending_pack
        if not pp:
            return
        picked = pp["picked"]
        self.pending_pack = None
        self.say(f"跳过卡包，保留已选的 {picked} 张牌" if picked else "跳过卡包")
