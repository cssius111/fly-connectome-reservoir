"""M3.5 research: functional receptive fields of LPLC2 and LC4 from their inputs' spread (read-only).

Exploratory. No runtime file changes. game/M3_5_STRIKE_ESCAPE_RESEARCH.md (section 5) traced the
late v30 decisions to recruitment: the M3.4 encoder drives each cell through its dendritic
columns only, while LPLC2's functional field reaches 60° (Klapoetke et al. 2017).

A cell's functional field is its dendritic column map blurred by the spatial spread of the
columnar cells that feed it. This tool measures that spread in MaleCNS itself:
- **Per input cell.** For a sample of right-side cells of each main input type (T4a-d and T5a-d
  for LPLC2; T2, TmY3, Tm4, Tm2 and Tm3 for LC4; Tm5f and Tm20 for both), it takes the optic
  columns of the cell's own input synapses in the right optic lobe and maps them to viewing
  directions through the eye map of tools/m3_4_receptive_fields.py.
- **Spread.** The angular distances of those synapses from the cell's weighted centre give its
  spread. sigma is the RMS distance divided by sqrt(2), the per-axis width of an isotropic
  Gaussian.
- **Kernel.** The kernel of each target type is the input-weight-weighted mean sigma of its input
  types (weights from data/weights.npz).
- **Fields.** `fields` reports the functional r95 of LPLC2 and LC4: each cell's columns blurred by
  that kernel and by the 7.7° photoreceptor acceptance.

Seeds: the cell sample uses numpy seed 950900. Outputs go to artifacts/m3_5/functional/
(git-ignored). Needs the same extra dependencies as tools/m3_4_receptive_fields.py.

    python tools/m3_5_functional_fields.py kernels --eyemap ../eyemap_T4
    python tools/m3_5_functional_fields.py fields --eyemap ../eyemap_T4
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.m3_4_receptive_fields as RF  # noqa: E402

OUT = ROOT / 'artifacts/m3_5/functional'
INPUT_TYPES = {'LPLC2': ('T4a', 'T4b', 'T4c', 'T4d', 'T5a', 'T5b', 'T5c', 'T5d', 'Tm5f', 'Tm20'),
               'LC4': ('T2', 'TmY3', 'Tm4', 'Tm2', 'Tm3', 'Tm5f', 'Tm20')}
SAMPLE = 30
OPTIC_ROIS_R = ('ME(R)', 'LO(R)', 'LOP(R)')


def cell_spread(rec, roi_codes, eye):
    m = np.isin(rec['primary_roi'], roi_codes) & (rec['optic_column'] > 0)
    codes, counts = np.unique(rec['optic_column'][m].astype(int), return_counts=True)
    if counts.sum() < 20:
        return None
    dirs = np.array([eye.column(c, 'R')[0] for c in codes])
    w = counts / counts.sum()
    centre = (dirs * w[:, None]).sum(0)
    centre /= np.linalg.norm(centre)
    ang = np.degrees(np.arccos(np.clip(dirs @ centre, -1, 1)))
    return {'synapses': int(counts.sum()), 'columns': int(len(codes)),
            'sigma_deg': float(math.sqrt((w * ang ** 2).sum() / 2.0)),
            'r50_deg': float(np.interp(0.5, np.cumsum(w[np.argsort(ang)]), np.sort(ang)))}


def kernels(args):
    import scipy.sparse as sp
    eye = RF.EyeMap(args.eyemap)
    ids, types, sides = RF.brain_arrays()
    syn = RF.AnnotationLayer('synapses')
    roi = syn.enum('primary_roi')
    codes = [roi[name] for name in OPTIC_ROIS_R]
    rng = np.random.default_rng(950900)
    per_type = {}
    for t in sorted(set(sum(INPUT_TYPES.values(), ()))):
        pool = np.flatnonzero((types == t) & (sides == 'R'))
        chosen = rng.choice(pool, min(SAMPLE, len(pool)), replace=False)
        with ThreadPoolExecutor(8) as ex:
            recs = list(ex.map(lambda i: syn.related('body_post', int(ids[i])), chosen))
        cells = [s for s in (cell_spread(r, codes, eye) for r in recs) if s is not None]
        sig = np.array([c['sigma_deg'] for c in cells])
        per_type[t] = {'cells': len(cells), 'sigma_deg_median': float(np.median(sig)),
                       'sigma_deg_iqr': [float(x) for x in np.percentile(sig, [25, 75])],
                       'columns_median': float(np.median([c['columns'] for c in cells]))}
        print('%-5s n %2d  sigma median %.2f deg (IQR %.2f-%.2f)  columns %.0f' % (
            t, len(cells), per_type[t]['sigma_deg_median'], *per_type[t]['sigma_deg_iqr'],
            per_type[t]['columns_median']), flush=True)
    w = np.load(ROOT / 'data/weights.npz')
    W = sp.csr_matrix((w['data'], w['indices'], w['indptr']), shape=tuple(w['shape']))
    out = {'per_type': per_type, 'kernel': {}}
    for target, inputs in INPUT_TYPES.items():
        rows = W[np.flatnonzero((types == target) & (sides == 'R'))]
        share = {t: float(rows[:, np.flatnonzero((types == t) & (sides == 'R'))].sum()) for t in inputs}
        total = sum(share.values())
        sigma = sum(share[t] * per_type[t]['sigma_deg_median'] for t in inputs) / total
        out['kernel'][target] = {'sigma_deg': sigma, 'input_share': share}
        print('%s kernel: sigma %.2f deg from %s' % (target, sigma, ', '.join(
            '%s %.3f' % (t, share[t]) for t in inputs)))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'kernels.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')


def fields(args):
    eye = RF.EyeMap(args.eyemap)
    k = json.loads((OUT / 'kernels.json').read_text(encoding='utf-8'))['kernel']
    data = RF.load_fields()
    optics = RF.ACCEPTANCE_SIGMA_DEG
    rng = np.random.default_rng(950901)
    for t in RF.TYPES:
        sigma = math.sqrt(optics ** 2 + k[t]['sigma_deg'] ** 2)
        r95 = {'dendritic': [], 'optics': [], 'functional': []}
        for c in data[t]:
            dirs = np.array([eye.column(code, c['side'])[0] for code in c['column_codes']])
            w = np.array(c['column_counts'], float)
            w /= w.sum()
            centre = (dirs * w[:, None]).sum(0)
            centre /= np.linalg.norm(centre)
            for label, s in (('dendritic', 0.0), ('optics', optics), ('functional', sigma)):
                # Monte Carlo: columns drawn by weight, each blurred by an isotropic Gaussian of s deg.
                pick = rng.choice(len(w), 4000, p=w)
                d = dirs[pick] + np.radians(s) * rng.standard_normal((4000, 3))
                d /= np.linalg.norm(d, axis=1, keepdims=True)
                r95[label].append(np.percentile(np.degrees(np.arccos(np.clip(d @ centre, -1, 1))), 95))
        print('%s: kernel sigma %.2f deg, total sigma %.2f deg (FWHM %.1f deg) | median r95: dendritic %.1f, '
              '+optics %.1f, functional %.1f deg (diameter %.0f deg)' % (
                  t, k[t]['sigma_deg'], sigma, 2.3548 * sigma, np.median(r95['dendritic']),
                  np.median(r95['optics']), np.median(r95['functional']), 2 * np.median(r95['functional'])))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('kernels', 'fields'))
    parser.add_argument('--eyemap', required=True)
    args = parser.parse_args()
    {'kernels': kernels, 'fields': fields}[args.mode](args)


if __name__ == '__main__':
    main()
