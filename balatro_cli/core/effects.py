from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

from .items import JokerItem, ConsumableItem, Tag
from .card import Card, rank_id, rank_value, RANKS, SUITS, SUIT_CN
from .hand_eval import HAND_ORDER, HAND_CN, evaluate_poker_hand
from ..data import centers as centers_data
from ..data import consumables as consumable_data
from ..data import tags as tag_data
from ..data import blinds as blind_data
from .lookup import guaranteed_edition, joker_cn, roll_prob
from .joker_fx import JOKER_FX, _joker_index, calculate_joker, is_face_card




# ==========================================================================
# 动态小丑：当前已生效效果（只读实时预览，供 UI 显示）
# ==========================================================================
def _fmt_x(v: float) -> str:
    """把 x_mult 数值渲染成紧凑形式：×1 → ×1.25 → ×1.5。"""
    if abs(v - round(v)) < 1e-9:
        return f"×{int(round(v))}"
    return f"×{f'{v:.2f}'.rstrip('0').rstrip('.')}"


def _le_yorick(game, j):
    stat = j.stat
    n = stat.get("discards", 0) // 23
    return f"{_fmt_x(1.0 + n)}(弃{stat.get('discards', 0)}/{(n + 1) * 23})"


def _le_caino(game, j):
    return _fmt_x(1.0 + game.face_destroyed)


def _le_hologram(game, j):
    return _fmt_x(1.0 + 0.25 * game.hologram_count)


def _le_glass(game, j):
    return _fmt_x(1.0 + 0.75 * game.glass_broken)


def _le_hit_the_road(game, j):
    return _fmt_x(max(1.0, 1.0 + 0.5 * j.stat.get("jacks", 0)))


def _le_constellation(game, j):
    return _fmt_x(1.0 + 0.1 * game.constellation_count)


def _le_lucky_cat(game, j):
    return _fmt_x(1.0 + 0.25 * game.lucky_triggers)


def _le_throwback(game, j):
    return _fmt_x(1.0 + 0.25 * game.skips)


def _count_enhanced(game, kind=None):
    """统计全牌组（含手牌/出牌区/弃牌堆）的增强牌数；kind 为 None 时统计任意增强。"""
    def match(c):
        return bool(c.enhanced) if kind is None else c.enhanced == kind
    return sum(1 for c in game.all_playing_cards() if match(c))


def _le_steel_joker(game, j):
    return _fmt_x(1.0 + 0.2 * _count_enhanced(game, "steel"))


def _le_baseball(game, j):
    n = sum(1 for oj in game.jokers
            if centers_data.JOKERS.get(oj.key, {}).get("r") == 2)
    return _fmt_x(1.0 + 1.5 * n)


def _le_stencil(game, j):
    n = game.joker_slots - len(game.jokers) + game.count_jokers("j_stencil")
    return _fmt_x(float(n)) if n >= 1 else "无生效"


def _le_drivers_license(game, j):
    n = _count_enhanced(game)
    return "×3" if n >= 16 else f"未激活({n}/16)"


def _le_ramen(game, j):
    return _fmt_x(max(1.0, 2.0 - j.stat.get("lost", 0.0)))


def _le_todo_list(game, j):
    t = j.stat.get("todo", "High Card")
    return f"目标{HAND_CN.get(t, t)}"


def _le_ancient(game, j):
    suit = j.stat.get("suit", "S")
    return f"花色{SUIT_CN.get(suit, suit)}"


def _le_idol(game, j):
    r, s = j.stat.get("card", ("A", "H"))
    return f"{r}{SUIT_CN.get(s, s)}"


def _le_mail(game, j):
    return f"目标{j.stat.get('rank', 'A')}"


def _le_luchador(game, j):
    # 对应原版卡面的 ACTIVE / NO BOSS ACTIVE
    if game.boss_disabled():
        return "已禁用当前盲注"
    return "可禁用" if game.current_blind_key() in blind_data.BOSS_BLINDS else "无头目生效"


#: 隐形小丑需要的回合数（card.lua 的 config.extra = 2）
_INVISIBLE_ROUNDS = 2


def _le_invisible(game, j):
    # 对应原版卡面底部的「(当前为 N/2)」，满 2 轮后显示 ACTIVE
    n = j.stat.get("invis_rounds", 0)
    return "可复制" if n >= _INVISIBLE_ROUNDS else f"{n}/{_INVISIBLE_ROUNDS}"


def _le_blue_joker(game, j):
    return f"+{game.deck.count() * 2}筹码"


def _le_bull(game, j):
    return f"+{game.dollars * 2}筹码"


def _le_stone(game, j):
    return f"+{_count_enhanced(game, 'stone') * 25}筹码"


def _le_banner(game, j):
    return f"+{game.discards_left * 30}筹码"


def _le_abstract(game, j):
    return f"+{3 * len(game.jokers)}倍率"


def _le_swashbuckler(game, j):
    total = sum(oj.sell_value() for oj in game.jokers if oj is not j)
    return f"+{total}倍率"


def _le_bootstraps(game, j):
    return f"+{(game.dollars // 5) * 2}倍率"


def _le_fortune_teller(game, j):
    return f"+{game.tarots_used}倍率"


def _le_mystic_summit(game, j):
    return "+15倍率" if game.discards_left == 0 else "未激活"


def _le_erosion(game, j):
    below = game.starting_deck_size - len(game.all_playing_cards())
    return f"+{4 * below}倍率" if below > 0 else ""


def _le_campfire(game, j):
    return _fmt_x(j.stat.get("x_mult", 1.0))


def _le_raised_fist(game, j):
    held = [c for c in game.hand if c.enhanced != "stone"]
    if not held:
        return ""
    lowest = None
    for c in held:
        if lowest is None or c.get_id() <= lowest.get_id():
            lowest = c
    if lowest is None or lowest.debuffed:
        return ""
    return f"+{2 * rank_value(lowest.rank)}倍率"


#: 小丑 key -> 实时效果文案（供 UI 预览；未登记的不显示附加信息）
_LIVE_EFFECTS = {
    "j_yorick": _le_yorick, "j_caino": _le_caino, "j_hologram": _le_hologram,
    "j_glass": _le_glass, "j_hit_the_road": _le_hit_the_road,
    "j_constellation": _le_constellation, "j_lucky_cat": _le_lucky_cat,
    "j_throwback": _le_throwback, "j_steel_joker": _le_steel_joker,
    "j_baseball": _le_baseball, "j_stencil": _le_stencil,
    "j_drivers_license": _le_drivers_license, "j_ramen": _le_ramen,
    "j_todo_list": _le_todo_list, "j_ancient": _le_ancient,
    "j_idol": _le_idol, "j_mail": _le_mail, "j_luchador": _le_luchador,
    "j_invisible": _le_invisible,
    "j_blue_joker": _le_blue_joker, "j_bull": _le_bull, "j_stone": _le_stone,
    "j_banner": _le_banner, "j_abstract": _le_abstract,
    "j_swashbuckler": _le_swashbuckler, "j_bootstraps": _le_bootstraps,
    "j_fortune_teller": _le_fortune_teller,
    "j_mystic_summit": _le_mystic_summit, "j_erosion": _le_erosion,
    "j_raised_fist": _le_raised_fist,
    "j_campfire": _le_campfire,
}


