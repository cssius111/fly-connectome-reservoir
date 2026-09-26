"""Episode metrics and anti-cheating diagnostics (environment side; never observed).

Per-tick records are taken after each session tick. Metrics are computed per episode and
aggregated per policy. Anti-cheating diagnostics compare a policy with the accepted baseline
using FROZEN thresholds (below), and are validated on exploit probes built to trigger them.
"""
from __future__ import annotations

from collections import Counter
import math

import numpy as np

from ..edge_analysis import edge_diagnostics

NEAR = 310.0
STRIKE_PHASES = ('commit', 'fast_swing', 'active_contact', 'follow_through', 'recovery')

# Frozen anti-cheating thresholds (absolute margins over the accepted baseline).
ANTI_CHEAT = {
    'wall_hugging': 'near-wall time fraction > baseline + 0.10 and > 1.5 x baseline',
    'max_speed_flight': 'fraction of airborne time at >= 0.9 x max speed > baseline + 0.05',
    'constant_turning': 'fraction of ticks with abs(turn) >= 0.3 or a saccade request > 0.5, or turn-sign switches '
                        '> 5 per second',
    'freezing': 'fraction of airborne time below 0.25 x cruise speed > baseline + 0.10',
    'spawn_exploit': 'escape in the first 1 s of > 50 % of episodes',
    'paddle_timing_exploit': 'more than 50 % of escapes are blind (summed DNp01 trace < 0.5) and more than 30 % of '
                             'committed strikes are preceded by a blind escape within 0.5 s',
    'ecology_avoidance': 'perches per minute < 0.5 x baseline (added after the v1 benchmark showed that policies '
                         'which never perch escape the perched-strike scenario entirely)',
}


def category(action):
    if action.escape and action.strength > 0:
        if abs(action.lateral) >= abs(action.forward):
            return 'ESCAPE_LEFT' if action.lateral < 0 else 'ESCAPE_RIGHT'
        return 'ESCAPE_FORWARD' if action.forward >= 0 else 'ESCAPE_BACKWARD'
    if action.saccade:
        return 'SACCADE'
    if abs(action.turn) >= 0.3:
        return 'TURN_LEFT' if action.turn < 0 else 'TURN_RIGHT'
    return 'NONE'


def entropy(counts):
    n = sum(counts.values())
    if n == 0:
        return 0.0
    p = np.array([c / n for c in counts.values() if c])
    return float(-(p * np.log2(p)).sum())


class EpisodeRecorder:
    def __init__(self, session):
        self.s = session
        w = session.world
        self.max_speed, self.cruise = w.max_speed, w.baseline_speed
        self.rows = []
        self.strike_ticks = []
        self.prev_strikes = w.stats.strikes

    def record(self, t, action, events, maneuver_index=None):
        w = self.s.world
        f, sw = w.fly, w.swatter
        motor = self.s.fly_loop.last_motor
        e = edge_diagnostics(w)
        life = w.lifecycle
        if w.stats.strikes > self.prev_strikes:
            self.strike_ticks.append(t)
            self.prev_strikes = w.stats.strikes
        self.rows.append({
            'x': f.x, 'y': f.y, 'speed': math.hypot(f.vx, f.vy), 'alive': f.alive,
            'airborne': not (life is not None and life.stationary),
            'life_mode': None if life is None else life.mode,
            'wall': bool(w.wall_contact), 'object': bool(w.object_contact), 'near_wall': bool(e['fly_near_wall']),
            'horizontal': math.hypot(sw.x - f.x, sw.y - f.y), 'committed': sw.phase.value in STRIKE_PHASES,
            'escape': bool(action.escape and action.strength > 0), 'turn': float(action.turn),
            'saccade': bool(action.saccade), 'category': category(action), 'maneuver': maneuver_index,
            'dnp01': 0.0 if motor is None else motor.dnp01_total,
            'hit': bool(events.hit), 'resolved': bool(events.strike_resolved)})

    def metrics(self, scenario_info=None):
        R = self.rows
        n = len(R)
        dt = 0.02
        minutes = n * dt / 60
        w = self.s.world
        st = w.stats
        speeds = np.array([r['speed'] for r in R])
        air = np.array([r['airborne'] for r in R])
        esc = [i for i, r in enumerate(R) if r['escape']]
        unnecessary = [i for i in esc if not R[i]['committed'] and R[i]['horizontal'] > NEAR
                       and not any(0 <= s - i <= 25 for s in self.strike_ticks)]
        blind = [i for i in esc if R[i]['dnp01'] < 0.5]
        pre_click_blind = sum(1 for s in self.strike_ticks if any(0 < s - i <= 25 for i in blind))
        step = np.hypot(np.diff([r['x'] for r in R]), np.diff([r['y'] for r in R])) if n > 1 else np.zeros(0)
        turns = np.array([r['turn'] for r in R])
        signs = np.sign(turns[np.abs(turns) >= 0.05])
        switches = int(np.sum(signs[1:] != signs[:-1])) if signs.size > 1 else 0
        modes = [r['life_mode'] for r in R]
        stuck = 0
        run = 0
        for m in modes:
            run = run + 1 if m == 'LAND_APPROACH' else 0
            if run == 500:
                stuck += 1
        perches = sum(1 for a, b in zip(modes, modes[1:]) if a != 'TOUCHDOWN' and b == 'TOUCHDOWN')
        cats = Counter(r['category'] for r in R)
        man = Counter(r['maneuver'] for r in R if r['maneuver'] is not None)
        air_speed = speeds[air] if air.any() else np.zeros(0)
        return {
            'ticks': n, 'seconds': n * dt,
            'died': any(r['hit'] for r in R), 'alive_end': R[-1]['alive'] if R else True,
            'strikes': st.strikes, 'hits': st.hits, 'misses': st.misses, 'escape_assisted_misses': st.escapes,
            'escapes': len(esc), 'escapes_per_min': len(esc) / minutes if minutes else 0.0,
            'unnecessary_escapes': len(unnecessary), 'unnecessary_per_min': len(unnecessary) / minutes if minutes else 0.0,
            'wall_contact_fraction': float(np.mean([r['wall'] for r in R])),
            'object_contact_fraction': float(np.mean([r['object'] for r in R])),
            'near_wall_fraction': float(np.mean([r['near_wall'] for r in R])),
            'distance_bl': float(step.sum() / w.body_length),
            'speed_bl_s_p10_p50_p90': [float(np.percentile(speeds, p)) / w.body_length for p in (10, 50, 90)],
            'max_speed_fraction': float(np.mean(air_speed >= 0.9 * self.max_speed)) if air_speed.size else 0.0,
            'airborne_slow_fraction': float(np.mean(air_speed < 0.25 * self.cruise)) if air_speed.size else 0.0,
            'airborne_fraction': float(air.mean()),
            'turn_active_fraction': float(np.mean([(abs(r['turn']) >= 0.3) or r['saccade'] for r in R])),
            'saccades_per_min': sum(r['saccade'] for r in R) / minutes if minutes else 0.0,
            'turn_sign_switches_per_s': switches / (n * dt) if n else 0.0,
            'perches': perches, 'perched_fraction': float(np.mean([m in ('TOUCHDOWN', 'PERCHED') for m in modes])),
            'land_approach_stuck_10s': stuck,
            'failed_approaches': getattr(w.lifecycle, 'failed_approaches', None) if w.lifecycle is not None else None,
            'early_escape': any(i < 50 for i in esc),
            'blind_escapes': len(blind), 'pre_click_blind_strikes': pre_click_blind,
            'category_counts': dict(cats), 'category_entropy_bits': entropy(cats),
            'maneuver_counts': {str(k): v for k, v in man.items()}, 'maneuver_entropy_bits': entropy(man) if man else None,
            **({} if scenario_info is None else {'scenario': scenario_info})}


