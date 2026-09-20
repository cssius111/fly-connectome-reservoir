"""Execution modes are distinct from physical arena presets. No mode learns yet."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Mode:
    name: str
    deterministic_default_seed: bool
    record_by_default: bool
    future_updates_allowed: bool
    updates_enabled: bool = False


MODES = {
    'lab': Mode('lab', True, False, False),
    'evaluation': Mode('evaluation', True, True, False),
    'play': Mode('play', False, True, False),
    'training': Mode('training', False, True, True),
}


def resolve_mode(name):
    if name not in MODES:
        raise ValueError('mode must be lab, evaluation, play or training')
    return MODES[name]
