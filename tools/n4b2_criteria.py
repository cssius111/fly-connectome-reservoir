"""M1.8-N4B2 research: candidate rule, readout family and frozen criteria.

Research only. Nothing here is imported by the runtime, and no readout defined here is a
policy input. `tools/n4b2_analysis.py freeze` records this module's sha256 before the new
independent N0 holdout is generated, and the holdout tools refuse to run if the module
changed afterwards.

Structure:

* CANDIDATE_RULE: which descending-neuron (DN) types are studied. The rule is mechanistic
  (direct wiring from the encoder's chosen LC4/LPLC2 cells against the rest-to-threshold
  margin), not chosen from activity.
* Readout family: event rules on per-side spike trains. Every rule shares the runtime
  escape semantics: an event fires on a sample outside a 20-sample (0.4 s) refractory
  period; spike memory from before an event is cleared when it fires, so evidence never
  pairs across an event; the qualifying spike must be on the current sample.
* FROZEN: the specific criteria selected on development data (see SELECTION_PROTOCOL).
  Filled in once, before the holdout exists; never tuned on the holdout.

All parameters are Class C simulator-derived engineering values, not biological constants.
"""
from __future__ import annotations

import numpy as np

REFRACTORY_SAMPLES = 20                     # 0.4 s at 20 ms, as in the accepted runtime
TRACE_DECAY = float(np.exp(-0.02 / 0.1))    # flybrain.Trace, tau 0.1 s, 20 ms samples
THRESHOLD_MARGIN = 0.228                    # threshold 1.0 minus rest 0.14 / (1 - 0.8187)

CANDIDATE_RULE = (
    'A DN type is a candidate when it has one cell per side and, on BOTH sides, a full '
    'ipsilateral volley of the encoder\'s chosen LC4 + LPLC2 cells alone delivers at least '
    'the rest-to-threshold margin: gain (3.0) * direct weight >= 0.228 V. DNp01 is the '
    'frozen N4B1C reference; DNp04 is the pre-specified primary hypothesis; the other '
    'qualifying types are the comparison set. Two-hop drive is reported but no DN without '
    'qualifying direct input reaches the margin through intermediates (connectome.json).')
REFERENCE_TYPE = 'DNp01'
PRIMARY_TYPE = 'DNp04'

SELECTION_PROTOCOL = (
    '1. Development data only: original N0 (70 min), N4B1 fresh N0 (280 min), N4B1C '
    'holdout (280 min) = 630 min, plus N1 and both human sessions. '
    '2. For each candidate type and readout form, the development-N0 envelope is measured. '
    '3. Criteria are frozen in FROZEN below, with their rationale, before any new holdout '
    'seed is simulated. '
    '4. The new holdout (280 min, seeds 310000-340149) and the post-freeze ROOM no-player '
    'arm are evaluated once, for every frozen criterion, and all results are reported.')


# ----------------------------------------------------------------- event rules ---
def _scan(candidates, n_prev_needed):
    """Apply refractory and memory clearing to time-sorted qualifying samples.

    candidates: iterable of (t, earliest_partner_sample, label). A candidate fires when
    it is outside refractory and every spike it relies on is later than the last event.
    """
    events, last = [], -10 ** 9
    for t, partner, label in candidates:
        if t - last <= REFRACTORY_SAMPLES:
            continue
        if partner is not None and partner <= last:
            continue
        events.append((int(t), label))
        last = t
    return events


def same_side_k(spk_l, spk_r, k, window):
    """k spikes on ONE side, the first at most `window` samples before the current one."""
    cands = []
    for label, spk in (('L', spk_l), ('R', spk_r)):
        times = np.flatnonzero(spk)
        if times.size < k:
            continue
        first = times[:-(k - 1)] if k > 1 else times
        cur = times[k - 1:]
        ok = cur - first <= window
        cands.extend(zip(cur[ok].tolist(), first[ok].tolist(), [label] * int(ok.sum())))
    cands.sort()
    return _scan(cands, k - 1)


def any_spike(spk_l, spk_r):
    """A single spike on either side."""
    t = np.flatnonzero(spk_l | spk_r)
    lab = np.where(spk_l[t], 'L', 'R')
    return _scan(zip(t.tolist(), [None] * t.size, lab.tolist()), 0)


def bilateral_pair(spk_l, spk_r, window):
    """A spike on one side and a spike on the OTHER side at most `window` samples apart."""
    cands = []
    tl, tr = np.flatnonzero(spk_l), np.flatnonzero(spk_r)
    for cur_times, other, label in ((tl, tr, 'L'), (tr, tl, 'R')):
        if other.size == 0:
            continue
        j = np.searchsorted(other, cur_times, side='right') - 1     # latest other spike <= t
        ok = j >= 0
        prev = np.where(ok, other[np.clip(j, 0, None)], -10 ** 9)
        good = ok & (cur_times - prev <= window)
        cands.extend(zip(cur_times[good].tolist(), prev[good].tolist(), [label + '+other'] * int(good.sum())))
    cands.sort()
    return _scan(cands, 1)


def trace(spk):
    """flybrain.Trace arithmetic (float32, +1 per spike)."""
    d = np.float32(TRACE_DECAY)
    out = np.empty(spk.size, np.float32)
    t = np.float32(0.0)
    for i in range(spk.size):
        t = np.float32(t * d)
        if spk[i]:
            t = np.float32(t + np.float32(1.0))
        out[i] = t
    return out


