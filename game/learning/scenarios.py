"""Scripted opponents and scenario setup for the M2.0 benchmark (environment side).

Scenario code plays the role of the human player and of the experimenter. It MAY read the
world (it must aim the paddle), but nothing it computes is passed to a policy: the only
policy input remains the MotorState built by the unchanged FlyLoop. Every scenario drives
the paddle through the accepted physical swatter by pointer targets and strike requests,
exactly like a player.

Each scenario draws its opponent parameters from an encounter RNG seeded by the episode
seed, so an EVAL episode is fully determined by (scenario, seed).
"""
from __future__ import annotations

import math

import numpy as np

PARKED = (1920.0, 388.8)
STRIKE_PHASES = ('commit', 'fast_swing', 'active_contact', 'follow_through', 'recovery')


def phase(world):
    return world.swatter.phase.value


def fly_xy(world):
    return world.fly.x, world.fly.y


class Scenario:
    name = 'base'
    seconds = 20.0
    max_seconds = None          # hard cap when the scenario extends itself (perched)

    def setup(self, session, rng):
        pass

    def step(self, session, t, rng):
        return PARKED, False

    def done(self, session, t):
        return t * 0.02 >= self.seconds

    def info(self):
        return {}


class _Striker:
    """Scripted player: tracks the fly with a lead and clicks when the paddle is within a
    per-strike trigger distance.

    The pointer tracks the fly with a human-like lag (0.05-0.30 s) and a slowly varying aim
    error (stationary standard deviation 0-80 units). The trigger distance is drawn from
    U(50, 350) units for every strike. That matches the
    paddle-to-fly distance at the click in the recorded human sessions (pooled over three
    sessions, 52 strikes: p10 about 50-130, median 130-300, p75 185-615 units; human hit
    rate 21 / 52). It is a geometric calibration, not a neural one.
    """

    def __init__(self, rng):
        # Human-like tracking: the pointer follows where the fly was `lag` seconds ago, with a
        # slowly varying aim error (per-episode sigma), not the fly's current position.
        self.lag_ticks = int(round(float(rng.uniform(0.05, 0.30)) / 0.02))
        self.gap_lo, self.gap_hi = 0.8, 1.6
        self.next_ok = float(rng.uniform(0.5, 1.5))
        self.sigma = float(rng.uniform(0.0, 80.0))
        self.err = np.zeros(2)
        self.trigger = float(rng.uniform(50.0, 350.0))
        self.track = []

    def step(self, world, t, rng):
        self.track.append(fly_xy(world))
        lx, ly = self.track[max(0, len(self.track) - 1 - self.lag_ticks)]
        self.err = 0.9 * self.err + 0.1 * rng.normal(0.0, self.sigma, 2) * np.sqrt(19.0)
        px, py = lx + self.err[0], ly + self.err[1]
        fx, fy = fly_xy(world)
        sw = world.swatter
        strike = False
        if t * 0.02 >= self.next_ok and phase(world) == 'approach' \
                and math.hypot(sw.x - fx, sw.y - fy) <= self.trigger:
            strike = True
            self.next_ok = t * 0.02 + float(rng.uniform(self.gap_lo, self.gap_hi))
            self.trigger = float(rng.uniform(50.0, 350.0))
        return (px, py), strike


class DirectStrike(Scenario):
    name = 'direct_strike'
    seconds = 20.0

    def setup(self, session, rng):
        self.striker = _Striker(rng)

    def step(self, session, t, rng):
        return self.striker.step(session.world, t, rng)


class HoverChase(Scenario):
    """Hovers beside the fly (150-260 units) for 1.5-3.5 s, then attacks; repeats."""
    name = 'hover_chase'
    seconds = 20.0

    def setup(self, session, rng):
        self.striker = _Striker(rng)
        self._new_cycle(0, rng)

    def _new_cycle(self, t, rng):
        self.mode = 'hover'
        self.until = t * 0.02 + float(rng.uniform(1.5, 3.5))
        self.radius = float(rng.uniform(150.0, 260.0))
        self.angle = float(rng.uniform(0, 2 * math.pi))
        self.spin = float(rng.uniform(-1.0, 1.0))

    def step(self, session, t, rng):
        w = session.world
        if self.mode == 'hover':
            self.angle += self.spin * 0.02
            fx, fy = fly_xy(w)
            if t * 0.02 >= self.until:
                self.mode = 'attack'
                self.attack_until = t * 0.02 + 2.0
            return (fx + self.radius * math.cos(self.angle), fy + self.radius * math.sin(self.angle)), False
        pointer, strike = self.striker.step(w, t, rng)
        if strike or t * 0.02 >= self.attack_until:
            self._new_cycle(t, rng)
        return pointer, strike


