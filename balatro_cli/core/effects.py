from __future__ import annotations
from typing import List

from .scoring import Effect, Ctx
from .items import JokerItem, ConsumableItem, Tag
from .card import Card, rank_id, RANKS, SUITS, SUIT_CN
from .hand_eval import HAND_ORDER, HAND_CN, evaluate_poker_hand
from ..data import centers as centers_data
from ..data import consumables as consumable_data
from ..data import tags as tag_data


def joker_cn(key: str) -> str:
    if key in centers_data.JOKERS:
        return centers_data.JOKERS[key]["cn"]
    if key in consumable_data.ALL_CONSUMABLES:
        return consumable_data.ALL_CONSUMABLES[key]["cn"]
    return key


def roll_prob(game, denom: int, label: str = "") -> bool:
    if game.any_joker("j_oops"):
        denom = max(1, denom // 2)
    return game.rng.chance(denom, label)


# ==========================================================================
# 手牌"包含"关系（配对系小丑：j_jolly 等）
#
# 键 = 被包含的牌型，值 = 打出后会同时满足该牌型的牌型。
# 依据 Lua evaluate_poker_hand 返回的 results 表：某牌型 K 非空即表示该手牌
# "包含" K。除各分支的直接判定外，源码末尾还有三条派生：
#   五条 → 四条 → 三条 → 对子（取前 4/3/2 张），
# 因此例如葫芦含有对子/两对/三条、同花五条含有四条/三条/对子；
# 而四条不含两对（get_X_same(2) 恰好取 2 张，四条手牌里没有这样的组）。
# ==========================================================================
_CONTAINS = {
    "High Card": {"Flush Five", "Flush House", "Five of a Kind", "Straight Flush",
                  "Four of a Kind", "Full House", "Flush", "Straight",
                  "Three of a Kind", "Two Pair", "Pair"},
    "Pair": {"Flush Five", "Flush House", "Five of a Kind", "Four of a Kind",
             "Full House", "Three of a Kind", "Two Pair"},
    "Two Pair": {"Flush House", "Full House"},
    "Three of a Kind": {"Flush Five", "Flush House", "Five of a Kind",
                        "Four of a Kind", "Full House"},
    "Straight": {"Straight Flush"},
    "Flush": {"Flush Five", "Flush House", "Straight Flush"},
    "Full House": {"Flush House"},
    "Four of a Kind": {"Flush Five", "Five of a Kind"},
    "Straight Flush": set(),
    "Five of a Kind": {"Flush Five"},
    "Flush House": set(),
    "Flush Five": set(),
}


def contains_hand(actual: str, target: str) -> bool:
    """打出的 actual 牌型是否包含 target 牌型（如葫芦包含对子）。"""
    if actual == target:
        return True
    return actual in _CONTAINS.get(target, set())


def is_face_card(card: Card, game) -> bool:
    if game.any_joker("j_pareidolia"):
        return True
    return card.is_face()

def calculate_joker(game, joker: JokerItem, ctx: Ctx) -> List[Effect]:
    fn = JOKER_FX.get(joker.key)
    if fn is None:
        return []
    return fn(game, joker, ctx)


def _E(chips=0.0, mult=0.0, x_mult=1.0, dollars=0.0, repetitions=0, message="") -> Effect:
    return Effect(chips=chips, mult=mult, x_mult=x_mult, dollars=dollars,
                  repetitions=repetitions, message=message)

def _always_mult(game, j, ctx, base):
    if ctx.phase == "joker_main":
        return [_E(mult=base)]
    return []


def fx_j_joker(game, j, ctx):
    return _always_mult(game, j, ctx, 4)


def _suit_mult(game, j, ctx, suit, mult):
    if ctx.phase != "individual" or not ctx.other_card or ctx.hand_being_evaluated:
        return []
    c = ctx.other_card
    if c.debuffed:
        return []
    if c.is_suit(suit, smeared=game.any_joker("j_smeared")):
        return [_E(mult=mult)]
    return []


def fx_j_greedy_joker(game, j, ctx): return _suit_mult(game, j, ctx, "D", 3)
def fx_j_lusty_joker(game, j, ctx): return _suit_mult(game, j, ctx, "H", 3)
def fx_j_wrathful_joker(game, j, ctx): return _suit_mult(game, j, ctx, "S", 3)
def fx_j_gluttenous_joker(game, j, ctx): return _suit_mult(game, j, ctx, "C", 3)


def _hand_type(game, j, ctx, hand_type, mult=0, chips=0, x_mult=1.0):
    if ctx.phase != "joker_main":
        return []
    if contains_hand(ctx.scoring_name, hand_type):
        out = []
        if mult:
            out.append(_E(mult=mult))
        if chips:
            out.append(_E(chips=chips))
        if x_mult != 1.0:
            out.append(_E(x_mult=x_mult))
        return out
    return []


def fx_j_jolly(game, j, ctx): return _hand_type(game, j, ctx, "Pair", mult=8)
def fx_j_zany(game, j, ctx): return _hand_type(game, j, ctx, "Three of a Kind", mult=12)
def fx_j_mad(game, j, ctx): return _hand_type(game, j, ctx, "Two Pair", mult=10)
def fx_j_crazy(game, j, ctx): return _hand_type(game, j, ctx, "Straight", mult=12)
def fx_j_droll(game, j, ctx): return _hand_type(game, j, ctx, "Flush", mult=10)
def fx_j_sly(game, j, ctx): return _hand_type(game, j, ctx, "Pair", chips=50)
def fx_j_wily(game, j, ctx): return _hand_type(game, j, ctx, "Three of a Kind", chips=100)
def fx_j_clever(game, j, ctx): return _hand_type(game, j, ctx, "Two Pair", chips=80)
def fx_j_devious(game, j, ctx): return _hand_type(game, j, ctx, "Straight", chips=100)
def fx_j_crafty(game, j, ctx): return _hand_type(game, j, ctx, "Flush", chips=80)
def fx_j_duo(game, j, ctx): return _hand_type(game, j, ctx, "Pair", x_mult=2)
def fx_j_trio(game, j, ctx): return _hand_type(game, j, ctx, "Three of a Kind", x_mult=3)
def fx_j_family(game, j, ctx): return _hand_type(game, j, ctx, "Four of a Kind", x_mult=4)
def fx_j_order(game, j, ctx): return _hand_type(game, j, ctx, "Straight", x_mult=3)
def fx_j_tribe(game, j, ctx): return _hand_type(game, j, ctx, "Flush", x_mult=2)


def fx_j_half(game, j, ctx):
    if ctx.phase == "joker_main" and len(ctx.played_cards) <= 3:
        return [_E(mult=20)]
    return []


def fx_j_stencil(game, j, ctx):
    if ctx.phase != "joker_main":
        return []
    empty = game.joker_slots - len(game.jokers)
    if empty >= 1:
        return [_E(x_mult=empty)]
    return []


def fx_j_credit_card(game, j, ctx):
    return []


def fx_j_banner(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(chips=game.discards_left * 30)]
    return []


def fx_j_mystic_summit(game, j, ctx):
    if ctx.phase == "joker_main" and game.discards_left == 0:
        return [_E(mult=15)]
    return []


def fx_j_misprint(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=game.rng.int(0, 23, "misprint"))]
    return []


