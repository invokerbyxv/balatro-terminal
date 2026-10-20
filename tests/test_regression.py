"""回归测试：固定种子 + 已知断言。

这组测试的目的不是覆盖全部规则，而是在重构（拆分模块、改分发表）时
提供"行为没有变"的护栏。每条断言都对应一个曾经修过或有明确出处的行为。
"""
from __future__ import annotations

import unittest

from balatro_cli.core.card import ENHANCED, RANKS, SUITS, Card
from balatro_cli.core.game import Game
from balatro_cli.core.hand_eval import evaluate_poker_hand, best_hand
from balatro_cli.core.items import BoosterPack, ConsumableItem, JokerItem, Tag
from balatro_cli.core.scoring import card_edition, evaluate_play, blocked_play_reason
from tests.helpers import (cards, greedy_play, new_game, play_rounds, select_cards,
                           select_rank, set_hand, snapshot)


class TestHandEvaluation(unittest.TestCase):
    def check(self, specs, expected_name, **kw):
        name, _ = evaluate_poker_hand(cards(*specs), **kw)
        self.assertEqual(name, expected_name, specs)

    def test_basic_hands(self):
        self.check(["A-S", "A-H", "K-S", "K-H", "2-C"], "Two Pair")
        self.check(["A-S", "A-H", "A-C", "K-S", "K-H"], "Full House")
        self.check(["A-S", "K-S", "Q-S", "J-S", "10-S"], "Straight Flush")
        self.check(["2-S", "3-S", "4-S", "5-S", "6-S"], "Straight Flush")
        self.check(["9-S", "8-H", "7-C", "6-D", "5-S"], "Straight")
        self.check(["A-S", "2-H", "3-C", "4-D", "5-S"], "Straight")
        self.check(["A-S", "K-S", "Q-S", "J-S", "9-S"], "Flush")
        self.check(["A-S", "K-H", "Q-C", "J-D", "9-S"], "High Card")
        self.check(["3-S", "3-H", "3-C", "3-D", "3-S"], "Five of a Kind")

    def test_four_fingers_and_shortcut(self):
        # 四根手指：4 张同花即可（用不连续点数，避免同时凑成顺子）
        self.check(["A-S", "K-S", "Q-S", "9-S", "2-H"], "Flush", four_fingers=True)
        # 缺 10 的顺子需要捷径
        self.check(["J-S", "Q-H", "K-C", "A-D", "9-S"], "High Card")
        self.check(["J-S", "Q-H", "K-C", "A-D", "9-S"], "Straight", shortcut=True)

    def test_best_hand_preview(self):
        hand = cards("A-S", "A-H", "K-S", "K-H", "Q-S", "Q-H", "2-C")
        name, _ = best_hand(hand)
        self.assertEqual(name, "Two Pair")


class TestScoring(unittest.TestCase):
    def test_plain_pair_score(self):
        g = new_game(seed=7)
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "2-C", "3-D", "4-S", "5-H"])
        select_cards(g, 5)          # A,A,K,K,2 → 两对
        g.play_selected()
        # 两对基础 20 筹码 + 计分牌 A,A,K,K 共 42 → 62 × 2 = 124
        self.assertEqual(g.chips, 124)

    def test_polychrome_edition_applies(self):
        c = Card(rank="A", suit="S", edition="polychrome")
        self.assertEqual(card_edition(None, c), (0, 0, 1.5))
        g = new_game(seed=7)
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "2-C", "3-D", "4-S", "5-H"])
        g.hand[0].edition = "polychrome"
        select_cards(g, 5)
        g.play_selected()
        self.assertEqual(g.chips, 186)     # 124 × 1.5

    def test_hand_level_applies(self):
        g = new_game(seed=7)
        g.hand_levels["Two Pair"] = 3
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "2-C", "3-D", "4-S", "5-H"])
        select_cards(g, 5)
        g.play_selected()
        self.assertGreater(g.chips, 124)

    def test_joker_mult(self):
        g = new_game(seed=7)
        g.jokers.append(JokerItem(key="j_joker"))
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "2-C", "3-D", "4-S", "5-H"])
        select_cards(g, 5)
        g.play_selected()
        # 62 筹码 × (2 + 4) 倍率
        self.assertEqual(g.chips, 372)


