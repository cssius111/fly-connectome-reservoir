"""M3.5 research: why the M3.4 candidate decides fast expansion late (read-only).

Exploratory. No runtime file changes. game/M3_5_STRIKE_ESCAPE_RESEARCH.md found that the v30
candidate decides strikes after contact. This tool splits the decision latency into its parts,
tick by tick:
- the encoder drive (how many LPLC2/LC4 cells are driven, and how many at the 0.8 V cap);
- the LPLC2/LC4 spikes;
- the DNp01 spikes and the first same-side doublet (the M3.3 decision).

Stimuli:
- **strikes.** The fixed-fly strikes of tools/m3_5_strike_escapes.py, overhead and right
  80 units, seeds 950001-950012.
- **looms.** The M3.0 protocol-E disk at right azimuth on the horizon, l/v 20 and 40 ms, seeds
  960001-960012.
- **step.** A network latency floor: a constant drive to a fraction (25, 50 or 100 %) of the right
  side's encoder cells of both types from tick 0. The output is the tick of the first right DNp01
  doublet, seeds 960101-960124.

Arms: v29 (M3.3 candidate `9830757`) and v30 (M3.4 candidate `10e12f6`), each with its own
record. Outputs go to artifacts/m3_5/latency/ (git-ignored).

    NUMBA_NUM_THREADS=1 python tools/m3_5_latency.py trace --arm v29
    NUMBA_NUM_THREADS=1 python tools/m3_5_latency.py trace --arm v30
    NUMBA_NUM_THREADS=1 python tools/m3_5_latency.py step
    python tools/m3_5_latency.py summary
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from game.session import Session  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_5_strike_escapes as S  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/latency'
STRIKE_SEEDS = tuple(range(950001, 950013))
LOOM_SEEDS = tuple(range(960001, 960013))
STEP_SEEDS = tuple(range(960101, 960125))
STRIKES = {'overhead': (0.0, 0.0), 'right_80': (80.0, 90.0)}
LOOM_LV_MS = (20, 40)
STEP_FRACTIONS = (0.25, 0.5, 1.0)
STEP_TICKS = 25
CAP = 0.8


def doublet_tick(spikes, start=0):
    """First tick t >= start with a spike whose previous same-side spike is at most 2 ticks before."""
    last = {}
    for t, by_side in enumerate(spikes):
        for s in 'LR':
            if by_side[s]:
                if t >= start and s in last and t - last[s] <= 2:
                    return t, s
                last[s] = t
    return None, None


class Probe:
    """Per-tick encoder drive and spikes, by wrapping encoder.inject and brain.step (unchanged)."""

    def __init__(self, session):
        self.session = session
        enc, brain = session.encoder, session.brain
        self.cells = {'LPLC2': enc._fd.cells['loom'], 'LC4': enc._fd.cells['threat']}
        self.dnp01 = {s: int(brain.groups['escape_' + s][0]) for s in 'LR'}
        self.rows = []
        self._inject, self._step = enc.inject, brain.step
        enc.inject = self.inject
        brain.step = self.step

    def inject(self, retina):
        out = self._inject(retina)
        row = {'theta_deg': math.degrees(retina.theta)}
        for t, by_side in self.cells.items():
            for s, cells in by_side.items():
                driven = capped = 0
                for idx, amount in out:
                    k = int(np.isin(idx, cells).sum())
                    driven += k
                    capped += k if float(amount) >= CAP - 1e-6 else 0
                row['%s_%s_driven' % (t, s)] = driven
                row['%s_%s_capped' % (t, s)] = capped
        self.rows.append(row)
        return out

    def step(self, *args, **kwargs):
        fired = self._step(*args, **kwargs)
        if not self.rows or 'dnp01' in self.rows[-1]:
            self.rows.append({})                     # a step without an inject of its own
        row = self.rows[-1]
        row['dnp01'] = {s: int(i in fired) for s, i in self.dnp01.items()}
        for t, by_side in self.cells.items():
            for s, cells in by_side.items():
                row['%s_%s_spikes' % (t, s)] = int(np.isin(fired, cells).sum())
        return fired

    def close(self):
        del self.session.encoder.inject
        del self.session.brain.step


def strike_trial(session, seed, distance, bearing):
    session.reset(seed)
    w = session.world
    fly = w.fly
    a = fly.heading + math.radians(bearing)
    pointer = (fly.x + distance * math.cos(a), fly.y + distance * math.sin(a))
    settle = round(session.config['swatter']['physical']['calibration_settle_seconds'] / session.tick_seconds)
    for _ in range(settle):
        session.tick(pointer=pointer, strike=False)
    probe = Probe(session)
    try:
        for t in range(30):
            session.tick(pointer=pointer, strike=(t == 0))
    finally:
        probe.close()
    return probe.rows


def loom_trial(session, retinas, seed):
    session.reset(seed)
    probe = Probe(session)
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    try:
        for _ in retinas:
            session.tick()
    finally:
        del session.projector.project
        probe.close()
    return probe.rows


def trace(arm):
    config = S.arm_config(arm)
    session = Session(config, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    dt = float(config['sim']['tick_seconds'])
    out = OUT / arm
    M.check_provenance(out, '*.json')
    for name, (d, b) in STRIKES.items():
        path = out / ('strike_%s.json' % name)
        if not path.exists():
            path.write_text(json.dumps([strike_trial(session, seed, d, b) for seed in STRIKE_SEEDS]) + '\n',
                            encoding='utf-8')
            print(arm, 'strike', name, 'done', flush=True)
    for lv_ms in LOOM_LV_MS:
        path = out / ('loom_%d.json' % lv_ms)
        if not path.exists():
            retinas, pre, t0, thetas = M.stimulus(lv_ms / 1000.0, M.AZIMUTHS['right'], dt)
            rows = [loom_trial(session, retinas, seed)[pre - 5:] for seed in LOOM_SEEDS]
            path.write_text(json.dumps({'onset_offset': 5, 't0': t0, 'trials': rows}) + '\n', encoding='utf-8')
            print(arm, 'loom', lv_ms, 'done', flush=True)
    session.close()


def step():
    config = S.arm_config('v30')
    session = Session(config, root=ROOT, ecology_enabled=False)
    brain = session.brain
    cells = np.concatenate([session.encoder._fd.cells['loom']['R'], session.encoder._fd.cells['threat']['R']])
    dnp01 = {s: int(brain.groups['escape_' + s][0]) for s in 'LR'}
    out = OUT / 'step'
    M.check_provenance(out, '*.json')
    rng = np.random.default_rng(960100)
    result = {}
    for fraction in STEP_FRACTIONS:
        for amount in (0.4, 0.8):
            ticks = []
            for seed in STEP_SEEDS:
                chosen = np.sort(rng.choice(cells, int(round(fraction * len(cells))), replace=False))
                brain.reset(seed)
                for _ in range(30):
                    brain.step()
                spikes = []
                for _ in range(STEP_TICKS):
                    fired = brain.step(inject=[(chosen, amount)])
                    spikes.append({s: int(i in fired) for s, i in dnp01.items()})
                ticks.append(doublet_tick(spikes)[0])
            hit = [t for t in ticks if t is not None]
            result['%.2f@%.1f' % (fraction, amount)] = {'doublet_fraction': len(hit) / len(ticks),
                                                        'median_tick': statistics.median(hit) if hit else None,
                                                        'ticks': ticks}
            print('step %.0f %% of right cells at %.1f V: doublet %d/%d, median tick %s' % (
                100 * fraction, amount, len(hit), len(ticks), statistics.median(hit) if hit else '-'), flush=True)
    (out / 'step.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')
    session.close()


def summary():
    keys = ('LPLC2', 'LC4')
    for arm in ('v29', 'v30'):
        out = OUT / arm
        if not out.exists():
            continue
        print('==', arm)
        for name in STRIKES:
            trials = json.loads((out / ('strike_%s.json' % name)).read_text(encoding='utf-8'))
            print(' strike %s (median over %d seeds; tick: theta | driven/capped L+R per type | spikes L+R per type | DNp01 L,R)'
                  % (name, len(trials)))
            for t in range(16):
                rows = [tr[t] for tr in trials]
                med = lambda f: statistics.median(f(r) for r in rows)
                print('  %2d: %5.1f | %s | %s | %.2f,%.2f' % (
                    t, med(lambda r: r['theta_deg']),
                    ' '.join('%s %g/%g' % (k, med(lambda r: r['%s_L_driven' % k] + r['%s_R_driven' % k]),
                                            med(lambda r: r['%s_L_capped' % k] + r['%s_R_capped' % k])) for k in keys),
                    ' '.join('%s %g' % (k, med(lambda r: r['%s_L_spikes' % k] + r['%s_R_spikes' % k])) for k in keys),
                    np.mean([r['dnp01']['L'] for r in rows]), np.mean([r['dnp01']['R'] for r in rows])))
            dec = [doublet_tick([r['dnp01'] for r in tr])[0] for tr in trials]
            print('  doublet ticks:', dec)
        for lv in LOOM_LV_MS:
            d = json.loads((out / ('loom_%d.json' % lv)).read_text(encoding='utf-8'))
            dec = [doublet_tick([r['dnp01'] for r in tr], d['onset_offset'])[0] for tr in d['trials']]
            first_cap = []
            for tr in d['trials']:
                k = next((i for i, r in enumerate(tr) if r['LPLC2_R_capped'] + r['LC4_R_capped'] > 0), None)
                first_cap.append(k)
            n = int(math.ceil(d['t0'] / 0.02))
            capped = [k for k in first_cap if k is not None]
            print(' loom l/v %d ms: onset at row %d, collision at row %d; first capped cell row %s; doublet rows %s'
                  % (lv, d['onset_offset'], d['onset_offset'] + n, statistics.median(capped) if capped else '-', dec))
    if (OUT / 'step' / 'step.json').exists():
        print('== step (right encoder cells, constant drive):')
        for k, v in json.loads((OUT / 'step' / 'step.json').read_text(encoding='utf-8')).items():
            print('  %s: doublet %.2f, median tick %s' % (k, v['doublet_fraction'], v['median_tick']))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('trace', 'step', 'summary'))
    parser.add_argument('--arm', choices=('v29', 'v30'))
    args = parser.parse_args()
    if args.mode == 'trace':
        if args.arm is None:
            parser.error('trace needs --arm')
        trace(args.arm)
    elif args.mode == 'step':
        step()
    else:
        summary()


if __name__ == '__main__':
    main()