def aggregate(episodes):
    """Pool episode metrics of one policy (all scenarios or one scenario)."""
    E = episodes
    if not E:
        return {}
    strikes = sum(e['strikes'] for e in E)
    minutes = sum(e['seconds'] for e in E) / 60
    esc = sum(e['escapes'] for e in E)
    cats = Counter()
    for e in E:
        cats.update(e['category_counts'])

    def mean(k):
        return float(np.mean([e[k] for e in E]))
    return {
        'episodes': len(E), 'minutes': minutes,
        'survival_fraction': float(np.mean([not e['died'] for e in E])),
        'strikes': strikes, 'hit_rate_per_strike': (sum(e['hits'] for e in E) / strikes) if strikes else None,
        'escape_assisted_survival_per_strike': (sum(e['escape_assisted_misses'] for e in E) / strikes) if strikes else None,
        'escapes_per_min': esc / minutes if minutes else None,
        'unnecessary_escapes_per_min': sum(e['unnecessary_escapes'] for e in E) / minutes if minutes else None,
        'wall_contact_fraction': mean('wall_contact_fraction'), 'object_contact_fraction': mean('object_contact_fraction'),
        'near_wall_fraction': mean('near_wall_fraction'), 'distance_bl_per_min': sum(e['distance_bl'] for e in E) / minutes,
        'speed_bl_s_p50': float(np.median([e['speed_bl_s_p10_p50_p90'][1] for e in E])),
        'speed_bl_s_p90': float(np.median([e['speed_bl_s_p10_p50_p90'][2] for e in E])),
        'max_speed_fraction': mean('max_speed_fraction'), 'airborne_slow_fraction': mean('airborne_slow_fraction'),
        'turn_active_fraction': mean('turn_active_fraction'), 'saccades_per_min': mean('saccades_per_min'),
        'turn_sign_switches_per_s': mean('turn_sign_switches_per_s'),
        'perches_per_min': sum(e['perches'] for e in E) / minutes if minutes else None,
        'perched_fraction': mean('perched_fraction'),
        'lifecycle_stuck_approaches': sum(e['land_approach_stuck_10s'] for e in E),
        'early_escape_fraction': float(np.mean([e['early_escape'] for e in E])),
        'blind_escape_fraction': (sum(e['blind_escapes'] for e in E) / esc) if esc else 0.0,
        'pre_click_blind_per_strike': (sum(e['pre_click_blind_strikes'] for e in E) / strikes) if strikes else 0.0,
        'category_entropy_bits': entropy(cats), 'category_counts': dict(cats),
    }


def anti_cheat(policy_agg, baseline_agg):
    p, b = policy_agg, baseline_agg
    flags = {
        'wall_hugging': p['near_wall_fraction'] > b['near_wall_fraction'] + 0.10
        and p['near_wall_fraction'] > 1.5 * b['near_wall_fraction'],
        'max_speed_flight': p['max_speed_fraction'] > b['max_speed_fraction'] + 0.05,
        'constant_turning': p['turn_active_fraction'] > 0.5 or p['turn_sign_switches_per_s'] > 5.0,
        'freezing': p['airborne_slow_fraction'] > b['airborne_slow_fraction'] + 0.10,
        'spawn_exploit': p['early_escape_fraction'] > 0.5,
        'paddle_timing_exploit': p['blind_escape_fraction'] > 0.5 and p['pre_click_blind_per_strike'] > 0.3,
        'ecology_avoidance': bool(b.get('perches_per_min')) and (p.get('perches_per_min') or 0.0)
        < 0.5 * b['perches_per_min'],
    }
    return flags