def joker_live_effect(game, j) -> str:
    handler = _LIVE_EFFECTS.get(j.key)
    return handler(game, j) if handler else ""


#: 小丑 key -> 每轮结算时额外给的钱（对应 card.lua calculate_dollar_bonus）
def _db_golden(game, joker):
    return 4


def _db_cloud_9(game, joker):
    """9霄云外：统计**全牌组**（含手牌 / 出牌区 / 弃牌堆）的 9（card.lua 4191-4195）。"""
    return sum(1 for c in game.all_playing_cards() if c.get_id() == 9)


def _db_rocket(game, joker):
    return joker.stat.get("dollars", 1)


def _db_satellite(game, joker):
    return len(game.planets_used)


def _db_delayed_grat(game, joker):
    return game.discards_left * 2 if game.discards_used_round == 0 else 0


_DOLLAR_BONUS = {
    "j_golden": _db_golden,
    "j_cloud_9": _db_cloud_9,
    "j_rocket": _db_rocket,
    "j_satellite": _db_satellite,
    "j_delayed_grat": _db_delayed_grat,
}


def joker_dollar_bonus(game, joker: JokerItem) -> int:
    handler = _DOLLAR_BONUS.get(joker.key)
    return handler(game, joker) if handler else 0


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


# ----------------------------------------------------------------------
# 消耗牌：无目标效果
#
# 每个 handler 接收 (game, item) 并返回 "done"；需要从手牌选目标的一律落到
# needs_target，由 UI 收集目标后交给 finish_consumable_target；没有可用目标时
# 返回 "invalid" 且不移除 item（对应原版 can_use_consumeable 禁用该牌）。
# 移除 item 的时机刻意与原实现逐条保持一致：部分效果（女祭司/皇帝、
# 愚者）在判定栏位时依赖 item 是否还在 consumeables 里。
# ----------------------------------------------------------------------
def _use_fool(game, item):
    last = game.last_tarot_planet
    if last and last != "c_fool" and last in consumable_data.ALL_CONSUMABLES:
        info = consumable_data.ALL_CONSUMABLES[last]
        if len(game.consumeables) < game.consumable_slots:
            game.consumeables.append(ConsumableItem(key=last))
            game.say(f"愚者：生成 {consumable_data.get_consumable_cn(last)}")
        else:
            game.say("愚者：消耗品栏已满")
    else:
        game.say("愚者：没有可复制的牌")
    game.consumeables.remove(item)
    return "done"


def _use_high_priestess(game, item):
    game.consumeables.remove(item)
    for _ in range(2):
        game.gain_consumable(game.rng.choice(list(consumable_data.PLANETS)))
    game.say("女祭司：生成 2 张星球牌")
    return "done"


def _use_emperor(game, item):
    game.consumeables.remove(item)
    for _ in range(2):
        game.gain_consumable(game.rng.choice(list(consumable_data.TAROTS)))
    game.say("皇帝：生成 2 张塔罗牌")
    return "done"


def _use_hermit(game, item):
    gain = min(game.dollars, 20)
    game.dollars += gain
    game.say(f"隐者：金钱翻倍 +${gain}")
    game.consumeables.remove(item)
    return "done"


def _use_temperance(game, item):
    gain = min(sum(j.sell_value() for j in game.jokers), 50)
    game.dollars += gain
    game.say(f"节制：+${gain}")
    game.consumeables.remove(item)
    return "done"


def _editionless_jokers(game) -> List[JokerItem]:
    """可附加版本的小丑：镜像 card.lua 的 ``eligible_*_jokers``（4209-4224）。

    原版把「没有任何版本」的小丑单独收集起来给命运之轮 / 灵质 / 诅咒挑选，
    因此已经有版本（箔片 / 全息 / 彩绘 / 负片）的小丑不会被再次附加，也不会
    丢掉原来那个版本。
    """
    return [j for j in game.jokers if j.edition is None]


def _use_wheel_of_fortune(game, item):
    pool = _editionless_jokers(game)
    if not pool:
        # 原版在没有候选小丑时由 can_use_consumeable 直接禁用这张塔罗
        # （card.lua 1533-1535），这里同样不消耗它，免得白白浪费一张牌。
        game.say("命运之轮：没有可附加版本的小丑（未消耗）" if game.jokers
                 else "命运之轮：没有小丑牌（未消耗）")
        return "invalid"
    if roll_prob(game, 4, "wheel"):
        j = game.rng.choice(pool)
        j.edition = guaranteed_edition(game, "wheel_of_fortune")
        game.say(f"命运之轮：{joker_cn(j.key)} 获得版本 {j.edition}！")
    else:
        game.say("命运之轮：NOPE！")
    game.consumeables.remove(item)
    return "done"


def _gain_joker_from_pack(game, jk, empty_msg, got):
    """审判/魅影/灵魂共用：小丑栏满则提示，否则获得并播报。"""
    if len(game.jokers) >= game.joker_slots:
        game.say(empty_msg)
        return
    cfg = centers_data.joker_cfg(jk)
    game.jokers.append(JokerItem(key=jk))
    game.say(got.format(cn=cfg["cn"]))


def _use_judgement(game, item):
    _gain_joker_from_pack(game, centers_data.random_joker_key(game),
                          "审判：小丑栏已满", "审判：获得小丑 {cn}")
    game.consumeables.remove(item)
    return "done"


def _use_wraith(game, item):
    _gain_joker_from_pack(game, centers_data.random_joker_key(game, rarity=3),
                          "魅影：小丑栏已满", "魅影：获得稀有小丑 {cn}")
    game.dollars = 0
    game.consumeables.remove(item)
    return "done"


def _use_soul(game, item):
    _gain_joker_from_pack(game, centers_data.random_joker_key(game, rarity=4),
                          "灵魂：小丑栏已满", "灵魂：获得传说小丑 {cn}！")
    game.consumeables.remove(item)
    return "done"


def _use_immolate(game, item):
    n = min(5, len(game.hand))
    for c in game.rng.sample(game.hand, n):
        game.notify_destroyed(c)
    game.dollars += 20
    game.say(f"献祭：销毁 {n} 张手牌，+$20")
    game.consumeables.remove(item)
    return "done"


def _use_black_hole(game, item):
    for h in game.hand_levels:
        game.hand_levels[h] += 1
    game.say("黑洞：所有手牌类型等级 +1")
    game.consumeables.remove(item)
    return "done"


def _summon_hand(game, count, msg, **card_kwargs):
    """眷属/阴森/咒文共用：先销毁 1 张随机手牌，再生成 count 张随机牌。"""
    _destroy_random_hand(game, 1)
    for _ in range(count):
        game.hand.append(_random_card(game, **card_kwargs))
    game.sort_hand()
    game.say(msg)


def _use_familiar(game, item):
    _summon_hand(game, 3, "眷属：销毁 1 张手牌，生成 3 张人头", face=True)
    game.consumeables.remove(item)
    return "done"


