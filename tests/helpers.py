"""测试辅助：固定种子建局、可复现的自动对局、状态快照。"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List

from balatro_cli.core.card import Card
from balatro_cli.core.game import Game


def new_game(seed: int = 1234, deck: str = "b_red", blind: bool = True) -> Game:
    """建一局并（默认）迎来第一个盲注，手牌已补齐。"""
    g = Game(seed=seed)
    g.start_run(deck)
    if blind:
        g.select_blind()
    return g


def cards(*specs: str) -> List[Card]:
    """按 "rank-suit" 或 "rank-suit-enhanced" 生成牌，如 cards("A-S", "10-H-glass")。"""
    out = []
    for spec in specs:
        parts = spec.split("-")
        rank, suit = parts[0], parts[1]
        enhanced = parts[2] if len(parts) > 2 else None
        out.append(Card(rank=rank, suit=suit, enhanced=enhanced))
    return out


def set_hand(g: Game, specs: List[str]) -> None:
    """把手牌替换成指定牌（其余牌放回牌堆，保证总数不变）。"""
    cards_in_hand = cards(*specs)
    ids = {id(c) for c in cards_in_hand}
    g.deck.cards.extend(c for c in g.hand if id(c) not in ids)
    g.hand = cards_in_hand


def select_rank(g: Game, rank: str, limit: int = 5) -> None:
    """选中手牌里某个点数的牌，最多 limit 张。"""
    for c in g.hand:
        c.selected = False
    picked = [c for c in g.hand if c.rank == rank][:limit]
    for c in picked:
        c.selected = True


def select_cards(g: Game, count: int) -> None:
    """选中手牌前 count 张（测试用的固定策略）。"""
    for c in g.hand:
        c.selected = False
    for c in g.hand[:count]:
        c.selected = True


def greedy_play(g: Game) -> str:
    """打出手牌里数量最多的同点数牌（测试用的固定策略）。"""
    counts = Counter(c.rank for c in g.hand)
    rank = counts.most_common(1)[0][0]
    select_rank(g, rank)
    msgs = g.play_selected()
    return msgs[0] if msgs else ""


def play_rounds(g: Game, rounds: int) -> None:
    """以固定策略推进若干回合，含商店与卡包；遇到终局即停。"""
    played = 0
    while played < rounds and not (g.run_lost or g.run_won):
        if g.blind_key is None:
            g.select_blind()
        for _ in range(g.hands_left + 1):
            if g.round_over():
                break
            greedy_play(g)
            for c in g.hand:
                c.selected = False
            played += 1
        if not g.round_over():
            break
        g.end_round()
        if g.run_lost or g.run_won:
            break
        g.enter_shop()
        if g.pending_pack:
            if g.pending_pack["choose"] == 1:
                g.pack_choose([0])
            g.skip_pack()          # 取满会自行关闭；没取满的（如 4 选 2）在这里结束
        g.shop_closed()


def snapshot(g: Game) -> Dict:
    """回合状态快照：用于断言确定性，不包含对象身份。"""
    return {
        "ante": g.ante,
        "round": g.round,
        "chips": g.chips,
        "dollars": g.dollars,
        "hands_left": g.hands_left,
        "discards_left": g.discards_left,
        "hand_size": g.hand_size,
        "deck": g.deck.count(),
        "hand": [(c.rank, c.suit, c.enhanced, c.seal, c.edition) for c in g.hand],
        "jokers": [j.key for j in g.jokers],
        "consumeables": [c.key for c in g.consumeables],
        "hand_levels": dict(g.hand_levels),
        "blind": g.blind_key,
        "on_deck": g.blind_on_deck,
        "run_won": g.run_won,
        "run_lost": g.run_lost,
    }