def fx_j_raised_fist(game, j, ctx):
    if ctx.phase != "individual" or not ctx.hand_being_evaluated:
        return []
    held = [c for c in game.hand if not c.debuffed]
    if not held:
        return []
    lowest = min(held, key=lambda c: rank_id(c.rank))
    return [_E(mult=2 * rank_id(lowest.rank))]


def fx_j_scary_face(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game):
            return [_E(chips=30)]
    return []


def fx_j_abstract(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=3 * max(0, len(game.jokers) - 1))]
    return []


def fx_j_even_steven(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        rid = rank_id(ctx.other_card.rank)
        if rid in (2, 4, 6, 8, 10):
            return [_E(mult=4)]
    return []


def fx_j_odd_todd(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        rid = rank_id(ctx.other_card.rank)
        if rid in (3, 5, 7, 9, 11, 14):
            return [_E(chips=31)]
    return []


def fx_j_scholar(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.rank == "A":
            return [_E(chips=20, mult=4)]
    return []


def fx_j_fibonacci(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        rid = rank_id(ctx.other_card.rank)
        if rid in (14, 2, 3, 5, 8):
            return [_E(mult=8)]
    return []


def fx_j_supernova(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=game.hands_count.get(ctx.scoring_name, 0))]
    return []


def fx_j_runner(game, j, ctx):
    if ctx.phase == "joker_main":
        if contains_hand(ctx.scoring_name, "Straight"):
            j.stat["chips"] = j.stat.get("chips", 0) + 15
        return [_E(chips=j.stat.get("chips", 0))]
    return []


def fx_j_ice_cream(game, j, ctx):
    if ctx.phase == "joker_main":
        j.stat["chips"] = j.stat.get("chips", 100) - 5
        return [_E(chips=max(0, j.stat["chips"]))]
    return []


def fx_j_blue_joker(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(chips=game.deck.count() * 2)]
    return []


def fx_j_green_joker(game, j, ctx):
    if ctx.phase == "after":
        j.stat["mult"] = j.stat.get("mult", 0) + 1
    if ctx.phase == "joker_main":
        return [_E(mult=j.stat.get("mult", 0))]
    return []


def fx_j_todo_list(game, j, ctx):
    if ctx.phase == "joker_main" and ctx.scoring_name == j.stat.get("todo", "High Card"):
        return [_E(dollars=4)]
    return []


def fx_j_square(game, j, ctx):
    if ctx.phase == "joker_main":
        if len(ctx.played_cards) == 4:
            j.stat["chips"] = j.stat.get("chips", 0) + 4
        return [_E(chips=j.stat.get("chips", 0))]
    return []


def fx_j_bull(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(chips=game.dollars * 2)]
    return []


def fx_j_popcorn(game, j, ctx):
    if ctx.phase == "joker_main":
        j.stat["mult"] = j.stat.get("mult", 20) - 4
        return [_E(mult=max(0, j.stat["mult"]))]
    return []


def fx_j_ramen(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 2.0 - j.stat.get("lost", 0.0)))]
    return []


def fx_j_trousers(game, j, ctx):
    if ctx.phase == "joker_main":
        if contains_hand(ctx.scoring_name, "Two Pair"):
            j.stat["mult"] = j.stat.get("mult", 0) + 2
        return [_E(mult=j.stat.get("mult", 0))]
    return []


def fx_j_gros_michel(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=15)]
    return []


def fx_j_cavendish(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=3)]
    return []


def fx_j_superposition(game, j, ctx):
    if ctx.phase == "joker_main" and contains_hand(ctx.scoring_name, "Straight"):
        if any(c.rank == "A" for c in ctx.scoring_cards):
            game.gain_random_consumable_of("tarot")
            return [_E(message="叠加：生成塔罗牌")]
    return []


def fx_j_swashbuckler(game, j, ctx):
    if ctx.phase == "joker_main":
        total = sum(oj.sell_value() for oj in game.jokers if oj is not j)
        return [_E(mult=total)]
    return []


def fx_j_shoot_the_moon(game, j, ctx):
    if ctx.phase == "individual" and ctx.hand_being_evaluated and ctx.other_card:
        if ctx.other_card.rank == "Q" and not ctx.other_card.debuffed:
            return [_E(mult=13)]
    return []


def fx_j_smiley(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game):
            return [_E(mult=5)]
    return []


def fx_j_walkie_talkie(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.rank in ("10", "4"):
            return [_E(chips=10, mult=4)]
    return []


def fx_j_stone(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for c in game.deck.cards if c.enhanced == "stone")
        n += sum(1 for c in game.hand if c.enhanced == "stone")
        return [_E(chips=n * 25)]
    return []


def fx_j_lucky_cat(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.25 * game.lucky_triggers))]
    return []


def fx_j_hanging_chad(game, j, ctx):
    if ctx.phase == "repetition" and ctx.other_card is not None:
        if ctx.other_card in ctx.scoring_cards and ctx.scoring_cards.index(ctx.other_card) == 0:
            return [_E(repetitions=2)]
    return []


def fx_j_mime(game, j, ctx):
    if ctx.phase == "repetition" and ctx.hand_being_evaluated:
        return [_E(repetitions=1)]
    return []


def fx_j_hack(game, j, ctx):
    if ctx.phase == "repetition" and ctx.other_card and not ctx.hand_being_evaluated:
        if rank_id(ctx.other_card.rank) in (2, 3, 4, 5):
            return [_E(repetitions=1)]
    return []


def fx_j_sock_and_buskin(game, j, ctx):
    if ctx.phase == "repetition" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game):
            return [_E(repetitions=1)]
    return []


def fx_j_dusk(game, j, ctx):
    if ctx.phase == "repetition" and not ctx.hand_being_evaluated and ctx.other_card:
        if game.hands_left == 0:
            return [_E(repetitions=1)]
    return []


def fx_j_acrobat(game, j, ctx):
    if ctx.phase == "joker_main" and game.hands_left == 0:
        return [_E(x_mult=3)]
    return []


def fx_j_selzer(game, j, ctx):
    if ctx.phase == "repetition" and ctx.other_card and not ctx.hand_being_evaluated:
        if j.stat.get("hands_left", 10) > 0:
            return [_E(repetitions=1)]
    if ctx.phase == "after":
        if j.stat.get("hands_left", 10) > 0:
            j.stat["hands_left"] = j.stat.get("hands_left", 10) - 1
    return []


def fx_j_card_sharp(game, j, ctx):
    if ctx.phase == "joker_main":
        if game.round_hand_played.count(ctx.scoring_name) >= 2:
            return [_E(x_mult=3)]
    return []