def _use_grim(game, item):
    _summon_hand(game, 2, "阴森：销毁 1 张手牌，生成 2 张增强 A",
                 rank="A", enhanced="bonus")
    game.consumeables.remove(item)
    return "done"


def _use_incantation(game, item):
    _summon_hand(game, 4, "咒文：销毁 1 张手牌，生成 4 张增强数字牌",
                 number=True, enhanced="bonus")
    game.consumeables.remove(item)
    return "done"


def _use_sigil(game, item):
    suit = game.rng.choice(SUITS)
    for c in game.hand:
        c.suit = suit
    game.sort_hand()
    game.say(f"纹章：所有手牌变成 {suit}")
    game.consumeables.remove(item)
    return "done"


def _use_ouija(game, item):
    rank = game.rng.choice(RANKS)
    for c in game.hand:
        c.rank = rank
    game.change_hand_size(-1)
    game.say(f"灵应盘：所有手牌变成 {rank}，手牌上限 -1")
    game.consumeables.remove(item)
    return "done"


def _use_ectoplasm(game, item):
    pool = _editionless_jokers(game)
    if not pool:
        # 原版 can_use_consumeable 在没有候选小丑时禁用这张幻灵（card.lua 1547-1548），
        # 所以「手牌上限 -1」也不会发生。
        game.say("灵质：没有可附加版本的小丑（未消耗）" if game.jokers
                 else "灵质：没有小丑牌（未消耗）")
        return "invalid"
    j = game.rng.choice(pool)
    j.edition = "negative"
    game.say(f"灵质：{joker_cn(j.key)} 获得负片版本")
    game.change_hand_size(-1)
    game.say("灵质：手牌上限 -1")
    game.consumeables.remove(item)
    return "done"


def _use_ankh(game, item):
    if game.jokers:
        keep = game.rng.choice(game.jokers)
        for v in list(game.jokers):
            if v is not keep and not v.eternal:
                game.jokers.remove(v)
        if len(game.jokers) < game.joker_slots or keep.negative:
            game.jokers.append(JokerItem(key=keep.key, edition=keep.edition,
                                         buy_cost=keep.buy_cost, extra_value=keep.extra_value,
                                         stat=dict(keep.stat)))
        game.say("安卡：销毁其他小丑，复制 1 张")
    game.consumeables.remove(item)
    return "done"


def _use_hex(game, item):
    pool = _editionless_jokers(game)
    if not pool:
        # 同上：没有候选小丑时原版禁用这张幻灵（card.lua 1547-1548），其他小丑也不会被销毁。
        game.say("诅咒：没有可附加版本的小丑（未消耗）" if game.jokers
                 else "诅咒：没有小丑牌（未消耗）")
        return "invalid"
    j = game.rng.choice(pool)
    j.edition = "polychrome"
    game.say(f"诅咒：{joker_cn(j.key)} 获得彩绘版本")
    for v in list(game.jokers):
        if v is not j and not v.eternal:
            game.jokers.remove(v)
    game.consumeables.remove(item)
    return "done"


#: 无目标消耗牌 key -> handler。不在表里的走 needs_target（需要选手牌目标）。
_NO_TARGET_CONSUMABLES = {
    "c_fool": _use_fool,
    "c_high_priestess": _use_high_priestess,
    "c_emperor": _use_emperor,
    "c_hermit": _use_hermit,
    "c_temperance": _use_temperance,
    "c_wheel_of_fortune": _use_wheel_of_fortune,
    "c_judgement": _use_judgement,
    "c_wraith": _use_wraith,
    "c_soul": _use_soul,
    "c_immolate": _use_immolate,
    "c_black_hole": _use_black_hole,
    "c_familiar": _use_familiar,
    "c_grim": _use_grim,
    "c_incantation": _use_incantation,
    "c_sigil": _use_sigil,
    "c_ouija": _use_ouija,
    "c_ectoplasm": _use_ectoplasm,
    "c_ankh": _use_ankh,
    "c_hex": _use_hex,
}


def _apply_consumable(game, item: ConsumableItem) -> str:
    key = item.key
    if key in consumable_data.PLANETS:
        _add_planet(game, key)
        game.consumeables.remove(item)
        return "done"
    handler = _NO_TARGET_CONSUMABLES.get(key)
    if handler is not None:
        return handler(game, item)
    game.pending_consumable = item
    return "needs_target"


def _destroy_random_hand(game, n: int):
    n = min(n, len(game.hand))
    for c in game.rng.sample(game.hand, n):
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


#: 星级/生肖牌（星星/月亮/太阳/世界）共用：把目标牌变成指定花色
_SUIT_TAROTS = {"c_star", "c_moon", "c_sun", "c_world"}

_RANK_BUMP = {2: "3", 3: "4", 4: "5", 5: "6", 6: "7", 7: "8", 8: "9", 9: "10",
              10: "J", 11: "Q", 12: "K", 13: "A", 14: "A"}


# ----------------------------------------------------------------------
# 消耗牌：目标效果
#
# 每个 handler 接收 (game, targets, info) 并返回提示文本；targets 已按
# min/max_highlighted 截断。未登记的 key 给出「未知消耗牌」提示。
# ----------------------------------------------------------------------
def _target_enhance(enhanced, msg):
    def apply(game, targets, info):
        for c in targets:
            c.enhanced = enhanced
        return msg
    return apply


def _target_single_enhance(enhanced, msg):
    def apply(game, targets, info):
        if targets:
            targets[0].enhanced = enhanced
        return msg
    return apply


def _target_single_seal(seal, msg):
    def apply(game, targets, info):
        if targets:
            targets[0].seal = seal
        return msg
    return apply


def _target_strength(game, targets, info):
    for c in targets:
        c.rank = _RANK_BUMP[rank_id(c.rank)]
    return "力量：点数 +1"


def _target_hanged_man(game, targets, info):
    glass = 0
    for c in targets:
        if c.enhanced == "glass" and not c.debuffed:
            glass += 1
        game.notify_destroyed(c, shattered=(c.enhanced == "glass"))
    return f"倒吊人：销毁 {len(targets)} 张牌" + (f"（玻璃 {glass} 张）" if glass else "")


def _target_death(game, targets, info):
    right = targets[-1]
    for c in targets[:-1]:
        c.rank, c.suit, c.enhanced, c.edition, c.seal =             right.rank, right.suit, right.enhanced, right.edition, right.seal
    return "死神：复制最右牌"


def _target_suit(game, targets, info):
    conv = info["suit_conv"]
    for c in targets:
        c.suit = conv
    return f"{info['cn']}：变为花色 {conv}"


def _target_aura(game, targets, info):
    if targets:
        targets[0].edition = guaranteed_edition(game, "aura")
    return "灵光：附加随机版本"


def _target_cryptid(game, targets, info):
    if targets:
        c = targets[0]
        for _ in range(2):
            game.hand.append(c.copy())
        game.sort_hand()
    return "神秘生物：创建 2 张副本"


