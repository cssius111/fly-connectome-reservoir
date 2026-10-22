"""M3.3 research: offline decoder and encoder variants for the escape decision (read-only).

Exploratory. No runtime file changes. Every variant below exists only inside this tool. A
recording policy never escapes; in the fixed-fly protocols the brain therefore runs exactly as
under the live decoder, and any decoder rule can be replayed offline on the recorded DNp01
activity. Outputs go to artifacts/m3_3/ (git-ignored), with the M3.0 provenance guard.

Encoder variants (on the v27 ROOM configuration):
- legacy: unchanged;
- ache_sX: the M3.2 ache2019_v1 mode with scale X V/mV;
- ache_sX_gateH: the same, with the LPLC2 term multiplied by theta_dot / (theta_dot + H), H in
  deg/s (a looming-motion requirement).

Protocols:
- loom: the M3.0 constant-l/v disk from 10 deg to collision, right azimuth, l/v 10-160 ms, seeds
  700001-700024 (fresh);
- rest: a static 10 deg disk, 48 seeds x 20 s (no encoder drive under any variant);
- flight: Retina sequences recorded in no-player v27 ROOM flight (seeds 9701-9720, 180 s each),
  replayed open-loop through each encoder variant. This approximates what the variant would
  have seen, since the fly's path would change after its first different action.

    python tools/m3_3_research.py loom
    python tools/m3_3_research.py rest
    python tools/m3_3_research.py flight-record
    python tools/m3_3_research.py flight-replay
    python tools/m3_3_research.py analyze
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import statistics
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.action import Action, FixedEscapePolicy, MotorState  # noqa: E402
from game.fly import build_brain  # noqa: E402
from game.perception import Retina  # noqa: E402
from game.session import Session, build_policy  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402

OUT = ROOT / 'artifacts/m3_3'
DT = 0.02
LOOM_LV_MS = (10, 20, 40, 80, 160)
LOOM_SEEDS = tuple(range(700001, 700025))
REST_SEEDS = tuple(range(700101, 700149))
REST_TICKS = 1000
FLIGHT_SEEDS = tuple(range(9701, 9721))
FLIGHT_TICKS = 9000
LOOM_VARIANTS = ('legacy', 'ache_s0.20', 'ache_s0.24', 'ache_s0.28', 'ache_s0.36', 'ache_s0.28_gate10')
FLIGHT_VARIANTS = ('legacy', 'ache_s0.28', 'ache_s0.28_gate5', 'ache_s0.28_gate10', 'ache_s0.28_gate20')
REFRACTORY_TICKS = 20
SPIKE_RULES = {'2in3': (2, 3), '2in2': (2, 2), '3in4': (3, 4), '3in5': (3, 5), '4in6': (4, 6)}


class Recorder:
    """Never escapes; keeps the descending-neuron readout of every sample."""

    def __init__(self):
        self.rows = []

    def reset(self):
        self.rows = []

    def decide(self, motor):
        self.rows.append((motor.dnp01_left, motor.dnp01_right, motor.dna02_left, motor.dna02_right))
        return Action()


def parse_variant(name):
    if name == 'legacy':
        return None, None
    parts = name.split('_')
    scale = float(parts[1][1:])
    gate = float(parts[2][4:]) if len(parts) > 2 else None
    return scale, gate


def variant_session(name, brain=None):
    config = copy.deepcopy(M.config())
    scale, gate = parse_variant(name)
    if scale is not None:
        config['encoder']['feature_model'] = 'ache2019_v1'
        config['encoder']['ache2019'] = {'scale_volts_per_mv': scale}
    recorder = Recorder()
    session = Session(config, brain=brain, policy=recorder, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    if gate is not None:
        encoder = session.fly_loop.encoder
        original = encoder.inject
        loom_cells = encoder._fd.cells['loom']

        def inject(retina, original=original, loom_cells=loom_cells, gate=gate):
            pairs = original(retina)
            speed = max(0.0, math.degrees(retina.theta_dot))
            factor = speed / (speed + gate)
            return [(c, np.float32(a * factor) if any(c is loom_cells[s] for s in 'LR') else a)
                    for c, a in pairs]
        encoder.inject = inject
    return session, recorder


def run_feed(session, recorder, retinas, seed):
    """Feed Retinas; return per-tick DNp01 spikes (L, R) and the recorded readout."""
    dn = (int(session.brain.groups['escape_L'][0]), int(session.brain.groups['escape_R'][0]))
    session.reset(seed)
    session.world.fly.vx = session.world.fly.vy = 0.0
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    spikes = np.zeros((len(retinas), 2), np.uint8)
    try:
        for i in range(len(retinas)):
            session.tick()
            fired = np.asarray(session.brain.fired)
            spikes[i] = ((fired == dn[0]).any(), (fired == dn[1]).any())
    finally:
        del session.projector.project
    return spikes, np.array(recorder.rows, np.float64)


# ------------------------------------------------------------------------------- runs ---
def loom():
    out = OUT / 'loom'
    M.check_provenance(out, '*.npz')
    brain = build_brain(M.config(), ROOT)
    for name in LOOM_VARIANTS:
        path = out / ('%s.npz' % name)
        if path.exists():
            continue
        session, recorder = variant_session(name, brain)
        data = {}
        for lv_ms in LOOM_LV_MS:
            retinas, pre, t0, thetas, last = R.looming(lv_ms / 1000.0, DT, 10.0, None, M.WINDOW_AFTER_S)
            spk, rd = [], []
            for seed in LOOM_SEEDS:
                s, r = run_feed(session, recorder, retinas, seed)
                spk.append(s); rd.append(r)
            data['lv%d_spikes' % lv_ms] = np.array(spk)
            data['lv%d_readout' % lv_ms] = np.array(rd)
            data['lv%d_meta' % lv_ms] = np.array([pre, t0, last])
            data['lv%d_theta' % lv_ms] = np.array(thetas)
        np.savez_compressed(path, **data)
        print('loom', name, 'done', flush=True)


def rest():
    out = OUT / 'rest'
    M.check_provenance(out, '*.npz')
    path = out / 'legacy.npz'
    if path.exists():
        return
    session, recorder = variant_session('legacy')
    static = [Retina(theta=math.radians(10.0), theta_dot=0.0, azimuth=0.5)] * REST_TICKS
    spk, rd = [], []
    for seed in REST_SEEDS:
        s, r = run_feed(session, recorder, static, seed)
        spk.append(s); rd.append(r)
    np.savez_compressed(path, spikes=np.array(spk), readout=np.array(rd))
    print('rest done', flush=True)


def flight_record():
    out = OUT / 'flight_record'
    M.check_provenance(out, '*.npz')
    config = M.config()
    brain = None
    for seed in FLIGHT_SEEDS:
        path = out / ('seed%d.npz' % seed)
        if path.exists():
            continue
        session = Session(config, brain=brain, root=ROOT, seed=seed, mode='evaluation')
        brain, w = session.brain, session.world
        rows = np.zeros((FLIGHT_TICKS, 5), np.float64)
        for t in range(FLIGHT_TICKS):
            session.tick(pointer=M.PARKED)
            r = session.last_retina
            airborne = w.fly.alive and not (w.lifecycle_active and w.lifecycle.stationary)
            rows[t] = (r.theta, r.theta_dot, r.azimuth, airborne, session.fly_loop.last_action.escape)
        session.close()
        np.savez_compressed(path, rows=rows)
        print('flight record', seed, 'done', flush=True)


def flight_replay():
    out = OUT / 'flight_replay'
    M.check_provenance(out, '*.npz')
    brain = build_brain(M.config(), ROOT)
    for name in FLIGHT_VARIANTS:
        path = out / ('%s.npz' % name)
        if path.exists():
            continue
        session, recorder = variant_session(name, brain)
        spk, rd = [], []
        for seed in FLIGHT_SEEDS:
            rows = np.load(OUT / 'flight_record' / ('seed%d.npz' % seed))['rows']
            retinas = [Retina(theta=float(a), theta_dot=float(b), azimuth=float(c)) for a, b, c in rows[:, :3]]
            s, r = run_feed(session, recorder, retinas, seed)
            spk.append(s); rd.append(r)
        np.savez_compressed(path, spikes=np.array(spk), readout=np.array(rd))
        print('flight replay', name, 'done', flush=True)


# --------------------------------------------------------------------------- decoders ---
def n4b1c_escapes(readout):
    """The accepted runtime decoder, replayed on a recorded readout; escape tick indices."""
    policy, _ = build_policy(M.config(), ROOT)
    policy.reset()
    ticks = []
    zero = np.zeros(1, np.float32)
    for i, (dl, dr, al, ar) in enumerate(readout):
        a = policy.decide(MotorState(dnp01_left=dl, dnp01_right=dr, dna02_left=al, dna02_right=ar, trace=zero))
        if a.escape:
            ticks.append(i)
    return ticks


def spike_rule_escapes(spikes, k, window):
    """k same-side DNp01 spikes within `window` ticks (current spike included); refractory 0.4 s."""
    ticks, cooldown = [], 0
    for i in range(len(spikes)):
        if cooldown:
            cooldown -= 1
            continue
        lo = max(0, i - window + 1)
        for side in (0, 1):
            if spikes[i, side] and spikes[lo:i + 1, side].sum() >= k:
                ticks.append(i)
                cooldown = REFRACTORY_TICKS
                break
    return ticks


def decoders():
    rules = {'N4B1C': lambda s, r: n4b1c_escapes(r)}
    for label, (k, w) in SPIKE_RULES.items():
        rules['spikes_' + label] = (lambda s, r, k=k, w=w: spike_rule_escapes(s, k, w))
    return rules


# ---------------------------------------------------------------------------- analysis ---
def fit_threshold(points):
    if len({p[0] for p in points}) < 3:
        return None
    x, y = np.array(points).T
    alpha, delta = np.polyfit(x, y, 1)
    return {'alpha': round(float(alpha), 2), 'delta_ms': round(float(delta) * 1000, 1),
            'theta_th_deg': round(math.degrees(2 * math.atan(1 / alpha)), 1) if alpha > 0 else None}


def analyze():
    rules = decoders()
    report = {'loom': {}, 'rest': {}, 'flight': {}}
    for name in LOOM_VARIANTS:
        path = OUT / 'loom' / ('%s.npz' % name)
        if not path.exists():
            continue
        z = np.load(path)
        for rule, fn in rules.items():
            per, points = {}, []
            for lv_ms in LOOM_LV_MS:
                pre, t0, last = z['lv%d_meta' % lv_ms]
                pre, last = int(pre), int(last)
                thetas = z['lv%d_theta' % lv_ms]
                sizes = []
                for s, r in zip(z['lv%d_spikes' % lv_ms], z['lv%d_readout' % lv_ms]):
                    first = next((t for t in fn(s, r) if pre <= t <= last), None)
                    if first is not None:
                        sizes.append(math.degrees(thetas[first]))
                        points.append((lv_ms / 1000.0, t0 - (first - pre + 1) * DT))
                per[lv_ms] = {'fraction': round(len(sizes) / len(LOOM_SEEDS), 2),
                              'median_size_deg': None if not sizes else round(statistics.median(sizes), 1)}
            report['loom'].setdefault(name, {})[rule] = {'per_lv': per, 'fit': fit_threshold(points)}
    path = OUT / 'rest' / 'legacy.npz'
    if path.exists():
        z = np.load(path)
        minutes = z['spikes'].shape[0] * z['spikes'].shape[1] * DT / 60
        for rule, fn in rules.items():
            n = sum(len(fn(s, r)) for s, r in zip(z['spikes'], z['readout']))
            report['rest'][rule] = {'escapes': n, 'per_min': round(n / minutes, 3), 'minutes': round(minutes, 1)}
    for name in FLIGHT_VARIANTS:
        path = OUT / 'flight_replay' / ('%s.npz' % name)
        if not path.exists():
            continue
        z = np.load(path)
        minutes = z['spikes'].shape[0] * z['spikes'].shape[1] * DT / 60
        for rule, fn in rules.items():
            n = sum(len(fn(s, r)) for s, r in zip(z['spikes'], z['readout']))
            report['flight'].setdefault(name, {})[rule] = {'escapes': n, 'per_min': round(n / minutes, 3)}
    (OUT / 'report.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    for name, by_rule in report['loom'].items():
        print('\nloom', name)
        for rule, r in by_rule.items():
            per = ' '.join('%d:%.2f/%s' % (lv, p['fraction'], p['median_size_deg']) for lv, p in r['per_lv'].items())
            print('  %-12s %s | fit %s' % (rule, per, r['fit']))
    print('\nrest', report['rest'])
    for name, by_rule in report['flight'].items():
        print('flight', name, {k: v['per_min'] for k, v in by_rule.items()})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('loom', 'rest', 'flight-record', 'flight-replay', 'analyze'))
    mode = parser.parse_args().mode
    {'loom': loom, 'rest': rest, 'flight-record': flight_record, 'flight-replay': flight_replay,
     'analyze': analyze}[mode]()


if __name__ == '__main__':
    main()
