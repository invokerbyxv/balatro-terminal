"""小丑的记分效果表（对应 Lua card.lua 各小丑的 calculate_joker 分支）。

每个 ``fx_*`` 接收 (game, joker, ctx)，返回 :class:`~.scoring.Effect` 列表。
``ctx.phase`` 决定该效果在记分管线哪个阶段生效：
before / individual / joker_main / other_joker / repetition / after。

按需在 effects 里重导出，保持 ``effects.JOKER_FX`` 的导入路径不变。
"""
from __future__ import annotations

from typing import List

from .scoring import Effect, Ctx
from .items import JokerItem
from .card import Card, rank_id, rank_value
from .hand_eval import HAND_CN
from ..data import centers as centers_data
from .lookup import roll_prob


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


def is_face_card(card: Card, game, from_boss: bool = False) -> bool:
    """这张牌此刻是否算人头牌（叠加幻视 Pareidolia）。

    对应 card.lua 的 ``Card:is_face(from_boss)``：被禁用的牌先返回 false
    （``from_boss=True`` 时跳过这一步，供头目自己判断要不要禁用），然后才是
    ``id == 11/12/13`` 或持有幻视。石头牌 ``get_id()`` 为负，自然不算。
    """
    if card.debuffed and not from_boss:
        return False
    if game.any_joker("j_pareidolia"):
        return True
    return card.is_face(from_boss=from_boss)

def calculate_joker(game, joker: JokerItem, ctx: Ctx) -> List[Effect]:
    fn = JOKER_FX.get(joker.key)
    if fn is None:
        return []
    return fn(game, joker, ctx)


def _joker_index(game, joker) -> int:
    """小丑在序列中的位置，找不到返回 -1。

    用 is 比较：JokerItem 是 dataclass，== 按字段相等匹配，会把同款的另一张
    小丑（例如并排的两张蓝图）认成自己。
    """
    for i, x in enumerate(game.jokers):
        if x is joker:
            return i
    return -1


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
    """模具小丑：空槽数 + 模具小丑自身数量（card.lua 4203-4207）。"""
    if ctx.phase != "joker_main":
        return []
    empty = game.joker_slots - len(game.jokers)
    n = empty + game.count_jokers("j_stencil")
    if n >= 1:
        return [_E(x_mult=float(n))]
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


def lowest_held_card(game) -> Card | None:
    """致胜之拳锁定的那张手牌：点数最低的非石头牌（并列取靠后的一张）。

    对应 card.lua 3320-3325 的循环：``temp_ID >= base.id`` 用「大于等于」，
    因此并列时会选中后面那张；石头牌被 ``ability.effect ~= 'Stone Card'`` 排除。
    """
    lowest = None
    for c in game.hand:
        if c.enhanced == "stone":
            continue
        if lowest is None or c.get_id() <= lowest.get_id():
            lowest = c
    return lowest


def fx_j_raised_fist(game, j, ctx):
    """致胜之拳：只对**手里点数最低的那张牌**生效一次；A=11、J/Q/K=10（card.lua 3320-3340）。"""
    if ctx.phase != "individual" or not ctx.hand_being_evaluated or ctx.other_card is None:
        return []
    target = lowest_held_card(game)
    if target is None or target is not ctx.other_card:
        return []
    if target.debuffed:
        return []
    return [_E(mult=2 * rank_value(target.rank))]


def fx_j_scary_face(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game):
            return [_E(chips=30)]
    return []


def fx_j_abstract(game, j, ctx):
    """抽象小丑：统计**所有**小丑，包括自己（card.lua 的计数循环）。"""
    if ctx.phase == "joker_main":
        return [_E(mult=3 * len(game.jokers))]
    return []


def fx_j_reserved_parking(game, j, ctx):
    """预留车位：每张**手持**人头牌在计分时各有 1/2 概率 +$1（card.lua 3302-3319）。"""
    if ctx.phase != "individual" or not ctx.hand_being_evaluated or ctx.other_card is None:
        return []
    c = ctx.other_card
    if not c.is_face() or c.debuffed:
        return []
    if roll_prob(game, 2, "parking"):
        return [_E(dollars=1)]
    return []