_TARGET_CONSUMABLES = {
    "c_magician": _target_enhance("lucky", "魔术师：变为幸运牌"),
    "c_empress": _target_enhance("mult", "女皇：变为倍率牌"),
    "c_heirophant": _target_enhance("bonus", "教皇：变为加分牌"),
    "c_lovers": _target_single_enhance("wild", "恋人：变为百搭牌"),
    "c_chariot": _target_single_enhance("steel", "战车：变为钢铁牌"),
    "c_justice": _target_single_enhance("glass", "正义：变为玻璃牌"),
    "c_devil": _target_single_enhance("gold", "恶魔：变为黄金牌"),
    "c_tower": _target_single_enhance("stone", "高塔：变为石头牌"),
    "c_strength": _target_strength,
    "c_hanged_man": _target_hanged_man,
    "c_death": _target_death,
    "c_star": _target_suit,
    "c_moon": _target_suit,
    "c_sun": _target_suit,
    "c_world": _target_suit,
    "c_talisman": _target_single_seal("gold", "护符：加上金色蜡封"),
    "c_aura": _target_aura,
    "c_deja_vu": _target_single_seal("red", "似曾相识：加上红色蜡封"),
    "c_trance": _target_single_seal("blue", "出神：加上蓝色蜡封"),
    "c_medium": _target_single_seal("purple", "灵媒：加上紫色蜡封"),
    "c_cryptid": _target_cryptid,
}


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
    # 灵光只能作用于还没有版本的牌（card.lua 1544-1545 的 can_use_consumeable）
    if info.get("editionless_target") and any(c.edition for c in targets):
        game.say(f"{info.get('cn', key)}：目标牌已有版本（未消耗）")
        return "invalid"
    handler = _TARGET_CONSUMABLES.get(key)
    msg = (handler(game, targets, info) if handler is not None
           else f"未知消耗牌 {key}")

    mark_consumable_used(game, key)
    game.consumeables.remove(item)
    game.pending_consumable = None
    game.say(msg)
    return "done"


# ==========================================================================
# 标签（Tag）
#
# 原版 Tag:apply_to_run(context) 按 ``config.type`` 分阶段触发，触发后立刻从
# G.GAME.tags 里移除（tag.lua 的 yep/remove）。因此跳过盲注的**当下**就能拿到
# 开卡包/给钱/加等级，而不是拖到进商店（button_callbacks.lua 2772-2777）。
#
#   immediate          Top-up / Skip / Garbage / Handy / Economy / Orbital
#   new_blind_choice   Charm / Meteor / Ethereal / Standard / Buffoon / Boss
#   voucher_add        Voucher
#   round_start_bonus  Juggle
#   store_joker_create Rare / Uncommon
#   shop_start         D6
#   store_joker_modify Foil / Holo / Polychrome / Negative
#   shop_final_pass    Coupon
#   eval               Investment
# ==========================================================================
TAG_IMMEDIATE = "immediate"
TAG_NEW_BLIND = "new_blind_choice"
TAG_VOUCHER_ADD = "voucher_add"
TAG_ROUND_START = "round_start_bonus"
TAG_STORE_CREATE = "store_joker_create"
TAG_STORE_MODIFY = "store_joker_modify"
TAG_SHOP_START = "shop_start"
TAG_FINAL_PASS = "shop_final_pass"
TAG_EVAL = "eval"

#: 标签 key -> 触发阶段（对应 game.lua 225-249 的 config.type）
TAG_TYPE = {
    "tag_top_up": TAG_IMMEDIATE,
    "tag_skip": TAG_IMMEDIATE,
    "tag_garbage": TAG_IMMEDIATE,
    "tag_handy": TAG_IMMEDIATE,
    "tag_economy": TAG_IMMEDIATE,
    "tag_orbital": TAG_IMMEDIATE,
    "tag_charm": TAG_NEW_BLIND,
    "tag_meteor": TAG_NEW_BLIND,
    "tag_ethereal": TAG_NEW_BLIND,
    "tag_standard": TAG_NEW_BLIND,
    "tag_buffoon": TAG_NEW_BLIND,
    "tag_boss": TAG_NEW_BLIND,
    "tag_voucher": TAG_VOUCHER_ADD,
    "tag_juggle": TAG_ROUND_START,
    "tag_rare": TAG_STORE_CREATE,
    "tag_uncommon": TAG_STORE_CREATE,
    "tag_d_six": TAG_SHOP_START,
    "tag_foil": TAG_STORE_MODIFY,
    "tag_holo": TAG_STORE_MODIFY,
    "tag_polychrome": TAG_STORE_MODIFY,
    "tag_negative": TAG_STORE_MODIFY,
    "tag_coupon": TAG_FINAL_PASS,
    "tag_investment": TAG_EVAL,
    # tag_double 特殊：在 add_tag（tag_add 上下文）时由 Game.add_tag 直接复制
}

#: 版本类标签 -> 附加的版本
_EDITION_TAGS = {"tag_foil": "foil", "tag_holo": "holo",
                 "tag_polychrome": "polychrome", "tag_negative": "negative"}

#: 开包类标签 -> 卡包键
_TAG_PACK = {
    "tag_standard": "p_standard_mega",
    "tag_charm": "p_arcana_mega",
    "tag_meteor": "p_celestial_mega",
    "tag_buffoon": "p_buffoon_mega",
    "tag_ethereal": "p_spectral_normal",
}


def _tag_cn(tag) -> str:
    return tag_data.TAGS.get(tag.key, {}).get("cn", tag.key)


def _tag_top_up(game, tag):
    # 原版 create_card('Joker', ..., _rarity = 0) → 稀有度被归一到 1（普通小丑）
    got = []
    for _ in range(2):
        if len(game.jokers) >= game.joker_slots:
            break
        key = centers_data.random_joker_key(game, rarity=1)
        game.jokers.append(JokerItem(key=key))
        got.append(centers_data.joker_cfg(key)["cn"])
    game.say(f"{_tag_cn(tag)}：获得小丑 {('、'.join(got)) or '（栏位已满）'}")


def _tag_skip(game, tag):
    gain = 5 * game.skips
    game.dollars += gain
    game.say(f"{_tag_cn(tag)}：+${gain}")


def _tag_garbage(game, tag):
    gain = game.unused_discards
    game.dollars += gain
    game.say(f"{_tag_cn(tag)}：+${gain}（本局累计未使用弃牌 {game.unused_discards}）")


def _tag_handy(game, tag):
    gain = game.hands_played_total
    game.dollars += gain
    game.say(f"{_tag_cn(tag)}：+${gain}（本局已打出 {game.hands_played_total} 手）")


def _tag_economy(game, tag):
    gain = min(40, max(0, game.dollars))
    game.dollars += gain
    game.say(f"{_tag_cn(tag)}：+${gain}")


def _tag_orbital(game, tag):
    h = game.rng.choice(game.visible_hands())
    game.hand_levels[h] += 3
    game.say(f"{_tag_cn(tag)}：{HAND_CN.get(h, h)} 等级 +3")