class TestBlindsAndEconomy(unittest.TestCase):
    def test_disabled_wall_and_vessel_thresholds(self):
        # 墙 mult=4、紫瓶 mult=6；Blind:disable 分别除以 2 与 3，禁用后都是 ×2
        g = new_game(seed=1, blind=False)
        g.ante = 2
        normal = {}
        for boss in ("bl_wall", "bl_final_vessel", "bl_club"):
            g.boss_key, g.blind_on_deck, g.blind_key = boss, "Boss", boss
            normal[boss] = g.current_blind_chips()
        self.assertEqual(normal["bl_wall"], normal["bl_club"] * 2)          # 4 / 2
        self.assertEqual(normal["bl_final_vessel"], normal["bl_club"] * 3)  # 6 / 2
        for boss in ("bl_wall", "bl_final_vessel", "bl_club"):
            g.boss_key, g.blind_on_deck, g.blind_key = boss, "Boss", boss
            g.boss_disabled_round = True
            # 墙 4/2=2、紫瓶 6/3=2、俱乐部本身就是 ×2
            self.assertEqual(g.current_blind_chips(), normal["bl_club"], boss)

    def test_hand_size_modifiers_survive_next_round(self):
        g = new_game(seed=1)
        base = g.round_hand_size()
        # 灵应盘：永久 -1
        g.consumeables.append(ConsumableItem(key="c_ouija"))
        g.use_consumable(0)
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertEqual(g.round_hand_size(), base - 1)
        # 画笔：下一回合 +1
        g.redeem_voucher("v_paint_brush")
        self.assertEqual(g.round_hand_size(), base)

    def test_juggle_tag_is_temporary(self):
        g = new_game(seed=1)
        g.temp_hand_size = 3
        self.assertEqual(g.round_hand_size(), 11)
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertEqual(g.round_hand_size("bl_big"), 8)

    def test_blind_chips_scale_with_ante(self):
        g = new_game(seed=1, blind=False)
        g.ante = 1
        small = g.current_blind_chips()
        g.ante = 2
        self.assertGreater(g.current_blind_chips(), small)


class TestBlockedPlay(unittest.TestCase):
    def test_psychic_requires_five(self):
        g = new_game(seed=1)
        g.blind_key = "bl_psychic"
        self.assertIsNotNone(blocked_play_reason(g, cards("A-S", "A-H")))
        self.assertIsNone(blocked_play_reason(g, cards("A-S", "A-H", "K-S", "K-H", "2-C")))

    def test_eye_rejects_repeat_hand(self):
        g = new_game(seed=1)
        g.blind_key = "bl_eye"
        g.round_hand_played = ["Pair"]
        self.assertIsNotNone(blocked_play_reason(g, cards("A-S", "A-H")))
        self.assertIsNone(blocked_play_reason(g, cards("A-S", "K-H")))

    def test_chicot_disables_all(self):
        g = new_game(seed=1)
        g.blind_key = "bl_psychic"
        g.jokers.append(JokerItem(key="j_chicot"))
        self.assertIsNone(blocked_play_reason(g, cards("A-S", "A-H")))


