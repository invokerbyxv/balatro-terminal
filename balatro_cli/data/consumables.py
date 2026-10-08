"""消耗牌数据：塔罗牌、星球牌、幻灵牌。

来源：game.lua G.P_CENTERS（364-702）。tarot/planet 售价 3，spectral 售价 4。
效果机制在 core/effects.py 的 use_consumable 实现。
"""
from __future__ import annotations

TAROTS = {
    "c_fool": {"cn": "愚者", "cost": 3,
               "effect": "生成 1 张上一次使用过的塔罗牌或星球牌的复制品"},
    "c_magician": {"cn": "魔术师", "cost": 3, "max_highlighted": 2,
                   "effect": "将选中的 1-2 张牌变成幸运牌"},
    "c_high_priestess": {"cn": "女祭司", "cost": 3,
                         "effect": "生成 2 张随机星球牌"},
    "c_empress": {"cn": "女皇", "cost": 3, "max_highlighted": 2,
                  "effect": "将选中的 1-2 张牌变成倍率牌（+4 倍率）"},
    "c_emperor": {"cn": "皇帝", "cost": 3,
                  "effect": "生成 2 张随机塔罗牌"},
    "c_heirophant": {"cn": "教皇", "cost": 3, "max_highlighted": 2,
                     "effect": "将选中的 1-2 张牌变成加分牌（+30 筹码）"},
    "c_lovers": {"cn": "恋人", "cost": 3, "max_highlighted": 1,
                 "effect": "将 1 张选中牌变成百搭牌"},
    "c_chariot": {"cn": "战车", "cost": 3, "max_highlighted": 1,
                  "effect": "将 1 张选中牌变成钢铁牌（×1.5 倍率）"},
    "c_justice": {"cn": "正义", "cost": 3, "max_highlighted": 1,
                  "effect": "将 1 张选中牌变成玻璃牌（×2 倍率）"},
    "c_hermit": {"cn": "隐者", "cost": 3, "extra": 20,
                 "effect": "金钱翻倍，最高 +$20"},
    "c_wheel_of_fortune": {"cn": "命运之轮", "cost": 3, "extra": 4,
                           "effect": "随机 1 张小丑牌获得 1/4 概率附加随机版本"},
    "c_strength": {"cn": "力量", "cost": 3, "max_highlighted": 2,
                   "effect": "将选中的 1-2 张牌点数 +1"},
    "c_hanged_man": {"cn": "倒吊人", "cost": 3, "max_highlighted": 2,
                     "effect": "销毁选中的 1-2 张牌"},
    "c_death": {"cn": "死神", "cost": 3, "min_highlighted": 2, "max_highlighted": 2,
                "effect": "选 2 张牌，将其中最右边的牌复制到其他选中牌"},
    "c_temperance": {"cn": "节制", "cost": 3, "extra": 50,
                     "effect": "获得所有小丑牌售价总和，最高 $50"},
    "c_devil": {"cn": "恶魔", "cost": 3, "max_highlighted": 1,
                "effect": "将 1 张选中牌变成黄金牌（回合结束 +$3）"},
    "c_tower": {"cn": "高塔", "cost": 3, "max_highlighted": 1,
                "effect": "将 1 张选中牌变成石头牌（+50 筹码）"},
    "c_star": {"cn": "星星", "cost": 3, "max_highlighted": 3, "suit_conv": "D",
               "effect": "将选中的 1-3 张牌变成方块"},
    "c_moon": {"cn": "月亮", "cost": 3, "max_highlighted": 3, "suit_conv": "C",
               "effect": "将选中的 1-3 张牌变成梅花"},
    "c_sun": {"cn": "太阳", "cost": 3, "max_highlighted": 3, "suit_conv": "H",
              "effect": "将选中的 1-3 张牌变成红心"},
    "c_judgement": {"cn": "审判", "cost": 3,
                    "effect": "生成 1 张随机小丑牌"},
    "c_world": {"cn": "世界", "cost": 3, "max_highlighted": 3, "suit_conv": "S",
                "effect": "将选中的 1-3 张牌变成黑桃"},
}

