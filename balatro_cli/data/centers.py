"""小丑牌（Joker）数据目录 + 商店生成辅助。

来源：game.lua G.P_CENTERS（368-526）的 150 个小丑定义。
rarity: 1=common 2=uncommon 3=rare 4=legendary。
"""
from __future__ import annotations

# 每项：cn=中文名, r=稀有度, c=价格, e=效果描述
JOKERS = {
    # ---------- common ----------
    "j_joker": {"cn": "小丑", "r": 1, "c": 2, "e": "无条件 +4 倍率"},
    "j_greedy_joker": {"cn": "贪婪小丑", "r": 1, "c": 5, "e": "打出的方块牌计分时 +3 倍率"},
    "j_lusty_joker": {"cn": "色欲小丑", "r": 1, "c": 5, "e": "打出的红心牌计分时 +3 倍率"},
    "j_wrathful_joker": {"cn": "愤怒小丑", "r": 1, "c": 5, "e": "打出的黑桃牌计分时 +3 倍率"},
    "j_gluttenous_joker": {"cn": "暴食小丑", "r": 1, "c": 5, "e": "打出的梅花牌计分时 +3 倍率"},
    "j_jolly": {"cn": "开心小丑", "r": 1, "c": 3, "e": "手牌含对子时 +8 倍率"},
    "j_zany": {"cn": "古怪小丑", "r": 1, "c": 4, "e": "手牌含三条时 +12 倍率"},
    "j_mad": {"cn": "疯狂小丑", "r": 1, "c": 4, "e": "手牌含两对时 +10 倍率"},
    "j_crazy": {"cn": "狂野小丑", "r": 1, "c": 4, "e": "手牌含顺子时 +12 倍率"},
    "j_droll": {"cn": "滑稽小丑", "r": 1, "c": 4, "e": "手牌含同花时 +10 倍率"},
    "j_sly": {"cn": "奸诈小丑", "r": 1, "c": 3, "e": "手牌含对子时 +50 筹码"},
    "j_wily": {"cn": "狡猾小丑", "r": 1, "c": 4, "e": "手牌含三条时 +100 筹码"},
    "j_clever": {"cn": "聪敏小丑", "r": 1, "c": 4, "e": "手牌含两对时 +80 筹码"},
    "j_devious": {"cn": "阴险小丑", "r": 1, "c": 4, "e": "手牌含顺子时 +100 筹码"},
    "j_crafty": {"cn": "精明小丑", "r": 1, "c": 4, "e": "手牌含同花时 +80 筹码"},
    "j_half": {"cn": "半张小丑", "r": 1, "c": 5, "e": "打出牌 ≤3 张时 +20 倍率"},
    "j_credit_card": {"cn": "信用卡", "r": 1, "c": 1, "e": "允许欠债到 -$20"},
    "j_banner": {"cn": "旗帜", "r": 1, "c": 5, "e": "每剩余 1 次弃牌 +30 筹码"},
    "j_mystic_summit": {"cn": "神秘之峰", "r": 1, "c": 5, "e": "弃牌次数为 0 时 +15 倍率"},
    "j_8_ball": {"cn": "八号球", "r": 1, "c": 5, "e": "每个打出的 8 有 1/4 概率生成塔罗牌"},
    "j_misprint": {"cn": "印错小丑", "r": 1, "c": 4, "e": "每手牌随机 +0~+23 倍率"},
    "j_raised_fist": {"cn": "致胜之拳", "r": 1, "c": 5, "e": "手持最低点数牌的点数 ×2 加入倍率"},
    "j_chaos": {"cn": "混沌小丑", "r": 1, "c": 4, "e": "每商店 1 次免费重掷"},
    "j_scary_face": {"cn": "恐怖面孔", "r": 1, "c": 4, "e": "打出的人头牌计分时 +30 筹码"},
    "j_abstract": {"cn": "抽象小丑", "r": 1, "c": 4, "e": "每张小丑牌 +3 倍率"},
    "j_delayed_grat": {"cn": "延迟满足", "r": 1, "c": 4, "e": "整轮未用弃牌时每剩余弃牌 +$2"},
    "j_gros_michel": {"cn": "大麦克香蕉", "r": 1, "c": 5, "e": "+15 倍率，每轮结束 1/6 概率销毁"},
    "j_even_steven": {"cn": "偶数史蒂文", "r": 1, "c": 4, "e": "打出的偶数点数牌（10/8/6/4/2）计分时 +4 倍率"},
    "j_odd_todd": {"cn": "奇数托德", "r": 1, "c": 4, "e": "打出的奇数点数牌（A/9/7/5/3）计分时 +31 筹码"},
    "j_scholar": {"cn": "学者", "r": 1, "c": 4, "e": "打出的 A 计分时 +20 筹码 +4 倍率"},
    "j_business": {"cn": "名片", "r": 1, "c": 4, "e": "打出的人头牌 1/2 概率计分时给 $2"},
    "j_supernova": {"cn": "超新星", "r": 1, "c": 5, "e": "本局该手牌被打出的次数计入倍率"},
    "j_ride_the_bus": {"cn": "搭乘巴士", "r": 1, "c": 6, "e": "连续不打出计分人头牌每手 +1 倍率（被人头牌打断）"},
    "j_egg": {"cn": "鸡蛋", "r": 1, "c": 4, "e": "每轮结束卖价 +$3"},
    "j_runner": {"cn": "跑步选手", "r": 1, "c": 5, "e": "手牌含顺子时 +15 筹码（永久）"},
    "j_ice_cream": {"cn": "冰淇淋", "r": 1, "c": 5, "e": "+100 筹码，每手 -5 筹码"},
    "j_splash": {"cn": "飞溅", "r": 1, "c": 3, "e": "所有打出的牌都参与计分"},
    "j_blue_joker": {"cn": "蓝色小丑", "r": 1, "c": 5, "e": "牌组每剩 1 张牌 +2 筹码"},
    "j_faceless": {"cn": "无面小丑", "r": 1, "c": 4, "e": "一次性弃掉 ≥3 张人头牌时 +$5"},
    "j_green_joker": {"cn": "绿色小丑", "r": 1, "c": 4, "e": "每打 1 手 +1 倍率，每弃 1 次 -1 倍率"},
    "j_superposition": {"cn": "叠加态", "r": 1, "c": 4, "e": "手牌含 A 和顺子时生成塔罗牌"},
    "j_todo_list": {"cn": "待办清单", "r": 1, "c": 4, "e": "手牌是指定牌型时 +$4，牌型每轮轮换"},
    "j_cavendish": {"cn": "卡文迪什", "r": 1, "c": 4, "e": "×3 倍率，每轮 1/1000 概率销毁"},
    "j_red_card": {"cn": "红牌", "r": 1, "c": 5, "e": "跳过卡包时 +3 倍率（永久）"},
    "j_square": {"cn": "方形小丑", "r": 1, "c": 4, "e": "手牌恰 4 张时 +4 筹码（永久）"},
    "j_riff_raff": {"cn": "乌合之众", "r": 1, "c": 6, "e": "选盲注时生成 2 张普通小丑"},
    "j_hanging_chad": {"cn": "未断选票", "r": 1, "c": 4, "e": "计分第一张牌额外重触发 2 次"},
    "j_golden": {"cn": "黄金小丑", "r": 1, "c": 6, "e": "每轮结束 +$4"},
    "j_swashbuckler": {"cn": "侠盗", "r": 1, "c": 4, "e": "其他所有小丑的卖价之和加入倍率"},
    "j_shoot_the_moon": {"cn": "射月", "r": 1, "c": 5, "e": "手持每张 Q +13 倍率"},
    "j_smiley": {"cn": "微笑表情", "r": 1, "c": 4, "e": "打出的人头牌计分时 +5 倍率"},
    "j_ticket": {"cn": "黄金门票", "r": 1, "c": 5, "e": "打出的黄金牌计分时 +$4"},
    "j_walkie_talkie": {"cn": "对讲机", "r": 1, "c": 4, "e": "每张打出的 10 或 4 计分时 +10 筹码 +4 倍率"},
    "j_hallucination": {"cn": "幻觉", "r": 1, "c": 4, "e": "打开卡包时 1/2 概率生成塔罗牌"},
    "j_fortune_teller": {"cn": "占卜师", "r": 1, "c": 6, "e": "本局每用 1 张塔罗牌 +1 倍率（永久）"},
    "j_juggler": {"cn": "杂耍师", "r": 1, "c": 4, "e": "+1 手牌上限"},
    "j_drunkard": {"cn": "醉汉", "r": 1, "c": 4, "e": "每轮 +1 次弃牌"},
    "j_stone": {"cn": "石头小丑", "r": 2, "c": 6, "e": "全牌组每张石头牌 +25 筹码"},
    "j_lucky_cat": {"cn": "招财猫", "r": 2, "c": 6, "e": "幸运牌成功触发时 +×0.25 倍率（永久）"},
    "j_bull": {"cn": "斗牛", "r": 2, "c": 6, "e": "每持有 $1 +2 筹码"},
    "j_popcorn": {"cn": "爆米花", "r": 1, "c": 5, "e": "+20 倍率，每轮 -4 倍率"},
    "j_ramen": {"cn": "拉面", "r": 2, "c": 6, "e": "×2 倍率，每弃 1 张 -×0.01 倍率"},
    "j_selzer": {"cn": "苏打水", "r": 2, "c": 6, "e": "接下来 10 手牌内所有打出牌重触发一次"},
    "j_trousers": {"cn": "备用裤子", "r": 2, "c": 6, "e": "手牌含两对时 +2 倍率（永久）"},
    "j_mime": {"cn": "哑剧演员", "r": 2, "c": 5, "e": "重触发所有手持牌能力"},
    "j_stencil": {"cn": "模具小丑", "r": 2, "c": 8, "e": "每个空小丑槽 ×1 倍率"},
    "j_dusk": {"cn": "黄昏", "r": 2, "c": 5, "e": "本轮最后一手牌的所有打出牌重触发一次"},
    "j_acrobat": {"cn": "杂技演员", "r": 2, "c": 6, "e": "本轮最后一手牌 ×3 倍率"},
    # ---------- uncommon ----------
    "j_four_fingers": {"cn": "四指", "r": 2, "c": 7, "e": "同花与顺子只需 4 张牌"},
    "j_ceremonial": {"cn": "仪式匕首", "r": 2, "c": 6, "e": "选盲注时摧毁右侧小丑，将其两倍卖价永久加入倍率"},
    "j_marble": {"cn": "大理石小丑", "r": 2, "c": 6, "e": "选盲注时给牌组加 1 张石头牌"},
    "j_loyalty_card": {"cn": "积分卡", "r": 2, "c": 5, "e": "每打出 5 手牌，第 5 手 ×4 倍率"},
    "j_fibonacci": {"cn": "斐波那契", "r": 2, "c": 8, "e": "打出的 A/2/3/5/8 计分时 +8 倍率"},
    "j_steel_joker": {"cn": "钢铁小丑", "r": 2, "c": 7, "e": "全牌组每张钢铁牌 ×0.2 倍率"},
    "j_hack": {"cn": "烂脱口秀演员", "r": 2, "c": 6, "e": "重触发每个打出的 2/3/4/5"},
    "j_pareidolia": {"cn": "幻视", "r": 2, "c": 5, "e": "所有牌视为人头牌"},
    "j_space": {"cn": "太空小丑", "r": 2, "c": 5, "e": "打出后 1/4 概率升级该手牌等级"},
    "j_burglar": {"cn": "窃贼", "r": 2, "c": 6, "e": "选盲注时 +3 手牌，失去全部弃牌"},
    "j_blackboard": {"cn": "黑板", "r": 2, "c": 6, "e": "手持全为黑桃或梅花时 ×3 倍率"},
    "j_dna": {"cn": "DNA", "r": 3, "c": 8, "e": "回合首手牌仅 1 张时复制加入牌组并抓入手"},
    "j_sixth_sense": {"cn": "第六感", "r": 2, "c": 6, "e": "回合首手是单张 6 时销毁它并生成幻灵牌"},
    "j_constellation": {"cn": "星座", "r": 2, "c": 6, "e": "每使用 1 张星球牌 +×0.1 倍率（永久）"},
    "j_hiker": {"cn": "徒步者", "r": 2, "c": 5, "e": "每张打出的牌计分后永久 +5 筹码"},
    "j_card_sharp": {"cn": "老千小丑", "r": 2, "c": 6, "e": "打出本回合已打过的牌型时 ×3 倍率"},
    "j_madness": {"cn": "疯狂", "r": 2, "c": 7, "e": "选小/大盲注时 +×0.5 倍率并摧毁随机小丑"},
    "j_seance": {"cn": "通灵", "r": 2, "c": 6, "e": "手牌是同花顺时生成幻灵牌"},
    "j_vampire": {"cn": "吸血鬼", "r": 2, "c": 7, "e": "每打出 1 张计分增强牌 +×0.1 倍率并移除其增强"},
    "j_shortcut": {"cn": "捷径", "r": 2, "c": 7, "e": "顺子允许跨越 1 个点数的空档"},
    "j_hologram": {"cn": "全息影像", "r": 2, "c": 7, "e": "每张牌加入牌组 +×0.25 倍率（永久）"},
    "j_cloud_9": {"cn": "9霄云外", "r": 2, "c": 7, "e": "每轮结束按全牌组 9 的数量每张 $1"},
    "j_rocket": {"cn": "火箭", "r": 2, "c": 6, "e": "每轮 +$1，击败头目盲注后 +$2（永久）"},
    "j_midas_mask": {"cn": "迈达斯面具", "r": 2, "c": 7, "e": "打出的人头牌计分时变成黄金牌"},
    "j_luchador": {"cn": "摔跤手", "r": 2, "c": 5, "e": "出售以禁用当前头目盲注效果"},
    "j_photograph": {"cn": "照片", "r": 1, "c": 5, "e": "第一张打出的人头牌计分时 ×2 倍率"},
    "j_gift": {"cn": "礼品卡", "r": 2, "c": 6, "e": "每轮结束给所有小丑和消耗牌 +$1 卖价"},
    "j_turtle_bean": {"cn": "黑龟豆", "r": 2, "c": 6, "e": "+5 手牌，每轮 -1"},
    "j_erosion": {"cn": "侵蚀", "r": 2, "c": 6, "e": "全牌组每低于 52 张 1 张 +4 倍率"},
    "j_reserved_parking": {"cn": "私人车位", "r": 1, "c": 6, "e": "手持每张人头牌 1/2 概率 +$1"},
    "j_mail": {"cn": "邮件回扣", "r": 1, "c": 4, "e": "每弃掉指定点数的牌 +$5，点数每轮轮换"},
    "j_to_the_moon": {"cn": "冲向月球", "r": 2, "c": 5, "e": "每轮结束每持有 $5 额外 +$1 利息"},
    "j_lucky_cat2": {"cn": "招财猫", "r": 2, "c": 6, "e": "幸运牌成功触发时 +×0.25 倍率"},
    "j_baseball": {"cn": "棒球卡", "r": 3, "c": 8, "e": "每个罕见小丑 +×1.5 倍率"},
    "j_diet_cola": {"cn": "零糖可乐", "r": 2, "c": 6, "e": "出售生成一个免费双重标签"},
    "j_trading": {"cn": "交易卡", "r": 2, "c": 6, "e": "回合首次弃牌若只有 1 张，销毁并 +$3"},
    "j_flash": {"cn": "闪示卡", "r": 2, "c": 5, "e": "每次商店重掷 +2 倍率（永久）"},
    "j_ancient": {"cn": "古老小丑", "r": 3, "c": 8, "e": "每张选定花色牌计分时 ×1.5 倍率，花色每轮轮换"},
    "j_castle": {"cn": "城堡", "r": 2, "c": 6, "e": "每弃一张指定花色的牌 +3 筹码，花色每轮轮换"},
    "j_sock_and_buskin": {"cn": "喜与悲", "r": 2, "c": 6, "e": "重触发所有打出的人头牌"},
    "j_troubadour": {"cn": "游吟诗人", "r": 2, "c": 6, "e": "+2 手牌，每轮 -1 手牌"},
    "j_certificate": {"cn": "证书", "r": 2, "c": 6, "e": "回合开始加 1 张带随机蜡封的随机牌入手"},
    "j_smeared": {"cn": "模糊小丑", "r": 2, "c": 7, "e": "红心=方块、黑桃=梅花"},
    "j_throwback": {"cn": "回溯", "r": 2, "c": 6, "e": "本局每跳过 1 个盲注 +×0.25 倍率"},
    "j_rough_gem": {"cn": "璞玉", "r": 2, "c": 7, "e": "打出的方块牌计分时 +$1"},
    "j_bloodstone": {"cn": "血石", "r": 2, "c": 7, "e": "打出的红心牌 1/2 概率计分时 ×1.5 倍率"},
    "j_arrowhead": {"cn": "箭头", "r": 2, "c": 7, "e": "打出的黑桃牌计分时 +50 筹码"},
    "j_onyx_agate": {"cn": "缟玛瑙", "r": 2, "c": 7, "e": "打出的梅花牌计分时 +7 倍率"},
    "j_glass": {"cn": "玻璃小丑", "r": 2, "c": 6, "e": "每张玻璃牌被摧毁 +×0.75 倍率（永久）"},
    "j_ring_master": {"cn": "马戏团长", "r": 2, "c": 5, "e": "小丑/塔罗/星球/幻灵可在商店重复出现"},
    "j_flower_pot": {"cn": "花盆", "r": 2, "c": 6, "e": "手牌同时含四种花色时 ×3 倍率"},
    "j_wee": {"cn": "小小丑", "r": 3, "c": 8, "e": "每张打出的 2 计分时 +8 筹码（永久）"},
    "j_merry_andy": {"cn": "快乐安迪", "r": 2, "c": 7, "e": "+3 次弃牌，-1 手牌上限"},
    "j_oops": {"cn": "六六大顺", "r": 2, "c": 4, "e": "所有列出的概率翻倍"},
    "j_idol": {"cn": "偶像", "r": 2, "c": 6, "e": "每张选定点数+花色牌计分时 ×2 倍率，每轮轮换"},
    "j_seeing_double": {"cn": "重影", "r": 2, "c": 6, "e": "手牌含计分梅花牌和其他花色牌时 ×2 倍率"},
    "j_matador": {"cn": "斗牛士", "r": 2, "c": 7, "e": "打出触发头目盲注能力的手牌时 +$8"},
    "j_obelisk": {"cn": "方尖石塔", "r": 3, "c": 8, "e": "每连续打出非最常打牌型的手牌 +×0.2 倍率（打断重置）"},
    "j_stuntman": {"cn": "特技演员", "r": 3, "c": 7, "e": "+250 筹码，-2 手牌上限"},
    "j_satellite": {"cn": "卫星", "r": 2, "c": 6, "e": "每轮结束按本局用过的不同星球牌数每张 $1"},
    "j_cartomancer": {"cn": "卡牌术士", "r": 2, "c": 6, "e": "选盲注时生成 1 张塔罗牌"},
    "j_astronomer": {"cn": "天文学家", "r": 2, "c": 8, "e": "商店中的星球牌与星球包免费"},
    "j_bootstraps": {"cn": "提靴带", "r": 2, "c": 7, "e": "每持有 $5 +2 倍率"},
    "j_cloud_9_dup": {"cn": "", "r": 2, "c": 0, "e": ""},
    # ---------- rare ----------
    "j_dna_dup": {"cn": "", "r": 3, "c": 0, "e": ""},
    "j_vagabond": {"cn": "流浪者", "r": 3, "c": 8, "e": "手里 ≤$4 时打牌生成塔罗牌"},
    "j_baron": {"cn": "男爵", "r": 3, "c": 8, "e": "手持每张 K ×1.5 倍率"},
    "j_blueprint": {"cn": "蓝图", "r": 3, "c": 10, "e": "复制其右侧小丑的能力"},
    "j_brainstorm": {"cn": "头脑风暴", "r": 3, "c": 10, "e": "复制最左侧小丑的能力"},
    "j_drivers_license": {"cn": "驾驶执照", "r": 3, "c": 7, "e": "全牌组 ≥16 张增强牌时 ×3 倍率"},
    "j_burnt": {"cn": "烧焦小丑", "r": 3, "c": 8, "e": "每轮升级首次弃掉的牌型等级"},
    "j_hit_the_road": {"cn": "上路吧杰克", "r": 3, "c": 8, "e": "本局每弃 1 张 J +×0.5 倍率"},
    "j_duo": {"cn": "二重奏", "r": 3, "c": 8, "e": "手牌含对子时 ×2 倍率"},
    "j_trio": {"cn": "三重奏", "r": 3, "c": 8, "e": "手牌含三条时 ×3 倍率"},
    "j_family": {"cn": "一家人", "r": 3, "c": 8, "e": "手牌含四条时 ×4 倍率"},
    "j_order": {"cn": "秩序", "r": 3, "c": 8, "e": "手牌含顺子时 ×3 倍率"},
    "j_tribe": {"cn": "部落", "r": 3, "c": 8, "e": "手牌含同花时 ×2 倍率"},
    "j_invisible": {"cn": "隐形小丑", "r": 3, "c": 8, "e": "2 轮后出售可复制一个随机小丑"},
    # ---------- legendary ----------
    "j_caino": {"cn": "卡尼奥", "r": 4, "c": 20, "e": "每被摧毁 1 张人头牌 +×1 倍率（永久）"},
    "j_triboulet": {"cn": "特里布莱", "r": 4, "c": 20, "e": "打出的 K 与 Q 每张计分时 ×2 倍率"},
    "j_yorick": {"cn": "约里克", "r": 4, "c": 20, "e": "每弃 23 张牌 +×1 倍率（永久）"},
    "j_chicot": {"cn": "希科", "r": 4, "c": 20, "e": "禁用所有头目盲注效果"},
    "j_perkeo": {"cn": "帕奇欧", "r": 4, "c": 20, "e": "商店结束时复制 1 张随机消耗牌（负片）"},
    # ---------- 审计补录：原版存在但 CLI 原先缺失的 2 张 ----------
    "j_campfire": {"cn": "篝火", "r": 3, "c": 9,
                   "e": "每卖出一张牌 +×0.25 倍率，击败头目后重置为 ×1"},
    "j_mr_bones": {"cn": "骨头先生", "r": 2, "c": 5,
                   "e": "失败时若已达目标 25% 则免除失败，并销毁自身"},
}

