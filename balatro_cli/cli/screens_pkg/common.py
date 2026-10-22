"""CLI 的共享渲染与输入工具。

通过 mixin 组合进 :class:`balatro_cli.cli.screens.App`，各 mixin 共用同一份
``self`` 状态（game / log / state / regions），因此可以互相调用。
"""
from typing import List, Optional

from .. import terminal, ui
from ...core.game import Game, MAX_PLAY_SIZE, WIN_ANTE
from ...data import blinds as blind_data

LOG_LEN = 3   # 实时消息最多保留/展示的条数，更旧的移出


class CommonMixin:

    def __init__(self):
        self.game: Optional[Game] = None
        self.state = "menu"
        self.log: List[str] = []
        self.target_needed: Optional[int] = None
        self.target_min: int = 1
        self.return_state: str = "play"
        self.target_return: str = "play"
        self.info_return: str = "play"
        self.regions: List[ui.Region] = []


    def run(self):
        try:
            self._run_loop()
        finally:
            terminal.restore()


    def _run_loop(self):
        while True:
            ui.clear_screen()
            try:
                if self.state == "menu":
                    if not self._menu():
                        break
                elif self.state == "deck":
                    self._deck_select()
                elif self.state == "blind":
                    self._blind_select()
                elif self.state == "play":
                    self._play()
                elif self.state == "settle":
                    self._settle()
                elif self.state == "shop":
                    self._shop()
                elif self.state == "pack":
                    self._pack()
                elif self.state == "consume":
                    self._consume()
                elif self.state == "sell":
                    self._sell_screen()
                elif self.state == "target":
                    self._target()
                elif self.state == "over":
                    if not self._over():
                        break
                elif self.state == "collection":
                    self._collection()
                elif self.state == "items":
                    self._items()
                elif self.state == "info":
                    self._info()
            except (EOFError, KeyboardInterrupt):
                return


    def _push_log(self, msgs):
        for m in (msgs or []):
            if m:
                self.log.append(m)
        self.log = self.log[-LOG_LEN:]


    def _show_log(self):
        """实时消息：一行显示，右为新、左为旧，最多三条，放不下的旧消息移出。"""
        line = ui.log_line(self.log)
        if line:
            print(f"  {ui.c(line, ui.GRAY)}")


    def _banner(self, title: str, sub: str = ""):
        head = f"{ui.BOLD}{title}{ui.RESET}"
        if sub:
            head += f"   {ui.c(sub, ui.GRAY)}"
        print(f"{ui.c('━', ui.DIM)} {head} {ui.c('━', ui.DIM)}")


    def _hand_line(self, clickable: bool = False):
        g = self.game
        row, measured = ui.print_tracked(ui.hand_line_text(g.hand), measure=clickable)
        if row is not None:
            self.regions.extend(ui.hand_regions(row, g.hand, measured))


    def _button_line(self, buttons):
        """打印一行可点击按钮（同时充当快捷键说明）。"""
        text, _ = ui.button_row(buttons)
        row, _ = ui.print_tracked("  " + text)
        if row is not None:
            self.regions.extend(ui.button_regions(row, 2, buttons))


    def _jokers(self):
        """完整列出小丑牌（二级界面与售卖界面用）。"""
        g = self.game
        if not g.jokers:
            print(f"  {ui.c('（暂无小丑牌）', ui.GRAY)}")
            return
        print("小丑:")
        for i, j in enumerate(g.jokers):
            print(" " + ui.joker_line(i + 1, g, j))


    def _consumables(self):
        """完整列出消耗牌（二级界面与售卖界面用）。"""
        g = self.game
        if not g.consumeables:
            print(f"  {ui.c('（暂无消耗牌）', ui.GRAY)}")
            return
        print("消耗牌:")
        for i, c in enumerate(g.consumeables):
            print(" " + ui.consumable_line(i + 1, g, c))


    @staticmethod
    def _slots(n: int, cap: int) -> str:
        return f"{ui.c(str(n), ui.YELLOW if n >= cap else ui.GREEN)}/{ui.c(str(cap), ui.GRAY)}"


    def _items_line(self, clickable: bool = False):
        """小丑 / 消耗牌 / 标签折叠成一行：只显示已拥有数量，按 j 进二级界面看详情。

        ``clickable`` 为真时末尾渲染成可点击的「查看」按钮并登记点击区域
        （只有把 regions 交给 prompt 的界面才需要）。
        """
        g = self.game
        head = (f"{ui.c('小丑', ui.GRAY)} {self._slots(len(g.jokers), g.joker_slots)}   "
                f"{ui.c('消耗牌', ui.GRAY)} {self._slots(len(g.consumeables), g.consumable_slots)}   ")
        if g.tags:
            head += f"{ui.c('标签', ui.GRAY)} {ui.c(str(len(g.tags)), ui.MAGENTA)}   "
        if not clickable:
            print("  " + head + ui.c("（j 查看）", ui.GRAY))
            return
        buttons = [("查看", "j")]
        text, _ = ui.button_row(buttons)
        row, _ = ui.print_tracked("  " + head + text, measure=True)
        if row is not None:
            self.regions.extend(ui.button_regions(row, 2 + ui.disp_len(head), buttons))


    def _parse_indices(self, spec: str, limit: int) -> set[int]:
        idxs: set[int] = set()
        for part in spec.replace(",", " ").split():
            if "-" in part:
                a, _, b = part.partition("-")
                try:
                    lo, hi = int(a), int(b)
                except ValueError:
                    continue
                if lo > hi:
                    lo, hi = hi, lo
                for n in range(lo, hi + 1):
                    if 0 <= n - 1 < limit:
                        idxs.add(n - 1)
            else:
                try:
                    i = int(part) - 1
                except ValueError:
                    continue
                if 0 <= i < limit:
                    idxs.add(i)
        return idxs


    def _click_select(self, index: int, limit: Optional[int] = MAX_PLAY_SIZE):
        """选中一张牌；超出出牌/弃牌上限时不生效，提示进实时消息（下次重绘显示）。"""
        if self.game.toggle_select(index, limit):
            return
        hint = f"一次最多选择 {limit} 张牌"
        if hint not in self.log:
            self._push_log([hint])


    def _toggle_cards(self, cmd: str, limit: Optional[int] = MAX_PLAY_SIZE):
        g = self.game
        for i in sorted(self._parse_indices(cmd, len(g.hand))):
            self._click_select(i, limit)


    def _check_round_over(self):
        g = self.game
        if self.state == "play" and g.round_over():
            self.state = "settle"


    def _ante_label(self) -> str:
        """底注标签：未通关时按 HUD 的写法显示「第 X 底注 / 8」，无尽模式标「无尽」。"""
        g = self.game
        if g.endless:
            return f"第 {g.ante} 底注" + ui.c("（无尽）", ui.BLUE)
        return f"第 {g.ante} 底注 / {WIN_ANTE}"


    def _blind_meta(self):
        g = self.game
        b = blind_data.get_blind_cfg(g.blind_key)
        name = b["cn"]
        if g.blind_on_deck == "Boss":
            name = f"★{name}★"
        effect = ui.prob_text(g, b.get("effect", ""))
        if g.boss_disabled():
            effect = f"{effect} · {ui.c('已禁用', ui.GREEN)}"
        self._banner(f"{self._ante_label()} · {name}", f"{g.round_label()} · {effect}")


    def _stats(self):
        g = self.game
        target = g.current_blind_chips()
        pct = g.chips / target * 100 if target else 0
        print(f"目标 {ui.c(str(target), ui.YELLOW)}   得分 {ui.c(str(g.chips), ui.GREEN)} ({pct:.0f}%)    "
              f"金钱 {ui.c('$' + str(g.dollars), ui.YELLOW)}   出牌 {ui.c(str(g.hands_left), ui.GREEN)}    "
              f"弃牌 {ui.c(str(g.discards_left), ui.GREEN)}   牌组 {g.deck.count()}   {g.round_label()}")


    def _tags(self):
        """完整列出持有的标签（二级界面用）。"""
        g = self.game
        if not g.tags:
            print(f"  {ui.c('（暂无标签）', ui.GRAY)}")
            return
        print("标签:")
        for t in g.tags:
            print(" " + ui.tag_line(t))