class TestShopAndPacks(unittest.TestCase):
    def test_shop_has_items_and_voucher(self):
        g = new_game(seed=3, blind=False)
        g.enter_shop()
        self.assertTrue(g.shop_jokers)
        self.assertEqual(len(g.shop_boosters), 2)

    def test_shop_card_slot_generates_and_buys(self):
        # 回归：_make_card_for_shop 曾漏导入 RANKS/SUITS/ENHANCED，
        # 商店随机到「增强卡牌」格子时（打出制胜一手后进商店）整局崩溃。
        g = new_game(seed=3, blind=False)
        g.enter_shop()
        card = g._make_card_for_shop()
        self.assertIsInstance(card, Card)
        self.assertIn(card.rank, RANKS)
        self.assertIn(card.suit, SUITS)
        self.assertIn(card.enhanced, ENHANCED)
        self.assertGreaterEqual(g.shop_item_price(card), 1)
        g.shop_jokers = [card]
        g.dollars = 100
        self.assertTrue(g.buy_shop_item(0))

    def test_enter_shop_applies_tags(self):
        # 回归：ConsumableMixin._apply_tag 曾漏导入 effects.apply_tag，
        # 带着标签进商店（跳过盲注后必然发生）时 NameError 崩整局。
        # 注意 test_all_tags_apply 直接调 effects.apply_tag，绕过了 mixin，抓不到这类漏导入。
        g = new_game(seed=3, blind=False)
        g.dollars = 10
        g.tags = [Tag(key="tag_economy")]
        g.enter_shop()                          # 不应抛异常
        self.assertEqual(g.dollars, 20)         # 经济标签：$10 -> +$10

    def test_shop_close_keeps_only_persistent_tags(self):
        # 回归：shop_closed 曾漏导入 PERSISTENT_TAGS。
        g = new_game(seed=3, blind=False)
        g.enter_shop()
        g.tags = [Tag("tag_double"), Tag("tag_handy")]
        g.shop_closed()
        self.assertEqual([t.key for t in g.tags], ["tag_double"])

    def test_reroll_cost_increases(self):
        g = new_game(seed=3, blind=False)
        g.enter_shop()
        first = g.calculate_reroll_cost()
        g.dollars = 100
        g.reroll_shop()
        self.assertGreater(g.calculate_reroll_cost(), first)

    def test_buy_joker_takes_a_slot(self):
        g = new_game(seed=3, blind=False)
        g.enter_shop()
        g.dollars = 100
        idx = next(i for i, x in enumerate(g.shop_jokers) if isinstance(x, JokerItem))
        before = len(g.jokers)
        self.assertTrue(g.buy_shop_item(idx))
        self.assertEqual(len(g.jokers), before + 1)

    def test_pack_choose_adds_consumeable(self):
        g = new_game(seed=3, blind=False)
        g.enter_shop()
        g.dollars = 100
        # 商店卡包是随机抽的；直接指定一个塔罗包，避免依赖种子
        bp = BoosterPack(key="p_arcana_normal", cost=4, buy_cost=4)
        g.shop_boosters = [bp]
        self.assertTrue(g.buy_booster(0))
        self.assertIsNotNone(g.pending_pack)
        status = g.pack_choose([0])
        self.assertIn(status, ("done", "needs_sell"))
        if status == "done":
            self.assertIsNone(g.pending_pack)


class TestBossDetails(unittest.TestCase):
    def serpent_game(self, seed=1):
        g = new_game(seed=seed, blind=False)
        g.ante, g.boss_key = 2, "bl_serpent"
        g.blind_on_deck = "Boss"
        g.select_blind()
        self.assertEqual(g.blind_key, "bl_serpent")
        return g

    def test_serpent_draws_three_not_to_limit(self):
        # 出 5 张后剩 3 张，蛇再抽 3 张 → 6 张
        g = self.serpent_game()
        select_cards(g, 5)
        g.play_selected()
        self.assertEqual(len(g.hand), 6)

    def test_serpent_also_on_discard(self):
        # 弃 2 张后剩 6 张，蛇再抽 3 张 → 9 张
        g = self.serpent_game()
        select_cards(g, 2)
        g.discard_selected()
        self.assertEqual(len(g.hand), 9)

    def test_serpent_not_on_first_deal(self):
        g = self.serpent_game()
        self.assertEqual(len(g.hand), 8)

    def test_serpent_disabled_by_chicot(self):
        g = self.serpent_game()
        g.jokers.append(JokerItem(key="j_chicot"))
        select_cards(g, 5)
        g.play_selected()
        self.assertEqual(len(g.hand), 8)

    def test_rocket_upgrades_only_after_boss(self):
        # 普通盲注：不增长，收入仍是 1
        g = new_game(seed=1)
        g.jokers.append(JokerItem(key="j_rocket"))
        g.chips = g.current_blind_chips()
        g.end_round()
        self.assertEqual(g.jokers[0].stat.get("dollars", 1), 1)
        # 头目盲注：+2
        b = new_game(seed=1, blind=False)
        b.ante, b.boss_key = 2, "bl_club"
        b.blind_on_deck, b.blind_key = "Boss", "bl_club"
        b.jokers.append(JokerItem(key="j_rocket"))
        b.chips = b.current_blind_chips()
        b.end_round()
        self.assertEqual(b.jokers[0].stat["dollars"], 3)


