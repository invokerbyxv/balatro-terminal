"""审计报告（CLI vs 原版）中 P0 / P1 修复项的行为断言。

每个测试都对应审计报告第 9 节列出的一个具体修复点，注释里标出原版源码位置，
这样以后改动时可以对照"原版怎么算"而不是"以前 CLI 怎么算"。
"""
from __future__ import annotations

import unittest

from balatro_cli.core.card import Card
from balatro_cli.core.game import Game
from balatro_cli.core.hand_eval import evaluate_poker_hand
from balatro_cli.core.items import BoosterPack, ConsumableItem, JokerItem, Tag
from balatro_cli.core.joker_fx import calculate_joker, is_face_card
from balatro_cli.core.lookup import roll_prob
from balatro_cli.core.scoring import Ctx
from balatro_cli.data import boosters as booster_data
from balatro_cli.data import centers as centers_data
from balatro_cli.data import consumables as consumable_data
from balatro_cli.data.blinds import BOSS_BLINDS
from tests.helpers import cards, new_game, select_cards, set_hand


def stub_roll(g, value):
    """把 RNG 的 roll 固定成 value（概率类判定的边界测试）。"""
    g.rng.roll = lambda label="": value


def ctx(**kw):
    return Ctx(**kw)


class TestCardIdentity(unittest.TestCase):
    """P0-1 牌身份：石头牌无点数无花色；被禁用的牌不算人头牌。"""

    def test_stone_has_no_rank_or_suit(self):
        stone = Card(rank="A", suit="S", enhanced="stone")
        self.assertLess(stone.get_id(), 0)          # card.lua 957-962 返回随机负数
        self.assertFalse(stone.is_face())
        self.assertFalse(stone.is_suit("S"))
        self.assertFalse(stone.is_suit("S", flush_calc=True))

    def test_stone_does_not_join_pairs_or_straights(self):
        self.assertEqual(
            evaluate_poker_hand(cards("A-S", "A-H", "A-C", "A-D", "2-C-stone"))[0],
            "Four of a Kind")
        self.assertEqual(
            evaluate_poker_hand(cards("2-S", "3-S", "4-S", "5-S", "6-S-stone"))[0],
            "High Card")

    def test_debuffed_face_is_not_face(self):
        g = new_game(seed=1)
        j = Card(rank="J", suit="S", debuffed=True)
        self.assertFalse(is_face_card(j, g))
        self.assertTrue(is_face_card(j, g, from_boss=True))   # The Plant 用 is_face(true)
        j.debuffed = False
        self.assertTrue(is_face_card(j, g))

    def test_debuffed_face_does_not_trigger_scary_face(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_scary_face")]
        played = cards("J-S", "K-H")
        played[0].debuffed = True
        effs = calculate_joker(g, g.jokers[0],
                               ctx(phase="individual", other_card=played[0],
                                   scoring_cards=played, played_cards=played))
        self.assertEqual(effs, [])


class TestDestructionAndSeals(unittest.TestCase):
    """P0-2 销毁 / 封印：玻璃真碎、吊人计数、蓝封、钩子弃牌上下文。"""

    def test_glass_card_is_really_destroyed(self):
        g = new_game(seed=7)
        set_hand(g, ["A-S", "A-H", "2-C-glass", "2-H", "3-D", "4-S", "5-H", "6-S"])
        stub_roll(g, 0.0)                     # 所有概率判定必定成功
        glass = g.hand[2]
        select_cards(g, 4)                    # A,A,2(玻璃),2 → 两对，玻璃牌参与计分
        g.play_selected()
        self.assertEqual(g.glass_broken, 1)
        self.assertNotIn(glass, g._round_cards)
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertNotIn(glass, g.deck.cards)   # 不再被洗回牌组

    def test_hanged_man_counts_glass_joker(self):
        from balatro_cli.core.effects import finish_consumable_target, use_consumable

        g = new_game(seed=7)
        g.hand = cards("2-C-glass")
        item = ConsumableItem(key="c_hanged_man")
        g.consumeables = [item]
        self.assertEqual(use_consumable(g, item), "needs_target")
        finish_consumable_target(g, [g.hand[0]])
        self.assertEqual(g.glass_broken, 1)
        self.assertEqual(g.hand, [])

    def test_blue_seal_creates_planet_for_last_hand(self):
        g = new_game(seed=7)
        card = Card(rank="2", suit="C", seal="blue")
        g.hand = [card, Card(rank="3", suit="H")]
        g.last_hand_played = "Pair"
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertIn("c_mercury", [c.key for c in g.consumeables])

    def test_hook_discard_runs_full_discard_context(self):
        g = new_game(seed=7)
        g.blind_key = "bl_hook"
        g.jokers = [JokerItem(key="j_yorick")]
        set_hand(g, ["A-S", "A-H", "3-C", "4-D", "5-S", "6-H", "7-D", "8-C"])
        select_cards(g, 2)
        g.play_selected()
        self.assertEqual(g.jokers[0].stat.get("discards"), 2)
        self.assertEqual(g.discards_used_round, 0)     # 钩子弃牌不消耗弃牌次数

    def test_purple_seal_on_hook_discard(self):
        g = new_game(seed=7)
        g.blind_key = "bl_hook"
        g.hand = [Card(rank="2", suit="C", seal="purple"),
                  Card(rank="3", suit="C")]
        g.jokers = []
        g._press_play()
        self.assertEqual(len(g.consumeables), 1)       # 紫封生成了塔罗


class TestShopGeneration(unittest.TestCase):
    """P0-3 商店 / 卡包生成。"""

    def test_default_shop_has_no_cards_or_spectrals(self):
        g = new_game(seed=3, blind=False)
        rates = g._shop_rates()
        self.assertEqual(rates, {"joker": 20, "tarot": 4, "planet": 4})

    def test_ghost_deck_spectral_rate(self):
        g = Game(seed=1)
        g.start_run("b_ghost")
        self.assertEqual(g.spectral_rate, 2)

    def test_magic_trick_and_illusion_enable_cards(self):
        g = new_game(seed=3, blind=False)
        g.redeem_voucher("v_magic_trick")
        self.assertEqual(g.playing_card_rate, 4)
        g.redeem_voucher("v_illusion")
        self.assertTrue(g.has_voucher("v_illusion"))

    def test_tarot_merchant_rates(self):
        g = new_game(seed=3, blind=False)
        g.redeem_voucher("v_tarot_merchant")
        self.assertAlmostEqual(g.tarot_rate, 9.6)
        g2 = new_game(seed=3, blind=False)
        g2.redeem_voucher("v_tarot_merchant")
        g2.redeem_voucher("v_tarot_tycoon")
        self.assertEqual(g2.tarot_rate, 32)

    def test_poll_edition_boundaries(self):
        g = new_game(seed=3, blind=False)
        for value, expected in ((0.9999, "negative"), (0.995, "polychrome"),
                                (0.99, "holo"), (0.97, "foil"), (0.5, None)):
            stub_roll(g, value)
            self.assertEqual(centers_data.poll_edition(g), expected, value)

    def test_hone_doubles_edition_rate(self):
        g = new_game(seed=3, blind=False)
        g.redeem_voucher("v_hone")
        self.assertEqual(g.edition_rate, 2)
        # edition_rate=1: 箔片需要 > 0.96；=2: 箔片只需 > 0.92、全息 > 0.96
        stub_roll(g, 0.95)
        g.edition_rate = 1
        self.assertIsNone(centers_data.poll_edition(g))
        g.edition_rate = 2
        self.assertEqual(centers_data.poll_edition(g), "foil")
        g.edition_rate = 1
        stub_roll(g, 0.97)
        self.assertEqual(centers_data.poll_edition(g), "foil")
        g.edition_rate = 2
        self.assertEqual(centers_data.poll_edition(g), "holo")

    def test_no_legendary_jokers_in_pool(self):
        g = new_game(seed=3)
        got = {centers_data.random_joker_key(g) for _ in range(300)}
        self.assertFalse(any(centers_data.JOKERS[k]["r"] == 4 for k in got))

    def test_enhancement_gate_blocks_stone_joker(self):
        g = new_game(seed=3)
        self.assertNotIn("j_stone", {centers_data.random_joker_key(g) for _ in range(400)})
        g.deck.cards.append(Card(rank="2", suit="C", enhanced="stone"))
        self.assertTrue(centers_data.pool_allowed(g, "j_stone"))

    def test_pool_flags_for_banana(self):
        g = new_game(seed=3)
        self.assertTrue(centers_data.pool_allowed(g, "j_gros_michel"))
        self.assertFalse(centers_data.pool_allowed(g, "j_cavendish"))
        g.pool_flags["gros_michel_extinct"] = True
        self.assertFalse(centers_data.pool_allowed(g, "j_gros_michel"))
        self.assertTrue(centers_data.pool_allowed(g, "j_cavendish"))

    def test_pack_weights_cover_15_types(self):
        self.assertEqual(len(booster_data.PACK_WEIGHTS), 15)
        for key in ("p_spectral_mega", "p_arcana_jumbo", "p_buffoon_mega"):
            self.assertIn(key, booster_data.PACK_WEIGHTS)
            self.assertIn(key, booster_data.BOOSTERS)

    def test_standard_pack_never_has_negative(self):
        g = new_game(seed=3, blind=False)
        for _ in range(200):
            self.assertNotEqual(g._random_standard_card().edition, "negative")

    def test_soul_and_black_hole_not_in_consumable_pools(self):
        g = new_game(seed=3)
        for kind in ("tarot", "planet", "spectral"):
            pool = consumable_data.pool(g, kind)
            self.assertNotIn("c_soul", pool)
            self.assertNotIn("c_black_hole", pool)

    def test_omen_globe_gives_no_extra_slot(self):
        g = new_game(seed=3, blind=False)
        before = g.consumable_slots
        g.redeem_voucher("v_omen_globe")
        self.assertEqual(g.consumable_slots, before)


class TestTagTiming(unittest.TestCase):
    """P0-4 标签：跳过盲注当场结算。"""

    def test_immediate_tag_applies_on_skip(self):
        g = new_game(seed=3)
        g.dollars = 10
        g.blind_tags = {"Small": "tag_economy", "Big": None}
        g.skip_blind()
        self.assertEqual(g.dollars, 20)
        self.assertEqual(g.tags, [])

    def test_handy_uses_total_hands_played(self):
        from balatro_cli.core.effects import apply_tag

        g = new_game(seed=3)
        g.hands_played_total = 7
        g.dollars = 0
        self.assertTrue(apply_tag(g, Tag("tag_handy"), "immediate"))
        self.assertEqual(g.dollars, 7)

    def test_garbage_uses_unused_discards(self):
        from balatro_cli.core.effects import apply_tag

        g = new_game(seed=3)
        g.unused_discards = 4
        g.dollars = 0
        self.assertTrue(apply_tag(g, Tag("tag_garbage"), "immediate"))
        self.assertEqual(g.dollars, 4)

    def test_top_up_only_common(self):
        from balatro_cli.core.effects import apply_tag

        g = new_game(seed=3)
        apply_tag(g, Tag("tag_top_up"), "immediate")
        self.assertEqual(len(g.jokers), 2)
        self.assertTrue(all(centers_data.JOKERS[j.key]["r"] == 1 for j in g.jokers))

    def test_juggle_applies_at_round_start(self):
        g = new_game(seed=3)
        g.blind_tags = {"Small": "tag_juggle", "Big": None}
        base = g.hand_size
        g.skip_blind()
        g.select_blind()                     # 进入大盲注
        self.assertEqual(g.hand_size, base + 3)
        self.assertEqual(len(g.hand), g.hand_size)

    def test_voucher_tag_adds_extra_voucher(self):
        g = new_game(seed=3, blind=False)
        g.tags = [Tag("tag_voucher")]
        g.enter_shop()
        self.assertEqual(len(g.shop_offer_vouchers), len(g.shop_vouchers) + 1)

    def test_boss_tag_rerolls_boss(self):
        g = new_game(seed=3)
        g.blind_tags = {"Small": "tag_boss", "Big": None}
        g.skip_blind()
        self.assertIn(g.boss_key, BOSS_BLINDS)
        self.assertTrue(g.boss_rerolled)

    def test_coupon_only_marks_current_items(self):
        g = new_game(seed=3, blind=False)
        g.tags = [Tag("tag_coupon")]
        g.enter_shop()
        self.assertTrue(g.shop_free)
        self.assertTrue(all(g.shop_item_price(x) == 0 for x in g.shop_jokers))
        self.assertTrue(all(g.shop_item_price(x) == 0 for x in g.shop_boosters))
        self.assertNotEqual(g.voucher_price(), 0)     # 优惠券本身不免费


class TestFinalBosses(unittest.TestCase):
    """P0-5 决战头目 + 禁止跳过 Boss + 头目重掷。"""

    def boss_game(self, key: str, seed: int = 5):
        g = new_game(seed=seed, blind=False)
        g.ante, g.boss_key = 8, key
        g.blind_on_deck = "Boss"
        return g

    def test_cannot_skip_boss(self):
        g = self.boss_game("bl_final_bell")
        self.assertFalse(g.skip_blind())
        self.assertEqual(g.blind_on_deck, "Boss")

    def test_cerulean_bell_forces_selection(self):
        g = self.boss_game("bl_final_bell")
        g.select_blind()
        forced = [c for c in g.hand if c.forced_selection]
        self.assertEqual(len(forced), 1)
        self.assertTrue(forced[0].selected)
        idx = g.hand.index(forced[0])
        self.assertFalse(g.toggle_select(idx))        # 无法取消
        self.assertTrue(forced[0].selected)

    def test_verdant_leaf_debuffs_until_sell(self):
        g = self.boss_game("bl_final_leaf")
        g.jokers = [JokerItem(key="j_joker"), JokerItem(key="j_bull")]
        g.select_blind()
        self.assertTrue(all(c.debuffed for c in g.hand))
        g.dollars = 100
        self.assertTrue(g.sell_joker(0))
        self.assertFalse(any(c.debuffed for c in g.hand))
        self.assertTrue(g.boss_disabled())

    def test_crimson_heart_debuffs_one_joker_per_hand(self):
        g = self.boss_game("bl_final_heart")
        g.jokers = [JokerItem(key="j_joker"), JokerItem(key="j_bull"),
                    JokerItem(key="j_greedy_joker")]
        g.select_blind()
        select_cards(g, 2)
        g.play_selected()
        self.assertEqual(sum(1 for j in g.jokers if j.debuffed), 1)

    def test_directors_cut_reroll(self):
        g = new_game(seed=3, blind=False)
        self.assertFalse(g.boss_can_reroll())
        g.redeem_voucher("v_directors_cut")
        self.assertTrue(g.boss_can_reroll())
        g.dollars = 20
        self.assertTrue(g.reroll_boss())
        self.assertEqual(g.dollars, 10)
        self.assertFalse(g.boss_can_reroll())         # 每底注 1 次
        g.redeem_voucher("v_retcon")
        self.assertTrue(g.boss_can_reroll())


class TestJokerEffects(unittest.TestCase):
    """P1 小丑效果逐项。"""

    def test_raised_fist_only_lowest_once(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_raised_fist")]
        g.hand = cards("2-S", "K-H", "A-C")
        j = g.jokers[0]
        ef = calculate_joker(g, j, ctx(phase="individual", hand_being_evaluated=True,
                                       other_card=g.hand[0]))
        self.assertEqual(ef[0].mult, 4)               # 2 × 2
        self.assertEqual(calculate_joker(g, j, ctx(phase="individual", hand_being_evaluated=True,
                                                   other_card=g.hand[1])), [])
        # A 的 nominal 是 11，不是 14
        g.hand = cards("A-S")
        ef = calculate_joker(g, j, ctx(phase="individual", hand_being_evaluated=True,
                                       other_card=g.hand[0]))
        self.assertEqual(ef[0].mult, 22)

    def test_abstract_counts_itself(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_abstract")]
        ef = calculate_joker(g, g.jokers[0], ctx(phase="joker_main"))
        self.assertEqual(ef[0].mult, 3)
        g.jokers.append(JokerItem(key="j_joker"))
        ef = calculate_joker(g, g.jokers[0], ctx(phase="joker_main"))
        self.assertEqual(ef[0].mult, 6)

    def test_stencil_counts_itself(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_stencil")]
        ef = calculate_joker(g, g.jokers[0], ctx(phase="joker_main"))
        self.assertEqual(ef[0].x_mult, g.joker_slots)     # (槽位-1) + 1

    def test_odd_todd_excludes_jack(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_odd_todd")]
        for rank, expect in (("J", False), ("3", True), ("9", True), ("A", True)):
            c = Card(rank=rank, suit="S")
            ef = calculate_joker(g, g.jokers[0],
                                 ctx(phase="individual", other_card=c, scoring_cards=[c]))
            self.assertEqual(bool(ef), expect, rank)

    def test_photograph_first_face_not_first_card(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_photograph")]
        played = cards("2-C", "J-S", "J-H")
        first = calculate_joker(g, g.jokers[0],
                                ctx(phase="individual", other_card=played[1],
                                    scoring_cards=played, played_cards=played))
        self.assertEqual(first[0].x_mult, 2)
        none = calculate_joker(g, g.jokers[0],
                               ctx(phase="individual", other_card=played[0],
                                   scoring_cards=played, played_cards=played))
        self.assertEqual(none, [])

    def test_ice_cream_counts_before_decay(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_ice_cream")]
        j = g.jokers[0]
        self.assertEqual(calculate_joker(g, j, ctx(phase="joker_main"))[0].chips, 100)
        calculate_joker(g, j, ctx(phase="after"))
        self.assertEqual(calculate_joker(g, j, ctx(phase="joker_main"))[0].chips, 95)
        j.stat["chips"] = 5
        calculate_joker(g, j, ctx(phase="after"))
        self.assertEqual(g.jokers, [])                 # 降到 0 销毁

    def test_popcorn_decays_per_round(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_popcorn")]
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertEqual(g.jokers[0].stat["mult"], 16)

    def test_ride_the_bus_before_phase(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_ride_the_bus")]
        j = g.jokers[0]
        played = cards("2-C", "3-C")
        calculate_joker(g, j, ctx(phase="before", scoring_cards=played, played_cards=played))
        ef = calculate_joker(g, j, ctx(phase="joker_main", scoring_cards=played))
        self.assertEqual(ef[0].mult, 1)                # 当前手就吃到 +1
        face = cards("J-C")
        calculate_joker(g, j, ctx(phase="before", scoring_cards=face, played_cards=face))
        self.assertEqual(j.stat["mult"], 0)

    def test_green_joker_before_and_discard(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_green_joker")]
        j = g.jokers[0]
        calculate_joker(g, j, ctx(phase="before"))
        self.assertEqual(calculate_joker(g, j, ctx(phase="joker_main"))[0].mult, 1)
        set_hand(g, ["A-S", "A-H", "3-C", "4-D"])
        select_cards(g, 1)
        g.discard_selected()
        self.assertEqual(j.stat["mult"], 0)

    def test_space_joker_levels_before_scoring(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_space")]
        stub_roll(g, 0.0)
        before = g.hand_levels["Pair"]
        set_hand(g, ["A-S", "A-H", "3-C", "4-D", "5-S", "6-H", "7-D", "8-C"])
        select_cards(g, 2)
        g.play_selected()
        self.assertEqual(g.hand_levels["Pair"], before + 1)

    def test_reserved_parking_pays_per_held_face(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_reserved_parking")]
        stub_roll(g, 0.0)
        g.hand = cards("J-S", "Q-H", "2-C")
        gained = 0
        for c in g.hand:
            for ef in calculate_joker(g, g.jokers[0],
                                      ctx(phase="individual", hand_being_evaluated=True,
                                          other_card=c)):
                gained += ef.dollars
        self.assertEqual(gained, 2)

    def test_cloud_9_counts_all_playing_cards(self):
        from balatro_cli.core.effects import joker_dollar_bonus

        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_cloud_9")]
        nine = Card(rank="9", suit="S")
        g.deck.cards = [nine]
        g._round_cards = [Card(rank="9", suit="H")]
        g.hand = []
        self.assertEqual(joker_dollar_bonus(g, g.jokers[0]), 2)

    def test_erosion_uses_starting_deck_size(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_erosion")]
        g.starting_deck_size = 52
        g.deck.cards = []
        g.hand = []
        g._round_cards = [Card(rank="2", suit="S")]
        ef = calculate_joker(g, g.jokers[0], ctx(phase="joker_main"))
        self.assertEqual(ef[0].mult, 4 * 51)

    def test_to_the_moon_respects_interest_cap(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_to_the_moon")]
        g.dollars = 100
        g.chips = g.current_blind_chips()
        before = g.dollars
        g.end_round()
        # 利息 = 2 × min(100//5, 25//5) = 2 × 5 = 10；再加盲注奖励与剩余次数
        self.assertEqual(g.dollars - before, 3 + 10 + g.hands_left * 1)

    def test_hit_the_road_resets_each_round(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_hit_the_road")]
        g.jokers[0].stat["jacks"] = 4
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertEqual(g.jokers[0].stat["jacks"], 0)

    def test_loyalty_card_counts_from_acquisition(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_loyalty_card")]
        j = g.jokers[0]
        got = []
        for _ in range(6):
            calculate_joker(g, j, ctx(phase="before"))
            got.append(bool(calculate_joker(g, j, ctx(phase="joker_main"))))
        self.assertEqual(got, [False, False, False, False, True, False])

    def test_obelisk_needs_strictly_more(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_obelisk")]
        j = g.jokers[0]
        j.stat["x_mult"] = 3.0
        g.hands_count = {"Pair": 5, "High Card": 5}
        calculate_joker(g, j, ctx(phase="before", scoring_name="Pair"))
        self.assertEqual(j.stat["x_mult"], 3.2)         # 并列 → 不重置，继续成长
        g.hands_count = {"Pair": 6, "High Card": 5}
        calculate_joker(g, j, ctx(phase="before", scoring_name="Pair"))
        self.assertEqual(j.stat["x_mult"], 1.0)         # 严格多于 → 重置

    def test_blackboard_counts_debuffed_cards(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_blackboard")]
        g.hand = cards("A-S", "K-C")
        g.hand[0].debuffed = True
        ef = calculate_joker(g, g.jokers[0], ctx(phase="joker_main"))
        self.assertEqual(ef[0].x_mult, 3)

    def test_campfire_grows_on_sell_and_resets_on_boss(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_campfire"), JokerItem(key="j_joker")]
        g.dollars = 100
        g.sell_joker(1)
        self.assertAlmostEqual(g.jokers[0].stat["x_mult"], 1.25)
        g.chips = g.current_blind_chips()
        g.boss_key = g.blind_key or "bl_club"
        g.blind_on_deck = "Boss"
        g.blind_key = g.boss_key
        g.end_round()
        self.assertAlmostEqual(g.jokers[0].stat["x_mult"], 1.0)

    def test_mr_bones_needs_25_percent_and_destroys_itself(self):
        g = new_game(seed=1)
        g.jokers = [JokerItem(key="j_mr_bones")]
        target = g.current_blind_chips()
        g.chips = target // 5                    # 不足 25%
        self.assertFalse(g.end_round())
        self.assertEqual(len(g.jokers), 1)       # 未救场

        h = new_game(seed=1)
        h.jokers = [JokerItem(key="j_mr_bones")]
        h.chips = int(h.current_blind_chips() * 0.3)
        self.assertTrue(h.end_round())
        self.assertEqual(h.jokers, [])           # 救场后销毁

    def test_matador_pays_on_debuffed_hand(self):
        g = new_game(seed=1)
        g.blind_key = "bl_psychic"
        g.jokers = [JokerItem(key="j_matador")]
        g.dollars = 10
        set_hand(g, ["A-S", "A-H", "3-C", "4-D", "5-S", "6-H", "7-D", "8-C"])
        select_cards(g, 2)                        # 通灵者要求 5 张 → 本手不计分
        g.play_selected()
        self.assertEqual(g.dollars, 18)

    def test_chaos_stacks(self):
        g = new_game(seed=3, blind=False)
        g.jokers = [JokerItem(key="j_chaos"), JokerItem(key="j_chaos")]
        g.enter_shop()
        self.assertEqual(g.free_rerolls, 2)

    def test_oops_doubles_probability_not_denominator(self):
        g = new_game(seed=1)
        stub_roll(g, 0.28)
        self.assertFalse(roll_prob(g, 7, "x"))     # 1/7 ≈ 0.143
        g.jokers = [JokerItem(key="j_oops")]
        self.assertTrue(roll_prob(g, 7, "x"))      # 2/7 ≈ 0.286


class TestStakes(unittest.TestCase):
    """P2-1 赌注：8 档难度梯度（game.lua 2049-2059）。"""

    def test_red_stake_removes_small_blind_reward(self):
        g = Game(seed=1)
        g.start_run("b_red", "stake_red")
        g.select_blind()                       # 小盲注
        g.chips = g.current_blind_chips()
        before = g.dollars
        g.end_round()
        # 只有剩余手牌/弃牌收入，没有 $3 盲注奖励
        self.assertEqual(g.dollars - before, g.hands_left * 1 + g.money_per_discard * g.discards_left)

    def test_green_and_purple_scaling(self):
        g = Game(seed=1)
        g.start_run("b_red", "stake_green")
        self.assertEqual(g.ante_scaling, 2)
        h = Game(seed=1)
        h.start_run("b_red", "stake_purple")
        self.assertEqual(h.ante_scaling, 3)
        # 紫赌注包含绿赌注，仍按 3（覆盖而不是相乘）
        self.assertEqual(h.stake_level, 6)

    def test_blue_stake_costs_a_discard(self):
        g = Game(seed=1)
        g.start_run("b_red", "stake_blue")
        g.select_blind()
        self.assertEqual(g.discards_left, 3)    # 红牌组 4 - 1

    def test_black_orange_gold_stickers(self):
        g = Game(seed=1)
        g.start_run("b_red", "stake_black")
        self.assertTrue(g.enable_eternals_in_shop)
        self.assertFalse(g.enable_rentals_in_shop)
        h = Game(seed=1)
        h.start_run("b_red", "stake_gold")
        self.assertTrue(h.enable_perishables_in_shop)
        self.assertTrue(h.enable_rentals_in_shop)

    def test_shop_joker_may_get_stickers_only_with_stake(self):
        g = Game(seed=1)
        g.start_run("b_red", "stake_white")
        g.enter_shop()
        got = [g.make_joker("j_joker") for _ in range(30)]
        self.assertFalse(any(j.eternal or j.perishable or j.rental for j in got))

        h = Game(seed=1)
        h.start_run("b_red", "stake_gold")
        h.enable_eternals_in_shop = False       # 单独验证租赁
        got = [h.make_joker("j_joker") for _ in range(60)]
        self.assertTrue(any(j.rental for j in got))



class TestRestart(unittest.TestCase):
    """同一 Game 对象重新开局时，run 级统计必须清零（重开 / 读档的前置）。"""

    def test_start_run_resets_run_state(self):
        g = new_game(seed=3)
        g.dollars = 99
        g.jokers = [JokerItem(key="j_joker")]
        g.consumeables = [ConsumableItem(key="c_fool")]
        g.tags = [Tag("tag_handy")]
        g.hands_played_total = 7
        g.glass_broken = 3
        g.skip_blind()
        g.start_run("b_blue")
        self.assertEqual(g.dollars, 4)
        self.assertEqual(g.jokers, [])
        self.assertEqual(g.consumeables, [])
        self.assertEqual(g.tags, [])
        self.assertEqual(g.hands_played_total, 0)
        self.assertEqual(g.glass_broken, 0)
        self.assertEqual(g.ante, 1)
        self.assertEqual(g.deck_key, "b_blue")



if __name__ == "__main__":
    unittest.main()
