"""盲注（Blind）数据目录。

来源：game.lua G.P_BLINDS（263-296）、blind.lua、functions/misc_functions.lua
get_blind_amount（919-954）。
"""
from __future__ import annotations

# 底注难度表（get_blind_amount 的三个 scaling 档位）
# scaling=1 默认；scaling=2 等离子牌组；scaling=3 挑战模式
BLIND_AMOUNTS = {
    1: {1: 300, 2: 800, 3: 2000, 4: 5000, 5: 11000, 6: 20000, 7: 35000, 8: 50000},
    2: {1: 300, 2: 900, 3: 2600, 4: 8000, 5: 20000, 6: 36000, 7: 60000, 8: 100000},
    3: {1: 300, 2: 1000, 3: 3200, 4: 9000, 5: 25000, 6: 60000, 7: 110000, 8: 200000},
}

# ante>8 的无限模式基础值
BLIND_AMOUNT_INF = {1: 50000, 2: 100000, 3: 200000}


def get_blind_amount(ante: int, scaling: int = 1) -> int:
    """底注 ante 的基础筹码（再乘盲注 mult 得实际门槛）。"""
    if ante < 1:
        return 100
    if ante <= 8:
        return BLIND_AMOUNTS[scaling][ante]
    # 无限模式：floor(a * (1.6 + (0.75*c)^d)^c)，c=ante-8, d=1+0.2*c
    a = BLIND_AMOUNT_INF.get(scaling, 50000)
    c = ante - 8
    d = 1 + 0.2 * c
    amount = int(a * (1.6 + (0.75 * c) ** d) ** c)
    # 向下取整到 2 位有效数字
    if amount > 0:
        order = 10 ** (len(str(amount)) - 2)
        amount -= amount % order
    return amount


# ---------------------------------------------------------------------------
# 盲注定义
# ---------------------------------------------------------------------------
# 每个盲注：cn=中文名, dollars=胜出奖金, mult=门槛倍率, min/max=头目可出现的底注区间,
# showdown=是否决战头目, effect=机制描述（引擎在 blind_effects.py 实现）

SMALL_BLIND = {
    "key": "bl_small", "cn": "小盲注", "dollars": 3, "mult": 1.0,
    "effect": "标准盲注",
}
BIG_BLIND = {
    "key": "bl_big", "cn": "大盲注", "dollars": 4, "mult": 1.5,
    "effect": "标准盲注",
}

BOSS_BLINDS = {
    "bl_hook": {"cn": "钩子", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                "effect": "每打完一手牌，随机弃掉你手牌中的 2 张"},
    "bl_mouth": {"cn": "嘴", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                 "effect": "本回合只能打出一手与上一手相同的手牌类型"},
    "bl_fish": {"cn": "鱼", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                "effect": "每打完一手牌后，抓到的牌背面朝上"},
    "bl_club": {"cn": "俱乐部", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                "effect": "所有梅花牌被禁用"},
    "bl_manacle": {"cn": "手铐", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                   "effect": "手牌上限 -1"},
    "bl_tooth": {"cn": "牙", "dollars": 5, "mult": 2.0, "min": 3, "max": 10,
                 "effect": "每打出一张牌，失去 $1"},
    "bl_wall": {"cn": "墙", "dollars": 5, "mult": 4.0, "min": 2, "max": 10,
                "effect": "超大盲注：得分门槛 ×4"},
    "bl_house": {"cn": "房子", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                 "effect": "本回合你打出的第一手牌背面朝上"},
    "bl_mark": {"cn": "记号", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                "effect": "所有人头牌（J/Q/K）背面朝上"},
    "bl_wheel": {"cn": "轮子", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                 "effect": "每张抽到的牌有 1/7 概率背面朝上"},
    "bl_arm": {"cn": "手臂", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
               "effect": "你打出的手牌类型等级 -1"},
    "bl_psychic": {"cn": "通灵者", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                   "effect": "必须打出 5 张牌才能得分"},
    "bl_goad": {"cn": "刺棒", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                "effect": "所有黑桃牌被禁用"},
    "bl_water": {"cn": "水", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                 "effect": "以 0 次弃牌开始本回合"},
    "bl_eye": {"cn": "眼睛", "dollars": 5, "mult": 2.0, "min": 3, "max": 10,
               "effect": "本回合内不得打出与之前相同的手牌类型"},
    "bl_plant": {"cn": "植物", "dollars": 5, "mult": 2.0, "min": 4, "max": 10,
                 "effect": "所有人头牌（J/Q/K）被禁用"},
    "bl_needle": {"cn": "针", "dollars": 5, "mult": 1.0, "min": 2, "max": 10,
                  "effect": "本回合只能打出 1 手牌"},
    "bl_head": {"cn": "头", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                "effect": "所有红心牌被禁用"},
    "bl_window": {"cn": "窗", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                  "effect": "所有方块牌被禁用"},
    "bl_serpent": {"cn": "蛇", "dollars": 5, "mult": 2.0, "min": 5, "max": 10,
                   "effect": "每次打出或弃牌后，总是抽 3 张牌"},
    "bl_pillar": {"cn": "柱", "dollars": 5, "mult": 2.0, "min": 1, "max": 10,
                  "effect": "本底注内你之前打出的牌被禁用"},
    "bl_flint": {"cn": "燧石", "dollars": 5, "mult": 2.0, "min": 2, "max": 10,
                 "effect": "基础筹码与基础倍率减半"},
    "bl_ox": {"cn": "牛", "dollars": 5, "mult": 2.0, "min": 6, "max": 10,
              "effect": "打出你玩得最多的手牌类型时，金钱归零"},
    # 决战头目（ante 为 8 的倍数且 ≥2 时出现）
    "bl_final_bell": {"cn": "青钟", "dollars": 8, "mult": 2.0, "min": 8, "max": 8,
                      "showdown": True, "effect": "1 张手牌始终处于选中状态"},
    "bl_final_leaf": {"cn": "绿叶", "dollars": 8, "mult": 2.0, "min": 8, "max": 8,
                      "showdown": True, "effect": "所有牌被禁用，直到你卖掉 1 张小丑牌"},
    "bl_final_vessel": {"cn": "紫瓶", "dollars": 8, "mult": 6.0, "min": 8, "max": 8,
                        "showdown": True, "effect": "超大盲注：得分门槛 ×6"},
    "bl_final_acorn": {"cn": "琥珀橡果", "dollars": 8, "mult": 2.0, "min": 8, "max": 8,
                       "showdown": True, "effect": "洗乱并翻转你所有的小丑牌"},
    "bl_final_heart": {"cn": "深红之心", "dollars": 8, "mult": 2.0, "min": 8, "max": 8,
                       "showdown": True, "effect": "每打出一手牌，随机禁用 1 张小丑牌"},
}


def get_blind_cfg(key: str) -> dict:
    if key == "bl_small":
        return dict(SMALL_BLIND)
    if key == "bl_big":
        return dict(BIG_BLIND)
    return dict(BOSS_BLINDS[key])


def blind_chips(key: str, ante: int, scaling: int = 1) -> int:
    """盲注实际得分门槛。"""
    cfg = get_blind_cfg(key)
    base = get_blind_amount(ante, scaling)
    return int(base * cfg["mult"])