def fx_j_photograph(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.scoring_cards and ctx.other_card is ctx.scoring_cards[0]:
            if is_face_card(ctx.other_card, game):
                return [_E(x_mult=2)]
    return []


def fx_j_triboulet(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.rank in ("K", "Q"):
            return [_E(x_mult=2)]
    return []


def fx_j_ancient(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        suit = j.stat.get("suit", "S")
        if ctx.other_card.is_suit(suit, smeared=game.any_joker("j_smeared")):
            return [_E(x_mult=1.5)]
    return []


def fx_j_bloodstone(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.is_suit("H", smeared=game.any_joker("j_smeared")) and roll_prob(game, 2, "bloodstone"):
            return [_E(x_mult=1.5)]
    return []


def fx_j_arrowhead(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.is_suit("S", smeared=game.any_joker("j_smeared")):
            return [_E(chips=50)]
    return []


def fx_j_onyx_agate(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.is_suit("C", smeared=game.any_joker("j_smeared")):
            return [_E(mult=7)]
    return []


def fx_j_idol(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        key = j.stat.get("card", ("A", "H"))
        if ctx.other_card.rank == key[0] and ctx.other_card.is_suit(key[1], smeared=game.any_joker("j_smeared")):
            return [_E(x_mult=2)]
    return []


def fx_j_seeing_double(game, j, ctx):
    if ctx.phase == "joker_main":
        smeared = game.any_joker("j_smeared")
        has_club = any(c.is_suit("C", smeared=smeared) for c in ctx.scoring_cards)
        has_other = any(not c.is_suit("C", smeared=smeared) for c in ctx.scoring_cards)
        if has_club and has_other:
            return [_E(x_mult=2)]
    return []


def fx_j_flower_pot(game, j, ctx):
    if ctx.phase == "joker_main":
        # 对应 Lua card.lua Flower Pot：逐张计数，elseif 保证每张牌只补一个花色；
        # 模糊小丑下黑牌可能同时满足 S/C，红牌同时满足 H/D。
        smeared = game.any_joker("j_smeared")
        suits = {"H": 0, "D": 0, "S": 0, "C": 0}
        for c in ctx.scoring_cards:
            if c.enhanced != "wild":
                for s in ("H", "D", "S", "C"):
                    if c.is_suit(s, smeared=smeared) and suits[s] == 0:
                        suits[s] += 1
                        break
        for c in ctx.scoring_cards:
            if c.enhanced == "wild":
                for s in ("H", "D", "S", "C"):
                    if c.is_suit(s, smeared=smeared) and suits[s] == 0:
                        suits[s] += 1
                        break
        if all(suits.values()):
            return [_E(x_mult=3)]
    return []


def fx_j_blackboard(game, j, ctx):
    if ctx.phase == "joker_main":
        smeared = game.any_joker("j_smeared")
        if all(c.is_suit("S", smeared=smeared) or c.is_suit("C", smeared=smeared) for c in game.hand):
            return [_E(x_mult=3)]
    return []


def fx_j_baron(game, j, ctx):
    if ctx.phase == "individual" and ctx.hand_being_evaluated and ctx.other_card:
        if ctx.other_card.rank == "K" and not ctx.other_card.debuffed:
            return [_E(x_mult=1.5)]
    return []


def fx_j_steel_joker(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for c in game.deck.cards if c.enhanced == "steel")
        n += sum(1 for c in game.hand if c.enhanced == "steel")
        return [_E(x_mult=max(1.0, 1.0 + 0.2 * n))]
    return []


def fx_j_drivers_license(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for c in game.deck.cards if c.enhanced)
        n += sum(1 for c in game.hand if c.enhanced)
        if n >= 16:
            return [_E(x_mult=3)]
    return []


def fx_j_erosion(game, j, ctx):
    if ctx.phase == "joker_main":
        below = 52 - len(game.deck.cards)
        if below > 0:
            return [_E(mult=4 * below)]
    return []


def fx_j_throwback(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.25 * game.skips))]
    return []


def fx_j_ride_the_bus(game, j, ctx):
    if ctx.phase == "after":
        if any(is_face_card(c, game) for c in ctx.scoring_cards):
            j.stat["mult"] = 0
        else:
            j.stat["mult"] = j.stat.get("mult", 0) + 1
    if ctx.phase == "joker_main":
        return [_E(mult=j.stat.get("mult", 0))]
    return []


def fx_j_constellation(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.1 * game.constellation_count))]
    return []


def fx_j_hologram(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.25 * game.hologram_count))]
    return []


def fx_j_vampire(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.enhanced and ctx.other_card.enhanced != "stone":
            j.stat["x_mult"] = j.stat.get("x_mult", 1.0) + 0.1
            ctx.other_card.enhanced = None
            return [_E(message="吸血鬼吸走了增强")]
    if ctx.phase == "joker_main":
        return [_E(x_mult=j.stat.get("x_mult", 1.0))]
    return []


def fx_j_obelisk(game, j, ctx):
    if ctx.phase == "after":
        most = max(game.hands_count, key=lambda k: game.hands_count[k]) if game.hands_count else None
        if most != ctx.scoring_name:
            j.stat["x_mult"] = j.stat.get("x_mult", 1.0) + 0.2
        else:
            j.stat["x_mult"] = 1.0
    if ctx.phase == "joker_main":
        return [_E(x_mult=j.stat.get("x_mult", 1.0))]
    return []


def fx_j_wee(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.rank == "2":
            j.stat["chips"] = j.stat.get("chips", 0) + 8
    if ctx.phase == "joker_main":
        return [_E(chips=j.stat.get("chips", 0))]
    return []


def fx_j_red_card(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=j.stat.get("mult", 0))]
    return []


def fx_j_flash(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=j.stat.get("mult", 0))]
    return []


def fx_j_baseball(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for oj in game.jokers
                if centers_data.JOKERS.get(oj.key, {}).get("r") == 2)
        return [_E(x_mult=max(1.0, 1.0 + 1.5 * n))]
    return []


def fx_j_stuntman(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(chips=250)]
    return []


def fx_j_bootstraps(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=(game.dollars // 5) * 2)]
    return []


def fx_j_loyalty_card(game, j, ctx):
    if ctx.phase == "joker_main":
        if game.hands_played_total % 5 == 0 and game.hands_played_total > 0:
            return [_E(x_mult=4)]
    return []


def fx_j_mr_bones(game, j, ctx):
    return []


def fx_j_chicot(game, j, ctx):
    return []


def fx_j_yorick(game, j, ctx):
    if ctx.phase == "joker_main":
        n = j.stat.get("discards", 0) // 23
        return [_E(x_mult=max(1.0, 1.0 + float(n)))]
    return []


def fx_j_caino(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + float(game.face_destroyed)))]
    return []


def fx_j_glass(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.75 * game.glass_broken))]
    return []


def fx_j_hit_the_road(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.5 * j.stat.get("jacks", 0)))]
    return []


def fx_j_midas_mask(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game) and not ctx.other_card.enhanced:
            ctx.other_card.enhanced = "gold"
    return []