def _tag_open_pack(game, tag):
    from ..data import boosters as bd
    pk = _TAG_PACK[tag.key]
    game.say(f"{_tag_cn(tag)}：开启 {bd.BOOSTERS[pk]['cn']}")
    game._open_pack_now(pk, free=True)


def _tag_boss(game, tag):
    # 对应 tag.lua 284-301：免费重掷一次头目（不花 $10）
    game.reroll_boss(free=True)


def _tag_voucher(game, tag):
    # 对应 tag.lua 302-318：在商店里额外加 1 张优惠券（不是把当前那张变免费）
    game.pending_extra_voucher = True
    game.say(f"{_tag_cn(tag)}：本底注商店多 1 张优惠券")


def _tag_juggle(game, tag):
    # round_start_bonus：下一个回合抽牌前手牌上限 +3，回合结束回退
    game.temp_hand_size += 3
    game.say(f"{_tag_cn(tag)}：本回合手牌上限 +3")


def _tag_d_six(game, tag):
    game.temp_reroll_cost = 0
    game.say(f"{_tag_cn(tag)}：本商店重掷免费")


def _tag_coupon(game, tag):
    # 对应 tag.lua 447-465：只把**当前已生成**的商品置为免费（重掷出的新商品不免费，
    # 优惠券本身也不在其中）。
    if game.shop_free:
        return False
    game.shop_free = True
    for item in game.shop_jokers:
        item.couponed = True
    for bp in game.shop_boosters:
        bp.couponed = True
    game.say(f"{_tag_cn(tag)}：当前商店商品全部免费")
    return None


def _tag_investment(game, tag):
    game.investment_tag_active = True


#: key -> handler（只登记需要动作的阶段；其余是「已生效但无需动作」）
_TAG_HANDLERS = {
    "tag_top_up": _tag_top_up,
    "tag_skip": _tag_skip,
    "tag_garbage": _tag_garbage,
    "tag_handy": _tag_handy,
    "tag_economy": _tag_economy,
    "tag_orbital": _tag_orbital,
    "tag_standard": _tag_open_pack,
    "tag_charm": _tag_open_pack,
    "tag_meteor": _tag_open_pack,
    "tag_buffoon": _tag_open_pack,
    "tag_ethereal": _tag_open_pack,
    "tag_boss": _tag_boss,
    "tag_voucher": _tag_voucher,
    "tag_juggle": _tag_juggle,
    "tag_d_six": _tag_d_six,
    "tag_coupon": _tag_coupon,
    "tag_investment": _tag_investment,
}


def apply_tag(game, tag: Tag, context: str) -> bool:
    """按阶段应用一个标签；返回是否已触发（触发后从收藏里移除）。

    未到该阶段的标签原样保留在 :attr:`Game.tags` 里，等下一个阶段再结算。
    """
    if TAG_TYPE.get(tag.key) != context:
        return False
    handler = _TAG_HANDLERS.get(tag.key)
    if handler is not None and handler(game, tag) is False:
        return False
    for i, t in enumerate(game.tags):
        if t is tag:
            game.tags.pop(i)
            break
    return True


def edition_tag_for_couponed(game) -> str | None:
    """取出第一张版本类标签对应的版本（``store_joker_modify`` 上下文）。

    命中后消耗该标签并返回版本键；没有版本标签时返回 None。
    """
    for tag in list(game.tags):
        if TAG_TYPE.get(tag.key) == TAG_STORE_MODIFY:
            for i, t in enumerate(game.tags):
                if t is tag:
                    game.tags.pop(i)
                    break
            return _EDITION_TAGS[tag.key]
    return None


def forced_rarity_tag(game) -> int | None:
    """取出「罕见/稀有标签」，返回它要求的稀有度（``store_joker_create``）。

    对应 tag.lua 344-381：下一个生成的商店商品被替换成指定稀有度的小丑并免费。
    """
    for tag in list(game.tags):
        if tag.key == "tag_rare":
            for i, t in enumerate(game.tags):
                if t is tag:
                    game.tags.pop(i)
                    break
            return 3
        if tag.key == "tag_uncommon":
            for i, t in enumerate(game.tags):
                if t is tag:
                    game.tags.pop(i)
                    break
            return 2
    return None

def blind_boss_cn(game) -> str:
    from ..data.blinds import get_blind_cfg
    if game.boss_key:
        return get_blind_cfg(game.boss_key)["cn"]
    return ""


# ==========================================================================
# 事件钩子（由 game.py 调用）
#
# 原版这些事件同样走 Card:calculate_joker(context)：state_events.lua 与
# button_callbacks.lua 逐个调用 G.jokers.cards[i]:calculate_joker{...}。因此
# 蓝图会把 context 转发给它右侧的小丑、头脑风暴转发给最左侧的小丑，被转发
# 的小丑再按自身分支上的 `not context.blueprint` 守卫决定是否真的生效。
# 例如帕奇欧（ending_shop）没有守卫，蓝图贴着它就能多复制一张负片消耗牌；
# 而闪示卡、红牌、约里克、黑龟豆等都带守卫，蓝图贴着它们不会有额外收益。
# ==========================================================================

@dataclass
class HookCtx:
    """非记分钩子的上下文，对应 Lua calculate_joker 收到的 context 表。"""
    blueprint: int = 0                            # 蓝图转发链深度（Lua context.blueprint）
    discarded: List[Card] = field(default_factory=list)
    boss_beaten: bool = False


def _hook_one(game, joker, ctx, handler):
    """单个小丑的钩子：蓝图转发给右侧、头脑风暴转发给最左。"""
    target = None
    if joker.key == "j_blueprint":
        idx = _joker_index(game, joker)
        if 0 <= idx < len(game.jokers) - 1:
            target = game.jokers[idx + 1]
    elif joker.key == "j_brainstorm":
        if game.jokers and game.jokers[0] is not joker:
            target = game.jokers[0]
    if target is None or target is joker:
        handler(game, joker, ctx)
        return
    if ctx.blueprint >= len(game.jokers) + 1:     # 与 Lua 的链深上限一致，防互指死循环
        return
    ctx.blueprint += 1
    try:
        _hook_one(game, target, ctx, handler)
    finally:
        ctx.blueprint -= 1


def _hook_walk(game, ctx, handler):
    """按原版 Card:calculate_joker 的语义逐个结算钩子。"""
    for j in list(game.jokers):
        if j.debuffed:
            continue
        _hook_one(game, j, ctx, handler)


#: 小丑对手牌上限的常驻增减（对应 Lua joker config 的 h_size）
HAND_SIZE_EFFECT = {
    "j_juggler": 1,
    "j_merry_andy": -1,
    "j_troubadour": 2,
    "j_stuntman": -2,
    "j_turtle_bean": 5,
}


def joker_hand_size_bonus(game) -> int:
    """持有小丑对手牌上限的常驻增减；被禁用的小丑不生效。

    黑龟豆的每轮增减累计记在 j.stat["hand_size"]。
    """
    n = 0
    for j in game.jokers:
        if j.debuffed:
            continue
        base = HAND_SIZE_EFFECT.get(j.key)
        if base is not None:
            n += base + j.stat.get("hand_size", 0)
    return n


