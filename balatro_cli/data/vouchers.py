"""优惠券（Voucher）数据。

来源：game.lua G.P_CENTERS 的 Voucher 部分（592-624）。全部售价 $10。
二级券 requires=需先购买的一级券。效果在 core/effects.py apply_voucher 实现。
"""
from __future__ import annotations

VOUCHERS = {
    # 一级券
    "v_overstock_norm": {"cn": "过载", "cost": 10, "upgrade": "v_overstock_plus",
                         "effect": "商店多 1 个小丑牌栏位"},
    "v_clearance_sale": {"cn": "清仓大甩卖", "cost": 10, "upgrade": "v_liquidation", "discount": 25,
                         "effect": "所有商店商品 75 折"},
    "v_hone": {"cn": "磨砺", "cost": 10, "upgrade": "v_glow_up",
               "effect": "商店小丑牌附加版本的概率翻倍"},
    "v_reroll_surplus": {"cn": "重掷富余", "cost": 10, "upgrade": "v_reroll_glut",
                         "effect": "商店重掷费用 -2"},
    "v_crystal_ball": {"cn": "水晶球", "cost": 10, "upgrade": "v_omen_globe",
                       "effect": "消耗品格 +1"},
    "v_telescope": {"cn": "望远镜", "cost": 10, "upgrade": "v_observatory",
                    "effect": "星球包中的第一张牌总是最常用手牌对应的星球牌"},
    "v_grabber": {"cn": "抓取者", "cost": 10, "upgrade": "v_nacho_tong",
                  "effect": "每回合出牌次数 +1"},
    "v_wasteful": {"cn": "浪费者", "cost": 10, "upgrade": "v_recyclomancy",
                   "effect": "每回合弃牌次数 +1"},
    "v_tarot_merchant": {"cn": "塔罗商人", "cost": 10, "upgrade": "v_tarot_tycoon",
                         "effect": "商店塔罗牌出现率提升"},
    "v_planet_merchant": {"cn": "星球商人", "cost": 10, "upgrade": "v_planet_tycoon",
                          "effect": "商店星球牌出现率提升"},
    "v_seed_money": {"cn": "种子资金", "cost": 10, "upgrade": "v_money_tree",
                     "effect": "利息上限 +$25（最高 $50）"},
    "v_blank": {"cn": "空白", "cost": 10, "upgrade": "v_antimatter",
                "effect": "无效果"},
    "v_magic_trick": {"cn": "魔术戏法", "cost": 10, "upgrade": "v_illusion",
                      "effect": "商店基础扑克牌出现率提升"},
    "v_hieroglyph": {"cn": "象形文字", "cost": 10, "upgrade": "v_petroglyph",
                     "effect": "底注 -1，每回合出牌次数 -1"},
    "v_directors_cut": {"cn": "导演剪辑版", "cost": 10, "upgrade": "v_retcon",
                        "effect": "每底注可花 $10 重掷 1 次头目盲注"},
    "v_paint_brush": {"cn": "画笔", "cost": 10, "upgrade": "v_palette",
                      "effect": "手牌上限 +1"},
    # 二级券
    "v_overstock_plus": {"cn": "过载增强版", "cost": 10, "requires": "v_overstock_norm",
                         "effect": "商店再 +1 个小丑牌栏位"},
    "v_liquidation": {"cn": "清算", "cost": 10, "requires": "v_clearance_sale", "discount": 50,
                      "effect": "所有商店商品半价"},
    "v_glow_up": {"cn": "发光升级", "cost": 10, "requires": "v_hone",
                  "effect": "商店小丑牌附加版本的概率大幅提升"},
    "v_reroll_glut": {"cn": "重掷过剩", "cost": 10, "requires": "v_reroll_surplus",
                      "effect": "商店重掷费用再 -2"},
    "v_omen_globe": {"cn": "预兆之球", "cost": 10, "requires": "v_crystal_ball",
                     "effect": "消耗品格 +1；塔罗包有 20% 概率开出幻灵牌"},
    "v_observatory": {"cn": "天文台", "cost": 10, "requires": "v_telescope",
                      "effect": "手中的星球牌若匹配手牌类型，提供 ×1.5 倍率"},
    "v_nacho_tong": {"cn": "纳乔舌", "cost": 10, "requires": "v_grabber",
                     "effect": "每回合出牌次数 +2"},
    "v_recyclomancy": {"cn": "回收术", "cost": 10, "requires": "v_wasteful",
                       "effect": "每回合弃牌次数 +2"},
    "v_tarot_tycoon": {"cn": "塔罗大亨", "cost": 10, "requires": "v_tarot_merchant",
                       "effect": "商店塔罗牌出现率大幅提升"},
    "v_planet_tycoon": {"cn": "星球大亨", "cost": 10, "requires": "v_planet_merchant",
                        "effect": "商店星球牌出现率大幅提升"},
    "v_money_tree": {"cn": "摇钱树", "cost": 10, "requires": "v_seed_money",
                     "effect": "利息上限升至 $100"},
    "v_antimatter": {"cn": "反物质", "cost": 10, "requires": "v_blank",
                     "effect": "小丑牌栏位 +1"},
    "v_illusion": {"cn": "幻象", "cost": 10, "requires": "v_magic_trick",
                   "effect": "商店基础牌出现率大幅提升，并可能附加版本/增强"},
    "v_petroglyph": {"cn": "岩画", "cost": 10, "requires": "v_hieroglyph",
                     "effect": "底注 -1，每回合弃牌次数 -1"},
    "v_retcon": {"cn": "回溯", "cost": 10, "requires": "v_directors_cut",
                 "effect": "无限次花 $10 重掷头目盲注"},
    "v_palette": {"cn": "调色板", "cost": 10, "requires": "v_paint_brush",
                  "effect": "手牌上限 +2"},
}

# 二级券 → 升级来源
UPGRADE_MAP = {d.get("upgrade"): k for k, d in VOUCHERS.items() if "upgrade" in d}


def get_next_voucher(used: set) -> str | None:
    """商店应出售的下一张优惠券：优先已购券的升级券，否则任意未购入的一级券。

    保证商店每店默认出售一张优惠券（全部买完才返回 None）。
    """
    # 1) 升级券：已购一级券对应的二级券
    for key, d in VOUCHERS.items():
        req = d.get("requires")
        if req and req in used and key not in used:
            return key
    # 2) 兜底：任意未购入的一级券
    for key, d in VOUCHERS.items():
        if key not in used and d.get("requires") is None:
            return key
    return None
