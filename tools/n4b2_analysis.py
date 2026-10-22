"""M1.8-N4B2 research: alternative descending-neuron readout analysis.

Research only. No runtime file, configuration, calibration record, policy whitelist,
Retina, encoder, brain parameter, noise, lifecycle, physics or recorder change. Every DN
readout here is offline and evaluated in shadow mode; none is a policy input. World
geometry is read only to interpret recorded situations.

The frozen M1.8-N4B1C runtime decoder (lateral_dual_path_v1) is the reference. It is
replayed with the runtime's own FixedEscapePolicy, loaded from a clean detached worktree of
feature/m1-8-n4b1c-runtime (e3c55b3), on DNp01 traces rebuilt from re-simulated spikes.

Inputs (all git-ignored):

* artifacts/m1_8_n4/          N4A exact re-simulations (original N0, N1, both human sessions)
* artifacts/m1_8_n4b2/        N4B2 DN-panel re-simulations (tools/n4b2_record.py)
* artifacts/m1_8_loom_robustness/  N1 trial metadata
* results/game/sessions/      the two human sessions

Modes:

    python tools/n4b2_analysis.py dev        # development characterization -> dev.json
    python tools/n4b2_analysis.py freeze     # record the criteria module hash
    python tools/n4b2_analysis.py holdout    # frozen criteria on the new N0 holdout + ROOM arm
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import glob
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.stats import chi2  # noqa: E402

from tools import n4_diagnosis as D  # noqa: E402
from tools import n4b2_criteria as C  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b2'
N4 = ROOT / 'artifacts/m1_8_n4'
RUNTIME_WORKTREE = Path(os.environ.get('N4B1C_WORKTREE',
                                       ROOT / 'artifacts/worktrees/n4b1c-runtime-detached')).resolve()
RUNTIME_COMMIT = 'e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf'
DT = 0.02
TICKS_PER_MIN = 3000
CANDIDATES = ('DNp04', 'DNp01', 'DNp02', 'DNg40', 'DNp11', 'DNp03', 'DNp05', 'DNpe056',
              'DNp103', 'DNpe025')
DESCRIPTIVE_ONLY = ('DNp06', 'DNp71', 'DNp35')   # panel types that fail CANDIDATE_RULE


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def poisson_upper(k, minutes):
    """Exact one-sided 95 % Poisson upper bound on the rate per minute."""
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def med(v):
    v = [x for x in v if x is not None]
    return None if not v else float(np.median(v))


def pct(v, p):
    v = [x for x in v if x is not None]
    return None if not v else float(np.percentile(v, p))


# ================================================================== panel ===
def panel():
    meta = json.loads((OUT / 'connectome.json').read_text(encoding='utf-8'))
    cells = [r['cell'] for r in meta['panel']]
    types = [r['type'] for r in meta['panel']]
    sides = [r['side'] for r in meta['panel']]
    idx = {}
    for j, (t, s) in enumerate(zip(types, sides)):
        idx.setdefault(t, {})[s] = j
    return np.array(cells), types, sides, idx, meta


CELLS, TYPES, SIDES, IDX, CONNECTOME = panel()


def lr(spikes, dn_type):
    """(left, right) spike trains of one DN type from a (T, panel) bool matrix."""
    return spikes[:, IDX[dn_type]['L']], spikes[:, IDX[dn_type]['R']]


# ================================================================== runtime reference ===
def runtime_policy_class():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=RUNTIME_WORKTREE, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=RUNTIME_WORKTREE, text=True).strip()
    if head != RUNTIME_COMMIT or dirty:
        raise SystemExit('runtime worktree must be clean at %s' % RUNTIME_COMMIT)
    spec = importlib.util.spec_from_file_location('n4b1c_runtime_action',
                                                  RUNTIME_WORKTREE / 'game/action.py')
    mod = importlib.util.module_from_spec(spec)
    sys.modules['n4b1c_runtime_action'] = mod
    spec.loader.exec_module(mod)
    config = json.loads((RUNTIME_WORKTREE / 'game_room_config.json').read_text(encoding='utf-8'))
    d, p = config['policy']['escape_decoder'], config['policy']
    assert d['kind'] == 'lateral_dual_path_v1'
    tick = float(config['sim']['tick_seconds'])
    kwargs = dict(threshold=float(d['sustained_threshold']), refractory_seconds=float(p['refractory_seconds']),
                  tick_seconds=tick, fast_threshold=float(d['summed_fast_threshold']),
                  persistence_samples=int(d['sustained_required_samples']),
                  sustained_window_samples=int(d['sustained_window_samples']),
                  require_current_qualifying=bool(d['require_current_qualifying']),
                  lateral_window_samples=int(round(d['lateral_same_side_window_ms'] / 1000.0 / tick)),
                  lateral_required_spikes=int(d['lateral_required_spikes']),
                  trace_decay=float(np.float32(np.exp(-tick / float(config['brain']['trace_tau_seconds'])))))
    return mod, kwargs


_RUNTIME = None


def n4b1c_events(left, right):
    """Firing samples of the frozen runtime decoder on DNp01 traces (fresh policy state)."""
    global _RUNTIME
    if _RUNTIME is None:
        _RUNTIME = runtime_policy_class()
    mod, kwargs = _RUNTIME
    pol = mod.FixedEscapePolicy(**kwargs)
    pol.reset()
    zero = np.zeros(1, np.float32)
    out = []
    for t in range(left.size):
        a = pol.decide(mod.MotorState(float(left[t]), float(right[t]), 0.0, 0.0, zero))
        if a.escape:
            out.append((t, pol.criterion_diagnostics()['escape_trigger_paths']))
    return out


# ================================================================== segments ===
class Seg:
    """One offline segment: panel spikes, DNp01 traces with history, sensory, drive."""

    def __init__(self, name, cls, spikes, trace_l, trace_r, sensory, drive, anchors=None, info=None):
        self.name, self.cls = name, cls
        self.spikes, self.trace_l, self.trace_r = spikes, trace_l, trace_r
        self.sensory, self.drive = sensory, drive
        self.anchors = anchors or {}
        self.info = info or {}

    @property
    def n(self):
        return self.spikes.shape[0]


def sim_panel_matrix(a):
    """(steps, panel) bool matrix from an N4A re-simulation's dn_steps / dn_cells."""
    slot = np.full(int(max(CELLS.max(), a['dn_cells'].max())) + 1, -1)
    slot[CELLS] = np.arange(CELLS.size)
    s = slot[a['dn_cells']]
    keep = s >= 0
    m = np.zeros((a['spk_L'].size, CELLS.size), bool)
    m[a['dn_steps'][keep], s[keep]] = True
    # DNp01 in the panel must equal the directly recorded DNp01 spikes.
    assert np.array_equal(m[:, IDX['DNp01']['L']], a['spk_L'] > 0)
    assert np.array_equal(m[:, IDX['DNp01']['R']], a['spk_R'] > 0)
    return m


