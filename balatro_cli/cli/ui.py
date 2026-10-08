from __future__ import annotations
import sys
import os
import re
import shutil
import unicodedata
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

from . import terminal

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


def truncate(text: str, width: int) -> str:
    """按显示宽度截断文本（忽略 ANSI 颜色），超出部分以 … 收尾。"""
    plain = _ANSI_RE.sub("", text)
    if width <= 0:
        return ""
    if disp_len(plain) <= width:
        return plain
    # … 是宽度歧义字符，disp_len 按 2 列算，预留时用同一口径
    ell = "…"
    budget = width - disp_len(ell)
    out: List[str] = []
    w = 0
    for ch in plain:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F", "A") else 1
        if w + cw > budget:
            break
        out.append(ch)
        w += cw
    return "".join(out) + ell


#: 实时消息行中两条消息之间的分隔符
LOG_SEP = "  │  "


def log_line(msgs: Sequence[str], cols: Optional[int] = None, sep: str = LOG_SEP) -> str:
    """把实时消息排成一行：最旧的在左、最新的在右。

    最多保留 ``len(msgs)`` 条（调用方已截断到最近若干条）；整行放不下时从最旧
    的一条开始丢弃，只剩一条仍放不下则截断该条。全部为空时返回空串。
    """
    limit = (cols if cols is not None else _term_cols()) - 2
    kept = [str(m) for m in msgs if m]
    while kept:
        text = sep.join(kept)
        if disp_len(text) <= limit:
            return text
        if len(kept) == 1:
            return truncate(kept[0], limit)
        kept.pop(0)
    return ""


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


# ---------- 鼠标点击区域 ----------

HAND_PREFIX = "手牌: "

#: 点击手牌后 prompt() 的返回值：调用方只需重绘，不做别的处理
REDRAW = "\x00redraw"


@dataclass
class Region:
    """一块可点击的屏幕区域，行列均从 1 开始，列区间为左闭右开。"""

    row: int
    col_start: int
    col_end: int
    kind: str               # "card" | "cmd"
    value: object = None    # card → 手牌下标；cmd → 命令字符串


def hit_test(regions: Sequence[Region], row: int, col: int) -> Optional[Region]:
    for r in regions:
        if r.row == row and r.col_start <= col < r.col_end:
            return r
    return None


def _term_cols() -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def hand_line_text(cards) -> str:
    parts = [f"{i + 1}{render_card(c, getattr(c, 'selected', False))}"
             for i, c in enumerate(cards)]
    return HAND_PREFIX + "  ".join(parts)


def amb_count(text: str) -> int:
    """统计东亚宽度歧义字符（♠ ♥ ♣ ─ 等）的个数。

    ``disp_len`` 按 2 列计算它们，但终端未必如此，需要靠实测宽度校正。
    """
    return sum(1 for ch in _ANSI_RE.sub("", text)
               if unicodedata.east_asian_width(ch) == "A")


def hand_regions(row: int, cards, measured: Optional[int] = None) -> List[Region]:
    """算出每张牌在屏幕上的列区间；行宽超出终端时返回空表（不登记点击）。

    ``measured`` 为终端实测的整行占用列数（见 :func:`print_tracked`），
    用于校正歧义字符的宽度差异。
    """
    texts = [f"{i + 1}{render_card(c, getattr(c, 'selected', False))}"
             for i, c in enumerate(cards)]
    if not texts:
        return []
    widths = [disp_len(t) for t in texts]
    prefix = disp_len(HAND_PREFIX)
    total = prefix + sum(widths) + 2 * (len(widths) - 1)
    if measured and measured > 1 and measured != total:
        amb = sum(amb_count(t) for t in texts)
        if amb and abs(measured - (total - amb)) < abs(measured - total):
            widths = [w - amb_count(t) for w, t in zip(widths, texts)]
            total = prefix + sum(widths) + 2 * (len(widths) - 1)
    if total > _term_cols():
        return []
    regions: List[Region] = []
    col = prefix + 1
    for i, w in enumerate(widths):
        left = col - 1 if i > 0 else col              # 与左邻平分 2 空格间隔
        right = col + w + 1 if i < len(widths) - 1 else col + w
        regions.append(Region(row, left, right, "card", i))
        col += w + 2
    return regions


