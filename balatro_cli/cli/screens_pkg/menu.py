"""CLI 的主菜单、牌组选择、结算与收藏。

通过 mixin 组合进 :class:`balatro_cli.cli.screens.App`，各 mixin 共用同一份
``self`` 状态（game / log / state / regions），因此可以互相调用。
"""

from .. import ui
from ...core.game import Game, WIN_ANTE
from ...data import decks as deck_data
from ...data import centers as centers_data
from ...data import consumables as consumable_data
from ...data import vouchers as voucher_data

LOG_LEN = 3   # 实时消息最多保留/展示的条数，更旧的移出


class MenuMixin:

    def _menu(self) -> bool:
        ui.clear_screen()
        print()
        print(f"  {ui.c(ui.BOLD + '小 丑 牌  (Balatro) 命令行版', ui.MAGENTA)}")
        print(f"  {ui.c('JOKER · 命令行文字界面', ui.GRAY)}")
        print()
        print(f"  {ui.c('1', ui.CYAN)} 开始新游戏")
        print(f"  {ui.c('2', ui.CYAN)} 退出")
        print()
        cmd = ui.prompt()
        if cmd == "1":
            self.state = "deck"
        elif cmd == "2" or cmd == "quit":
            return False
        return True


    def _deck_select(self):
        self._banner("选择牌组", "不同牌组提供不同初始优势")
        names = list(deck_data.DECK_ORDER)
        cells = []
        for i, k in enumerate(names):
            d = deck_data.DECKS[k]
            cfg = d["config"]
            bonus = []
            if cfg.get("dollars"): bonus.append(f"+${cfg['dollars']}")
            if cfg.get("hands"): bonus.append(f"手牌+{cfg['hands']}")
            if cfg.get("discards"): bonus.append(f"弃牌+{cfg['discards']}")
            if cfg.get("hand_size"): bonus.append(f"手牌上限{cfg['hand_size']:+}")
            if cfg.get("joker_slot"): bonus.append(f"小丑槽{cfg['joker_slot']:+}")
            if cfg.get("voucher"): bonus.append("自带优惠券")
            if cfg.get("remove_faces"): bonus.append("去掉人头排")
            if cfg.get("checkered"): bonus.append("只有黑桃与红心")
            if cfg.get("double_tag"): bonus.append("击败头目得双重标签")
            if cfg.get("no_interest"): bonus.append("无利息")
            if cfg.get("ante_scaling", 1) == 2: bonus.append("等离子记分")
            if cfg.get("randomize_rank_suit"): bonus.append("随机花色点数")
            if cfg.get("spectral_rate"): bonus.append("幻灵生成率×2")
            extra = "  ".join(bonus) if bonus else ""
            cell = f"{ui.c(str(i + 1), ui.CYAN)} {ui.BOLD}{d['cn']}{ui.RESET}"
            if extra:
                cell += f"  {ui.c(extra, ui.GRAY)}"
            cells.append(cell)
        for line in ui.grid_lines(cells, 3):
            print(f"  {line}")
        print(f"  {ui.c('0', ui.CYAN)} 返回")
        cmd = ui.prompt()
        if cmd == "0" or cmd == "quit":
            self.state = "menu"
            return
        try:
            idx = int(cmd) - 1
            key = names[idx]
        except (ValueError, IndexError):
            return
        self.game = Game(seed=getattr(self, "_seed_override", None))
        self.log = []
        self.game.start_run(key)
        self.state = "blind"


    def _over(self) -> bool:
        g = self.game
        title = "通关！" if not g.run_lost else ("无尽模式结束" if g.endless else "游戏结束")
        self._banner(title, g.round_label())
        if g.run_lost:
            if g.endless:
                # 对应 game.lua 3585：通关之后的失败不计入战绩（原版结算界面在无尽模式里是蓝色）
                print(f"  {ui.c('无尽模式止步于第 ' + str(g.ante) + ' 底注。', ui.RED)}")
                print(f"  {ui.c(f'本局已在第 {WIN_ANTE} 底注通关，无尽模式里的失败不算失败。', ui.GRAY)}")
            else:
                print(f"  {ui.c('你止步于第 ' + str(g.ante) + ' 底注。', ui.RED)}")
        else:
            print(f"  {ui.c(f'你击败了第 {WIN_ANTE} 底注的头目！', ui.YELLOW)}")
        print(f"  共 {g.round} 回合 · 最终得分 {g.chips} · 金钱 ${g.dollars}")
        print(f"  {ui.c('1', ui.CYAN)} 返回主菜单   {ui.c('2', ui.CYAN)} 退出")
        cmd = ui.prompt()
        if cmd == "2" or cmd == "quit":
            return False
        self.game = None
        self.log = []
        self.state = "menu"
        return True


    def _win_screen(self):
        """通关窗口（对应原版 UI_definitions.lua create_UIBox_win）。

        原版的「Endless Mode」按钮就是关闭通关窗口的按钮——关掉即继续游戏，
        没有回合上限；这里把「继续」与「结束」两个选择显式分开。
        """
        g = self.game
        self._banner("通关！", f"第 {WIN_ANTE} 底注 · 共 {g.round} 回合")
        print(f"  {ui.c(ui.BOLD + f'★★★ 你击败了第 {WIN_ANTE} 底注的头目！ ★★★', ui.YELLOW)}")
        print(f"  金钱 ${g.dollars} · 跳过盲注 {g.skips} 次")
        print(f"  {ui.c('1', ui.CYAN)} 进入无尽模式（没有回合上限，继续本局）   "
              f"{ui.c('2', ui.CYAN)} 结束本局")
        cmd = ui.prompt()
        if cmd == "2" or cmd == "quit":
            self.state = "over"
            return
        g.enter_endless()
        for m in g.messages:
            print(f"  {ui.c(m, ui.GRAY)}")
        g.messages.clear()
        input("  [回车进入结算商店]")
        self._enter_shop()


    def _collection(self):
        self._banner("收藏图鉴", "查看所有可收集内容")
        print(f"  {ui.c('1', ui.CYAN)} 小丑牌（{len(centers_data.JOKERS)}）")
        print(f"  {ui.c('2', ui.CYAN)} 塔罗牌（{len(consumable_data.TAROTS)}）")
        print(f"  {ui.c('3', ui.CYAN)} 星球牌（{len(consumable_data.PLANETS)}）")
        print(f"  {ui.c('4', ui.CYAN)} 幻灵牌（{len(consumable_data.SPECTRALS)}）")
        print(f"  {ui.c('5', ui.CYAN)} 优惠券（{len(voucher_data.VOUCHERS)}）")
        print(f"  {ui.c('6', ui.CYAN)} 牌组（{len(deck_data.DECKS)}）")
        print(f"  {ui.c('0', ui.RED)} 返回")
        cmd = ui.prompt()
        if cmd == "0" or cmd == "quit":
            self.state = self.return_state if (self.game and self.game.deck_key) else "menu"
            return
        if cmd == "1":
            self._list_jokers()
        elif cmd == "2":
            self._list_consumables("tarot")
        elif cmd == "3":
            self._list_consumables("planet")
        elif cmd == "4":
            self._list_consumables("spectral")
        elif cmd == "5":
            self._list_vouchers()
        elif cmd == "6":
            self._list_decks()


    def _list_jokers(self):
        ui.clear_screen()
        self._banner("小丑图鉴", "按稀有度排序")
        for r in (1, 2, 3, 4):
            items = [k for k, d in centers_data.JOKERS.items() if d["r"] == r]
            if not items:
                continue
            print(f"  {ui.c('— ' + centers_data.RARITY_CN[r] + ' —', ui.rarity_color(r))}")
            for k in items:
                d = centers_data.JOKERS[k]
                print(f"    {ui.c(d['cn'], ui.rarity_color(r))}  {ui.c('$' + str(d['c']), ui.YELLOW)}  {ui.c(ui.prob_text(self.game, d['e']), ui.GRAY)}")
        print()
        input("  [回车返回收藏]")
        self.state = "collection"


    def _list_consumables(self, kind: str):
        pool = {"tarot": consumable_data.TAROTS, "planet": consumable_data.PLANETS,
                "spectral": consumable_data.SPECTRALS}[kind]
        ui.clear_screen()
        self._banner(f"{kind}图鉴", "")
        for k, d in pool.items():
            print(f"  {ui.BOLD}{d['cn']}{ui.RESET}  {ui.c('$' + str(d['cost']), ui.YELLOW)}  {ui.c(ui.prob_text(self.game, d.get('effect', '')), ui.GRAY)}")
        print()
        input("  [回车返回收藏]")
        self.state = "collection"


    def _list_vouchers(self):
        ui.clear_screen()
        self._banner("优惠券图鉴", "")
        for k, d in voucher_data.VOUCHERS.items():
            print(f"  {ui.BOLD}{d['cn']}{ui.RESET}  {ui.c('$10', ui.YELLOW)}  {ui.c(d['effect'], ui.GRAY)}")
        print()
        input("  [回车返回收藏]")
        self.state = "collection"


    def _list_decks(self):
        ui.clear_screen()
        self._banner("牌组一览", "")
        for k in deck_data.DECK_ORDER:
            d = deck_data.DECKS[k]
            print(f"  {ui.BOLD}{d['cn']}{ui.RESET}  {ui.c(d['effect'], ui.GRAY)}")
        print()
        input("  [回车返回收藏]")
        self.state = "collection"