def traces_over(spk, starts, n):
    """DNp01 trace per step, reset at each segment start (flybrain.Trace arithmetic)."""
    out = np.zeros(n, np.float64)
    bounds = sorted(set(starts)) + [n]
    for b0, b1 in zip(bounds[:-1], bounds[1:]):
        out[b0:b1] = C.trace(spk[b0:b1])
    return out


def n0_original():
    a, m = D.load_sim('n0')
    M = sim_panel_matrix(a)
    starts = [t['first_step'] for t in m['trials']]
    tl = traces_over(a['spk_L'] > 0, starts, a['spk_L'].size)
    tr = traces_over(a['spk_R'] > 0, starts, a['spk_R'].size)
    sens = np.stack([a['LPLC2_L'], a['LPLC2_R'], a['LC4_L'], a['LC4_R']], 1)
    drv = np.stack([a['drive_loomL'], a['drive_loomR'], a['drive_threatL'], a['drive_threatR']], 1)
    segs = []
    for t in m['trials']:
        s = slice(t['record_first_step'], t['end_step'])
        segs.append(Seg('n0_orig_%d' % t['seed'], 'N0', M[s], tl[s], tr[s], sens[s], drv[s],
                        info={'seed': t['seed']}))
    return segs


def n0_chunks(name):
    segs = []
    files = sorted(glob.glob(str(OUT / ('n0_%s_chunk*.npz' % name))))
    for f in files:
        d = np.load(f)
        meta = json.loads(Path(f[:-4] + '.json').read_text(encoding='utf-8'))
        assert meta['panel_cells'] == [int(c) for c in CELLS], 'panel mismatch'
        if meta['exact_trials'] != meta['trials']:
            raise SystemExit('%s: only %d / %d trials exact' % (f, meta['exact_trials'], meta['trials']))
        for i in range(d['spikes'].shape[0]):
            sp = d['spikes'][i]
            # The recorded window follows a settle period; traces start from the window here
            # (a trace carried from the settle adds at most the decayed settle spikes).
            segs.append(Seg('n0_%s_%d' % (name, int(d['seeds'][i])), 'N0', sp,
                            C.trace(sp[:, IDX['DNp01']['L']]).astype(np.float64),
                            C.trace(sp[:, IDX['DNp01']['R']]).astype(np.float64),
                            d['sensory'][i], d['drive'][i], info={'seed': int(d['seeds'][i])}))
    return segs, files


def n1_segments():
    a, m = D.load_sim('n1')
    M = sim_panel_matrix(a)
    data = np.load(D.N1_DIR / 'trials.npz')
    meta = json.loads((D.N1_DIR / 'trials_meta.json').read_text(encoding='utf-8'))
    starts = [t['first_step'] for t in m['trials']]
    tl = traces_over(a['spk_L'] > 0, starts, a['spk_L'].size)
    tr = traces_over(a['spk_R'] > 0, starts, a['spk_R'].size)
    events = D.n1_events(a, m, data, meta)
    segs = []
    for e in events:
        st = np.array(e.ref['steps'])
        sens = np.stack([e.f['LPLC2_L'], e.f['LPLC2_R'], e.f['LC4_L'], e.f['LC4_R']], 1)
        drv = np.stack([e.f['drive_loomL'], e.f['drive_loomR'], e.f['drive_threatL'], e.f['drive_threatR']], 1)
        segs.append(Seg(e.label, e.cls, M[st], tl[st], tr[st], sens, drv, dict(e.anchors),
                        {'retina': e.retina}))
    return segs


