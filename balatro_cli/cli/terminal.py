"""CLI 的终端底层：原始模式、鼠标上报与转义序列解析。

Windows Terminal、VS Code 集成终端等支持 xterm 鼠标协议（SGR 1006）的终端
可以通过 ``ESC[?1000h`` 上报鼠标点击。本模块把 stdin 切到原始模式、打开鼠标
上报，并把读到的字符流解析成 :class:`KeyEvent` / :class:`MouseEvent`。

终端不支持时 :func:`mouse_available` 返回 False，上层会退回普通的 ``input()``，
行为与未引入鼠标之前完全一致。
"""

from __future__ import annotations

import atexit
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import List, Optional, Tuple

# ---------- 事件 ----------

#: 鼠标按键编号（SGR 协议）
BTN_LEFT = 0
BTN_MIDDLE = 1
BTN_RIGHT = 2
BTN_WHEEL_UP = 64
BTN_WHEEL_DOWN = 65


@dataclass
class KeyEvent:
    """一次按键。``char`` 为普通字符，``name`` 为特殊键名。"""

    char: str = ""
    name: str = ""


@dataclass
class MouseEvent:
    """一次鼠标事件。``x`` 为屏幕列，``y`` 为屏幕行，均从 1 开始。"""

    button: int
    x: int
    y: int
    pressed: bool
    motion: bool = False


# ---------- 转义序列 ----------

MOUSE_ON = "\x1b[?1000h\x1b[?1006h"
MOUSE_OFF = "\x1b[?1000l\x1b[?1006l"
CPR_QUERY = "\x1b[6n"

_CPR_RE = re.compile(r"\x1b\[(\d+);(\d+)R")

# Windows 控制台模式位
_ENABLE_PROCESSED_INPUT = 0x0001
_ENABLE_LINE_INPUT = 0x0002
_ENABLE_ECHO_INPUT = 0x0004
_ENABLE_VIRTUAL_TERMINAL_INPUT = 0x0200

_STD_INPUT_HANDLE = -10


def _is_tty() -> bool:
    try:
        return bool(sys.stdin) and sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