# 去掉占位重复键
JOKERS.pop("j_lucky_cat2", None)
JOKERS.pop("j_cloud_9_dup", None)
JOKERS.pop("j_dna_dup", None)

# 稀有度名称
RARITY_CN = {1: "普通", 2: "罕见", 3: "稀有", 4: "传说"}

# 打折字段（在商店打折的券）
DISCOUNT_VOUCHERS = {}


def joker_cfg(key: str) -> dict:
    d = JOKERS.get(key, {})
    return {"cn": d.get("cn", key), "rarity": d.get("r", 1), "cost": d.get("c", 1),
            "e": d.get("e", "")}


def joker_price(key: str) -> int:
    return JOKERS.get(key, {}).get("c", 1)


# ----------------------------------------------------------------------
# 卡池门控（对应 common_events.lua get_current_pool 的筛选条件）
# ----------------------------------------------------------------------
#: 需要牌组里已有该增强牌才会出现的小丑（``enhancement_gate``）
ENHANCEMENT_GATE = {
    "j_steel_joker": "steel",
    "j_stone": "stone",
    "j_lucky_cat": "lucky",
    "j_ticket": "gold",
    "j_glass": "glass",
}

#: 池标记：大麦克香蕉灭绝后不再出现；卡文迪什只在灭绝后才出现
#: （``no_pool_flag`` / ``yes_pool_flag``，pool_flags 由 j_gros_michel 销毁时置位）
NO_POOL_FLAG = {"j_gros_michel": "gros_michel_extinct"}
YES_POOL_FLAG = {"j_cavendish": "gros_michel_extinct"}