def session_segments():
    """Human-session events (N4A definitions) plus whole-episode segments for synced replay."""
    segs, episodes = [], {}
    for sess, name in D.SESSIONS.items():
        a, m = D.load_sim('session_' + name)
        M = sim_panel_matrix(a)
        eps, strikes = D.session_rows(name)
        starts = [e['first_step'] for e in m['episodes']]
        tl = traces_over(a['spk_L'] > 0, starts, a['spk_L'].size)
        tr = traces_over(a['spk_R'] > 0, starts, a['spk_R'].size)
        # The rebuilt traces must equal the recorded DNp01 observation on every stepped row.
        for e in m['episodes']:
            rows = eps[e['episode']]
            for k, r in zip(e['row_step'], rows):
                if k >= 0:
                    assert tl[k] == r['neural']['dnp01_left'] and tr[k] == r['neural']['dnp01_right']
        for e in D.human_events(sess, name, a, m):
            st = np.array(e.ref['steps'])
            sens = np.stack([e.f['LPLC2_L'], e.f['LPLC2_R'], e.f['LC4_L'], e.f['LC4_R']], 1)
            drv = np.stack([e.f['drive_loomL'], e.f['drive_loomR'], e.f['drive_threatL'],
                            e.f['drive_threatR']], 1)
            segs.append(Seg(e.label, e.cls, M[st], tl[st], tr[st], sens, drv, dict(e.anchors),
                            {'session': sess, 'episode': e.ref['episode'], 'rows': e.ref['rows'],
                             'retina': e.retina, 'geometry': e.ref['geometry']}))
        for e in m['episodes']:
            rows = eps[e['episode']]
            keep = [j for j, k in enumerate(e['row_step']) if k >= 0]
            st = np.array([e['row_step'][j] for j in keep])
            episodes[(sess, e['episode'])] = {'spikes': M[st], 'tl': tl[st], 'tr': tr[st],
                                              'rows': [rows[j] for j in keep]}
    return segs, episodes


def room_segments(seeds):
    segs = []
    for seed in seeds:
        d = np.load(OUT / ('room_seed%d.npz' % seed))
        meta = json.loads((OUT / ('room_seed%d.json' % seed)).read_text(encoding='utf-8'))
        assert meta['panel_cells'] == [int(c) for c in CELLS]
        rows = [meta['rows'][k] for k in d['stepped_ticks']]
        tl = np.array([r['dnp01_left'] for r in rows])
        tr = np.array([r['dnp01_right'] for r in rows])
        sp = d['spikes']
        # Episode boundaries (death / respawn) reset the trace; check the rebuilt trace.
        re_l = C.trace(sp[:, IDX['DNp01']['L']])
        ok = np.mean(np.abs(re_l - tl) < 1e-6)
        segs.append(Seg('room_%d' % seed, 'ROOM_no_player', sp, tl, tr, d['sensory'], d['drive'],
                        info={'seed': seed, 'rows': rows, 'trace_match_fraction': float(ok),
                              'runtime_escapes': [i for i, r in enumerate(rows) if r['escape']]}))
    return segs


# ================================================================== readout evaluation ===
def first_after(events, t0):
    for t, lab in events:
        if t >= t0:
            return t, lab
    return None, None


def cell_stats(spk):
    t = np.flatnonzero(spk)
    isi = np.diff(t)
    return t, isi


def n0_structure(segs, dn_type):
    """Spontaneous structure of one DN type over N0 segments."""
    n_samples = sum(s.n for s in segs)
    minutes = n_samples / TICKS_PER_MIN
    rate, isi_min, close = {}, {}, {}
    all_isi = {'L': [], 'R': []}
    for side in 'LR':
        cnt = 0
        for s in segs:
            spk = s.spikes[:, IDX[dn_type][side]]
            t, isi = cell_stats(spk)
            cnt += t.size
            all_isi[side].append(isi)
        rate[side] = cnt / (n_samples * DT)
        isi = np.concatenate(all_isi[side]) if all_isi[side] else np.zeros(0)
        isi_min[side] = int(isi.min()) if isi.size else None
        close[side] = {str(w): int((isi <= w).sum()) for w in (1, 2, 3, 4, 5, 10)}
    bil = 0
    for s in segs:
        l, r = lr(s.spikes, dn_type)
        bil += int((l & r).sum())
    expected_bil = rate['L'] * DT * rate['R'] * DT * n_samples
    return {'minutes': minutes, 'rate_hz': rate, 'same_side_isi_min_samples': isi_min,
            'same_side_isi_le_w': close, 'same_tick_bilateral': bil,
            'same_tick_bilateral_expected_if_independent': expected_bil}


