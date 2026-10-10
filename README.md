# Balatro Terminal

《小丑牌》(Balatro) 的终端复刻版本，以游戏原始 Lua 源码（`balatro_source_code/`）作为实现参考，
提供两套界面：

- **CLI** —— 纯 ANSI 文字界面，逐条输入指令，代码位于 `balatro_cli/`
- **TUI** —— 基于 [Textual](https://textual.textualize.io/) 的全屏图形界面，代码位于 `balatro_tui/`

## 环境要求

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/)

```bash
uv sync
```

## 启动方式

### CLI 版本

```bash
uv run main.py --cli
# 或
uv run cli
```

支持透传参数，例如指定随机种子：

```bash
uv run main.py --cli -s 12345
```

颜色默认关闭（用终端默认前景色，更素净），需要彩色输出时加 `--color`：

```bash
uv run main.py --cli --color
# 或设环境变量
BALATRO_CLI_COLOR=1 uv run main.py --cli
```

`--no-color` / `BALATRO_CLI_COLOR=0` 可显式关闭；命令行参数优先于环境变量。

### TUI 版本

```bash
uv run main.py --tui
# 或
uv run tui
```

### TUI 开发模式

先在一个终端启动 Textual 控制台：

```bash
uv run textual console
```

再在另一个终端以开发模式启动应用，即可在控制台实时查看日志与组件树：

```bash
uv run textual run --dev main.py --tui
```

> `uv run main.py` 不带参数时只打印用法并以退出码 2 结束，需显式指定 `--cli` 或 `--tui`。

## 操作说明

### CLI

启动后进入主菜单，按提示输入序号即可。对局流程为：
选择牌组 → 选择盲注（可跳过换标签）→ 出牌/弃牌 → 结算 → 商店/补充包 → 下一底注。

出牌界面常用指令：

- `1 2 3` / `1-3` —— 选中/取消选中手牌（可多选，重复输入即取消；出牌/弃牌一次最多 5 张）
- `p` —— 打出已选中的牌
- `d` —— 弃掉已选中的牌
- `u` —— 使用消耗品（塔罗/星球/幻灵）
- `s` —— 出售小丑牌或消耗品
- `j` —— 查看小丑牌 / 消耗牌（二级界面）
- `o` —— 手牌排序（花色 ⇄ 点数）
- `o 1 2` —— 手动调整手牌顺序
- `q` —— 退出当前对局

界面上的小丑牌与消耗牌默认**折叠为一行**，只显示「已拥有数量 / 上限」，
按 `j`（或点击该行的「查看」按钮）进入二级界面查看完整列表与效果；
出牌、商店、选择盲注三个界面都支持 `j`。

底部实时消息显示为**一行**：最旧的在左、最新的在右，最多保留最近 3 条；
一行放不下时从最旧的一条开始移出。

盲注限制（眼睛 / 嘴 / 通灵者）**不阻止出牌**：条件不满足时牌照样打出、出牌次数
照扣，只是这一手不计分。出牌界面会在选牌后提前给出提示。

#### 鼠标操作

在 Windows Terminal、VS Code 集成终端等支持 xterm 鼠标协议的终端里，出牌界面与
「选择目标牌」界面可以直接用鼠标操作：

- **点击手牌**即选中/取消选中（等价于输入序号）
- 点击底部的按钮行即可**打出 / 弃牌 / 消耗 / 售卖 / 排序 / 手动 / 退出**
  （选择目标牌界面为**确认 / 取消**）

说明：

- 鼠标是增量能力，**键盘输入全程可用**，两者可以混用。
- 启动时会向终端查询光标位置来探测能力，终端不支持（例如 PyCharm 运行窗口未勾选
  「Emulate terminal in output console」）时自动回退为纯键盘操作。
- 鼠标上报只在等待输入的那一小段时间开启，退出时（含 Ctrl+C 与异常）会还原。
- 开启期间终端自身的拖拽选中文本会被拦截，按住 `Shift` 拖拽仍可选中复制。
- 需要关闭鼠标支持时：`uv run main.py --cli --no-mouse`，或设环境变量
  `BALATRO_CLI_MOUSE=0`；`--mouse` / `BALATRO_CLI_MOUSE=1` 可强制开启。

### TUI

- **首页** —— `←` `→` 切换按钮，`Enter` 确认，`c` 打开收藏，`q` 退出
- **选择牌组** —— `↑` `↓` 在「牌组 / 赌注」两行间切换，`←` `→` 切换选项，`Enter` 确认，`Esc` 返回
- **准备界面** —— 方向键在盲注、标签、小丑牌、消耗品等区域间移动焦点，`Esc` 返回
- **收藏图鉴** —— 方向键在分类宫格间移动，`Enter` 查看详情，`Esc` 返回

## 项目结构

```
main.py                     # 统一入口，按 --cli / --tui 分发
balatro_cli/
  cli/                      # CLI 界面：__main__ / screens / ui / terminal（终端与鼠标）
  core/                     # 牌、牌堆、手牌判定、计分、道具、效果
  data/                     # 盲注、卡包、卡牌中心、消耗品、牌组、标签、优惠券
balatro_tui/
  app.py                    # Textual App
  screens/                  # home / deck_select / preparation / battle / collection
  game_engine/              # 牌、手牌、计分、对局状态
  utils/                    # 本地化文本、收藏数据、Lua 数据解析
  css/                      # 各界面的 .tcss 样式
  data/zh_CN.json           # 中文本地化文本
balatro_source_code/        # 《小丑牌》原始 Lua 源码，作为实现参考
```

## 开发进度

- **CLI**：对局主循环完整，涵盖牌组、盲注与标签、出牌与弃牌、计分与小丑牌效果、
  商店与优惠券、补充包、收藏图鉴。
- **TUI**：首页、选择牌组、准备界面、收藏图鉴已完成；战斗界面（`screens/battle.py`）
  目前仍是空壳，尚未接入对局逻辑。

## 关于 balatro_source_code/

该目录存放《小丑牌》游戏的原始 Lua 源码，是本项目的参考实现。

TUI 的「收藏图鉴」界面会解析其中 `game.lua` 的静态数据（`P_CENTERS`、`P_TAGS`、
`P_BLINDS` 等），用于生成卡牌名称、描述、价格与稀有度。查找顺序为：

1. 环境变量 `BALATRO_LUA_DIR` 指定的目录
2. 项目根目录下的 `balatro_lua_source_code/`
3. 项目根目录下的 `balatro_source_code/`