def pool_allowed(game, key: str) -> bool:
    """这张小丑此刻是否允许出现在卡池里。"""
    gate = ENHANCEMENT_GATE.get(key)
    if gate and not any(c.enhanced == gate for c in game.all_playing_cards()):
        return False
    flag = NO_POOL_FLAG.get(key)
    if flag and game.pool_flags.get(flag):
        return False
    flag = YES_POOL_FLAG.get(key)
    if flag and not game.pool_flags.get(flag):
        return False
    return True


def roll_joker_rarity(game) -> int:
    """抽取小丑稀有度：普通 70% / 罕见 25% / 稀有 5%（传说不在随机池里）。

    对应 common_events.lua 1969-1971：``> 0.95 → 3``、``> 0.7 → 2``，其余 1。
    """
    x = game.rng.roll("rarity")
    if x > 0.95:
        return 3
    if x > 0.7:
        return 2
    return 1


def _rarity_pool(game, rarity: int, exclude: set) -> list:
    return [k for k, d in JOKERS.items()
            if d["r"] == rarity and k not in exclude and pool_allowed(game, k)]


def random_joker_key(game, rarity=None, exclude=None, legendary=False) -> str:
    """按稀有度加权抽取一张小丑（对应 create_card('Joker') + get_current_pool）。

    - ``rarity=None`` 时按 70/25/5 抽稀有度；传说（4）只能通过 ``legendary=True``
      或显式 ``rarity=4`` 得到——普通商店 / 卡包 / 审判都不会出传说；
    - 排除已拥有以及本批已生成过的小丑（原版 ``G.GAME.used_jokers``），
      持有「马戏团长」时不排除，允许重复出现；
    - 卡池门控：增强牌门控与池标记。
    """
    exclude = set(exclude or [])
    if not game.any_joker("j_ring_master"):
        exclude |= {j.key for j in game.jokers}
    if rarity is None:
        rarity = 4 if legendary else roll_joker_rarity(game)
    pool = _rarity_pool(game, rarity, exclude)
    if not pool:
        # 该稀有度的可选项都被排除时放宽「已拥有」限制（原版会重抽 UNAVAILABLE，
        # 卡池抽空则回退 j_joker）
        pool = _rarity_pool(game, rarity, set())
    if not pool:
        return "j_joker"
    return game.rng.choice(pool, "joker")


