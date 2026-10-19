"""游戏主状态机：建局、盲注调度、出牌弃牌、回合结算与收入。

对应 Lua game.lua + functions/* 的状态机。纯逻辑，不含 I/O。
商店 / 卡包 / 消耗品 / 标签分别在 shop.py、packs.py、consumables.py 里，
通过 mixin 组合成完整的 Game。
"""
import random
from typing import List, Optional

from .card import Card, RANKS, SUITS
from .deck import Deck, build_deck
from .rng import RNG
from .items import JokerItem, ConsumableItem, BoosterPack, Tag
from .hand_eval import HAND_ORDER
from .effects import (
    is_face_card, joker_cn, joker_dollar_bonus, joker_hand_size_bonus,
    on_blind_select, on_discard, on_end_round, roll_prob,
)
from .scoring import evaluate_play
from .shop import ShopMixin
from .packs import PackMixin
from .consumables import ConsumableMixin
from ..data import decks as deck_data
from ..data import blinds as blind_data
from ..data import tags as tag_data
from ..data import vouchers as voucher_data

# 起始参数（misc_functions.lua get_starting_params）
START_PARAMS = {
    "dollars": 4, "hand_size": 8, "discards": 3, "hands": 4,
    "reroll_cost": 5, "joker_slots": 5, "consumable_slots": 2,
    "ante_scaling": 1,
}

#: 通关判定线（对应 G.GAME.win_ante）。无尽模式没有回合上限：通关只是在这里宣布，
#: 之后底注照常推进，决战头目仍在 WIN_ANTE 的倍数底jin注出现。
WIN_ANTE = 8

#: 出牌 / 弃牌一次最多 5 张（对应 Lua 的 play/discard 区上限，牌型判定也以此为限）
MAX_PLAY_SIZE = 5

#: 离开商店时保留的标签：它们的效果要等到后续事件才触发（双重标签等下一个标签、
#: 版本标签等下一张商店小丑），原版会一直留在收藏里；其余标签进商店即已生效。
PERSISTENT_TAGS = {"tag_double", "tag_foil", "tag_holo", "tag_polychrome", "tag_negative"}