def n0_family_events(segs, dn_type, fam):
    out = {}
    minutes = sum(s.n for s in segs) / TICKS_PER_MIN
    for key, spec in fam.items():
        ev = []
        for s in segs:
            l, r = lr(s.spikes, dn_type)
            for t, lab in C.evaluate(spec, l, r):
                ev.append({'segment': s.name, 'sample': t, 'label': lab})
        out[key] = {'events': len(ev), 'per_min': len(ev) / minutes,
                    'upper95_per_min': poisson_upper(len(ev), minutes), 'examples': ev[:5]}
    return out


def pooled_trace_envelope(segs, dn_type):
    """Max same-side and summed trace over N0 (for trace-form readouts)."""
    lat, summ = 0.0, 0.0
    for s in segs:
        l, r = lr(s.spikes, dn_type)
        tl, tr = C.trace(l), C.trace(r)
        lat = max(lat, float(np.max(np.maximum(tl, tr))))
        summ = max(summ, float(np.max(tl + tr)))
    return {'lateral_max': lat, 'summed_max': summ}


def detection(seg, dn_type, spec, t0=None):
    """First firing of a readout at or after the segment onset (clean start at segment start)."""
    t0 = seg.anchors.get('onset', 0) if t0 is None else t0
    l, r = lr(seg.spikes, dn_type)
    ev = C.evaluate(spec, l, r)
    t, lab = first_after(ev, t0)
    pre = sum(1 for tt, _ in ev if tt < t0)
    return (None if t is None else t - t0), lab, pre


def ref_detection(seg, t0=None):
    t0 = seg.anchors.get('onset', 0) if t0 is None else t0
    ev = n4b1c_events(seg.trace_l, seg.trace_r)
    t, lab = first_after(ev, t0)
    return (None if t is None else t - t0), lab, sum(1 for tt, _ in ev if tt < t0)


def spike_profile(seg, dn_type, t0=None, horizon=None):
    """First-spike latency, spike counts and laterality after onset."""
    t0 = seg.anchors.get('onset', 0) if t0 is None else t0
    t1 = seg.n if horizon is None else min(seg.n, t0 + horizon)
    l, r = lr(seg.spikes, dn_type)
    l, r = l[t0:t1], r[t0:t1]
    tl, tr = np.flatnonzero(l), np.flatnonzero(r)
    first = min([x[0] for x in (tl, tr) if x.size], default=None)
    both = bool(tl.size and tr.size)
    return {'first_spike': None if first is None else int(first), 'n_left': int(tl.size),
            'n_right': int(tr.size), 'bilateral': both}


def driven_side(seg, t0, t1):
    s = seg.sensory[t0:t1]
    left = s[:, 0].sum() + s[:, 2].sum()
    right = s[:, 1].sum() + s[:, 3].sum()
    return 'L' if left > right else 'R' if right > left else None


# ================================================================== human detail ===
KEY_READOUTS = ('pair_3', 'pair_5', 'triple_10', 'same_3_in_25', 'pooled_4_in_10', 'single')


def window_first(seg, dn_type, spec, anchor):
    """First firing anywhere in the segment (clean start at its first sample), relative to
    `anchor` (negative = before it)."""
    if dn_type == 'N4B1C':
        ev = n4b1c_events(seg.trace_l, seg.trace_r)
    else:
        l, r = lr(seg.spikes, dn_type)
        ev = C.evaluate(spec, l, r)
    return (None, None) if not ev else (ev[0][0] - anchor, ev[0][1])


def human_detail(hs, fam, types):
    """Per-event detections for the human cases (clean start at each event window)."""
    out = {}
    for s in hs:
        a = s.anchors
        if s.cls == 'human_direct_strike':
            anchor, horizon = a['click'], s.n
        elif s.cls in ('human_hover_escape', 'human_strike_escape', 'chase_before_589', 'slow_close'):
            anchor, horizon = 0, s.n
        else:
            anchor, horizon = 0, s.n
        row = {'cls': s.cls, 'n': s.n, 'anchors': a,
               'N4B1C': window_first(s, 'N4B1C', None, anchor)}
        for t in types:
            row[t] = {k: window_first(s, t, fam[k], anchor) for k in KEY_READOUTS}
        out[s.name] = row
    return out


def contexts(rows):
    """Offline context label per stepped row (WORLD geometry; interpretation only)."""
    out = []
    for r in rows:
        sw, fl = r['swatter'], r['fly']
        d = math.hypot(fl['x'] - sw['x'], fl['y'] - sw['y'])
        perched = r['ecology'].get('landing_perching') if r.get('ecology') else None
        if sw['phase'] in D.STRIKE_PHASES:
            c = 'strike'
        elif d < 300:
            c = 'hover_near_lt300'
        elif d < 800:
            c = 'mid_300_800'
        else:
            c = 'far_ge800'
        out.append((c, d, perched))
    return out