def poll_edition(game, mod: int = 1, no_neg: bool = False) -> str | None:
    """随机给一张牌附加版本（对应 common_events.lua 的 poll_edition）。

    默认（``mod=1``、``G.GAME.edition_rate=1``）：
    负片 0.3%、彩绘 0.6%、全息 2%、箔片 4%；磨砺 / 发光升级把
    ``edition_rate`` 提到 2 / 4，彩绘以下三档概率随之放大。
    """
    x = game.rng.roll("edition")
    rate = getattr(game, "edition_rate", 1)
    if x > 1 - 0.003 * mod and not no_neg:
        return "negative"
    if x > 1 - 0.006 * rate * mod:
        return "polychrome"
    if x > 1 - 0.02 * rate * mod:
        return "holo"
    if x > 1 - 0.04 * rate * mod:
        return "foil"
    return None


def apply_voucher(game, vk: str):
    """优惠券立即生效（对应 card.lua 的 ``Card:apply_to_run``，1880-1971）。

    商店概率类（塔罗/星球商人、魔术戏法、幻象、磨砺、发光升级）改的是
    ``G.GAME.*_rate`` 这类运行期参数，由商店生成时读取。
    """
    from ..data.vouchers import VOUCHERS
    d = VOUCHERS.get(vk, {})
    if "discount" in d:
        game.discount_percent = d["discount"]
    if vk in ("v_overstock_norm", "v_overstock_plus"):
        game.shop_joker_max += 1
    if vk in ("v_reroll_surplus", "v_reroll_glut"):
        game.reroll_cost_base = max(1, game.reroll_cost_base - 2)
    if vk in ("v_seed_money", "v_money_tree"):
        game.interest_cap = 50 if vk == "v_seed_money" else 100
    if vk == "v_crystal_ball":
        # 只有水晶球加消耗品格；预兆之球（v_omen_globe）不加（原版 apply_to_run 无此分支）
        game.add_consumable_slot()
    if vk == "v_tarot_merchant":
        game.tarot_rate = 4 * (9.6 / 4)          # 9.6
    if vk == "v_tarot_tycoon":
        game.tarot_rate = 4 * (32 / 4)           # 32
    if vk == "v_planet_merchant":
        game.planet_rate = 4 * (9.6 / 4)         # 9.6
    if vk == "v_planet_tycoon":
        game.planet_rate = 4 * (32 / 4)          # 32
    if vk == "v_hone":
        game.edition_rate = 2
    if vk == "v_glow_up":
        game.edition_rate = 4
    if vk in ("v_magic_trick", "v_illusion"):
        game.playing_card_rate = 4
    if vk in ("v_paint_brush", "v_palette"):
        pass  # 手牌上限每回合由 Game.round_hand_size 的 _voucher_bonus 汇总
    if vk in ("v_grabber", "v_nacho_tong", "v_wasteful", "v_recyclomancy"):
        pass  # 每回合生效，见 Game._voucher_bonus
    if vk == "v_antimatter":
        game.add_joker_slot()
    if vk in ("v_hieroglyph", "v_petroglyph"):
        # 底注 -1；象形文字另扣出牌次数、岩画另扣弃牌次数（见 _voucher_bonus）
        game.ante = max(1, game.ante - 1)
    if vk in ("v_telescope", "v_observatory"):
        pass  # 星球包首张 / 手中星球牌 ×1.5，分别在开包与记分时读取
    if vk in ("v_omen_globe", "v_directors_cut", "v_retcon", "v_blank"):
        pass  # 开包 / 头目重掷时读取
