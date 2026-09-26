"""M1.8-N4B3 research: preregistered selective DNp04 candidate family and frozen criteria.

Research only. Nothing here is imported by the runtime and nothing is a policy input.
`tools/n4b3_analysis.py freeze` records this module's sha256 before the new holdout is
generated; the holdout tools refuse to run if the module changed afterwards.

Every candidate starts from the N4B2 DNp04 readout: two DNp04 spikes on the SAME side,
the second at most 3 samples (60 ms) after the first. A candidate adds one gate evaluated
on the sample of the second spike. Gates may read only what a policy could legally
observe:

* DNp01 spikes (already in the policy observation; inferred per side from the trace);
* the whitelisted MotionState: forward_speed, lateral_speed, yaw_rate,
  saccade_remaining, and the policy's own history of them.

No gate reads mouse or paddle coordinates, world distance, contact, raw Retina values or
LC4/LPLC2 activity. Those are used offline only, to label events.

Families (preregistered before the N4B3 development evaluation):

* A. DNp04 + DNp01 coincidence: an ipsilateral DNp01 spike within the pair window.
* B. DNp04 + existing DNp01 evidence: DNp01 evidence in the preceding 0.5 s, so DNp04 can
  only accelerate an already-supported threat state.
* C. DNp04 + internal-motion discount: the pair counts only when the fly's own motion is
  small (slow forward flight, low yaw, no saccade), where self-generated expansion should
  be weak.

Each candidate is also evaluated as "N4B1C OR candidate" (one shared 0.4 s refractory).
Event semantics follow the runtime: 20-sample refractory; evidence memory, gating spikes
included, is cleared on an event; the qualifying DNp04 spike is on the current sample.

All thresholds are Class C engineering values, not biological constants.
"""
from __future__ import annotations

import numpy as np

REFRACTORY_SAMPLES = 20
PAIR_WINDOW = 3


def _scan(cands):
    events, last = [], -10 ** 9
    for t, partner, label in cands:
        if t - last <= REFRACTORY_SAMPLES or partner <= last:
            continue
        events.append((int(t), label))
        last = t
    return events


def _kth_recent(times, t, window, k):
    """Time of the k-th most recent spike in [t - window, t], or None."""
    lo = np.searchsorted(times, t - window, side='left')
    hi = np.searchsorted(times, t, side='right')
    if hi - lo < k:
        return None
    return int(times[hi - k])


def _motion_ok(gate, motion, t):
    if motion is None:
        raise ValueError('a motion gate needs MotionState')
    h0 = max(0, t - gate.get('history', 0))
    m = motion[h0:t + 1]
    if 'max_forward_speed' in gate and motion[t, 0] > gate['max_forward_speed']:
        return False
    if 'max_speed' in gate and np.hypot(motion[t, 0], motion[t, 1]) > gate['max_speed']:
        return False
    if 'max_abs_yaw' in gate and np.max(np.abs(m[:, 2])) > gate['max_abs_yaw']:
        return False
    if gate.get('no_saccade') and np.any(m[:, 3] > 0):
        return False
    return True


def dnp04_candidates(crit, spikes, motion, idx):
    """Qualifying samples (t, earliest relied-on spike, label) of a gated DNp04 pair."""
    gate = crit.get('gate', {})
    t01 = {s: np.flatnonzero(spikes[:, idx['DNp01'][s]]) for s in 'LR'}
    t01_any = np.sort(np.concatenate([t01['L'], t01['R']]))
    cands = []
    for side in 'LR':
        t = np.flatnonzero(spikes[:, idx['DNp04'][side]])
        for a, b in zip(t[:-1], t[1:]):
            if b - a > PAIR_WINDOW:
                continue
            partner = int(a)
            if 'dnp01_ipsi' in gate:
                g = gate['dnp01_ipsi']
                k = _kth_recent(t01[side], int(b), g['window'], g['min'])
                if k is None:
                    continue
                partner = min(partner, k)
            if 'dnp01_any' in gate:
                g = gate['dnp01_any']
                k = _kth_recent(t01_any, int(b), g['window'], g['min'])
                if k is None:
                    continue
                partner = min(partner, k)
            if 'motion' in gate and not _motion_ok(gate['motion'], motion, int(b)):
                continue
            cands.append((int(b), partner, side))
    cands.sort()
    return cands


