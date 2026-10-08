"""确定性随机数（对应 Lua 的 pseudorandom / random）。

保证同一种子下整局可复现。
"""
from __future__ import annotations
import random


class RNG:
    def __init__(self, seed: int = 0):
        self.seed = seed
        self._rng = random.Random(seed)
        self.calls = 0

    def roll(self, label: str = "") -> float:
        """返回 [0,1) 均匀随机数（对应 pseudorandom）。"""
        self.calls += 1
        return self._rng.random()

    def chance(self, denominator: float, label: str = "") -> bool:
        """1/denominator 概率为真。probabilities.normal=1 的默认因子。"""
        return self.roll(label) < 1.0 / denominator

    def int(self, a: int, b: int, label: str = "") -> int:
        return self._rng.randint(a, b)

    def choice(self, seq, label: str = ""):
        return self._rng.choice(list(seq))

    def choices(self, seq, k: int = 1):
        return self._rng.choices(list(seq), k=k)

    def sample(self, seq, k: int):
        return self._rng.sample(list(seq), k)

    def shuffle(self, seq):
        self._rng.shuffle(seq)
        return seq

    def weighted_choice(self, items, weights, label: str = ""):
        """items/weights 并行列表，返回一个 item。"""
        total = sum(weights)
        r = self.roll(label) * total
        acc = 0.0
        for item, w in zip(items, weights):
            acc += w
            if r < acc:
                return item
        return items[-1]
