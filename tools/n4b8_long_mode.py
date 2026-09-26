"""M1.8-N4B8: biological long-mode escape pathway feasibility (research only).

No runtime code, configuration, decoder, whitelist, Retina / encoder equation, MaleCNS
parameter, brain noise, physics, controller, geometry or lifecycle is changed. The accepted
runtime (M1.8-N4B5R @ 363a1a9) is imported read-only from its worktree, which must stay
clean. The candidate set and measurement plan are frozen in `tools/n4b8_candidates.py`
before any N4B8 simulation; every simulation mode refuses to run if it changed. Spikes are
only observed (the brain step is wrapped to record which cells fired); nothing is injected.

    python tools/n4b8_long_mode.py connectome
    python tools/n4b8_long_mode.py freeze
    python tools/n4b8_long_mode.py controlled --worker K --workers 6
    python tools/n4b8_long_mode.py n1
    python tools/n4b8_long_mode.py room --worker K --workers 4
    python tools/n4b8_long_mode.py human
    python tools/n4b8_long_mode.py analyze

Outputs go to artifacts/m1_8_n4b8/ (git-ignored).
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'artifacts/m1_8_n4b8'
PREREG = OUT / 'preregistration.json'
CAND_FILE = ROOT / 'tools/n4b8_candidates.py'
DT = 0.02
PARKED = (1920.0, 388.8)


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode')
    p.add_argument('--worker', type=int, default=0)
    p.add_argument('--workers', type=int, default=1)
    return p.parse_args()


ARGS = _args() if __name__ == '__main__' else None
os.environ.setdefault('NUMBA_NUM_THREADS', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = load_module('n4b8_candidates', CAND_FILE)
N6 = load_module('n4b6_controlled_approach', ROOT / 'tools/n4b6_controlled_approach.py')
N7 = load_module('n4b7_long_readout', ROOT / 'tools/n4b7_long_readout.py')
P6 = N6.P
RUNTIME = N6.RUNTIME
TYPES = list(C.CANDIDATES)


def runtime():
    N7.runtime()


def write(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, indent=1, default=float) + '\n', encoding='utf-8')


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def check_frozen():
    if not PREREG.exists():
        raise SystemExit('run `freeze` first')
    reg = json.loads(PREREG.read_text(encoding='utf-8'))
    if sha256(CAND_FILE) != reg['candidates_sha256']:
        raise SystemExit('tools/n4b8_candidates.py changed after the freeze')
    return reg


def cell_table(brain):
    ct = np.array([str(t) for t in brain.cell_type])
    sd = np.array([str(s) for s in brain.side])
    cells = {}
    for t in TYPES:
        for s in 'LR':
            idx = np.flatnonzero((ct == t) & (sd == s))
            if idx.size != 1:
                raise RuntimeError('%s %s: expected one cell, found %d' % (t, s, idx.size))
            cells['%s_%s' % (t, s)] = int(idx[0])
    return cells


CELL_KEYS = ['%s_%s' % (t, s) for t in TYPES for s in 'LR']


class SpikeTap:
    """Wraps brain.step to record which candidate cells fired (observation only)."""

    def __init__(self, brain):
        self.brain, self.orig = brain, brain.step
        cells = cell_table(brain)
        self.ids = np.array([cells[k] for k in CELL_KEYS])
        self.rows = []
        brain.step = self.step

    def step(self, *a, **k):
        fired = self.orig(*a, **k)
        self.rows.append(np.isin(self.ids, np.asarray(fired)))
        return fired

    def take(self):
        out = np.array(self.rows, dtype=bool).reshape(-1, len(CELL_KEYS))
        self.rows = []
        return out


# ================================================================== connectome ===
def connectome():
    runtime()
    from scipy import sparse
    from game.fly import build_brain
    from game.perception import RetinalEncoder
    config = N7.room_config()
    brain = build_brain(config, RUNTIME, warmup=False)
    encoder = RetinalEncoder(brain, config)
    gain = float(brain.gain)
    margin = 0.228
    W = sparse.csc_matrix((brain.weights, brain.indices, brain.indptr), shape=(brain.n, brain.n)).tocsr()   # W[post, pre]
    ct = np.array([str(t) for t in brain.cell_type])
    sd = np.array([str(s) for s in brain.side])
    sc = np.array([str(s) for s in brain.superclass])
    chosen = {'%s_%s' % (lab, s): np.asarray(encoder._fd.cells[ch][s]) for ch, lab in (('loom', 'LPLC2'), ('threat', 'LC4')) for s in 'LR'}
    driven = np.concatenate(list(chosen.values()))
    is_driven = np.zeros(brain.n, bool)
    is_driven[driven] = True
    cells = cell_table(brain)
    vpn = sc == 'visual_projection'
    res = {'gain': gain, 'margin_v': margin, 'n_neurons': int(brain.n),
           'encoder_driven_cells': {k: int(v.size) for k, v in chosen.items()},
           'modelled_visual_input': 'only the encoder-chosen LC4 and LPLC2 cells are driven (sensory_input=False); '
                                    'every other visual projection neuron receives no visual drive', 'cells': {}}
    # One-hop driven intermediates: cells a full ipsilateral volley can fire from rest.
    vol = {s: np.zeros(brain.n) for s in 'LR'}
    for s in 'LR':
        vol[s][chosen['LPLC2_' + s]] = 1.0
        vol[s][chosen['LC4_' + s]] = 1.0
    direct_all = {s: W @ vol[s] for s in 'LR'}
    for key, c in cells.items():
        t, s = key.split('_')
        row = W[c]
        pre, w = row.indices, row.data
        by_type = Counter()
        for p, x in zip(pre, w):
            by_type[ct[p]] += float(x)
        vpn_in = {k: v for k, v in by_type.items() if k and np.any(vpn[ct == k])}
        exc, inh = float(w[w > 0].sum()), float(w[w < 0].sum())
        per = {k: float(W[c][:, v].sum()) for k, v in chosen.items()}
        all_lc = {'%s_%s' % (typ, side): float(sum(x for p, x in zip(pre, w) if ct[p] == typ and sd[p] == side))
                  for typ in ('LC4', 'LPLC2') for side in 'LR'}
        ipsi = per['LC4_' + s] + per['LPLC2_' + s]
        contra = per['LC4_' + ('R' if s == 'L' else 'L')] + per['LPLC2_' + ('R' if s == 'L' else 'L')]
        # Two-hop: intermediates (not driven encoder cells) receiving driven input and projecting to c.
        inter = []
        for p, x in zip(pre, w):
            if is_driven[p]:
                continue
            fin = float(direct_all[s][p])
            if abs(fin) > 1e-6:
                inter.append((abs(fin * x), str(ct[p]), str(sd[p]), round(fin, 4), round(float(x), 4),
                              bool(gain * fin >= margin)))
        inter.sort(reverse=True)
        driven_vpn = sum(v for k, v in vpn_in.items() if k in ('LC4', 'LPLC2'))
        total_vpn = sum(v for v in vpn_in.values() if v > 0)
        res['cells'][key] = {
            'cell': c, 'type': t, 'side': s, 'n_presynaptic': int(pre.size),
            'total_excitatory_weight': exc, 'total_inhibitory_weight': inh,
            'direct_from_encoder_cells': per, 'direct_from_all_LC4_LPLC2': all_lc,
            'ipsilateral_driven_weight': ipsi, 'contralateral_driven_weight': contra,
            'ipsilateral_full_volley_voltage': gain * ipsi, 'full_volley_over_margin': gain * ipsi / margin,
            'vpn_input_by_type': dict(sorted(vpn_in.items(), key=lambda kv: -abs(kv[1]))[:12]),
            'fraction_of_excitatory_vpn_input_from_modelled_types': (driven_vpn / total_vpn) if total_vpn > 0 else None,
            'top_input_types': sorted(((k, round(v, 4)) for k, v in by_type.items()), key=lambda kv: -abs(kv[1]))[:10],
            'top_two_hop_paths': [{'via': a, 'via_side': b, 'driven_input_to_via': d, 'via_to_cell': e,
                                   'via_fires_from_volley': f} for _, a, b, d, e, f in inter[:6]]}
    write('connectome.json', res)
    for k, v in res['cells'].items():
        print('%-9s ipsi %.3f (x%.2f margin) contra %.3f exc %.2f inh %.2f modelled-VPN share %s top VPN %s' % (
            k, v['ipsilateral_driven_weight'], v['full_volley_over_margin'], v['contralateral_driven_weight'],
            v['total_excitatory_weight'], v['total_inhibitory_weight'],
            None if v['fraction_of_excitatory_vpn_input_from_modelled_types'] is None else round(v['fraction_of_excitatory_vpn_input_from_modelled_types'], 2),
            list(v['vpn_input_by_type'].items())[:4]))


# ================================================================== freeze ===
def freeze():
    if PREREG.exists():
        raise SystemExit('already frozen')
    reg = {'label': 'M1.8-N4B8 frozen candidate set and measurement plan (research only)',
           'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'frozen_before_any_n4b8_simulation': True,
           'candidates_sha256': sha256(CAND_FILE), 'runner_sha256_at_freeze': sha256(Path(__file__)),
           'n4b6_protocol_sha256': sha256(N6.PROTOCOL_FILE), 'runtime_commit': N6.RUNTIME_COMMIT,
           'candidates': C.CANDIDATES, 'excluded': C.EXCLUDED, 'data': C.DATA, 'metrics': C.METRICS,
           'outcome_rule': C.OUTCOME_RULE,
           'connectome_sha256': sha256(OUT / 'connectome.json') if (OUT / 'connectome.json').exists() else None}
    write('preregistration.json', reg)
    print('frozen', reg['candidates_sha256'])


# ================================================================== controlled + mirror ===
MIRRORS = {'M_A2_self_approach_130': 'A2_frontal_slow', 'M_B1_self_approach_300': 'B1_frontal_medium'}


def controlled():
    check_frozen()
    session, policy, config = N6.make_session()
    tap = SpikeTap(session.brain)
    mine = [s for i, s in enumerate(P6.SEEDS) if i % ARGS.workers == ARGS.worker]
    t0 = time.time()
    for tid in list(P6.MATRIX) + list(MIRRORS):
        d = OUT / 'controlled' / tid
        d.mkdir(parents=True, exist_ok=True)
        mirror = tid in MIRRORS
        src = MIRRORS.get(tid, tid)
        offs, path, marks = N6.pointer_path(src)
        ref_geo = np.load(ROOT / 'artifacts/m1_8_n4b6' / ('geometry_%s.npy' % src)) if mirror else None
        for seed in mine:
            f = d / ('%d.npz' % seed)
            if f.exists():
                continue
            session.reset(seed)
            N6.place(session, offs)
            w = session.world
            if mirror:
                # Park the paddle where the approach started; move the fly instead.
                sw = w.swatter
                park = (sw.x, sw.y)
            policy.reset()
            tap.take()
            geo, ret, sens = [], [], []
            for k, (ox, oy) in enumerate(path):
                if mirror:
                    rx, ry = ref_geo[k, 0] - P6.FLY_POSE[0], ref_geo[k, 1] - P6.FLY_POSE[1]
                    w.fly.x, w.fly.y = park[0] - rx, park[1] - ry
                    w.swatter.orientation = float(ref_geo[k, 4])
                    w.swatter.angular_velocity = 0.0
                    pointer = park
                else:
                    pointer = (P6.FLY_POSE[0] + ox, P6.FLY_POSE[1] + oy)
                geo.append(N6.geometry_row(w)[:9] + (w.fly.x, w.fly.y))
                session.tick(pointer=pointer, strike=False)
                r = session.last_retina
                ret.append((r.theta, r.theta_dot, r.azimuth))
                s = session.fly_loop.last_sensory_spikes
                sens.append((s['LPLC2_left'] + s['LC4_left'], s['LPLC2_right'] + s['LC4_right']))
                if 'approach' not in str(w.swatter.phase).lower():
                    raise RuntimeError('strike phase entered')
                if mirror and math.hypot(w.swatter.x - park[0], w.swatter.y - park[1]) > 1e-6:
                    raise RuntimeError('parked paddle moved in the mirror')
            np.savez_compressed(f, geo=np.array(geo), retina=np.array(ret), sensory=np.array(sens, np.int32),
                                spikes=tap.take(), dnp01_trace=np.array([(m.dnp01_left, m.dnp01_right) for m in policy.history]))
        print('worker %d %s done (%.0f s)' % (ARGS.worker, tid, time.time() - t0), flush=True)
    session.close()


# ================================================================== N1 ===
def n1():
    check_frozen()
    runtime()
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy
    from tools.loom_robustness_study import run_trial, DT as LDT
    config = N7.room_config()
    settle = max(40, round(config['swatter'].get('physical', {}).get('calibration_settle_seconds', 0.8) / LDT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=RUNTIME, ecology_enabled=False)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    tap = SpikeTap(session.brain)
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + 991)
    out = []
    for ci, kind in enumerate(('strong_direct', 'medium_committed')):
        for i in range(60):
            tap.take()
            t = run_trial(session, policy, 6000 + ci * 1000 + i, kind, rng, settle)
            spk = tap.take()[-t['ticks']:]
            out.append({'kind': kind, 'click': t['click_tick'], 'spikes': spk.astype(int).tolist(),
                        'azimuth': t['azimuth'].tolist()})
    session.close()
    write('n1.json', out)
    print('n1 done', len(out))


# ================================================================== free flight ===
def room():
    check_frozen()
    runtime()
    from game.session import Session
    if os.environ['NUMBA_NUM_THREADS'] != '1':
        raise SystemExit('ROOM runs require NUMBA_NUM_THREADS=1')
    seeds = list(range(7601, 7641))
    mine = [s for i, s in enumerate(seeds) if i % ARGS.workers == ARGS.worker]
    d = OUT / 'room'
    d.mkdir(parents=True, exist_ok=True)
    for seed in mine:
        f = d / ('%d.npz' % seed)
        if f.exists():
            continue
        policy = N7.C.make_policy(N7.room_config(), None, 'n4b1c', RUNTIME)
        s = Session(N7.room_config(), policy=policy, seed=seed, mode='evaluation', root=RUNTIME)
        tap = SpikeTap(s.brain)
        rows = []
        for t in range(9000):
            s.tick(pointer=PARKED, strike=False)
            m, fly, sw, r = s.fly_loop.last_motor, s.world.fly, s.world.swatter, s.last_retina
            dd = s.encoder.last_drive or {}
            sp = s.fly_loop.last_sensory_spikes
            rows.append((r.theta, r.theta_dot, r.azimuth, sum(dd.get(x, 0.0) for x in ('loomL', 'loomR', 'threatL', 'threatR')),
                         m.dnp01_left, m.dnp01_right, fly.x, fly.y, fly.vx, fly.vy, sw.x, sw.y, sw.height, sw.vx, sw.vy,
                         float(bool(s.fly_loop.last_action.escape)),
                         float(bool(s.world.lifecycle is not None and not s.world.lifecycle.stationary)),
                         sp['LPLC2_left'] + sp['LC4_left'], sp['LPLC2_right'] + sp['LC4_right']))
        s.close()
        spk = tap.take()
        ref = json.loads((ROOT / 'artifacts/m1_8_n4b7/hold_room' / ('%d.json' % seed)).read_text(encoding='utf-8'))['N4B1C']['rows']
        a = np.array(rows)
        exact = bool(np.array_equal(a[:, 4], np.array(ref['dl'])) and np.array_equal(a[:, 5], np.array(ref['dr'])))
        np.savez_compressed(f, rows=a, spikes=spk, dnp01_equal_to_n4b7_reference=np.array(exact))
        print('worker %d seed %d done; DNp01 identical to N4B7 reference: %s' % (ARGS.worker, seed, exact), flush=True)


# ================================================================== human ===
def human():
    check_frozen()
    runtime()
    from game.fly import build_brain
    from game.perception import Retina, RetinalEncoder
    from game.world import World
    windows = N7.human_windows()
    out = {}
    for sess, name in N7.SESSIONS.items():
        path = ROOT / 'results/game/sessions' / name
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        config = copy.deepcopy(manifest['config'])
        config['swatter']['directional']['tilt_geometry'] = 'elevation_aware_tilt_v1'
        w = World(config, 1)
        brain = build_brain(config, RUNTIME)
        encoder = RetinalEncoder(brain, config)
        tap = SpikeTap(brain)
        seeds = {json.loads(l)['episode']: json.loads(l)['seed'] for l in (path / 'episodes.jsonl').open(encoding='utf-8')}
        eps = {}
        for l in (path / 'ticks.jsonl').open(encoding='utf-8'):
            r = json.loads(l)
            eps.setdefault(r['episode'], []).append(r)

        def theta_of(row):
            f, s = row['fly'], row['swatter']
            w.fly.x, w.fly.y = f['x'], f['y']
            sw = w.swatter
            sw.x, sw.y, sw.height, sw.face, sw.orientation = s['x'], s['y'], s['height'], s['face'], s['orientation']
            rng = math.sqrt((s['x'] - f['x']) ** 2 + (s['y'] - f['y']) ** 2 + s['height'] ** 2)
            return 2.0 * math.atan(w.visual_half_size / max(rng, 1e-6))
        sess_out = {}
        for ep, er in eps.items():
            brain.reset(int(seeds[ep]) + 977)
            tap.take()
            thetas = [er[0]['retina']['theta']] + [theta_of(er[i - 1]) for i in range(1, len(er))]
            ticks, az = [], []
            for i, r in enumerate(er):
                if not r['neural']['brain_stepped']:
                    continue
                td = 0.0 if i == 0 else (thetas[i] - thetas[i - 1]) / DT
                brain.step(inject=encoder.inject(Retina(thetas[i], td, r['retina']['azimuth'])))
                ticks.append(r['tick'])
                az.append(r['retina']['azimuth'])
            sess_out[str(ep)] = {'ticks': ticks, 'azimuth': az, 'spikes': tap.take().astype(int).tolist()}
        out[sess] = sess_out
    write('human.json', {'windows': windows, 'sessions': out})
    print('human done')


# ================================================================== analysis ===
def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not pos.size or not neg.size:
        return None
    from scipy.stats import mannwhitneyu
    return float(mannwhitneyu(pos, neg, alternative='two-sided').statistic / (pos.size * neg.size))


def count_ipsi(spk, t_end, side, t0=None):
    a = max(0, t_end - C.WINDOW + 1) if t0 is None else t0
    return spk[a:t_end + 1, side].sum(0)


def side_cols(side):
    """Column indices of all candidate types on one side (0 = L, 1 = R)."""
    return [2 * i + side for i in range(len(TYPES))]


def controlled_windows(tid):
    """Per trial: ipsilateral 1 s counts per type at the analysis window, plus baseline windows."""
    rows = []
    for f in sorted((OUT / 'controlled' / tid).glob('*.npz')):
        z = np.load(f)
        spk, geo, ret = z['spikes'], z['geo'], z['retina']
        on = P6.PRE_HOLD_TICKS
        src = MIRRORS.get(tid, tid)
        role = P6.MATRIX[src]['role']
        if role in ('approach', 'abort'):
            c = N6.closest_tick(geo[:, 6], on)
            t_end = c - C.MARGIN
        elif src == 'F3_orbit_constant_range':
            t_end = on + P6.script(P6.MATRIX[src]['geometry'])[1] + C.WINDOW - 1
        else:
            t_end = on + 3 * C.WINDOW - 1
        side = int(ret[t_end, 2] >= 0.0)
        cnt = spk[t_end - C.WINDOW + 1:t_end + 1][:, side_cols(side)].sum(0)
        base = [spk[50:100][:, side_cols(sd)].sum(0) for sd in (0, 1)]
        base15 = [spk[85:100][:, side_cols(sd)].sum(0) for sd in (0, 1)]
        rows.append({'seed': int(f.stem), 'count': cnt, 'baseline': base, 'baseline15': base15, 'side': side,
                     'sensory': int(z['sensory'][t_end - C.WINDOW + 1:t_end + 1, side].sum()),
                     'retina': ret, 'spikes': spk})
    return rows


def analyze():
    check_frozen()
    res = {'types': TYPES}
    # --- controlled
    base, base15 = [], []
    ctl = {}
    for tid in list(P6.MATRIX) + list(MIRRORS):
        rows = controlled_windows(tid)
        ctl[tid] = rows
        base += [b for r in rows for b in r['baseline']]
        base15 += [b for r in rows for b in r['baseline15']]
    base15 = np.array(base15)
    base = np.array(base)                                   # baseline 1 s windows, per type
    res['baseline_rate_hz'] = {t: float(base[:, i].mean()) for i, t in enumerate(TYPES)}
    res['controlled'] = {}
    for tid, rows in ctl.items():
        cnt = np.array([r['count'] for r in rows])
        res['controlled'][tid] = {t: {'median_count': float(np.median(cnt[:, i])), 'mean_count': float(cnt[:, i].mean()),
                                      'auc_vs_stationary_baseline': auc(cnt[:, i], base[:, i])}
                                  for i, t in enumerate(TYPES)}
        res['controlled'][tid]['_sensory_median'] = float(np.median([r['sensory'] for r in rows]))
    # --- DNp01 / DNp04 identity with stored N4B6 records, and the mirror test
    ident = {}
    for tid in P6.MATRIX:
        eq = 0
        for r in ctl[tid]:
            z6 = np.load(ROOT / 'artifacts/m1_8_n4b6/trials' / tid / ('%d.npz' % r['seed']))
            s6 = z6['spikes']
            mine = r['spikes'][:, [TYPES.index('DNp01') * 2, TYPES.index('DNp01') * 2 + 1, TYPES.index('DNp04') * 2, TYPES.index('DNp04') * 2 + 1]]
            eq += bool(np.array_equal(mine.astype(np.uint8), s6))
        ident[tid] = [eq, len(ctl[tid])]
    res['n4b6_dnp01_dnp04_reproduced'] = ident
    mirror = {}
    for m, src in MIRRORS.items():
        dr, sp_eq = [], 0
        for rm, rs in zip(ctl[m], ctl[src]):
            assert rm['seed'] == rs['seed']
            dr.append(float(np.max(np.abs(rm['retina'] - rs['retina']))))
            sp_eq += bool(np.array_equal(rm['spikes'], rs['spikes']))
        cm = np.array([r['count'] for r in ctl[m]])
        cs = np.array([r['count'] for r in ctl[src]])
        mirror[m] = {'source': src, 'max_abs_retina_difference': max(dr), 'trials_with_identical_candidate_spikes': [sp_eq, len(dr)],
                     'auc_external_vs_self_by_type': {t: auc(cs[:, i], cm[:, i]) for i, t in enumerate(TYPES)}}
    res['mirror'] = mirror
    # --- N1
    n1d = read('n1.json')
    res['n1'] = {}
    for kind in ('strong_direct', 'medium_committed'):
        tr = [t for t in n1d if t['kind'] == kind]
        res['n1'][kind] = {}
        for i, t_ in enumerate(TYPES):
            lat, cnts = [], []
            for t in tr:
                spk = np.array(t['spikes'])
                side = int(t['azimuth'][t['click']] >= 0.0)
                col = 2 * i + side
                k = np.flatnonzero(spk[t['click']:, col])
                lat.append(None if not k.size else k[0] * DT)
                cnts.append(int(spk[t['click']:t['click'] + 15, col].sum()))
            got = [x for x in lat if x is not None]
            res['n1'][kind][t_] = {'fired': len(got), 'n': len(tr), 'median_first_spike_s': float(np.median(got)) if got else None,
                                   'within_0_2s': sum(1 for x in got if x <= 0.2) / len(tr),
                                   'mean_count_0_3s': float(np.mean(cnts)),
                                   'auc_count_0_3s_vs_baseline': auc(cnts, base15[:, i])}
    # --- free flight
    slow = [r for tid in C.SLOW_130 for r in ctl[tid]]
    ext = np.array([r['count'] for r in slow])
    levels = {}
    for i, t in enumerate(TYPES):
        v = np.sort(ext[:, i])[::-1]
        levels[t] = {'L50': int(v[int(np.ceil(0.5 * len(v))) - 1]), 'L90': int(v[int(np.ceil(0.9 * len(v))) - 1])}
    files = sorted((OUT / 'room').glob('*.npz'))
    minutes = 0.0
    episodes = {t: {'L50': 0, 'L90': 0} for t in TYPES}
    self_counts = {t: [] for t in TYPES}
    rate = {t: [] for t in TYPES}
    exact = 0
    for f in files:
        z = np.load(f)
        a, spk = z['rows'], z['spikes']
        exact += bool(z['dnp01_equal_to_n4b7_reference'])
        n = len(a)
        minutes += n * DT / 60
        for i, t in enumerate(TYPES):
            rate[t].append(spk[:, 2 * i:2 * i + 2].sum() / (n * DT) / 2)
            for sd in (0, 1):
                c = np.convolve(spk[:, 2 * i + sd].astype(int), np.ones(C.WINDOW, int))[:n]
                for lev in ('L50', 'L90'):
                    L = levels[t][lev]
                    above = np.flatnonzero(c >= max(L, 1))
                    if above.size:
                        episodes[t][lev] += 1 + int(np.sum(np.diff(above) > C.WINDOW))
        # self-approach windows (fly airborne, paddle parked; matched Retina band)
        fx, fy, fvx, fvy, px, py, ph, pvx, pvy = (a[:, k] for k in range(6, 15))
        dh = np.hypot(px - fx, py - fy)
        rng = np.sqrt(dh ** 2 + ph ** 2)
        rr = -((px - fx) * (fvx - pvx) + (py - fy) * (fvy - pvy)) / rng
        td_mean = np.convolve(a[:, 1], np.ones(C.WINDOW) / C.WINDOW)[:n]
        lo, hi = C.SELF_APPROACH['theta_dot_band']
        ok = ((rr <= C.SELF_APPROACH['range_rate_max']) & (dh >= C.SELF_APPROACH['horizontal_min'])
              & (dh <= C.SELF_APPROACH['horizontal_max']) & (td_mean >= lo) & (td_mean <= hi) & (a[:, 16] > 0.5))
        ok[:C.WINDOW] = False
        last = -10 ** 9
        for t_end in np.flatnonzero(ok):
            if t_end - last < C.WINDOW:
                continue
            last = t_end
            side = int(a[t_end, 2] >= 0.0)
            cnt = spk[t_end - C.WINDOW + 1:t_end + 1][:, side_cols(side)].sum(0)
            for i, t in enumerate(TYPES):
                self_counts[t].append(int(cnt[i]))
    res['free_flight'] = {'runs': len(files), 'minutes': minutes, 'dnp01_identical_runs': exact,
                          'self_approach_windows': len(self_counts[TYPES[0]]), 'by_type': {}}
    for i, t in enumerate(TYPES):
        res['free_flight']['by_type'][t] = {
            'mean_rate_hz_per_cell': float(np.mean(rate[t])),
            'matched_levels_from_130': levels[t],
            'episodes_per_min_at_L50': episodes[t]['L50'] / minutes, 'episodes_per_min_at_L90': episodes[t]['L90'] / minutes,
            'self_approach_median_count': float(np.median(self_counts[t])) if self_counts[t] else None,
            'external_130_median_count': float(np.median(ext[:, i])),
            'auc_external_130_vs_self_approach': auc(ext[:, i], self_counts[t])}
    # --- human sessions (descriptive): ipsilateral counts per window class
    h = read('human.json')
    hum = {}
    for wdw in h['windows']:
        e = h['sessions'][wdw['session']][str(wdw['episode'])]
        ticks = e['ticks']
        spk = np.array(e['spikes'])
        idx = [k for k, x in enumerate(ticks) if wdw['t0'] <= x <= wdw['t1']]
        if not idx:
            continue
        side = int(e['azimuth'][idx[-1]] >= 0.0)
        cnt = spk[idx][:, side_cols(side)].sum(0) / (len(idx) * DT)
        hum.setdefault(wdw['cls'], []).append(cnt)
    res['human_rate_hz_by_window_class'] = {c: {t: float(np.mean([v[i] for v in vs])) for i, t in enumerate(TYPES)} | {'n': len(vs)}
                                            for c, vs in hum.items()}
    res['outcome'] = outcome(res)
    write('results.json', res)
    show(res)


def outcome(res):
    crit = {}
    for t in C.NON_REFERENCE:
        i_ok = sum(1 for tid in C.SLOW_130 if (res['controlled'][tid][t]['auc_vs_stationary_baseline'] or 0) >= 0.90) >= 2
        ff = res['free_flight']['by_type']
        ii_rate = (ff[t]['episodes_per_min_at_L50'] <= 0.5 * ff['DNp01']['episodes_per_min_at_L50']
                   and ff[t]['episodes_per_min_at_L50'] <= 0.5 * ff['DNp04']['episodes_per_min_at_L50'])
        ii_self = (ff[t]['auc_external_130_vs_self_approach'] or 0) >= 0.80
        n1s = res['n1']['strong_direct'][t]
        iii = n1s['within_0_2s'] >= 0.9 or (n1s['auc_count_0_3s_vs_baseline'] or 0) >= 0.90
        crit[t] = {'i_responds_130': i_ok, 'ii_rate_selective': ii_rate, 'ii_self_vs_external': ii_self,
                   'ii': ii_rate and ii_self, 'iii_strong_threat': iii}
    if any(c['i_responds_130'] and c['ii'] and c['iii_strong_threat'] for c in crit.values()):
        oc = 'A. VIABLE BIOLOGICAL LONG-MODE SIGNAL EXISTS'
    elif any(c['i_responds_130'] for c in crit.values()):
        oc = 'B. SIGNAL EXISTS BUT IS NOT SELECTIVE'
    else:
        oc = 'C. NO USEFUL LONG-MODE SIGNAL FOUND'
    return {'per_candidate': crit, 'outcome': oc}


def show(res):
    print('baseline Hz', {t: round(v, 3) for t, v in res['baseline_rate_hz'].items()})
    for tid, v in res['controlled'].items():
        print('%-26s' % tid, ' '.join('%s %.1f/%.2f' % (t, v[t]['median_count'], v[t]['auc_vs_stationary_baseline'] or 0) for t in TYPES))
    print('reproduced', res['n4b6_dnp01_dnp04_reproduced'])
    print('mirror', json.dumps(res['mirror']))
    for k, v in res['n1'].items():
        print('N1', k, {t: (x['median_first_spike_s'], round(x['within_0_2s'], 2), round(x['auc_count_0_3s_vs_baseline'] or 0, 2)) for t, x in v.items()})
    ff = res['free_flight']
    print('free flight', ff['runs'], round(ff['minutes']), 'exact', ff['dnp01_identical_runs'], 'self windows', ff['self_approach_windows'])
    for t, v in ff['by_type'].items():
        print(' ', t, v)
    print(json.dumps(res['outcome'], indent=1))


if __name__ == '__main__':
    {'connectome': connectome, 'freeze': freeze, 'controlled': controlled, 'n1': n1, 'room': room,
     'human': human, 'analyze': analyze}[ARGS.mode]()