def episode_shadow(episodes, fam, types):
    """Whole-episode open-loop replay (fresh state per episode): firing counts by context.

    Open loop: a readout firing does not change the recorded trajectory, so counts after the
    first firing of a bout describe evidence, not closed-loop behaviour."""
    res = {}
    total_min = 0.0
    ctx_min = Counter()
    per = {'N4B1C': Counter()}
    extra = {}
    for key, ep in episodes.items():
        ctx = contexts(ep['rows'])
        n = len(ctx)
        total_min += n / TICKS_PER_MIN
        for c, _, _ in ctx:
            ctx_min[c] += 1 / TICKS_PER_MIN
        ref = n4b1c_events(ep['tl'], ep['tr'])
        ref_t = np.array([t for t, _ in ref])
        for t, _ in ref:
            per['N4B1C'][ctx[t][0]] += 1
        for dn_type in types:
            for k in KEY_READOUTS:
                name = '%s %s' % (dn_type, k)
                l, r = lr(ep['spikes'], dn_type)
                ev = C.evaluate(fam[k], l, r)
                per.setdefault(name, Counter())
                extra.setdefault(name, Counter())
                for t, _ in ev:
                    per[name][ctx[t][0]] += 1
                    # "Additional": no N4B1C firing within +/- 20 samples (one refractory).
                    if ref_t.size == 0 or np.min(np.abs(ref_t - t)) > C.REFRACTORY_SAMPLES:
                        extra[name][ctx[t][0]] += 1
    res['minutes_total'] = total_min
    res['minutes_by_context'] = dict(ctx_min)
    res['firings_by_context'] = {k: dict(v) for k, v in per.items()}
    res['additional_to_n4b1c_by_context'] = {k: dict(v) for k, v in extra.items()}
    return res


def slow_close_timeline(episodes, fam):
    """Episode 5 of the N2b session, ticks 600-680, with offline geometry."""
    ep = episodes[('n2b', 5)]
    rows = ep['rows']
    tick_index = {r['tick']: j for j, r in enumerate(rows)}
    j0, j1 = tick_index[600], tick_index[680]
    lines = []
    for j in range(j0, j1 + 1):
        r = rows[j]
        sw, fl = r['swatter'], r['fly']
        d = math.hypot(fl['x'] - sw['x'], fl['y'] - sw['y'])
        v = r['visual_input']
        s = r['sensory_spikes']
        lines.append({'tick': r['tick'], 'phase': sw['phase'], 'horizontal_distance': d,
                      'height': sw['height'], 'distance_3d': math.hypot(d, sw['height']),
                      'swatter_speed': sw['speed'], 'theta': r['retina']['theta'],
                      'theta_dot': r['retina']['theta_dot'], 'azimuth': r['retina']['azimuth'],
                      'drive': v['loomL'] + v['loomR'] + v['threatL'] + v['threatR'],
                      'sensory_L': s['LPLC2_left'] + s['LC4_left'], 'sensory_R': s['LPLC2_right'] + s['LC4_right'],
                      'DNp01_L': bool(ep['spikes'][j, IDX['DNp01']['L']]),
                      'DNp01_R': bool(ep['spikes'][j, IDX['DNp01']['R']]),
                      'DNp04_L': bool(ep['spikes'][j, IDX['DNp04']['L']]),
                      'DNp04_R': bool(ep['spikes'][j, IDX['DNp04']['R']]),
                      'recorded_escape': bool(r['action']['escape'])})
    # Clean-start readouts at tick 610 (N2b refractory ended at 609).
    k0 = tick_index[610]
    sub = Seg('slow', 'slow', ep['spikes'][k0:j1 + 1], ep['tl'][k0:j1 + 1], ep['tr'][k0:j1 + 1],
              None, None)
    fires = {'N4B1C': [(rows[k0 + t]['tick'], lab) for t, lab in n4b1c_events(sub.trace_l, sub.trace_r)]}
    for dn_type in ('DNp04', 'DNp01', 'DNp02', 'DNg40', 'DNp11'):
        l, r = lr(sub.spikes, dn_type)
        for k in KEY_READOUTS:
            fires['%s %s' % (dn_type, k)] = [(rows[k0 + t]['tick'], lab) for t, lab in C.evaluate(fam[k], l, r)]
    # Offline geometry landmarks inside 610-669.
    seg_lines = [x for x in lines if 610 <= x['tick'] <= 669]
    closest = min(seg_lines, key=lambda x: x['horizontal_distance'])
    return {'lines': lines, 'clean_start_610_firings': fires, 'closest_horizontal': closest['tick'],
            'first_positive_theta_dot': next((x['tick'] for x in seg_lines if x['theta_dot'] > 1e-6), None),
            'first_drive': next((x['tick'] for x in seg_lines if x['drive'] > 1e-6), None),
            'first_sensory_above_22': next((x['tick'] for x in seg_lines
                                            if max(x['sensory_L'], x['sensory_R']) > 22), None)}


