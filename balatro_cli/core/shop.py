"""商店 / 商品生成 / 优惠券 / 卡包：Game 的功能切片。

通过 mixin 组合进 :class:`balatro_cli.core.game.Game`，方法仍以 ``self`` 访问
同一份游戏状态，外部调用方式不变。拆分的目的是让 game.py 只保留主状态机。

生成规则对齐原版：

* 商品槽按 ``G.GAME.joker_rate/tarot_rate/planet_rate/playing_card_rate/
  spectral_rate`` 加权抽取（默认 20 / 4 / 4 / 0 / 0，即**默认不出售扑克牌与
  幻灵牌**）；
* 小丑按 70% / 25% / 5% 抽稀有度（传说只能由「灵魂」给出），并过卡池门控；
* 每张小丑都过一次 ``poll_edition``，可以自带版本；
* 卡包按原版 32 个 Booster 定义折算的权重抽取，含 jumbo / spectral 变体。
"""
from __future__ import annotations

from .card import Card, ENHANCED, RANKS, SUITS
from .items import BoosterPack, ConsumableItem, JokerItem, shop_cost
from .effects import (TAG_FINAL_PASS, TAG_SHOP_START, TAG_VOUCHER_ADD,
                      edition_tag_for_couponed, forced_rarity_tag,
                      joker_cn, on_reroll, on_shop_closed, on_sell_card,
                      on_sell_joker)
from ..data import boosters as booster_data
from ..data import centers as centers_data
from ..data import consumables as consumable_data
from ..data import vouchers as voucher_data