# ==========================================================================
# 钩子表
#
# 每个事件一张 {小丑 key: (handler, copyable)} 表。``copyable`` 表示该分支在
# 原版 Lua 里没有 `not context.blueprint` 守卫——蓝图/头脑风暴转发过来时仍然
# 生效；否则转发一律跳过。钩子函数本身只做业务，不再重复写守卫。
# ==========================================================================
def _make_hook(table):
    """把 (handler, copyable) 表包成 _hook_walk 需要的回调。"""
    def fx(game, j, ctx):
        entry = table.get(j.key)
        if entry is None:
            return
        handler, copyable = entry
        if ctx.blueprint and not copyable:
            return
        handler(game, j, ctx)
    return fx


# ---- 选盲注 ----
def _bs_riff_raff(game, j, ctx):
    for _ in range(2):
        if len(game.jokers) < game.joker_slots:
            jk = centers_data.random_joker_key(game, rarity=1)
            cfg = centers_data.joker_cfg(jk)
            game.jokers.append(JokerItem(key=jk))
            game.say(f"乌合之众：获得 {cfg['cn']}")


def _bs_marble(game, j, ctx):
    game.deck.add(Card(rank="A", suit="S", enhanced="stone", uid=0))
    game.hologram_count += 1
    game.say("大理石小丑：牌组 +1 石头牌")


def _bs_ceremonial(game, j, ctx):
    """仪式匕首：只销毁右侧**非永恒**小丑；右侧是永恒时什么都不做（card.lua 2561-2579）。"""
    victims = list(game.jokers[_joker_index(game, j) + 1:])
    if not victims:
        return
    victim = victims[0]
    if victim.eternal:
        game.say(f"典礼匕首：{joker_cn(victim.key)} 是永恒小丑，无法销毁")
        return
    gain = victim.sell_value(game.inflation, game.discount_percent) * 2
    j.stat["mult"] = j.stat.get("mult", 0) + gain
    game.jokers.remove(victim)
    game.say(f"典礼匕首：销毁 {joker_cn(victim.key)}，+{gain} 倍率")


def _bs_madness(game, j, ctx):
    """疯狂：只在**小盲/大盲**选择时触发，头目盲注不触发（card.lua 2503-2521）。"""
    if game.blind_on_deck == "Boss" or game.current_blind_key() in blind_data.BOSS_BLINDS:
        return
    j.stat["x_mult"] = j.stat.get("x_mult", 1.0) + 0.5
    others = [x for x in game.jokers if x is not j and not x.eternal]
    if others:
        victim = game.rng.choice(others, "madness")
        game.jokers.remove(victim)
        game.say("疯狂：+×0.5 倍率，销毁 1 张小丑")


def _bs_cartomancer(game, j, ctx):
    game.gain_random_consumable_of("tarot")
    game.say("占卜师：生成塔罗牌")


def _bs_burglar(game, j, ctx):
    game.hands_left += 3
    game.discards_left = 0
    game.say("盗贼：+3 手牌，失去全部弃牌")


def _bs_troubadour(game, j, ctx):
    game.hands_left = max(1, game.hands_left - 1)


def _bs_merry_andy(game, j, ctx):
    game.discards_left += 3


def _bs_drunkard(game, j, ctx):
    game.discards_left += 1


def _bs_todo(game, j, ctx):
    """待办清单：从可见牌型里随机选一个，并排除上一轮的目标（card.lua 2975-2983）。"""
    pool = [h for h in game.visible_hands() if h != j.stat.get("todo")]
    j.stat["todo"] = game.rng.choice(pool or game.visible_hands(), "todo")


def _bs_suit(game, j, ctx):
    """古老小丑 / 城堡：随机选一个**与上一轮不同**的花色。

    原版从牌组里实际存在的花色（城堡取非石头牌的花色）中抽，
    这里同样按牌组花色过滤（common_events.lua 2303-2324）。
    """
    present = [s for s in SUITS
               if any(c.is_suit(s, bypass_debuff=True) for c in game.all_playing_cards())]
    pool = [s for s in (present or list(SUITS)) if s != j.stat.get("suit")]
    j.stat["suit"] = game.rng.choice(pool or present or list(SUITS), "suit")


def _bs_idol(game, j, ctx):
    """偶像：从牌组里随机选一张**非石头牌**，取它的点数+花色（common_events 2271-2286）。"""
    pool = [c for c in game.all_playing_cards() if c.enhanced != "stone"]
    if pool:
        c = game.rng.choice(pool, "idol")
        j.stat["card"] = (c.rank, c.suit)
    else:
        j.stat["card"] = (game.rng.choice(RANKS), game.rng.choice(SUITS))


def _bs_mail(game, j, ctx):
    """邮件回扣：从牌组里随机选一张**非石头牌**，取它的点数（common_events 2288-2301）。"""
    pool = [c for c in game.all_playing_cards() if c.enhanced != "stone"]
    if pool:
        j.stat["rank"] = game.rng.choice(pool, "mail").rank
    else:
        j.stat["rank"] = game.rng.choice(RANKS)


#: key -> (handler, 可被蓝图复制)。希科/疯狂/典礼匕首带守卫；
#: 乌合之众/大理石/占卜师/盗贼在原版没有守卫，可被转发。
_BLIND_SELECT_HOOKS = {
    "j_riff_raff": (_bs_riff_raff, True),
    "j_marble": (_bs_marble, True),
    "j_ceremonial": (_bs_ceremonial, False),
    "j_madness": (_bs_madness, False),
    "j_cartomancer": (_bs_cartomancer, True),
    "j_burglar": (_bs_burglar, True),
    "j_troubadour": (_bs_troubadour, False),
    "j_merry_andy": (_bs_merry_andy, False),
    "j_drunkard": (_bs_drunkard, False),
    "j_todo_list": (_bs_todo, False),
    "j_ancient": (_bs_suit, False),
    "j_idol": (_bs_idol, False),
    "j_mail": (_bs_mail, False),
    "j_castle": (_bs_suit, False),
}

_blind_select_fx = _make_hook(_BLIND_SELECT_HOOKS)


def on_blind_select(game):
    """选中盲注时触发：被动成长/生成系小丑 + 每轮轮换目标。"""
    _hook_walk(game, HookCtx(), _blind_select_fx)


# ---- 首次抽牌（first_hand_drawn）----
def _fh_certificate(game, j, ctx):
    """证书：本回合**首次抽牌之后**额外加 1 张带随机蜡封的牌（card.lua 2462-2482）。

    加牌发生在补牌之后，因此手牌可以超过上限 1 张；同时触发「有牌加入牌组」
    的钩子（全息影像 +×0.25）。
    """
    card = _random_card(game, seal=True)
    game.deck.add(card)
    game.hand.append(card)
    game.hologram_count += 1
    game.sort_hand()
    game.say(f"证书：{card.display()} 入手")


_FIRST_HAND_HOOKS = {
    "j_certificate": (_fh_certificate, True),
}

_first_hand_fx = _make_hook(_FIRST_HAND_HOOKS)