class Game(ShopMixin, PackMixin, ConsumableMixin):
    def __init__(self, seed: Optional[int] = None):
        import os
        self.seed = seed if seed is not None else (os.urandom(4)[0] | (os.urandom(4)[0] << 8))
        self.rng = RNG(self.seed)
        self.messages: List[str] = []          # 最近一轮展示消息
        self.deck_key: str | None = None
        self.deck: Deck = Deck()
        self.hand: List[Card] = []
        self.play: List[Card] = []
        self.sort_mode: Optional[str] = "rank"   # 手牌排序方式："rank"/"suit"/None(手动排序)
        self._round_cards: List[Card] = []       # 本盲注已离手、待回收到牌堆的牌
        self._destroyed_ids: set[int] = set()
        self.jokers: List[JokerItem] = []
        self.consumeables: List[ConsumableItem] = []
        self.tags: List[Tag] = []

        # 经济 / 回合
        self.dollars = START_PARAMS["dollars"]
        self.reroll_cost_base = START_PARAMS["reroll_cost"]
        self.reroll_cost_increase = 0
        self.hands_left = START_PARAMS["hands"]
        self.discards_left = START_PARAMS["discards"]
        self.hand_size = START_PARAMS["hand_size"]
        #: 手牌上限的持久修正（灵应盘/灵质），与优惠券/小丑加成一起由 round_hand_size 汇总
        self.hand_size_offset = 0
        #: 本回合的临时修正（杂耍标签），回合结束时清零（Lua round_resets.temp_handsize）
        self.temp_hand_size = 0
        self._joker_slots = START_PARAMS["joker_slots"]
        self._consumable_slots = START_PARAMS["consumable_slots"]
        self.interest_cap = 25
        self.ante_scaling = 1
        self.no_interest = False
        self.money_per_hand = 1
        self.money_per_discard = 0
        self.discount_percent = 0
        self.shop_free = False
        self.temp_reroll_cost: Optional[int] = None
        self.free_reroll_used = False
        self.shop_joker_max = 2

        # 进度
        self.ante = 1
        self.round = 0                     # 回合计数（对应 G.GAME.round）
        self.chips = 0
        self.run_won = False
        self.run_lost = False
        #: 通关后是否进入无尽模式。原版没有回合上限：第 8 底注通关后关闭通关窗口
        #: （UI_definitions.lua create_UIBox_win 的「Endless Mode」按钮）即继续，
        #: 只有失败或退出才会停；通关只宣布一次，之后回合文本变为「无尽回合」。
        self.endless = False
        self.blind_key: Optional[str] = None       # 当前迎战的盲注
        self.blind_status = {"Small": "Select", "Big": "Upcoming", "Boss": "Upcoming"}
        self.blind_on_deck = "Small"
        self.boss_key: Optional[str] = None
        self.skips = 0
        self.bosses_used: List[str] = []
        #: 头目盲注的「已准备」标记（对应 blind.lua 的 self.prepped）：鱼在打出牌后
        #: 置位，紧随其后的那次补牌抽到的牌保持背面朝下，补牌结束即清除。
        self.blind_prepped = False

        # 手牌等级
        self.hand_levels = {h: 1 for h in HAND_ORDER}
        self.played_this_ante: List[Card] = []   # 柱 boss 用
        self.hands_played_round = 0
        self.last_hand_name: Optional[str] = None
        self.round_hand_played: List[str] = []   # 眼睛 boss 用（本回合已打牌型）

        # 商店
        self.shop_jokers: List[JokerItem] = []
        self.shop_boosters: List[BoosterPack] = []
        #: 本底注的优惠券（对应 G.GAME.current_round.voucher）：每个底注只随机抽一次
        #: （开局与击败头目后的回合重置），同一底注内的各商店展示同一张，兑换后清空。
        self.shop_voucher: Optional[str] = None
        self.used_vouchers: set = set()
        self.inflation = 0
        # 通货膨胀挑战（原版 c_inflation_1）才启用：每购买一件商品，商店价格 +1。
        # CLI 暂未实现挑战系统，默认关闭；以后做挑战时把此开关设为 True 即可。
        self.inflation_enabled = False
        self.last_shop_was_first = False

        # 标签 / 缓冲
        self.blind_tags: dict = {}               # 本底注各盲注的跳过标签 {Small/Big/Boss: 标签键}，reset_blinds 预生成

        # 统计与效果状态（由 effects.py 读写）
        self.hands_count: dict = {}              # 每种手牌类型本局被打出的次数
        self.last_tarot_planet: str | None = None
        self.planets_used: set = set()
        self.constellation_count = 0
        self.tarots_used = 0
        self.lucky_triggers = 0
        self.hologram_count = 0
        self.glass_broken = 0
        self.face_destroyed = 0
        self.card_chip_extra: dict = {}          # id(card) -> 额外筹码（远足者）
        self.hands_played_total = 0
        self.discards_used_round = 0
        self.rerolls_total = 0
        self.pending_consumable: Optional[ConsumableItem] = None
        self.pending_pack: Optional[dict] = None
        self.pending_shop_free_joker: Optional[str] = None
        self.pending_free_voucher = False
        self.investment_tag_active = False
        self.boss_disabled_round = False
        self.mr_bones_used = False

    # ------------------------------------------------------------------
    # 槽位（joker_slots / consumable_slots）
    # 负片编辑（edition=="negative"）不占槽且 +1 槽：当前槽位 = 基础槽位 + 持有负片数。
    # 这样任何加/删负片（买入、灵质、安卡复制、珀可、出售、销毁）都自动保持正确，
    # 无需逐处维护 +=1 / -=1。基础槽位只由 牌组配置 和 优惠券（反物质/水晶球/占卜球）调整。
    # ------------------------------------------------------------------
    @property
    def joker_slots(self) -> int:
        return self._joker_slots + sum(1 for j in self.jokers if j.negative)

    @joker_slots.setter
    def joker_slots(self, v: int):
        self._joker_slots = v

    @property
    def consumable_slots(self) -> int:
        return self._consumable_slots + sum(1 for c in self.consumeables if c.negative)

    @consumable_slots.setter
    def consumable_slots(self, v: int):
        self._consumable_slots = v

    def add_joker_slot(self, n: int = 1):
        self._joker_slots += n

    def add_consumable_slot(self, n: int = 1):
        self._consumable_slots += n

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------
    def say(self, msg: str):
        self.messages.append(msg)

    # ------------------------------------------------------------------
    # 开始一局
    # ------------------------------------------------------------------
    def start_run(self, deck_key: str):
        self.deck_key = deck_key
        cfg = deck_data.DECKS[deck_key]["config"]
        self.deck = build_deck(deck_key, self.rng)
        self.deck.shuffle(self.rng)
        self.hand = []
        self.play = []
        self._round_cards = []
        self._destroyed_ids = set()

        self.dollars = START_PARAMS["dollars"] + cfg.get("dollars", 0)
        self.hands_left = START_PARAMS["hands"] + cfg.get("hands", 0)
        self.discards_left = START_PARAMS["discards"] + cfg.get("discards", 0)
        self.hand_size = START_PARAMS["hand_size"] + cfg.get("hand_size", 0)
        self.hand_size_offset = 0
        self.temp_hand_size = 0
        self.joker_slots = START_PARAMS["joker_slots"] + cfg.get("joker_slot", 0)
        self.consumable_slots = START_PARAMS["consumable_slots"] + cfg.get("consumable_slot", 0)
        self.ante_scaling = cfg.get("ante_scaling", 1)
        self.no_interest = cfg.get("no_interest", False)
        if "money_per_hand" in cfg:
            self.money_per_hand = cfg["money_per_hand"]
        if "money_per_discard" in cfg:
            self.money_per_discard = cfg["money_per_discard"]

        # 牌组自带优惠券
        for vk in [cfg.get("voucher")] if cfg.get("voucher") else []:
            self.redeem_voucher(vk)
        for vk in cfg.get("vouchers", []):
            self.redeem_voucher(vk)
        # 牌组自带消耗牌
        for ck in cfg.get("consumables", []):
            self.gain_consumable(ck)
        # 随机牌组
        if cfg.get("randomize_rank_suit"):
            self._randomize_deck()
        # 棋盘牌组特殊牌堆已在 build_deck 处理

        self.boss_key = self._get_new_boss()
        self.reset_blinds()
        # 对应 game.lua 2178：开局即抽出本底注的优惠券
        self.shop_voucher = self._next_voucher_key()
        self.say(f"开始新的一局（{deck_data.DECKS[deck_key]['cn']}）")

    def _randomize_deck(self):
        base = random.Random(self.seed)
        # 随机化每花色牌数（和 = 52）
        counts = [0, 0, 0, 0]
        for _ in range(52):
            counts[base.randrange(4)] += 1
        cards = []
        uid = 0
        for suit_i, n in enumerate(counts):
            suit = SUITS[suit_i]
            ranks = base.choices(RANKS, k=n)
            for rank in ranks:
                uid += 1
                cards.append(Card(rank=rank, suit=suit, uid=uid))
        self.deck.cards = cards
        self.deck.shuffle(self.rng)

    # ------------------------------------------------------------------
    # 盲注
    # ------------------------------------------------------------------
    def reset_blinds(self):
        self.blind_status = {"Small": "Select", "Big": "Upcoming", "Boss": "Upcoming"}
        self.blind_on_deck = "Small"
        self.blind_key = None
        self.played_this_ante = []
        self.round_hand_played = []
        # 与 Lua 一致（button_callbacks.lua set_blind）：新底注开始时预生成各盲注的
        # 跳过标签，让选择盲注界面能提前展示跳过后会获得哪个标签。
        self.blind_tags = {"Small": self.next_tag_key(), "Big": self.next_tag_key(),
                           "Boss": self.next_tag_key()}

    def _get_new_boss(self) -> str:
        """抽取头目盲注：使用次数最少优先，随机。"""
        candidates = []
        for key, d in blind_data.BOSS_BLINDS.items():
            if d.get("showdown"):
                if self.ante % WIN_ANTE == 0 and self.ante >= 2:
                    candidates.append(key)
            else:
                if self.ante % WIN_ANTE != 0 or self.ante < 2:
                    # 对应 common_events.lua 2353：判定只看 min，max 不参与（数据里的
                    # max 是图鉴/排布用的）——否则无尽模式过了第 10 底注就没有普通头目可选
                    if d["min"] <= self.ante:
                        candidates.append(key)
        if not candidates:
            candidates = [k for k, d in blind_data.BOSS_BLINDS.items() if not d.get("showdown")]
        # 使用次数最少优先
        min_use = min(self.bosses_used.count(c) for c in candidates)
        pool = [c for c in candidates if self.bosses_used.count(c) == min_use]
        return self.rng.choice(pool, "boss")

    def current_blind_key(self) -> str:
        """当前盲注键；``blind_key`` 未定（选盲注阶段）时按 ``blind_on_deck`` 推导。"""
        if self.blind_key:
            return self.blind_key
        return {"Small": "bl_small", "Big": "bl_big",
                "Boss": self.boss_key or "bl_big"}[self.blind_on_deck]

    def current_blind_chips(self) -> int:
        """当前（或待选）盲注的得分门槛。"""
        key = self.current_blind_key()
        if self.boss_disabled():
            # 墙 / 紫瓶的门槛倍率本身就是它的效果。对应 blind.lua Blind:disable：
            # 把 chips 除以倍率（墙 = mult/2，紫瓶 = mult/3），即禁用后按一半/三分之一算。
            cfg = blind_data.get_blind_cfg(key)
            mult = cfg["mult"]
            if key == "bl_wall":
                mult /= 2
            elif key == "bl_final_vessel":
                mult /= 3
            return int(blind_data.get_blind_amount(self.ante, self.ante_scaling) * mult)
        return blind_data.blind_chips(key, self.ante, self.ante_scaling)

    def round_counts(self, blind_key: Optional[str] = None) -> tuple[int, int]:
        """本回合的出牌 / 弃牌次数（含牌组与优惠券加成、头目限制）。

        ``blind_key`` 缺省时按 :meth:`current_blind_key` 推导，因此在 select_blind
        执行之前也能算出即将开始的回合的真实次数（那时字段里还是上一轮的旧值）。
        """
        key = blind_key or self.current_blind_key()
        cfg = deck_data.DECKS[self.deck_key]["config"] if self.deck_key else {}
        hands = max(1, START_PARAMS["hands"] + cfg.get("hands", 0)) + self._voucher_bonus("hands")
        discards = max(0, START_PARAMS["discards"] + cfg.get("discards", 0)) + self._voucher_bonus("discards")
        if self.boss_disabled():
            return hands, discards
        if key == "bl_needle":
            hands = 1
        if key == "bl_water":
            discards = 0
        return hands, discards

    def round_hand_size(self, blind_key: Optional[str] = None) -> int:
        """本回合的手牌上限（含牌组、小丑与优惠券加成、头目限制）。"""
        key = blind_key or self.current_blind_key()
        cfg = deck_data.DECKS[self.deck_key]["config"] if self.deck_key else {}
        n = (START_PARAMS["hand_size"] + cfg.get("hand_size", 0)
             + self._voucher_bonus("hand_size") + self.hand_size_offset + self.temp_hand_size)
        n += joker_hand_size_bonus(self)
        if key == "bl_manacle" and not self.boss_disabled():
            n -= 1
        return max(1, n)

    def change_hand_size(self, delta: int, persistent: bool = True):
        """改变手牌上限：立即作用于本回合，并在计算基准里留下修正。

        ``persistent`` 为真时写入 :attr:`hand_size_offset`（灵应盘/灵质，永久）；
        否则只影响本回合（黑龟豆，每轮累计已记在小丑的 stat 里）。
        """
        self.hand_size = max(1, self.hand_size + delta)
        if persistent:
            self.hand_size_offset += delta

    def blind_cn(self, key: str) -> str:
        return blind_data.get_blind_cfg(key)["cn"]

    def next_tag_key(self) -> Optional[str]:
        """随机抽取一个标签（对应 Lua get_next_tag_key），用于预生成各盲注的跳过标签。"""
        keys = [k for k, d in tag_data.TAGS.items() if d["min_ante"] <= self.ante]
        return self.rng.choice(keys, "tag") if keys else None

    def _next_voucher_key(self) -> Optional[str]:
        """随机抽取本底注的优惠券（对应 Lua get_next_voucher_key）。"""
        return voucher_data.get_next_voucher_key(self.rng, self.used_vouchers)

    def blind_tag_key(self, blind: str) -> Optional[str]:
        """当前底注下，跳过某盲注（Small/Big/Boss）会获得的标签键；由 reset_blinds 预生成。"""
        return self.blind_tags.get(blind)

    def add_tag(self, key: str) -> Tag:
        """获得一个标签（对应 Lua add_tag）。

        每获得一个新标签，收藏里每个「双重标签」都会复制一份新标签并消耗自身
        （tag.lua 的 tag_add 上下文）；双重标签本身不会再被复制。
        """
        tag = Tag(key=key, skips=self.skips)
        self.tags.append(tag)
        self.say(f"获得标签：{tag_data.TAGS[key]['cn']}")
        if key != "tag_double":
            for i in reversed([i for i, t in enumerate(self.tags) if t.key == "tag_double"]):
                self.tags.pop(i)
                self.tags.append(Tag(key=key, skips=self.skips))
                self.say(f"双重标签：复制 {tag_data.TAGS[key]['cn']}")
        return tag

    def skip_blind(self) -> bool:
        """跳过当前盲注。返回 True 表示本底注结束（应进入商店）。"""
        self.skips += 1
        self.boss_disabled_round = False      # 被跳过的盲注不再吃摔跤手的禁用
        self.say("跳过了盲注")
        tag_key = self.blind_tag_key(self.blind_on_deck) or self.next_tag_key()
        if tag_key:
            self.add_tag(tag_key)
        return self._advance_blind()

    def _advance_blind(self) -> bool:
        order = ["Small", "Big", "Boss"]
        idx = order.index(self.blind_on_deck)
        self.blind_status[self.blind_on_deck] = "Skipped"
        if idx < 2:
            self.blind_on_deck = order[idx + 1]
            self.blind_status[self.blind_on_deck] = "Select"
            return False
        # 跳过头目：本底注结束
        self._boss_beaten(skipped=True)
        return True

    def select_blind(self):
        key = {"Small": "bl_small", "Big": "bl_big", "Boss": self.boss_key}[self.blind_on_deck]
        self.blind_key = key
        # 对应 button_callbacks.lua 2533 ease_round(1)：只有迎战盲注才推进回合数，
        # 跳过盲注拿标签不算一个回合。
        self.round += 1
        self.chips = 0
        # 注意：played_this_ante 在整个底注内累积（柱头 boss），在 reset_blinds（新底注）时清空
        self.round_hand_played = []
        self.hands_left, self.discards_left = self.round_counts(key)
        self.reroll_cost_increase = 0
        self.hands_played_round = 0
        self.last_hand_name = None
        self.discards_used_round = 0
        # boss_disabled_round 不在这里清：CLI 的商店在选盲注之前（与原版一致，
        # 商店与盲注选择同屏），在商店里卖掉摔跤手要作用到紧接着迎战的这个盲注，
        # 所以标志由 end_round / skip_blind 在回合结束时清掉。
        self.blind_prepped = False
        self.pending_consumable = None
        # 小丑选盲注触发 + 每轮轮换目标
        on_blind_select(self)
        # 手牌上限：牌组/优惠券/小丑加成 + 头目限制。放在 on_blind_select 之后，
        # 乌合之众当场获得的小丑也算入本回合。
        self.hand_size = self.round_hand_size(key)
        # 头目 debuff：禁用花色/人头牌
        boss_ok = not self.boss_disabled()
        for c in self.hand:
            c.debuffed = False
        if boss_ok:
            self._apply_boss_debuffs()
        self.say(f"迎战盲注：{self.blind_cn(self.blind_key)}（目标 {self.current_blind_chips()} 分）")
        self._draw_to_hand()
        if boss_ok:
            self._apply_boss_debuffs()

    def _apply_boss_debuffs(self):
        """将当前头目盲注的牌面限制应用到现有手牌。

        对应 blind.lua 的 Blind:debuff_card：花色判定走 ``is_suit(suit, bypass_debuff=True)``，
        所以模糊小丑下黑桃/梅花、红心/方块会一起被禁用，百搭牌（算任意花色）也被禁用；
        石头牌无花色不受影响。被禁用的牌仍可打出、仍参与牌型判定，只是不计分。
        """
        dis_suit = {"bl_club": "C", "bl_goad": "S", "bl_head": "H", "bl_window": "D"}.get(self.blind_key)
        smeared = self.any_joker("j_smeared")
        played_ids = {id(c) for c in self.played_this_ante} if self.blind_key == "bl_pillar" else set()
        for c in self.hand:
            if dis_suit and c.is_suit(dis_suit, bypass_debuff=True, smeared=smeared):
                c.debuffed = True
            if self.blind_key == "bl_plant" and c.is_face():
                c.debuffed = True
            if id(c) in played_ids:
                c.debuffed = True

    def _voucher_bonus(self, what: str) -> int:
        n = 0
        if what == "hands":
            for k in self.used_vouchers:
                if k in ("v_grabber",): n += 1
                if k in ("v_nacho_tong",): n += 2
        if what == "discards":
            for k in self.used_vouchers:
                if k in ("v_wasteful",): n += 1
                if k in ("v_recyclomancy",): n += 2
        if what == "hand_size":
            for k in self.used_vouchers:
                if k in ("v_paint_brush",): n += 1
                if k in ("v_palette",): n += 2
        return n

    def _draw_to_hand(self):
        """补牌至手牌上限；蛇头目改为「抽到 3 张」。

        对应 state_events.lua 的 draw_from_deck_to_hand：蛇在已经出过牌或弃过牌后
        把 ``hand_space`` 固定为 3（不是补满手牌）。补牌发生在 play_selected 里
        递增 hands_played_round 之后，所以这里读到的就是「本回合已出过牌」。
        """
        if self._serpent_active():
            need = 3
        else:
            need = self.hand_size - len(self.hand)
        while need > 0 and self.deck.count() > 0:
            c = self.deck.draw_one(self.rng)
            self.hand.append(c)
            if self.boss_disabled():
                c.debuffed = False
            else:
                self._apply_boss_debuffs()
            if self.blind_stays_flipped(c):
                c.face_down = True
            need -= 1
        # 对应 Blind:drawn_to_hand：补牌结束即清除 prepped，只有紧随出牌的那一批牌保持背面
        self.blind_prepped = False
        self.sort_hand()
        if self.deck.count() == 0 and len(self.hand) == 0:
            self.say("牌组已耗尽！")

    def _serpent_active(self) -> bool:
        return (self.blind_key == "bl_serpent" and not self.boss_disabled()
                and (self.hands_played_round > 0 or self.discards_used_round > 0))

    def blind_stays_flipped(self, card: Card) -> bool:
        """刚抽到手牌的牌是否保持背面朝下（对应 blind.lua 的 Blind:stay_flipped）。"""
        if self.boss_disabled():
            return False
        if self.blind_key == "bl_wheel":
            return roll_prob(self, 7, "wheel")
        if self.blind_key == "bl_house" and self.hands_played_round == 0 and self.discards_used_round == 0:
            # 房子：第一手牌（出牌且未弃牌前抽到的牌）背面朝下
            return True
        if self.blind_key == "bl_mark":
            # 记号：所有人头牌（J/Q/K）背面朝下；幻视把全部牌视为人头牌时同样生效
            return is_face_card(card, self)
        if self.blind_key == "bl_fish" and self.blind_prepped:
            return True
        return False

    def _recycle_round_cards(self):
        """回合结束时将手牌与弃牌堆洗回牌组，销毁牌不再回收。"""
        seen = set()
        cards = []
        for card in self.hand + self._round_cards:
            cid = id(card)
            if cid in seen or cid in self._destroyed_ids:
                continue
            seen.add(cid)
            card.selected = False
            card.debuffed = False
            card.face_down = False
            cards.append(card)
        self.deck.cards.extend(cards)
        self.deck.shuffle(self.rng)
        self.hand.clear()
        self._round_cards.clear()
        self.play.clear()

    # ------------------------------------------------------------------
    # 出牌 / 弃牌
    # ------------------------------------------------------------------
    def toggle_select(self, index: int, limit: Optional[int] = MAX_PLAY_SIZE) -> bool:
        """切换选中状态；选中数已达 ``limit`` 时拒绝新增并返回 False。

        ``limit=None`` 表示不限（消耗牌选目标等场景自行判断）。
        """
        if not (0 <= index < len(self.hand)):
            return False
        card = self.hand[index]
        if not getattr(card, "selected", False) and limit is not None \
                and len(self.selected_cards()) >= limit:
            return False
        card.selected = not getattr(card, "selected", False)
        return True

    def sort_hand(self, mode: Optional[str] = None):
        """对手牌排序（仅影响显示顺序，不影响出牌/弃牌/牌型判定）。

        mode:
          "suit" —— 按花色排序（♠ > ♥ > ♣ > ♦），相同花色按点数（A 最大）；
          "rank" —— 按点数排序（A 最大），相同点数按花色（♠ > ♥ > ♣ > ♦）；
        缺省时使用 self.sort_mode；sort_mode 为 None（手动排序）则不自动排序，
        手牌顺序由玩家用 CLI 的 o 命令手动交换。
        已选中的牌会随排序保留选中状态。
        """
        m = mode if mode is not None else self.sort_mode
        if not m:
            return
        suit_order = {s: i for i, s in enumerate(SUITS)}
        if m == "suit":
            self.hand.sort(key=lambda c: (suit_order[c.suit], -c.get_id()))
        elif m == "rank":
            self.hand.sort(key=lambda c: (-c.get_id(), suit_order[c.suit]))

    def selected_cards(self) -> List[Card]:
        return [c for c in self.hand if getattr(c, "selected", False)]

    def play_selected(self) -> List[str]:
        """打出选中牌，返回过程消息。

        盲注规则（眼睛/嘴/通灵者）不再阻止出牌，而是让这一手得 0 分，
        因此这里没有回滚分支：牌一旦打出就离手、出牌次数照扣。
        """
        if not self.can_play() or self.round_over():
            self.say("当前回合已经结束")
            return []
        played = self.selected_cards()
        if not played:
            self.say("请先选择要打出的牌")
            return []
        if len(played) > MAX_PLAY_SIZE:
            self.say(f"一次最多打出 {MAX_PLAY_SIZE} 张牌（当前选了 {len(played)} 张）")
            return []
        for c in played:
            c.selected = False
        for c in played:
            self.hand.remove(c)
        self._round_cards.extend(played)
        self.hands_left -= 1
        self.hands_played_round += 1
        self.hands_played_total += 1
        self.play = played
        # 进入出牌区的牌翻回正面（对应 CardArea:emplace），打出后牌面可见
        for c in played:
            c.face_down = False
        msgs = evaluate_play(self)
        self.play = []
        self.hands_left = max(0, self.hands_left)
        # 鱼：本次出牌后补进手牌的牌保持背面朝下（对应 Blind:press_play 置 prepped）
        if self.blind_key == "bl_fish" and not self.boss_disabled():
            self.blind_prepped = True
        # 盲注触发的回合效果
        self._after_play_blind_effects()
        # 补牌至手牌上限
        self._draw_to_hand()
        # 检查回合结束
        if self.chips >= self.current_blind_chips():
            self.say("已达成盲注目标！")
        return msgs

    def discard_selected(self) -> bool:
        """弃掉选中牌并补牌。返回是否成功。"""
        if self.round_over() or self.blind_key is None:
            self.say("当前回合已经结束")
            return False
        selected = self.selected_cards()
        if not selected:
            self.say("请先选择要弃掉的牌")
            return False
        if len(selected) > MAX_PLAY_SIZE:
            self.say(f"一次最多弃掉 {MAX_PLAY_SIZE} 张牌（当前选了 {len(selected)} 张）")
            return False
        if self.discards_left <= 0:
            self.say("本回合没有剩余弃牌次数")
            return False
        for c in selected:
            c.selected = False
            if c.seal == "purple":
                self._gain_random_tarot()
            self.hand.remove(c)
        self._round_cards.extend(selected)
        self.discards_left -= 1
        self.say(f"弃掉了 {len(selected)} 张牌")
        on_discard(self, selected)
        # 与 Lua 一致：小丑在 discards_used 递增前判定"首次弃牌"（card.lua 2802 / state_events.lua 437）
        self.discards_used_round += 1
        self._draw_to_hand()
        return True

    def _after_play_blind_effects(self):
        if self.boss_disabled():
            return
        b = self.blind_key
        if b == "bl_hook" and len(self.hand) > 0:
            n = min(2, len(self.hand))
            gone = self.rng.sample(self.hand, n)
            for c in gone:
                self.hand.remove(c)
                self._round_cards.append(c)
            self.say(f"钩子：随机弃掉了 {n} 张手牌")
        # 蛇的补牌由 _draw_to_hand 统一处理（对应 draw_from_deck_to_hand 里对蛇的
        # hand_space = 3 覆盖），这里不能再抽一次

    def boss_disabled(self) -> bool:
        """头目盲注效果是否被禁用（奇科特 / 出售摔跤手）。"""
        return self.any_joker("j_chicot") or self.boss_disabled_round

    def disable_current_blind(self) -> bool:
        """当场禁用当前盲注的效果（对应 blind.lua 的 Blind:disable）。

        光置标志不够：选盲注时已经施加过的效果要立刻撤销——牌面 debuff、手牌上限、
        出牌 / 弃牌次数、背面朝下的牌。返回 False 表示本来就没有可禁用的效果。
        """
        if self.boss_disabled():
            return False
        self.boss_disabled_round = True
        # Blind:debuff_card 在 disabled 时把 debuffed 复位；Wheel/House/Mark/Fish 翻回正面
        for c in self.hand + self.play:
            c.debuffed = False
            c.face_down = False
        key = self.current_blind_key()
        if self.blind_key:
            # 已经用掉的次数不回退，只把头目扣掉的那部分补回来（对应 ease_hands_played(hands_sub)
            # / ease_discard(discards_sub)）。此时 round_counts 走的是「已禁用」分支，即未扣减值。
            full_hands, full_discards = self.round_counts(key)
            if key == "bl_needle":
                self.hands_left += full_hands - 1
            if key == "bl_water":
                self.discards_left += full_discards
            if key == "bl_manacle":
                self.change_hand_size(1, persistent=False)
                self._draw_to_hand()      # 原版 G.hand:change_size(1) 后补抽 1 张
        return True

    def notify_destroyed(self, card: Card):
        """牌被销毁时通知（卡尼奥等），并阻止它在回合结束时回收到牌组。"""
        self._destroyed_ids.add(id(card))
        if card.is_face() or card.rank == "A":
            self.face_destroyed += 1

    def can_afford(self, price: int) -> bool:
        if self.dollars >= price:
            return True
        if self.any_joker("j_credit_card"):
            return self.dollars - price >= -20
        return False

    def can_play(self) -> bool:
        return self.hands_left > 0 and len(self.hand) > 0

    # ------------------------------------------------------------------
    # 无尽模式
    # ------------------------------------------------------------------
    def round_label(self) -> str:
        """回合文本（对应 G.GAME.current_round.round_text）：通关后为「无尽回合」。"""
        return f"无尽回合 {self.round}" if self.endless else f"回合 {self.round}"

    def enter_endless(self) -> bool:
        """通关后选择继续 —— 进入无尽模式，没有回合上限。

        对应原版通关窗口的「Endless Mode」按钮（UI_definitions.lua 2785，即关闭
        通关窗口）：第 8 底注的头目被击败即通关，之后底注照常推进、决战头目照常在
        8 的倍数底注出现，通关不再重复宣布，失败只结束无尽模式而不计为失败。
        """
        if not self.run_won or self.endless:
            return False
        self.endless = True
        self.say("进入无尽模式（没有回合上限）")
        self._advance_ante()
        return True

    # ------------------------------------------------------------------
    # 回合结束
    # ------------------------------------------------------------------
    def round_over(self) -> bool:
        """当前回合是否已结束（达成目标或手牌用完且无法继续）。"""
        if self.chips >= self.current_blind_chips():
            return True
        if self.hands_left <= 0:
            return True
        if len(self.hand) == 0 and self.deck.count() == 0:
            return True
        return False

    def end_round(self) -> bool:
        """结算回合。返回 True=胜利推进，False=游戏结束。"""
        completed_blind_key = self.blind_key
        # 通关后若进入无尽模式，回合仍要照常结算
        if completed_blind_key is None or self.run_lost or (self.run_won and not self.endless):
            self.say("当前没有需要结算的回合")
            return False
        won = self.chips >= self.current_blind_chips()
        if not won and self.any_joker("j_mr_bones") and not self.mr_bones_used:
            # 骨头先生：本局第一次失败时救场，目标视为达成并正常推进
            self.mr_bones_used = True
            self.chips = self.current_blind_chips()
            self.say("骨头先生：免除失败！目标达成！")
            won = True
        boss_beaten = False
        if won:
            self.say(f"击败了盲注 {self.blind_cn(self.blind_key)}！")
            if completed_blind_key == self.boss_key:
                boss_beaten = True
                self._boss_beaten()
            else:
                self.blind_status[self.blind_on_deck] = "Won"
                # 推进到下一个盲注
                order = ["Small", "Big", "Boss"]
                idx = order.index(self.blind_on_deck)
                if idx < 2:
                    self.blind_on_deck = order[idx + 1]
                    self.blind_status[self.blind_on_deck] = "Select"
                self.blind_key = None
            self._round_income(boss_beaten=boss_beaten, blind_key=completed_blind_key)
            on_end_round(self, boss_beaten=boss_beaten)
            self.boss_disabled_round = False      # 摔跤手的禁用只作用于本回合
            self._recycle_round_cards()
            # 对应 state_events.lua 270：临时手牌上限（杂耍标签）在回合结算时回退
            self.temp_hand_size = 0
            return True
        self.run_lost = True
        self.say("未能达到盲注目标，" + ("无尽模式结束。" if self.endless else "游戏结束。"))
        self.boss_disabled_round = False
        self.temp_hand_size = 0
        self._recycle_round_cards()
        return False

    def _boss_beaten(self, skipped: bool = False):
        if not skipped:
            self.bosses_used.append(self.boss_key or "")
            # 浮雕牌组：击败头目盲注后获得一个双重标签（back.lua trigger_effect / eval）。
            # 跳过头目不触发（原版在打出手牌结算时触发），故放在 skipped 分支里。
            if self.deck_key == "b_anaglyph":
                self.add_tag("tag_double")
        if self.ante == WIN_ANTE and not self.endless:
            # 通关只宣布一次：此时底注停在第 8 底注，等玩家决定是否进入无尽模式
            self.run_won = True
            self.say(f"你击败了第 {WIN_ANTE} 底注的头目！通关！")
            return
        self._advance_ante()

    def _advance_ante(self):
        self.ante += 1
        self.boss_key = self._get_new_boss()
        self.reset_blinds()
        # 对应 state_events.lua 263：只有头目盲注结束（击败或跳过）触发回合重置时才重新抽券；
        # 小/大盲注结束不刷新，同一底注内的商店展示同一张。
        self.shop_voucher = self._next_voucher_key()
        self.say(f"进入第 {self.ante} 底注")

    def _round_income(self, boss_beaten: bool = False, blind_key: Optional[str] = None):
        """回合收入：盲注奖励 + 剩余手牌/弃牌 + 小丑 + 利息。"""
        key = blind_key or self.blind_key
        if key is None:
            key = {"Small": "bl_small", "Big": "bl_big", "Boss": self.boss_key or "bl_big"}[self.blind_on_deck]
        bcfg = blind_data.get_blind_cfg(key)
        income = 0
        rows = []
        income += bcfg["dollars"]
        rows.append(f"盲注奖励 +${bcfg['dollars']}")
        if boss_beaten and self.investment_tag_active:
            income += 25
            rows.append("投资标签 +$25")
            self.investment_tag_active = False
        if self.hands_left > 0:
            m = self.hands_left * self.money_per_hand
            income += m
            rows.append(f"剩余手牌 {self.hands_left}×${self.money_per_hand} +${m}")
        if self.discards_left > 0 and self.money_per_discard:
            m = self.discards_left * self.money_per_discard
            income += m
            rows.append(f"剩余弃牌 {self.discards_left}×${self.money_per_discard} +${m}")
        # 小丑收入
        for j in self.jokers:
            d = joker_dollar_bonus(self, j)
            if d:
                income += d
                rows.append(f"{joker_cn(j.key)} +${d}")
        # 黄金牌（手中）
        for c in self.hand:
            if c.enhanced == "gold" and not c.debuffed:
                income += 3
                rows.append(f"黄金牌 +$3")
        # 利息
        if not self.no_interest and self.dollars >= 5:
            interest = min(self.dollars // 5, self.interest_cap // 5)
            if interest:
                income += interest
                rows.append(f"利息 +${interest}")
        self.dollars += income
        self.say("  |  ".join(rows))

    # ------------------------------------------------------------------
    # 商店

    # ------------------------------------------------------------------
    # 小丑工具
    # ------------------------------------------------------------------
    def count_jokers(self, *keys: str) -> int:
        return sum(1 for j in self.jokers if j.key in keys)

    def any_joker(self, *keys: str) -> bool:
        return self.count_jokers(*keys) > 0

    def has_voucher(self, *keys: str) -> bool:
        return any(k in self.used_vouchers for k in keys)
