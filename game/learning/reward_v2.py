"""M2.1 reward v2 (event-level) and behavioural constraints (research only; no training here).

Computed outside the policy from privileged state; never observed.

Threat trials (one committed strike each):
    +avoid (1.0) when the strike misses, hit (-1.0) when it hits
    -effort per executed escape in the response window beyond the first (repeated responses)
Background episodes (no strike):
    -unnecessary per unnecessary escape (escape while no strike is committed and the paddle
     is > 310 units away)

Evaluation objective:
    J = mean trial score  -  unnecessary x (background unnecessary escapes per minute)
Constraints (constraint-first; envelopes measured from the accepted baseline on TRAIN /
development seeds, never on EVAL):
    background unnecessary escapes / min <= the baseline's 95 % upper bound (a behavioural
    budget); perch participation >= 0.5 x baseline; wall-contact and max-speed fractions <= the
    baseline's 95 % upper bound + 0.05 and continuous-turn fraction <= 0.5 (movement-pathology
    margins from the frozen M2.0 anti-cheat thresholds, so that merely different behaviour is
    allowed); no anti-cheat flag.

Coefficients are not chosen by intuition. `derive` computes the admissible band of the
unnecessary-escape price from probe-policy inequalities on development data:
    lower bound: every degenerate escape-spam probe whose threat score beats the baseline must
                 lose once its background escapes are priced;
    upper bound: the baseline must beat no_escape and always_turn despite its own escapes.
The price is the geometric mean of the band. An empty band means NO-GO.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math

import numpy as np
from scipy.stats import chi2

DEGENERATE_SPAM = ('random_legal', 'probe_always_escape', 'probe_clock_escape')
DEGENERATE_PASSIVE = ('no_escape', 'probe_constant_turn')


@dataclass(frozen=True)
class RewardV2:
    avoid: float = 1.0
    hit: float = -1.0
    effort: float = 0.0
    unnecessary: float = 0.0
    version: str = 'm2.1-reward-v2'

    def as_dict(self):
        return asdict(self)

    def sha256(self):
        return hashlib.sha256(json.dumps(self.as_dict(), sort_keys=True).encode()).hexdigest()


def trial_score(rec, spec: RewardV2):
    if not rec['exposed']:
        raise ValueError('every threat trial must be exposed')
    base = spec.hit if rec['hit'] else spec.avoid
    return base - spec.effort * max(0, rec['escapes_in_window'] - 1)


def threat_summary(trials):
    n = len(trials)
    hits = sum(t['hit'] for t in trials)
    lat = [t['escape_latency_s'] for t in trials if t.get('escape_latency_s') is not None]
    return {'trials': n, 'exposed': sum(t['exposed'] for t in trials), 'hits': hits,
            'hit_probability': hits / n if n else None,
            'escape_in_window_fraction': float(np.mean([t['escape_in_window'] for t in trials])) if n else None,
            'median_escape_latency_s': float(np.median(lat)) if lat else None,
            'mean_extra_escapes_in_window': float(np.mean([max(0, t['escapes_in_window'] - 1) for t in trials])) if n else None,
            'pre_threat_escape_fraction': float(np.mean([t['pre_threat_escape'] for t in trials])) if n else None,
            'escape_state_at_click_fraction': float(np.mean([t['escape_state_at_click'] for t in trials])) if n else None,
            'forced_click_fraction': float(np.mean([t['forced_click'] for t in trials])) if n else None}


def poisson_upper(k, minutes):
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def bootstrap_upper(values, seed=0, n=2000):
    v = np.asarray(values, float)
    rng = np.random.default_rng(seed)
    means = [rng.choice(v, v.size, replace=True).mean() for _ in range(n)]
    return float(np.percentile(means, 95))


def derive(dev):
    """dev[policy] = {'threat': [trial records], 'background': [episode metrics]}.
    Returns (RewardV2, constraints, derivation record)."""
    def score(pol, spec):
        return float(np.mean([trial_score(t, spec) for t in dev[pol]['threat']]))

    def unnec_rate(pol):
        B = dev[pol]['background']
        return sum(e['unnecessary_escapes'] for e in B) / (sum(e['seconds'] for e in B) / 60)

    s0 = {p: score(p, RewardV2()) for p in dev}
    U = {p: unnec_rate(p) for p in dev}
    b = 'baseline_n4b1c'
    lo, hi = 0.0, math.inf
    lo_terms, hi_terms = {}, {}
    for p in DEGENERATE_SPAM:
        if p in dev and s0[p] > s0[b]:
            if U[p] <= U[b]:
                lo_terms[p] = math.inf
            else:
                lo_terms[p] = (s0[p] - s0[b]) / (U[p] - U[b])
    for p in DEGENERATE_PASSIVE:
        if p in dev and U[b] > U[p]:
            hi_terms[p] = (s0[b] - s0[p]) / (U[b] - U[p]) if s0[b] > s0[p] else -math.inf
    if lo_terms:
        lo = max(lo_terms.values())
    if hi_terms:
        hi = min(hi_terms.values())
    feasible = lo < hi and hi > 0
    price = math.sqrt(max(lo, 1e-6) * hi) if feasible and math.isfinite(hi) else (2 * lo if feasible else None)
    # Effort: at most a quarter of the baseline's margin over no_escape after pricing.
    margin = (s0[b] - s0.get('no_escape', s0[b])) - (price or 0.0) * (U[b] - U.get('no_escape', 0.0))
    extra_b = float(np.mean([max(0, t['escapes_in_window'] - 1) for t in dev[b]['threat']]))
    effort = min(0.05, 0.25 * margin / extra_b) if (feasible and margin > 0 and extra_b > 0) else 0.0
    spec = RewardV2(effort=round(effort, 6), unnecessary=round(price, 6) if price else 0.0)
    # Constraint envelopes from the baseline's development background episodes.
    B = dev[b]['background']
    minutes = sum(e['seconds'] for e in B) / 60
    k = sum(e['unnecessary_escapes'] for e in B)
    perch_rate = sum(e['perches'] for e in B) / minutes
    constraints = {
        'unnecessary_escapes_per_min': {'max': poisson_upper(k, minutes),
                                        'basis': 'exact 95 % Poisson upper bound of the baseline development rate'},
        # Movement pathologies use the frozen M2.0 anti-cheat margins, so behaviour that merely
        # differs from the baseline (for example more turning to dodge) is not excluded.
        'wall_contact_fraction': {'max': bootstrap_upper([e['wall_contact_fraction'] for e in B], 1) + 0.05,
                                  'basis': 'bootstrap 95 % upper bound of the baseline episode mean + 0.05 '
                                           '(pathology margin, as the M2.0 max-speed flag)'},
        'max_speed_fraction': {'max': bootstrap_upper([e['max_speed_fraction'] for e in B], 2) + 0.05,
                               'basis': 'bootstrap 95 % upper bound of the baseline episode mean + 0.05 '
                                        '(the M2.0 max_speed_flight margin)'},
        'turn_active_fraction': {'max': 0.5, 'basis': 'the M2.0 constant_turning threshold (not baseline-anchored)'},
        'perches_per_min': {'min': 0.5 * perch_rate, 'basis': '0.5 x the baseline development perch rate'},
    }
    record = {'threat_score_unpriced': s0, 'background_unnecessary_per_min': U,
              'price_lower_bound_terms': lo_terms, 'price_upper_bound_terms': hi_terms,
              'price_band': [lo, hi], 'feasible': feasible, 'baseline_margin_over_no_escape': margin,
              'baseline_mean_extra_escapes_in_window': extra_b}
    return spec, constraints, record


def objective(threat_trials, background, spec: RewardV2):
    s = float(np.mean([trial_score(t, spec) for t in threat_trials]))
    minutes = sum(e['seconds'] for e in background) / 60
    u = sum(e['unnecessary_escapes'] for e in background) / minutes
    return s - spec.unnecessary * u, s, u


def constraint_check(background_agg, constraints):
    out = {}
    for k, c in constraints.items():
        v = background_agg.get(k)
        out[k] = {'value': v, **c, 'ok': (v <= c['max']) if 'max' in c else (v >= c['min'])}
    return out
