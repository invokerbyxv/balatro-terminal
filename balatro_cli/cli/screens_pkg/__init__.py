"""CLI 场景包：App 由若干 mixin 组合而成。

- common.py  共享渲染、输入与状态工具
- menu.py    主菜单、牌组选择、结算、收藏
- round.py   盲注选择、出牌、消耗牌、售卖
- shop.py    商店与卡包

各 mixin 共用同一份 ``self``（game / log / state / regions），按屏幕职责
拆分只是为了不再维护一个千行的类。
"""
from __future__ import annotations

from .common import CommonMixin
from .menu import MenuMixin
from .round import RoundMixin
from .shop import ShopMixin


class App(CommonMixin, MenuMixin, RoundMixin, ShopMixin):
    """CLI 应用：由各场景 mixin 组合而成。"""


def run():
    from .. import ui
    ui.setup_console()
    App().run()
