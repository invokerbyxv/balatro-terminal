from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

SUITS = ("S", "H", "C", "D")
SUIT_DISPLAY = {"S": "♠", "H": "♥", "C": "♣", "D": "♦"}
SUIT_CN = {"S": "黑桃", "H": "红心", "C": "梅花", "D": "方块"}

RANKS = ("2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A")

ENHANCED = ("bonus", "mult", "wild", "glass", "steel", "stone", "gold", "lucky")

EDITIONS = ("foil", "holo", "poly", "negative")

SEALS = ("gold", "red", "blue", "purple")

ENHANCED_CN = {
    "bonus": "加分牌", "mult": "倍率牌", "wild": "百搭牌", "glass": "玻璃牌",
    "steel": "钢铁牌", "stone": "石头牌", "gold": "黄金牌", "lucky": "幸运牌",
}
EDITION_CN = {
    "foil": "箔", "holo": "全息", "poly": "彩绘", "negative": "负片",
}
SEAL_CN = {"gold": "金", "red": "红", "blue": "蓝", "purple": "紫"}


def rank_id(rank: str) -> int:
    if rank == "A":
        return 14
    if rank == "K":
        return 13
    if rank == "Q":
        return 12
    if rank == "J":
        return 11
    return int(rank)


def rank_value(rank: str) -> int:
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K", "10"):
        return 10
    return int(rank)


SUIT_NOMINAL = {"D": 0.01, "C": 0.02, "H": 0.03, "S": 0.04}
FACE_NOMINAL = {"J": 0.1, "Q": 0.2, "K": 0.3, "A": 0.4}


@dataclass
class Card:
    rank: str
    suit: str
    enhanced: Optional[str] = None
    edition: Optional[str] = None
    seal: Optional[str] = None
    debuffed: bool = False
    uid: int = field(default=0, compare=False)

    seal_purple_used: bool = field(default=False, compare=False)

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return object.__hash__(self)

    # ---------- 基础查询 ----------
    def get_id(self) -> int:
        return rank_id(self.rank)

    def get_nominal(self) -> float:
        if self.enhanced == "stone":
            return -1000
        return (rank_value(self.rank) * 1.0
                + SUIT_NOMINAL.get(self.suit, 0.0)
                + FACE_NOMINAL.get(self.rank, 0.0))

    def is_face(self) -> bool:
        return self.rank in ("J", "Q", "K")

    def is_suit(self, suit: str, flush_calc: bool = False, smeared: bool = False) -> bool:
        if self.enhanced == "stone":
            return False
        if self.enhanced == "wild":
            return True
        if smeared:
            reds = ("H", "D")
            blacks = ("S", "C")
            if suit in reds and self.suit in reds:
                return True
            if suit in blacks and self.suit in blacks:
                return True
            return False
        return self.suit == suit

    # ---------- 显示 ----------
    def display(self) -> str:
        s = f"{SUIT_DISPLAY[self.suit]}{self.rank}"
        tags = []
        if self.enhanced:
            tags.append(ENHANCED_CN[self.enhanced])
        if self.edition:
            tags.append(EDITION_CN[self.edition])
        if self.seal:
            tags.append(SEAL_CN[self.seal])
        if tags:
            s += "·" + ",".join(tags)
        return s

    def short(self) -> str:
        s = f"{SUIT_DISPLAY[self.suit]}{self.rank}"
        if self.enhanced == "steel":
            s += "钢"
        elif self.enhanced == "glass":
            s += "玻"
        elif self.enhanced == "stone":
            s = "石"
        return s

    def copy(self) -> "Card":
        c = Card(
            rank=self.rank, suit=self.suit, enhanced=self.enhanced,
            edition=self.edition, seal=self.seal, debuffed=self.debuffed, uid=self.uid,
        )
        c.seal_purple_used = self.seal_purple_used
        return c

    def __repr__(self):
        return f"<Card {self.display()}>"