class TestHookCoverage(unittest.TestCase):
    """确保每条钩子分支都能被实际执行到（防止拆分时漏 import 之类的问题）。"""

    def test_all_hooks_run(self):
        from balatro_cli.core import effects

        cases = [
            (effects.on_blind_select, ()),
            (effects.on_discard, ([Card("A", "S"), Card("K", "H"), Card("J", "D")],)),
            (effects.on_end_round, (True,)),
        ]
        keys = set()
        for table in (effects._BLIND_SELECT_HOOKS, effects._DISCARD_HOOKS,
                      effects._END_ROUND_HOOKS):
            keys |= set(table)
        self.assertTrue(keys)

        for joker_key in sorted(keys):
            for fn, args in cases:
                g = new_game(seed=5)
                g.jokers = [JokerItem(key=joker_key)]
                g.dollars = 20
                try:
                    fn(g, *args)
                except Exception as exc:       # noqa: BLE001 - 测试里要看到具体是哪个
                    self.fail(f"{fn.__name__} + {joker_key}: {type(exc).__name__}: {exc}")

    def test_hooks_with_blueprint_forward(self):
        from balatro_cli.core import effects

        for joker_key in sorted(set(effects._BLIND_SELECT_HOOKS) |
                                set(effects._DISCARD_HOOKS) |
                                set(effects._END_ROUND_HOOKS)):
            g = new_game(seed=5)
            g.jokers = [JokerItem(key="j_blueprint"), JokerItem(key=joker_key)]
            for fn, args in ((effects.on_blind_select, ()),
                             (effects.on_discard, ([Card("A", "S")],)),
                             (effects.on_end_round, (False,))):
                try:
                    fn(g, *args)
                except Exception as exc:   # noqa: BLE001
                    self.fail(f"blueprint->{joker_key} {fn.__name__}: {exc}")

    def test_all_tags_apply(self):
        from balatro_cli.data.tags import TAGS
        from balatro_cli.core.effects import apply_tag
        for key in TAGS:
            g = new_game(seed=5)
            g.dollars = 20
            apply_tag(g, Tag(key=key))


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_run(self):
        runs = []
        for _ in range(2):
            g = new_game(seed=2024)
            play_rounds(g, 12)
            runs.append(snapshot(g))
        self.assertEqual(runs[0], runs[1])

    def test_seed_actually_varies(self):
        a = new_game(seed=1)
        b = new_game(seed=2)
        self.assertNotEqual(snapshot(a)["hand"], snapshot(b)["hand"])

    def test_no_card_leak_or_duplicate(self):
        g = new_game(seed=2024)
        play_rounds(g, 12)
        ids = [id(c) for c in g.hand + g._round_cards + g.deck.cards]
        self.assertEqual(len(ids), len(set(ids)))
        # 52 张基础牌中可能被销毁，但不应凭空增加
        self.assertLessEqual(len(ids), 52 + 10)


class TestConsumables(unittest.TestCase):
    def test_every_consumable_is_usable(self):
        from balatro_cli.data.consumables import ALL_CONSUMABLES
        for key in ALL_CONSUMABLES:
            g = new_game(seed=5)
            g.consumeables.append(ConsumableItem(key=key))
            status = g.use_consumable(0)
            if status == "needs_target":
                info = ALL_CONSUMABLES[key]
                n = max(info.get("min_highlighted", 1), 1)
                status = g.finish_consumable_target(list(range(n)))
            self.assertEqual(status, "done", key)

    def test_planet_levels_hand(self):
        g = new_game(seed=5)
        g.consumeables.append(ConsumableItem(key="c_mercury"))
        g.use_consumable(0)
        self.assertEqual(g.hand_levels["Pair"], 2)


class TestRunFlow(unittest.TestCase):
    def test_start_run_applies_deck_config(self):
        g = Game(seed=1)
        g.start_run("b_black")
        self.assertEqual(g.hands_left, 3)
        self.assertEqual(g.joker_slots, 6)

    def test_end_round_win_advances_blind(self):
        g = new_game(seed=1)
        self.assertEqual(g.blind_on_deck, "Small")
        g.chips = g.current_blind_chips()
        self.assertTrue(g.end_round())
        self.assertEqual(g.blind_on_deck, "Big")
        self.assertIsNone(g.blind_key)

    def test_end_round_loss(self):
        g = new_game(seed=1)
        self.assertFalse(g.end_round())
        self.assertTrue(g.run_lost)

    def test_endless_after_win(self):
        g = new_game(seed=1, blind=False)
        g.ante = 8
        g.run_won = True
        self.assertTrue(g.enter_endless())
        self.assertEqual(g.ante, 9)


if __name__ == "__main__":
    unittest.main()
