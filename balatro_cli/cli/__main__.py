import os
import sys

from . import ui
from .ui import setup_console
from . import terminal
from .screens import App


def main(argv: list[str] | None = None) -> None:
    """启动 CLI 版本。

    Args:
        argv: 命令行参数（不含程序名）。为 None 时读取 ``sys.argv[1:]``。
    """
    setup_console()
    args = list(sys.argv[1:] if argv is None else argv)
    if "--no-mouse" in args:
        terminal.force(False)
    elif "--mouse" in args:
        terminal.force(True)
    # 颜色默认关闭；--color 开启，--no-color 强制关闭，都没给时看环境变量
    if "--color" in args:
        ui.set_color(True)
    elif "--no-color" in args:
        ui.set_color(False)
    else:
        ui.set_color(os.environ.get("BALATRO_CLI_COLOR", "").strip().lower()
                     in ("1", "on", "true", "yes"))
    seed = None
    if "-s" in args:
        i = args.index("-s")
        if i + 1 < len(args):
            try:
                seed = int(args[i + 1])
            except ValueError:
                pass
    app = App()
    if seed is not None:
        app._seed_override = seed
    app.run()


if __name__ == "__main__":
    main()
