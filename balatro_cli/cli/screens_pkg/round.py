"""CLI 的盲注选择、出牌、消耗牌与售卖。

通过 mixin 组合进 :class:`balatro_cli.cli.screens.App`，各 mixin 共用同一份
``self`` 状态（game / log / state / regions），因此可以互相调用。
"""
from typing import Optional

from .. import ui
from ...core.game import MAX_PLAY_SIZE
from ...core.scoring import blocked_play_reason
from ...core.hand_eval import HAND_CN, HAND_ORDER, best_hand, hand_level_stats
from ...data import blinds as blind_data
from ...data import consumables as consumable_data
from ...data import vouchers as voucher_data
from ...data import tags as tag_data

LOG_LEN = 3   # 实时消息最多保留/展示的条数，更旧的移出


class RoundMixin:

    def _blind_select(self):
        g = self.game
        self._banner(f"{self._ante_label()} · 选择盲注", "跳过可获得标签")
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
            if g.run_won and not g.endless:
                self._win_screen()
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


    def _settle(self):
        g = self.game
        self._banner("回合结算", g.round_label())
        won = g.end_round()
        self._push_log(g.messages)
        g.messages.clear()
        self._show_log()
        print()
        if g.run_won and not g.endless:
            self._win_screen()
            return
        if g.run_lost:
            self.state = "over"
            return
        self._enter_shop()


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


    def _info(self):
        """信息界面：牌型等级 / 出牌次数 / 筹码倍率 / 已拥有的优惠券。"""
        g = self.game
        key = g.current_blind_key()
        name = g.blind_cn(key)
        if key == g.boss_key:
            name = f"★{name}★"
        self._banner("局面信息", f"{self._ante_label()} · {name} · {g.round_label()}")
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
