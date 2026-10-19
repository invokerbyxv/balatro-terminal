"""CLI 冒烟测试：屏幕上每个场景都能渲染且不抛异常。

不做像素级断言（终端输出含颜色/宽度处理），只保证拆分后各 mixin 能拿到
自己需要的符号与状态；配合 test_regression 的行为测试提供护栏。
"""
from __future__ import annotations

import contextlib
import io
import unittest
from unittest.mock import patch

from balatro_cli.cli.screens_pkg import App
from balatro_cli.core.game import Game
from balatro_cli.core.items import BoosterPack, ConsumableItem, JokerItem
from tests.helpers import new_game


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

    def test_target_screen(self):
        app = make_app()
        g = app.game
        g.consumeables.append(ConsumableItem("c_magician"))
        self.assertEqual(g.use_consumable(0), "needs_target")
        app.target_needed = 2
        app.target_min = 1
        self.assert_renders(app._target, ("q",))

    def test_full_play_loop_does_not_crash(self):
        """从选牌到出牌再到结算，走一遍状态机。"""
        app = make_app()
        g = app.game
        for c in g.hand[:3]:
            c.selected = True
        self.assert_renders(app._play)          # 默认输入 "0" 会被当成选牌命令
        g.play_selected()
        self.assertTrue(g.messages or g.chips >= 0)

    def test_parse_indices(self):
        app = make_app()
        self.assertEqual(app._parse_indices("1 3 5", 8), {0, 2, 4})
        self.assertEqual(app._parse_indices("2-4", 8), {1, 2, 3})
        self.assertEqual(app._parse_indices("9", 8), set())
        self.assertEqual(app._parse_indices("1,2", 2), {0, 1})


if __name__ == "__main__":
    unittest.main()