# ================================================================== dev ===
def dev():
    started = time.perf_counter()
    fam = C.family()
    result = {'label': 'M1.8-N4B2 development characterization (research only, offline)',
              'candidates': list(CANDIDATES), 'descriptive_only': list(DESCRIPTIVE_ONLY),
              'family': fam}
    # ---- N0 development data
    n0 = {'original': n0_original()}
    for name in ('n4b1_fresh', 'n4b1c_holdout'):
        segs, files = n0_chunks(name)
        n0[name] = segs
        result.setdefault('inputs', {})[name] = {Path(f).name: sha256(f) for f in files}
    dev_n0 = [s for v in n0.values() for s in v]
    result['n0_minutes'] = {k: sum(s.n for s in v) / TICKS_PER_MIN for k, v in n0.items()}
    print('N0 dev minutes', result['n0_minutes'], flush=True)
    result['n0_max_encoder_drive'] = float(max(np.max(s.drive) for s in dev_n0))
    # N4B1C reference on development N0 (cross-check against N4B1C's own evaluation).
    ref_ev = defaultdict(list)
    for k, v in n0.items():
        for s in v:
            for t, lab in n4b1c_events(s.trace_l, s.trace_r):
                ref_ev[k].append({'segment': s.name, 'sample': t, 'paths': lab})
    result['n0_n4b1c_reference'] = dict(ref_ev)
    print('N4B1C on dev N0:', {k: len(v) for k, v in ref_ev.items()}, flush=True)
    result['n0_structure'] = {t: n0_structure(dev_n0, t) for t in CANDIDATES + DESCRIPTIVE_ONLY}
    result['n0_family'] = {t: {k: n0_family_events(v, t, fam) for k, v in n0.items()}
                           for t in CANDIDATES}
    result['n0_trace_envelope'] = {t: pooled_trace_envelope(dev_n0, t) for t in CANDIDATES}
    print('N0 done %.0fs' % (time.perf_counter() - started), flush=True)
    # ---- N1
    n1 = n1_segments()
    classes = ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach')
    n1_res = {}
    for cls in classes:
        segs = [s for s in n1 if s.cls == cls]
        row = {'n': len(segs)}
        ref = [ref_detection(s) for s in segs]
        row['N4B1C'] = {'detected': sum(r[0] is not None for r in ref),
                        'median_s': None if med([r[0] for r in ref]) is None else med([r[0] for r in ref]) * DT,
                        'p95_s': None if pct([r[0] for r in ref], 95) is None else pct([r[0] for r in ref], 95) * DT,
                        'pre_onset_events': sum(r[2] for r in ref)}
        for t in CANDIDATES:
            per = {}
            for key, spec in fam.items():
                det = [detection(s, t, spec) for s in segs]
                lat = [d[0] for d in det]
                per[key] = {'detected': sum(x is not None for x in lat),
                            'median_s': None if med(lat) is None else med(lat) * DT,
                            'p95_s': None if pct(lat, 95) is None else pct(lat, 95) * DT,
                            'pre_onset_events': sum(d[2] for d in det)}
            prof = [spike_profile(s, t, horizon=25) for s in segs]
            sides = []
            for s, p in zip(segs, prof):
                ds = driven_side(s, s.anchors.get('onset', 0), s.n)
                sides.append(ds)
            per['profile_first_500ms'] = {
                'first_spike_median_s': None if med([p['first_spike'] for p in prof]) is None
                else med([p['first_spike'] for p in prof]) * DT,
                'any_spike': sum(p['first_spike'] is not None for p in prof),
                'spikes_median': med([p['n_left'] + p['n_right'] for p in prof]),
                'bilateral_fraction': float(np.mean([p['bilateral'] for p in prof])),
                'driven_side_share': float(np.mean([
                    (p['n_left'] if ds == 'L' else p['n_right']) / max(1, p['n_left'] + p['n_right'])
                    for p, ds in zip(prof, sides) if ds is not None and p['n_left'] + p['n_right'] > 0]))
                if any(ds is not None for ds in sides) else None}
            row[t] = per
        n1_res[cls] = row
    result['n1'] = n1_res
    # N1 pre-onset (settled static hover before the click, an N0-like interval): events per readout.
    print('N1 done %.0fs' % (time.perf_counter() - started), flush=True)
    # ---- human sessions
    hs, episodes = session_segments()
    result['human_event_counts'] = dict(Counter(s.cls for s in hs))
    hres = defaultdict(dict)
    for cls in sorted(set(s.cls for s in hs)):
        segs = [s for s in hs if s.cls == cls]
        esc = [s.anchors.get('escape') for s in segs]
        ref = [ref_detection(s) for s in segs]
        hres[cls]['n'] = len(segs)
        hres[cls]['recorded_escape_median_s'] = None if med(esc) is None else med(esc) * DT
        hres[cls]['N4B1C'] = {'detected': sum(r[0] is not None for r in ref),
                              'median_s': None if med([r[0] for r in ref]) is None else med([r[0] for r in ref]) * DT,
                              'per_event': [r[0] for r in ref]}
        for t in CANDIDATES:
            per = {}
            for key, spec in fam.items():
                det = [detection(s, t, spec) for s in segs]
                lat = [d[0] for d in det]
                per[key] = {'detected': sum(x is not None for x in lat),
                            'median_s': None if med(lat) is None else med(lat) * DT,
                            'per_event': lat}
            hres[cls][t] = per
    result['human'] = dict(hres)
    result['human_segments'] = [{'name': s.name, 'cls': s.cls, 'anchors': s.anchors, 'n': s.n,
                                 **{k: v for k, v in s.info.items() if k in ('session', 'episode', 'rows')}}
                                for s in hs]
    result['human_detail'] = human_detail(hs, fam, CANDIDATES)
    result['episode_shadow'] = episode_shadow(episodes, fam, CANDIDATES)
    result['slow_close'] = slow_close_timeline(episodes, fam)
    print('human done %.0fs' % (time.perf_counter() - started), flush=True)
    # ---- ROOM no-player development runs (shadow mode under the accepted runtime)
    rooms = [s for s in ROOM_DEV_SEEDS if (OUT / ('room_seed%d.npz' % s)).exists()]
    if rooms:
        crit = {'N4B1C': {'reference_only': True}}
        crit.update({'%s %s' % (t, k): {'type': t, 'spec': fam[k]} for t in CANDIDATES for k in KEY_READOUTS})
        crit.update({'N4B1C OR %s %s' % (t, k): {'type': t, 'spec': fam[k], 'combine_with_n4b1c': True}
                     for t in ('DNp04', 'DNp02') for k in ('pair_3', 'triple_10', 'pooled_4_in_10')})
        room = room_eval(room_segments(rooms), crit)
        for v in room['criteria'].values():
            if v['events'] > 200:
                v['list'] = v['list'][:20]
        result['room_dev'] = room
        print('ROOM dev done %.0fs' % (time.perf_counter() - started), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'dev.json').write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')
    print('wrote dev.json %.0fs' % (time.perf_counter() - started))


