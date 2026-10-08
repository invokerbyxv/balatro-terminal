from __future__ import annotations
from typing import List, Optional

from .card import Card, SUITS, RANKS
from .rng import RNG


class Deck:
    def __init__(self, cards: Optional[List[Card]] = None):
        self.cards: List[Card] = cards or []
        self._uid = 0

    def _next_uid(self) -> int:
        self._uid += 1
        return self._uid

    @staticmethod
    def build_standard() -> "Deck":
        d = Deck()
        for rank in RANKS:
            for suit in SUITS:
                d.cards.append(Card(rank=rank, suit=suit, uid=d._next_uid()))
        return d

    @staticmethod
    def build_abandoned() -> "Deck":
        d = Deck()
        for rank in RANKS:
            if rank in ("J", "Q", "K"):
                continue
            for suit in SUITS:
                d.cards.append(Card(rank=rank, suit=suit, uid=d._next_uid()))
        return d

    @staticmethod
    def build_checkered() -> "Deck":
        d = Deck()
        for rank in RANKS:
            for suit in ("S", "H"):
                d.cards.append(Card(rank=rank, suit=suit, uid=d._next_uid()))
        return d

    def shuffle(self, rng: RNG):
        rng.shuffle(self.cards)

    def draw(self, n: int, rng: RNG) -> List[Card]:
        out, self.cards = self.cards[:n], self.cards[n:]
        return out

    def draw_one(self, rng: RNG) -> Optional[Card]:
        return self.cards.pop(0) if self.cards else None

    def count(self) -> int:
        return len(self.cards)

    def add(self, card: Card):
        card.uid = self._next_uid() if not card.uid else card.uid
        self.cards.append(card)


def build_deck(deck_key: str, rng: RNG) -> Deck:
    from ..data.decks import DECKS
    cfg = DECKS[deck_key]["config"]
    if cfg.get("checkered"):
        return Deck.build_checkered()
    if cfg.get("remove_faces"):
        return Deck.build_abandoned()
    return Deck.build_standard()
