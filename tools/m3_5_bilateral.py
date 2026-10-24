"""M3.5 research: how much of the contralateral eye reaches each giant fiber (read-only).

Exploratory. No runtime file changes. Whole-cell recordings show that the giant fiber responds to
looms seen only by the contralateral eye as strongly and as fast as to ipsilateral ones, through
an unidentified commissural pathway (Jang et al. 2023, J Exp Biol 226:jeb244790).
game/M3_5_STRIKE_ESCAPE_RESEARCH.md (section 8) compares this with the frozen network:
- **paths.** The direct and two-hop weights from each eye's LPLC2 and LC4 onto each DNp01, and
  the intermediate cells that carry the contralateral two-hop weight. Weights come from
  data/weights.npz (rows postsynaptic).
- **drive.** A constant 0.8 V drive to 25, 50 or 100 % of one side's encoder cells of both types,
  and the synaptic input that each DNp01 then receives per tick (gain times the weights of the
  cells that fired), minus the same quantity without drive. The cell choice uses numpy seed
  960200; the network seeds are 960201-960212.

Outputs go to artifacts/m3_5/bilateral/ (git-ignored). Needs scipy, like
tools/m3_4_receptive_fields.py.

    python tools/m3_5_bilateral.py paths
    NUMBA_NUM_THREADS=1 python tools/m3_5_bilateral.py drive
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

import tools.m3_0_scorecard as M  # noqa: E402
import tools.m3_4_receptive_fields as RF  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/bilateral'
VISUAL = ('LPLC2', 'LC4')
FRACTIONS = (0.25, 0.5, 1.0)
AMOUNT = 0.8
SETTLE_TICKS = 30
DRIVE_TICKS = 6
CHOICE_SEED = 960200
NETWORK_SEEDS = tuple(range(960201, 960213))
CARRIERS = ('PVLP151', 'AMMC-A1', 'DNp11', 'GFC1', 'GFC2', 'GFC3', 'GFC4')


def other(side):
    return 'R' if side == 'L' else 'L'


def paths(_args):
    _, types, sides = RF.brain_arrays()
    W = RF.weights().tocsr()
    WT = W.T.tocsr()                      # rows presynaptic
    eye = {s: np.flatnonzero(np.isin(types, VISUAL) & (sides == s)) for s in 'LR'}
    gf = {s: int(np.flatnonzero((types == 'DNp01') & (sides == s))[0]) for s in 'LR'}
    out = {'dnp01': {}, 'carriers': {}}
    for s, g in gf.items():
        row = W[g]
        out['dnp01'][s] = {}
        for label, src_side in (('ipsilateral', s), ('contralateral', other(s))):
            src = eye[src_side]
            via = W[row.indices][:, src].sum(axis=1).A1 * row.data
            order = np.argsort(-via)[:6]
            out['dnp01'][s][label] = {
                'direct': float(row[:, src].sum()), 'two_hop': float(via.sum()),
                'top_carriers': [{'type': str(types[row.indices[k]]), 'side': str(sides[row.indices[k]]),
                                  'weight': float(via[k])} for k in order if via[k] > 0]}
            print('DNp01 %s from the %s eye: direct %.4f, two-hop %.5f via %s' % (
                s, label, out['dnp01'][s][label]['direct'], out['dnp01'][s][label]['two_hop'],
                ', '.join('%s %s %.5f' % (c['type'], c['side'], c['weight'])
                          for c in out['dnp01'][s][label]['top_carriers'][:4])))
    for t in CARRIERS:
        for s in 'LR':
            idx = np.flatnonzero((types == t) & (sides == s))
            if not len(idx):
                continue
            rows = W[idx]
            entry = {'cells': int(len(idx)),
                     'input_from': {'%s_%s' % (v, e): float(rows[:, np.flatnonzero((types == v) & (sides == e))].sum()
                                                            / len(idx)) for v in VISUAL for e in 'LR'},
                     'output_to_dnp01': {e: float(WT[idx][:, [gf[e]]].sum()) for e in 'LR'}}
            out['carriers']['%s_%s' % (t, s)] = entry
            print('%-8s %s n=%d | mean input from %s | to DNp01 L %.4f R %.4f' % (
                t, s, len(idx), ' '.join('%s %.3f' % kv for kv in entry['input_from'].items()),
                entry['output_to_dnp01']['L'], entry['output_to_dnp01']['R']))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'paths.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')


def drive(_args):
    M.check_provenance(OUT, 'drive.json')
    brain, _, cells = RF.encoder_cells()
    W = RF.weights().tocsr()
    gf = {s: int(brain.groups['escape_' + s][0]) for s in 'LR'}
    rows = {s: W[gf[s]].toarray().ravel() for s in 'LR'}
    rng = np.random.default_rng(CHOICE_SEED)
    result = {}
    for side in 'LR':
        pool = np.concatenate([cells['LPLC2'][side], cells['LC4'][side]])
        for fraction in FRACTIONS:
            gained = {'ipsilateral': [], 'contralateral': []}
            spikes = {'ipsilateral': 0, 'contralateral': 0}
            for seed in NETWORK_SEEDS:
                chosen = np.sort(rng.choice(pool, int(round(fraction * len(pool))), replace=False))
                per = {}
                for label, inject in (('drive', [(chosen, AMOUNT)]), ('none', [])):
                    brain.reset(seed)
                    for _ in range(SETTLE_TICKS):
                        brain.step()
                    per[label] = {'ipsilateral': [], 'contralateral': []}
                    for _ in range(DRIVE_TICKS):
                        fired = np.asarray(brain.step(inject=inject))
                        for rel, s in (('ipsilateral', side), ('contralateral', other(side))):
                            per[label][rel].append(brain.gain * rows[s][fired].sum())
                            if label == 'drive' and gf[s] in fired:
                                spikes[rel] += 1
                for rel in gained:
                    gained[rel].append(np.array(per['drive'][rel]) - np.array(per['none'][rel]))
            key = '%s_%.2f' % (side, fraction)
            result[key] = {rel: {'input_per_tick': [float(x) for x in np.mean(gained[rel], 0)],
                                 'input_mean': float(np.mean(gained[rel])),
                                 'spikes': spikes[rel], 'ticks': DRIVE_TICKS * len(NETWORK_SEEDS)}
                           for rel in gained}
            ipsi, contra = result[key]['ipsilateral'], result[key]['contralateral']
            print('drive %s %3.0f %%: input per tick ipsilateral DNp01 %+.3f (spikes %d/%d), contralateral '
                  '%+.3f (spikes %d/%d), ratio %.3f' % (
                      side, 100 * fraction, ipsi['input_mean'], ipsi['spikes'], ipsi['ticks'],
                      contra['input_mean'], contra['spikes'], contra['ticks'],
                      contra['input_mean'] / ipsi['input_mean']), flush=True)
    (OUT / 'drive.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('paths', 'drive'))
    args = parser.parse_args()
    {'paths': paths, 'drive': drive}[args.mode](args)


if __name__ == '__main__':
    main()
