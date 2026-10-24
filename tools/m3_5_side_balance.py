"""M3.5 research: left-right balance of the M3.4 retinotopic encoder (read-only).

Exploratory. No runtime file changes. M3.4 failed V8a: at l/v 10 ms the right side escaped in 42
of 48 trials and the left in 31, and left escapes came later at every l/v
(results/game/M3_4_RETINOTOPIC_DRIVE.md). The report attributes this to the count-balanced subsets.
`RetinalEncoder` drives min(left, right) cells per type and side, so 55 of the 71 left LC4 cells
and 91 of the 94 left LPLC2 cells, and the right subsets carry more DNp01 weight. The report
proposed balancing by weight instead.

This tool compares four selection rules inside the research harness only:
- `count`: the v30 encoder as committed (count-balanced subsets);
- `all`: every LPLC2 and LC4 cell of both sides, each through its own receptive field;
- `count_weighted`: the count subsets, with each side's drive of a type multiplied by
  (mean of the two sides' DNp01 weight) / (this side's DNp01 weight);
- `all_weighted`: every cell, with the same per-side factor.

Subcommands:
- `weights`: each rule's DNp01, DNp02, DNp11 and DNp04 input weight per side and type, from
  data/weights.npz;
- `reach`: the coverage-weighted DNp01 weight of mirrored disks (no dynamics);
- `trials --rule R`: the M3.0 protocol-E loom at right and left azimuth (elevation 0), l/v 10,
  20 and 80 ms, decided by the v30 doublet decoder from its own record. Seeds 970001-970024.

All rules use the v30 candidate configuration (`10e12f6`) and its scale of 71.3 V/mV, which was
calibrated for `count`. Outputs go to artifacts/m3_5/side_balance/ (git-ignored). Needs scipy and
data/receptive_fields_v1.npz.

    python tools/m3_5_side_balance.py weights
    python tools/m3_5_side_balance.py reach
    NUMBA_NUM_THREADS=1 python tools/m3_5_side_balance.py trials --rule count
    python tools/m3_5_side_balance.py summary
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

from game.perception import LOOM_TYPES, THREAT_TYPES, RetinotopicDrive, view_direction  # noqa: E402
from game.session import Session  # noqa: E402
import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_2_escape_roles as R  # noqa: E402
import tools.m3_4_retinotopic as T  # noqa: E402
import tools.m3_5_strike_escapes as S  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/side_balance'
RULES = ('count', 'all', 'count_weighted', 'all_weighted')
CHANNELS = {'loom': LOOM_TYPES, 'threat': THREAT_TYPES}
CHANNEL_NAME = {'loom': 'LPLC2', 'threat': 'LC4'}
DNS = ('DNp01', 'DNp02', 'DNp11', 'DNp04')
LV_MS = (10, 20, 80)
SEEDS = tuple(range(970001, 970025))
SIDES = {'right': 0.5, 'left': -0.5}


def v30_session():
    config = S.arm_config('v30')
    session = Session(config, root=ROOT, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    return config, session


def dn_index(brain):
    return {'%s_%s' % (d, s): int(np.flatnonzero((brain.cell_type == d) & (brain.side == s))[0])
            for d in DNS for s in 'LR'}


def rule_cells(brain, encoder, rule):
    if rule.startswith('count'):
        return {ch: {s: np.asarray(encoder._fd.cells[ch][s]) for s in 'LR'} for ch in CHANNELS}
    return {ch: {s: brain.cells(types, s).astype(np.int64) for s in 'LR'} for ch, types in CHANNELS.items()}


def dnp01_weight(W, brain, cells):
    dn = dn_index(brain)
    return {ch: {s: float(W[dn['DNp01_' + s]][:, by_side[s]].sum()) for s in 'LR'} for ch, by_side in cells.items()}


def side_factors(W, brain, cells, rule):
    if not rule.endswith('weighted'):
        return {ch: {'L': 1.0, 'R': 1.0} for ch in cells}
    w = dnp01_weight(W, brain, cells)
    return {ch: {s: 0.5 * (w[ch]['L'] + w[ch]['R']) / w[ch][s] for s in 'LR'} for ch in cells}


def install(session, rule, W=None):
    """Replace the v30 encoder's RetinotopicDrive by one for the rule; returns the factors used."""
    import tools.m3_4_receptive_fields as RF
    W = RF.weights().tocsr() if W is None else W
    brain, encoder, config = session.brain, session.encoder, session.config
    cells = rule_cells(brain, encoder, rule)
    with np.load(ROOT / config['brain']['data'] / 'brain.npz') as meta:
        body_ids = meta['ids']
    drive = RetinotopicDrive(brain, body_ids, cells, config['encoder']['retinotopic'], encoder.cap, ROOT)
    factors = side_factors(W, brain, cells, rule)
    if rule.endswith('weighted'):
        base = drive.coverage
        per_cell = {ch: np.where(drive.channels[ch]['side'] == 'L', factors[ch]['L'], factors[ch]['R'])
                    for ch in drive.channels}
        drive.coverage = lambda channel, centre, theta_deg: base(channel, centre, theta_deg) * per_cell[channel]
    encoder._retinotopic = drive
    return cells, factors


