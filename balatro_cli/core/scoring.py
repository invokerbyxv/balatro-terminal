"""记分管线：打出的一手牌如何变成得分。

严格按 functions/state_events.lua evaluate_play 的阶段顺序：
  基础手牌 → joker before → 重读+盲注修改 → 阶段A(逐张记分牌) → 阶段B(手中牌)
  → 阶段C(joker 主效果/消耗品) → 牌背 final → 玻璃破碎 → floor(chips*mult)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional

from .card import Card
from .hand_eval import evaluate_poker_hand, hand_level_stats, is_royal_flush, HAND_CN
from ..data import boosters as booster_data
from ..data import consumables as consumable_data


class InvalidPlay(Exception):
    """手牌被盲注规则判定无效：牌留在手中，不消耗出牌次数。"""


@dataclass
class Effect:
    """一次效果：任选字段叠加。"""
    chips: float = 0.0
    mult: float = 0.0
    x_mult: float = 1.0
    dollars: float = 0.0
    repetitions: int = 0
    message: str = ""
    card: Optional[Card] = None


@dataclass
class Ctx:
    """joker 效果上下文。"""
    phase: str = "joker_main"          # before/individual/joker_main/other_joker/after/discard/draw/end_of_round
    blueprint: int = 0                 # 蓝图/头脑风暴复制链深度（对应 Lua context.blueprint）
    scoring_name: str = ""
    scoring_cards: List[Card] = field(default_factory=list)
    played_cards: List[Card] = field(default_factory=list)
    other_card: Optional[Card] = None
    other_joker: Optional[object] = None
    hand_being_evaluated: bool = False
    full_hand: bool = False
    game: Optional[object] = None


@dataclass
class Breakdown:
    """记分来源汇总：打印公式时展示各来源的贡献（基础/牌/各小丑…）。"""
    base_chips: float = 0.0
    base_mult: float = 0.0
    chips: dict = field(default_factory=dict)        # 标签 -> 筹码累计（筹码只有加法）
    mult: List[tuple] = field(default_factory=list)  # 倍率事件序列：(kind, 标签, 值)，kind='+'加法/'×'乘法


def _record(bd, label, chips=0.0, mult=0.0, x_mult=1.0):
    """把一次贡献记入 breakdown（bd 为 None 时不记录）。"""
    if bd is None:
        return
    if chips:
        bd.chips[label] = bd.chips.get(label, 0.0) + chips
    if mult:
        bd.mult.append(("+", label, mult))
    if x_mult != 1.0:
        bd.mult.append(("×", label, x_mult))


# ----------------------------------------------------------------------
# 阶段 A：单张牌的记分贡献（eval_card → get_chip_*）
# ----------------------------------------------------------------------
def card_chip_bonus(game, card: Card) -> int:
    """打出记分时该牌的筹码：rank值 + 增强 + 远足者额外。debuff 则为 0。"""
    if card.debuffed:
        return 0
    from .card import rank_value
    chips = rank_value(card.rank)
    if card.enhanced == "stone":
        return booster_data.ENHANCED["m_stone"]["bonus"]
    if card.enhanced == "bonus":
        chips += booster_data.ENHANCED["m_bonus"]["bonus"]
    chips += getattr(game, "card_chip_extra", {}).get(id(card), 0)
    return chips


def card_mult_bonus(game, card: Card) -> int:
    if card.debuffed:
        return 0
    m = 0
    if card.enhanced == "mult":
        m += booster_data.ENHANCED["m_mult"]["mult"]
    if card.enhanced == "lucky":
        from .effects import roll_prob
        if roll_prob(game, booster_data.ENHANCED["m_lucky"]["mult_chance"], "lucky"):
            m += booster_data.ENHANCED["m_lucky"]["mult"]
            game.lucky_triggers += 1
    return m


def card_x_mult_bonus(game, card: Card) -> float:
    if card.debuffed:
        return 1.0
    if card.enhanced == "glass":
        return booster_data.ENHANCED["m_glass"]["x_mult"]
    return 1.0


def card_dollars_bonus(game, card: Card) -> int:
    if card.debuffed:
        return 0
    d = 0
    if card.seal == "gold":
        d += 3
    if card.enhanced == "lucky":
        from .effects import roll_prob
        if roll_prob(game, booster_data.ENHANCED["m_lucky"]["dollars_chance"], "lucky_money"):
            d += booster_data.ENHANCED["m_lucky"]["p_dollars"]
            game.lucky_triggers += 1
    return d


def card_edition(game, card: Card):
    """返回 (chips_mod, mult_mod, x_mult_mod)。"""
    if card.debuffed or not card.edition:
        return 0, 0, 1.0
    e = booster_data.EDITIONS.get("e_" + card.edition)
    if not e:
        return 0, 0, 1.0
    return e.get("chips", 0), e.get("mult", 0), e.get("x_mult", 1.0)


def held_card_effect(game, card: Card) -> tuple:
    """阶段 B：留在手牌的牌的效果（钢铁 ×1.5）。返回 (mult_mod, x_mult_mod)。"""
    if card.debuffed:
        return 0, 1.0
    if card.enhanced == "steel":
        return 0, booster_data.ENHANCED["m_steel"]["h_x_mult"]
    return 0, 1.0


# ----------------------------------------------------------------------
# 主管线
# ----------------------------------------------------------------------
def evaluate_play(game) -> List[str]:
    """结算打出的手牌。返回展示消息列表。"""
    from .effects import calculate_joker, joker_cn
    msgs: List[str] = []
    played = game.play[:]

    # Step 1: 判定手牌
    name, scoring_hand = evaluate_poker_hand(
        played,
        four_fingers=game.any_joker("j_four_fingers"),
        shortcut=game.any_joker("j_shortcut"),
        smeared=game.any_joker("j_smeared"),
    )
    display_name = "皇家同花顺" if is_royal_flush(name, scoring_hand) else HAND_CN.get(name, name)
    boss_disabled = game.boss_disabled()

    # 眼睛 boss：本回合不得重复牌型
    if not boss_disabled and game.blind_key == "bl_eye" and name in game.round_hand_played:
        raise InvalidPlay("眼睛：本回合已打过该牌型，无效！")

    # 嘴 boss：只能打出与上一手相同的牌型（首手不限）
    if not boss_disabled and game.blind_key == "bl_mouth":
        if not game.first_hand_face_down and game.last_hand_name != name:
            raise InvalidPlay("嘴：只能打出与上一手相同的牌型！")
        game.first_hand_face_down = False

    game.last_hand_name = name
    game.round_hand_played.append(name)

    # Step 2: 额外记分牌（石头牌总是记分；Splash 所有牌都记分）
    extra = []
    for c in played:
        if c.enhanced == "stone" and c not in scoring_hand:
            extra.append(c)
    if game.any_joker("j_splash"):
        extra = [c for c in played if c not in scoring_hand]
    scoring_hand = scoring_hand + [c for c in extra if c not in scoring_hand]

    # Step 3: 盲注 debuff 检查
    if _blind_disallows_hand(game, name, scoring_hand):
        raise InvalidPlay(f"盲注效果：不允许打出 {display_name}！")

    # 通灵者：必须打满 5 张
    if not boss_disabled and game.blind_key == "bl_psychic" and len(played) < 5:
        raise InvalidPlay("通灵者：必须打出 5 张牌才能得分！")

    # Step 4: 基础数值
    mult, hand_chips = hand_level_stats(name, game.hand_levels[name])

    # 手臂 boss：降级
    if not boss_disabled and game.blind_key == "bl_arm":
        if game.hand_levels[name] > 1:
            game.hand_levels[name] -= 1
            mult, hand_chips = hand_level_stats(name, game.hand_levels[name])
            msgs.append(f"手臂：{display_name} 等级 -1")

    # (b) joker before 阶段
    ctx = Ctx(phase="before", scoring_name=name, scoring_cards=scoring_hand,
              played_cards=played, game=game)
    for j in list(game.jokers):
        if j.debuffed or j.disabled_round:
            continue
        for ef in calculate_joker(game, j, ctx):
            _apply_effect(game, ef, mult, hand_chips)

    # (c) 重读基础值 + 盲注修改
    bd = Breakdown()  # 记分分项（公式展示用）
    mult, hand_chips = hand_level_stats(name, game.hand_levels[name])
    if not boss_disabled and game.blind_key == "bl_flint":
        mult = max(1, int(mult / 2))
        hand_chips = max(0, int(hand_chips / 2))
    bd.base_chips, bd.base_mult = hand_chips, mult

    # (d) 阶段 A：记分牌逐张
    for card in scoring_hand:
        reps = 1
        if card.seal == "red":
            reps += 1
        # joker repetition
        ctx = Ctx(phase="repetition", scoring_name=name, scoring_cards=scoring_hand,
                  other_card=card, game=game)
        for j in list(game.jokers):
            if j.debuffed or j.disabled_round:
                continue
            for ef in calculate_joker(game, j, ctx):
                reps += ef.repetitions
        for _ in range(reps):
            # 牌自身效果
            ch = card_chip_bonus(game, card)
            m = card_mult_bonus(game, card)
            x = card_x_mult_bonus(game, card)
            d = card_dollars_bonus(game, card)
            hand_chips += ch
            mult += m
            _record(bd, "牌", chips=ch, mult=m, x_mult=x)
            if d:
                game.dollars += d
                msgs.append(f"+${d}")
            if x != 1.0:
                mult *= x
            c_mod, m_mod, x_mod = card_edition(game, card)
            if c_mod:
                hand_chips += c_mod
            if m_mod:
                mult += m_mod
            if x_mod != 1.0:
                mult *= x_mod
            _record(bd, "牌", chips=c_mod, mult=m_mod, x_mult=x_mod)
            # 小丑 individual
            ctx = Ctx(phase="individual", scoring_name=name, scoring_cards=scoring_hand,
                      other_card=card, played_cards=played, game=game)
            for j in list(game.jokers):
                if j.debuffed or j.disabled_round:
                    continue
                for ef in calculate_joker(game, j, ctx):
                    hand_chips, mult = _apply(game, ef, hand_chips, mult, msgs, bd, joker_cn(j.key))

    # (e) 阶段 B：手中牌
    for card in game.hand:
        reps = 1
        if card.seal == "red":
            reps += 1
        # 重触发（默剧演员等）
        ctx = Ctx(phase="repetition", scoring_name=name, scoring_cards=scoring_hand,
                  other_card=card, game=game, hand_being_evaluated=True)
        for j in list(game.jokers):
            if j.debuffed or j.disabled_round:
                continue
            for ef in calculate_joker(game, j, ctx):
                reps += ef.repetitions
        for _ in range(reps):
            m_mod, x_mod = held_card_effect(game, card)
            mult += m_mod
            if x_mod != 1.0:
                mult *= x_mod
            _record(bd, "钢铁", mult=m_mod, x_mult=x_mod)
            ctx = Ctx(phase="individual", scoring_name=name, scoring_cards=scoring_hand,
                      other_card=card, game=game, hand_being_evaluated=True)
            for j in list(game.jokers):
                if j.debuffed or j.disabled_round:
                    continue
                for ef in calculate_joker(game, j, ctx):
                    hand_chips, mult = _apply(game, ef, hand_chips, mult, msgs, bd, joker_cn(j.key))

    # (f) 阶段 C：小丑主效果 + 版本 + 消耗品（天文台）
    for j in list(game.jokers):
        if j.debuffed or j.disabled_round:
            continue
        jlabel = joker_cn(j.key)
        ctx = Ctx(phase="joker_main", scoring_name=name, scoring_cards=scoring_hand,
                  played_cards=played, game=game)
        for ef in calculate_joker(game, j, ctx):
            hand_chips, mult = _apply(game, ef, hand_chips, mult, msgs, bd, jlabel)
        # 小丑自身版本
        if j.edition:
            e = booster_data.EDITIONS.get("e_" + j.edition)
            if e:
                hand_chips += e.get("chips", 0)
                mult += e.get("mult", 0)
                if e.get("x_mult"):
                    mult *= e["x_mult"]
                _record(bd, jlabel, chips=e.get("chips", 0), mult=e.get("mult", 0),
                        x_mult=e.get("x_mult", 1.0))
        # other_joker 互查
        for oj in list(game.jokers):
            if oj is j:
                continue
            ctx = Ctx(phase="other_joker", scoring_name=name, scoring_cards=scoring_hand,
                      other_joker=j, game=game)
            for ef in calculate_joker(game, oj, ctx):
                hand_chips, mult = _apply(game, ef, hand_chips, mult, msgs, bd, joker_cn(oj.key))

    # 天文台：手牌中的匹配星球牌 ×1.5
    if game.has_voucher("v_observatory"):
        for c in game.consumeables:
            info = consumable_data.PLANETS.get(c.key)
            if info and info["hand"] == name:
                mult *= 1.5
                _record(bd, "天文台", x_mult=1.5)

    # (g) 牌背 final_scoring_step（浮雕牌组给双重标签在 boss 击败时处理）
    if game.deck_key == "b_plasma":
        avg = (hand_chips + mult) / 2
        hand_chips, mult = int(avg), int(avg)
        bd = None  # 取平均后无法还原分项，退回简单公式
    elif game.deck_key == "b_anaglyph":
        pass

    # (h) 玻璃破碎
    from .effects import roll_prob
    broken = []
    for card in scoring_hand:
        if card.enhanced == "glass" and not card.debuffed:
            if roll_prob(game, booster_data.ENHANCED["m_glass"]["break_chance"], "glass"):
                broken.append(card)
                game.glass_broken += 1
                if card.is_face():
                    game.face_destroyed += 1
                msgs.append(f"玻璃牌碎裂：{card.display()}")

    # Step 5: 最终分
    final_score = int(hand_chips * mult)
    game.chips += final_score
    msgs.insert(0, format_formula(bd, display_name, hand_chips, mult, final_score))

    # 触手 boss：每张牌 -$1
    if not boss_disabled and game.blind_key == "bl_tooth":
        cost = len(played)
        game.dollars = max(0, game.dollars - cost)
        msgs.append(f"牙：打出 {cost} 张牌，-${cost}")

    # 牛 boss：打出最常玩牌型清零金钱
    if not boss_disabled and game.blind_key == "bl_ox":
        most = max(game.hand_levels, key=lambda k: game.hands_count.get(k, 0))
        if name == most and game.dollars > 0:
            game.dollars = 0
            msgs.append("牛：金钱归零！")

    # 玻璃破碎牌从场中移除
    for card in broken:
        pass  # 已打出，无需从手牌移除

    # Step 6: joker after 阶段
    ctx = Ctx(phase="after", scoring_name=name, scoring_cards=scoring_hand,
              played_cards=played, game=game)
    for j in list(game.jokers):
        if j.debuffed or j.disabled_round:
            continue
        for ef in calculate_joker(game, j, ctx):
            hand_chips, mult = _apply(game, ef, hand_chips, mult, msgs)
    game.hands_count.setdefault(name, 0)
    game.hands_count[name] += 1
    game.played_this_ante.extend(played)
    return msgs


def format_formula(bd, display_name, hand_chips, mult, final_score) -> str:
    """渲染带分项的计算公式；bd 为 None（等离子牌组取平均）时退回简单格式。

    筹码是纯加法，按来源汇总；倍率中加法在 ×边界内按来源合并（如 5 张牌各
    +3 → +15），×乘法保持触发顺序（加法可交换、乘法不可，跨 × 的加法不能合并），
    保证推算与真实得分一致。
    """
    if bd is None:
        return f"打出 {display_name}：{int(hand_chips)} × {int(mult)} = {final_score}"
    chips = [f"基础{int(bd.base_chips)}"] + [f"{k}{v:+.0f}" for k, v in bd.chips.items() if v]
    terms = []
    add_accum: dict = {}   # ×边界内：标签 -> 加法累计
    add_order: list = []   # 标签首次出现顺序
    def flush_adds():
        for label in add_order:
            v = add_accum[label]
            if v:
                terms.append(f"{v:+.0f}[{label}]")
        add_accum.clear()
        add_order.clear()
    for kind, label, value in bd.mult:
        if kind == "+":
            if label not in add_accum:
                add_order.append(label)
                add_accum[label] = 0.0
            add_accum[label] += value
        else:
            flush_adds()
            terms.append(f"×{value:g}[{label}]")
    flush_adds()
    muls = [f"基础{int(bd.base_mult)}"] + terms
    return (f"打出 {display_name}：（{' + '.join(chips)}） × （{' '.join(muls)}） = {final_score}")


def _blind_disallows_hand(game, name, scoring_hand) -> bool:
    """返回 True 则整手牌无效。"""
    if game.blind_key == "bl_psychic" and len(scoring_hand) < 5:
        return True
    return False


def _apply_effect(game, ef, mult, hand_chips, bd=None, label=""):
    """before 阶段的 apply（无消息收集）。"""
    if ef.chips:
        hand_chips += ef.chips
    if ef.mult:
        mult += ef.mult
    if ef.x_mult != 1.0:
        mult *= ef.x_mult
    _record(bd, label, chips=ef.chips, mult=ef.mult, x_mult=ef.x_mult)
    return hand_chips, mult


def _apply(game, ef, hand_chips, mult, msgs, bd=None, label=""):
    hand_chips += ef.chips
    mult += ef.mult
    if ef.x_mult != 1.0:
        mult *= ef.x_mult
    _record(bd, label, chips=ef.chips, mult=ef.mult, x_mult=ef.x_mult)
    if ef.dollars:
        game.dollars += ef.dollars
    if ef.message:
        msgs.append(ef.message)
    return hand_chips, mult
