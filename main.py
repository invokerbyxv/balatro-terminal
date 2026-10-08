"""Balatro Terminal 统一启动入口。

用法::

    uv run main.py --cli     # 启动 CLI 版本
    uv run main.py --tui     # 启动 TUI 版本

等价的命令入口（由 pyproject.toml 的 [project.scripts] 提供）::

    uv run cli
    uv run tui

TUI 开发模式（需要另开一个终端运行 ``uv run textual console``）::

    uv run textual run --dev main.py --tui
"""

from __future__ import annotations

import sys


def _force_utf8_output() -> None:
    """避免 Windows 控制台按 GBK 输出中文时出现乱码。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


USAGE = """\
Balatro Terminal

用法:
  uv run main.py --cli     启动 CLI 版本
  uv run main.py --tui     启动 TUI 版本

命令入口:
  uv run cli               等价于 uv run main.py --cli
  uv run tui               等价于 uv run main.py --tui

TUI 开发模式:
  uv run textual run --dev main.py --tui

CLI 版本支持透传参数，例如指定随机种子:
  uv run main.py --cli -s 12345
  uv run main.py --cli --color   # 彩色输出（默认关闭，也可用 BALATRO_CLI_COLOR=1）
"""


def run_cli(argv: list[str]) -> None:
    """启动 CLI 版本，``argv`` 为透传给 CLI 的参数。"""
    from balatro_cli.cli.__main__ import main as cli_main

    cli_main(argv)


def run_tui(argv: list[str]) -> None:
    """启动 TUI 版本，``argv`` 为透传给 TUI 的参数。"""
    from balatro_tui.app import main as tui_main

    tui_main(argv)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if any(arg in ("-h", "--help") for arg in args):
        _force_utf8_output()
        print(USAGE, end="")
        return 0

    mode: str | None = None
    passthrough: list[str] = []
    for arg in args:
        if mode is None and arg in ("--cli", "--tui"):
            mode = arg[2:]
        else:
            passthrough.append(arg)

    if mode == "cli":
        run_cli(passthrough)
    elif mode == "tui":
        run_tui(passthrough)
    else:
        _force_utf8_output()
        print(USAGE, end="", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