def fx_j_even_steven(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        rid = ctx.other_card.get_id()
        if rid in (2, 4, 6, 8, 10):
            return [_E(mult=4)]
    return []


def fx_j_odd_todd(game, j, ctx):
    """奇数托德：只对 3/5/7/9/A（id 3/5/7/9/14）生效，J 的 id 是 11 因此不触发。"""
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        rid = ctx.other_card.get_id()
        if rid in (3, 5, 7, 9, 14):
            return [_E(chips=31)]
    return []


def fx_j_scholar(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.get_id() == 14:
            return [_E(chips=20, mult=4)]
    return []


def fx_j_fibonacci(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        rid = ctx.other_card.get_id()
        if rid in (14, 2, 3, 5, 8):
            return [_E(mult=8)]
    return []


def fx_j_supernova(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=game.hands_count.get(ctx.scoring_name, 0))]
    return []


def fx_j_runner(game, j, ctx):
    if ctx.blueprint:
        return []
    if ctx.phase == "joker_main":
        if contains_hand(ctx.scoring_name, "Straight"):
            j.stat["chips"] = j.stat.get("chips", 0) + 15
        return [_E(chips=j.stat.get("chips", 0))]
    return []


def fx_j_ice_cream(game, j, ctx):
    if ctx.blueprint:
        return []
    """冰淇淋：本次计分先按当前筹码给分，计分后 -5；降到 0 时销毁（card.lua 3571-3599）。"""
    if ctx.phase == "joker_main":
        return [_E(chips=j.stat.get("chips", 100))]
    if ctx.phase == "after":
        left = j.stat.get("chips", 100) - 5
        if left <= 0:
            if j in game.jokers:
                game.jokers.remove(j)
            return [_E(message="冰淇淋融化了！")]
        j.stat["chips"] = left
    return []


def fx_j_blue_joker(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(chips=game.deck.count() * 2)]
    return []


def fx_j_green_joker(game, j, ctx):
    if ctx.blueprint:
        return []
    """绿色小丑：每打一手**前** +1，每弃一次牌 -1（card.lua 2846、3563-3569）。"""
    if ctx.phase == "before":
        j.stat["mult"] = j.stat.get("mult", 0) + 1
    elif ctx.phase == "joker_main":
        return [_E(mult=j.stat.get("mult", 0))]
    return []


def fx_j_todo_list(game, j, ctx):
    if ctx.phase == "joker_main" and ctx.scoring_name == j.stat.get("todo", "High Card"):
        return [_E(dollars=4)]
    return []


def fx_j_square(game, j, ctx):
    if ctx.blueprint:
        return []
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
    """爆米花：每**回合** -4（end_of_round 里扣），降到 0 销毁；本手只读当前值。"""
    if ctx.phase == "joker_main":
        return [_E(mult=j.stat.get("mult", 20))]
    return []


def fx_j_ramen(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, j.stat.get("x_mult", 2.0)))]
    return []


def fx_j_trousers(game, j, ctx):
    if ctx.blueprint:
        return []
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
        if ctx.other_card.get_id() == 12 and not ctx.other_card.debuffed:
            return [_E(mult=13)]
    return []