# ================================================================== ROOM shadow ===
def room_context(row, paddle):
    fx, fy = row['fly_xyz'][0], row['fly_xyz'][1]
    d = math.hypot(fx - paddle[0], fy - paddle[1])
    return {'lifecycle_mode': row['lifecycle_mode'], 'distance_to_parked_paddle': d,
            'theta': row['theta'], 'theta_dot': row['theta_dot']}


def criterion_events(seg, crit):
    """Events of a frozen criterion on a segment (see FROZEN in tools/n4b2_criteria.py)."""
    if crit.get('reference_only'):
        return n4b1c_events(seg.trace_l, seg.trace_r)
    l, r = lr(seg.spikes, crit['type'])
    ev = C.evaluate(crit['spec'], l, r)
    if not crit.get('combine_with_n4b1c'):
        return ev
    ref = [(t, 'N4B1C:' + lab) for t, lab in n4b1c_events(seg.trace_l, seg.trace_r)]
    merged = sorted(ref + [(t, crit['type'] + ':' + lab) for t, lab in ev])
    return C._scan(((t, None, lab) for t, lab in merged), 0)


def room_eval(segs, criteria):
    out = {'minutes': sum(s.n for s in segs) / TICKS_PER_MIN, 'runs': []}
    for s in segs:
        rows = s.info['rows']
        replay = [t for t, _ in n4b1c_events(s.trace_l, s.trace_r)]
        modes = Counter(r['lifecycle_mode'] for r in rows)
        events = Counter(e for r in rows for e in r['events'])
        out['runs'].append({'seed': s.info['seed'], 'samples': s.n,
                            'trace_match_fraction': s.info['trace_match_fraction'],
                            'runtime_escapes': s.info['runtime_escapes'], 'replayed_n4b1c': replay,
                            'replay_matches_runtime': replay == s.info['runtime_escapes'],
                            'lifecycle_modes': dict(modes), 'lifecycle_events': dict(events)})
    res = {}
    for name, crit in criteria.items():
        ev = []
        for s in segs:
            for t, lab in criterion_events(s, crit):
                ev.append({'seed': s.info['seed'], 'sample': t, 'label': lab,
                           **room_context(s.info['rows'][t], (1920.0, 388.8))})
        res[name] = {'events': len(ev), 'per_min': len(ev) / out['minutes'],
                     'upper95_per_min': poisson_upper(len(ev), out['minutes']),
                     'by_lifecycle_mode': dict(Counter(e['lifecycle_mode'] for e in ev)),
                     'list': ev}
    out['criteria'] = res
    return out


# ================================================================== freeze / holdout ===
FROZEN_FILE = OUT / 'frozen_criteria.json'
ROOM_DEV_SEEDS = (7101, 7102, 7103, 7104)
ROOM_HOLDOUT_SEEDS = tuple(range(7201, 7213))