class ShopMixin:
    """见模块文档。"""

    # ------------------------------------------------------------------
    # 进入商店
    # ------------------------------------------------------------------
    def enter_shop(self):
        self.shop_jokers = []
        self.shop_boosters = []
        self.shop_used_jokers = set()      # 本次商店已生成的小丑（原版 used_jokers）
        self.shop_free = False
        self.free_reroll_used = 0          # 混沌小丑的免费重掷次数（每商店重置）
        # shop_start：D6 标签把本商店重掷费降到 0（原版 game.lua 3093-3095）
        self._apply_tags(TAG_SHOP_START)
        self._generate_shop()
        self.say("进入商店")

    def _generate_shop(self):
        # 【商品】按权重抽；「稀有/罕见标签」会把第一个商品替换成指定稀有度的小丑
        for _ in range(self.shop_joker_max):
            self.shop_jokers.append(self._generate_shop_goods())

        # 【优惠券】本底注抽到的那张；「优惠券标签」在生成之后再额外加 1 张
        self.shop_offer_vouchers = list(self.shop_vouchers)
        self._apply_tags(TAG_VOUCHER_ADD)
        if self.pending_extra_voucher:
            self.pending_extra_voucher = False
            extra = self._next_voucher_key()
            if extra and extra not in self.shop_offer_vouchers:
                self.shop_offer_vouchers.append(extra)

        # 【卡包】首个商店保底一个普通小丑包，其余按权重抽
        for i in range(2):
            if not self.last_shop_was_first and i == 0:
                pk = "p_buffoon_normal"
            else:
                keys = list(booster_data.PACK_WEIGHTS)
                weights = list(booster_data.PACK_WEIGHTS.values())
                pk = self.rng.weighted_choice(keys, weights, "pack")
            cfg = booster_data.BOOSTERS[pk]
            self.shop_boosters.append(BoosterPack(key=pk, cost=cfg["cost"], buy_cost=cfg["cost"]))
        self.last_shop_was_first = True

        # shop_final_pass：优惠券标签把**当前已生成**的商品全部置为免费
        self._apply_tags(TAG_FINAL_PASS)

    # ------------------------------------------------------------------
    # 商品生成
    # ------------------------------------------------------------------
    def _shop_rates(self) -> dict:
        """商品槽的种类权重（对应 create_card_for_shop 的 total_rate）。"""
        rates = {
            "joker": self.joker_rate,
            "tarot": self.tarot_rate,
            "planet": self.planet_rate,
            "card": self.playing_card_rate,
            "spectral": self.spectral_rate,
        }
        return {k: v for k, v in rates.items() if v > 0}

    def _poll_shop_type(self) -> str:
        rates = self._shop_rates()
        return self.rng.weighted_choice(list(rates), list(rates.values()), "shop")

    def _generate_shop_goods(self):
        """生成一件【商品】。"""
        forced = forced_rarity_tag(self)
        if forced is not None:
            key = centers_data.random_joker_key(self, rarity=forced,
                                                exclude=self.shop_used_jokers)
            self.shop_used_jokers.add(key)
            j = self._make_joker_for_shop(key)
            j.couponed = True
            self.say(f"标签：免费{centers_data.RARITY_CN[forced]}小丑 {joker_cn(key)}")
            return j
        kind = self._poll_shop_type()
        if kind == "joker":
            key = centers_data.random_joker_key(self, exclude=self.shop_used_jokers)
            self.shop_used_jokers.add(key)
            return self._make_joker_for_shop(key)
        if kind in ("tarot", "planet", "spectral"):
            return self._make_consumable_for_shop(
                consumable_data.random_consumable(self, kind))
        return self._make_card_for_shop()

    def make_joker(self, key: str, shop: bool = True):
        """生成一张小丑并抽一次版本（对应 ``create_card`` 的 poll_edition）。

        ``shop=True`` 时还会尝试消费版本类标签（``store_joker_modify``，只在
        商店商品上生效——原版不给卡包小丑套用标签）。
        """
        j = JokerItem(key=key)
        j.edition = centers_data.poll_edition(self)
        if shop and j.edition is None:
            edition = edition_tag_for_couponed(self)
            if edition:
                j.edition = edition
                j.couponed = True
        self._apply_stake_stickers(j)
        return j

    def _apply_stake_stickers(self, j: JokerItem):
        """赌注贴纸：永恒 / 易腐 / 租赁（common_events.lua 2137-2147）。

        原版对商店与卡包小丑各抽一次 ``etperpoll``：> 0.7 为永恒、
        (0.4, 0.7] 为易腐（都需要对应赌注开启）；租赁另抽一次 ``ssjr``。
        """
        if self.enable_eternals_in_shop or self.enable_perishables_in_shop:
            x = self.rng.roll("etperpoll")
            if self.enable_eternals_in_shop and x > 0.7:
                j.eternal = True
            elif self.enable_perishables_in_shop and 0.4 < x <= 0.7:
                j.perishable = True
        if self.enable_rentals_in_shop and not j.eternal and self.rng.roll("ssjr") > 0.7:
            j.rental = True

    def _make_joker_for_shop(self, key: str):
        """生成一张商店小丑。"""
        return self.make_joker(key, shop=True)

    def _make_consumable_for_shop(self, key: str):
        return ConsumableItem(key=key)

    def _make_card_for_shop(self) -> Card:
        """商店扑克牌（对应 ``create_card('Base' or 'Enhanced')``）。

        默认不出售（``playing_card_rate = 0``）；魔术戏法把它提到 4。幻象还会给
        40% 的增强与 20% 的版本（原版这里不附加蜡封）。
        """
        illusion = self.has_voucher("v_illusion")
        enhanced = illusion and self.rng.roll("illusion") > 0.6
        c = Card(rank=self.rng.choice(RANKS), suit=self.rng.choice(SUITS), uid=0)
        if enhanced:
            c.enhanced = self.rng.choice(ENHANCED)
        if illusion and self.rng.roll("illusion") > 0.8:
            x = self.rng.roll("illusion")
            c.edition = "polychrome" if x > 0.85 else ("holo" if x > 0.5 else "foil")
        return c

    def _card_shop_price(self, card: Card) -> int:
        """扑克牌价格：基础 $1，增强不加价，只有版本加价（card.lua 369-385）。"""
        return shop_cost(1, self.inflation, self.discount_percent, card.edition)

    def shop_item_price(self, item) -> int:
        # 标签带来的免费商品（Lua ability.couponed → set_cost 置 0）
        if getattr(item, "couponed", False):
            return 0
        # 天文学家：星球牌与星球包免费
        if self.any_joker("j_astronomer"):
            if isinstance(item, ConsumableItem) and item.key in consumable_data.PLANETS:
                return 0
            if isinstance(item, BoosterPack) and booster_data.BOOSTERS[item.key]["kind"] == "planet":
                return 0
        if isinstance(item, Card):
            return self._card_shop_price(item)
        return shop_cost(item.buy_cost, self.inflation, self.discount_percent,
                         getattr(item, "edition", None))

    # ------------------------------------------------------------------
    # 购买 / 出售
    # ------------------------------------------------------------------
    def buy_shop_item(self, index: int) -> bool:
        if 0 <= index < len(self.shop_jokers):
            item = self.shop_jokers[index]
            if isinstance(item, JokerItem):
                if len(self.jokers) >= self.joker_slots and not item.negative:
                    self.say("小丑牌栏位已满")
                    return False
            elif isinstance(item, ConsumableItem):
                if len(self.consumeables) >= self.consumable_slots:
                    self.say("消耗品栏位已满")
                    return False
            price = self.shop_item_price(item)
            if not self.can_afford(price):
                self.say("金钱不足")
                return False
            self.dollars -= price
            self.shop_jokers.pop(index)
            if self.inflation_enabled:
                self.inflation += 1
            if isinstance(item, JokerItem):
                self.jokers.append(item)
                self.say(f"购买小丑牌：{joker_cn(item.key)}")
            elif isinstance(item, ConsumableItem):
                self.consumeables.append(item)
                self.say(f"购买消耗牌：{consumable_data.get_consumable_cn(item.key)}")
            else:
                # 扑克牌：加入牌组（手牌有空位则抓入手）
                self.deck.add(item)
                if len(self.hand) < self.hand_size:
                    self.hand.append(self.deck.cards.pop())
                self.hologram_count += 1
                self.sort_hand()
                self.say(f"购买扑克牌：{item.display()}")
            return True
        return False

    def buy_booster(self, index: int) -> bool:
        if 0 <= index < len(self.shop_boosters):
            bp = self.shop_boosters[index]
            price = self.shop_item_price(bp)
            if not self.can_afford(price):
                self.say("金钱不足")
                return False
            self.dollars -= price
            self.shop_boosters.pop(index)
            if self.inflation_enabled:
                self.inflation += 1
            self._open_pack(bp)
            return True
        return False

    def buy_voucher(self, index: int = 0) -> bool:
        if not (0 <= index < len(self.shop_offer_vouchers)):
            return False
        vk = self.shop_offer_vouchers[index]
        price = self.voucher_price()
        if not self.can_afford(price):
            self.say("金钱不足")
            return False
        self.dollars -= price
        self.shop_offer_vouchers.pop(index)
        # 本底注固定的那张兑换后本底注不再出现；标签额外给的那张只属于本次商店
        if vk in self.shop_vouchers:
            self.shop_vouchers.remove(vk)
        self.redeem_voucher(vk)
        return True

    def voucher_price(self) -> int:
        """优惠券价格：$10 也吃折扣与通胀（card.lua 375 的 set_cost 对所有卡生效）。"""
        return shop_cost(10, self.inflation, self.discount_percent)

    def redeem_voucher(self, vk: str):
        if vk in self.used_vouchers:
            return
        self.used_vouchers.add(vk)
        centers_data.apply_voucher(self, vk)
        self.say(f"启用优惠券：{voucher_data.VOUCHERS[vk]['cn']}")

    def shop_closed(self):
        """离开商店：红卡/珀可等结算，随后自动进入下一盲注。"""
        # 兜底：卡包还开着就离开商店时，已取走的牌保留，剩余的直接放弃。
        self.skip_pack()
        on_shop_closed(self)
        self.temp_reroll_cost = None

    # ------------------------------------------------------------------
    # 重掷
    # ------------------------------------------------------------------
    @property
    def free_rerolls(self) -> int:
        """混沌小丑：每个商店首次重掷免费，多张叠加（每张 1 次）。

        由「持有几张混沌小丑」实时推导，因此商店中买入即生效、卖出即失效；
        每商店在 enter_shop 重置。
        """
        if not self.any_joker("j_chaos"):
            return 0
        return max(0, self.count_jokers("j_chaos") - self.free_reroll_used)

    def reroll_shop(self) -> bool:
        free = self.free_rerolls > 0
        cost = self.calculate_reroll_cost()
        if free:
            self.free_reroll_used += 1
        elif not self.can_afford(cost):
            self.say("金钱不足")
            return False
        else:
            self.dollars -= cost
        # 免费重掷不抬高后续价格（原版 calculate_reroll_cost(final_free) 的 skip_increment）
        if not free:
            self.reroll_cost_increase += 1
        self.rerolls_total += 1
        on_reroll(self)
        self._generate_shop_jokers_only()
        return True

    def _generate_shop_jokers_only(self):
        self.shop_jokers = []
        self.shop_used_jokers = set()
        for _ in range(self.shop_joker_max):
            self.shop_jokers.append(self._generate_shop_goods())

    def calculate_reroll_cost(self) -> int:
        if self.free_rerolls > 0:
            return 0
        base = self.temp_reroll_cost if self.temp_reroll_cost is not None else self.reroll_cost_base
        return max(0, base + self.reroll_cost_increase)

    # ------------------------------------------------------------------
    # 出售
    # ------------------------------------------------------------------
    def sell_joker(self, index: int) -> bool:
        if 0 <= index < len(self.jokers):
            j = self.jokers[index]
            if j.eternal:
                self.say("永恒小丑牌无法出售")
                return False
            self.dollars += j.sell_value(self.inflation, self.discount_percent)
            # 卖出效果必须在移除之前结算：被卖的小丑若是蓝图，它会把 selling_self
            # 转发给自己右侧的小丑（原版 card.lua:1599 的 calculate_joker 语义）。
            on_sell_joker(self, j)
            self.jokers.pop(index)
            self._leaf_sold()
            self.say("售出小丑牌")
            return True
        return False

    def sell_consumable(self, index: int) -> bool:
        if 0 <= index < len(self.consumeables):
            c = self.consumeables[index]
            self.dollars += c.sell_value(self.inflation, self.discount_percent)
            self.consumeables.pop(index)
            on_sell_card(self)
            self._leaf_sold()
            self.say("售出消耗牌")
            return True
        return False


    def _leaf_sold(self):
        """绿叶头目：卖掉任意一张牌即解除全部 debuff（card.lua 1616）。"""
        if self.blind_key == "bl_final_leaf" and not self.boss_disabled():
            self.disable_current_blind()
            self.say("绿叶：已卖掉一张牌，头目效果解除")