def trace_threshold(spk_l, spk_r, theta, mode):
    """Trace readout: 'lateral' (max of the two sides) or 'summed' (L + R) >= theta."""
    tl, tr = trace(spk_l), trace(spk_r)
    x = np.maximum(tl, tr) if mode == 'lateral' else tl + tr
    t = np.flatnonzero(x >= theta)
    lab = np.where(tl[t] >= tr[t], 'L', 'R')
    return _scan(zip(t.tolist(), [None] * t.size, lab.tolist()), 0)


def pooled_k(spk_l, spk_r, k, window):
    """k spikes pooled over BOTH sides, the first at most `window` samples before the
    current one (a same-tick L+R pair counts as two spikes)."""
    times = np.sort(np.concatenate([np.flatnonzero(spk_l), np.flatnonzero(spk_r)]))
    if times.size < k:
        return []
    first = times[:-(k - 1)] if k > 1 else times
    cur = times[k - 1:]
    ok = cur - first <= window
    cands = sorted(set(zip(cur[ok].tolist(), first[ok].tolist())))
    # For a repeated current sample keep the latest (most permissive) partner.
    best = {}
    for t, p in cands:
        best[t] = max(best.get(t, -10 ** 9), p)
    return _scan(((t, best[t], 'pooled') for t in sorted(best)), k - 1)


def evaluate(spec, spk_l, spk_r):
    """Events of one readout spec on one segment; returns [(sample, label)]."""
    kind = spec['kind']
    if kind == 'single':
        return any_spike(spk_l, spk_r)
    if kind == 'same_side':
        return same_side_k(spk_l, spk_r, spec['k'], spec['window'])
    if kind == 'pooled':
        return pooled_k(spk_l, spk_r, spec['k'], spec['window'])
    if kind == 'bilateral':
        return bilateral_pair(spk_l, spk_r, spec['window'])
    if kind == 'trace':
        return trace_threshold(spk_l, spk_r, spec['theta'], spec['mode'])
    raise ValueError(kind)


def family():
    """The descriptive readout family evaluated for every candidate type."""
    out = {'single': {'kind': 'single'}}
    for w in (1, 2, 3, 4, 5, 10):
        out['pair_%d' % w] = {'kind': 'same_side', 'k': 2, 'window': w}
    out['triple_5'] = {'kind': 'same_side', 'k': 3, 'window': 5}
    out['triple_10'] = {'kind': 'same_side', 'k': 3, 'window': 10}
    # Longer integration (0.5 s): sparse repeated spikes of a slow approach.
    out['same_3_in_25'] = {'kind': 'same_side', 'k': 3, 'window': 24}
    out['same_4_in_25'] = {'kind': 'same_side', 'k': 4, 'window': 24}
    out['bilateral_3'] = {'kind': 'bilateral', 'window': 3}
    out['pooled_3_in_5'] = {'kind': 'pooled', 'k': 3, 'window': 4}
    out['pooled_4_in_10'] = {'kind': 'pooled', 'k': 4, 'window': 9}
    out['pooled_5_in_25'] = {'kind': 'pooled', 'k': 5, 'window': 24}
    return out


# ----------------------------------------------------------------- frozen criteria ---
# Filled in from development data only, before the new holdout exists.
#
# Rationale (development data: N0 630 min, N1 300 trials, both human sessions, ROOM
# no-player 12 min):
# * Only DNp04 detects committed strikes earlier than DNp01 and detects the weak / slow N1
#   classes and the slow-close case earlier than N4B1C. The other eight comparison types
#   are equal or slower on committed strikes and less sensitive on weak approaches, so
#   none is carried to the holdout.
# * The two DNp04 forms reuse parameters already fixed by earlier milestones instead of
#   choosing new ones: the 60 ms same-side pair is the N4B1C Rule A form, and the 200 ms
#   same-side triple is the N3 "three spikes in 200 ms" form. Both have 0 development-N0
#   events. Longer integration (3 same-side spikes in 500 ms: 106 N0 events) fails the
#   target and is rejected.
# * DNp04 pair <= 100 ms (5 development-N0 events) is carried only as a margin probe that
#   shows how close the 60 ms form sits to the spontaneous envelope; it is not a candidate.
# * The combined forms are the architecture question: N4B1C (unchanged) OR a DNp04 path,
#   with one shared refractory. Evaluated here as the union of the two event streams with
#   a shared 20-sample refractory (the first firing is exact; counts are the union).
FROZEN: dict = {
    'DNp04 pair 60 ms': {
        'type': 'DNp04', 'spec': {'kind': 'same_side', 'k': 2, 'window': 3},
        'role': 'primary DNp04 readout'},
    'DNp04 triple 200 ms': {
        'type': 'DNp04', 'spec': {'kind': 'same_side', 'k': 3, 'window': 10},
        'role': 'conservative DNp04 readout'},
    'N4B1C OR DNp04 pair 60 ms': {
        'type': 'DNp04', 'spec': {'kind': 'same_side', 'k': 2, 'window': 3},
        'combine_with_n4b1c': True, 'role': 'primary candidate architecture'},
    'N4B1C OR DNp04 triple 200 ms': {
        'type': 'DNp04', 'spec': {'kind': 'same_side', 'k': 3, 'window': 10},
        'combine_with_n4b1c': True, 'role': 'conservative candidate architecture'},
    'DNp04 pair 100 ms (margin probe)': {
        'type': 'DNp04', 'spec': {'kind': 'same_side', 'k': 2, 'window': 5},
        'role': 'margin probe only; not a candidate'},
}
