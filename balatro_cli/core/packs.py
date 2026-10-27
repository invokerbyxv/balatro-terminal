"""卡包：Game 的功能切片。

通过 mixin 组合进 :class:`balatro_cli.core.game.Game`，方法仍以 ``self`` 访问
同一份游戏状态，外部调用方式不变。

取牌规则对齐原版（card.lua ``Card:open`` 的 ``G.GAME.pack_choices`` 与
functions/button_callbacks.lua 的 ``can_select_card`` / ``skip_booster``）：

* ``choose`` 是**上限**而非配额：取不满也能结束，已取走的牌保留；
* 每张牌选中即结算并从卡包移除，选满后卡包自动关闭；
* 小丑栏 / 消耗品栏已满时不能取走对应牌，需先出售一张再选；
* 同一个卡包内不出现重复的塔罗 / 星球 / 幻灵 / 小丑牌（持有「马戏团长」时除外）；
* 开包触发 ``open_booster``（幻觉），跳过卡包触发 ``skipping_booster``（红牌）。
"""
from __future__ import annotations

from typing import List

from .card import Card, ENHANCED, RANKS, SUITS
from .items import BoosterPack, ConsumableItem, JokerItem
from .lookup import roll_prob
from ..data import boosters as booster_data
from ..data import centers as centers_data
from ..data import consumables as consumable_data


class PackMixin:
    """见模块文档。"""

    # ------------------------------------------------------------------
    # 开包
    # ------------------------------------------------------------------
    def _open_pack(self, bp: BoosterPack):
        self._open_pack_now(bp.key, free=False)

    def _open_pack_now(self, pk: str, free: bool = True):
        cfg = booster_data.BOOSTERS[pk]
        self.pending_pack = {"key": pk, "cfg": cfg,
                             "items": self._generate_pack_contents(pk),
                             "choose": cfg["choose"], "picked": 0,
                             "free": free}
        self._fire_open_booster()

    def _fire_open_booster(self):
        """打开补充包（``open_booster`` 上下文）：幻觉有 1/2 概率给张塔罗。"""
        for j in list(self.jokers):
            if j.debuffed:
                continue
            if j.key != "j_hallucination":
                continue
            if len(self.consumeables) >= self.consumable_slots:
                continue
            if roll_prob(self, 2, "halu"):
                key = consumable_data.random_consumable(self, "tarot")
                self.gain_consumable(key)
                self.say(f"幻觉：开启卡包获得 {consumable_data.get_consumable_cn(key)}")

    # ------------------------------------------------------------------
    # 卡包内容
    # ------------------------------------------------------------------
    def _generate_pack_contents(self, pk: str) -> list:
        cfg = booster_data.BOOSTERS[pk]
        kind = cfg["kind"]
        n = cfg["pack_size"]
        items: list = []
        if kind in ("tarot", "planet", "spectral"):
            drawn: set = set()
            for i in range(n):
                key = self._pack_consumable_key(kind, i, drawn)
                drawn.add(key)
                items.append(ConsumableItem(key=key))
        elif kind == "buffoon":
            drawn = set() if self.any_joker("j_ring_master") else {j.key for j in self.jokers}
            for _ in range(n):
                key = centers_data.random_joker_key(self, exclude=drawn)
                drawn.add(key)
                # 卡包小丑同样过 poll_edition，但不吃版本类标签
                items.append(self.make_joker(key, shop=False))
        elif kind == "standard":
            for _ in range(n):
                items.append(self._random_standard_card())
        return items

    def _pack_consumable_key(self, kind: str, index: int, drawn: set) -> str:
        """一张卡包消耗牌（对应 card.lua 1728-1775 的 create_card 分支）。

        - 塔罗包：预兆之球 20% 改为幻灵牌；
        - 星球包：望远镜让第 1 张变成「最常打牌型」对应的星球牌；
        - 灵魂 / 黑洞：每张牌 0.3% 概率被替换（不会作为普通候选出现）。
        """
        if kind == "tarot":
            if self.has_voucher("v_omen_globe") and self.rng.roll("omen_globe") > 0.8:
                pool_kind = "spectral"
            else:
                pool_kind = "tarot"
        elif kind == "planet":
            pool_kind = "planet"
            if self.has_voucher("v_telescope") and index == 0:
                hand = self.most_played_hand()
                planet = consumable_data.planet_for_hand(hand) if hand else None
                if planet:
                    return planet
        else:
            pool_kind = "spectral"

        # 灵魂 / 黑洞的 0.3% 替换：塔罗/幻灵 → 灵魂，星球/幻灵 → 黑洞
        # （原版两段判定各用一次 pseudoseed，因此互相独立）
        if pool_kind in ("tarot", "spectral") and self.rng.roll("soul") > 0.997:
            return "c_soul"
        if pool_kind in ("planet", "spectral") and self.rng.roll("soul") > 0.997:
            return "c_black_hole"

        keys = consumable_data.pool(self, pool_kind)
        if not self.any_joker("j_ring_master"):
            keys = [k for k in keys if k not in drawn] or keys
        return self.rng.choice(keys, pool_kind)

    def _random_standard_card(self) -> Card:
        """标准包：40% 增强 / 20% 蜡封 / 版本按 poll_edition(2, no_neg) 抽。

        对应 card.lua 1758-1772。概率：彩绘 1.2% / 全息 4% / 箔片 8%。
        """
        c = Card(rank=self.rng.choice(RANKS), suit=self.rng.choice(SUITS), uid=0)
        if self.rng.roll("stdset") > 0.6:
            c.enhanced = self.rng.choice(ENHANCED)
        c.edition = centers_data.poll_edition(self, mod=2, no_neg=True)
        if self.rng.roll("stdseal") > 0.8:
            x = self.rng.roll("stdsealtype")
            c.seal = ("red" if x > 0.75 else
                      "blue" if x > 0.5 else
                      "gold" if x > 0.25 else "purple")
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

    def pack_consumable_fits(self) -> bool:
        """消耗品栏还有空位取走卡包里的消耗牌。"""
        return len(self.consumeables) < self.consumable_slots

    def pack_choose(self, indices: List[int]) -> str:
        """从打开的卡包中取牌，逐张结算，最多取 ``choose`` 张。

        ``indices`` 为卡包内下标（按输入顺序结算）。返回：

        * ``none`` —— 没有打开的卡包；
        * ``empty`` —— 没有合法序号；
        * ``no_space`` —— 选中的牌都因栏位已满没取到（卡包保持打开）；
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
            if kind in ("tarot", "planet", "spectral") and not self.pack_consumable_fits():
                self.say("消耗品栏已满，请先使用或出售一张再选")
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
        else:
            self.consumeables.append(item)
            self.say(f"获得消耗牌：{consumable_data.get_consumable_cn(item.key)}")

    def skip_pack(self):
        """结束当前卡包，已经取走的牌保留（对应原版 skip_booster）。

        跳过卡包会触发 ``skipping_booster``（红牌 +3 倍率）。
        """
        pp = self.pending_pack
        if not pp:
            return
        picked = pp["picked"]
        self.pending_pack = None
        self.say(f"跳过卡包，保留已选的 {picked} 张牌" if picked else "跳过卡包")
        self._fire_skipping_booster()

    def _fire_skipping_booster(self):
        for j in list(self.jokers):
            if j.debuffed:
                continue
            if j.key == "j_red_card":
                j.stat["mult"] = j.stat.get("mult", 0) + 3
                self.say("红牌：跳过卡包 +3 倍率")
