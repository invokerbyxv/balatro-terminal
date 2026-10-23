"""CLI 冒烟测试：屏幕上每个场景都能渲染且不抛异常。

不做像素级断言（终端输出含颜色/宽度处理），只保证拆分后各 mixin 能拿到
自己需要的符号与状态；配合 test_regression 的行为测试提供护栏。
"""
from __future__ import annotations

import contextlib
import io
import re
import unittest
from unittest.mock import patch

from balatro_cli.cli.screens_pkg import App
from balatro_cli.core.game import Game
from balatro_cli.core.items import BoosterPack, ConsumableItem, JokerItem, Tag
from tests.helpers import set_hand

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def plain(text: str) -> str:
    """去掉 ANSI 颜色码，便于断言屏幕文本。"""
    return _ANSI_RE.sub("", text)


def make_app(seed: int = 42) -> App:
    app = App()
    g = Game(seed=seed)
    g.start_run("b_red")
    g.select_blind()
    app.game = g
    return app


def render(fn, prompts=("0",)) -> str:
    buf = io.StringIO()
    answers = iter(prompts)
    with contextlib.redirect_stdout(buf), \
            patch("balatro_cli.cli.ui.prompt", lambda *a, **k: next(answers, "0")), \
            patch("builtins.input", lambda *a, **k: ""):
        fn()
    return buf.getvalue()