def evaluate(crit, spikes, trace_l, trace_r, motion, idx, n4b1c):
    """Events [(sample, label)] of one criterion on one segment."""
    if crit['kind'] == 'reference':
        return n4b1c(trace_l, trace_r)
    cands = dnp04_candidates(crit, spikes, motion, idx)
    if not crit.get('combine_with_n4b1c'):
        return _scan(cands)
    ref = [(t, t, 'N4B1C:' + lab) for t, lab in n4b1c(trace_l, trace_r)]
    ours = [(t, p, 'DNp04:' + lab) for t, p, lab in cands]
    # Reference events carry their own evidence handling; the union shares one refractory.
    return _scan(sorted(ref + ours, key=lambda c: (c[0], c[2])))


def uses_motion(crit):
    return 'motion' in crit.get('gate', {})


def _pair(gate=None, combine=False):
    return {'kind': 'dnp04_pair', 'gate': gate or {}, 'combine_with_n4b1c': combine}


# ----------------------------------------------------------------- family ---
_BASE = {
    'DNp04 pair (N4B2, ungated)': {},
    # A: coincidence
    'A1 pair + ipsi DNp01 within 60 ms': {'dnp01_ipsi': {'window': 3, 'min': 1}},
    # B: existing DNp01 evidence
    'B1 pair + ipsi DNp01 within 0.5 s': {'dnp01_ipsi': {'window': 25, 'min': 1}},
    'B2 pair + 2 ipsi DNp01 within 0.5 s': {'dnp01_ipsi': {'window': 25, 'min': 2}},
    'B3 pair + 2 DNp01 (any side) within 0.5 s': {'dnp01_any': {'window': 25, 'min': 2}},
    # C: internal-motion discount
    'C1 pair + forward_speed <= 50': {'motion': {'max_forward_speed': 50.0}},
    'C2 pair + forward_speed <= 100': {'motion': {'max_forward_speed': 100.0}},
    'C3 pair + forward_speed <= 150': {'motion': {'max_forward_speed': 150.0}},
    'C4 pair + |yaw| <= 1 rad/s over 0.5 s': {'motion': {'max_abs_yaw': 1.0, 'history': 25}},
    'C5 pair + no saccade over 0.5 s': {'motion': {'no_saccade': True, 'history': 25}},
    'C6 pair + planar speed <= 100': {'motion': {'max_speed': 100.0}},
    # A + C
    'A1+C2 pair + ipsi DNp01 60 ms + forward_speed <= 100': {'dnp01_ipsi': {'window': 3, 'min': 1},
                                                             'motion': {'max_forward_speed': 100.0}},
    # Added during development (before the freeze), after A1 and C4 each kept the slow-close
    # detection: their conjunction.
    'A1+C4 pair + ipsi DNp01 60 ms + |yaw| <= 1 over 0.5 s': {'dnp01_ipsi': {'window': 3, 'min': 1},
                                                              'motion': {'max_abs_yaw': 1.0, 'history': 25}},
}
FAMILY = {'N4B1C (frozen runtime)': {'kind': 'reference'}}
for _name, _gate in _BASE.items():
    FAMILY[_name] = _pair(_gate)
for _name, _gate in _BASE.items():
    FAMILY['N4B1C OR ' + _name] = _pair(_gate, combine=True)

# ----------------------------------------------------------------- frozen ---
# Filled in from development data only, before the new holdout exists.
FROZEN: list = [
    'N4B1C (frozen runtime)',
    'DNp04 pair (N4B2, ungated)',
    'A1 pair + ipsi DNp01 within 60 ms',
    'A1+C4 pair + ipsi DNp01 60 ms + |yaw| <= 1 over 0.5 s',
    'C2 pair + forward_speed <= 100',
    'N4B1C OR A1 pair + ipsi DNp01 within 60 ms',
    'N4B1C OR A1+C4 pair + ipsi DNp01 60 ms + |yaw| <= 1 over 0.5 s',
    'N4B1C OR C2 pair + forward_speed <= 100',
]
FROZEN_RATIONALE = (
    'Development (N0 630 min, ROOM 72 + 12 min, N1, both human sessions). No family member '
    'both keeps the slow-close detection (tick 613) and brings ROOM free flight below '
    '0.1/min. Frozen for the independent test: (1) the N4B1C reference and the ungated '
    'N4B2 pair, to replicate their rates on new data; (2) A1, the neural gate that keeps '
    'the slow-close detection with the fewest ROOM events (16/72 min); (3) A1+C4, the '
    'least-firing ROOM form that keeps the slow-close detection (11/72 min); (4) C2, the '
    'motion gate with 0/72 ROOM events, which keeps only stationary-fly detections and '
    'loses the airborne slow-close case; (5) each gated form combined with N4B1C. B1 '
    '(same as ungated), B2/B3 (lose slow-close), C1/C3/C6 (equivalent to C2) and C4/C5 '
    'alone (dominated by A1+C4) are not carried forward.')
