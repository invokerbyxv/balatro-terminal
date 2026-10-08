from __future__ import annotations
import sys
import os
import re
import unicodedata
from typing import List

# ---------- ANSI 颜色 ----------
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
GRAY = "\033[90m"


def c(text, color):
    return f"{color}{text}{RESET}"


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def disp_len(text: str) -> int:
    w = 0
    for ch in _ANSI_RE.sub("", text):
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1
    return w


def grid_lines(items: List[str], cols: int) -> List[str]:
    rows = [items[i:i + cols] for i in range(0, len(items), cols)]
    widths = [
        max((disp_len(r[c]) for r in rows if c < len(r)), default=0)
        for c in range(cols)
    ]
    out = []
    for r in rows:
        cells = [it + " " * (widths[c] - disp_len(it)) for c, it in enumerate(r)]
        out.append("  ".join(cells))
    return out


def setup_console():
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if os.name == "nt":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        try:
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004 | 0x0008)
        except Exception:
            pass


def clear_screen():
    print("\033[2J\033[H", end="")


SUIT_COLOR = {"S": CYAN, "H": RED, "C": GREEN, "D": YELLOW}


def render_card(card, selected: bool = False, colorized: bool = True) -> str:
    from ..core.card import SUIT_DISPLAY, ENHANCED_CN, EDITION_CN, SEAL_CN
    s = f"{SUIT_DISPLAY[card.suit]}{card.rank}"
    if card.debuffed:
        s = f"▫{card.rank}{card.suit}" if False else f"{card.suit}*{card.rank}"
    tags = []
    if card.enhanced:
        tags.append(ENHANCED_CN[card.enhanced])
    if card.edition:
        tags.append(EDITION_CN[card.edition])
    if card.seal:
        tags.append(SEAL_CN[card.seal])
    if tags:
        s += "·" + "·".join(tags)
    core = f"{s}"
    if colorized and not card.debuffed:
        core = f"{SUIT_COLOR.get(card.suit, '')}{s}{RESET}"
    if selected:
        core = f"[{BOLD}{core}{RESET}]"
    else:
        core = f" {core} "
    return core


def suit_cn(suit: str) -> str:
    from ..core.card import SUIT_CN
    return SUIT_CN.get(suit, suit)


def rarity_color(r: int) -> str:
    return {1: GRAY, 2: GREEN, 3: BLUE, 4: MAGENTA}.get(r, RESET)


def joker_line(idx: int, game, j) -> str:
    from ..data import centers as cd
    from ..core.card import EDITION_CN
    cfg = cd.joker_cfg(j.key)
    extra = ""
    if j.edition:
        extra += f"·{EDITION_CN.get(j.edition, j.edition)}"
    if j.eternal:
        extra += "·永恒"
    if j.perishable:
        extra += f"·易腐{j.perish_tally}"
    if j.rental:
        extra += "·租借"
    # 累计状态显示
    if "chips" in j.stat:
        extra += f" +{int(j.stat['chips'])}筹码"
    if "mult" in j.stat:
        extra += f" +{int(j.stat['mult'])}倍率"
    if "x_mult" in j.stat and j.stat["x_mult"] != 1.0:
        extra += f" ×{j.stat['x_mult']:.2f}"
    if j.key == "j_egg":
        extra += f" 卖价{j.sell_value()}"
    if game is not None:
        from ..core.effects import joker_live_effect
        live = joker_live_effect(game, j)
        if live:
            extra += f" {c('»' + live, CYAN)}"
    name = cfg["cn"]
    rarity = cd.RARITY_CN.get(cfg["rarity"], "")
    desc = cfg["e"]
    star = "★" if j.debuffed else " "
    line = f"{idx}.{star}{rarity_color(cfg['rarity'])}{name}{RESET} {c('['+rarity+']', rarity_color(cfg['rarity']))} {c('$'+str(j.sell_value()), YELLOW)}{extra}"
    return line + f"  {c(desc, GRAY)}"


def consumable_line(idx: int, game, item) -> str:
    from ..data import consumables as cd
    from ..core.hand_eval import HAND_CN
    from ..core.card import EDITION_CN
    d = cd.ALL_CONSUMABLES.get(item.key, {})
    kind = "塔罗" if item.key in cd.TAROTS else ("星球" if item.key in cd.PLANETS else "幻灵")
    color = {"塔罗": BLUE, "星球": YELLOW, "幻灵": MAGENTA}[kind]
    name = d.get("cn", item.key)
    eff = d.get("effect", "")
    if not eff and d.get("hand"):
        eff = f"升级{HAND_CN.get(d['hand'], d['hand'])}"
    extra = ""
    if item.edition:
        extra += f"·{EDITION_CN.get(item.edition, item.edition)}"
    return f"{idx}.{color}{name}（{kind}）{RESET} {c('$'+str(item.sell_value()), YELLOW)}{extra}  {c(eff, GRAY)}"


def prompt(default: str = "") -> str:
    try:
        line = input(c("> ", CYAN) + default).strip()
    except (EOFError, KeyboardInterrupt):
        return "quit"
    return line
