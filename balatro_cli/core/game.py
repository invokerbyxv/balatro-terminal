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
    TAG_IMMEDIATE, TAG_NEW_BLIND, TAG_ROUND_START, apply_tag,
    is_face_card, joker_cn, joker_dollar_bonus, joker_hand_size_bonus,
    on_blind_select, on_discard, on_end_round, on_first_hand_drawn, roll_prob,
)
from .scoring import evaluate_play
from .shop import ShopMixin
from .packs import PackMixin
from .consumables import ConsumableMixin
from ..data import decks as deck_data
from ..data import blinds as blind_data
from ..data import consumables as consumable_data
from ..data import stakes as stake_data
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

#: 开局即可见的牌型（对应 game.lua 2005-2013 的 ``visible``）：
#: 五张同花 / 同花葫芦 / 五条要打出过一次才会出现。
BASE_VISIBLE_HANDS = ("Straight Flush", "Four of a Kind", "Full House", "Flush",
                      "Straight", "Three of a Kind", "Two Pair", "Pair", "High Card")


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
        #: 已销毁的牌（玻璃碎裂 / 吊人 / 献祭等）。存对象本身：销毁后卡片不再被
        #: 任何区域引用，若只存 id 会有 id 复用导致误判的风险。
        self.destroyed_cards: set = set()
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

        # 商店商品出现权重（对应 G.GAME.*_rate，create_card_for_shop 按此加权重抽）
        # 原版默认不出售扑克牌（playing_card_rate = 0）与幻灵牌（spectral_rate = 0）。
        self.joker_rate = 20
        self.tarot_rate = 4
        self.planet_rate = 4
        self.spectral_rate = 0
        self.playing_card_rate = 0
        #: 版本出现倍率（磨砺 2 / 发光升级 4，poll_edition 用）
        self.edition_rate = 1
        #: 卡池标记（对应 G.GAME.pool_flags）：大麦克香蕉灭绝后置位
        self.pool_flags: dict = {}

        # 赌注（难度梯度）：level 越高包含越多修正，见 data/stakes.py
        self.stake = "stake_white"
        self.stake_level = 1
        #: 赌注带来的弃牌次数修正（蓝赌注 -1）
        self.stake_discard_mod = 0
        #: 不给奖励金的盲注名（红赌注：Small）
        self.no_blind_reward: set = set()
        self.enable_eternals_in_shop = False
        self.enable_perishables_in_shop = False
        self.enable_rentals_in_shop = False

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
        #: 本局最后一次打出的牌型（对应 G.GAME.last_hand_played）；蓝封据此选星球牌，
        #: 因此跨回合保留，不在 select_blind 里清空。
        self.last_hand_played: Optional[str] = None
        #: 上一轮头目结算时「打得最多的牌型」（对应 most_played_poker_hand，初始 High Card）。
        #: 牛头目在计分前用它判定，所以必须是上一次头目结束时的快照。
        self.most_played_snapshot: str = "High Card"
        self.round_hand_played: List[str] = []   # 眼睛 boss 用（本回合已打牌型）

        # 商店
        self.shop_jokers: List[JokerItem] = []
        self.shop_boosters: List[BoosterPack] = []
        #: 本底注的优惠券（对应 G.GAME.current_round.voucher）：每个底注只随机抽一次
        #: （开局与击败头目后的回合重置），同一底注内的各商店展示同一张，兑换后清空。
        self.shop_vouchers: List[str] = []
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
        #: 本局累计「未使用的弃牌次数」（对应 G.GAME.unused_discards），
        #: 垃圾标签按它给钱。
        self.unused_discards = 0
        self.rerolls_total = 0
        self.pending_consumable: Optional[ConsumableItem] = None
        self.pending_pack: Optional[dict] = None
        self.pending_shop_free_joker: Optional[str] = None
        #: 优惠券标签：本底注的商店额外多 1 张优惠券
        self.pending_extra_voucher = False
        self.boss_disabled_round = False
        self.boss_rerolled = False
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
    def start_run(self, deck_key: str, stake: str = "stake_white"):
        self.deck_key = deck_key
        cfg = deck_data.DECKS[deck_key]["config"]
        self.deck = build_deck(deck_key, self.rng)
        self.deck.shuffle(self.rng)
        self.hand = []
        self.play = []
        self._round_cards = []
        self.destroyed_cards = set()
        # 同一对象重复开局（重开 / 未来的读档）时，run 级统计必须清零
        self.jokers = []
        self.consumeables = []
        self.tags = []
        self.used_vouchers = set()
        self.hands_count = {}
        self.hands_played_total = 0
        self.hands_played_round = 0
        self.discards_used_round = 0
        self.unused_discards = 0
        self.skips = 0
        self.bosses_used = []
        self.rerolls_total = 0
        self.planets_used = set()
        self.constellation_count = 0
        self.tarots_used = 0
        self.lucky_triggers = 0
        self.hologram_count = 0
        self.glass_broken = 0
        self.face_destroyed = 0
        self.card_chip_extra = {}
        self.last_tarot_planet = None
        self.last_hand_name = None
        self.last_hand_played = None
        self.most_played_snapshot = "High Card"
        self.played_this_ante = []
        self.round_hand_played = []
        self.pending_consumable = None
        self.pending_pack = None
        self.pending_shop_free_joker = None
        self.pending_extra_voucher = False
        self.boss_disabled_round = False
        self.boss_rerolled = False
        self.mr_bones_used = False
        self.ante = 1
        self.round = 0
        self.chips = 0
        self.run_won = False
        self.run_lost = False
        self.endless = False
        self.last_shop_was_first = False
        self.temp_reroll_cost = None
        self.free_reroll_used = False
        self.interest_cap = 25
        self.money_per_hand = 1
        self.money_per_discard = 0
        self.discount_percent = 0
        self.shop_free = False
        self.inflation = 0
        self.shop_jokers = []
        self.shop_boosters = []
        self.shop_offer_vouchers = []
        self.hand_levels = {h: 1 for h in HAND_ORDER}
        self.blind_prepped = False

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
        # 商店权重：牌组可覆盖幻灵出现率（鬼牌组 spectral_rate = 2）
        self.joker_rate = 20
        self.tarot_rate = 4
        self.planet_rate = 4
        self.spectral_rate = cfg.get("spectral_rate", 0)
        self.playing_card_rate = 0
        self.edition_rate = 1
        self.pool_flags = {}
        #: 起始牌组张数（侵蚀按它算缺口，对应 G.GAME.starting_deck_size）
        self.starting_deck_size = len(self.deck.cards)

        # 赌注修正（对应 game.lua 2049-2059；牌组的 ante_scaling 先设，赌注可覆盖）
        self.apply_stake(stake)
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
        self.shop_vouchers = self._roll_vouchers()
        self.say(f"开始新的一局（{deck_data.DECKS[deck_key]['cn']}）")

    def apply_stake(self, stake: str):
        """应用赌注难度修正（对应 game.lua 2049-2059）。

        各档位是叠加的，所以按 level 判断：>=2 小盲无奖励、>=3 增速 2、
        >=4 永恒小丑、>=5 弃牌 -1、>=6 增速 3、>=7 易腐小丑、>=8 租赁小丑。
        """
        self.stake = stake if stake in stake_data.STAKES else "stake_white"
        level = stake_data.stake_level(self.stake)
        self.stake_level = level
        self.no_blind_reward = set()
        self.stake_discard_mod = 0
        self.enable_eternals_in_shop = False
        self.enable_perishables_in_shop = False
        self.enable_rentals_in_shop = False
        if level >= 2:
            self.no_blind_reward.add("Small")
        if level >= 3:
            self.ante_scaling = 2
        if level >= 4:
            self.enable_eternals_in_shop = True
        if level >= 5:
            self.stake_discard_mod = -1
        if level >= 6:
            self.ante_scaling = 3
        if level >= 7:
            self.enable_perishables_in_shop = True
        if level >= 8:
            self.enable_rentals_in_shop = True
        if level > 1:
            self.say(f"赌注：{stake_data.stake_cfg(self.stake)['cn']}"
                     f"（{stake_data.stake_cfg(self.stake)['effect']}）")

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
        # 与 Lua 一致（game.lua 2179-2180）：只为小盲/大盲预生成跳过标签——原版
        # 头目盲注没有「跳过」按钮，因此 Boss 不生成标签。
        self.blind_tags = {"Small": self.next_tag_key(), "Big": self.next_tag_key()}
        #: 本底注是否已经用掉「导演剪辑版」的 1 次头目重掷
        self.boss_rerolled = False

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
        discards = (max(0, START_PARAMS["discards"] + cfg.get("discards", 0))
                    + self._voucher_bonus("discards") + self.stake_discard_mod)
        hands = max(1, hands)
        discards = max(0, discards)
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

    def _roll_vouchers(self) -> List[str]:
        """本底注出现的优惠券列表（默认 1 张；「优惠券标签」在商店里再额外加 1 张）。"""
        key = self._next_voucher_key()
        return [key] if key else []

    # ---- 头目重掷（导演剪辑版 / 回溯）----
    def boss_can_reroll(self) -> bool:
        """是否还能重掷头目盲注（导演剪辑版每底注 1 次，回溯无限制）。"""
        if self.has_voucher("v_retcon"):
            return True
        return self.has_voucher("v_directors_cut") and not self.boss_rerolled

    def boss_reroll_cost(self) -> int:
        return 10

    def reroll_boss(self, free: bool = False) -> bool:
        """花 $10 重掷头目盲注（对应 G.FUNCS.reroll_boss，button_callbacks 2800）。"""
        if not free:
            if not self.boss_can_reroll():
                self.say("没有可用的头目重掷（需要导演剪辑版 / 回溯）")
                return False
            if not self.can_afford(self.boss_reroll_cost()):
                self.say("金钱不足")
                return False
            self.dollars -= self.boss_reroll_cost()
        self.boss_rerolled = True
        self.boss_key = self._get_new_boss()
        self.say(f"重掷头目盲注：{self.blind_cn(self.boss_key)}")
        return True

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
        """跳过当前盲注。返回 True 表示本底注结束（应进入商店）。

        原版头目盲注没有跳过按钮（``blind_tags`` 只预生成 Small/Big），这里同样
        拒绝——否则可以直接跳过 Boss 破坏整条进度。

        标签在**跳过的当下**结算：先全部 ``immediate``（给钱 / 加等级 / 给随机
        小丑），再结算第一个 ``new_blind_choice``（开卡包 / 重掷头目），对应
        button_callbacks.lua 2772-2777 的顺序。
        """
        if self.blind_on_deck == "Boss":
            self.say("头目盲注不能跳过")
            return False
        self.skips += 1
        self.boss_disabled_round = False      # 被跳过的盲注不再吃摔跤手的禁用
        self.say("跳过了盲注")
        tag_key = self.blind_tag_key(self.blind_on_deck) or self.next_tag_key()
        if tag_key:
            self.add_tag(tag_key)
        done = self._advance_blind()
        self._apply_tags(TAG_IMMEDIATE)
        self._apply_tags(TAG_NEW_BLIND, stop_on_first=True)
        return done

    def _apply_tags(self, context: str, stop_on_first: bool = False) -> int:
        """按阶段结算收藏里的标签（对应 tag.lua 的 ``apply_to_run``）。

        触发过的标签由 :func:`effects.apply_tag` 从 :attr:`tags` 里移除；
        未到该阶段的标签原样留在收藏里等下一次机会。返回触发了几个。
        """
        applied = 0
        for tag in list(self.tags):
            if not any(t is tag for t in self.tags):
                continue
            if apply_tag(self, tag, context):
                applied += 1
                if stop_on_first:
                    break
        return applied

    def visible_hands(self) -> List[str]:
        """可见的牌型列表（对应 ``G.GAME.hands[...].visible``）。

        五张同花 / 同花葫芦 / 五条要打出来才解锁，其余开局即见；轨道标签据此
        选牌型升级。
        """
        return [h for h in HAND_ORDER
                if h in BASE_VISIBLE_HANDS or self.hands_count.get(h, 0) > 0]

    def most_played_hand(self) -> Optional[str]:
        """本局打得最多的可见牌型（对应 G.GAME.current_round.most_played_poker_hand）。

        原版遍历 ``G.handlist`` 用「严格大于」比较，因此并列时取顺序靠前者；
        这里用 :data:`HAND_ORDER`（与原版手牌顺序一致）实现同样的取舍。
        """
        best, best_n = None, 0
        for h in self.visible_hands():
            n = self.hands_count.get(h, 0)
            if n > best_n:
                best, best_n = h, n
        return best

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
        # 新盲注从小丑正面朝上开始，再施加这个头目的一次性效果。对应 blind.lua：
        # set_blind 里的头目效果先于小丑的 setting_blind 触发，所以乌合之众当场
        # 拿到的小丑保持正面，也不参与这次洗乱。
        self._unflip_jokers()
        if key == "bl_final_acorn" and not self.boss_disabled():
            self._flip_and_shuffle_jokers()
        # 小丑选盲注触发 + 每轮轮换目标
        on_blind_select(self)
        # 杂耍标签等 round_start_bonus：在本回合抽牌前修改手牌上限（原版在
        # DRAW_TO_HAND 状态里结算，见 game.lua 3214-3216）
        self._apply_tags(TAG_ROUND_START)
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
        # 希科：选盲注时禁用头目效果（card.lua 2491-2502）；之后卖掉不会恢复
        if self.any_joker("j_chicot") and not self.boss_disabled_round:
            self.disable_current_blind()
            self.say("希科：已禁用本盲注的头目效果")
        # 首次抽牌后触发 first_hand_drawn（证书加牌，card.lua 2462-2482 / state_events 3226）
        on_first_hand_drawn(self)

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
            if self.blind_key == "bl_plant" and is_face_card(c, self, from_boss=True):
                c.debuffed = True
            if id(c) in played_ids:
                c.debuffed = True
            # 绿叶：直到卖掉一张小丑之前，所有牌都被禁用（blind.lua 650）
            if self.blind_key == "bl_final_leaf":
                c.debuffed = True

    def _flip_and_shuffle_jokers(self):
        """琥珀橡果：翻转并洗乱所有小丑牌（blind.lua 190-205）。

        翻转只影响显示（被翻转的小丑照常计分），洗乱则实打实地改变顺序——小丑的
        先后决定计分顺序。原版连洗三次只是动画，这里按需求随机打乱一次。
        """
        if not self.jokers:
            return
        for j in self.jokers:
            j.face_down = True
        if len(self.jokers) > 1:
            self.rng.shuffle(self.jokers)
        self.say("琥珀橡果：翻转并洗乱了所有小丑牌")

    def _unflip_jokers(self):
        """把小丑翻回正面（blind.lua 的 Blind:defeat / Blind:disable）。"""
        for j in self.jokers:
            j.face_down = False

    def _voucher_bonus(self, what: str) -> int:
        """优惠券对每回合出牌 / 弃牌 / 手牌上限的累计修正。

        抓取者与纳乔舌各 +1（总 +2），浪费者与回收术各 +1（总 +2），
        画笔与调色板各 +1（总 +2）；象形文字额外 -1 出牌、岩画额外 -1 弃牌。
        """
        hands = discards = hand_size = 0
        for k in self.used_vouchers:
            if k == "v_grabber":
                hands += 1
            elif k == "v_nacho_tong":
                hands += 1
            elif k == "v_hieroglyph":
                hands -= 1
            elif k == "v_wasteful":
                discards += 1
            elif k == "v_recyclomancy":
                discards += 1
            elif k == "v_petroglyph":
                discards -= 1
            elif k == "v_paint_brush":
                hand_size += 1
            elif k == "v_palette":
                hand_size += 1
        return {"hands": hands, "discards": discards, "hand_size": hand_size}.get(what, 0)

    def all_playing_cards(self) -> List[Card]:
        """全牌组：抽牌堆 + 手牌 + 本回合已打出/弃掉待回收的牌。

        对应原版的 ``G.playing_cards``——它包含所有还在牌局里的牌（含出牌区与
        弃牌堆），「全牌组统计」类小丑（石头/钢铁/驾驶执照/侵蚀/九霄云外）与
        增强牌门控都按它计数。已销毁的牌不在任何区域里，自然不会计入。
        """
        out: List[Card] = []
        seen = set()
        for area in (self.deck.cards, self.hand, self._round_cards, self.play):
            for c in area:
                if c in seen:
                    continue
                seen.add(c)
                out.append(c)
        return out

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
        self._after_drawn_to_hand()
        self.blind_prepped = False
        self.sort_hand()
        if self.deck.count() == 0 and len(self.hand) == 0:
            self.say("牌组已耗尽！")

    def _after_drawn_to_hand(self):
        """补牌结束后的头目效果（对应 blind.lua 的 Blind:drawn_to_hand）。"""
        if self.boss_disabled():
            for c in self.hand:
                c.forced_selection = False
            return
        if self.blind_key == "bl_final_bell":
            self._apply_forced_selection()
        if self.blind_key == "bl_final_heart" and self.blind_prepped:
            self._apply_crimson_heart()

    def _apply_forced_selection(self):
        """青钟：手牌里始终有一张被强制选中（blind.lua 574-587）。"""
        if any(c.forced_selection for c in self.hand):
            return
        if not self.hand:
            return
        for c in self.hand:
            c.selected = False
        card = self.rng.choice(self.hand, "cerulean_bell")
        card.forced_selection = True
        card.selected = True

    def _apply_crimson_heart(self):
        """深红之心：每打出一手后随机禁用 1 张小丑（blind.lua 588-600）。

        候选是「此刻未被禁用的小丑」（只有 1 张时就是它自己），先把所有小丑的
        禁用状态清空，再随机禁掉其中一个——因此每手只会有一张被禁用。
        """
        if not self.jokers:
            return
        pool = [j for j in self.jokers if not j.debuffed]
        if len(self.jokers) < 2 or not pool:
            pool = list(self.jokers)
        for j in self.jokers:
            j.debuffed = False
        victim = self.rng.choice(pool, "crimson_heart")
        victim.debuffed = True
        self.say(f"深红之心：{joker_cn(victim.key)} 被禁用")

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
            # 记号：所有人头牌（J/Q/K）背面朝下；幻视把全部牌视为人头牌时同样生效。
            # 原版用 card:is_face(true)（绕过 debuff）判断。
            return is_face_card(card, self, from_boss=True)
        if self.blind_key == "bl_fish" and self.blind_prepped:
            return True
        return False

    def _recycle_round_cards(self):
        """回合结束时将手牌与弃牌堆洗回牌组，销毁牌不再回收。"""
        seen = set()
        cards = []
        for card in self.hand + self._round_cards:
            if card in seen or card in self.destroyed_cards:
                continue
            seen.add(card)
            card.selected = False
            card.forced_selection = False
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
        # 青钟：被强制选中的牌无法取消（原版 forced_selection 会禁用取消选中）
        if card.forced_selection and card.selected:
            self.say("青钟：这张牌被强制选中，无法取消")
            return False
        if not card.selected and limit is not None \
                and len(self.selected_cards()) >= limit:
            return False
        card.selected = not card.selected
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
        return [c for c in self.hand if c.selected]

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
        # 出牌瞬间的盲注效果（钩子弃牌）先于记分，与原版 press_play 的顺序一致
        self._press_play()
        msgs = evaluate_play(self)
        self.play = []
        self.hands_left = max(0, self.hands_left)
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
            self.hand.remove(c)
        self._round_cards.extend(selected)
        self.say(f"弃掉了 {len(selected)} 张牌")
        self._discard_context(selected)
        self._draw_to_hand()
        return True

    def _discard_context(self, cards: List[Card], consume_discard: bool = True):
        """走完整的「弃牌」上下文（对应 discard_cards_from_highlighted 的主体）。

        - 紫封（对应 ``Card:calculate_seal{discard=true}``）：消耗品栏有空位时
          每张紫封生成 1 张塔罗；
        - 弃牌系小丑（约里克 / 上路吧杰克 / 拉面 / 邮件回扣 / 城堡 / 交易卡…）。

        钩子盲注的强制弃牌也走这里，但不扣弃牌次数（Lua 里 hook 分支跳过
        ``ease_discard`` 与 ``discards_used`` 自增）。
        """
        for c in cards:
            if c.seal == "purple":
                self._gain_random_tarot()
        # 与 Lua 一致：小丑在 discards_used 递增前判定首次弃牌（card.lua 2802）
        on_discard(self, cards)
        if consume_discard:
            self.discards_left -= 1
            self.discards_used_round += 1

    def _press_play(self):
        """出牌瞬间的盲注效果（对应 blind.lua 的 Blind:press_play）。

        先于记分执行：钩子在牌离手之后、结算之前随机弃掉 2 张手牌，因此这 2 张
        不参与本手记分，并触发完整弃牌上下文；鱼在此刻置 prepped，让随后的补牌
        保持背面朝下。蛇的补牌由 _draw_to_hand 统一处理（对应 draw_from_deck_to_hand
        里对蛇的 hand_space = 3 覆盖），这里不能再抽一次。
        """
        if self.boss_disabled():
            return
        if self.blind_key == "bl_hook" and len(self.hand) > 0:
            n = min(2, len(self.hand))
            gone = self.rng.sample(self.hand, n)
            for c in gone:
                self.hand.remove(c)
            self._round_cards.extend(gone)
            self._discard_context(gone, consume_discard=False)
            self.say(f"钩子：随机弃掉了 {n} 张手牌")
        if self.blind_key == "bl_fish":
            self.blind_prepped = True
        # 深红之心：本次出牌后、补牌时随机禁用 1 张小丑（blind.lua 488-493）
        if self.blind_key == "bl_final_heart" and self.jokers:
            self.blind_prepped = True

    def boss_disabled(self) -> bool:
        """头目盲注效果是否被禁用（奇科特 / 摔跤手 / 绿叶卖牌）。

        用标志位而不是「当前是否持有奇科特」实时判定：原版在**选盲注时**就调用
        ``Blind:disable``（card.lua 2491-2502），之后卖掉奇科特也不会让头目效果
        中途恢复。
        """
        return self.boss_disabled_round

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
        # 琥珀橡果翻转的小丑也翻回正面（Blind:disable 的同名分支）
        self._unflip_jokers()
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

    def notify_destroyed(self, card: Card, shattered: bool = False):
        """牌被销毁（对应 Lua 的 ``start_dissolve`` / ``shatter``）。

        - 记入 :attr:`destroyed_cards`，回合结束时不再回收到牌组；这里保存
          **对象本身**而不是 ``id(card)``：销毁后卡片可能已被移出所有区域，
          若只存 id，对象被回收后新牌可能复用同一 id 而被误判为已销毁。
        - 从手牌 / 出牌区 / 待回收区 / 牌组里移除，避免「碎而不消失」；
        - ``shattered=True``（玻璃牌碎裂）累计玻璃小丑，人头牌累计卡尼奥。
        """
        self.destroyed_cards.add(card)
        for area in (self.hand, self.play, self._round_cards, self.deck.cards):
            try:
                area.remove(card)
            except ValueError:
                pass
        if shattered and card.enhanced == "glass" and not card.debuffed:
            self.glass_broken += 1
        if is_face_card(card, self):
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
        if not won:
            # 骨头先生：失败时若已达目标 25% 则免除失败，并销毁自身
            # （card.lua 3047-3063 的 context.game_over 分支）
            target = self.current_blind_chips()
            bones = next((x for x in self.jokers
                          if x.key == "j_mr_bones" and not x.debuffed), None)
            if bones is not None and target and self.chips / target >= 0.25:
                self.jokers.remove(bones)
                self.chips = target
                self.say("骨头先生：免除失败！目标视为达成（自身已销毁）")
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
            self._unflip_jokers()                 # 琥珀橡果：头目被击败，小丑翻回正面
            # 顺序与原版一致：end_of_round 小丑（火箭 +$2 等）与租金/易腐 →
            # 手牌自身效果（黄金牌入账、蓝封生成星球）→ 结算收入与利息
            on_end_round(self, boss_beaten=boss_beaten)
            self._end_of_round_hand_effects()
            self._round_income(boss_beaten=boss_beaten, blind_key=completed_blind_key)
            # 本局累计未使用的弃牌（垃圾标签用），对应 state_events.lua 124
            self.unused_discards += self.discards_left
            self.boss_disabled_round = False      # 摔跤手的禁用只作用于本回合
            self._recycle_round_cards()
            # 对应 state_events.lua 270：临时手牌上限（杂耍标签）在回合结算时回退
            self.temp_hand_size = 0
            return True
        self.run_lost = True
        self.say("未能达到盲注目标，" + ("无尽模式结束。" if self.endless else "游戏结束。"))
        self.boss_disabled_round = False
        self.temp_hand_size = 0
        self._unflip_jokers()
        self._recycle_round_cards()
        return False

    def _boss_beaten(self, skipped: bool = False):
        if not skipped:
            self.bosses_used.append(self.boss_key or "")
            # 对应 state_events.lua 129-138：击败头目时刷新 most_played_poker_hand
            self.most_played_snapshot = self.most_played_hand() or "High Card"
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
        self.shop_vouchers = self._roll_vouchers()
        self.say(f"进入第 {self.ante} 底注")

    def _end_of_round_hand_effects(self):
        """回合结束时手牌自身的效果（对应 state_events.lua 171-233）。

        - 黄金牌：每张 +$3，直接进 ``dollars``——因此会抬高随后的利息；
        - 蓝封：消耗品栏有空位时，生成「本局最后一次打出的牌型」对应的星球牌。
        """
        last = self.last_hand_played
        for c in list(self.hand):
            if c.debuffed:
                continue
            if c.enhanced == "gold":
                self.dollars += 3
                self.say("黄金牌 +$3")
            if c.seal == "blue" and last:
                planet = consumable_data.planet_for_hand(last)
                if planet is None:
                    continue
                if len(self.consumeables) < self.consumable_slots:
                    self.gain_consumable(planet)
                    self.say(f"蓝封：生成 {consumable_data.get_consumable_cn(planet)}")
                else:
                    self.say("蓝封：消耗品栏已满，未生成星球牌")

    def _round_income(self, boss_beaten: bool = False, blind_key: Optional[str] = None):
        """回合收入：盲注奖励 + 剩余手牌/弃牌 + 小丑 + 利息。"""
        key = blind_key or self.blind_key
        if key is None:
            key = {"Small": "bl_small", "Big": "bl_big", "Boss": self.boss_key or "bl_big"}[self.blind_on_deck]
        bcfg = blind_data.get_blind_cfg(key)
        income = 0
        rows = []
        blind_kind = {"bl_small": "Small", "bl_big": "Big"}.get(key, "Boss")
        if blind_kind in self.no_blind_reward:
            rows.append("盲注奖励 $0（赌注）")
        else:
            income += bcfg["dollars"]
            rows.append(f"盲注奖励 +${bcfg['dollars']}")
        if boss_beaten:
            gain = self._tag_eval_income()
            if gain:
                income += gain
                rows.append(f"投资标签 +${gain}")
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
        # 利息：按当前 dollars 计算（黄金牌已在 _end_of_round_hand_effects 里入账），
        # 并且本金在上面的收入入账之前——与 state_events.lua 1191 一致。
        # 冲向月球每张把利息倍率 +1，仍受利息上限约束（card.lua 613-615）。
        if not self.no_interest and self.dollars >= 5:
            amount = 1 + self.count_jokers("j_to_the_moon")
            interest = amount * min(self.dollars // 5, self.interest_cap // 5)
            if interest:
                income += interest
                rows.append(f"利息 +${interest}")
        self.dollars += income
        self.say("  |  ".join(rows))

    def _tag_eval_income(self) -> int:
        """结算 eval 阶段的标签收入（投资标签：击败头目 +$25）。

        对应 state_events.lua 1183-1189：标签收入计入回合结算的 dollars 变量，
        而不是先加进 G.GAME.dollars——因此不会抬高随后的利息。
        """
        gain = 0
        for tag in list(self.tags):
            if tag.key != "tag_investment":
                continue
            gain += 25
            for i, t in enumerate(self.tags):
                if t is tag:
                    self.tags.pop(i)
                    break
        return gain

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
