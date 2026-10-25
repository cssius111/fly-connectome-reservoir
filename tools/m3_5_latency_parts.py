"""M3.5 research: which parts of the M3.4 candidate's decision delay could shorten (read-only).

Exploratory. No runtime file changes. game/M3_5_STRIKE_ESCAPE_RESEARCH.md (sections 14-15) found
that the v30 fly decides about 2.5 ticks after its DNp01 input could first form a doublet:
- one tick of synaptic transmission from LPLC2/LC4 to DNp01;
- a median of 1-1.5 ticks for the stochastic second spike.
This tool tests the two parts an encoder or decoder change could reach, inside the research
harness only:
- **Encoder cap.** At the 0.8 V cap a driven cell reaches only 0.94 V on the tick after a spike,
  so it fires about every second tick. Caps of 0.86 and 1.0 V let it fire every tick. The scale
  stays 71.3 V/mV.
- **Decoder rule** (offline, on the recorded spike trains):
  - the runtime same-side doublet (two DNp01 spikes at most 2 ticks apart);
  - a DNp01 spike with a same-side DNp02, DNp04 or DNp11 spike in the same tick;
  - the same within one tick.
  Their false alarms come from a rest run.

Stimuli:
- **looms.** V2's loom from 10° at azimuth 90°, elevation 0°, l/v 20, 40 and 80 ms. Seeds
  970501-970524.
- **rest.** A static 10° disk at the same position, 10 s. Seeds 970601-970624; the cap does not
  matter at rest.

Each loom trial records the DNp01, DNp02, DNp04 and DNp11 spikes per side and tick, and the
synaptic input to the right DNp01. The decision delay is read as the intercept of a linear fit of
the decision time before collision against l/v. The real-fly comparators:
- **X16.** Slope 2.0, intercept -6 ms (Fotowat et al. 2009).
- **X24.** A neural delay of 30.1 ms for GF-driven short-mode escapes, 45.7 ms for long-mode
  ones (von Reyn et al. 2014).

Outputs go to artifacts/m3_5/latency_parts/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    NUMBA_NUM_THREADS=1 python tools/m3_5_latency_parts.py looms --cap 0.8
    NUMBA_NUM_THREADS=1 python tools/m3_5_latency_parts.py looms --cap 0.86
    NUMBA_NUM_THREADS=1 python tools/m3_5_latency_parts.py looms --cap 1.0
    NUMBA_NUM_THREADS=1 python tools/m3_5_latency_parts.py rest
    python tools/m3_5_latency_parts.py summary
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

from game.perception import RetinotopicDrive  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_side_balance as B  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/latency_parts'
CAPS = (0.8, 0.86, 1.0)
LV_MS = (20, 40, 80)
AZ_DEG, EL_DEG, START_DEG = 90.0, 0.0, 10.0
LOOM_SEEDS = tuple(range(970501, 970525))
REST_SEEDS = tuple(range(970601, 970625))
REST_S = 10.0
DNS = ('DNp01', 'DNp02', 'DNp04', 'DNp11')
PARTNERS = ('DNp02', 'DNp04', 'DNp11')
DOUBLET_INPUT_V = 0.41


def set_cap(session, cap):
    encoder, config = session.encoder, session.config
    with np.load(ROOT / config['brain']['data'] / 'brain.npz') as meta:
        body_ids = meta['ids']
    cells = {ch: dict(encoder._fd.cells[ch]) for ch in ('loom', 'threat')}
    encoder._retinotopic = RetinotopicDrive(session.brain, body_ids, cells, config['encoder']['retinotopic'],
                                            cap, ROOT)


def record(session, retinas, seed, dn, row):
    """Per-tick DN spikes (by name and side) and the right DNp01's synaptic input, one fixed-fly trial."""
    session.reset(seed)
    fly = session.world.fly
    fly.vx = fly.vy = 0.0
    feed = iter(retinas)
    session.projector.project = lambda world, feed=feed: next(feed)
    brain = session.brain
    original = brain.step
    ticks = []

    def step(*args, **kwargs):
        fired = original(*args, **kwargs)
        entry = {k: int(i in fired) for k, i in dn.items()}
        entry['input_next'] = float(brain.gain * row[fired].sum())
        ticks.append(entry)
        return fired
    brain.step = step
    decisions = []
    try:
        for i in range(len(retinas)):
            session.tick()
            if session.fly_loop.last_action.escape:
                decisions.append(i)
    finally:
        del session.projector.project
        del brain.step
    return ticks, decisions


def setup():
    import tools.m3_4_receptive_fields as RF
    config, session = B.v30_session()
    W = RF.weights().tocsr()
    dn = {'%s_%s' % (d, s): int(np.flatnonzero((session.brain.cell_type == d) & (session.brain.side == s))[0])
          for d in DNS for s in 'LR'}
    row = W[dn['DNp01_R']].toarray().ravel()
    return config, session, dn, row