def fx_j_smiley(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if is_face_card(ctx.other_card, game):
            return [_E(mult=5)]
    return []


def fx_j_walkie_talkie(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.get_id() in (10, 4):
            return [_E(chips=10, mult=4)]
    return []


def fx_j_stone(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for c in game.all_playing_cards() if c.enhanced == "stone")
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
    if ctx.blueprint:
        return []
    """苏打水：接下来 10 手内所有打出的牌重触发一次，用尽后销毁（card.lua 3601-3630）。"""
    if ctx.phase == "repetition" and ctx.other_card and not ctx.hand_being_evaluated:
        if j.stat.get("uses", 10) > 0:
            return [_E(repetitions=1)]
    if ctx.phase == "after":
        left = j.stat.get("uses", 10) - 1
        if left <= 0:
            if j in game.jokers:
                game.jokers.remove(j)
            return [_E(message="苏打水喝完了！")]
        j.stat["uses"] = left
    return []


def fx_j_card_sharp(game, j, ctx):
    if ctx.phase == "joker_main":
        if game.round_hand_played.count(ctx.scoring_name) >= 2:
            return [_E(x_mult=3)]
    return []


def fx_j_photograph(game, j, ctx):
    """照片：计分手牌里**第一张人头牌** ×2（不要求它同时是第一张计分牌）。"""
    if ctx.phase != "individual" or ctx.hand_being_evaluated or ctx.other_card is None:
        return []
    first_face = next((c for c in ctx.scoring_cards if is_face_card(c, game)), None)
    if first_face is not None and ctx.other_card is first_face:
        return [_E(x_mult=2)]
    return []


def fx_j_triboulet(game, j, ctx):
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.get_id() in (13, 12):
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
    """重影：逐花色精确计数（card.lua 3840-3872）。

    非百搭牌按 ``is_suit(suit)`` 计（受 debuff 影响），百搭牌只补「还没计到的
    花色」，顺序为 ♣ → ♦ → ♠ → ♥；条件是有梅花且还有其他任一花色。
    """
    if ctx.phase != "joker_main":
        return []
    smeared = game.any_joker("j_smeared")
    suits = {"H": 0, "D": 0, "S": 0, "C": 0}
    for c in ctx.scoring_cards:
        if c.enhanced == "wild":
            continue
        for s in ("H", "D", "S", "C"):
            if c.is_suit(s, smeared=smeared):
                suits[s] += 1
    for c in ctx.scoring_cards:
        if c.enhanced != "wild":
            continue
        for s in ("C", "D", "S", "H"):
            if c.is_suit(s, smeared=smeared) and suits[s] == 0:
                suits[s] += 1
                break
    if suits["C"] > 0 and (suits["H"] > 0 or suits["D"] > 0 or suits["S"] > 0):
        return [_E(x_mult=2)]
    return []


def fx_j_flower_pot(game, j, ctx):
    """花盆：四种花色齐全时 ×3；非百搭牌用 ``bypass_debuff`` 计花色（card.lua 3807-3838）。"""
    if ctx.phase != "joker_main":
        return []
    smeared = game.any_joker("j_smeared")
    suits = {"H": 0, "D": 0, "S": 0, "C": 0}
    for c in ctx.scoring_cards:
        if c.enhanced == "wild":
            continue
        for s in ("H", "D", "S", "C"):
            if c.is_suit(s, bypass_debuff=True, smeared=smeared) and suits[s] == 0:
                suits[s] += 1
                break
    for c in ctx.scoring_cards:
        if c.enhanced != "wild":
            continue
        for s in ("H", "D", "S", "C"):
            if c.is_suit(s, smeared=smeared) and suits[s] == 0:
                suits[s] += 1
                break
    if all(suits.values()):
        return [_E(x_mult=3)]
    return []


def fx_j_blackboard(game, j, ctx):
    """黑板：手持全是黑桃/梅花时 ×3；原版用 ``is_suit(suit, nil, true)``（flush_calc）。"""
    if ctx.phase == "joker_main":
        smeared = game.any_joker("j_smeared")
        if all(c.is_suit("S", flush_calc=True, smeared=smeared)
               or c.is_suit("C", flush_calc=True, smeared=smeared)
               for c in game.hand):
            return [_E(x_mult=3)]
    return []


def fx_j_baron(game, j, ctx):
    if ctx.phase == "individual" and ctx.hand_being_evaluated and ctx.other_card:
        if ctx.other_card.get_id() == 13 and not ctx.other_card.debuffed:
            return [_E(x_mult=1.5)]
    return []


def fx_j_steel_joker(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for c in game.all_playing_cards() if c.enhanced == "steel")
        return [_E(x_mult=max(1.0, 1.0 + 0.2 * n))]
    return []


def fx_j_drivers_license(game, j, ctx):
    if ctx.phase == "joker_main":
        n = sum(1 for c in game.all_playing_cards() if c.enhanced)
        if n >= 16:
            return [_E(x_mult=3)]
    return []


def fx_j_erosion(game, j, ctx):
    """侵蚀：起始牌组张数 − 当前全牌组张数（含手牌/出牌区/弃牌堆）。"""
    if ctx.phase == "joker_main":
        below = game.starting_deck_size - len(game.all_playing_cards())
        if below > 0:
            return [_E(mult=4 * below)]
    return []


def fx_j_throwback(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(x_mult=max(1.0, 1.0 + 0.25 * game.skips))]
    return []


def fx_j_ride_the_bus(game, j, ctx):
    if ctx.blueprint:
        return []
    """搭乘巴士：计分**前**结算——本手有计分人头牌则清零，否则 +1；当前手立刻享受新值。"""
    if ctx.phase == "before":
        if any(is_face_card(c, game) for c in ctx.scoring_cards):
            j.stat["mult"] = 0
        else:
            j.stat["mult"] = j.stat.get("mult", 0) + 1
    elif ctx.phase == "joker_main":
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
    if ctx.blueprint:
        return []
    """方尖石塔：只有本手牌型**严格多于**其他所有可见牌型时才重置（card.lua 3543-3561）。"""
    if ctx.phase == "before":
        mine = game.hands_count.get(ctx.scoring_name, 0)
        others = [h for h in game.visible_hands() if h != ctx.scoring_name]
        reset = all(game.hands_count.get(h, 0) < mine for h in others)
        if reset:
            j.stat["x_mult"] = 1.0
        else:
            j.stat["x_mult"] = j.stat.get("x_mult", 1.0) + 0.2
    elif ctx.phase == "joker_main":
        return [_E(x_mult=j.stat.get("x_mult", 1.0))]
    return []


def fx_j_wee(game, j, ctx):
    if ctx.blueprint:
        return []
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        if ctx.other_card.get_id() == 2:
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
    """积分卡：从**获得这张小丑起**每 5 手触发一次 ×4（card.lua 3632-3651）。

    原版用 ``hands_played_at_create`` 记录获得时的手数，剩余 = (4 - delta) mod 6，
    因此 delta ≡ 5 (mod 6) 时触发，即获得后的第 5、11、17… 手。
    """
    if ctx.phase == "before":
        j.stat["hands"] = j.stat.get("hands", 0) + 1
    elif ctx.phase == "joker_main":
        if j.stat.get("hands", 0) % 6 == 5:
            return [_E(x_mult=4)]
    return []


def fx_j_mr_bones(game, j, ctx):
    return []


def fx_j_hallucination(game, j, ctx):
    # 开包时触发（packs.py 的 open_booster），记分阶段无效果
    return []


def fx_j_chaos(game, j, ctx):
    # 商店免费重掷在 shop.py 的 free_rerolls 里实时推导
    return []


def fx_j_matador(game, j, ctx):
    """斗牛士：头目能力触发（使这手不计分）时 +$8（card.lua 2735-2747）。"""
    if ctx.phase == "debuffed_hand":
        return [_E(dollars=8, message="斗牛士：+$8")]
    return []


def fx_j_campfire(game, j, ctx):
    if ctx.blueprint:
        return []
    """篝火：每卖出一张牌 +×0.25（selling_card），击败头目后重置为 ×1。"""
    if ctx.phase == "joker_main":
        return [_E(x_mult=j.stat.get("x_mult", 1.0))]
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
    if ctx.blueprint:
        return []
    """太空小丑：在 **before** 阶段升级本手牌型，当前手立即受益（card.lua 3420-3426）。"""
    if ctx.phase == "before":
        if roll_prob(game, 4, "space"):
            game.hand_levels[ctx.scoring_name] += 1
            return [_E(message=f"太空小丑：{HAND_CN.get(ctx.scoring_name, ctx.scoring_name)} 等级+1")]
    return []


def fx_j_sixth_sense(game, j, ctx):
    if ctx.phase == "joker_main" and game.hands_played_round == 1:
        if len(ctx.played_cards) == 1 and ctx.played_cards[0].get_id() == 6:
            card = ctx.played_cards[0]
            game.notify_destroyed(card)
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
        if ctx.other_card.get_id() == 8 and roll_prob(game, 4, "8ball"):
            game.gain_random_consumable_of("tarot")
            return [_E(message="八号球：生成塔罗牌")]
    return []


def fx_j_vagabond(game, j, ctx):
    if ctx.phase == "after" and game.dollars <= 4:
        game.gain_random_consumable_of("tarot")
        return [_E(message="流浪汉：生成塔罗牌")]
    return []


def fx_j_hiker(game, j, ctx):
    if ctx.blueprint:
        return []
    if ctx.phase == "individual" and ctx.other_card and not ctx.hand_being_evaluated:
        game.card_chip_extra[id(ctx.other_card)] = game.card_chip_extra.get(id(ctx.other_card), 0) + 5
    return []


def fx_j_fortune_teller(game, j, ctx):
    if ctx.phase == "joker_main":
        return [_E(mult=game.tarots_used)]
    return []


def fx_j_blueprint(game, j, ctx):
    idx = _joker_index(game, j)
    if not 0 <= idx < len(game.jokers) - 1:
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
    "j_reserved_parking": fx_j_reserved_parking,
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
    "j_hallucination": fx_j_hallucination, "j_chaos": fx_j_chaos,
    "j_matador": fx_j_matador, "j_campfire": fx_j_campfire,
    "j_blueprint": fx_j_blueprint, "j_brainstorm": fx_j_brainstorm,
}
