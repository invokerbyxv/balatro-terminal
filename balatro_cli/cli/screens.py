from __future__ import annotations
from typing import List, Optional, Tuple

from . import ui
from . import terminal
from ..core.game import Game, MAX_PLAY_SIZE
from ..core.card import Card
from ..core.items import JokerItem
from ..core.scoring import blocked_play_reason
from ..core.hand_eval import HAND_CN, HAND_ORDER, best_hand, hand_level_stats
from ..data import decks as deck_data
from ..data import blinds as blind_data
from ..data import centers as centers_data
from ..data import consumables as consumable_data
from ..data import boosters as booster_data
from ..data import vouchers as voucher_data
from ..data import tags as tag_data

LOG_LEN = 3   # 实时消息最多保留/展示的条数，更旧的移出


class App:
    def __init__(self):
        self.game: Optional[Game] = None
        self.state = "menu"
        self.log: List[str] = []
        self.pack_picked: int = 0
        self.pack_selection: set[int] = set()
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
                elif self.state == "pack_sell":
                    self._pack_sell()
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

    def _items(self):
        """二级界面：完整查看小丑牌、消耗牌与标签。"""
        g = self.game
        self._banner("小丑 / 消耗牌 / 标签",
                     f"小丑 {len(g.jokers)}/{g.joker_slots} · 消耗牌 {len(g.consumeables)}/{g.consumable_slots}"
                     f" · 标签 {len(g.tags)}")
        self._jokers()
        self._consumables()
        self._tags()
        self._show_log()
        hint = f"{ui.c('0', ui.CYAN)} 返回"
        if len(g.jokers) >= 2:
            hint = f"输入两个{ui.c('小丑序号', ui.CYAN)}（空格间隔）交换位置   " + hint
        print(f"  {hint}")
        cmd = ui.prompt()
        if cmd in ("", "0", "q", "quit"):
            self.state = self.return_state
            return
        self._swap_jokers(cmd)

    def _swap_jokers(self, cmd: str) -> bool:
        """输入「序号1 序号2」交换两张小丑的位置（小丑的先后决定计分顺序）。"""
        g = self.game
        parts = cmd.replace(",", " ").split()
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            print("  用法：输入两个小丑序号（空格间隔），如 1 3")
            input("  [回车继续]")
            return False
        a, b = int(parts[0]) - 1, int(parts[1]) - 1
        if not (0 <= a < len(g.jokers) and 0 <= b < len(g.jokers)):
            print("  无效的小丑序号")
            input("  [回车继续]")
            return False
        if a == b:
            return False
        g.jokers[a], g.jokers[b] = g.jokers[b], g.jokers[a]
        self._push_log([f"重排小丑：交换 #{a + 1} 与 #{b + 1}"])
        return True

    # ------------------------------------------------------------------
    # 信息界面（i）
    # ------------------------------------------------------------------
    def _info(self):
        """信息界面：牌型等级 / 出牌次数 / 筹码倍率 / 已拥有的优惠券。"""
        g = self.game
        key = g.current_blind_key()
        name = g.blind_cn(key)
        if key == g.boss_key:
            name = f"★{name}★"
        self._banner("局面信息", f"第 {g.ante} 底注 · {name}")
        target = g.current_blind_chips()
        if g.blind_key is None:
            # 选盲注 / 商店阶段：chips 还是上一回合的旧值
            score = ui.c("尚未开始", ui.GRAY)
        else:
            pct = g.chips / target * 100 if target else 0
            score = f"{ui.c(str(g.chips), ui.GREEN)} ({pct:.0f}%)"
        hands, discards = g.round_counts()
        print(f"  目标 {ui.c(str(target), ui.YELLOW)}   得分 {score}   "
              f"金钱 {ui.c('$' + str(g.dollars), ui.YELLOW)}   牌组 {g.deck.count()}")
        print(f"  本回合 出牌 {ui.c(str(hands), ui.GREEN)} 次   弃牌 {ui.c(str(discards), ui.GREEN)} 次   "
              f"手牌上限 {g.round_hand_size()}   本局已打出 {g.hands_played_total} 手")
        self._hand_preview()
        print()
        self._hand_levels(self._preview_hand_name())
        print()
        self._owned_vouchers()
        self._show_log()
        print(f"  {ui.c('0', ui.CYAN)} 返回")
        cmd = ui.prompt()
        if cmd in ("", "0", "q", "quit"):
            self.state = self.info_return

    def _preview_hand_name(self) -> Optional[str]:
        """当前选择（没选牌时为整手牌）能打出的最佳牌型名；无牌时返回 None。"""
        g = self.game
        cards = g.selected_cards() or g.hand
        if not cards:
            return None
        name, _ = best_hand(cards,
                            four_fingers=g.any_joker("j_four_fingers"),
                            shortcut=g.any_joker("j_shortcut"),
                            smeared=g.any_joker("j_smeared"))
        return name or None

    def _hand_preview(self):
        """当前手牌能打出的牌型及其等级数值。"""
        g = self.game
        name = self._preview_hand_name()
        if name is None:
            return
        lv = g.hand_levels[name]
        mult, chips = hand_level_stats(name, lv)
        label = "当前选择" if g.selected_cards() else "当前手牌可组成"
        print(f"  {ui.c(label, ui.GRAY)} {ui.c(HAND_CN.get(name, name), ui.YELLOW)} · "
              f"Lv.{lv}（{ui.c(str(chips), ui.GREEN)} 筹码 × {ui.c(str(mult), ui.RED)} 倍率）")

    def _hand_levels(self, current: Optional[str]):
        """牌型等级表：★ 标出当前手牌能打出的牌型，等级 >1 的用绿色标出。"""
        g = self.game
        print("牌型等级:")
        cells = []
        for name in HAND_ORDER:
            lv = g.hand_levels[name]
            mult, chips = hand_level_stats(name, lv)
            text = f"{HAND_CN.get(name, name)} Lv.{lv} {chips}×{mult}"
            if name == current:
                text = ui.c("★" + text, ui.YELLOW)
            elif lv > 1:
                text = ui.c(text, ui.GREEN)
            else:
                text = ui.c(text, ui.GRAY)
            cells.append(text)
        for line in ui.grid_lines(cells, 3):
            print(f"  {line}")

    def _owned_vouchers(self):
        """已拥有的优惠券（按数据表顺序，即一级券在前、二级券在后）。"""
        g = self.game
        owned = [d for k, d in voucher_data.VOUCHERS.items() if k in g.used_vouchers]
        if not owned:
            print(f"优惠券: {ui.c('（暂无）', ui.GRAY)}")
            return
        print("优惠券:")
        for d in owned:
            print(f"  {ui.BOLD}{d['cn']}{ui.RESET}  {ui.c(d['effect'], ui.GRAY)}")

    def _tags(self):
        """完整列出持有的标签（二级界面用）。"""
        g = self.game
        if not g.tags:
            print(f"  {ui.c('（暂无标签）', ui.GRAY)}")
            return
        print("标签:")
        for t in g.tags:
            print(" " + ui.tag_line(t))

    def _stats(self):
        g = self.game
        target = g.current_blind_chips()
        pct = g.chips / target * 100 if target else 0
        print(f"目标 {ui.c(str(target), ui.YELLOW)}   得分 {ui.c(str(g.chips), ui.GREEN)} ({pct:.0f}%)    "
              f"金钱 {ui.c('$' + str(g.dollars), ui.YELLOW)}   出牌 {ui.c(str(g.hands_left), ui.GREEN)}    "
              f"弃牌 {ui.c(str(g.discards_left), ui.GREEN)}   牌组 {g.deck.count()}")

    def _blind_meta(self):
        g = self.game
        b = blind_data.get_blind_cfg(g.blind_key)
        name = b["cn"]
        if g.blind_on_deck == "Boss":
            name = f"★{name}★"
        effect = ui.prob_text(g, b.get("effect", ""))
        if g.boss_disabled():
            effect = f"{effect} · {ui.c('已禁用', ui.GREEN)}"
        self._banner(f"第 {g.ante} 底注 · {name}", effect)

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

    def _blind_select(self):
        g = self.game
        self._banner(f"第 {g.ante} 底注 · 选择盲注", "跳过可获得标签")
        # 预览跳过后会获得的标签（reset_blinds 已预生成，所见即所得）
        tag_key = g.blind_tag_key(g.blind_on_deck)
        if tag_key:
            t = tag_data.TAGS[tag_key]
            skip_line = f"跳过    （获得标签：{ui.c(t['cn'], ui.YELLOW)}·{t['effect']}）"
        else:
            skip_line = "跳过    （获得随机标签）"
        if g.ante == 1:
            print(f"  {ui.c('1', ui.CYAN)} 迎战 小盲注  （目标 {ui.c(str(g.current_blind_chips()), ui.YELLOW)} · 奖励 $3）")
            print(f"  {ui.c('2', ui.CYAN)} {skip_line}")
        else:
            order = ["Small", "Big", "Boss"]
            label = {"Small": "小盲注", "Big": "大盲注", "Boss": "头目盲注"}[g.blind_on_deck]
            mult = {"Small": "", "Big": " · 奖励 $4", "Boss": " · 奖励 $5"}[g.blind_on_deck]
            if g.blind_on_deck == "Boss":
                boss = blind_data.get_blind_cfg(g.boss_key)
                effect = ui.prob_text(g, boss["effect"])
                if g.boss_disabled():
                    effect = f"{effect} · {ui.c('已禁用', ui.GREEN)}"
                print(f"  {ui.c('1', ui.CYAN)} 迎战  ★{boss['cn']}★  （目标 {ui.c(str(g.current_blind_chips()), ui.YELLOW)} · {effect}）")
            else:
                print(f"  {ui.c('1', ui.CYAN)} 迎战 {label}  （目标 {ui.c(str(g.current_blind_chips()), ui.YELLOW)}{mult}）")
            print(f"  {ui.c('2', ui.CYAN)} {skip_line}")
        self._items_line()
        print(f"  {ui.c('u', ui.BLUE)} 用消耗   {ui.c('c', ui.CYAN)} 收藏   "
              f"{ui.c('i', ui.CYAN)} 信息   {ui.c('q', ui.CYAN)} 返回菜单")
        cmd = ui.prompt()
        if cmd == "1":
            g.select_blind()
            self._push_log(g.messages)
            g.messages.clear()
            self.state = "play"
        elif cmd == "2":
            ante_before = g.ante
            g.skip_blind()
            self._push_log(g.messages)
            g.messages.clear()
            # 跳过头目则本底注结束，进入商店；跳过最终头目则通关
            if g.run_won:
                print(f"  {ui.c(ui.BOLD + '★★★ 你通关了！ ★★★', ui.YELLOW)}")
                input("  [回车进入结算商店]")
                self._enter_shop()
            elif g.ante > ante_before:
                self._enter_shop()
            else:
                self._show_log()
                input("  [回车继续]")
        elif cmd == "3" or cmd == "j":
            self.return_state = "blind"
            self.state = "items"
        elif cmd == "i":
            self.info_return = "blind"
            self.state = "info"
        elif cmd == "u":
            self.return_state = "blind"
            self.state = "consume"
        elif cmd == "c":
            self.return_state = "blind"
            self.state = "collection"
        elif cmd == "q" or cmd == "quit":
            self.state = "menu"

    def _play(self):
        g = self.game
        self.regions = []
        self._blind_meta()
        self._stats()
        self._hand_line(clickable=True)
        self._blocked_hint()
        self._items_line(clickable=True)
        self._show_log()
        print(f"  选牌：点击卡片或输入序号（如 {ui.c('1 2 3', ui.CYAN)} / {ui.c('1-3', ui.CYAN)}），"
              f"重复输入取消；一次最多 {ui.c(str(MAX_PLAY_SIZE), ui.CYAN)} 张"
              f"（已选 {ui.c(str(len(g.selected_cards())), ui.CYAN)}）；"
              f"{ui.c('o 1 2', ui.CYAN)} 换位")
        self._button_line([("打出", "p"), ("弃牌", "d"), ("消耗", "u"), ("售卖", "s"),
                           ("信息", "i"), ("排序", "o"), ("手动", "ou"), ("退出", "q")])
        cmd = ui.prompt(regions=self.regions, on_click=self._click_select)
        if cmd == ui.REDRAW:
            return
        if cmd in ("p", ""):
            if not g.selected_cards():
                print("  请先用数字选择要打出的牌")
                input("  [回车继续]")
                return
            self._push_log(g.play_selected())
            self._push_log(g.messages)
            g.messages.clear()
            self._check_round_over()
        elif cmd == "d":
            if not g.selected_cards():
                print("  请先用数字选择要弃掉的牌")
                input("  [回车继续]")
                return
            g.discard_selected()
            self._push_log(g.messages)
            g.messages.clear()
            self._check_round_over()
        elif cmd == "j":
            self.return_state = "play"
            self.state = "items"
        elif cmd == "i":
            self.info_return = "play"
            self.state = "info"
        elif cmd == "u":
            self.return_state = "play"
            self.state = "consume"
        elif cmd == "s":
            self.return_state = "play"
            self.state = "sell"
        elif cmd.startswith("o"):
            self._reorder(cmd)
        elif cmd == "q" or cmd == "quit":
            self.state = "menu"
        else:
            self._toggle_cards(cmd)

    def _blocked_hint(self):
        """盲注规则（眼睛/嘴/通灵者）下当前选牌会 0 分时提前提示——牌仍可打出。"""
        g = self.game
        reason = blocked_play_reason(g, g.selected_cards())
        if reason:
            print(f"  {ui.c('⚠ ' + reason + '，本手打出将不计分', ui.RED)}")

    def _toggle_cards(self, cmd: str, limit: Optional[int] = MAX_PLAY_SIZE):
        g = self.game
        for i in sorted(self._parse_indices(cmd, len(g.hand))):
            self._click_select(i, limit)

    def _click_select(self, index: int, limit: Optional[int] = MAX_PLAY_SIZE):
        """选中一张牌；超出出牌/弃牌上限时不生效，提示进实时消息（下次重绘显示）。"""
        if self.game.toggle_select(index, limit):
            return
        hint = f"一次最多选择 {limit} 张牌"
        if hint not in self.log:
            self._push_log([hint])

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

    def _check_round_over(self):
        g = self.game
        if self.state == "play" and g.round_over():
            self.state = "settle"

    def _consume(self):
        g = self.game
        if not g.consumeables:
            print(f"  {ui.c('（暂无消耗牌）', ui.GRAY)}")
            input("  [回车返回]")
            self.state = self.return_state
            return
        self._banner("使用消耗牌", "输入序号使用，0 返回")
        self._consumables()
        self._show_log()
        cmd = ui.prompt()
        if cmd in ("0", "q", "quit"):
            self.state = self.return_state
            return
        try:
            idx = int(cmd) - 1
        except ValueError:
            return
        if not (0 <= idx < len(g.consumeables)):
            print("  无效的消耗牌序号")
            input("  [回车继续]")
            return
        self._use_consumable_at(idx)

    def _use_consumable_at(self, idx: int):
        g = self.game
        c = g.consumeables[idx]
        if self.return_state != "play" and consumable_data.needs_target(c.key):
            print("  该消耗牌需要选择手牌目标，只能在牌局中使用")
            input("  [回车继续]")
            return
        status = g.use_consumable(idx)
        self._push_log(g.messages)
        g.messages.clear()
        if status == "needs_target":
            info = consumable_data.ALL_CONSUMABLES.get(g.pending_consumable.key, {})
            self.target_needed = info.get("max_highlighted", 1)
            self.target_min = info.get("min_highlighted", 1)
            if self.target_min is None:
                self.target_min = 1
            self.target_return = self.state
            self.state = "target"
        self._check_round_over()

    def _sell_screen(self):
        g = self.game
        if not g.jokers and not g.consumeables:
            print(f"  {ui.c('（没有可出售的小丑或消耗牌）', ui.GRAY)}")
            input("  [回车返回]")
            self.state = self.return_state
            return
        self._banner("售卖", "输入序号出售，0 返回")
        if g.jokers:
            print("小丑:")
            for i, j in enumerate(g.jokers):
                print(" " + ui.joker_line(i + 1, g, j))
        if g.consumeables:
            off = len(g.jokers)
            print("消耗牌:")
            for i, c in enumerate(g.consumeables):
                print(" " + ui.consumable_line(off + i + 1, g, c))
        self._show_log()
        cmd = ui.prompt()
        if cmd in ("0", "q", "quit"):
            self.state = self.return_state
            return
        try:
            idx = int(cmd) - 1
        except ValueError:
            return
        if 0 <= idx < len(g.jokers):
            g.sell_joker(idx)
            self._push_log(g.messages)
            g.messages.clear()
        elif 0 <= idx - len(g.jokers) < len(g.consumeables):
            g.sell_consumable(idx - len(g.jokers))
            self._push_log(g.messages)
            g.messages.clear()
        else:
            print("  无效的序号")
            input("  [回车继续]")

    def _reorder(self, cmd: str):
        g = self.game
        key = " ".join(cmd.lower().split())
        parts = cmd.split()
        # ou：手动排序
        if key in ("ou", "o u"):
            g.sort_mode = None
            self._push_log(["已开启手动排序：关闭自动排序，输入 o <序号1> <序号2> 交换手牌位置"])
            return
        # o <a> <b>：交换位置（自动排序时交换小丑，手动排序时交换手牌）
        if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
            a, b = int(parts[1]) - 1, int(parts[2]) - 1
            if g.sort_mode is None:
                if 0 <= a < len(g.hand) and 0 <= b < len(g.hand):
                    g.hand[a], g.hand[b] = g.hand[b], g.hand[a]
                    self._push_log([f"重排手牌：交换 #{a + 1} 与 #{b + 1}"])
            elif 0 <= a < len(g.jokers) and 0 <= b < len(g.jokers):
                g.jokers[a], g.jokers[b] = g.jokers[b], g.jokers[a]
                self._push_log([f"重排小丑：交换 #{a + 1} 与 #{b + 1}"])
            return
        # o：自动排序，在花色与点数之间切换
        if key == "o":
            g.sort_mode = "rank" if g.sort_mode == "suit" else "suit"
            g.sort_hand()
            label = "点数" if g.sort_mode == "rank" else "花色"
            self._push_log([f"手牌按{label}排序（同{label}再按另一项），此后抽牌保持此顺序"])
            return
        print("  用法：o 自动排序（在花色与点数之间切换）  ou 手动排序（关闭自动排序）")
        print("        o <序号1> <序号2> 交换位置（自动排序时交换小丑，手动排序时交换手牌）")
        input("  [回车继续]")

    # ==========================================================
    # 回合结算
    # ==========================================================
    def _settle(self):
        g = self.game
        self._banner("回合结算", "")
        won = g.end_round()
        self._push_log(g.messages)
        g.messages.clear()
        self._show_log()
        print()
        if g.run_won:
            print(f"  {ui.c(ui.BOLD + '★★★ 你通关了！ ★★★', ui.YELLOW)}")
            input("  [回车进入结算商店]")
            self._enter_shop()
            return
        if g.run_lost:
            self.state = "over"
            return
        self._enter_shop()

    def _enter_shop(self):
        g = self.game
        g.enter_shop()
        self._push_log(g.messages)
        g.messages.clear()
        self.log = []
        self.state = "shop"

    def _shop(self):
        g = self.game
        self._banner(f"商店 · 第 {g.ante} 底注", f"金钱 {ui.c('$' + str(g.dollars), ui.YELLOW)}")
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
            if g.run_won:
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

    def _target(self):
        g = self.game
        if not g.pending_consumable:
            self.state = self.target_return
            return
        info = consumable_data.ALL_CONSUMABLES.get(g.pending_consumable.key, {})
        self.regions = []
        self._banner(f"选择目标牌 · {info.get('cn', '')}",
                     f"需选择 {self.target_min}-{self.target_needed} 张")
        self._hand_line(clickable=True)
        print(f"  点击卡片或输入序号（如 {ui.c('1 2 3', ui.CYAN)} 或 {ui.c('1-3', ui.CYAN)}），重复输入可取消")
        self._show_log()
        self._button_line([("确认", "0"), ("取消", "q")])
        cmd = ui.prompt(regions=self.regions,
                        on_click=lambda i: self._click_select(i, self.target_needed))
        if cmd == ui.REDRAW:
            return
        if cmd == "0":
            selected = [i for i, c in enumerate(g.hand) if getattr(c, "selected", False)]
            if len(selected) < self.target_min:
                print(f"  至少选择 {self.target_min} 张牌")
                input("  [回车继续]")
                return
            if self.target_needed is not None and len(selected) > self.target_needed:
                print(f"  最多选择 {self.target_needed} 张牌")
                input("  [回车继续]")
                return
            result = g.finish_consumable_target(selected)
            if result == "invalid":
                return
            self._push_log(g.messages)
            g.messages.clear()
            for c in g.hand:
                c.selected = False
            self.state = self.target_return
            self._check_round_over()
        elif cmd == "q" or cmd == "quit":
            g.pending_consumable = None
            self.state = self.target_return
        else:
            self._toggle_cards(cmd, self.target_needed)

    def _over(self) -> bool:
        g = self.game
        self._banner("游戏结束" if g.run_lost else "通关！", "")
        if g.run_lost:
            print(f"  {ui.c('你止步于第 ' + str(g.ante) + ' 底注。', ui.RED)}")
        else:
            print(f"  {ui.c('你击败了第 ' + str(g.ante) + ' 底注的头目！', ui.YELLOW)}")
        print(f"  最终得分 {g.chips} · 金钱 ${g.dollars}")
        print(f"  {ui.c('1', ui.CYAN)} 返回主菜单   {ui.c('2', ui.CYAN)} 退出")
        cmd = ui.prompt()
        if cmd == "2" or cmd == "quit":
            return False
        self.game = None
        self.log = []
        self.state = "menu"
        return True

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


def run():
    ui.setup_console()
    App().run()
