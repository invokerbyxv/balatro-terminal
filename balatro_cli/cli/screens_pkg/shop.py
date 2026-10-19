"""CLI 的商店与卡包。

通过 mixin 组合进 :class:`balatro_cli.cli.screens.App`，各 mixin 共用同一份
``self`` 状态（game / log / state / regions），因此可以互相调用。
"""

from .. import ui
from ...core.card import Card
from ...core.items import JokerItem
from ...data import boosters as booster_data
from ...data import vouchers as voucher_data

LOG_LEN = 3   # 实时消息最多保留/展示的条数，更旧的移出


class ShopMixin:

    def _enter_shop(self):
        g = self.game
        g.enter_shop()
        self._push_log(g.messages)
        g.messages.clear()
        self.log = []
        self.state = "shop"


    def _shop(self):
        g = self.game
        self._banner(f"商店 · {self._ante_label()}", f"金钱 {ui.c('$' + str(g.dollars), ui.YELLOW)}")
        if g.shop_jokers:
            print("商品:")
            for i, item in enumerate(g.shop_jokers):
                price = g.shop_item_price(item)
                if isinstance(item, JokerItem):
                    line = ui.joker_line(i + 1, g, item)
                elif isinstance(item, Card):
                    line = f"{i + 1}.{ui.render_card(item)}"
                else:
                    line = ui.consumable_line(i + 1, g, item)
                print(f"  {line}  {ui.c('售价 $' + str(price), ui.YELLOW)}")
        if g.shop_boosters:
            print("卡包:")
            for i, bp in enumerate(g.shop_boosters):
                price = g.shop_item_price(bp)
                info = booster_data.BOOSTERS[bp.key]
                pack_desc = f"({info['pack_size']}选{info['choose']})"
                print(f"  {ui.c('b' + str(i + 1), ui.CYAN)} {info['cn']}  {ui.c('$' + str(price), ui.YELLOW)}"
                      f"  {ui.c(pack_desc, ui.GRAY)}")
        if g.shop_voucher:
            vd = voucher_data.VOUCHERS[g.shop_voucher]
            price = 0 if g.pending_free_voucher else 10
            print(f"优惠券: {ui.c('v', ui.CYAN)} {ui.BOLD}{vd['cn']}{ui.RESET}  {ui.c('$' + str(price), ui.YELLOW)}  {ui.c(vd['effect'], ui.GRAY)}")
        self._items_line()
        self._show_log()
        print(f"  {ui.c('r', ui.GREEN)}重掷(${g.calculate_reroll_cost()})  {ui.c('s', ui.YELLOW)}售卖  "
              f"{ui.c('u', ui.BLUE)}用消耗  {ui.c('i', ui.CYAN)}信息  {ui.c('x', ui.RED)}离开商店  "
              f"{ui.c('q', ui.RED)}退出游戏")
        cmd = ui.prompt()
        if cmd.startswith("b"):
            try:
                idx = int(cmd[1:]) - 1
            except ValueError:
                return
            if 0 <= idx < len(g.shop_boosters):
                g.buy_booster(idx)
                self._push_log(g.messages)
                g.messages.clear()
                if g.pending_pack:
                    self.pack_picked = 0
                    self.pack_selection.clear()
                    self.state = "pack"
        elif cmd == "j":
            self.return_state = "shop"
            self.state = "items"
        elif cmd == "i":
            self.info_return = "shop"
            self.state = "info"
        elif cmd == "s":
            self.return_state = "shop"
            self.state = "sell"
        elif cmd == "u":
            self.return_state = "shop"
            self.state = "consume"
        elif cmd == "v":
            g.buy_voucher()
            self._push_log(g.messages)
            g.messages.clear()
        elif cmd == "r":
            g.reroll_shop()
            self._push_log(g.messages)
            g.messages.clear()
        elif cmd == "x" or cmd == "quit":
            g.shop_closed()
            self._push_log(g.messages)
            g.messages.clear()
            if g.run_won and not g.endless:
                self.state = "over"
            else:
                self.state = "blind"
        elif cmd == "q":
            self.state = "menu"
        else:
            try:
                idx = int(cmd) - 1
            except ValueError:
                return
            if 0 <= idx < len(g.shop_jokers):
                g.buy_shop_item(idx)
                self._push_log(g.messages)
                g.messages.clear()


    def _pack(self):
        g = self.game
        pp = g.pending_pack
        if not pp:
            self.state = "shop"
            return
        cfg = pp["cfg"]
        self._banner(f"卡包 · {cfg['cn']}", f"选择 {pp['choose']} 张（当前 {self.pack_picked}/{pp['choose']}）")
        kind = cfg["kind"]
        for i, item in enumerate(pp["items"]):
            if kind == "buffoon":
                print(ui.joker_line(i + 1, g, item))
            elif kind in ("tarot", "planet", "spectral"):
                print(ui.consumable_line(i + 1, g, item))
            else:
                print(f"  {ui.c(str(i + 1), ui.CYAN)} {ui.render_card(item)}")
        print(f"  {ui.c('0', ui.RED)} 跳过")
        cmd = ui.prompt()
        if cmd == "0" or cmd == "quit":
            g.skip_pack()
            self.pack_selection.clear()
            self.state = "shop"
            return
        self.pack_selection |= self._parse_indices(cmd, len(pp["items"]))
        remaining = pp["choose"] - len(self.pack_selection)
        if remaining > 0:
            self.pack_picked = len(self.pack_selection)
            self._push_log([f"还需选择 {remaining} 张牌"])
            return
        status = g.pack_choose(sorted(self.pack_selection))
        self._push_log(g.messages)
        g.messages.clear()
        if status == "needs_sell":
            self.pack_picked = 0
            self.pack_selection.clear()
            self.state = "pack_sell"
            return
        if status == "done":
            self.pack_picked = 0
            self.pack_selection.clear()
            self.state = "shop"


    def _pack_sell(self):
        g = self.game
        pp = g.pending_pack
        if not pp or not pp.get("sells"):
            self.state = "shop"
            return
        cfg = pp["cfg"]
        self._banner(f"卡包 · {cfg['cn']} · 小丑栏已满",
                     f"还有 {len(pp['sells'])} 张小丑待放入")
        print("  待放入:")
        for i, j in enumerate(pp["sells"]):
            print(" " + ui.joker_line(i + 1, g, j))
        print()
        self._jokers()
        self._show_log()
        print(f"  输入{ui.c('小丑序号', ui.CYAN)} 出售它腾出空位并放入待选小丑；"
              f"{ui.c('0', ui.RED)} 放弃待放入的小丑")
        cmd = ui.prompt()
        if cmd == "0" or cmd == "quit":
            g.pack_discard_waiting()
            self._push_log(g.messages)
            g.messages.clear()
            self.state = "shop"
            return
        idxs = self._parse_indices(cmd, len(g.jokers))
        if not idxs:
            return
        ok = g.pack_sell_for_waiting(min(idxs))
        self._push_log(g.messages)
        g.messages.clear()
        if ok and not g.pending_pack:
            self.state = "shop"
