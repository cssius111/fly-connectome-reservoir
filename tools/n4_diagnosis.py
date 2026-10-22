"""M1.8-N4A research: sensory-to-descending pathway diagnosis.

Research only. Reads the recordings and the exact instrumented re-simulations written by
`tools/n4_resimulate.py`; changes no runtime file, configuration, calibration record,
policy observation, brain, encoder or Retina parameter.

Offline-only data. World geometry, Retina values, encoder drive, sensory spikes, DNp01
membrane voltage and the spikes of other descending neurons are used here to diagnose where
threat information is lost or delayed. None of them is, or is proposed here to become, a
policy input. Other descending neurons are exploratory and are not wired into anything.

Processing levels compared against the N0 no-loom background:

A. Retina (theta, theta_dot, azimuth);
B. LC4/LPLC2 encoder drive and sensory spikes;
C. DNp01 spikes (deconvolution-free: the re-simulation records them directly);
D. DNp01 trace (what the policy observes);
E. exploratory: other descending neurons.

    python tools/n4_diagnosis.py
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

DT = 0.02
LOW, FAST = 1.45, 2.10
SIM = ROOT / 'artifacts/m1_8_n4'
N1_DIR = ROOT / 'artifacts/m1_8_loom_robustness'
SESSIONS = {'strict_n2': '20260923T005351.731330Z-38255ec8',
            'n2b': '20260924T000111.561327Z-c337a721'}
STRIKE_PHASES = ('windup', 'active', 'commit', 'fast_swing', 'active_contact')
LARGE_THETA = 0.35          # rad; offline label for "large nearby object"
STATIC_THETA_DOT = 0.25     # rad/s; offline label for "angular size nearly constant"
GAP = 10                    # ticks; bout separation, as in N3
EPS = 1e-6                  # static-hover float residue in theta_dot / drive is about 1e-11
TONIC, DECAY, KICK = 0.14, float(np.float32(np.exp(-0.2))), 0.22


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def q(v, p):
    v = [x for x in v if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.percentile(v, p)) if v else None


def med(v):
    return q(v, 50)


# ---------------------------------------------------------------- loading ---
def load_sim(name):
    a = dict(np.load(SIM / (name + '.npz')))
    m = json.loads((SIM / (name + '.json')).read_text(encoding='utf-8'))
    return a, m


def frame(a, steps):
    """Per-tick arrays for a list of re-simulation steps (both sides kept)."""
    s = np.asarray(steps)
    return {k: a[k][s] for k in a if k not in ('dn_steps', 'dn_cells')}


def dn_spikes_by_step(a):
    order = np.argsort(a['dn_steps'], kind='stable')
    steps, cells = a['dn_steps'][order], a['dn_cells'][order]
    bounds = np.searchsorted(steps, np.arange(a['spk_L'].size + 1))
    return steps, cells, bounds


class Event:
    """One threat bout or reference interval, with per-tick arrays (offline)."""

    def __init__(self, dataset, cls, label, f, retina, anchors, ref=None):
        self.dataset, self.cls, self.label = dataset, cls, label
        self.f, self.retina, self.anchors, self.ref = f, retina, anchors, ref or {}

    @property
    def n(self):
        return self.f['spk_L'].size


# ---------------------------------------------------------------- events ---
def n1_events(a, m, data, meta):
    out = []
    for t, tm in zip(m['trials'], meta['trials']):
        i = t['index']
        steps = range(t['record_first_step'], t['end_step'])
        f = frame(a, list(steps))
        retina = {'theta': data['%d_theta' % i], 'theta_dot': data['%d_theta_dot' % i],
                  'azimuth': data['%d_azimuth' % i]}
        onset = tm['click_tick'] if tm['click_tick'] is not None else tm['window_start']
        out.append(Event('n1', t['kind'], 'n1_%d' % i, f, retina,
                         {'onset': onset, 'window': (tm['window_start'], tm['window_end'])},
                         {'steps': list(steps)}))
    return out


def session_rows(name):
    path = ROOT / 'results/game/sessions' / name
    rows = [json.loads(l) for l in (path / 'ticks.jsonl').open(encoding='utf-8')]
    eps = {}
    for r in rows:
        eps.setdefault(r['episode'], []).append(r)
    strikes = json.loads((path / 'strikes.json').read_text(encoding='utf-8'))
    return eps, strikes


def drive_of(r):
    v = r['visual_input']
    return v['loomL'] + v['loomR'] + v['threatL'] + v['threatR']


def bout_start(rows, e, floor, gap=GAP):
    i, quiet, first = e, 0, None
    while i >= floor:
        if drive_of(rows[i]) > EPS:
            first, quiet = i, 0
        else:
            quiet += 1
            if quiet >= gap and first is not None:
                break
        i -= 1
    return first


def human_events(sess, name, a, m):
    eps, strikes = session_rows(name)
    row_step = {e['episode']: e['row_step'] for e in m['episodes']}
    out = []

    def make(cls, label, ep, r0, r1, anchors):
        rows = eps[ep][r0:r1 + 1]
        steps = [row_step[ep][k] for k in range(r0, r1 + 1)]
        keep = [j for j, s in enumerate(steps) if s >= 0]
        f = frame(a, [steps[j] for j in keep])
        rows = [rows[j] for j in keep]
        retina = {k: np.array([r['retina'][k] for r in rows]) for k in ('theta', 'theta_dot', 'azimuth')}
        geo = {'distance': np.array([math.hypot(r['fly']['x'] - r['swatter']['x'],
                                                r['fly']['y'] - r['swatter']['y']) for r in rows]),
               'swatter_speed': np.array([r['swatter']['speed'] for r in rows]),
               'height': np.array([r['swatter']['height'] for r in rows]),
               'tick': np.array([r['tick'] for r in rows]),
               'escape': np.array([bool(r['action']['escape']) for r in rows])}
        # Anchors are row offsets from r0; re-index them onto brain-stepped rows only.
        anchors = {k: (None if v is None else int(np.searchsorted(keep, v)))
                   for k, v in anchors.items()}
        out.append(Event(sess, cls, label, f, retina, anchors, {'episode': ep, 'rows': (r0, r1),
                                                                'geometry': geo,
                                                                'steps': [steps[j] for j in keep]}))

    # Recorded escapes, split by strike phase (direct strike) or not (hover / chase).
    for ep, rows in eps.items():
        seg = 0
        for i, r in enumerate(rows):
            if not (r['action']['escape'] and r['neural']['brain_stepped']):
                continue
            b = bout_start(rows, i, seg)
            if b is not None:
                cls = 'human_strike_escape' if r['swatter']['phase'] in STRIKE_PHASES \
                    else 'human_hover_escape'
                make(cls, '%s_e%d_r%d' % (sess, ep, i), ep, b, i, {'onset': 0, 'escape': i - b})
            seg = i + 1
    # Direct strikes: 0.5 s before the click to resolution.
    for s in strikes:
        rows = eps[s['episode']]
        idx = {r['tick']: k for k, r in enumerate(rows)}
        c, r = idx[s['start_tick']], idx[s['resolved_tick']]
        a0 = max(0, c - 25)
        esc = idx.get(s['escape_tick']) if s.get('escape_tick') is not None else None
        make('human_direct_strike', '%s_s%d_%d' % (sess, s['episode'], s['strike_id']),
             s['episode'], a0, r, {'onset': c - a0, 'click': c - a0,
                                   'escape': None if esc is None else esc - a0,
                                   'preexisting': 1 if s.get('escape_preexisting') else 0})
    if sess == 'n2b':
        rows = eps[5]
        idx = {r['tick']: k for k, r in enumerate(rows)}
        make('slow_close', 'n2b_e5_610_669', 5, idx[610], idx[670],
             {'onset': 0, 'closest': 623 - 610, 'reversal': 670 - 610, 'escape': 670 - 610})
        make('chase_before_589', 'n2b_e5_570_589', 5, idx[570], idx[589],
             {'onset': 0, 'escape': 589 - 570})
        rows1 = eps[1]
        k = next(i for i, r in enumerate(rows1) if any(e['type'] == 'voluntary_takeoff'
                                                       for e in r['lifecycle']['events']))
        make('voluntary_takeoff_reference', 'n2b_e1_voluntary', 1, k - 50, min(len(rows1) - 1, k + 25),
             {'onset': 0, 'takeoff': 50})
    if sess == 'strict_n2':
        make('far_perched_reference', 'strict_e1_far_perched', 1, 2434, 2528, {'onset': 0})
    return out


# ---------------------------------------------------------------- metrics ---
def runs(mask):
    out, n = [], 0
    for v in mask:
        if v:
            n += 1
        elif n:
            out.append(n)
            n = 0
    if n:
        out.append(n)
    return out


def retina_metrics(e):
    th, td, az = e.retina['theta'], e.retina['theta_dot'], e.retina['azimuth']
    sig = td[np.abs(td) > 0.02]
    flips = int(np.sum(np.diff(np.sign(sig)) != 0)) if sig.size > 1 else 0
    dur = e.n * DT
    pos = td > EPS
    side = np.sign(az)
    return {'theta_mean': float(th.mean()), 'theta_max': float(th.max()),
            'theta_dot_peak': float(td.max()), 'positive_fraction': float(pos.mean()),
            'longest_positive_run_s': (max(runs(pos)) if pos.any() else 0) * DT,
            'sign_flips_per_s': flips / dur,
            'integrated_positive_growth_rad': float(np.clip(td, 0, None).sum() * DT),
            'large_theta_static_s': float(((th > LARGE_THETA) & (np.abs(td) < STATIC_THETA_DOT)).sum() * DT),
            'side_switches_per_s': float(np.sum(np.diff(side[side != 0]) != 0) / dur),
            'duration_s': dur}


def encoder_metrics(e):
    f = e.f
    loom = f['drive_loomL'] + f['drive_loomR']
    threat = f['drive_threatL'] + f['drive_threatR']
    drive = loom + threat
    sl = f['LPLC2_L'] + f['LC4_L']
    sr = f['LPLC2_R'] + f['LC4_R']
    tot = sl + sr
    on = drive > EPS
    return {'drive_positive_ticks': int(on.sum()), 'loom_drive_peak': float(loom.max()),
            'threat_drive_peak': float(threat.max()),
            'integrated_drive': float(drive.sum()),
            'longest_drive_burst_s': (max(runs(on)) if on.any() else 0) * DT,
            'drive_bursts': len(runs(on)),
            'sensory_spikes_total': int(tot.sum()),
            'sensory_spikes_peak_per_tick': int(tot.max()),
            'sensory_spikes_per_drive_tick': float(tot[on].mean()) if on.any() else 0.0,
            'lr_asymmetry': float(abs(sl.sum() - sr.sum()) / max(1, tot.sum())),
            'drive_side_switches': int(np.sum(np.diff(np.sign(
                (f['drive_loomR'] + f['drive_threatR'] - f['drive_loomL'] - f['drive_threatL'])[on])) != 0))
            if on.sum() > 1 else 0}


def transfer_metrics(e):
    f = e.f
    spk = f['spk_L'] + f['spk_R']
    drive = f['drive_loomL'] + f['drive_loomR'] + f['drive_threatL'] + f['drive_threatR']
    on = np.flatnonzero(drive > EPS)
    times = [j for j in range(e.n) for _ in range(int(spk[j]))]
    first = None
    if on.size:
        after = [t for t in times if t >= on[0]]
        first = (after[0] - on[0]) * DT if after else None
    isi = [(b - a) * DT for a, b in zip(times, times[1:])]
    kick_needed = 0
    for side in 'LR':
        s = np.flatnonzero(f['spk_' + side] > 0)
        for j in s:
            if f['kick_' + side][j] and f['v_pre_' + side][j] - KICK < 1.0:
                kick_needed += 1
    enc = np.maximum(f['cur_enc_L'], f['cur_enc_R'])
    return {'dnp01_spikes_L': int(f['spk_L'].sum()), 'dnp01_spikes_R': int(f['spk_R'].sum()),
            'first_spike_latency_from_drive_s': first,
            'isi_median_s': med(isi), 'spike_probability_per_tick': float(spk.sum() / e.n),
            'spikes_per_1000_sensory_spikes': float(1000 * spk.sum() / max(1, (
                f['LPLC2_L'] + f['LPLC2_R'] + f['LC4_L'] + f['LC4_R']).sum())),
            'encoder_current_peak_V': float(enc.max()),
            'inhibitory_current_min_V': float(min(f['cur_inh_L'].min(), f['cur_inh_R'].min())),
            'spikes_needing_noise_kick': kick_needed}


def stimulus_view(e):
    """N1 metrics cover the labelled stimulus (onset to window end), not the static
    pre-stimulus hover; human events are already bout windows."""
    if e.dataset != 'n1':
        return e
    a, b = e.anchors['onset'], e.anchors['window'][1] + 1
    return Event(e.dataset, e.cls, e.label, {k: v[a:b] for k, v in e.f.items()},
                 {k: v[a:b] for k, v in e.retina.items()}, {'onset': 0}, e.ref)


def summarise(events, fn):
    by = {}
    for e in events:
        by.setdefault(e.cls, []).append(fn(stimulus_view(e)))
    out = {}
    for cls, rows in by.items():
        keys = rows[0].keys()
        out[cls] = {'n': len(rows)}
        for k in keys:
            vals = [r[k] for r in rows if r[k] is not None]
            out[cls][k] = {'median': med(vals), 'p10': q(vals, 10), 'p90': q(vals, 90)} if vals else None
    return out


# ---------------------------------------------------------------- transfer curves ---
def transfer_curves(frames):
    """Pooled per-tick relationships (both sides; the encoder wiring is ipsilateral)."""
    cols = [[], [], [], [], [], []]
    for f in frames:
        for s in 'LR':
            sens = f['LPLC2_' + s] + f['LC4_' + s]
            drive = f['drive_loom' + s] + f['drive_threat' + s]
            for c, v in zip(cols, (drive[:-1], sens[:-1], f['cur_enc_' + s][1:], f['v_old_' + s][1:],
                                   f['spk_' + s][1:], f['cur_inh_' + s][1:])):
                c.append(v)
    drive, sens, cur, vold, spk, inh = (np.concatenate(c) for c in cols)
    out = {'ticks': int(drive.size), 'drive_to_sensory': [], 'sensory_to_current': [],
           'current_to_spike_by_voltage': []}
    for lo, hi in ((0, 0), (EPS, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 0.4), (0.4, 0.8), (0.8, 2.0)):
        m = (drive < EPS) if hi == 0 else (drive >= lo) & (drive < hi)
        if m.sum():
            out['drive_to_sensory'].append({'drive': [lo, hi], 'ticks': int(m.sum()),
                                            'sensory_spikes_mean': float(sens[m].mean()),
                                            'p_sensory_ge_40': float((sens[m] >= 40).mean()),
                                            'p_dnp01_spike_next_tick': float(spk[m].mean())})
    for lo, hi in ((0, 1), (1, 5), (5, 20), (20, 50), (50, 100), (100, 200)):
        m = (sens >= lo) & (sens < hi)
        if m.sum():
            out['sensory_to_current'].append({'sensory_spikes': [lo, hi], 'ticks': int(m.sum()),
                                              'encoder_current_V_mean': float(cur[m].mean()),
                                              'p_dnp01_spike_next_tick': float(spk[m].mean()),
                                              'inhibitory_current_V_mean': float(inh[m].mean())})
    for clo, chi in ((0, 0.05), (0.05, 0.2), (0.2, 0.4), (0.4, 0.7), (0.7, 2.0)):
        for vlo, vhi, lab in ((-1, 0.3, 'recovering (v_old < 0.3)'), (0.3, 0.6, 'v_old 0.3-0.6'),
                              (0.6, 2, 'near rest (v_old >= 0.6)')):
            m = (cur >= clo) & (cur < chi) & (vold >= vlo) & (vold < vhi)
            if m.sum() >= 5:
                out['current_to_spike_by_voltage'].append({'encoder_current_V': [clo, chi],
                                                           'voltage': lab, 'ticks': int(m.sum()),
                                                           'p_spike': float(spk[m].mean())})
    return out


# ---------------------------------------------------------------- N0 background ---
def n0_background(a, m):
    rec = np.zeros(a['spk_L'].size, bool)
    for t in m['trials']:
        rec[t['record_first_step']:t['end_step']] = True
    idx = np.flatnonzero(rec)
    L, R = a['spk_L'][idx] > 0, a['spk_R'][idx] > 0
    n = idx.size
    out = {'ticks': int(n), 'minutes': n * DT / 60,
           'rate_L_hz': float(L.sum() / (n * DT)), 'rate_R_hz': float(R.sum() / (n * DT)),
           'same_tick_bilateral_pairs': int((L & R).sum()),
           'same_tick_expected_if_independent': float(L.mean() * R.mean() * n),
           'encoder_drive_max': float(max(a[k][idx].max() for k in
                                          ('drive_loomL', 'drive_loomR', 'drive_threatL', 'drive_threatR')))}
    # Sensory spontaneous activity (per side, LPLC2 + LC4 chosen cells).
    sl = a['LPLC2_L'][idx] + a['LC4_L'][idx]
    sr = a['LPLC2_R'][idx] + a['LC4_R'][idx]
    per_side = np.concatenate([sl, sr])
    out['sensory_spikes_per_side_tick'] = {'mean': float(per_side.mean()), 'max': int(per_side.max()),
                                           'p99_99': float(np.percentile(per_side, 99.99))}
    w3 = np.concatenate([np.convolve(x, np.ones(3), 'valid') for x in (sl, sr)])
    out['sensory_spikes_per_side_60ms_max'] = int(w3.max())
    # Cross-correlogram L vs R (counts of R spikes at lag relative to L spikes).
    lags = range(-10, 11)
    ccg = {}
    for lag in lags:
        if lag >= 0:
            ccg[lag] = int((L[:n - lag] & R[lag:]).sum())
        else:
            ccg[lag] = int((L[-lag:] & R[:n + lag]).sum())
    out['lr_cross_correlogram'] = ccg
    out['lr_expected_per_lag'] = float(L.mean() * R.mean() * n)
    # ISIs per side and pooled (recorded ticks are contiguous within a trial).
    isi = {}
    for name, s in (('L', L), ('R', R), ('pooled', L | R)):
        v = []
        for t in m['trials']:
            seg = (a['spk_L'] if name == 'L' else a['spk_R'] if name == 'R' else
                   a['spk_L'] + a['spk_R'])[t['record_first_step']:t['end_step']]
            times = np.flatnonzero(seg > 0)
            v.extend(np.diff(times).tolist())
        v = np.array(v)
        isi[name] = {'n': int(v.size), 'median_ticks': float(np.median(v)),
                     'le_4_ticks': int((v <= 4).sum()), 'le_2_ticks': int((v <= 2).sum()),
                     'min_ticks': int(v.min())}
    out['isi'] = isi
    # Spike causes.
    causes = Counter()
    kick_recent = Counter()
    vold = []
    for side in 'LR':
        s = idx[a['spk_' + side][idx] > 0]
        for j in s:
            kick = a['kick_' + side][j] > 0
            syn = a['cur_enc_' + side][j] + a['cur_exc_' + side][j] + a['cur_inh_' + side][j]
            base = a['v_old_' + side][j] * DECAY + TONIC
            vold.append(a['v_old_' + side][j])
            if kick and base + syn < 1.0:
                if base + KICK >= 1.0:
                    causes['noise kick alone suffices (synaptic input not needed)'] += 1
                else:
                    causes['noise kick + net excitatory synaptic input, both needed'] += 1
            elif kick:
                causes['synaptic input alone suffices, kick also present'] += 1
            else:
                causes['synaptic input without noise kick'] += 1
            prev = a['kick_' + side][j - 1] > 0 if j > 0 else False
            kick_recent['kick on previous tick' if prev else 'no kick on previous tick'] += 1
    out['spike_causes'] = dict(causes)
    out['previous_tick_kick'] = dict(kick_recent)
    out['v_old_at_spike'] = {'median': float(np.median(vold)), 'p10': float(np.percentile(vold, 10))}
    # Upstream partner types contributing positive current at spontaneous spikes.
    rec_steps = set(idx.tolist())
    types = Counter()
    ptype = m['partner_types']
    for sp in m['spike_partners']:
        if sp['step'] not in rec_steps:
            continue
        for j, c in sp['partners']:
            if c > 0:
                types[ptype[str(j)][0] + ' (' + ptype[str(j)][2] + ')'] += c
    out['top_excitatory_partner_types_at_spikes_V'] = dict(types.most_common(12))
    # Pairs of DNp01 spikes within 4 ticks (the events that lift the trace to >= 1.45).
    pairs = Counter()
    for t in m['trials']:
        sl_, sr_ = a['spk_L'][t['record_first_step']:t['end_step']], a['spk_R'][t['record_first_step']:t['end_step']]
        ev = sorted([(j, 'L') for j in np.flatnonzero(sl_)] + [(j, 'R') for j in np.flatnonzero(sr_)])
        for (j1, s1), (j2, s2) in zip(ev, ev[1:]):
            if j2 - j1 <= 4:
                pairs['%s, lag %d' % ('bilateral' if s1 != s2 else 'same side', j2 - j1)] += 1
    out['close_pairs_within_4_ticks'] = dict(sorted(pairs.items()))
    # Voltage distribution of DNp01 (how close to threshold it sits in N0).
    v = np.concatenate([a['v_pre_L'][idx], a['v_pre_R'][idx]])
    out['dnp01_v_pre'] = {'p50': float(np.median(v)), 'p99': float(np.percentile(v, 99)),
                          'fraction_above_0_95': float((v >= 0.95).mean())}
    return out, idx


# ---------------------------------------------------------------- separability ---
def level_detections(e, env):
    """First tick (relative to the event onset) at which each level exceeds its N0
    envelope. Retina/encoder are offline levels; C/D are DNp01; A/B are not policy inputs."""
    f, onset = e.f, e.anchors.get('onset') or 0
    td = e.retina['theta_dot']
    sens = np.maximum(f['LPLC2_L'] + f['LC4_L'], f['LPLC2_R'] + f['LC4_R'])
    drive = f['drive_loomL'] + f['drive_loomR'] + f['drive_threatL'] + f['drive_threatR']
    spk = f['spk_L'] + f['spk_R']
    times = [j for j in range(e.n) for _ in range(int(spk[j]))]
    trace = np.zeros(e.n)
    tr = 0.0
    for j in range(e.n):
        tr = tr * DECAY + spk[j]
        trace[j] = tr

    def first(mask):
        k = np.flatnonzero(mask[onset:])
        return int(k[0]) if k.size else None
    three = None
    for k in range(2, len(times)):
        if times[k] >= onset and times[k] - times[k - 2] < 10:
            three = times[k] - onset
            break
    two = next((times[k] - onset for k in range(1, len(times))
                if times[k] >= onset and times[k] - times[k - 1] <= 4), None)
    first_spk = next((t - onset for t in times if t >= onset), None)
    # Lateralized DNp01 (both cells are already in the policy observation): the first
    # sample at which one side holds two spikes within 5 samples; N0 never does.
    lat = None
    for side in 'LR':
        t = np.flatnonzero(f['spk_' + side] > 0)
        ok = [int(b) for a_, b in zip(t, t[1:]) if b - a_ < 5 and b >= onset]
        if ok:
            lat = ok[0] - onset if lat is None else min(lat, ok[0] - onset)
    return {'A_retina_positive_expansion': first(td > max(env['theta_dot'], EPS)),
            'B_encoder_drive': first(drive > max(env['drive'], EPS)),
            'B_sensory_spikes_above_n0_max': first(sens > env['sensory_per_side']),
            'C_first_dnp01_spike': first_spk,
            'C_second_dnp01_spike_within_80ms (not N0-safe)': two,
            'C_three_dnp01_spikes_in_200ms (N0-safe floor)': three,
            'C_lateral_two_same_side_spikes_in_100ms': lat,
            'D_trace_ge_2_10': first(trace >= FAST - 1e-9)}


def separability(events, env):
    by = {}
    for e in events:
        d = level_detections(e, env)
        by.setdefault(e.cls, []).append(d)
    out = {}
    for cls, rows in by.items():
        out[cls] = {'n': len(rows)}
        for k in rows[0]:
            v = [r[k] for r in rows]
            got = [x for x in v if x is not None]
            out[cls][k] = {'detected': len(got), 'median_s': None if not got else med(got) * DT,
                           'p90_s': None if not got else q(got, 90) * DT}
        gains = [r['C_three_dnp01_spikes_in_200ms (N0-safe floor)'] - r['B_sensory_spikes_above_n0_max']
                 for r in rows if r['C_three_dnp01_spikes_in_200ms (N0-safe floor)'] is not None
                 and r['B_sensory_spikes_above_n0_max'] is not None]
        out[cls]['sensory_level_lead_over_dnp01_floor_s'] = {'n': len(gains), 'median': None if not gains
                                                              else med(gains) * DT,
                                                              'p90': None if not gains else q(gains, 90) * DT}
    return out


# ---------------------------------------------------------------- other DNs (exploratory) ---
_SPIKE_CACHE = {}


def spikes_index(a):
    key = id(a)
    if key not in _SPIKE_CACHE:
        _SPIKE_CACHE[key] = dn_spikes_by_step(a)
    return _SPIKE_CACHE[key]


def cell_counts(a, steps, cells):
    """(len(steps), len(cells)) spike counts of the chosen cells (DNp01 included)."""
    _, dc, b = spikes_index(a)
    pos = {int(c): i for i, c in enumerate(cells)}
    out = np.zeros((len(steps), len(cells)), np.int16)
    for j, st in enumerate(steps):
        for c in dc[b[st]:b[st + 1]]:
            i = pos.get(int(c))
            if i is not None:
                out[j, i] += 1
    return out


def windowed(counts, w):
    c = np.cumsum(np.vstack([np.zeros((1, counts.shape[1]), np.int32), counts.astype(np.int32)]), 0)
    lo = np.maximum(np.arange(counts.shape[0]) + 1 - w, 0)
    return c[1:] - c[lo]


def n0_segments(m, first, last):
    return [list(range(t['record_first_step'], t['end_step'])) for t in m['trials'][first:last]]


def envelope(a, segs, cells, windows, pooled):
    env = {w: 0 for w in windows}
    for sg in segs:
        c = cell_counts(a, sg, cells)
        if pooled:
            c = c.sum(1, keepdims=True)
        for w in windows:
            env[w] = max(env[w], int(windowed(c, w).max()))
    return env


def n0_events(a, segs, cells, env, pooled):
    """Firings (with a 20-sample refractory) where any window exceeds the envelope."""
    n = 0
    for sg in segs:
        c = cell_counts(a, sg, cells)
        if pooled:
            c = c.sum(1, keepdims=True)
        hit = np.zeros(c.shape[0], bool)
        for w, mx in env.items():
            hit |= (windowed(c, w) > mx).any(1)
        k = 0
        while k < hit.size:
            if hit[k]:
                n += 1
                k += 20
            else:
                k += 1
    return n


def detect(a, event, cells, env, pooled):
    c = cell_counts(a, event.ref['steps'], cells)
    if pooled:
        c = c.sum(1, keepdims=True)
    onset = event.anchors.get('onset') or 0
    best = None
    for w, mx in env.items():
        k = np.flatnonzero((windowed(c, w) > mx).any(1)[onset:])
        if k.size:
            best = int(k[0]) if best is None else min(best, int(k[0]))
    return best


def dn_exploratory(n0a, n0m, n1a, events, sims, env_levels):
    """Offline only. Envelopes from N0 trials 0-74; N0 events counted on 0-74 and 75-149."""
    from scipy import sparse
    from game.fly import build_brain
    from game.perception import RetinalEncoder
    from game.session import load_config
    cfg = load_config(ROOT / 'game_room_config.json')
    brain = build_brain(cfg, ROOT, warmup=False)
    enc = RetinalEncoder(brain, cfg)
    W = sparse.csc_matrix((brain.weights, brain.indices, brain.indptr), shape=(brain.n, brain.n)).tocsr()
    enc_cells = np.concatenate([np.asarray(enc._fd.cells[ch][s]) for ch in ('loom', 'threat') for s in 'LR'])
    dn = brain.cells(['descending_neuron'])
    wsum = np.asarray(W[dn][:, enc_cells].sum(1)).ravel()
    direct = [int(c) for c, w in zip(dn, wsum) if w > 0.05]
    targets = sorted(({'cell': int(c), 'type': str(brain.cell_type[c]), 'side': str(brain.side[c]),
                       'encoder_weight_sum': float(w)} for c, w in zip(dn, wsum) if w > 0.05),
                     key=lambda r: -r['encoder_weight_sum'])
    by_type = {}
    for c in direct:
        by_type.setdefault(str(brain.cell_type[c]), []).append(c)
    windows = (1, 3, 5, 10)
    dnp01 = [int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0])]
    readouts = [('DNp01 summed L+R (policy trace basis)', dnp01, True),
                ('DNp01 lateralized (each side separately)', dnp01, False)]
    for t, cs in sorted(by_type.items()):
        if t != 'DNp01':
            readouts.append((t + ' lateralized', cs, False))
    readouts.append(('pooled: all %d DN cells with direct LC4/LPLC2 input' % len(direct), direct, True))
    readouts.append(('each of the %d direct-input DN cells separately' % len(direct), direct, False))
    sel_segs, held_segs = n0_segments(n0m, 0, 75), n0_segments(n0m, 75, 150)
    classes = ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach',
               'human_direct_strike', 'human_strike_escape', 'human_hover_escape', 'chase_before_589',
               'slow_close', 'far_perched_reference', 'voluntary_takeoff_reference')
    src = {'n1': n1a, 'strict_n2': sims['strict_n2'][0], 'n2b': sims['n2b'][0]}
    rows = []
    for name, cells, pooled in readouts:
        env = envelope(n0a, sel_segs, cells, windows, pooled)
        row = {'readout': name, 'cell_types': sorted({str(brain.cell_type[c]) for c in cells}),
               'cells': len(cells), 'pooled': pooled,
               'n0_selection_half_envelope': env,
               'n0_selection_half_events': n0_events(n0a, sel_segs, cells, env, pooled),
               'n0_held_out_half_events': n0_events(n0a, held_segs, cells, env, pooled),
               'classes': {}}
        for cls in classes:
            evs = [e for e in events if e.cls == cls]
            d = [detect(src[e.dataset], e, cells, env, pooled) for e in evs]
            got = [x for x in d if x is not None]
            row['classes'][cls] = {'n': len(evs), 'detected': len(got),
                                   'median_s': med(got) * DT if got else None,
                                   'p90_s': q(got, 90) * DT if got else None}
        rows.append(row)
        c = row['classes']
        print('%-58s env %s N0 sel %d held %d | S %d %.2f | M %d %.2f | w %d g %d a %d | slow %s far %d vol %d'
              % (name[:58], env, row['n0_selection_half_events'], row['n0_held_out_half_events'],
                 c['strong_direct']['detected'], c['strong_direct']['median_s'] or -1,
                 c['medium_committed']['detected'], c['medium_committed']['median_s'] or -1,
                 c['weak_approach']['detected'], c['glancing_pass']['detected'],
                 c['aborted_approach']['detected'], c['slow_close']['median_s'],
                 c['far_perched_reference']['detected'], c['voluntary_takeoff_reference']['detected']),
              flush=True)
    return {'note': 'offline exploratory only; N0 envelopes from N0 trials 0-74, events also counted '
                    'on trials 75-149 (held out); not a decoder proposal',
            'direct_encoder_targets': targets, 'readouts': rows}


# ---------------------------------------------------------------- main ---
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, default=SIM / 'diagnosis.json')
    args = ap.parse_args()

    n0a, n0m = load_sim('n0')
    n1a, n1m = load_sim('n1')
    data = np.load(N1_DIR / 'trials.npz')
    meta = json.loads((N1_DIR / 'trials_meta.json').read_text(encoding='utf-8'))
    result = {'label': 'M1.8-N4A sensory-to-descending diagnosis; research only; offline data only',
              'resimulation_exactness': {
                  'n0': [n0m['exact_trials'], len(n0m['trials'])],
                  'n1': [n1m['exact_trials'], len(n1m['trials'])]}}
    events = n1_events(n1a, n1m, data, meta)
    sims = {}
    for sess, name in SESSIONS.items():
        a, m = load_sim('session_' + name)
        sims[sess] = (a, m)
        result['resimulation_exactness'][sess] = [m['dnp01_exact_rows'], m['stepped_rows'],
                                                  m['sensory_exact_rows']]
        events += human_events(sess, name, a, m)
    result['model_mismatch_steps'] = {'n0': int(n0a['model_mismatch'].sum()),
                                      'n1': int(n1a['model_mismatch'].sum()),
                                      **{s: int(v[0]['model_mismatch'].sum()) for s, v in sims.items()}}
    result['inputs'] = {p.name: sha256(p) for p in sorted(SIM.glob('*.npz'))}
    print('events:', Counter(e.cls for e in events), flush=True)

    # ---- N0 background
    bg, idx_rec = n0_background(n0a, n0m)
    result['n0_background'] = bg
    print('N0 background:', json.dumps({k: bg[k] for k in ('rate_L_hz', 'rate_R_hz',
                                                            'same_tick_bilateral_pairs',
                                                            'same_tick_expected_if_independent',
                                                            'spike_causes', 'close_pairs_within_4_ticks')}),
          flush=True)
    # N0-equivalent static-hover Retina: the settled pre-click samples of N1 committed
    # trials use the same fixed-fly protocol (paddle hovering, static).
    pre = [e for e in events if e.cls in ('strong_direct', 'medium_committed')]
    static_theta = np.concatenate([e.retina['theta'][:e.anchors['onset']] for e in pre])
    static_td = np.concatenate([e.retina['theta_dot'][:e.anchors['onset']] for e in pre])
    result['n0_equivalent_static_retina'] = {'theta_min': float(static_theta.min()),
                                             'theta_max': float(static_theta.max()),
                                             'theta_dot_abs_max': float(np.abs(static_td).max())}
    env = {'theta_dot': 0.0, 'drive': bg['encoder_drive_max'],
           'sensory_per_side': bg['sensory_spikes_per_side_tick']['max']}
    result['n0_envelopes'] = env

    # ---- per-event metrics by class
    result['retina'] = summarise(events, retina_metrics)
    result['encoder'] = summarise(events, encoder_metrics)
    result['transfer'] = summarise(events, transfer_metrics)
    # Whole recordings, not overlapping events: all N1 trials, both human sessions, N0.
    skip = ('dn_steps', 'dn_cells')
    n1_frames = [e.f for e in events if e.dataset == 'n1']
    human_frames = [{k: v for k, v in sims[s][0].items() if k not in skip} for s in sims]
    n0_frame = [{k: v[idx_rec] for k, v in n0a.items() if k not in skip}]
    result['transfer_curves'] = {'n1_and_human': transfer_curves(n1_frames + human_frames),
                                 'n1_only': transfer_curves(n1_frames),
                                 'human_only': transfer_curves(human_frames),
                                 'n0_only': transfer_curves(n0_frame)}
    result['separability'] = separability(events, env)
    result['recorded_escape_offset_from_onset_s'] = {
        cls: {'n': len(v), 'median': med(v)}
        for cls, v in ((c, [e.anchors['escape'] * DT for e in events if e.cls == c
                            and e.anchors.get('escape') is not None])
                       for c in ('human_direct_strike', 'human_strike_escape', 'human_hover_escape',
                                 'chase_before_589', 'slow_close'))}

    # ---- hover geometry: expansion per unit swatter speed versus horizontal distance
    geo = []
    for e in events:
        g = e.ref.get('geometry')
        if g is None or e.cls not in ('human_hover_escape', 'slow_close', 'chase_before_589'):
            continue
        for d, sp, td, h in zip(g['distance'], g['swatter_speed'], e.retina['theta_dot'], g['height']):
            if sp > 50 and h >= 300:
                geo.append((d, abs(td) / sp))
    geo = np.array(geo)
    bins = []
    for lo, hi in ((0, 50), (50, 100), (100, 200), (200, 400), (400, 800)):
        m_ = (geo[:, 0] >= lo) & (geo[:, 0] < hi)
        if m_.sum():
            bins.append({'horizontal_distance': [lo, hi], 'ticks': int(m_.sum()),
                         'median_abs_theta_dot_per_1000_units_per_s': float(np.median(geo[m_, 1]) * 1000)})
    result['hover_expansion_efficiency'] = bins

    # ---- slow-close timeline (full per-tick)
    sc = next(e for e in events if e.cls == 'slow_close')
    result['slow_close_ticks'] = [{
        'tick': int(sc.ref['geometry']['tick'][j]), 'theta': round(float(sc.retina['theta'][j]), 4),
        'theta_dot': round(float(sc.retina['theta_dot'][j]), 3),
        'side': 'R' if sc.retina['azimuth'][j] >= 0 else 'L',
        'drive': round(float(sc.f['drive_loomL'][j] + sc.f['drive_loomR'][j]
                             + sc.f['drive_threatL'][j] + sc.f['drive_threatR'][j]), 3),
        'sensory_L': int(sc.f['LPLC2_L'][j] + sc.f['LC4_L'][j]),
        'sensory_R': int(sc.f['LPLC2_R'][j] + sc.f['LC4_R'][j]),
        'dnp01_L': int(sc.f['spk_L'][j]), 'dnp01_R': int(sc.f['spk_R'][j]),
        'v_old_L': round(float(sc.f['v_old_L'][j]), 3), 'v_old_R': round(float(sc.f['v_old_R'][j]), 3),
        'cur_enc_L': round(float(sc.f['cur_enc_L'][j]), 3), 'cur_enc_R': round(float(sc.f['cur_enc_R'][j]), 3),
        'kick_L': int(sc.f['kick_L'][j]), 'kick_R': int(sc.f['kick_R'][j]),
        'distance': round(float(sc.ref['geometry']['distance'][j]), 1)} for j in range(sc.n)]

    # ---- exploratory: other descending neurons (offline only; nothing is wired anywhere)
    result['descending_exploratory'] = dn_exploratory(n0a, n0m, n1a, events, sims, env)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')
    print('written', args.out)


if __name__ == '__main__':
    main()