class _Terminal:
    def __init__(self) -> None:
        self._probed: Optional[bool] = None
        self._force: Optional[bool] = None
        self._push: List[str] = []          # 回推缓冲（探测/转义序列的残留字符）
        self._raw = False
        self._mouse = False
        self._saved_in_mode: Optional[int] = None
        self._saved_attrs = None
        atexit.register(self.restore)

    # ------------------------------------------------------------------
    # 能力探测
    # ------------------------------------------------------------------
    def force(self, value: Optional[bool]) -> None:
        """强制开启/关闭鼠标支持（None 表示恢复自动探测）。"""
        self._force = value
        self._probed = None

    def mouse_available(self) -> bool:
        if self._force is not None:
            return self._force
        if self._probed is None:
            self._probed = self._detect()
        return self._probed

    def _detect(self) -> bool:
        env = os.environ.get("BALATRO_CLI_MOUSE", "").strip().lower()
        if env in ("0", "off", "false", "no"):
            return False
        if env in ("1", "on", "true", "yes"):
            return True
        if os.environ.get("TERM", "").lower() == "dumb":
            return False
        if not _is_tty():
            return False
        return self._cpr_probe()

    def _cpr_probe(self) -> bool:
        """发 ESC[6n 查光标位置；终端能应答才说明它处理转义序列。

        这样在 PyCharm 运行窗口（未开启终端模拟）等环境下会自动判定为不支持，
        避免出现「不回显、打不了字」的回归。
        """
        if not self._enter_raw():
            return False
        try:
            sys.stdout.write(CPR_QUERY)
            sys.stdout.flush()
            buf = ""
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                ch = self._read_char(0.05)
                if ch is None:
                    continue
                buf += ch
                m = _CPR_RE.search(buf)
                if m:
                    self._push[:0] = list(buf[m.end():])
                    return True
                if len(buf) > 64:
                    break
            self._push[:0] = list(buf)
            return False
        except Exception:
            return False
        finally:
            self._exit_raw()

    # ------------------------------------------------------------------
    # 原始模式
    # ------------------------------------------------------------------
    def _enter_raw(self) -> bool:
        if self._raw:
            return True
        try:
            if os.name == "nt":
                import ctypes
                from ctypes import wintypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
                mode = wintypes.DWORD()
                if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                    return False
                self._saved_in_mode = mode.value
                new_mode = (
                    mode.value
                    & ~_ENABLE_PROCESSED_INPUT
                    & ~_ENABLE_LINE_INPUT
                    & ~_ENABLE_ECHO_INPUT
                ) | _ENABLE_VIRTUAL_TERMINAL_INPUT
                if not kernel32.SetConsoleMode(handle, new_mode):
                    self._saved_in_mode = None
                    return False
            else:
                import termios

                fd = sys.stdin.fileno()
                attrs = termios.tcgetattr(fd)
                self._saved_attrs = attrs
                new_attrs = list(attrs)
                # lflag：关掉行缓冲、回显与信号（Ctrl+C 以 \x03 字符到达，由我们处理）
                new_attrs[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG)
                new_attrs[6] = list(attrs[6])
                new_attrs[6][termios.VMIN] = 1
                new_attrs[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, new_attrs)
            self._raw = True
            return True
        except Exception:
            self._saved_in_mode = None
            self._saved_attrs = None
            return False

    def _exit_raw(self) -> None:
        if not self._raw:
            return
        self._raw = False
        try:
            if os.name == "nt":
                if self._saved_in_mode is not None:
                    import ctypes

                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
                    kernel32.SetConsoleMode(handle, self._saved_in_mode)
            else:
                if self._saved_attrs is not None:
                    import termios

                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, self._saved_attrs)
        except Exception:
            pass
        finally:
            self._saved_in_mode = None
            self._saved_attrs = None

    # ------------------------------------------------------------------
    # 鼠标上报
    # ------------------------------------------------------------------
    def enable_mouse(self) -> None:
        if self._mouse:
            return
        try:
            sys.stdout.write(MOUSE_ON)
            sys.stdout.flush()
            self._mouse = True
        except Exception:
            pass

    def disable_mouse(self) -> None:
        if not self._mouse:
            return
        self._mouse = False
        try:
            sys.stdout.write(MOUSE_OFF)
            sys.stdout.flush()
        except Exception:
            pass

    def restore(self) -> None:
        """还原终端状态（幂等）。异常退出时由 atexit 兜底调用。"""
        self.disable_mouse()
        self._exit_raw()

    @contextmanager
    def raw_session(self, mouse: bool = True):
        """原始模式 +（可选）鼠标上报的上下文管理器（可嵌套）。"""
        already_raw = self._raw
        ok = self._enter_raw()
        enabled = False
        if ok and mouse and not self._mouse:
            self.enable_mouse()
            enabled = True
        try:
            yield ok
        finally:
            if enabled:
                self.disable_mouse()
            if not already_raw:
                self._exit_raw()

    def cursor_pos(self, timeout: float = 0.2) -> Optional[Tuple[int, int]]:
        """查询光标位置，返回 ``(行, 列)``（均从 1 开始）；终端不应答时返回 None。

        用它来定位某一行在屏幕上的行号，以及实测一行文字真实占了多少列——
        ``♠♥♣`` 这类「东亚宽度歧义」字符各终端渲染宽度不一致，按实测值校正
        点击区域才不会点错牌。
        """
        with self.raw_session(mouse=False) as ok:
            if not ok:
                return None
            try:
                sys.stdout.write(CPR_QUERY)
                sys.stdout.flush()
            except Exception:
                return None
            buf = ""
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                ch = self._read_char(0.05)
                if ch is None:
                    continue
                buf += ch
                m = _CPR_RE.search(buf)
                if m:
                    self._push[:0] = list(buf[m.end():])
                    return int(m.group(1)), int(m.group(2))
                if len(buf) > 64:
                    break
            self._push[:0] = list(buf)
            return None

    # ------------------------------------------------------------------
    # 读取与解析
    # ------------------------------------------------------------------
    def _read_char(self, timeout: Optional[float] = None) -> Optional[str]:
        if self._push:
            return self._push.pop(0)
        if os.name == "nt":
            return self._read_char_win(timeout)
        return self._read_char_posix(timeout)

    def _read_char_win(self, timeout: Optional[float]) -> Optional[str]:
        import msvcrt

        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if msvcrt.kbhit():
                return msvcrt.getwch()
            if deadline is not None and time.monotonic() >= deadline:
                return None
            time.sleep(0.005)

    def _read_char_posix(self, timeout: Optional[float]) -> Optional[str]:
        import select

        fd = sys.stdin.fileno()
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if deadline is None:
                wait = None
            else:
                wait = deadline - time.monotonic()
                if wait <= 0:
                    return None
            ready, _, _ = select.select([fd], [], [], wait)
            if not ready:
                return None
            data = os.read(fd, 1)
            if not data:
                return None
            first = data[0]
            if first < 0x80:
                return chr(first)
            # UTF-8 多字节：补齐剩余字节
            if 0xC0 <= first < 0xE0:
                need = 2
            elif 0xE0 <= first < 0xF0:
                need = 3
            else:
                need = 4
            buf = bytearray(data)
            while len(buf) < need:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    break
                more = os.read(fd, need - len(buf))
                if not more:
                    break
                buf += more
            return buf.decode("utf-8", errors="replace")

    def read_event(self, timeout: Optional[float] = None):
        """读取一个事件；超时返回 None。"""
        ch = self._read_char(timeout)
        if ch is None:
            return None
        if ch == "\x1b":
            return self._read_escape()
        if ch in ("\x00", "\xe0"):
            # Windows 传统功能键前缀，吞掉后续编码字节
            self._read_char(0.05)
            return KeyEvent(name="ignored")
        if ch in ("\r", "\n"):
            return KeyEvent(name="enter")
        if ch in ("\x7f", "\x08"):
            return KeyEvent(name="backspace")
        if ch == "\x03":
            return KeyEvent(name="ctrl-c")
        if ch == "\x04":
            return KeyEvent(name="ctrl-d")
        return KeyEvent(char=ch)

    def _read_escape(self):
        ch = self._read_char(0.05)
        if ch is None:
            return KeyEvent(name="escape")
        if ch == "[":
            return self._parse_csi(self._read_csi())
        if ch == "O":
            nxt = self._read_char(0.05)
            arrows = {"A": "up", "B": "down", "C": "right", "D": "left"}
            if nxt in arrows:
                return KeyEvent(name=arrows[nxt])
            if nxt is not None:
                self._push.insert(0, nxt)
            return KeyEvent(name="escape")
        self._push.insert(0, ch)
        return KeyEvent(name="escape")

    def _read_csi(self) -> str:
        """读取 CSI 序列的参数与结尾字节（不含开头的 ESC[）。"""
        body: List[str] = []
        while True:
            ch = self._read_char(0.05)
            if ch is None:
                return ""
            if ch == "\x1b":
                self._push.insert(0, ch)
                return ""
            if 0x40 <= ord(ch) <= 0x7E:
                return "".join(body) + ch
            body.append(ch)
            if len(body) > 32:
                return ""

    def _parse_csi(self, seq: str):
        if not seq:
            return KeyEvent(name="ignored")
        if seq[0] == "<" and seq[-1] in "Mm":
            return self._mouse_sgr(seq)
        if seq == "M":
            return self._mouse_x10()
        arrows = {"A": "up", "B": "down", "C": "right", "D": "left"}
        if seq in arrows:
            return KeyEvent(name=arrows[seq])
        return KeyEvent(name="ignored")

    @staticmethod
    def _mouse_sgr(seq: str) -> Optional[MouseEvent]:
        try:
            b, x, y = (int(p) for p in seq[1:-1].split(";"))
        except ValueError:
            return None
        return _decode_mouse(b, x, y, pressed=seq[-1] == "M")

    def _mouse_x10(self) -> Optional[MouseEvent]:
        """兼容旧式 ESC[M + 3 字节的鼠标编码。"""
        raw = [self._read_char(0.05) for _ in range(3)]
        if any(c is None for c in raw):
            return None
        b, x, y = (ord(c) - 32 for c in raw)
        return _decode_mouse(b, x, y, pressed=(b & 3) != 3)


def _decode_mouse(b: int, x: int, y: int, pressed: bool) -> MouseEvent:
    code = b & ~(4 | 8 | 16)        # 去掉 Shift/Meta/Ctrl 修饰位
    motion = bool(code & 32)
    if motion:
        code &= ~32
    if code >= 64:
        button = code                # 滚轮
    else:
        button = code & 3            # 0 左 1 中 2 右
    return MouseEvent(button=button, x=x, y=y, pressed=pressed, motion=motion)


_terminal = _Terminal()


# ---------- 模块级便捷函数 ----------

def mouse_available() -> bool:
    return _terminal.mouse_available()


def force(value: Optional[bool]) -> None:
    _terminal.force(value)


def raw_session(mouse: bool = True):
    return _terminal.raw_session(mouse)


def read_event(timeout: Optional[float] = None):
    return _terminal.read_event(timeout)


def cursor_pos(timeout: float = 0.2) -> Optional[Tuple[int, int]]:
    return _terminal.cursor_pos(timeout)


def restore() -> None:
    _terminal.restore()