def weights(_args):
    import tools.m3_4_receptive_fields as RF
    W = RF.weights().tocsr()
    _, session = v30_session()
    brain = session.brain
    dn = dn_index(brain)
    out = {}
    for rule in ('count', 'all'):
        cells = rule_cells(brain, session.encoder, rule)
        out[rule] = {}
        for ch, by_side in cells.items():
            for s in 'LR':
                out[rule]['%s_%s' % (CHANNEL_NAME[ch], s)] = {
                    'cells': int(len(by_side[s])),
                    **{d: float(W[dn['%s_%s' % (d, s)]][:, by_side[s]].sum()) for d in DNS}}
        factors = side_factors(W, brain, cells, rule + '_weighted')
        out[rule + '_weighted_factors'] = factors
        print('== %s' % rule)
        for key, v in out[rule].items():
            print('  %-8s n %3d  %s' % (key, v['cells'], '  '.join('%s %.4f' % (d, v[d]) for d in DNS)))
        print('  %s_weighted factors: %s' % (rule, ', '.join(
            '%s L %.3f R %.3f' % (CHANNEL_NAME[ch], f['L'], f['R']) for ch, f in factors.items())))
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'weights.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')


def reach(_args):
    """sum_i c_i * w_i * factor onto the ipsilateral DNp01, for mirrored disks."""
    import tools.m3_4_receptive_fields as RF
    W = RF.weights().tocsr()
    _, session = v30_session()
    brain = session.brain
    dn = dn_index(brain)
    positions = {'V1 lateral (az 90, el 0)': (90.0, 0.0), 'calibration (az 50, el 11)': (50.0, 11.0),
                 'front-lateral (az 30, el 0)': (30.0, 0.0), 'rear-lateral (az 130, el 0)': (130.0, 0.0)}
    sizes = (20.0, 40.0, 60.0, 90.0)
    out = {}
    for rule in RULES:
        install(session, rule, W)
        drive = session.encoder._retinotopic
        out[rule] = {}
        for label, (az, el) in positions.items():
            for size in sizes:
                row = {}
                for name, sign in (('right', 1.0), ('left', -1.0)):
                    centre = view_direction(math.radians(sign * az), math.radians(el))
                    s = 'R' if sign > 0 else 'L'
                    total = 0.0
                    for ch in drive.channels:
                        c = drive.coverage(ch, centre, size)
                        idx = drive.channels[ch]['index']
                        on = drive.channels[ch]['side'] == s
                        total += float((c[on] * W[dn['DNp01_' + s]][:, idx[on]].toarray().ravel()).sum())
                    row[name] = total
                out[rule]['%s, %g deg' % (label, size)] = row
        print('== %s: DNp01 reach right / left (ratio)' % rule)
        for key, row in out[rule].items():
            print('  %-36s %.4f / %.4f (%.3f)' % (key, row['right'], row['left'], row['right'] / row['left']))
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'reach.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')


def trials(args):
    out = OUT / args.rule
    M.check_provenance(out, '*.json')
    T.check_fields(out)
    config, session = v30_session()
    _, factors = install(session, args.rule)
    (out / 'factors.json').write_text(json.dumps(factors, indent=1) + '\n', encoding='utf-8')
    dt = float(config['sim']['tick_seconds'])
    for lv_ms in LV_MS:
        for name, azimuth in SIDES.items():
            path = out / ('lv%03d_%s.json' % (lv_ms, name))
            if path.exists():
                continue
            retinas, pre, t0, thetas = M.stimulus(lv_ms / 1000.0, azimuth, dt)
            last = pre + int(math.floor((t0 + M.WINDOW_AFTER_S) / dt + 1e-9)) - 1
            rows = []
            for seed in SEEDS:
                escapes = R.run_trial(session, retinas, seed)
                first = next((e for e in escapes if pre <= e[0] <= last), None)
                row = {'seed': seed, 'pre_stimulus_escapes': sum(1 for e in escapes if e[0] < pre),
                       'escaped': first is not None}
                if first is not None:
                    row.update({'tick': first[0], 't_before': t0 - (first[0] - pre + 1) * dt,
                                'theta_deg': math.degrees(thetas[first[0]])})
                rows.append(row)
            path.write_text(json.dumps({'lv_ms': lv_ms, 'side': name, 't0': t0, 'trials': rows}, indent=1)
                            + '\n', encoding='utf-8')
            print('%s lv %d ms %s: %d of %d escaped' % (args.rule, lv_ms, name,
                                                       sum(r['escaped'] for r in rows), len(rows)), flush=True)
    session.close()


def summary(_args):
    print('rule            l/v   right: escaped, median t_before, median theta | left: same')
    for rule in RULES:
        out = OUT / rule
        if not out.exists():
            continue
        for lv_ms in LV_MS:
            cells = []
            for name in SIDES:
                path = out / ('lv%03d_%s.json' % (lv_ms, name))
                if not path.exists():
                    cells.append('-')
                    continue
                rows = json.loads(path.read_text(encoding='utf-8'))['trials']
                hit = [r for r in rows if r['escaped']]
                cells.append('%2d/%d, %+6.0f ms, %5.1f deg' % (
                    len(hit), len(rows),
                    1000 * statistics.median(r['t_before'] for r in hit) if hit else float('nan'),
                    statistics.median(r['theta_deg'] for r in hit) if hit else float('nan')))
            print('%-15s %3d   %s | %s' % (rule, lv_ms, cells[0], cells[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('weights', 'reach', 'trials', 'summary'))
    parser.add_argument('--rule', choices=RULES)
    args = parser.parse_args()
    if args.mode == 'trials' and args.rule is None:
        parser.error('trials needs --rule')
    {'weights': weights, 'reach': reach, 'trials': trials, 'summary': summary}[args.mode](args)


if __name__ == '__main__':
    main()
