"""赌注（Stake）数据。

来源：game.lua G.P_STAKES（252-261）与 Game:start_run 的难度修正（2049-2059）。
赌注是难度梯度：每一档都**包含**前面档位的修正，所以用 ``level`` 表示档位，
运行期只判断 ``stake_level >= n``。
"""
from __future__ import annotations

STAKES = {
    "stake_white": {
        "cn": "白赌注", "level": 1, "order": 1,
        "effect": "标准难度",
    },
    "stake_red": {
        "cn": "红赌注", "level": 2, "order": 2,
        "effect": "小盲注不再给奖励金",
    },
    "stake_green": {
        "cn": "绿赌注", "level": 3, "order": 3,
        "effect": "盲注分数增速 ×2",
    },
    "stake_black": {
        "cn": "黑赌注", "level": 4, "order": 4,
        "effect": "商店可出现永恒小丑",
    },
    "stake_blue": {
        "cn": "蓝赌注", "level": 5, "order": 5,
        "effect": "每回合弃牌次数 -1",
    },
    "stake_purple": {
        "cn": "紫赌注", "level": 6, "order": 6,
        "effect": "盲注分数增速 ×3",
    },
    "stake_orange": {
        "cn": "橙赌注", "level": 7, "order": 7,
        "effect": "商店可出现易腐小丑",
    },
    "stake_gold": {
        "cn": "金赌注", "level": 8, "order": 8,
        "effect": "商店可出现租赁小丑",
    },
}

#: 由低到高的选择顺序
STAKE_ORDER = ["stake_white", "stake_red", "stake_green", "stake_black",
               "stake_blue", "stake_purple", "stake_orange", "stake_gold"]


def stake_cfg(key: str) -> dict:
    return STAKES.get(key, STAKES["stake_white"])


def stake_level(key: str) -> int:
    return stake_cfg(key)["level"]
