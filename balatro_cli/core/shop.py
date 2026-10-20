"""商店 / 卡包 / 消耗品 / 标签：Game 的功能切片。

通过 mixin 组合进 :class:`balatro_cli.core.game.Game`，方法仍以 ``self`` 访问
同一份游戏状态，外部调用方式不变。拆分的目的是让 game.py 只保留主状态机。
"""
from __future__ import annotations

from .card import Card, ENHANCED, RANKS, SUITS
from .items import JokerItem, ConsumableItem, BoosterPack
from .effects import joker_cn, on_reroll, on_sell_joker, on_shop_closed
from ..data import boosters as booster_data
from ..data import consumables as consumable_data
from ..data import vouchers as voucher_data
from ..data import centers as centers_data

#: 离开商店时保留的标签：它们的效果要等到后续事件才触发（双重标签等下一个标签、
#: 版本标签等下一张商店小丑），原版会一直留在收藏里；其余标签进商店即已生效。
#: 放在这里而不是 game.py，避免 shop_closed 运行时再反向导入 game（循环导入）。
PERSISTENT_TAGS = {"tag_double", "tag_foil", "tag_holo", "tag_polychrome", "tag_negative"}


class ShopMixin:
    """见模块文档。"""

    def enter_shop(self):
        self.shop_jokers = []
        self.shop_boosters = []
        # 优惠券不随商店刷新：本底注抽到的那张在整个底注内保持不变（对应
        # G.GAME.current_round.voucher），兑换后本底注剩余商店不再出现。
        self.shop_free = False
        self.free_reroll_used = False   # 混沌小丑的免费重掷每商店一次
        # 应用标签（版本类标签由 _make_joker_for_shop 在生成商品时消费）。跨商店保留的
        # 标签会再经过这里一次，但它们的效果都是 no-op，不会重复触发。
        for tag in list(self.tags):
            self._apply_tag(tag)
        # 生成商品
        self._generate_shop()
        if self.shop_voucher is None:
            self.pending_free_voucher = False
        self.say("进入商店")

    def _generate_shop(self):
        # 【商品】默认两个：随机小丑 / 塔罗 / 星球 / 增强卡牌
        joker_max = self.shop_joker_max
        free_joker_rarity = self.pending_shop_free_joker
        self.pending_shop_free_joker = None
        for i in range(joker_max):
            if i == 0 and free_joker_rarity:
                rarity = {"uncommon": 2, "rare": 3}[free_joker_rarity]
                key = centers_data.random_joker_key(self, rarity=rarity)
                j = self._make_joker_for_shop(key)
                j.couponed = True   # 免费小丑：商店内售价 0（原版 ability.couponed）
                self.shop_jokers.append(j)
                self.say(f"免费小丑：{centers_data.joker_cfg(key)['cn']}")
                continue
            self.shop_jokers.append(self._generate_shop_goods())
        # 【卡包】默认两个：随机小丑包 / 塔罗包 / 星球包 / 标准包
        for i in range(2):
            if not self.last_shop_was_first and i == 0:
                pk = "p_buffoon_normal"   # 首个商店保证有一格小丑包
            else:
                keys = list(booster_data.PACK_WEIGHTS)
                weights = list(booster_data.PACK_WEIGHTS.values())
                pk = self.rng.weighted_choice(keys, weights, "pack")
            cfg = booster_data.BOOSTERS[pk]
            self.shop_boosters.append(BoosterPack(key=pk, cost=cfg["cost"], buy_cost=cfg["cost"]))
        self.last_shop_was_first = True

    def _make_joker_for_shop(self, key: str):
        cfg = centers_data.joker_cfg(key)
        j = JokerItem(key=key)
        j.buy_cost = centers_data.joker_price(key)
        j.sell_price = max(1, cfg.get("cost", 1) // 2)
        # 标签应用版本（tag.lua store_joker_modify）：首个商店小丑获得版本后标签即被消费；
        # 这类小丑同时带 couponed，在商店内免费
        for tag in list(self.tags):
            if tag.key in ("tag_foil", "tag_holo", "tag_polychrome", "tag_negative"):
                if j.edition is None:
                    j.edition = {"tag_foil": "foil", "tag_holo": "holo",
                                 "tag_polychrome": "polychrome", "tag_negative": "negative"}[tag.key]
                    j.couponed = True
                    self.tags.remove(tag)
                    break
        return j

    def _make_consumable_for_shop(self, key: str):
        c = ConsumableItem(key=key)
        cfg = consumable_data.ALL_CONSUMABLES[key]
        c.buy_cost = cfg["cost"]
        c.sell_price = max(1, cfg["cost"] // 2)
        return c

    def _generate_shop_goods(self):
        """生成一件【商品】：随机小丑 / 塔罗 / 星球 / 增强卡牌。"""
        rates = {"joker": 20, "tarot": 4, "planet": 4, "card": 4}
        if "v_tarot_merchant" in self.used_vouchers:
            rates["tarot"] = 4 * 9.6 / 4 * 4
        if "v_planet_merchant" in self.used_vouchers:
            rates["planet"] = 4 * 9.6 / 4 * 4
        kind = self.rng.weighted_choice(list(rates), list(rates.values()), "shop")
        if kind == "joker":
            key = centers_data.random_joker_key(self)
            return self._make_joker_for_shop(key)
        if kind == "tarot":
            key = self.rng.choice([k for k in consumable_data.TAROTS])
            return self._make_consumable_for_shop(key)
        if kind == "planet":
            key = self.rng.choice([k for k in consumable_data.PLANETS])
            return self._make_consumable_for_shop(key)
        return self._make_card_for_shop()

    def _make_card_for_shop(self) -> Card:
        """生成一张商店【增强卡牌】：随机点数花色 + 随机增强，可能带版本/蜡封。"""
        c = Card(rank=self.rng.choice(RANKS), suit=self.rng.choice(SUITS), uid=0)
        c.enhanced = self.rng.choice(ENHANCED)
        if self.rng.chance(20, "std_ed"):
            c.edition = self.rng.choice(["foil", "holo", "polychrome"])
        if self.rng.chance(15, "std_seal"):
            c.seal = self.rng.choice(["gold", "red", "blue", "purple"])
        return c

    def _card_shop_price(self, card: Card) -> int:
        """增强卡牌基础价：$1 基础 + 增强 $1 + 版本 $2 + 蜡封 $1。"""
        price = 1
        if card.enhanced:
            price += 1
        if card.edition:
            price += 2
        if card.seal:
            price += 1
        return price

    def shop_item_price(self, item) -> int:
        # 标签带来的免费小丑（tag.lua 的 couponed → set_cost 置 0）
        if isinstance(item, JokerItem) and item.couponed:
            return 0
        # 天文学家：星球牌与星球包免费
        if self.any_joker("j_astronomer"):
            if isinstance(item, ConsumableItem) and item.key in consumable_data.PLANETS:
                return 0
            if isinstance(item, BoosterPack) and booster_data.BOOSTERS[item.key]["kind"] == "planet":
                return 0
        if isinstance(item, Card):
            base = self._card_shop_price(item)
        else:
            base = item.buy_cost
        price = max(1, int((base + self.inflation + 0.5) * (100 - self.discount_percent) / 100))
        if self.shop_free:
            return 0
        return price

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
                # 增强卡牌：加入牌组（手牌有空位则抓入手）
                self.deck.add(item)
                if len(self.hand) < self.hand_size:
                    self.hand.append(self.deck.cards.pop())
                self.hologram_count += 1
                self.sort_hand()
                self.say(f"购买增强卡牌：{item.display()}")
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

    def buy_voucher(self) -> bool:
        if not self.shop_voucher:
            return False
        price = 0 if self.pending_free_voucher else 10
        if not self.can_afford(price):
            self.say("金钱不足")
            return False
        self.dollars -= price
        vk = self.shop_voucher
        self.shop_voucher = None   # 对应 card.lua 1850：兑换后本底注不再出现优惠券
        self.pending_free_voucher = False
        self.redeem_voucher(vk)
        return True

    def redeem_voucher(self, vk: str):
        if vk in self.used_vouchers:
            return
        self.used_vouchers.add(vk)
        centers_data.apply_voucher(self, vk)
        self.say(f"启用优惠券：{voucher_data.VOUCHERS[vk]['cn']}")

    def shop_closed(self):
        """离开商店：红卡/珀可等结算，随后自动进入下一盲注。"""
        on_shop_closed(self)
        self.temp_reroll_cost = None
        # 进商店时已生效的标签在此消费，避免下次商店重复触发；双重标签与没被商店
        # 小丑用掉的版本标签留到后续事件（原版标签一直留在收藏里直到触发为止）。
        self.tags = [t for t in self.tags if t.key in PERSISTENT_TAGS]


    @property
    def free_rerolls(self) -> int:
        """混沌小丑：每个商店首次重掷免费，多张不叠加。

        由「是否拥有混沌小丑」实时推导，因此商店中买入即生效、卖出即失效；
        每商店在 enter_shop 重置一次。
        """
        if self.free_reroll_used or not self.any_joker("j_chaos"):
            return 0
        return 1

    def reroll_shop(self) -> bool:
        free = self.free_rerolls > 0
        cost = self.calculate_reroll_cost()
        if free:
            self.free_reroll_used = True
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
        for _ in range(self.shop_joker_max):
            self.shop_jokers.append(self._generate_shop_goods())

    def calculate_reroll_cost(self) -> int:
        if self.free_rerolls > 0:
            return 0
        base = self.temp_reroll_cost if self.temp_reroll_cost is not None else self.reroll_cost_base
        return max(0, base + self.reroll_cost_increase)

    def sell_joker(self, index: int) -> bool:
        if 0 <= index < len(self.jokers):
            j = self.jokers[index]
            if j.eternal:
                self.say("永恒小丑牌无法出售")
                return False
            self.dollars += j.sell_value()
            # 卖出效果必须在移除之前结算：被卖的小丑若是蓝图，它会把 selling_self
            # 转发给自己右侧的小丑（原版 card.lua:1599 的 calculate_joker 语义）。
            on_sell_joker(self, j)
            self.jokers.pop(index)
            self.say("售出小丑牌")
            return True
        return False

    def sell_consumable(self, index: int) -> bool:
        if 0 <= index < len(self.consumeables):
            c = self.consumeables[index]
            self.dollars += c.sell_value()
            self.consumeables.pop(index)
            self.say("售出消耗牌")
            return True
        return False