def on_first_hand_drawn(game):
    """本回合首次抽牌结束（对应 state_events.lua 3226-3229 的 first_hand_drawn）。"""
    _hook_walk(game, HookCtx(), _first_hand_fx)


# ---- 弃牌 ----
def _dc_yorick(game, j, ctx):
    j.stat["discards"] = j.stat.get("discards", 0) + len(ctx.discarded)


def _dc_hit_the_road(game, j, ctx):
    n = sum(1 for c in ctx.discarded if c.rank == "J")
    if n:
        j.stat["jacks"] = j.stat.get("jacks", 0) + n


def _dc_ramen(game, j, ctx):
    """拉面：每弃 1 张 -×0.01，降到 ×1 时销毁（card.lua 2757-2786）。"""
    cur = j.stat.get("x_mult", 2.0)
    step = 0.01 * len(ctx.discarded)
    if cur - step <= 1.0:
        if j in game.jokers:
            game.jokers.remove(j)
        game.say("拉面吃完了！")
    else:
        j.stat["x_mult"] = cur - step


def _dc_mail(game, j, ctx):
    if any(c.rank == j.stat.get("rank", "A") for c in ctx.discarded):
        game.dollars += 5
        game.say("邮寄回扣：+$5")


def _dc_castle(game, j, ctx):
    suit = j.stat.get("suit", "S")
    n = sum(1 for c in ctx.discarded
            if c.is_suit(suit, smeared=game.any_joker("j_smeared")))
    if n:
        j.stat["chips"] = j.stat.get("chips", 0) + 3 * n


def _dc_green_joker(game, j, ctx):
    """绿色小丑：每弃 1 次牌 -1 倍率（card.lua 2846-2856）。

    原版按 ``other_card == full_hand[1]`` 守卫，一次弃牌只扣一次；这里
    ``on_discard`` 本身每批只调用一次，因此直接减 1。
    """
    j.stat["mult"] = j.stat.get("mult", 0) - 1


def _dc_faceless(game, j, ctx):
    faces = [c for c in ctx.discarded if is_face_card(c, game)]
    if len(faces) >= 3:
        game.dollars += 5
        game.say("无脸小丑：+$5")


def _dc_trading(game, j, ctx):
    if game.discards_used_round == 0 and len(ctx.discarded) == 1:
        c = ctx.discarded[0]
        # 牌此刻在 _round_cards；notify_destroyed 会把它从待回收区移除，
        # 回合结束便不会回到牌组（人头牌同时计入卡尼奥）
        game.notify_destroyed(c)
        game.dollars += 3
        game.say("交易卡：销毁该牌 +$3")


def _dc_burnt(game, j, ctx):
    if game.discards_used_round != 0:
        return
    name, _ = evaluate_poker_hand(
        ctx.discarded,
        four_fingers=game.any_joker("j_four_fingers"),
        shortcut=game.any_joker("j_shortcut"),
        smeared=game.any_joker("j_smeared"),
    )
    if name:
        game.hand_levels[name] += 1
        game.say(f"烧焦小丑：{HAND_CN.get(name, name)} 等级 +1")


#: 原版只有邮件回扣、无面小丑、烧焦小丑的分支没带蓝图守卫
#: （烧焦小丑写的是从未赋值的 context.hook）。
_DISCARD_HOOKS = {
    "j_yorick": (_dc_yorick, False),
    "j_hit_the_road": (_dc_hit_the_road, False),
    "j_ramen": (_dc_ramen, False),
    "j_mail": (_dc_mail, True),
    "j_castle": (_dc_castle, False),
    "j_green_joker": (_dc_green_joker, False),
    "j_faceless": (_dc_faceless, True),
    "j_trading": (_dc_trading, False),
    "j_burnt": (_dc_burnt, True),
}

_discard_fx = _make_hook(_DISCARD_HOOKS)


def on_discard(game, discarded: List[Card]):
    """弃牌触发系小丑。discarded 为被弃的牌列表（已从手牌移除）。"""
    _hook_walk(game, HookCtx(discarded=discarded), _discard_fx)


# ---- 回合结束 ----
def _er_egg(game, j, ctx):
    j.extra_value += 3


def _er_gift(game, j, ctx):
    for x in game.jokers:
        x.extra_value += 1
    for x in game.consumeables:
        x.extra_value += 1


def _er_rocket(game, j, ctx):
    # card.lua 2896：只有击败头目才 +2；每轮收入由 calculate_dollar_bonus 给出
    if ctx.boss_beaten:
        j.stat["dollars"] = j.stat.get("dollars", 1) + 2


def _er_gros_michel(game, j, ctx):
    # 1/6 概率灭绝（吃六六大顺）；灭绝后卡池标记置位，卡文迪许才会出现
    if roll_prob(game, 6, "gros_michel"):
        if j in game.jokers:
            game.jokers.remove(j)
        game.pool_flags["gros_michel_extinct"] = True
        game.say("大麦克香蕉灭绝了！")


def _er_cavendish(game, j, ctx):
    if roll_prob(game, 1000, "cavendish"):
        if j in game.jokers:
            game.jokers.remove(j)
        game.say("卡文迪许消失了！")


def _er_popcorn(game, j, ctx):
    """爆米花：每**回合** -4，降到 0 销毁（card.lua 2945-2975）。"""
    left = j.stat.get("mult", 20) - 4
    if left <= 0:
        if j in game.jokers:
            game.jokers.remove(j)
        game.say("爆米花吃完了！")
    else:
        j.stat["mult"] = left


def _er_hit_the_road(game, j, ctx):
    """上路吧杰克：每回合结束把本回合累计的 J 清零（card.lua 3011-3017）。"""
    j.stat["jacks"] = 0


def _er_campfire(game, j, ctx):
    """篝火：击败头目后重置为 ×1（card.lua 2889-2895）。"""
    if ctx.boss_beaten and j.stat.get("x_mult", 1.0) > 1:
        j.stat["x_mult"] = 1.0
        game.say("篝火：被头目浇灭，倍率重置为 ×1")


def _er_turtle_bean(game, j, ctx):
    # 每轮 -1 记在 stat 里（累计），下一回合由 round_hand_size 重新汇总；
    # 降到 0 时销毁（card.lua 2903-2933）
    left = 5 + j.stat.get("hand_size", 0) - 1
    if left <= 0:
        if j in game.jokers:
            game.jokers.remove(j)
        game.say("黑龟豆吃完了！")
        return
    j.stat["hand_size"] = j.stat.get("hand_size", 0) - 1
    game.change_hand_size(-1, persistent=False)


def _er_invisible(game, j, ctx):
    # card.lua 2934：每轮 +1；满 2 轮后卡面转为 ACTIVE，可以出售复制
    n = j.stat.get("invis_rounds", 0) + 1
    j.stat["invis_rounds"] = n
    if n >= _INVISIBLE_ROUNDS:
        game.say("隐形小丑：已就绪，出售可复制一张小丑")
    else:
        game.say(f"隐形小丑：{n}/{_INVISIBLE_ROUNDS} 轮")