def freeze():
    if FROZEN_FILE.exists():
        print('already frozen', sha256(FROZEN_FILE))
        return
    if not C.FROZEN:
        raise SystemExit('tools/n4b2_criteria.py FROZEN is empty')
    holdout = sorted(OUT.glob('n0_n4b2_holdout_chunk*.npz')) + [OUT / ('room_seed%d.npz' % s)
                                                                 for s in ROOM_HOLDOUT_SEEDS]
    if any(p.exists() for p in holdout):
        raise SystemExit('holdout data already exist; the freeze must precede them')
    body = {'label': 'M1.8-N4B2 frozen DN readout criteria (research only)',
            'frozen_before_holdout': True,
            'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'criteria': C.FROZEN, 'candidate_rule': C.CANDIDATE_RULE,
            'selection_protocol': C.SELECTION_PROTOCOL,
            'criteria_module': 'tools/n4b2_criteria.py', 'criteria_module_sha256': sha256(ROOT / 'tools/n4b2_criteria.py'),
            'analysis_module_sha256': sha256(__file__),
            'record_module_sha256': sha256(ROOT / 'tools/n4b2_record.py'),
            'runtime_reference_commit': RUNTIME_COMMIT,
            'holdout_protocol': {'n0': {'set': 'n4b2_holdout', 'seeds': '310000 + chunk * 10000 + i, chunks 0-3, i < 150',
                                        'offset_rng': 'default_rng(encoder_seed + 717171 + chunk)',
                                        'minutes': 280, 'config_commit': '3d41113',
                                        'protocol': 'tools/calibrate_escape._trial, fixed fly, no loom'},
                                 'room_no_player': {'seeds': list(ROOM_HOLDOUT_SEEDS), 'ticks': 9000,
                                                    'runtime': RUNTIME_COMMIT}},
            'development_data_inspected': ['original N0 70 min (4000-4149)', 'N4B1 fresh N0 280 min (30000-60149)',
                                           'N4B1C holdout 280 min (210000-240149)', 'N1 300 trials',
                                           'both human sessions', 'ROOM no-player seeds %s' % list(ROOM_DEV_SEEDS)]}
    FROZEN_FILE.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
    print('frozen', FROZEN_FILE, sha256(FROZEN_FILE))


def check_frozen():
    frozen = json.loads(FROZEN_FILE.read_text(encoding='utf-8'))
    if sha256(ROOT / 'tools/n4b2_criteria.py') != frozen['criteria_module_sha256']:
        raise SystemExit('tools/n4b2_criteria.py changed after the freeze')
    return frozen


def all_criteria():
    crit = {'N4B1C (frozen runtime)': {'reference_only': True}}
    crit.update(C.FROZEN)
    return crit


def n0_eval(segs, criteria):
    minutes = sum(s.n for s in segs) / TICKS_PER_MIN
    out = {'minutes': minutes, 'max_encoder_drive': float(max(np.max(s.drive) for s in segs))}
    for name, crit in criteria.items():
        ev = []
        for s in segs:
            for t, lab in criterion_events(s, crit):
                ev.append({'segment': s.name, 'sample': t, 'label': lab})
        out[name] = {'events': len(ev), 'per_min': len(ev) / minutes,
                     'upper95_per_min': poisson_upper(len(ev), minutes),
                     'labels': dict(Counter(e['label'] for e in ev)), 'list': ev}
    return out


def holdout():
    frozen = check_frozen()
    crit = all_criteria()
    result = {'label': 'M1.8-N4B2 holdout evaluation of frozen criteria (research only)',
              'frozen_criteria_sha256': sha256(FROZEN_FILE), 'criteria': list(crit)}
    segs, files = n0_chunks('n4b2_holdout')
    for f in files:
        meta = json.loads(Path(f[:-4] + '.json').read_text(encoding='utf-8'))
        if meta.get('frozen_criteria_sha256') != sha256(FROZEN_FILE):
            raise SystemExit('%s was not generated under the current freeze' % f)
    result['n0_holdout_inputs'] = {Path(f).name: sha256(f) for f in files}
    result['n0_holdout'] = n0_eval(segs, crit)
    # Development N0 under the same frozen criteria (for the combined 910-min figure).
    dev_segs = n0_original() + n0_chunks('n4b1_fresh')[0] + n0_chunks('n4b1c_holdout')[0]
    result['n0_development'] = n0_eval(dev_segs, crit)
    rooms = [s for s in ROOM_HOLDOUT_SEEDS if (OUT / ('room_seed%d.npz' % s)).exists()]
    result['room_holdout_seeds'] = rooms
    result['room_holdout'] = room_eval(room_segments(rooms), crit) if rooms else None
    result['room_development'] = room_eval(room_segments(ROOM_DEV_SEEDS), crit)
    (OUT / 'holdout.json').write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')
    for name in crit:
        h = result['n0_holdout'][name]
        d = result['n0_development'][name]
        r = result['room_holdout']['criteria'][name] if rooms else None
        print('%-40s holdout N0 %3d (%.4f, up %.4f)  dev N0 %3d  ROOM %s' % (
            name, h['events'], h['per_min'], h['upper95_per_min'], d['events'],
            None if r is None else '%d / %.1f min (up %.3f)' % (r['events'], result['room_holdout']['minutes'],
                                                               r['upper95_per_min'])))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('dev', 'freeze', 'holdout'))
    args = ap.parse_args()
    if args.mode == 'dev':
        dev()
    elif args.mode == 'freeze':
        freeze()
    else:
        holdout()


if __name__ == '__main__':
    main()
