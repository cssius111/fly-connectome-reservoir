"""M1.8-N2 closed-loop ROOM validation of the dual-path escape decoder.

Every scenario runs the complete game path through `Session.tick`:

    pointer -> physical swatter -> Retina -> LC4/LPLC2 encoder -> MaleCNS -> DNp01
    -> FixedEscapePolicy -> Action -> lifecycle / physics

No DNp01, encoder or retinal value is injected. The only scripted input is the player's
pointer and click, exactly as a human produces them. Each scenario runs twice on the
identical seed and script: once with the pre-N2 single-sample decoder (built from the N1
baseline ROOM configuration and its calibration record) and once with the N2 decoder
(built from the working-tree ROOM configuration and the N2 record). World geometry is
read only for this report; it never reaches either policy.

    python tools/n2_closed_loop.py --report artifacts/m1_8_n2/closed_loop.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.session import Session, build_policy, load_config  # noqa: E402

DT = 0.02
PARKED = (1920.0, 388.8)       # the swatter spawn point: the paddle never receives a command
BASELINE_COMMIT = '76806f0'


STRICT_N2_CONFIG = ROOT / 'artifacts/m1_8_n2b/strict_n2_room_config_v14.json'


def policies():
    """legacy (76806f0), strict N2 (superseded v14 config, if preserved) and the
    working-tree decoder, each built by build_policy from a real configuration."""
    baseline = json.loads(subprocess.check_output(
        ['git', 'show', BASELINE_COMMIT + ':game_room_config.json'], cwd=ROOT, text=True))
    out = {'legacy': lambda: build_policy(baseline, ROOT)[0]}
    if STRICT_N2_CONFIG.exists():
        strict = load_config(STRICT_N2_CONFIG)
        out['strict_n2'] = lambda: build_policy(strict, ROOT)[0]
    out['current'] = lambda: build_policy(load_config(ROOT / 'game_room_config.json'), ROOT)[0]
    return out


class SwitchAtClick:
    """Controlled comparison: one decoder drives until the click, another after it.

    Both decoders receive every MotorState, so each keeps its own neural-only state, and
    two runs with the same seed and script are bit-identical up to the click. After the
    click, the only difference between arms is the escape criterion.
    """

    def __init__(self, before, after):
        self.before, self.after = before, after
        self.clicked = False
        self.samples = 0
        # Samples at which the inactive post-click decoder would itself have fired
        # before the click. Diagnostic only; those actions are discarded.
        self.after_internal_fires_before_click = []

    def reset(self):
        self.before.reset()
        self.after.reset()
        self.clicked = False
        self.samples = 0
        self.after_internal_fires_before_click = []

    def decide(self, motor):
        a = self.before.decide(motor)
        b = self.after.decide(motor)
        if not self.clicked and b.escape:
            self.after_internal_fires_before_click.append(self.samples)
        self.samples += 1
        return b if self.clicked else a

    def diagnostics(self):
        return (self.after if self.clicked else self.before).diagnostics()

    def criterion_diagnostics(self):
        return (self.after if self.clicked else self.before).criterion_diagnostics()


def _channels(escapes):
    out = {}
    for e in escapes:
        out[e['channel']] = out.get(e['channel'], 0) + 1
    return out


class Run:
    """One closed-loop episode with per-tick bookkeeping of escape provenance."""

    def __init__(self, config, policy, seed, brain, ecology=None):
        self.s = Session(config, brain=brain, policy=policy, seed=seed, mode='evaluation',
                         ecology_enabled=ecology)
        self.tick = 0
        self.escapes = []
        self.events = []
        self.peak_dnp01 = 0.0
        self.peak_theta_dot = 0.0
        self.click_tick = None
        self.after_refractory_at_click = None
        self.after_prefire = None

    def step(self, pointer, strike=False):
        s = self.s
        if strike and self.click_tick is None:
            self.click_tick = self.tick
            if isinstance(s.policy, SwitchAtClick):
                s.policy.clicked = True
                self.after_refractory_at_click = s.policy.after.refractory_remaining
                fires = list(s.policy.after_internal_fires_before_click)
                self.after_prefire = {
                    'count': len(fires), 'last_sample': fires[-1] if fires else None,
                    'samples_before_click': None if not fires else s.policy.samples - fires[-1],
                    # Clean isolated latency comparison only if the candidate is not
                    # refractory at the click.
                    'clean_latency_comparison': s.policy.after.refractory_remaining == 0}
        s.tick(pointer=pointer, strike=strike)
        motor = s.fly_loop.last_motor
        action = s.fly_loop.last_action
        total = 0.0 if motor is None else motor.dnp01_total
        self.peak_dnp01 = max(self.peak_dnp01, total)
        if s.last_retina is not None:
            self.peak_theta_dot = max(self.peak_theta_dot, s.last_retina.theta_dot)
        if action.escape:
            criterion = s.policy.criterion_diagnostics()
            drive = s.encoder.last_drive or {}
            self.escapes.append({'tick': self.tick, 'dnp01_total': total,
                                 'encoder_drive': sum(drive.get(k, 0.0) for k in
                                                      ('loomL', 'loomR', 'threatL', 'threatR')),
                                 'theta_dot': 0.0 if s.last_retina is None else s.last_retina.theta_dot,
                                 'channel': criterion['escape_trigger_channel'],
                                 'strength': action.strength, 'lateral': action.lateral,
                                 'lifecycle_mode': (s.world.lifecycle.mode
                                                    if s.world.lifecycle else None)})
        if s.world.lifecycle is not None:
            for e in s.world.lifecycle.events:
                self.events.append({'tick': self.tick, 'type': e['type'],
                                    'reason': e.get('reason')})
        self.tick += 1

    @property
    def fly(self):
        return self.s.world.fly

    def summary(self):
        s = self.s
        counts = {}
        for e in self.events:
            counts[e['type']] = counts.get(e['type'], 0) + 1
        channels = {}
        for e in self.escapes:
            channels[e['channel']] = channels.get(e['channel'], 0) + 1
        after = [e for e in self.escapes
                 if self.click_tick is not None and e['tick'] >= self.click_tick]
        before = [e for e in self.escapes
                  if self.click_tick is None or e['tick'] < self.click_tick]
        first = after[0] if after else None
        return {'ticks': self.tick, 'alive': bool(s.world.fly.alive),
                'hits': int(s.stats.hits), 'strikes': int(s.stats.strikes),
                'click_tick': self.click_tick,
                'escape_actions': len(self.escapes), 'escape_channels': channels,
                'escapes_before_click': len(before),
                'escape_channels_before_click': _channels(before),
                'escapes_after_click': len(after),
                'escape_channels_after_click': _channels(after),
                'first_escape_after_click': first,
                'first_escape_latency_from_click_s': (
                    None if first is None else round((first['tick'] - self.click_tick) * DT, 6)),
                'after_decoder_refractory_ticks_at_click': self.after_refractory_at_click,
                'after_decoder_internal_fires_before_click': self.after_prefire,
                'lifecycle_event_counts': counts,
                'escape_takeoffs': [e for e in self.events if e['type'] == 'escape_takeoff'],
                'voluntary_takeoffs': [e for e in self.events if e['type'] == 'voluntary_takeoff'],
                'peak_dnp01': self.peak_dnp01, 'peak_theta_dot': self.peak_theta_dot}

    def close(self):
        self.s.close()


def settle_to_perch(run, limit=400):
    for _ in range(limit):
        run.step(PARKED)
        if run.s.world.lifecycle.stationary:
            break
    for _ in range(10):
        run.step(PARKED)
    return run.s.world.lifecycle.stationary


def scenario_a_perched_strike(config, policy, seed, brain, offset, hold=100):
    """A: a perched fly under a committed strike. Collisions stay enabled.

    WORLD fixture, as in test_real_loom_aborts_approach: the physical paddle is placed
    at hover height beside the perched fly and held still, so the strike is the only
    loom. The policy still sees only Retina -> frozen brain -> DNp01.

    Placing the paddle is instantaneous. Two finite differences would otherwise see it
    as motion that no physical paddle can produce:
    - the retina would see a one-sample expansion spike (theta_dot about 20 rad/s);
    - the physical swatter would see a pointer jump and drive the paddle, which then
      overshoots and settles, producing real expansion during the hold.
    Both components' own resets are therefore applied immediately after placement (the
    projector reset used at a session reset, and PhysicalSwatter.reset, whose initial
    placement "is not an observed movement"), so the fixture means "the paddle was
    already hovering there". Every hold is then verified zero-loom (paddle speed,
    theta_dot and LC4/LPLC2 drive all exactly zero) and reported. No neural, encoder or
    retinal value is injected.
    """
    run = Run(config, policy, seed, brain)
    try:
        perched = settle_to_perch(run)
        fly, sw = run.fly, run.s.world.swatter
        target = (fly.x + offset[0], fly.y + offset[1])
        sw.x, sw.y = target
        sw.target_x, sw.target_y = target
        sw.vx = sw.vy = 0.0
        run.s.projector.reset()
        run.s.world.physical_swatter.reset()
        speed = theta_dot = drive = 0.0
        for _ in range(hold):
            run.step(target)
            d = run.s.encoder.last_drive or {}
            speed = max(speed, math.hypot(sw.vx, sw.vy))
            theta_dot = max(theta_dot, abs(run.s.last_retina.theta_dot))
            drive = max(drive, sum(d.get(k, 0.0) for k in ('loomL', 'loomR', 'threatL', 'threatR')))
        still_perched = run.s.world.lifecycle.stationary
        for t in range(120):
            run.step(target, strike=(t == 0))
        out = run.summary()
        out.update({'perched_before_threat': perched, 'perched_at_click': still_perched,
                    'offset': list(offset), 'hold_ticks': hold,
                    'hold_zero_loom': {'max_swatter_speed': speed, 'max_abs_theta_dot': theta_dot,
                                       'max_encoder_drive': drive,
                                       'clean': speed == 0.0 and theta_dot == 0.0 and drive == 0.0}})
        return out
    finally:
        run.close()


def scenario_a_perched_hover(config, policy, seed, brain):
    """A (M1.8-A reference): the accepted perched-threat test, pointer on the fly, no click."""
    run = Run(config, policy, seed, brain)
    try:
        for _ in range(170):
            run.step(PARKED)
        perched = run.s.world.lifecycle.stationary
        for _ in range(220):
            run.step((run.fly.x, run.fly.y))
            if run.s.world.lifecycle.mode == 'TAKEOFF_ESCAPE':
                break
        out = run.summary()
        out['perched_before_threat'] = perched
        return out
    finally:
        run.close()


def scenario_b_airborne_strike(config, policy, seed, brain, offset, lead=90):
    """B: an airborne fly (ecology off) tracked by the pointer, then a committed strike."""
    run = Run(config, policy, seed, brain, ecology=False)
    try:
        for _ in range(40):
            run.step(PARKED)
        for _ in range(lead):
            run.step((run.fly.x + offset[0], run.fly.y + offset[1]))
        for t in range(90):
            run.step((run.fly.x + offset[0], run.fly.y + offset[1]), strike=(t == 0))
        out = run.summary()
        out['offset'] = list(offset)
        return out
    finally:
        run.close()


def scenario_c_hover_approach(config, policy, seed, brain, start, speed):
    """C: a slow hover-height approach toward an airborne fly, never committed."""
    run = Run(config, policy, seed, brain, ecology=False)
    try:
        for _ in range(40):
            run.step(PARKED)
        angle = math.atan2(PARKED[1] - run.fly.y, PARKED[0] - run.fly.x)
        for t in range(200):
            r = max(0.0, start - speed * t * DT)
            run.step((run.fly.x + r * math.cos(angle), run.fly.y + r * math.sin(angle)))
        out = run.summary()
        out.update({'start_distance': start, 'pointer_speed': speed})
        return out
    finally:
        run.close()


def scenario_d_no_player(config, policy, seed, brain, ticks):
    """D: no player. The pointer stays on the swatter spawn point for the whole run."""
    run = Run(config, policy, seed, brain)
    try:
        max_swatter_speed = 0.0
        for _ in range(ticks):
            run.step(PARKED)
            sw = run.s.world.swatter
            max_swatter_speed = max(max_swatter_speed, math.hypot(sw.vx, sw.vy))
        out = run.summary()
        out['max_swatter_speed'] = max_swatter_speed
        return out
    finally:
        run.close()


# Seeds whose fly perches naturally within the 400-tick settle window (probed once under
# no player; seeds that never perch would only repeat the airborne scenario B).
PERCH_SEEDS = (255, 101, 14, 15, 16, 21, 28, 39, 46, 57)


def aggregate(rows):
    """Per-arm totals over the rows of one scenario group."""
    out = {}
    for label in rows[0]:
        runs = [row[label] for row in rows]
        lat = [r['first_escape_latency_from_click_s'] for r in runs
               if r['first_escape_latency_from_click_s'] is not None]
        channels = {}
        for r in runs:
            first = r['first_escape_after_click']
            if first is not None:
                channels[first['channel']] = channels.get(first['channel'], 0) + 1
        pre = {}
        for r in runs:
            for k, v in r['escape_channels_before_click'].items():
                pre[k] = pre.get(k, 0) + v
        out[label] = {
            'runs': len(runs),
            'alive_at_end': sum(r['alive'] for r in runs),
            'hits': sum(r['hits'] for r in runs),
            'escapes_before_click': sum(r['escapes_before_click'] for r in runs),
            'escape_channels_before_click': pre,
            'runs_with_escape_after_click': len(lat),
            'first_escape_after_click_channels': channels,
            'latency_from_click_s': sorted(lat),
            'median_latency_from_click_s': float(np.median(lat)) if lat else None,
            'p95_latency_from_click_s': float(np.percentile(lat, 95)) if lat else None,
            'escape_takeoffs': sum(len(r['escape_takeoffs']) for r in runs),
            'voluntary_takeoffs': sum(len(r['voluntary_takeoffs']) for r in runs),
            'perched_at_click': sum(bool(r.get('perched_at_click')) for r in runs),
            # Perched at the click and launched by the first post-click neural escape.
            'perched_neural_takeoff_after_click': sum(
                bool(r.get('perched_at_click')) and r['first_escape_after_click'] is not None
                and r['first_escape_after_click']['lifecycle_mode'] == 'TAKEOFF_ESCAPE'
                for r in runs),
            'perched_runs_alive_at_end': sum(bool(r.get('perched_at_click')) and r['alive']
                                             for r in runs),
        }
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'artifacts/m1_8_n2/closed_loop.json')
    parser.add_argument('--no-player-ticks', type=int, default=9000)
    args = parser.parse_args()
    config = load_config(ROOT / 'game_room_config.json')
    factories = policies()
    brain = None
    results = {}
    started = time.perf_counter()

    current = factories['current']

    def switch(after):
        return lambda: SwitchAtClick(current(), factories[after]())

    arms = {
        # Natural play: one decoder for the whole episode.
        'natural': dict(factories),
        # Controlled: the working-tree decoder drives until the click, so every arm
        # shares the exact state at the click; afterwards only the criterion differs.
        'controlled': {label: switch(label) for label in factories},
    }

    def both(name, fn, *a, arm='natural'):
        nonlocal brain
        row = {}
        for label, make in arms[arm].items():
            if brain is None:
                probe = Session(config, policy=factories['legacy'](), seed=1, mode='evaluation')
                brain = probe.brain
                probe.close()
            row[label] = fn(config, make(), *a[:1], brain, *a[1:])
        key = name + ('' if arm == 'natural' else '__' + arm)
        results.setdefault(key, []).append(row)
        print('%-40s %s  %.0fs' % (key, ' | '.join(
            '%s pre %d post %s %s' % (label, r['escapes_before_click'],
                                      r['first_escape_latency_from_click_s'],
                                      r['first_escape_after_click'] and
                                      r['first_escape_after_click']['channel'])
            for label, r in row.items()), time.perf_counter() - started), flush=True)
        return row

    for seed in PERCH_SEEDS:
        for offset in ((0.0, 0.0), (40.0, -30.0)):
            for arm in ('natural', 'controlled'):
                both('A_perched_committed_strike', scenario_a_perched_strike, seed, offset, arm=arm)
    both('A_perched_hover_m1_8_a', scenario_a_perched_hover, 255)
    for seed in (11, 12, 13, 14, 15, 16):
        for offset in ((20.0, 10.0), (-45.0, 30.0)):
            for arm in ('natural', 'controlled'):
                both('B_airborne_committed_strike', scenario_b_airborne_strike, seed, offset, arm=arm)
    for seed in (21, 22, 23):
        for start, speed in ((700.0, 260.0), (600.0, 150.0), (500.0, 90.0)):
            both('C_hover_approach', scenario_c_hover_approach, seed, start, speed)
    for seed in (101, 255, 4242):
        both('D_no_player', scenario_d_no_player, seed, args.no_player_ticks)

    report = {'label': 'M1.8-N2 closed-loop ROOM validation; real sensory and neural chain',
              'baseline_commit': BASELINE_COMMIT, 'parked_pointer': list(PARKED),
              'decoders': {label: make().criterion_diagnostics() for label, make in factories.items()},
              'summary': {key: aggregate(rows) for key, rows in results.items()},
              'scenarios': results, 'wall_seconds': time.perf_counter() - started}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('written', args.report)


if __name__ == '__main__':
    main()
