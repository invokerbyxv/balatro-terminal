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
        # 标签（小丑/塔罗/星球/标准/幻灵包）可能在进商店时就开了一个免费卡包
        self.state = "pack" if g.pending_pack else "shop"


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
        kind = cfg["kind"]
        left = g.pack_choices_left()
        self._banner(f"卡包 · {cfg['cn']}",
                     f"已选 {pp['picked']}/{pp['choose']} · 还能选 {left} 张")
        for i, item in enumerate(pp["items"]):
            if kind == "buffoon":
                line = ui.joker_line(i + 1, g, item)
                if not g.pack_joker_fits(item):
                    line += f"  {ui.c('（小丑栏已满，需先出售）', ui.RED)}"
                print(line)
            elif kind in ("tarot", "planet", "spectral"):
                print(ui.consumable_line(i + 1, g, item))
            else:
                print(f"  {ui.c(str(i + 1), ui.CYAN)} {ui.render_card(item)}")
        print(f"  {ui.c('小丑', ui.GRAY)} {self._slots(len(g.jokers), g.joker_slots)}   "
              f"{ui.c('消耗牌', ui.GRAY)} {self._slots(len(g.consumeables), g.consumable_slots)}")
        if kind == "buffoon" and len(g.jokers) >= g.joker_slots:
            print(f"  {ui.c('小丑栏已满：先按 s 出售一张现有小丑，再选择卡包小丑', ui.RED)}")
        self._show_log()
        print(f"  输入{ui.c('序号', ui.CYAN)}取牌（可多选，如 {ui.c('1 2', ui.CYAN)}）   "
              f"{ui.c('s', ui.YELLOW)}售卖  {ui.c('j', ui.GREEN)}查看  "
              f"{ui.c('0', ui.RED)}结束选择（已选的牌保留）")
        cmd = ui.prompt()
        if cmd == "0" or cmd == "quit":
            g.skip_pack()
            self._push_log(g.messages)
            g.messages.clear()
            self.state = "shop"
            return
        if cmd == "s":
            self.return_state = "pack"
            self.state = "sell"
            return
        if cmd == "j":
            self.return_state = "pack"
            self.state = "items"
            return
        idxs = self._parse_indices(cmd, len(pp["items"]))
        if not idxs:
            if cmd:
                self._push_log(["无效的序号"])
            return
        status = g.pack_choose(sorted(idxs))
        self._push_log(g.messages)
        g.messages.clear()
        if status in ("done", "none"):
            self.state = "shop"