def fx_j_ticket(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.enhanced == "gold":
            return [_E(dollars=4)]
    return []


def fx_j_rough_gem(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.is_suit("D", smeared=game.any_joker("j_smeared")):
            return [_E(dollars=1)]
    return []


def fx_j_business(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game) and roll_prob(game, 2, "business"):
            return [_E(dollars=2)]
    return []


def fx_j_space(game, j, ctx):
    if ctx.phase == "after":
        if roll_prob(game, 4, "space"):
            game.hand_levels[ctx.scoring_name] += 1
            return [_E(message=f"太空小丑：{HAND_CN.get(ctx.scoring_name, ctx.scoring_name)} 等级+1")]
    return []


def fx_j_sixth_sense(game, j, ctx):
    if ctx.phase == "joker_main" and game.hands_played_round == 1:
        if len(ctx.played_cards) == 1 and ctx.played_cards[0].rank == "6":
            card = ctx.played_cards[0]
            game.notify_destroyed(card)
            if card in game.deck.cards:
                game.deck.cards.remove(card)
            game.gain_random_consumable_of("spectral")
            return [_E(message="第六感：销毁 6 并生成幻灵牌")]
    return []


def fx_j_dna(game, j, ctx):
    if ctx.phase == "joker_main" and game.hands_played_round == 1:
        if len(ctx.played_cards) == 1:
            card = ctx.played_cards[0]
            copy = card.copy()
            game.deck.add(copy)
            game.hologram_count += 1
            game.hand.append(copy)
            game.sort_hand()
            return [_E(message="DNA：复制牌加入牌组并抓入手")]
    return []


def fx_j_seance(game, j, ctx):
    if ctx.phase == "joker_main" and ctx.scoring_name == "Straight Flush":
        game.gain_random_consumable_of("spectral")
        return [_E(message="降神会：生成幻灵牌")]
    return []


def fx_j_8_ball(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.rank == "8" and roll_prob(game, 4, "8ball"):
            game.gain_random_consumable_of("tarot")
            return [_E(message="八号球：生成塔罗牌")]
    return []


def fx_j_vagabond(game, j, ctx):
    if ctx.phase == "after" and game.dollars <= 4:
        game.gain_random_consumable_of("tarot")
        return [_E(message="流浪汉：生成塔罗牌")]
    return []


def fx_j_hiker(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        game.card_chip_extra[id(ctx.other_card)] = game.card_chip_extra.get(id(ctx.other_card), 0) + 5
    return []


def fx_j_fortune_teller(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=game.tarots_used)]
    return []


def fx_j_blueprint(game, j, ctx):
    idx = game.jokers.index(j)
    if idx + 1 >= len(game.jokers):
        return []
    if ctx.blueprint >= len(game.jokers) + 1:
        return []
    ctx.blueprint += 1
    try:
        return calculate_joker(game, game.jokers[idx + 1], ctx)
    finally:
        ctx.blueprint -= 1


def fx_j_brainstorm(game, j, ctx):
    if not game.jokers or game.jokers[0] is j:
        return []
    if ctx.blueprint >= len(game.jokers) + 1:
        return []
    ctx.blueprint += 1
    try:
        return calculate_joker(game, game.jokers[0], ctx)
    finally:
        ctx.blueprint -= 1


JOKER_FX = {
    "j_joker": fx_j_joker, "j_greedy_joker": fx_j_greedy_joker,
    "j_lusty_joker": fx_j_lusty_joker, "j_wrathful_joker": fx_j_wrathful_joker,
    "j_gluttenous_joker": fx_j_gluttenous_joker,
    "j_jolly": fx_j_jolly, "j_zany": fx_j_zany, "j_mad": fx_j_mad,
    "j_crazy": fx_j_crazy, "j_droll": fx_j_droll,
    "j_sly": fx_j_sly, "j_wily": fx_j_wily, "j_clever": fx_j_clever,
    "j_devious": fx_j_devious, "j_crafty": fx_j_crafty,
    "j_half": fx_j_half, "j_stencil": fx_j_stencil,
    "j_credit_card": fx_j_credit_card, "j_banner": fx_j_banner,
    "j_mystic_summit": fx_j_mystic_summit, "j_misprint": fx_j_misprint,
    "j_raised_fist": fx_j_raised_fist, "j_scary_face": fx_j_scary_face,
    "j_abstract": fx_j_abstract, "j_even_steven": fx_j_even_steven,
    "j_odd_todd": fx_j_odd_todd, "j_scholar": fx_j_scholar,
    "j_fibonacci": fx_j_fibonacci, "j_supernova": fx_j_supernova,
    "j_runner": fx_j_runner, "j_ice_cream": fx_j_ice_cream,
    "j_blue_joker": fx_j_blue_joker, "j_green_joker": fx_j_green_joker,
    "j_todo_list": fx_j_todo_list, "j_square": fx_j_square,
    "j_bull": fx_j_bull, "j_popcorn": fx_j_popcorn,
    "j_ramen": fx_j_ramen, "j_trousers": fx_j_trousers,
    "j_gros_michel": fx_j_gros_michel, "j_cavendish": fx_j_cavendish,
    "j_superposition": fx_j_superposition, "j_swashbuckler": fx_j_swashbuckler,
    "j_shoot_the_moon": fx_j_shoot_the_moon, "j_smiley": fx_j_smiley,
    "j_walkie_talkie": fx_j_walkie_talkie, "j_stone": fx_j_stone,
    "j_lucky_cat": fx_j_lucky_cat, "j_hanging_chad": fx_j_hanging_chad,
    "j_mime": fx_j_mime, "j_hack": fx_j_hack,
    "j_sock_and_buskin": fx_j_sock_and_buskin, "j_dusk": fx_j_dusk,
    "j_acrobat": fx_j_acrobat, "j_selzer": fx_j_selzer,
    "j_card_sharp": fx_j_card_sharp, "j_photograph": fx_j_photograph,
    "j_triboulet": fx_j_triboulet, "j_ancient": fx_j_ancient,
    "j_bloodstone": fx_j_bloodstone, "j_arrowhead": fx_j_arrowhead,
    "j_onyx_agate": fx_j_onyx_agate, "j_idol": fx_j_idol,
    "j_seeing_double": fx_j_seeing_double, "j_flower_pot": fx_j_flower_pot,
    "j_blackboard": fx_j_blackboard, "j_baron": fx_j_baron,
    "j_steel_joker": fx_j_steel_joker, "j_drivers_license": fx_j_drivers_license,
    "j_erosion": fx_j_erosion, "j_throwback": fx_j_throwback,
    "j_ride_the_bus": fx_j_ride_the_bus, "j_constellation": fx_j_constellation,
    "j_hologram": fx_j_hologram, "j_vampire": fx_j_vampire,
    "j_obelisk": fx_j_obelisk, "j_wee": fx_j_wee,
    "j_red_card": fx_j_red_card, "j_flash": fx_j_flash,
    "j_baseball": fx_j_baseball, "j_stuntman": fx_j_stuntman,
    "j_bootstraps": fx_j_bootstraps, "j_loyalty_card": fx_j_loyalty_card,
    "j_mr_bones": fx_j_mr_bones, "j_chicot": fx_j_chicot,
    "j_yorick": fx_j_yorick, "j_caino": fx_j_caino,
    "j_glass": fx_j_glass, "j_hit_the_road": fx_j_hit_the_road,
    "j_midas_mask": fx_j_midas_mask, "j_ticket": fx_j_ticket,
    "j_rough_gem": fx_j_rough_gem, "j_business": fx_j_business,
    "j_space": fx_j_space, "j_sixth_sense": fx_j_sixth_sense,
    "j_seance": fx_j_seance, "j_8_ball": fx_j_8_ball,
    "j_vagabond": fx_j_vagabond, "j_hiker": fx_j_hiker,
    "j_fortune_teller": fx_j_fortune_teller,
    "j_duo": fx_j_duo, "j_trio": fx_j_trio, "j_family": fx_j_family,
    "j_order": fx_j_order, "j_tribe": fx_j_tribe,
    "j_dna": fx_j_dna,
    "j_blueprint": fx_j_blueprint, "j_brainstorm": fx_j_brainstorm,
}


# ==========================================================================
# 动态小丑：当前已生效效果（只读实时预览，供 UI 显示）
# ==========================================================================
def _fmt_x(v: float) -> str:
    """把 x_mult 数值渲染成紧凑形式：×1 → ×1.25 → ×1.5。"""
    if abs(v - round(v)) < 1e-9:
        return f"×{int(round(v))}"
    return f"×{f'{v:.2f}'.rstrip('0').rstrip('.')}"


def joker_live_effect(game, j) -> str:
    k = j.key
    stat = j.stat

    # ---- 永久成长 ×倍率 ----
    if k == "j_yorick":
        n = stat.get("discards", 0) // 23
        nxt = (n + 1) * 23
        return f"{_fmt_x(1.0 + n)}(弃{stat.get('discards', 0)}/{nxt})"
    if k == "j_caino":
        return _fmt_x(1.0 + game.face_destroyed)
    if k == "j_hologram":
        return _fmt_x(1.0 + 0.25 * game.hologram_count)
    if k == "j_glass":
        return _fmt_x(1.0 + 0.75 * game.glass_broken)
    if k == "j_hit_the_road":
        return _fmt_x(1.0 + 0.5 * stat.get("jacks", 0))
    if k == "j_constellation":
        return _fmt_x(1.0 + 0.1 * game.constellation_count)
    if k == "j_lucky_cat":
        return _fmt_x(1.0 + 0.25 * game.lucky_triggers)
    if k == "j_throwback":
        return _fmt_x(1.0 + 0.25 * game.skips)
    if k == "j_steel_joker":
        n = sum(1 for c in game.deck.cards if c.enhanced == "steel")
        n += sum(1 for c in game.hand if c.enhanced == "steel")
        return _fmt_x(1.0 + 0.2 * n)
    if k == "j_baseball":
        n = sum(1 for oj in game.jokers
                if centers_data.JOKERS.get(oj.key, {}).get("r") == 2)
        return _fmt_x(1.0 + 1.5 * n)
    if k == "j_stencil":
        empty = game.joker_slots - len(game.jokers)
        return _fmt_x(float(empty)) if empty >= 1 else "无生效"
    if k == "j_drivers_license":
        n = sum(1 for c in game.deck.cards if c.enhanced)
        n += sum(1 for c in game.hand if c.enhanced)
        return "×3" if n >= 16 else f"未激活({n}/16)"
    if k == "j_ramen":
        return _fmt_x(max(1.0, 2.0 - stat.get("lost", 0.0)))

    # ---- 每轮随机目标（当前生效条件） ----
    if k == "j_todo_list":
        t = stat.get("todo", "High Card")
        return f"目标{HAND_CN.get(t, t)}"
    if k == "j_ancient":
        return f"花色{SUIT_CN.get(stat.get('suit', 'S'), stat.get('suit', 'S'))}"
    if k == "j_idol":
        r, s = stat.get("card", ("A", "H"))
        return f"{r}{SUIT_CN.get(s, s)}"
    if k == "j_mail":
        return f"目标{stat.get('rank', 'A')}"

    # ---- 随局实时 +筹码 / +倍率 ----
    if k == "j_blue_joker":
        return f"+{game.deck.count() * 2}筹码"
    if k == "j_bull":
        return f"+{game.dollars * 2}筹码"
    if k == "j_stone":
        n = sum(1 for c in game.deck.cards if c.enhanced == "stone")
        n += sum(1 for c in game.hand if c.enhanced == "stone")
        return f"+{n * 25}筹码"
    if k == "j_banner":
        return f"+{game.discards_left * 30}筹码"
    if k == "j_abstract":
        return f"+{3 * max(0, len(game.jokers) - 1)}倍率"
    if k == "j_swashbuckler":
        total = sum(oj.sell_value() for oj in game.jokers if oj is not j)
        return f"+{total}倍率"
    if k == "j_bootstraps":
        return f"+{(game.dollars // 5) * 2}倍率"
    if k == "j_fortune_teller":
        return f"+{game.tarots_used}倍率"
    if k == "j_mystic_summit":
        return "+15倍率" if game.discards_left == 0 else "未激活"
    if k == "j_erosion":
        below = 52 - len(game.deck.cards)
        if below > 0:
            return f"+{4 * below}倍率"
    if k == "j_raised_fist":
        held = [c for c in game.hand if not c.debuffed]
        if held:
            lowest = min(held, key=lambda c: rank_id(c.rank))
            return f"+{2 * rank_id(lowest.rank)}倍率"
    return ""


def joker_dollar_bonus(game, joker: JokerItem) -> int:
    key = joker.key
    d = 0
    if key == "j_golden":
        d += 4
    elif key == "j_cloud_9":
        n = sum(1 for c in game.deck.cards if c.rank == "9")
        d += n
    elif key == "j_rocket":
        d += joker.stat.get("dollars", 1)
    elif key == "j_satellite":
        d += len(game.planets_used)
    elif key == "j_to_the_moon":
        d += game.dollars // 5
    elif key == "j_delayed_grat":
        if game.discards_used_round == 0:
            d += game.discards_left * 2
    return d


def _add_planet(game, key: str) -> None:
    info = consumable_data.PLANETS[key]
    game.hand_levels[info["hand"]] += 1
    game.planets_used.add(key)
    game.constellation_count += 1
    game.say(f"星球牌：{info['cn']} —— {HAND_CN.get(info['hand'], info['hand'])} 等级升至 {game.hand_levels[info['hand']]}")


def mark_consumable_used(game, key: str) -> None:
    """记录一张刚生效的消耗牌（Lua 在 card:use_consumeable 里统一维护）。

    塔罗 / 星球牌写入 ``last_tarot_planet``——愚者据此复制上一次使用的牌；
    塔罗牌同时累计 ``tarots_used``——幸运预言师据此加倍数。
    """
    if key in consumable_data.TAROTS or key in consumable_data.PLANETS:
        game.last_tarot_planet = key
        if key in consumable_data.TAROTS:
            game.tarots_used += 1


def use_consumable(game, item: ConsumableItem) -> str:
    """使用一张消耗牌；返回 "done" / "needs_target" / "invalid"。

    需要选目标的塔罗牌此时只登记 ``pending_consumable``，等玩家选完目标后
    由 :func:`finish_consumable_target` 生效并补记使用状态。
    """
    status = _apply_consumable(game, item)
    if status == "done":
        mark_consumable_used(game, item.key)
    return status


def _apply_consumable(game, item: ConsumableItem) -> str:
    key = item.key
    if key in consumable_data.PLANETS:
        _add_planet(game, key)
        game.consumeables.remove(item)
        return "done"

    # ---- 塔罗牌（无目标）----
    if key == "c_fool":
        last = game.last_tarot_planet
        if last and last != "c_fool" and last in consumable_data.ALL_CONSUMABLES:
            info = consumable_data.ALL_CONSUMABLES[last]
            if len(game.consumeables) < game.consumable_slots:
                game.consumeables.append(ConsumableItem(key=last, buy_cost=info["cost"],
                                                        sell_price=max(1, info["cost"] // 2)))
                game.say(f"愚者：生成 {consumable_data.get_consumable_cn(last)}")
            else:
                game.say("愚者：消耗品栏已满")
        else:
            game.say("愚者：没有可复制的牌")
        game.consumeables.remove(item)
        return "done"
    if key == "c_high_priestess":
        game.consumeables.remove(item)
        for _ in range(2):
            pk = game.rng.choice(list(consumable_data.PLANETS))
            game.gain_consumable(pk)
        game.say("女祭司：生成 2 张星球牌")
        return "done"
    if key == "c_emperor":
        game.consumeables.remove(item)
        for _ in range(2):
            tk = game.rng.choice(list(consumable_data.TAROTS))
            game.gain_consumable(tk)
        game.say("皇帝：生成 2 张塔罗牌")
        return "done"
    if key == "c_hermit":
        gain = min(game.dollars, 20)
        game.dollars += gain
        game.say(f"隐者：金钱翻倍 +${gain}")
        game.consumeables.remove(item)
        return "done"
    if key == "c_temperance":
        total = sum(j.sell_value() for j in game.jokers)
        gain = min(total, 50)
        game.dollars += gain
        game.say(f"节制：+${gain}")
        game.consumeables.remove(item)
        return "done"
    if key == "c_wheel_of_fortune":
        if not game.jokers:
            game.say("命运之轮：没有小丑牌")
        elif roll_prob(game, 4, "wheel"):
            j = game.rng.choice(game.jokers)
            j.edition = game.rng.choice(["foil", "holo", "poly"])
            game.say(f"命运之轮：{joker_cn(j.key)} 获得版本 {j.edition}！")
        else:
            game.say("命运之轮：NOPE！")
        game.consumeables.remove(item)
        return "done"
    if key == "c_judgement":
        jk = centers_data.random_joker_key(game)
        if len(game.jokers) >= game.joker_slots:
            game.say("审判：小丑栏已满")
        else:
            cfg = centers_data.joker_cfg(jk)
            game.jokers.append(JokerItem(key=jk, buy_cost=cfg["cost"], sell_price=max(1, cfg["cost"] // 2)))
            game.say(f"审判：获得小丑 {cfg['cn']}")
        game.consumeables.remove(item)
        return "done"
    if key == "c_wraith":
        jk = centers_data.random_joker_key(game, rarity=3)
        if len(game.jokers) >= game.joker_slots:
            game.say("魅影：小丑栏已满")
        else:
            cfg = centers_data.joker_cfg(jk)
            game.jokers.append(JokerItem(key=jk, buy_cost=cfg["cost"], sell_price=max(1, cfg["cost"] // 2)))
            game.say(f"魅影：获得稀有小丑 {cfg['cn']}")
        game.dollars = 0
        game.consumeables.remove(item)
        return "done"
    if key == "c_immolate":
        n = min(5, len(game.hand))
        for c in game.rng.sample(game.hand, n):
            game.hand.remove(c)
            game.notify_destroyed(c)
        game.dollars += 20
        game.say(f"献祭：销毁 {n} 张手牌，+$20")
        game.consumeables.remove(item)
        return "done"
    if key == "c_soul":
        jk = centers_data.random_joker_key(game, rarity=4)
        if len(game.jokers) >= game.joker_slots:
            game.say("灵魂：小丑栏已满")
        else:
            cfg = centers_data.joker_cfg(jk)
            game.jokers.append(JokerItem(key=jk, buy_cost=cfg["cost"], sell_price=max(1, cfg["cost"] // 2)))
            game.say(f"灵魂：获得传说小丑 {cfg['cn']}！")
        game.consumeables.remove(item)
        return "done"
    if key == "c_black_hole":
        for h in game.hand_levels:
            game.hand_levels[h] += 1
        game.say("黑洞：所有手牌类型等级 +1")
        game.consumeables.remove(item)
        return "done"

    if key == "c_familiar":
        _destroy_random_hand(game, 1)
        for _ in range(3):
            game.hand.append(_random_card(game, face=True))
        game.sort_hand()
        game.say("眷属：销毁 1 张手牌，生成 3 张人头")
        game.consumeables.remove(item)
        return "done"
    if key == "c_grim":
        _destroy_random_hand(game, 1)
        for _ in range(2):
            game.hand.append(_random_card(game, rank="A", enhanced="bonus"))
        game.sort_hand()
        game.say("阴森：销毁 1 张手牌，生成 2 张增强 A")
        game.consumeables.remove(item)
        return "done"
    if key == "c_incantation":
        _destroy_random_hand(game, 1)
        for _ in range(4):
            game.hand.append(_random_card(game, number=True, enhanced="bonus"))
        game.sort_hand()
        game.say("咒文：销毁 1 张手牌，生成 4 张增强数字牌")
        game.consumeables.remove(item)
        return "done"
    if key == "c_sigil":
        suit = game.rng.choice(SUITS)
        for c in game.hand:
            c.suit = suit
        game.sort_hand()
        game.say(f"纹章：所有手牌变成 {suit}")
        game.consumeables.remove(item)
        return "done"
    if key == "c_ouija":
        rank = game.rng.choice(RANKS)
        for c in game.hand:
            c.rank = rank
        game.hand_size = max(1, game.hand_size - 1)
        game.say(f"灵应盘：所有手牌变成 {rank}，手牌上限 -1")
        game.consumeables.remove(item)
        return "done"
    if key == "c_ectoplasm":
        if game.jokers:
            j = game.rng.choice(game.jokers)
            j.edition = "negative"
            game.say(f"灵质：{joker_cn(j.key)} 获得负片版本")
        game.hand_size = max(1, game.hand_size - 1)
        game.say("灵质：手牌上限 -1")
        game.consumeables.remove(item)
        return "done"
    if key == "c_ankh":
        if game.jokers:
            keep = game.rng.choice(game.jokers)
            for v in list(game.jokers):
                if v is not keep and not v.eternal:
                    game.jokers.remove(v)
            if len(game.jokers) < game.joker_slots or keep.negative:
                copy = JokerItem(key=keep.key, edition=keep.edition,
                                 sell_price=keep.sell_price, buy_cost=keep.buy_cost,
                                 stat=dict(keep.stat))
                game.jokers.append(copy)
            game.say("安卡：销毁其他小丑，复制 1 张")
        game.consumeables.remove(item)
        return "done"
    if key == "c_hex":
        if game.jokers:
            j = game.rng.choice(game.jokers)
            j.edition = "poly"
            game.say(f"诅咒：{joker_cn(j.key)} 获得彩绘版本")
            for v in list(game.jokers):
                if v is not j and not v.eternal:
                    game.jokers.remove(v)
        game.consumeables.remove(item)
        return "done"

    game.pending_consumable = item
    return "needs_target"


def _destroy_random_hand(game, n: int):
    n = min(n, len(game.hand))
    for c in game.rng.sample(game.hand, n):
        game.hand.remove(c)
        game.notify_destroyed(c)


def _random_card(game, face=False, number=False, rank=None, enhanced=None, seal=False) -> Card:
    from .card import Card
    r = rank
    if r is None:
        if face:
            r = game.rng.choice(["J", "Q", "K"])
        elif number:
            r = game.rng.choice(["2", "3", "4", "5", "6", "7", "8", "9", "10"])
        else:
            r = game.rng.choice(RANKS)
    s = game.rng.choice(SUITS)
    sl = None
    if seal:
        sl = game.rng.choice(["gold", "red", "blue", "purple"])
    return Card(rank=r, suit=s, enhanced=enhanced, seal=sl, uid=0)


def finish_consumable_target(game, target_cards: List[Card]) -> str:
    item = game.pending_consumable
    if item is None:
        return "无待定消耗牌"
    key = item.key
    info = consumable_data.ALL_CONSUMABLES.get(key, {})
    min_sel = info.get("min_highlighted", 1)
    max_sel = info.get("max_highlighted", min_sel)
    if key == "c_death":
        max_sel = 2
    if len(target_cards) < min_sel or len(target_cards) > max_sel:
        game.say(f"目标数量必须为 {min_sel}-{max_sel} 张")
        return "invalid"
    targets = target_cards[:max_sel]
    msgs = []
    if key == "c_magician":
        for c in targets: c.enhanced = "lucky"
        msgs.append("魔术师：变为幸运牌")
    elif key == "c_empress":
        for c in targets: c.enhanced = "mult"
        msgs.append("女皇：变为倍率牌")
    elif key == "c_heirophant":
        for c in targets: c.enhanced = "bonus"
        msgs.append("教皇：变为加分牌")
    elif key == "c_lovers":
        if targets: targets[0].enhanced = "wild"
        msgs.append("恋人：变为百搭牌")
    elif key == "c_chariot":
        if targets: targets[0].enhanced = "steel"
        msgs.append("战车：变为钢铁牌")
    elif key == "c_justice":
        if targets: targets[0].enhanced = "glass"
        msgs.append("正义：变为玻璃牌")
    elif key == "c_strength":
        bump = {2: "3", 3: "4", 4: "5", 5: "6", 6: "7", 7: "8", 8: "9", 9: "10",
                10: "J", 11: "Q", 12: "K", 13: "A", 14: "A"}
        for c in targets:
            c.rank = bump[rank_id(c.rank)]
        msgs.append("力量：点数 +1")
    elif key == "c_hanged_man":
        for c in targets:
            game.hand.remove(c)
            game.notify_destroyed(c)
        msgs.append(f"倒吊人：销毁 {len(targets)} 张牌")
    elif key == "c_death":
        right = targets[-1]
        for c in targets[:-1]:
            c.rank, c.suit, c.enhanced, c.edition, c.seal = right.rank, right.suit, right.enhanced, right.edition, right.seal
        msgs.append("死神：复制最右牌")
    elif key == "c_devil":
        if targets: targets[0].enhanced = "gold"
        msgs.append("恶魔：变为黄金牌")
    elif key == "c_tower":
        if targets: targets[0].enhanced = "stone"
        msgs.append("高塔：变为石头牌")
    elif key in ("c_star", "c_moon", "c_sun", "c_world"):
        conv = info["suit_conv"]
        for c in targets: c.suit = conv
        msgs.append(f"{info['cn']}：变为花色 {conv}")
    elif key == "c_talisman":
        if targets: targets[0].seal = "gold"
        msgs.append("护符：加上金色蜡封")
    elif key == "c_aura":
        if targets: targets[0].edition = game.rng.choice(["foil", "holo", "poly"])
        msgs.append("灵光：附加随机版本")
    elif key == "c_deja_vu":
        if targets: targets[0].seal = "red"
        msgs.append("似曾相识：加上红色蜡封")
    elif key == "c_trance":
        if targets: targets[0].seal = "blue"
        msgs.append("出神：加上蓝色蜡封")
    elif key == "c_medium":
        if targets: targets[0].seal = "purple"
        msgs.append("灵媒：加上紫色蜡封")
    elif key == "c_cryptid":
        if targets:
            c = targets[0]
            for _ in range(2):
                game.hand.append(c.copy())
            game.sort_hand()
        msgs.append("神秘生物：创建 2 张副本")
    else:
        msgs.append(f"未知消耗牌 {key}")

    mark_consumable_used(game, key)
    game.consumeables.remove(item)
    game.pending_consumable = None
    for m in msgs:
        game.say(m)
    return "done"


# ==========================================================================
# 标签应用
# ==========================================================================
def apply_tag(game, tag: Tag):
    from ..data import boosters as bd
    k = tag.key
    d = tag_data.TAGS.get(k, {})
    cn = d.get("cn", k)
    if k == "tag_uncommon":
        game.pending_shop_free_joker = "uncommon"
    elif k == "tag_rare":
        game.pending_shop_free_joker = "rare"
    elif k in ("tag_foil", "tag_holo", "tag_polychrome", "tag_negative"):
        pass  # 由 _make_joker_for_shop 处理
    elif k == "tag_investment":
        game.investment_tag_active = True
    elif k == "tag_voucher":
        game.pending_free_voucher = True
    elif k == "tag_boss":
        game.boss_key = game._get_new_boss()
        game.say(f"头目标签：重掷头目为 {blind_boss_cn(game)}")
    elif k in ("tag_standard", "tag_charm", "tag_meteor", "tag_buffoon", "tag_ethereal"):
        pk = {"tag_standard": "p_standard_mega", "tag_charm": "p_arcana_mega",
              "tag_meteor": "p_celestial_mega", "tag_buffoon": "p_buffoon_mega",
              "tag_ethereal": "p_spectral_normal"}[k]
        game.say(f"{cn}：开启 {bd.BOOSTERS[pk]['cn']}")
        game._open_pack_now(pk, free=True)
    elif k == "tag_handy":
        game.dollars += game.hands_left
        game.say(f"{cn}：+${game.hands_left}")
    elif k == "tag_garbage":
        game.dollars += game.discards_left
        game.say(f"{cn}：+${game.discards_left}")
    elif k == "tag_coupon":
        game.shop_free = True
    elif k == "tag_double":
        pass  # 复制下一个标签，由 Game.add_tag 在获得标签时处理
    elif k == "tag_juggle":
        game.hand_size += 3
    elif k == "tag_d_six":
        game.temp_reroll_cost = 0
    elif k == "tag_top_up":
        for _ in range(2):
            jk = centers_data.random_joker_key(game)
            if len(game.jokers) < game.joker_slots:
                cfg = centers_data.joker_cfg(jk)
                game.jokers.append(JokerItem(key=jk, buy_cost=cfg["cost"], sell_price=max(1, cfg["cost"] // 2)))
        game.say(f"{cn}：获得 2 张小丑")
    elif k == "tag_skip":
        game.dollars += 5 * game.skips
        game.say(f"{cn}：+${5 * game.skips}")
    elif k == "tag_orbital":
        h = game.rng.choice(list(game.hand_levels))
        game.hand_levels[h] += 3
        game.say(f"{cn}：{HAND_CN.get(h, h)} 等级 +3")
    elif k == "tag_economy":
        gain = min(game.dollars, 40)
        game.dollars += gain
        game.say(f"{cn}：+${gain}")
    else:
        game.say(f"应用标签：{cn}")


def blind_boss_cn(game) -> str:
    from ..data.blinds import get_blind_cfg
    if game.boss_key:
        return get_blind_cfg(game.boss_key)["cn"]
    return ""


# ==========================================================================
# 事件钩子（由 game.py 调用）
# ==========================================================================
def on_blind_select(game):
    """选中盲注时触发：被动成长/生成系小丑 + 每轮轮换目标。"""
    for j in list(game.jokers):
        if j.debuffed:
            continue
        k = j.key
        if k == "j_riff_raff":
            for _ in range(2):
                if len(game.jokers) < game.joker_slots:
                    jk = centers_data.random_joker_key(game, rarity=1)
                    cfg = centers_data.joker_cfg(jk)
                    game.jokers.append(JokerItem(key=jk, buy_cost=cfg["cost"], sell_price=max(1, cfg["cost"] // 2)))
                    game.say(f"乌合之众：获得 {cfg['cn']}")
        elif k == "j_marble":
            from .card import Card
            game.deck.add(Card(rank="A", suit="S", enhanced="stone", uid=0))
            game.hologram_count += 1
            game.say("大理石小丑：牌组 +1 石头牌")
        elif k == "j_ceremonial":
            idx = game.jokers.index(j)
            victims = [x for x in game.jokers[idx + 1:]]
            if victims:
                victim = victims[0]
                gain = victim.sell_value() * 2
                j.stat["mult"] = j.stat.get("mult", 0) + gain
                game.jokers.remove(victim)
                game.say(f"典礼匕首：销毁 {joker_cn(victim.key)}，+{gain} 倍率")
        elif k == "j_madness":
            j.stat["x_mult"] = j.stat.get("x_mult", 1.0) + 0.5
            others = [x for x in game.jokers if x is not j and not x.eternal]
            if others:
                victim = game.rng.choice(others)
                game.jokers.remove(victim)
                game.say("疯狂：+×0.5 倍率，销毁 1 张小丑")
        elif k == "j_cartomancer":
            game.gain_random_consumable_of("tarot")
            game.say("占卜师：生成塔罗牌")
        elif k == "j_burglar":
            game.hands_left += 3
            game.discards_left = 0
            game.say("盗贼：+3 手牌，失去全部弃牌")
        elif k == "j_certificate":
            game.hand.append(_random_card(game, seal=True))
            game.sort_hand()
            game.say("证书：随机蜡封牌入手")
        elif k == "j_turtle_bean":
            game.hand_size += 5
        elif k == "j_troubadour":
            game.hand_size += 2
            game.hands_left = max(1, game.hands_left - 1)
        elif k == "j_merry_andy":
            game.discards_left += 3
            game.hand_size = max(1, game.hand_size - 1)
        elif k == "j_juggler":
            game.hand_size += 1
        elif k == "j_drunkard":
            game.discards_left += 1
        elif k == "j_todo_list":
            j.stat["todo"] = game.rng.choice(list(HAND_ORDER))
        elif k == "j_ancient":
            j.stat["suit"] = game.rng.choice(SUITS)
        elif k == "j_idol":
            j.stat["card"] = (game.rng.choice(RANKS), game.rng.choice(SUITS))
        elif k == "j_mail":
            j.stat["rank"] = game.rng.choice(RANKS)
        elif k == "j_castle":
            j.stat["suit"] = game.rng.choice(SUITS)


def on_discard(game, discarded: List[Card]):
    """弃牌触发系小丑。discarded 为被弃的牌列表（已从手牌移除）。"""
    for j in list(game.jokers):
        if j.debuffed:
            continue
        k = j.key
        if k == "j_yorick":
            j.stat["discards"] = j.stat.get("discards", 0) + len(discarded)
        elif k == "j_hit_the_road":
            n = sum(1 for c in discarded if c.rank == "J")
            if n:
                j.stat["jacks"] = j.stat.get("jacks", 0) + n
        elif k == "j_ramen":
            j.stat["lost"] = j.stat.get("lost", 0.0) + 0.01 * len(discarded)
        elif k == "j_mail":
            if any(c.rank == j.stat.get("rank", "A") for c in discarded):
                game.dollars += 5
                game.say("邮寄回扣：+$5")
        elif k == "j_castle":
            suit = j.stat.get("suit", "S")
            n = sum(1 for c in discarded if c.is_suit(suit, smeared=game.any_joker("j_smeared")))
            if n:
                j.stat["chips"] = j.stat.get("chips", 0) + 3 * n
        elif k == "j_reserved_parking":
            faces = [c for c in game.hand if is_face_card(c, game)]
            for c in faces:
                if roll_prob(game, 2, "parking"):
                    game.dollars += 1
            if faces:
                game.say("预留车位：+$")
        elif k == "j_faceless":
            faces = [c for c in discarded if is_face_card(c, game)]
            if len(faces) >= 3:
                game.dollars += 5
                game.say("无脸小丑：+$5")
        elif k == "j_trading" and game.discards_used_round == 0 and len(discarded) == 1:
            c = discarded[0]
            # 牌此刻在 _round_cards，不在 deck.cards；须 notify_destroyed 标记销毁，回合结束才不会被回收（人头牌计入卡尼奥）
            game.notify_destroyed(c)
            game.dollars += 3
            game.say("交易卡：销毁该牌 +$3")
        elif k == "j_burnt" and game.discards_used_round == 0:
            name, _ = evaluate_poker_hand(
                discarded,
                four_fingers=game.any_joker("j_four_fingers"),
                shortcut=game.any_joker("j_shortcut"),
                smeared=game.any_joker("j_smeared"),
            )
            if name:
                game.hand_levels[name] += 1
                game.say(f"烧焦小丑：{HAND_CN.get(name, name)} 等级 +1")


def on_end_round(game, boss_beaten: bool = False):
    """回合结束时触发：成长/消亡/租金系小丑。"""
    for j in list(game.jokers):
        k = j.key
        if k == "j_egg":
            j.sell_price += 3
        elif k == "j_gift":
            for x in game.jokers:
                x.sell_price += 1
            for x in game.consumeables:
                x.sell_price += 1
        elif k == "j_rocket":
            j.stat["dollars"] = j.stat.get("dollars", 1) + (2 if boss_beaten else 1)
        elif k == "j_gros_michel":
            if game.rng.chance(6, "gros"):
                game.jokers.remove(j)
                game.say("格罗斯米歇尔碎了！")
        elif k == "j_cavendish":
            if game.rng.chance(1000, "cav"):
                game.jokers.remove(j)
                game.say("卡文迪许消失了！")
        elif k == "j_turtle_bean":
            game.hand_size = max(1, game.hand_size - 1)
        if j.rental and not j.eternal:
            cost = j.sell_value()
            game.dollars = max(0, game.dollars - cost)
            game.say(f"租用小丑 {joker_cn(k)}：-${cost}")
        if j.perishable and not j.eternal:
            j.perish_tally -= 1
            if j.perish_tally <= 0:
                game.jokers.remove(j)
                game.say(f"{joker_cn(k)} 已过期消失")


def on_shop_closed(game):
    """离开商店时触发。"""
    for j in list(game.jokers):
        k = j.key
        if k == "j_red_card":
            n = len(game.shop_boosters)
            if n:
                j.stat["mult"] = j.stat.get("mult", 0) + 3 * n
                game.say(f"红卡：跳过 {n} 个卡包 +{3 * n} 倍率")
        elif k == "j_perkeo":
            if game.consumeables:
                c = game.rng.choice(game.consumeables)
                game.consumeables.append(ConsumableItem(key=c.key, edition="negative",
                                                        buy_cost=c.buy_cost, sell_price=c.sell_price))
                game.say("珀可：复制 1 张消耗牌（负片）")


def on_reroll(game):
    for j in game.jokers:
        if j.key == "j_flash":
            j.stat["mult"] = j.stat.get("mult", 0) + 2