def looms(args):
    out = OUT / ('cap%.2f' % args.cap)
    M.check_provenance(out, 'lv*.json')
    T.check_fields(out)
    config, session, dn, row = setup()
    set_cap(session, args.cap)
    dt = float(config['sim']['tick_seconds'])
    for lv_ms in LV_MS:
        path = out / ('lv%03d.json' % lv_ms)
        if path.exists():
            continue
        retinas, pre, t0, thetas, last = R.looming(lv_ms / 1000.0, dt, START_DEG, None, M.WINDOW_AFTER_S)
        retinas = T.placed(retinas, AZ_DEG, EL_DEG)
        trials = []
        for seed in LOOM_SEEDS:
            ticks, decisions = record(session, retinas, seed, dn, row)
            first = next((i for i in decisions if pre <= i <= last), None)
            trials.append({'seed': seed, 'decision': first, 'ticks': ticks[pre - 5:last + 1]})
        path.write_text(json.dumps({'lv_ms': lv_ms, 'cap': args.cap, 'onset': pre, 'last': last,
                                    'first_recorded': pre - 5,
                                    'tau_ms': [1000 * (t0 - (i - pre + 1) * dt) for i in range(len(retinas))],
                                    'theta_deg': [math.degrees(t) for t in thetas], 'trials': trials}) + '\n',
                        encoding='utf-8')
        print('cap %.2f lv %d: %d of %d decided' % (args.cap, lv_ms, sum(t['decision'] is not None for t in trials),
                                                     len(trials)), flush=True)
    session.close()


def rest(_args):
    out = OUT / 'rest'
    M.check_provenance(out, 'rest.json')
    T.check_fields(out)
    config, session, dn, row = setup()
    dt = float(config['sim']['tick_seconds'])
    n = int(round(REST_S / dt))
    retinas = T.placed(R.sequence([math.radians(START_DEG)] * n, dt), AZ_DEG, EL_DEG)
    trials = []
    for seed in REST_SEEDS:
        ticks, decisions = record(session, retinas, seed, dn, row)
        trials.append({'seed': seed, 'decisions': decisions,
                       'spikes': {k: [i for i, t in enumerate(ticks) if t[k]] for k in dn}})
    (out / 'rest.json').write_text(json.dumps({'seconds': REST_S, 'trials': trials}) + '\n', encoding='utf-8')
    print('rest: %d runtime decisions in %d x %g s' % (sum(len(t['decisions']) for t in trials), len(trials), REST_S))
    session.close()


def rule_ticks(spikes, rule):
    """All ticks at which a rule fires, from per-side spike tick lists {name_side: [ticks]}."""
    hits = []
    for s in 'LR':
        own = spikes['DNp01_' + s]
        if rule == 'doublet':
            hits += [b for a, b in zip(own, own[1:]) if b - a <= 2]
        else:
            lag = 0 if rule == 'coincident_0' else 1
            partner = sorted(set(t for p in PARTNERS for t in spikes['%s_%s' % (p, s)]))
            for t in own:
                if any(abs(t - u) <= lag for u in partner):
                    hits.append(max([t] + [u for u in partner if abs(t - u) <= lag]))
    return sorted(hits)


RULES = ('doublet', 'coincident_0', 'coincident_1')


def summary(_args):
    rest_path = OUT / 'rest' / 'rest.json'
    if rest_path.exists():
        d = json.loads(rest_path.read_text(encoding='utf-8'))
        total_s = d['seconds'] * len(d['trials'])
        rates = {k: sum(len(t['spikes'][k]) for t in d['trials']) / total_s for k in d['trials'][0]['spikes']}
        print('== rest: spontaneous spikes per s: %s' % ', '.join('%s %.2f' % kv for kv in sorted(rates.items())))
        for rule in RULES:
            hits = sum(len(rule_ticks(t['spikes'], rule)) for t in d['trials'])
            print('   rule %-13s false alarms: %d in %.0f s (%.3f per s)' % (rule, hits, total_s, hits / total_s))
    for cap in CAPS:
        out = OUT / ('cap%.2f' % cap)
        if not out.exists():
            continue
        print('== cap %.2f V' % cap)
        fits = {rule: [] for rule in RULES}
        for lv_ms in LV_MS:
            path = out / ('lv%03d.json' % lv_ms)
            if not path.exists():
                continue
            d = json.loads(path.read_text(encoding='utf-8'))
            base, onset, tau = d['first_recorded'], d['onset'], d['tau_ms']
            parts = []
            for rule in RULES:
                times, lags = [], []
                for tr in d['trials']:
                    spikes = {k: [base + i for i, t in enumerate(tr['ticks']) if t[k] and base + i >= onset]
                              for k in tr['ticks'][0] if k != 'input_next'}
                    hit = rule_ticks(spikes, rule)
                    if hit:
                        times.append(tau[hit[0]])
                        cross = next((base + i + 1 for i, t in enumerate(tr['ticks'])
                                      if base + i >= onset and t['input_next'] >= DOUBLET_INPUT_V), None)
                        if cross is not None:
                            lags.append(hit[0] - cross)
                if times:
                    fits[rule].append((lv_ms, statistics.median(times)))
                parts.append('%s %4.0f ms (n %d, lag after 0.41 V %s)' % (
                    rule, statistics.median(times) if times else float('nan'), len(times),
                    statistics.median(lags) if lags else '-'))
            print('   l/v %2d: %s' % (lv_ms, ' | '.join(parts)))
        for rule, pts in fits.items():
            if len(pts) >= 2:
                x = np.array([p[0] for p in pts], float)
                y = np.array([p[1] for p in pts], float)
                slope, intercept = np.polyfit(x, y, 1)
                print('   fit %-13s slope %.2f, intercept %+.0f ms (threshold %.0f deg)' % (
                    rule, slope, intercept, math.degrees(2 * math.atan(1 / slope)) if slope > 0 else float('nan')))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('looms', 'rest', 'summary'))
    parser.add_argument('--cap', type=float, choices=CAPS)
    args = parser.parse_args()
    if args.mode == 'looms' and args.cap is None:
        parser.error('looms needs --cap')
    {'looms': looms, 'rest': rest, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