class TestScreensRender(unittest.TestCase):
    def assert_renders(self, fn, prompts=("0",), *, nonempty=True):
        out = render(fn, prompts)
        if nonempty:
            self.assertTrue(out.strip())
        return out

    def test_main_screens(self):
        app = make_app()
        self.assert_renders(app._menu)
        self.assert_renders(app._deck_select)
        self.assert_renders(app._blind_select)
        self.assert_renders(app._play)
        self.assert_renders(app._info)
        self.assert_renders(app._items)
        self.assert_renders(app._collection)

    def test_collection_pages(self):
        app = make_app()
        self.assert_renders(app._list_jokers)
        self.assert_renders(lambda: app._list_consumables("tarot"))
        self.assert_renders(app._list_vouchers)
        self.assert_renders(app._list_decks)

    def test_shop_and_pack(self):
        app = make_app()
        app.game.enter_shop()
        self.assert_renders(app._shop, ("x",))

        app = make_app()
        app.game.enter_shop()
        app.game.dollars = 100
        app.game.shop_boosters = [BoosterPack("p_arcana_normal", 4, 4)]
        app.game.buy_booster(0)
        self.assert_renders(app._pack)

    def test_tag_pack_opens_on_shop_entry(self):
        # 跳过盲注拿到的「小丑」标签会在进商店时开一个免费卡包，界面应直接进入卡包
        app = make_app()
        app.game.tags = [Tag(key="tag_buffoon")]
        app._enter_shop()
        self.assertEqual(app.state, "pack")
        self.assertEqual(app.game.pending_pack["key"], "p_buffoon_mega")

    def test_pack_screen_sells_before_picking(self):
        app = make_app()
        g = app.game
        g.enter_shop()
        g.dollars = 100
        g.jokers = [JokerItem("j_joker") for _ in range(g.joker_slots)]
        g.shop_boosters = [BoosterPack("p_buffoon_normal", 4, 4)]
        g.buy_booster(0)
        app.state = "pack"
        # 小丑栏已满：取牌被拒绝，停在卡包界面（不再进已删除的 pack_sell 状态）
        self.assert_renders(app._pack, ("1",))
        self.assertEqual(app.state, "pack")
        self.assertIsNotNone(g.pending_pack)
        # 卡包界面可以直接进售卖界面，返回后仍回到卡包
        self.assert_renders(app._pack, ("s",))
        self.assertEqual((app.state, app.return_state), ("sell", "pack"))
        self.assert_renders(app._sell_screen, ("0",))
        self.assertEqual(app.state, "pack")

    def test_round_end_screens(self):
        app = make_app()
        app.game.chips = app.game.current_blind_chips()
        self.assert_renders(app._settle)

        app = make_app()
        app.game.run_lost = True
        self.assert_renders(app._over, ("2",))

        app = make_app()
        app.game.ante = 8
        app.game.run_won = True
        self.assert_renders(app._win_screen, ("2",))

    def test_consume_and_sell(self):
        app = make_app()
        app.game.consumeables.append(ConsumableItem("c_mercury"))
        self.assert_renders(app._consume)

        app = make_app()
        app.game.jokers.append(JokerItem("j_bull"))
        self.assert_renders(app._sell_screen)

    def test_consume_wheel_without_eligible_joker_keeps_card(self):
        """没有可附加版本的小丑：提示一句，塔罗留在消耗牌栏。"""
        app = make_app()
        g = app.game
        g.jokers.append(JokerItem("j_joker", edition="negative"))
        g.consumeables.append(ConsumableItem("c_wheel_of_fortune"))
        self.assert_renders(app._consume, ("1",))
        self.assertEqual([c.key for c in g.consumeables], ["c_wheel_of_fortune"])
        self.assertEqual(g.jokers[0].edition, "negative")
        self.assertIn("没有可附加版本的小丑", plain(" ".join(app.log)))

    def test_target_screen(self):
        app = make_app()
        g = app.game
        g.consumeables.append(ConsumableItem("c_magician"))
        self.assertEqual(g.use_consumable(0), "needs_target")
        app.target_needed = 2
        app.target_min = 1
        self.assert_renders(app._target, ("q",))

    def test_target_screen_rejects_editioned_card(self):
        """灵光选了已有版本的牌：提示原因、留在选牌界面、塔罗不消耗。"""
        app = make_app()
        g = app.game
        set_hand(g, ["A-S", "K-H"])
        g.hand[0].edition = "holo"
        g.consumeables.append(ConsumableItem("c_aura"))
        self.assertEqual(g.use_consumable(0), "needs_target")
        app.target_needed = 1
        app.target_min = 1
        g.hand[0].selected = True
        self.assert_renders(app._target, ("0",))
        self.assertEqual(g.hand[0].edition, "holo")
        self.assertEqual([c.key for c in g.consumeables], ["c_aura"])
        self.assertIn("目标牌已有版本", plain(" ".join(app.log)))

    def test_full_play_loop_does_not_crash(self):
        """从选牌到出牌再到结算，走一遍状态机。"""
        app = make_app()
        g = app.game
        for c in g.hand[:3]:
            c.selected = True
        self.assert_renders(app._play)          # 默认输入 "0" 会被当成选牌命令
        g.play_selected()
        self.assertTrue(g.messages or g.chips >= 0)

    def test_play_hand_type_preview(self):
        """出牌界面：选牌后显示牌型、等级数值与计分牌。"""
        app = make_app()
        g = app.game
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "Q-S", "2-C", "3-D", "4-D"])
        for c in g.hand:
            c.selected = False
        g.hand[0].selected = g.hand[1].selected = g.hand[2].selected = True
        g.hand_levels["Pair"] = 3
        out = plain(self.assert_renders(app._play))
        self.assertIn("牌型：对子 · Lv.3（40 筹码 × 4 倍率）", out)
        self.assertIn("计分牌 #1 #2", out)
        self.assertIn("不计分 #3", out)

    def test_play_previews_whole_hand_when_nothing_selected(self):
        """未选牌时给出整手最佳牌型的预判。"""
        app = make_app()
        g = app.game
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "Q-S", "2-C", "3-D", "4-D"])
        for c in g.hand:
            c.selected = False
        out = plain(self.assert_renders(app._play))
        self.assertIn("牌型：—", out)
        self.assertIn("整手最佳：两对", out)

    def test_play_marks_all_scoring_cards(self):
        """五张同花全部计分时显示「全部计分」，不再逐个列序号。"""
        app = make_app()
        g = app.game
        set_hand(g, ["A-S", "K-S", "Q-S", "J-S", "9-S", "2-C", "3-D", "4-D"])
        for i, c in enumerate(g.hand):
            c.selected = i < 5
        out = plain(self.assert_renders(app._play))
        self.assertIn("牌型：同花 · Lv.1（35 筹码 × 4 倍率）", out)
        self.assertIn("全部计分", out)

    def test_play_full_house_marks_pair_as_scoring(self):
        """葫芦的三条与对子都计分，不应把对子标成「不计分」。"""
        app = make_app()
        g = app.game
        set_hand(g, ["A-S", "A-C", "K-S", "Q-S", "Q-H", "Q-C", "J-H", "J-C"])
        for i, c in enumerate(g.hand):
            c.selected = i in {0, 1, 3, 4, 5}
        out = plain(self.assert_renders(app._play))
        self.assertIn("牌型：葫芦", out)
        self.assertIn("全部计分", out)
        self.assertNotIn("不计分", out)

    def test_play_shows_royal_flush_name(self):
        """同花顺中的 10-A 按结算的口径显示为「皇家同花顺」。"""
        app = make_app()
        g = app.game
        set_hand(g, ["10-S", "J-S", "Q-S", "K-S", "A-S", "2-C", "3-D", "4-D"])
        for i, c in enumerate(g.hand):
            c.selected = i < 5
        out = plain(self.assert_renders(app._play))
        self.assertIn("牌型：皇家同花顺", out)

    def test_play_hides_scoring_marks_when_hand_is_blocked(self):
        """盲注让本手不计分时，牌型行不再标计分牌（原因由下一行的警告说明）。"""
        app = make_app()
        g = app.game
        set_hand(g, ["A-S", "A-H", "K-S", "K-H", "Q-S", "2-C", "3-D", "4-D"])
        for c in g.hand:
            c.selected = False
        g.hand[0].selected = g.hand[1].selected = g.hand[2].selected = True
        g.blind_key = "bl_psychic"
        out = plain(self.assert_renders(app._play))
        self.assertIn("牌型：对子", out)
        self.assertNotIn("计分牌", out)
        self.assertIn("⚠ 通灵者", out)

    def test_parse_indices(self):
        app = make_app()
        self.assertEqual(app._parse_indices("1 3 5", 8), {0, 2, 4})
        self.assertEqual(app._parse_indices("2-4", 8), {1, 2, 3})
        self.assertEqual(app._parse_indices("9", 8), set())
        self.assertEqual(app._parse_indices("1,2", 2), {0, 1})


if __name__ == "__main__":
    unittest.main()