class GlancingPass(Scenario):
    """Fast sweeps past the fly at a miss distance of 250-450 units; never strikes."""
    name = 'glancing_pass'
    seconds = 20.0

    def setup(self, session, rng):
        self._new_sweep(session.world, 0, rng)

    def _new_sweep(self, w, t, rng):
        self.miss = float(rng.uniform(250.0, 450.0))
        self.speed = float(rng.uniform(900.0, 1500.0))
        a = float(rng.uniform(0, 2 * math.pi))
        self.c = (math.cos(a), math.sin(a))
        self.p = (-self.c[1], self.c[0])
        self.anchor = fly_xy(w)
        self.t0 = t
        self.span = 900.0
        self.pause_until = None

    def step(self, session, t, rng):
        w = session.world
        s = -self.span + self.speed * (t - self.t0) * 0.02
        if s > self.span:
            if self.pause_until is None:
                self.pause_until = t * 0.02 + float(rng.uniform(0.5, 1.5))
            if t * 0.02 >= self.pause_until:
                self._new_sweep(w, t, rng)
            s = self.span
        ax, ay = self.anchor
        return (ax + self.c[0] * self.miss + self.p[0] * s, ay + self.c[1] * self.miss + self.p[1] * s), False


class AbortedApproach(Scenario):
    """Approaches from 600-800 units to 300-420 units at 400-700 units/s, then retreats."""
    name = 'aborted_approach'
    seconds = 20.0

    def setup(self, session, rng):
        self._new(0, rng)

    def _new(self, t, rng):
        self.r0 = float(rng.uniform(600.0, 800.0))
        self.rmin = float(rng.uniform(300.0, 420.0))
        self.speed = float(rng.uniform(400.0, 700.0))
        a = float(rng.uniform(0, 2 * math.pi))
        self.dir = (math.cos(a), math.sin(a))
        self.t0 = t
        self.turn = (self.r0 - self.rmin) / self.speed

    def step(self, session, t, rng):
        s = (t - self.t0) * 0.02
        r = self.r0 - self.speed * s if s <= self.turn else self.rmin + self.speed * (s - self.turn)
        if r > self.r0 + 1e-9:
            self._new(t, rng)
            r = self.r0
        fx, fy = fly_xy(session.world)
        return (fx + self.dir[0] * r, fy + self.dir[1] * r), False


class FreeFlight(Scenario):
    """No player: the paddle stays parked."""
    name = 'free_flight'
    seconds = 60.0


class WallEdge(Scenario):
    """The fly starts 1.5-3 body lengths from a wall or corner, flying along it; a scripted
    player attacks. Placement is experimenter-side setup, never a policy input."""
    name = 'wall_edge_strike'
    seconds = 20.0

    def setup(self, session, rng):
        w = session.world
        bl, m, r = w.body_length, w.margin, w.fly_radius
        for _ in range(50):
            kind = int(rng.integers(8))
            gap = m + r + float(rng.uniform(1.5, 3.0)) * bl
            if kind < 4:                                   # along a wall
                along = float(rng.uniform(0.2, 0.8))
                x, y, h = [(gap, along * w.height, math.pi / 2), (w.width - gap, along * w.height, -math.pi / 2),
                           (along * w.width, gap, 0.0), (along * w.width, w.height - gap, math.pi)][kind]
            else:                                          # in a corner, heading into it
                cx = gap if kind in (4, 6) else w.width - gap
                cy = gap if kind in (4, 5) else w.height - gap
                x, y = cx, cy
                h = math.atan2((0 if cy < w.height / 2 else w.height) - cy, (0 if cx < w.width / 2 else w.width) - cx)
            if w.room is None or w.room.valid_spawn(x, y, r):
                w.fly.x, w.fly.y, w.fly.heading = x, y, h % (2 * math.pi)
                sp = math.hypot(w.fly.vx, w.fly.vy)
                w.fly.vx, w.fly.vy = sp * math.cos(h), sp * math.sin(h)
                self.placement = {'kind': 'wall' if kind < 4 else 'corner', 'x': x, 'y': y}
                break
        else:
            self.placement = {'kind': 'unplaced'}
        self.striker = _Striker(rng)

    def step(self, session, t, rng):
        return self.striker.step(session.world, t, rng)

    def info(self):
        return {'placement': self.placement.get('kind')}


class PerchedStrike(Scenario):
    """No player until the fly perches (lifecycle stationary) or 150 s; once perched, a
    scripted player attacks for 10 s. Not-reached episodes are reported separately. (In the
    accepted runtime's no-player free flight, 35 / 40 runs perch within 180 s; median first
    perch at 41 s, p90 at 120 s.)"""
    name = 'perched_strike'
    seconds = 150.0
    max_seconds = 160.0

    def setup(self, session, rng):
        self.striker = _Striker(rng)
        self.perch_t = None

    def step(self, session, t, rng):
        w = session.world
        if self.perch_t is None:
            if w.lifecycle is not None and w.lifecycle.stationary:
                self.perch_t = t
            else:
                return PARKED, False
        return self.striker.step(w, t, rng)

    def done(self, session, t):
        if self.perch_t is None:
            return t * 0.02 >= self.seconds
        return (t - self.perch_t) * 0.02 >= 10.0

    def info(self):
        return {'perch_reached': self.perch_t is not None,
                'perch_time_s': None if self.perch_t is None else self.perch_t * 0.02}


SCENARIOS = (DirectStrike, HoverChase, GlancingPass, AbortedApproach, FreeFlight, WallEdge, PerchedStrike)
SCENARIO_INDEX = {cls.name: i for i, cls in enumerate(SCENARIOS)}
