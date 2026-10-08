"""游戏主状态机：一局完整流程、回合、经济、商店、盲注调度。

对应 Lua game.lua + functions/* 的状态机。纯逻辑，不含 I/O。
"""
import random
from typing import List, Optional

from .card import Card, SUITS
from .deck import Deck, build_deck
from .rng import RNG
from .items import JokerItem, ConsumableItem, BoosterPack, Tag
from ..data import decks as deck_data
from ..data import blinds as blind_data
from ..data import tags as tag_data
from ..data import boosters as booster_data
from ..data import consumables as consumable_data
from ..data import vouchers as voucher_data

# 起始参数（misc_functions.lua get_starting_params）
START_PARAMS = {
    "dollars": 4, "hand_size": 8, "discards": 3, "hands": 4,
    "reroll_cost": 5, "joker_slots": 5, "consumable_slots": 2,
    "ante_scaling": 1,
}

WIN_ANTE = 8


class Game:
    def __init__(self, seed: Optional[int] = None):
        import os
        self.seed = seed if seed is not None else (os.urandom(4)[0] | (os.urandom(4)[0] << 8))
        self.rng = RNG(self.seed)
        self.log: List[str] = []
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
        self.free_rerolls = 0
        self.shop_joker_max = 2

        # 进度
        self.ante = 1
        self.chips = 0
        self.run_won = False
        self.run_lost = False
        self.blind_key: Optional[str] = None       # 当前迎战的盲注
        self.blind_status = {"Small": "Select", "Big": "Upcoming", "Boss": "Upcoming"}
        self.blind_on_deck = "Small"
        self.boss_key: Optional[str] = None
        self.skips = 0
        self.bosses_used: List[str] = []

        # 手牌等级
        from .hand_eval import HAND_ORDER
        self.hand_levels = {h: 1 for h in HAND_ORDER}
        self.played_this_ante: List[Card] = []   # 柱 boss 用
        self.hands_played_round = 0
        self.last_hand_name: Optional[str] = None
        self.round_hand_played: List[str] = []   # 眼睛 boss 用（本回合已打牌型）

        # 商店
        self.shop_jokers: List[JokerItem] = []
        self.shop_boosters: List[BoosterPack] = []
        self.shop_voucher: Optional[str] = None
        self.used_vouchers: set = set()
        self.inflation = 0
        # 通货膨胀挑战（原版 c_inflation_1）才启用：每购买一件商品，商店价格 +1。
        # CLI 暂未实现挑战系统，默认关闭；以后做挑战时把此开关设为 True 即可。
        self.inflation_enabled = False
        self.last_shop_was_first = False

        # 标签 / 缓冲
        self.pending_tags: List[Tag] = []        # 跳过盲注获得的标签，进商店时应用
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
        self.shop_voucher_override: Optional[str] = None
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
        self.say(f"开始新的一局（{deck_data.DECKS[deck_key]['cn']}）")

    def _randomize_deck(self):
        from .card import RANKS, SUITS
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
        from ..data.blinds import BOSS_BLINDS
        candidates = []
        for key, d in BOSS_BLINDS.items():
            if d.get("showdown"):
                if self.ante % WIN_ANTE == 0 and self.ante >= 2:
                    candidates.append(key)
            else:
                if self.ante % WIN_ANTE != 0 or self.ante < 2:
                    if d["min"] <= self.ante <= d["max"]:
                        candidates.append(key)
        if not candidates:
            candidates = [k for k, d in BOSS_BLINDS.items() if not d.get("showdown")]
        # 使用次数最少优先
        min_use = min(self.bosses_used.count(c) for c in candidates)
        pool = [c for c in candidates if self.bosses_used.count(c) == min_use]
        return self.rng.choice(pool, "boss")

    def blind_list(self) -> List[str]:
        """当前底注的盲注顺序（小/大/头目）。"""
        return ["bl_small", "bl_big", self.boss_key or "bl_big"]

    def current_blind_key(self) -> str:
        """当前盲注键；``blind_key`` 未定（选盲注阶段）时按 ``blind_on_deck`` 推导。"""
        if self.blind_key:
            return self.blind_key
        return {"Small": "bl_small", "Big": "bl_big",
                "Boss": self.boss_key or "bl_big"}[self.blind_on_deck]

    def current_blind_chips(self) -> int:
        """当前（或待选）盲注的得分门槛。"""
        return blind_data.blind_chips(self.current_blind_key(), self.ante, self.ante_scaling)

    def round_counts(self, blind_key: Optional[str] = None) -> tuple[int, int]:
        """本回合的出牌 / 弃牌次数（含牌组与优惠券加成、头目限制）。

        ``blind_key`` 缺省时按 :meth:`current_blind_key` 推导，因此在 select_blind
        执行之前也能算出即将开始的回合的真实次数（那时字段里还是上一轮的旧值）。
        """
        key = blind_key or self.current_blind_key()
        cfg = deck_data.DECKS[self.deck_key]["config"] if self.deck_key else {}
        hands = max(1, START_PARAMS["hands"] + cfg.get("hands", 0)) + self._voucher_bonus("hands")
        discards = max(0, START_PARAMS["discards"] + cfg.get("discards", 0)) + self._voucher_bonus("discards")
        if key == "bl_needle":
            hands = 1
        if key == "bl_water":
            discards = 0
        return hands, discards

    def round_hand_size(self, blind_key: Optional[str] = None) -> int:
        """本回合的手牌上限（含牌组与优惠券加成、头目限制）。"""
        key = blind_key or self.current_blind_key()
        cfg = deck_data.DECKS[self.deck_key]["config"] if self.deck_key else {}
        n = START_PARAMS["hand_size"] + cfg.get("hand_size", 0) + self._voucher_bonus("hand_size")
        if key == "bl_manacle":
            n = max(1, n - 1)
        return n

    def blind_cn(self, key: str) -> str:
        return blind_data.get_blind_cfg(key)["cn"]

    def next_tag_key(self) -> Optional[str]:
        """随机抽取一个标签（对应 Lua get_next_tag_key），用于预生成各盲注的跳过标签。"""
        keys = [k for k, d in tag_data.TAGS.items() if d["min_ante"] <= self.ante]
        return self.rng.choice(keys, "tag") if keys else None

    def blind_tag_key(self, blind: str) -> Optional[str]:
        """当前底注下，跳过某盲注（Small/Big/Boss）会获得的标签键；由 reset_blinds 预生成。"""
        return self.blind_tags.get(blind)

    def skip_blind(self) -> bool:
        """跳过当前盲注。返回 True 表示本底注结束（应进入商店）。"""
        self.skips += 1
        tag_key = self.blind_tag_key(self.blind_on_deck) or self.next_tag_key()
        if tag_key:
            self.tags.append(Tag(key=tag_key, skips=self.skips))
            self.say(f"跳过了盲注，获得标签：{tag_data.TAGS[tag_key]['cn']}")
            # 双重标签（tag.lua tag_add）：复制刚获得的非双重标签，并消耗自身
            if tag_key != "tag_double" and any(t.key == "tag_double" for t in self.tags[:-1]):
                self.tags.append(Tag(key=tag_key, skips=self.skips))
                self.tags = [t for t in self.tags if t.key != "tag_double"]
                self.say(f"双重标签：复制 {tag_data.TAGS[tag_key]['cn']}")
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
        self.chips = 0
        # 注意：played_this_ante 在整个底注内累积（柱头 boss），在 reset_blinds（新底注）时清空
        self.round_hand_played = []
        self.hands_left, self.discards_left = self.round_counts(key)
        self.hand_size = self.round_hand_size(key)
        self.reroll_cost_increase = 0
        self.hands_played_round = 0
        self.last_hand_name = None
        self.discards_used_round = 0
        self.boss_disabled_round = False
        self.pending_consumable = None
        # 小丑选盲注触发 + 每轮轮换目标
        from .effects import on_blind_select
        on_blind_select(self)
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
        """将当前头目盲注的牌面限制应用到现有手牌。"""
        dis_suit = {"bl_club": "C", "bl_goad": "S", "bl_head": "H", "bl_window": "D"}.get(self.blind_key)
        played_ids = {id(c) for c in self.played_this_ante} if self.blind_key == "bl_pillar" else set()
        for c in self.hand:
            if dis_suit and c.suit == dis_suit:
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
        need = self.hand_size - len(self.hand)
        while need > 0 and self.deck.count() > 0:
            c = self.deck.draw_one(self.rng)
            self.hand.append(c)
            if self.boss_disabled():
                c.debuffed = False
            else:
                self._apply_boss_debuffs()
            # 轮子 boss：1/7 概率背面朝上（显示隐藏）
            need -= 1
        self.sort_hand()
        if self.deck.count() == 0 and len(self.hand) == 0:
            self.say("牌组已耗尽！")

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
            cards.append(card)
        self.deck.cards.extend(cards)
        self.deck.shuffle(self.rng)
        self.hand.clear()
        self._round_cards.clear()
        self.play.clear()

    # ------------------------------------------------------------------
    # 出牌 / 弃牌
    # ------------------------------------------------------------------
    def toggle_select(self, index: int):
        if 0 <= index < len(self.hand):
            self.hand[index].selected = not getattr(self.hand[index], "selected", False)

    def clear_selection(self):
        for c in self.hand:
            c.selected = False

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
        from .scoring import evaluate_play
        if not self.can_play() or self.round_over():
            self.say("当前回合已经结束")
            return []
        played = self.selected_cards()
        if not played:
            self.say("请先选择要打出的牌")
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
        msgs = evaluate_play(self)
        self.play = []
        self.hands_left = max(0, self.hands_left)
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
        from .effects import on_discard
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
        if b == "bl_serpent":
            self._draw_to_hand()

    def boss_disabled(self) -> bool:
        """头目盲注效果是否被禁用（奇科特 / 出售摔跤手）。"""
        return self.any_joker("j_chicot") or self.boss_disabled_round

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
        if completed_blind_key is None or self.run_won or self.run_lost:
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
            from .effects import on_end_round
            on_end_round(self, boss_beaten=boss_beaten)
            self._recycle_round_cards()
            return True
        self.run_lost = True
        self.say("未能达到盲注目标，游戏结束。")
        self._recycle_round_cards()
        return False

    def _boss_beaten(self, skipped: bool = False):
        if self.ante == WIN_ANTE:
            self.run_won = True
            self.say("你击败了第 8 底注的头目！通关！")
            return
        if not skipped:
            self.bosses_used.append(self.boss_key or "")
        self.ante += 1
        self.boss_key = self._get_new_boss()
        self.reset_blinds()
        # 通关 Boss 后刷新优惠券
        nk = voucher_data.get_next_voucher(self.used_vouchers)
        if nk:
            self.shop_voucher_override = nk
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
        self.round_income_total = income

    # ------------------------------------------------------------------
    # 商店
    # ------------------------------------------------------------------
    def enter_shop(self):
        self.shop_jokers = []
        self.shop_boosters = []
        self.shop_voucher = None
        self.shop_free = False
        # 应用标签（版本类标签由 _make_joker_for_shop 在生成商品时消费）
        for tag in list(self.tags):
            self._apply_tag(tag)
        # 生成商品
        self._generate_shop()
        if self.shop_voucher is None:
            self.pending_free_voucher = False
        self.say("进入商店")

    def _generate_shop(self):
        from ..data import centers as centers_data
        # 【商品】默认两个：随机小丑 / 塔罗 / 星球 / 增强卡牌
        joker_max = self.shop_joker_max
        free_joker_rarity = self.pending_shop_free_joker
        self.pending_shop_free_joker = None
        for i in range(joker_max):
            if i == 0 and free_joker_rarity:
                rarity = {"uncommon": 2, "rare": 3}[free_joker_rarity]
                key = centers_data.random_joker_key(self, rarity=rarity)
                j = self._make_joker_for_shop(key)
                j.buy_cost = 0
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
        # 【优惠券】默认一张
        nk = self.shop_voucher_override or voucher_data.get_next_voucher(self.used_vouchers)
        self.shop_voucher_override = None
        if nk:
            self.shop_voucher = nk

    def _make_joker_for_shop(self, key: str):
        from ..data import centers as centers_data
        cfg = centers_data.joker_cfg(key)
        j = JokerItem(key=key)
        j.buy_cost = centers_data.joker_price(key, self.dollars)
        j.sell_price = max(1, cfg.get("cost", 1) // 2)
        # 标签应用版本（tag.lua store_joker_modify）：首个商店小丑获得版本后标签即被消费
        for tag in list(self.tags):
            if tag.key in ("tag_foil", "tag_holo", "tag_polychrome", "tag_negative"):
                if j.edition is None:
                    j.edition = {"tag_foil": "foil", "tag_holo": "holo",
                                 "tag_polychrome": "poly", "tag_negative": "negative"}[tag.key]
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
        from ..data import centers as centers_data
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
        from .card import RANKS, SUITS, ENHANCED
        c = Card(rank=self.rng.choice(RANKS), suit=self.rng.choice(SUITS), uid=0)
        c.enhanced = self.rng.choice(ENHANCED)
        if self.rng.chance(20, "std_ed"):
            c.edition = self.rng.choice(["foil", "holo", "poly"])
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
        self.shop_voucher = None
        self.pending_free_voucher = False
        self.redeem_voucher(vk)
        return True

    def redeem_voucher(self, vk: str):
        from ..data import centers as centers_data
        if vk in self.used_vouchers:
            return
        self.used_vouchers.add(vk)
        centers_data.apply_voucher(self, vk)
        self.say(f"启用优惠券：{voucher_data.VOUCHERS[vk]['cn']}")

    # ------------------------------------------------------------------
    # 卡包
    # ------------------------------------------------------------------
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
        from ..data import centers as centers_data
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
        from .card import RANKS, SUITS, ENHANCED
        c = Card(rank=self.rng.choice(RANKS), suit=self.rng.choice(SUITS), uid=0)
        if self.rng.chance(8, "std_enh"):
            c.enhanced = self.rng.choice(ENHANCED)   # card.py 的无 m_ 前缀键
        if self.rng.chance(20, "std_ed"):
            c.edition = self.rng.choice(["foil", "holo", "poly"])
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
        from ..data import centers as centers_data
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

    def shop_closed(self):
        """离开商店：红卡/珀可等结算，随后自动进入下一盲注。"""
        from .effects import on_shop_closed
        on_shop_closed(self)
        self.temp_reroll_cost = None
        # 标签已在本商店应用完毕，离开时全部消费，避免下一商店重复触发
        self.tags.clear()
        # 检查下一盲注
        self._advance_blind_from_shop()

    def _advance_blind_from_shop(self):
        pass  # 盲注推进由 end_round 完成

    def reroll_shop(self) -> bool:
        cost = self.calculate_reroll_cost()
        if self.free_rerolls > 0:
            self.free_rerolls -= 1
        elif not self.can_afford(cost):
            self.say("金钱不足")
            return False
        else:
            self.dollars -= cost
        self.reroll_cost_increase += 1
        self.rerolls_total += 1
        from .effects import on_reroll
        on_reroll(self)
        self._generate_shop_jokers_only()
        return True

    def _generate_shop_jokers_only(self):
        self.shop_jokers = []
        for _ in range(self.shop_joker_max):
            self.shop_jokers.append(self._generate_shop_goods())

    def calculate_reroll_cost(self) -> int:
        base = self.temp_reroll_cost if self.temp_reroll_cost is not None else self.reroll_cost_base
        return max(0, base + self.reroll_cost_increase)

    def sell_joker(self, index: int) -> bool:
        if 0 <= index < len(self.jokers):
            j = self.jokers[index]
            if j.eternal:
                self.say("永恒小丑牌无法出售")
                return False
            self.dollars += j.sell_value()
            self.jokers.pop(index)
            if j.key == "j_luchador":
                self.boss_disabled_round = True
                self.say("摔跤手：禁用当前头目盲注效果")
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

    def use_consumable(self, index: int):
        from .effects import use_consumable as uc
        if 0 <= index < len(self.consumeables):
            c = self.consumeables[index]
            return uc(self, c)
        return None

    def finish_consumable_target(self, indices: List[int]) -> str:
        """CLI 选择完目标牌后调用。indices 为手牌下标。"""
        from .effects import finish_consumable_target as fc
        cards = [self.hand[i] for i in indices if 0 <= i < len(self.hand)]
        result = fc(self, cards)
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

    # ------------------------------------------------------------------
    # 消耗品获得
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 标签应用
    # ------------------------------------------------------------------
    def _apply_tag(self, tag: Tag):
        from .effects import apply_tag as at
        at(self, tag)

    # ------------------------------------------------------------------
    # 小丑工具
    # ------------------------------------------------------------------
    def count_jokers(self, *keys: str) -> int:
        return sum(1 for j in self.jokers if j.key in keys)

    def any_joker(self, *keys: str) -> bool:
        return self.count_jokers(*keys) > 0

    def has_voucher(self, *keys: str) -> bool:
        return any(k in self.used_vouchers for k in keys)


# ----------------------------------------------------------------------
# 转发（在 effects 中实现，避免循环导入）
# ----------------------------------------------------------------------
def _lazy_effects():
    from .effects import joker_dollar_bonus as f1, joker_cn as f2
    return f1, f2


def joker_dollar_bonus(game, joker) -> int:
    from .effects import joker_dollar_bonus as f
    return f(game, joker)


def joker_cn(key: str) -> str:
    from .effects import joker_cn as f
    return f(key)