def button_row(buttons: Sequence[Tuple[str, str]]) -> Tuple[str, List[Tuple[int, int, str]]]:
    """渲染一行按钮，返回 (文本, [(列偏移, 宽度, 命令), ...])。"""
    parts: List[str] = []
    spans: List[Tuple[int, int, str]] = []
    offset = 0
    for label, cmd in buttons:
        text = f"[ {label} {cmd} ]"
        if parts:
            parts.append(" ")
            offset += 1
        spans.append((offset, disp_len(text), cmd))
        parts.append(text)
        offset += disp_len(text)
    return "".join(parts), spans


def button_regions(row: int, indent: int, buttons: Sequence[Tuple[str, str]]) -> List[Region]:
    """按钮行的点击区域；``indent`` 为文本前的空白列数。行宽超出终端时返回空表。"""
    text, spans = button_row(buttons)
    if indent + disp_len(text) > _term_cols():
        return []
    return [Region(row, indent + off + 1, indent + off + w + 1, "cmd", cmd)
            for off, w, cmd in spans]


def print_tracked(text: str, measure: bool = False) -> Tuple[Optional[int], Optional[int]]:
    """打印一行，并返回它落在屏幕第几行（``measure`` 为真时同时返回实测宽度）。

    行号通过向终端查询光标位置得到，不受换行与滚动影响；终端不应答时返回
    ``(None, None)``，调用方据此不登记点击区域。
    """
    if not terminal.mouse_available():
        print(text)
        return None, None
    start = terminal.cursor_pos()
    if start is None:
        print(text)
        return None, None
    row, col = start
    if not measure:
        print(text)
        return row, None
    print(text, end="", flush=True)
    end = terminal.cursor_pos()
    print()
    # 行尾恰好折行时 end 会落到下一行，此时宽度不可靠，交由 hand_regions 兜底
    width = end[1] - col if (end is not None and end[0] == row) else None
    return row, width


def prompt(default: str = "", regions: Optional[Sequence[Region]] = None,
           on_click: Optional[Callable[[object], None]] = None) -> str:
    """读取一行输入。

    ``regions`` 非空且终端支持鼠标时，点击会立即生效：
    ``kind == "card"`` 的区域调用 ``on_click(value)`` 并返回 :data:`REDRAW`；
    ``kind == "cmd"`` 的区域直接返回其命令字符串。
    """
    if regions and terminal.mouse_available():
        with terminal.raw_session() as ok:
            if ok:
                return _mouse_prompt(default, regions, on_click)
    return _plain_prompt(default)


def _plain_prompt(default: str = "") -> str:
    try:
        line = input(c("> ", CYAN) + default).strip()
    except (EOFError, KeyboardInterrupt):
        return "quit"
    return line


def _mouse_prompt(default: str, regions: Sequence[Region],
                  on_click: Optional[Callable[[object], None]]) -> str:
    """在原始模式下读一行；调用前必须已经进入 raw_session。"""
    buf = default
    print(c("> ", CYAN) + default, end="", flush=True)
    while True:
        ev = terminal.read_event()
        if ev is None:
            continue
        if isinstance(ev, terminal.MouseEvent):
            if ev.motion or not ev.pressed:
                continue
            if ev.button in (terminal.BTN_WHEEL_UP, terminal.BTN_WHEEL_DOWN):
                continue
            hit = hit_test(regions, ev.y, ev.x)
            if hit is None:
                continue
            print()
            if hit.kind == "cmd":
                return str(hit.value)
            if on_click is not None:
                on_click(hit.value)
            return REDRAW
        if ev.name == "enter":
            print()
            return buf.strip()
        if ev.name == "backspace":
            if buf:
                buf = buf[:-1]
                print("\b \b", end="", flush=True)
            continue
        if ev.name in ("ctrl-c", "ctrl-d"):
            print()
            return "quit"
        if ev.name:
            continue
        if ev.char and ev.char.isprintable():
            buf += ev.char
            print(ev.char, end="", flush=True)
