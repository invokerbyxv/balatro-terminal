from textual.app import App
from .screens.home import HomeScreen

class BalatroApp(App):
    BINDINGS = [
        ("q", "quit", "退出")
    ]
    
    def __init__(self):
        super().__init__()
        self.game_state = None
    
    def on_mount(self) -> None:
        self.push_screen(HomeScreen())
    
    def action_quit(self):
        self.exit()


def main(argv: list[str] | None = None) -> None:
    """启动 TUI 版本。

    Args:
        argv: 预留的透传参数，目前 Textual 通过 ``TEXTUAL`` 环境变量接收
            开发模式等配置，因此这里不做解析。
    """
    BalatroApp().run()


if __name__ == "__main__":
    main()
