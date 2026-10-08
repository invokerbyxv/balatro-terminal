"""卡牌包（Booster）数据与增强/版本/蜡封数据。

来源：game.lua G.P_CENTERS 的 Booster 部分（665-696）、Enhanced/Edition/Seal 部分。
"""
from __future__ import annotations

# 卡牌包：pack_size=开出张数, choose=可选张数, kind=种类
BOOSTERS = {
    "p_arcana_normal": {"cn": "塔罗包", "cost": 4, "pack_size": 3, "choose": 1, "kind": "tarot"},
    "p_arcana_jumbo": {"cn": "巨型塔罗包", "cost": 6, "pack_size": 5, "choose": 1, "kind": "tarot"},
    "p_arcana_mega": {"cn": "超大塔罗包", "cost": 8, "pack_size": 5, "choose": 2, "kind": "tarot"},
    "p_celestial_normal": {"cn": "星球包", "cost": 4, "pack_size": 3, "choose": 1, "kind": "planet"},
    "p_celestial_jumbo": {"cn": "巨型星球包", "cost": 6, "pack_size": 5, "choose": 1, "kind": "planet"},
    "p_celestial_mega": {"cn": "超大星球包", "cost": 8, "pack_size": 5, "choose": 2, "kind": "planet"},
    "p_spectral_normal": {"cn": "幻灵包", "cost": 4, "pack_size": 2, "choose": 1, "kind": "spectral"},
    "p_spectral_jumbo": {"cn": "巨型幻灵包", "cost": 6, "pack_size": 4, "choose": 1, "kind": "spectral"},
    "p_spectral_mega": {"cn": "超大幻灵包", "cost": 8, "pack_size": 4, "choose": 2, "kind": "spectral"},
    "p_standard_normal": {"cn": "标准包", "cost": 4, "pack_size": 3, "choose": 1, "kind": "standard"},
    "p_standard_jumbo": {"cn": "巨型标准包", "cost": 6, "pack_size": 5, "choose": 1, "kind": "standard"},
    "p_standard_mega": {"cn": "超大标准包", "cost": 8, "pack_size": 5, "choose": 2, "kind": "standard"},
    "p_buffoon_normal": {"cn": "小丑包", "cost": 4, "pack_size": 2, "choose": 1, "kind": "buffoon"},
    "p_buffoon_jumbo": {"cn": "巨型小丑包", "cost": 6, "pack_size": 4, "choose": 1, "kind": "buffoon"},
    "p_buffoon_mega": {"cn": "超大滑稽包", "cost": 8, "pack_size": 4, "choose": 2, "kind": "buffoon"},
}

# 补充包出现权重（普通种类权重 1.0，小丑 0.6；Mega 变体额外权重）
# 商店卡包只卖：小丑包 / 塔罗包 / 星球包 / 标准包（幻灵包仅由标签等效果开启）
PACK_WEIGHTS = {
    "p_arcana_normal": 1.0, "p_celestial_normal": 1.0, "p_standard_normal": 1.0,
    "p_buffoon_normal": 0.6,
    "p_arcana_mega": 0.25, "p_celestial_mega": 0.25, "p_standard_mega": 0.25,
    "p_buffoon_mega": 0.15,
}

# 增强卡（Enhanced）：数值对应 get_chip_bonus / get_chip_mult / get_chip_x_mult 等
ENHANCED = {
    "m_bonus": {"cn": "加分牌", "bonus": 30},
    "m_mult": {"cn": "倍率牌", "mult": 4},
    "m_wild": {"cn": "百搭牌", "config": {}},
    "m_glass": {"cn": "玻璃牌", "x_mult": 2, "break_chance": 4},
    "m_steel": {"cn": "钢铁牌", "h_x_mult": 1.5},
    "m_stone": {"cn": "石头牌", "bonus": 50},
    "m_gold": {"cn": "黄金牌", "h_dollars": 3},
    "m_lucky": {"cn": "幸运牌", "mult": 20, "p_dollars": 20, "mult_chance": 5, "dollars_chance": 15},
}

# 版本（Edition）
EDITIONS = {
    "e_base": {"cn": "基础", "config": {}},
    "e_foil": {"cn": "箔片", "chips": 50},
    "e_holo": {"cn": "全息", "mult": 10},
    "e_polychrome": {"cn": "彩绘", "x_mult": 1.5},
    "e_negative": {"cn": "负片", "negative": True},
}

# 蜡封（Seal）
SEALS = {
    "gold": {"cn": "金色蜡封", "effect": "打出时 +$3"},
    "red": {"cn": "红色蜡封", "effect": "重复触发 1 次"},
    "blue": {"cn": "蓝色蜡封", "effect": "回合结束生成对应星球牌"},
    "purple": {"cn": "紫色蜡封", "effect": "弃牌时生成塔罗牌"},
}

# 版本附加价格（购买时）
EDITION_PRICE = {"e_holo": 3, "e_foil": 2, "e_polychrome": 5, "e_negative": 5}

# 基础 52 张牌构建
RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")
SUITS = ("S", "H", "C", "D")
