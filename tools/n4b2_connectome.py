"""M1.8-N4B2 research: connectome characterization of candidate descending neurons.

Research only; reads the frozen MaleCNS graph and the encoder's chosen LC4/LPLC2 cells.
Nothing is changed and nothing here reaches a policy.

The candidate set is defined by a mechanistic rule fixed before the N4B2 activity
analysis (tools/n4b2_criteria.py, CANDIDATE_RULE): a DN type is a candidate when, on
BOTH sides, a full ipsilateral LC4 + LPLC2 volley of the encoder's chosen cells alone
delivers at least the rest-to-threshold margin (gain * direct weight >= 0.228 V). The
tool also reports two-hop drive through intermediates that such a volley can itself fire,
to check whether any DN without strong direct input deserves inclusion.

    python tools/n4b2_connectome.py     # writes artifacts/m1_8_n4b2/connectome.json
"""
from __future__ import annotations

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

from game.fly import build_brain  # noqa: E402
from game.perception import RetinalEncoder  # noqa: E402
from tools.n4b2_criteria import CANDIDATE_RULE, THRESHOLD_MARGIN  # noqa: E402
from tools.n4b2_record import encoder_cells, dn_panel  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b2'


def main():
    config = json.loads((ROOT / 'game_room_config.json').read_text(encoding='utf-8'))
    brain = build_brain(config, ROOT, warmup=False)
    encoder = RetinalEncoder(brain, config)
    gain = float(brain.gain)
    W = sparse.csc_matrix((brain.weights, brain.indices, brain.indptr),
                          shape=(brain.n, brain.n)).tocsr()          # W[post, pre]
    WT = W.T.tocsr()                                                  # WT[pre, post]
    ctype = np.array([str(t) for t in brain.cell_type])
    side = np.array([str(s) for s in brain.side])
    superclass = np.array([str(s) for s in brain.superclass])
    cells = encoder_cells(encoder)
    chosen = np.concatenate(list(cells.values()))
    dn = brain.cells(['descending_neuron'])
    is_dn = np.zeros(brain.n, bool)
    is_dn[dn] = True
    is_chosen = np.zeros(brain.n, bool)
    is_chosen[chosen] = True

    # One full volley of one side's chosen cells, as the encoder produces under saturation.
    volley = {}
    for s in 'LR':
        x = np.zeros(brain.n)
        x[cells['LPLC2_' + s]] = 1.0
        x[cells['LC4_' + s]] = 1.0
        volley[s] = x
    direct = {s: W @ volley[s] for s in 'LR'}            # summed weight each cell receives
    # Intermediates a volley alone can fire from rest (not DN, not a chosen encoder cell).
    driven = {s: np.flatnonzero((gain * direct[s] >= THRESHOLD_MARGIN) & ~is_dn & ~is_chosen)
              for s in 'LR'}
    two_hop = {}
    for s in 'LR':
        y = np.zeros(brain.n)
        y[driven[s]] = 1.0
        two_hop[s] = W @ y                                # weight from the driven intermediates

    panel, _, _ = dn_panel(brain, encoder)

    def cell_record(c):
        c = int(c)
        row = W[c]
        pre, w = row.indices, row.data
        per_source = {k: float(W[c][:, v].sum()) for k, v in cells.items()}
        ipsi = per_source['LPLC2_' + side[c]] + per_source['LC4_' + side[c]]
        exc, inh = float(w[w > 0].sum()), float(w[w < 0].sum())
        others = [(float(wj), int(j)) for j, wj in zip(pre, w) if not is_chosen[j]]
        others.sort(key=lambda t: -abs(t[0]))
        by_type = defaultdict(float)
        for wj, j in others:
            by_type[ctype[j] + '_' + side[j]] += wj
        top_inputs = sorted(by_type.items(), key=lambda t: -abs(t[1]))[:8]
        out_row = WT[c]
        post, wo = out_row.indices, out_row.data
        out_types = defaultdict(float)
        motor = defaultdict(float)
        for j, wj in zip(post, wo):
            out_types[ctype[j] + ' (' + superclass[j] + ')'] += wj
            if superclass[j] in ('vnc_motor', 'cb_motor'):
                motor[ctype[j]] += wj
        return {
            'cell': c, 'type': ctype[c], 'side': side[c],
            'direct_weight_by_source': {k: round(v, 4) for k, v in per_source.items()},
            'direct_ipsilateral_weight': round(ipsi, 4),
            'full_volley_voltage': round(gain * ipsi, 4),
            'full_volley_over_margin': round(gain * ipsi / THRESHOLD_MARGIN, 3),
            'two_hop_weight_from_driven_intermediates': round(float(two_hop[side[c]][c]), 4),
            'two_hop_voltage': round(gain * float(two_hop[side[c]][c]), 4),
            'total_excitatory_input_weight': round(exc, 4),
            'total_inhibitory_input_weight': round(inh, 4),
            'n_presynaptic': int(pre.size),
            'top_other_input_types': [[k, round(v, 4)] for k, v in top_inputs],
            'n_postsynaptic': int(post.size),
            'top_output_types': [[k, round(v, 4)] for k, v in
                                 sorted(out_types.items(), key=lambda t: -abs(t[1]))[:8]],
            'motor_neuron_outputs': [[k, round(v, 4)] for k, v in
                                     sorted(motor.items(), key=lambda t: -abs(t[1]))[:8]],
        }

    panel_records = [cell_record(c) for c in panel]
    by_type = defaultdict(dict)
    for r in panel_records:
        by_type[r['type']][r['side']] = r
    candidates = sorted(t for t, d in by_type.items()
                        if set(d) == {'L', 'R'} and all(d[s]['full_volley_voltage'] >= THRESHOLD_MARGIN
                                                        for s in 'LR'))
    excluded = sorted(set(by_type) - set(candidates))

    # Any DN without strong direct input but with two-hop drive above the margin?
    two_hop_dn = []
    for c in dn:
        # Midline cells ('M') are credited with the stronger of the two sides.
        s = side[c] if side[c] in ('L', 'R') else max('LR', key=lambda q: two_hop[q][c])
        v2 = gain * float(two_hop[s][c])
        v1 = gain * float(direct[s][c])
        two_hop_dn.append((v2, v1, int(c), ctype[c], side[c]))
    two_hop_dn.sort(reverse=True)

    out = {
        'candidate_rule': CANDIDATE_RULE, 'threshold_margin_v': THRESHOLD_MARGIN, 'gain': gain,
        'n_neurons': int(brain.n), 'n_descending': int(dn.size),
        'encoder_cells': {k: int(v.size) for k, v in cells.items()},
        'driven_intermediates_per_side': {s: int(driven[s].size) for s in 'LR'},
        'driven_intermediate_types': {s: Counter(ctype[driven[s]]).most_common(12) for s in 'LR'},
        'panel': panel_records,
        'candidate_types': candidates,
        'excluded_panel_types': excluded,
        'top_two_hop_dn': [{'two_hop_voltage': round(a, 4), 'direct_voltage': round(b, 4),
                            'cell': c, 'type': t, 'side': s} for a, b, c, t, s in two_hop_dn[:15]],
        'max_two_hop_voltage_any_dn': round(two_hop_dn[0][0], 4),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'connectome.json').write_text(json.dumps(out, indent=1, default=float) + '\n', encoding='utf-8')

    print('driven intermediates per side:', out['driven_intermediates_per_side'])
    print('candidate types:', candidates)
    print('excluded panel types:', excluded)
    print('%-9s %s %8s %8s %8s %8s %8s  %s' % ('type', 's', 'ipsi_w', 'volleyV', 'xmargin', '2hopV',
                                             'inh_w', 'motor outputs'))
    for r in sorted(panel_records, key=lambda r: (-max(by_type[r['type']][s]['direct_ipsilateral_weight']
                                                       for s in by_type[r['type']]), r['side'])):
        print('%-9s %s %8.3f %8.3f %8.2f %8.3f %8.3f  %s' % (
            r['type'], r['side'], r['direct_ipsilateral_weight'], r['full_volley_voltage'],
            r['full_volley_over_margin'], r['two_hop_voltage'], r['total_inhibitory_input_weight'],
            r['motor_neuron_outputs'][:3]))
    print('top two-hop DNs:')
    for r in out['top_two_hop_dn'][:10]:
        print('  ', r)


if __name__ == '__main__':
    main()
