"""M2.1 exposure-controlled benchmark (benchmark v2): discrete threat trials and separate
background / ecological episodes. Environment side only; nothing here reaches a policy.

Threat trials (family A). Each trial is one short episode from `Session.reset(seed)`:

    PRE-THREAT WINDOW -> THREAT (attacker engages, one committed strike) -> RESPONSE WINDOW
    -> OUTCOME (hit / miss) -> end of trial (the next trial is a new reset)

Exposure control:

* Every trial contains exactly one committed strike. The attacker engages at an engage time
  drawn from the seed BEFORE the first tick, and clicks when the paddle is within its
  trigger distance or, at the latest, 4 s after engaging (forced click). No policy
  behaviour can remove the strike.
* All random draws that define the encounter (engage time, attacker skill, hover duration,
  wall placement, perch delay, fallback time) are made at setup from the seed, in a fixed
  order. Aim-error noise comes from a separate per-tick stream consumed identically on every
  tick. The encounter is therefore identical across policies up to the policy's own effect
  on the fly.
* Perched family: if the fly perches naturally before its fallback time minus 2 s, the
  threat engages 1.0-2.5 s after the perch; otherwise a matched airborne threat engages at
  the predetermined fallback time (30-40 s). Never perching cannot avoid the threat.
  Lifecycle state is never forced.

Background episodes (family B) contain no strike and measure ecological / locomotor
behaviour. Threat and background results are reported separately.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

from .metrics import category
from .scenarios import AbortedApproach, FreeFlight, GlancingPass, PARKED, fly_xy

DT = 0.02
APPROACH_TIMEOUT_S = 4.0
RESPONSE_TAIL_S = 0.5
PRE_THREAT_S = 1.0

# Attacker skill distributions (per trial, drawn at setup). "nominal" is the M2.0 calibration
# (human click-distance geometry); "easy" and "hard" bracket it with longer / shorter tracking
# lag, larger / smaller aim error and farther / nearer clicks.
ATTACKERS = {
    'easy': {'lag_s': (0.20, 0.40), 'aim_sigma': (40.0, 100.0), 'trigger': (150.0, 400.0)},
    'nominal': {'lag_s': (0.05, 0.30), 'aim_sigma': (0.0, 80.0), 'trigger': (50.0, 350.0)},
    'hard': {'lag_s': (0.00, 0.10), 'aim_sigma': (0.0, 20.0), 'trigger': (30.0, 150.0)},
}


class Attacker:
    def __init__(self, profile, rng):
        p = ATTACKERS[profile]
        self.profile = profile
        self.lag_ticks = int(round(float(rng.uniform(*p['lag_s'])) / DT))
        self.sigma = float(rng.uniform(*p['aim_sigma']))
        self.trigger = float(rng.uniform(*p['trigger']))
        self.err = np.zeros(2)
        self.track = []

    def aim(self, world, noise_rng, offset=(0.0, 0.0)):
        self.track.append(fly_xy(world))
        lx, ly = self.track[max(0, len(self.track) - 1 - self.lag_ticks)]
        self.err = 0.9 * self.err + 0.1 * noise_rng.normal(0.0, 1.0, 2) * self.sigma * math.sqrt(19.0)
        return lx + offset[0] + self.err[0], ly + offset[1] + self.err[1]

    def params(self):
        return {'profile': self.profile, 'lag_s': self.lag_ticks * DT, 'aim_sigma': self.sigma, 'trigger': self.trigger}


class ThreatTrial:
    """Base threat trial: free flight with the paddle parked until the engage tick, then the
    attacker approaches and makes one committed strike."""
    name = 'threat_base'

    def setup(self, session, rng, attacker_profile):
        self.attacker = Attacker(attacker_profile, rng)
        self.engage_t = int(round(self.draw_engage(rng) / DT))
        self.click_t = None
        self.resolved_t = None
        self.forced = False
        self.hover_until = None

    def draw_engage(self, rng):
        return float(rng.uniform(1.5, 6.0))

    def engaged(self, session, t):
        return t >= self.engage_t

    def pointer(self, session, t, noise_rng):
        w = session.world
        # The aim stream is advanced every tick, so its sequence does not depend on the policy.
        target = self.attacker.aim(w, noise_rng)
        if not self.engaged(session, t):
            return PARKED, False
        strike = False
        if self.click_t is None and w.swatter.phase.value == 'approach':
            fx, fy = fly_xy(w)
            near = math.hypot(w.swatter.x - fx, w.swatter.y - fy) <= self.attacker.trigger
            timeout = t >= self.engage_t + int(APPROACH_TIMEOUT_S / DT)
            if near or timeout:
                strike = True
                self.forced = bool(timeout and not near)
        return target, strike

    def cap(self):
        return self.engage_t + int((APPROACH_TIMEOUT_S + 3.0) / DT)

    def info(self):
        return {}


class DirectThreat(ThreatTrial):
    name = 'direct'


class HoverThreat(ThreatTrial):
    """Engages, hovers 150-260 units beside the fly for 1-3 s, then strikes."""
    name = 'hover'

    def setup(self, session, rng, attacker_profile):
        super().setup(session, rng, attacker_profile)
        self.hover_ticks = int(round(float(rng.uniform(1.0, 3.0)) / DT))
        self.radius = float(rng.uniform(150.0, 260.0))
        self.angle = float(rng.uniform(0, 2 * math.pi))

    def draw_engage(self, rng):
        return float(rng.uniform(1.5, 4.0))

    def pointer(self, session, t, noise_rng):
        if self.engage_t <= t < self.engage_t + self.hover_ticks:
            w = session.world
            off = (self.radius * math.cos(self.angle), self.radius * math.sin(self.angle))
            return self.attacker.aim(w, noise_rng, off), False
        if t >= self.engage_t + self.hover_ticks:
            saved = self.engage_t
            self.engage_t = saved + self.hover_ticks          # the strike phase starts after hovering
            try:
                return super().pointer(session, t, noise_rng)
            finally:
                self.engage_t = saved
        return super().pointer(session, t, noise_rng)

    def cap(self):
        return self.engage_t + self.hover_ticks + int((APPROACH_TIMEOUT_S + 3.0) / DT)


class WallThreat(ThreatTrial):
    """The fly starts 1.5-3 body lengths from a wall or in a corner (experimenter setup)."""
    name = 'wall'

    def setup(self, session, rng, attacker_profile):
        w = session.world
        bl, m, r = w.body_length, w.margin, w.fly_radius
        self.placement = 'unplaced'
        for _ in range(50):
            kind = int(rng.integers(8))
            gap = m + r + float(rng.uniform(1.5, 3.0)) * bl
            if kind < 4:
                along = float(rng.uniform(0.2, 0.8))
                x, y, h = [(gap, along * w.height, math.pi / 2), (w.width - gap, along * w.height, -math.pi / 2),
                           (along * w.width, gap, 0.0), (along * w.width, w.height - gap, math.pi)][kind]
            else:
                x = gap if kind in (4, 6) else w.width - gap
                y = gap if kind in (4, 5) else w.height - gap
                h = math.atan2((0 if y < w.height / 2 else w.height) - y, (0 if x < w.width / 2 else w.width) - x)
            if w.room is None or w.room.valid_spawn(x, y, r):
                sp = math.hypot(w.fly.vx, w.fly.vy)
                w.fly.x, w.fly.y, w.fly.heading = x, y, h % (2 * math.pi)
                w.fly.vx, w.fly.vy = sp * math.cos(h), sp * math.sin(h)
                self.placement = 'wall' if kind < 4 else 'corner'
                break
        super().setup(session, rng, attacker_profile)

    def draw_engage(self, rng):
        return float(rng.uniform(1.0, 3.0))

    def info(self):
        return {'placement': self.placement}


class PerchedOrFallbackThreat(ThreatTrial):
    """Perched threat if the fly perches naturally in time, otherwise a matched airborne threat
    at the predetermined fallback time. Both branches are drawn at setup."""
    name = 'perched_or_fallback'

    def setup(self, session, rng, attacker_profile):
        super().setup(session, rng, attacker_profile)
        self.fallback_t = int(round(float(rng.uniform(30.0, 40.0)) / DT))
        self.perch_delay_t = int(round(float(rng.uniform(1.0, 2.5)) / DT))
        self.perch_t = None
        self.engage_t = self.fallback_t
        self.branch = 'airborne_fallback'

    def pointer(self, session, t, noise_rng):
        w = session.world
        if self.perch_t is None and t < self.fallback_t - int(2.0 / DT) and w.lifecycle is not None \
                and w.lifecycle.stationary:
            self.perch_t = t
            self.engage_t = t + self.perch_delay_t
            self.branch = 'perched'
        return super().pointer(session, t, noise_rng)

    def info(self):
        return {'branch': self.branch, 'perch_time_s': None if self.perch_t is None else self.perch_t * DT,
                'fallback_time_s': self.fallback_t * DT}


THREAT_FAMILIES = (DirectThreat, HoverThreat, WallThreat, PerchedOrFallbackThreat)


class HoverOnly(GlancingPass):
    """Background: the paddle hovers 150-260 units beside the fly for 20 s and never strikes."""
    name = 'hover_only'
    seconds = 20.0

    def setup(self, session, rng):
        self.radius = float(rng.uniform(150.0, 260.0))
        self.angle = float(rng.uniform(0, 2 * math.pi))
        self.spin = float(rng.uniform(-1.0, 1.0))

    def step(self, session, t, rng):
        self.angle += self.spin * DT
        fx, fy = fly_xy(session.world)
        return (fx + self.radius * math.cos(self.angle), fy + self.radius * math.sin(self.angle)), False


BACKGROUND_FAMILIES = (FreeFlight, GlancingPass, AbortedApproach, HoverOnly)


# ----------------------------------------------------------------- trial runner ---
def run_threat_trial(session, family_cls, attacker_profile, seed, mode, tick_hook=None):
    """One exposure-controlled threat trial. Returns a per-trial record (never seen by a policy)."""
    from .policies import ManeuverPolicy
    mode.check_seed(seed)
    policy = session.policy
    session.reset(seed)
    if isinstance(policy, ManeuverPolicy):
        policy.reseed(seed + 104_729)
        policy.explore = mode.explore
    setup_rng = np.random.default_rng([seed, 23])
    noise_rng = np.random.default_rng([seed, 29])
    trial = family_cls()
    trial.setup(session, setup_rng, attacker_profile)
    w = session.world
    rows = []
    h = hashlib.sha256()
    t = 0
    hit = False
    while True:
        pointer, strike = trial.pointer(session, t, noise_rng)
        committed_before = w.swatter.phase.value in ('commit', 'fast_swing', 'active_contact', 'follow_through', 'recovery')
        horizontal_before = math.hypot(w.swatter.x - w.fly.x, w.swatter.y - w.fly.y)
        mode_before = None if w.lifecycle is None else w.lifecycle.mode
        events = session.tick(pointer=pointer, strike=strike)
        if events.strike_started and trial.click_t is None:
            trial.click_t = t
        action = session.fly_loop.last_action
        motor = session.fly_loop.last_motor
        life = w.lifecycle
        rows.append({'escape': bool(action.escape and action.strength > 0), 'turn': float(action.turn),
                     'saccade': bool(action.saccade), 'category': category(action),
                     'speed': math.hypot(w.fly.vx, w.fly.vy), 'wall': bool(w.wall_contact or w.object_contact),
                     'stationary': bool(life is not None and life.stationary),
                     'behavior_state': (policy.diagnostics() or {}).get('behavior_state', 'CALM')
                     if hasattr(policy, 'diagnostics') else 'CALM',
                     'dnp01': 0.0 if motor is None else motor.dnp01_total,
                     'horizontal': math.hypot(w.swatter.x - w.fly.x, w.swatter.y - w.fly.y)})
        h.update(np.array([w.fly.x, w.fly.y, float(w.fly.alive), float(action.escape), action.turn]).tobytes())
        if events.hit:
            hit = True
        if trial.click_t is not None and trial.resolved_t is None and (events.strike_resolved or events.hit):
            trial.resolved_t = t
        if tick_hook is not None:
            tick_hook(session, t, events, action, committed_before, horizontal_before, mode_before,
                      trial.resolved_t == t)
        t += 1
        if hit:
            break
        if trial.resolved_t is not None and t >= trial.resolved_t + int(RESPONSE_TAIL_S / DT):
            break
        if t >= trial.cap():
            break
    return summarize_trial(trial, rows, hit, w, seed, family_cls.name, attacker_profile, h.hexdigest())


def summarize_trial(trial, rows, hit, world, seed, family, profile, traj_hash):
    c = trial.click_t
    end = trial.resolved_t if trial.resolved_t is not None else len(rows) - 1
    rec = {'family': family, 'attacker': profile, 'seed': seed, 'exposed': c is not None,
           'engage_s': trial.engage_t * DT, 'click_s': None if c is None else c * DT, 'hit': bool(hit),
           'forced_click': trial.forced, 'attacker_params': trial.attacker.params(), 'trajectory_sha256': traj_hash,
           'ticks': len(rows), **trial.info()}
    if c is None:
        return rec
    pre = rows[max(0, c - int(PRE_THREAT_S / DT)):c]
    win = rows[c:end + 1]
    esc_win = [i for i, r in enumerate(win) if r['escape']]
    rec.update({
        'exposure_type': 'perched' if rows[c]['stationary'] else ('airborne_fallback'
                                                                    if getattr(trial, 'branch', None) == 'airborne_fallback'
                                                                    else 'airborne'),
        'click_distance': rows[c]['horizontal'],
        'escape_in_window': bool(esc_win), 'escape_latency_s': None if not esc_win else esc_win[0] * DT,
        'escapes_in_window': len(esc_win),
        'pre_threat_escape': any(r['escape'] for r in pre),
        'escape_state_at_click': rows[c]['behavior_state'] == 'ESCAPE',
        'pre_threat_turn_saccade_fraction': float(np.mean([(abs(r['turn']) >= 0.3) or r['saccade'] for r in pre])) if pre else 0.0,
        'speed_at_click_bl_s': rows[c]['speed'] / world.body_length,
        'wall_contact_fraction': float(np.mean([r['wall'] for r in rows])),
        'max_speed_fraction': float(np.mean([r['speed'] >= 0.9 * world.max_speed for r in rows])),
        'escapes_before_click': sum(r['escape'] for r in rows[:c]),
        'seconds_before_click': c * DT,
        'blind_pre_click_escape': any(r['escape'] and r['dnp01'] < 0.5 for r in rows[max(0, c - 25):c]),
        'escapes_total': sum(r['escape'] for r in rows),
        'blind_escapes_total': sum(r['escape'] and r['dnp01'] < 0.5 for r in rows),
        'first_escape_s': next((i * DT for i, r in enumerate(rows) if r['escape']), None),
    })
    return rec


def run_background(session, scenario_cls, seed, mode, tick_hook=None):
    """Background episode: reuses the M2.0 runner and adds locomotor-diversity measures."""
    from .runner import run_episode
    r = run_episode(session, scenario_cls, seed, mode, keep_rows=True, tick_hook=tick_hook)
    rows = r.pop('rows')
    speeds = np.array([x['speed'] for x in rows]) / session.world.body_length
    hist = np.histogram(np.clip(speeds, 0, 40), bins=20, range=(0, 40))[0]
    p = hist[hist > 0] / hist.sum()
    cats = [x['category'] for x in rows]
    r['metrics']['speed_entropy_bits'] = float(-(p * np.log2(p)).sum())
    r['metrics']['category_switches_per_s'] = sum(1 for a, b in zip(cats, cats[1:]) if a != b) / (len(cats) * DT)
    r['metrics']['all_escapes_per_min'] = r['metrics']['escapes_per_min']
    return r


def definition():
    return {'version': 'm2.1-benchmark-v2', 'attackers': ATTACKERS, 'approach_timeout_s': APPROACH_TIMEOUT_S,
            'response_tail_s': RESPONSE_TAIL_S, 'pre_threat_s': PRE_THREAT_S,
            'threat_families': {
                'direct': 'engage U(1.5, 6.0) s; approach and strike',
                'hover': 'engage U(1.5, 4.0) s; hover 150-260 units for U(1, 3) s; then strike',
                'wall': 'fly placed 1.5-3 BL from a wall or in a corner; engage U(1.0, 3.0) s',
                'perched_or_fallback': 'perch before fallback - 2 s -> engage perch + U(1.0, 2.5) s; otherwise '
                                       'airborne engage at fallback U(30, 40) s'},
            'background_families': {'free_flight': '60 s, paddle parked', 'glancing_pass': '20 s (M2.0 scenario)',
                                    'aborted_approach': '20 s (M2.0 scenario)',
                                    'hover_only': '20 s, paddle hovers 150-260 units beside the fly, no strike'}}


def definition_sha256():
    return hashlib.sha256(json.dumps(definition(), sort_keys=True).encode()).hexdigest()


def attacker_sha256():
    return hashlib.sha256(json.dumps(ATTACKERS, sort_keys=True).encode()).hexdigest()
