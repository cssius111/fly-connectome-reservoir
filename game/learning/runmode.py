"""TRAIN / EVAL separation and the explicit seed registry.

TRAIN: may collect trajectories, may update learned parameters, may explore, and draws
randomized encounter seeds from the TRAIN range only.

EVAL: deterministic from seed, no parameter updates (the model is frozen and its parameter
hash is checked before and after), no exploration unless it is part of a frozen policy, and
EVAL seeds only. EVAL runs produce reproducible benchmark reports.

Never evaluate on training seeds: the ranges below are disjoint from each other and from
every seed used in M1 (N0 up to 440149 plus 4000-4149, N1 6000-10059, ROOM 7101-7680 and
101 / 255 / 4242, N4B6 500001-500048, N4B7 700001-700096 / 800001-800720 / 900001-900120).
The brain-noise seed is seed + 977; the ranges are wide enough apart that no world seed of
one set equals a brain seed of the other.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRAIN_SEED_RANGE = (20_000_000, 29_999_999)
EVAL_SEED_BASE = 3_000_000           # EVAL seeds: 3_000_000 + 100_000 * scenario_index + k, k = 1..999


@dataclass(frozen=True)
class RunMode:
    name: str
    updates_allowed: bool
    explore: bool

    def check_seed(self, seed: int):
        in_train = TRAIN_SEED_RANGE[0] <= seed <= TRAIN_SEED_RANGE[1]
        in_eval = EVAL_SEED_BASE < seed < EVAL_SEED_BASE + 1_000_000
        if self.name == 'EVAL' and not in_eval:
            raise ValueError('EVAL runs must use EVAL seeds (got %d)' % seed)
        if self.name == 'TRAIN' and not in_train:
            raise ValueError('TRAIN runs must use TRAIN seeds (got %d)' % seed)


TRAIN = RunMode('TRAIN', updates_allowed=True, explore=True)
EVAL = RunMode('EVAL', updates_allowed=False, explore=False)


def eval_seeds(scenario_index: int, n: int):
    if not 1 <= n <= 999:
        raise ValueError('at most 999 EVAL seeds per scenario')
    base = EVAL_SEED_BASE + 100_000 * (scenario_index + 1)
    return [base + k for k in range(1, n + 1)]


def train_seeds(master_seed: int, n: int):
    rng = np.random.default_rng(master_seed)
    return [int(s) for s in rng.integers(TRAIN_SEED_RANGE[0], TRAIN_SEED_RANGE[1] + 1, n)]


class EvalGuard:
    """Context manager: freezes a model for EVAL and verifies its parameters did not change."""

    def __init__(self, model):
        self.model = model

    def __enter__(self):
        self.before = self.model.param_hash() if self.model is not None else None
        if self.model is not None:
            self.model.frozen = True
        return self

    def __exit__(self, *exc):
        if self.model is not None:
            after = self.model.param_hash()
            self.model.frozen = False
            if after != self.before:
                raise RuntimeError('model parameters changed during EVAL')
        return False