#: 原版整个 end_of_round 分支都包在 `elseif not context.blueprint` 里
_END_ROUND_HOOKS = {
    "j_egg": (_er_egg, False),
    "j_gift": (_er_gift, False),
    "j_rocket": (_er_rocket, False),
    "j_campfire": (_er_campfire, False),
    "j_gros_michel": (_er_gros_michel, False),
    "j_cavendish": (_er_cavendish, False),
    "j_popcorn": (_er_popcorn, False),
    "j_hit_the_road": (_er_hit_the_road, False),
    "j_turtle_bean": (_er_turtle_bean, False),
    "j_invisible": (_er_invisible, False),
}

_end_round_fx = _make_hook(_END_ROUND_HOOKS)


def on_end_round(game, boss_beaten: bool = False):
    """回合结束时触发：成长/消亡/租金系小丑。"""
    ctx = HookCtx(boss_beaten=boss_beaten)
    for j in list(game.jokers):
        # 租金/过期与成长效果在同一趟里逐张结算（Lua 的 calculate_rental /
        # calculate_perishable 不经过 calculate_joker），所以不能拆成两趟：
        # 蛋与礼物卡会先抬高售价，紧接着收租才能拿到涨价后的数额。
        _hook_one(game, j, ctx, _end_round_fx)
        k = j.key
        if j.rental and not j.eternal:
            # 租金是固定 $3（G.GAME.rental_rate），不是按卖价收（card.lua 2271-2275）
            cost = 3
            game.dollars = max(0, game.dollars - cost)
            game.say(f"租用小丑 {joker_cn(k)}：-${cost}")
        if j.perishable and not j.eternal:
            # 易腐小丑 5 轮后**被禁用**而不是消失（card.lua 2278-2289）
            if j.perish_tally == 1:
                j.perish_tally = 0
                j.debuffed = True
                game.say(f"{joker_cn(k)} 已过期（效果禁用）")
            else:
                j.perish_tally -= 1


def _shop_closed_fx(game, j, ctx):
    k = j.key
    if k == "j_red_card":
        # 原版红卡挂在 skipping_booster 上且带蓝图守卫，蓝图贴着它不额外加成
        if ctx.blueprint:
            return
        n = len(game.shop_boosters)
        if n:
            j.stat["mult"] = j.stat.get("mult", 0) + 3 * n
            game.say(f"红卡：跳过 {n} 个卡包 +{3 * n} 倍率")
    elif k == "j_perkeo":
        # 原版帕奇欧的 ending_shop 分支没有蓝图守卫，蓝图贴着它能多复制一张
        if game.consumeables:
            c = game.rng.choice(game.consumeables)
            game.consumeables.append(ConsumableItem(key=c.key, edition="negative",
                                                    buy_cost=c.buy_cost, extra_value=c.extra_value))
            game.say("珀可：复制 1 张消耗牌（负片）")


def on_shop_closed(game):
    """离开商店时触发。"""
    _hook_walk(game, HookCtx(), _shop_closed_fx)


def _sell_luchador(game, j, ctx):
    # 摔跤手没有蓝图守卫，被蓝图转发时照样生效；
    # 但只有「当前正在打头目盲注」时才有效（card.lua 2354-2360）
    if game.current_blind_key() not in blind_data.BOSS_BLINDS:
        game.say("摔跤手：当前不是头目盲注，没有可禁用的效果")
        return
    if game.disable_current_blind():
        game.say("摔跤手：禁用当前头目盲注效果")
    else:
        game.say("摔跤手：当前没有可禁用的盲注效果")


def _sell_diet_cola(game, j, ctx):
    # 零糖可乐没有蓝图守卫：蓝图贴着它被转发时同样生成双重标签
    game.say("零糖可乐：生成双重标签")
    game.add_tag("tag_double")


def _sell_invisible(game, j, ctx):
    # card.lua 2371：满 2 轮后出售，随机复制另一张小丑
    n = j.stat.get("invis_rounds", 0)
    if n < _INVISIBLE_ROUNDS:
        game.say(f"隐形小丑：还需 {_INVISIBLE_ROUNDS - n} 轮才能复制")
        return
    others = [x for x in game.jokers if x is not j]
    if not others:
        game.say("隐形小丑：没有其他小丑可以复制")
        return
    # 容量检查在原版里是 `#G.jokers.cards <= card_limit`：此时被卖的小丑
    # 还在栏位里，它让出的那一格正好给复制品。
    if len(game.jokers) > game.joker_slots:
        game.say("隐形小丑：小丑栏位已满")
        return
    chosen = game.rng.choice(others, "invisible")
    # copy_card 的第 5 个参数 strip_edition = chosen.edition and chosen.edition.negative：
    # 复制负片小丑时，复制品不带版本。
    new_joker = chosen.copy(strip_edition=chosen.negative)
    # card.lua 2385：复制到的是隐形小丑时，复制品的轮数从 0 重新开始
    if "invis_rounds" in new_joker.stat:
        new_joker.stat["invis_rounds"] = 0
    game.jokers.append(new_joker)
    game.say(f"隐形小丑：复制了 {joker_cn(chosen.key)}")


#: 原版 selling_self 分支：摔跤手与零糖可乐没有蓝图守卫，
#: 隐形小丑带 `not context.blueprint`。
_SELL_HOOKS = {
    "j_luchador": (_sell_luchador, True),
    "j_diet_cola": (_sell_diet_cola, True),
    "j_invisible": (_sell_invisible, False),
}

_sell_fx = _make_hook(_SELL_HOOKS)


def on_sell_joker(game, sold):
    """卖出小丑时触发（在被卖的小丑还留在序列里时调用）。

    原版是 ``sold:calculate_joker{selling_self = true}``：只有被卖的那张小丑
    收到 context，但蓝图会把它转发给自己右侧的小丑——所以卖掉贴着摔跤手的
    蓝图同样能禁用当前头目盲注、卖掉贴着零糖可乐的蓝图同样能拿到双重标签，
    而隐形小丑带蓝图守卫，转发不会触发复制。

    卖出**任意**卡牌还会触发 ``selling_card``（篝火 +×0.25），见
    :func:`on_sell_card`。
    """
    _hook_one(game, sold, HookCtx(), _sell_fx)
    on_sell_card(game)


def on_sell_card(game):
    """卖出任意卡牌（``selling_card`` 上下文）：篝火 +×0.25（card.lua 2395-2401）。"""
    for j in list(game.jokers):
        if j.debuffed:
            continue
        if j.key == "j_campfire":
            j.stat["x_mult"] = j.stat.get("x_mult", 1.0) + 0.25
            game.say(f"篝火：+×0.25（当前 ×{j.stat['x_mult']:.2f}）")


def _reroll_fx(game, j, ctx):
    # 原版闪示卡挂在 reroll_shop 上且带蓝图守卫，蓝图贴着它不额外加成
    if ctx.blueprint:
        return
    if j.key == "j_flash":
        j.stat["mult"] = j.stat.get("mult", 0) + 2


def on_reroll(game):
    """重掷商店时触发。"""
    _hook_walk(game, HookCtx(), _reroll_fx)