PLANETS = {
    "c_mercury": {"cn": "水星", "cost": 3, "hand": "Pair"},
    "c_venus": {"cn": "金星", "cost": 3, "hand": "Three of a Kind"},
    "c_earth": {"cn": "地球", "cost": 3, "hand": "Full House"},
    "c_mars": {"cn": "火星", "cost": 3, "hand": "Four of a Kind"},
    "c_jupiter": {"cn": "木星", "cost": 3, "hand": "Flush"},
    "c_saturn": {"cn": "土星", "cost": 3, "hand": "Straight"},
    "c_uranus": {"cn": "天王星", "cost": 3, "hand": "Two Pair"},
    "c_neptune": {"cn": "海王星", "cost": 3, "hand": "Straight Flush"},
    "c_pluto": {"cn": "冥王星", "cost": 3, "hand": "High Card"},
    "c_planet_x": {"cn": "X 行星", "cost": 3, "hand": "Five of a Kind", "softlock": True},
    "c_ceres": {"cn": "谷神星", "cost": 3, "hand": "Flush House", "softlock": True},
    "c_eris": {"cn": "阋神星", "cost": 3, "hand": "Flush Five", "softlock": True},
}

SPECTRALS = {
    "c_familiar": {"cn": "眷属", "cost": 4,
                   "effect": "销毁 1 张随机手牌，创建 3 张随机人头牌（J/Q/K）"},
    "c_grim": {"cn": "阴森", "cost": 4,
               "effect": "销毁 1 张随机手牌，创建 2 张随机增强的 A 牌"},
    "c_incantation": {"cn": "咒文", "cost": 4,
                      "effect": "销毁 1 张随机手牌，创建 4 张随机增强的数字牌（2-10）"},
    "c_talisman": {"cn": "护符", "cost": 4, "max_highlighted": 1,
                   "effect": "给 1 张选中牌加上金色蜡封"},
    "c_aura": {"cn": "灵光", "cost": 4, "max_highlighted": 1,
               "effect": "给 1 张选中牌附加随机版本"},
    "c_wraith": {"cn": "魅影", "cost": 4,
                 "effect": "创建 1 张稀有小丑牌，并清零你的金钱"},
    "c_sigil": {"cn": "纹章", "cost": 4,
                "effect": "将手牌中所有牌变成随机 1 种花色"},
    "c_ouija": {"cn": "灵应盘", "cost": 4,
                "effect": "将手牌中所有牌变成随机 1 种点数，手牌上限 -1"},
    "c_ectoplasm": {"cn": "灵质", "cost": 4,
                    "effect": "给 1 张随机小丑牌附加负片版本，手牌上限 -1"},
    "c_immolate": {"cn": "献祭", "cost": 4,
                   "effect": "销毁 5 张随机手牌，获得 +$20"},
    "c_ankh": {"cn": "安卡", "cost": 4,
               "effect": "销毁所有其他非永恒小丑牌，复制 1 张随机小丑牌"},
    "c_deja_vu": {"cn": "似曾相识", "cost": 4, "max_highlighted": 1,
                  "effect": "给 1 张选中牌加上红色蜡封"},
    "c_hex": {"cn": "诅咒", "cost": 4,
              "effect": "给 1 张随机小丑牌附加彩绘版本，销毁所有其他非永恒小丑牌"},
    "c_trance": {"cn": "出神", "cost": 4, "max_highlighted": 1,
                 "effect": "给 1 张选中牌加上蓝色蜡封"},
    "c_medium": {"cn": "灵媒", "cost": 4, "max_highlighted": 1,
                 "effect": "给 1 张选中牌加上紫色蜡封"},
    "c_cryptid": {"cn": "神秘生物", "cost": 4, "max_highlighted": 1,
                  "effect": "创建 2 张选中牌的副本"},
    "c_soul": {"cn": "灵魂", "cost": 4, "hidden": True,
               "effect": "创建 1 张传说级小丑牌"},
    "c_black_hole": {"cn": "黑洞", "cost": 4, "hidden": True,
                     "effect": "所有手牌类型等级 +1"},
}

ALL_CONSUMABLES = {}
for _d in (TAROTS, PLANETS, SPECTRALS):
    ALL_CONSUMABLES.update(_d)


def get_consumable_cn(key: str) -> str:
    d = ALL_CONSUMABLES.get(key)
    return d["cn"] if d else key


def needs_target(key: str) -> bool:
    """该消耗牌是否需要从手牌中选定目标牌（魔术师/恋人等塔罗牌，以及部分幻灵牌）。

    有 min/max_highlighted 即需要目标。商店 / 盲注准备阶段手牌为空，
    因此这类消耗牌只能在牌局中使用。
    """
    d = ALL_CONSUMABLES.get(key, {})
    return "max_highlighted" in d or "min_highlighted" in d
