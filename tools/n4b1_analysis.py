"""M1.8-N4B1 research analysis (called by tools/n4b1_lateral.py). Research only.

mechanism   why one DNp01 cell rarely fires twice quickly under N0 (original instrumented
            N0 re-simulation from tools/n4_resimulate.py)
evaluate    frozen candidates and references on original N0, fresh N0, N1 (re-simulated
            per-side spikes, verified exact in N4A) and both human sessions (recorded
            per-side DNp01, open-loop, synced per segment as in N3)
closed-loop research-only closed-loop ROOM runs using tools/n2_closed_loop.py scenarios,
            including the corrected zero-loom perched fixture; runtime code untouched
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from tools import n4b1_lateral as L  # noqa: E402

DT = 0.02
N4 = ROOT / 'artifacts/m1_8_n4'
N1_DIR = ROOT / 'artifacts/m1_8_loom_robustness'
SESSIONS = {'strict_n2': ROOT / 'results/game/sessions/20260923T005351.731330Z-38255ec8',
            'n2b': ROOT / 'results/game/sessions/20260924T000111.561327Z-c337a721'}
TONIC, KICK, P_KICK, DECAY = 0.14, 0.22, 1.2 * 0.02, L.DECAY
STRIKE_PHASES = ('windup', 'active', 'commit', 'fast_swing', 'active_contact')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def med(v):
    v = [x for x in v if x is not None]
    return float(np.median(v)) if v else None


def pct(v, p):
    v = [x for x in v if x is not None]
    return float(np.percentile(v, p)) if v else None


def traces_from_spikes(spk):
    """flybrain.Trace per side: float32, x decay then +1 per spike."""
    d = np.float32(DECAY)
    t = np.float32(0.0)
    out = np.empty(spk.size)
    for i in range(spk.size):
        t = np.float32(t * d)
        if spk[i]:
            t = np.float32(t + np.float32(spk[i]))
        out[i] = float(t)
    return out


# ------------------------------------------------------------------ mechanism ---
def min_kicks_needed(max_lag=12):
    """Noise only, no synaptic input: kicks needed to reach threshold k samples after a
    reset, with the kicks placed as late as possible (the most favourable placement)."""
    a = DECAY
    out = {}
    for k in range(1, max_lag + 1):
        base = TONIC * (1 - a ** k) / (1 - a)
        need = None
        for m in range(0, k + 1):
            if base + KICK * sum(a ** j for j in range(m)) >= 1.0:
                need = m
                break
        out[k] = need
    return out


def mechanism():
    a = dict(np.load(N4 / 'n0.npz'))
    m = json.loads((N4 / 'n0.json').read_text(encoding='utf-8'))
    rec = np.zeros(a['spk_L'].size, bool)
    for t in m['trials']:
        rec[t['record_first_step']:t['end_step'] - 12] = True     # room for a 12-sample look-ahead
    out = {'noise_kick_probability_per_sample': P_KICK, 'kick_amplitude_V': KICK,
           'rest_voltage_V': TONIC / (1 - DECAY), 'rest_plus_one_kick_V': TONIC / (1 - DECAY) + KICK,
           'kicks_needed_after_reset_noise_only': min_kicks_needed()}
    lag_v = {k: [] for k in range(1, 11)}
    syn_rec, spikes = [], []
    observed_kick = []
    for side in 'LR':
        s = np.flatnonzero((a['spk_' + side] > 0) & rec)
        syn = a['cur_enc_' + side] + a['cur_exc_' + side] + a['cur_inh_' + side]
        for j in s:
            spikes.append((side, int(j), syn[j + 1:j + 13].copy()))
            for k in range(1, 11):
                lag_v[k].append(float(a['v_old_' + side][j + k]))
            syn_rec.append(syn[j + 1:j + 13])
            observed_kick.append(a['kick_' + side][j + 1:j + 13])
    syn_rec = np.array(syn_rec)
    out['spikes_analysed'] = len(spikes)
    # v_old at lag k is the voltage before step k; it is the recovery trajectory.
    out['recovery_voltage_after_spike'] = {k: {'median': float(np.median(v)), 'p99': float(np.percentile(v, 99)),
                                               'max': float(np.max(v))} for k, v in lag_v.items()}
    out['synaptic_input_during_recovery_V'] = {'median': float(np.median(syn_rec)),
                                               'p99_9': float(np.percentile(syn_rec, 99.9)),
                                               'max': float(syn_rec.max()), 'min': float(syn_rec.min())}
    out['observed_kicks_during_recovery_fraction'] = float(np.mean(observed_kick))
    # Probability of at least two kicks within k samples (pure noise statistics).
    out['p_two_or_more_kicks_within'] = {k: float(1 - (1 - P_KICK) ** k - k * P_KICK * (1 - P_KICK) ** (k - 1))
                                         for k in (2, 3, 4, 5, 6, 8)}
    # Monte Carlo: resample the noise kicks after each observed spike, keeping the recorded
    # synaptic input, and ask how often the same cell would fire again within g samples.
    rng = np.random.default_rng(20260924)
    R = 20000
    gaps = (3, 4, 5, 6, 7, 8, 10, 12)
    exp_with, exp_noise = {g: 0.0 for g in gaps}, {g: 0.0 for g in gaps}
    worst = []
    for side, j, syn in spikes:
        for with_syn, acc in ((True, exp_with), (False, exp_noise)):
            v = np.zeros(R)
            first = np.full(R, 99)
            for k in range(12):
                kicks = rng.random(R) < P_KICK
                v = v * DECAY + (syn[k] if with_syn else 0.0) + TONIC + kicks * KICK
                fired = v >= 1.0
                first[fired & (first == 99)] = k + 1
                v[fired] = 0.0
            for g in gaps:
                acc[g] += float(np.mean(first <= g))
            if with_syn:
                worst.append(float(np.mean(first <= 5)))
    minutes = rec.sum() * DT / 60
    out['monte_carlo'] = {
        'realisations_per_spike': R, 'minutes': minutes,
        'expected_same_side_refires_within_gap_70min_recorded_synaptic_input': exp_with,
        'expected_same_side_refires_within_gap_70min_noise_only': exp_noise,
        'expected_per_minute_recorded_synaptic_input': {g: v / minutes for g, v in exp_with.items()},
        'max_single_spike_probability_gap_le_5': max(worst),
        'observed_same_side_min_gap_samples': 8}
    # Left/right independence from the N4A cross-correlogram.
    d = json.loads((N4 / 'diagnosis.json').read_text(encoding='utf-8'))['n0_background']
    out['lr_cross_correlogram'] = d['lr_cross_correlogram']
    out['lr_expected_per_lag'] = d['lr_expected_per_lag']
    out['spike_causes'] = d['spike_causes']
    (L.OUT / 'mechanism.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(json.dumps({k: out[k] for k in ('kicks_needed_after_reset_noise_only', 'p_two_or_more_kicks_within',
                                          'synaptic_input_during_recovery_V')}, indent=0))
    print('recovery v:', {k: round(v['max'], 3) for k, v in out['recovery_voltage_after_spike'].items()})
    print('MC expected (recorded synaptic) 70 min:', {g: round(v, 4) for g, v in exp_with.items()})
    print('MC expected (noise only) 70 min:', {g: round(v, 5) for g, v in exp_noise.items()})


# ------------------------------------------------------------------ replay helpers ---
def motor(lv, rv):
    from game.action import MotorState
    return MotorState(float(lv), float(rv), 0.0, 0.0, np.zeros(1))


def replay_lr(policy, left, right):
    policy.reset()
    fires = []
    for t in range(left.size):
        act = policy.decide(motor(left[t], right[t]))
        if act.escape:
            ch = policy.criterion_diagnostics()['escape_trigger_channel'] \
                if hasattr(policy, 'criterion_diagnostics') else 'SINGLE_SAMPLE'
            trig = getattr(policy, 'last_trigger', None)
            fires.append({'tick': t, 'channel': ch, 'total': float(left[t] + right[t]),
                          'spikes': None if trig is None else trig['pair']})
    return fires


def same_side_pairs(left, right, gap):
    """Raw qualifying same-side pairs (no refractory), per side."""
    out = {}
    for side, tr in (('L', left), ('R', right)):
        prev = np.concatenate([[tr[0]], tr[:-1]])
        spk = np.flatnonzero(tr - DECAY * prev >= 0.5)
        out[side] = int(np.sum(np.diff(spk) <= gap))
    return out


def poisson(k, minutes):
    from scipy.stats import chi2
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def n0_sets():
    """Original N0 (per-side traces rebuilt from the exact N4A re-simulation) and fresh N0."""
    a = np.load(N4 / 'n0.npz')
    m = json.loads((N4 / 'n0.json').read_text(encoding='utf-8'))
    raw = np.load(ROOT / 'artifacts/m1_8_no_loom_calibration/raw.npz')['null']
    orig = []
    for i, t in enumerate(m['trials']):
        s0, s1, r0 = t['first_step'], t['end_step'], t['record_first_step']
        lt = traces_from_spikes(a['spk_L'][s0:s1])[r0 - s0:]
        rt = traces_from_spikes(a['spk_R'][s0:s1])[r0 - s0:]
        assert np.array_equal(lt + rt, raw[i * 1400:(i + 1) * 1400]), 'original N0 rebuild mismatch'
        orig.append((lt, rt))
    fresh, meta = [], []
    for c in range(4):
        path = L.OUT / ('fresh_n0_chunk%d.npz' % c)
        if not path.exists():
            continue
        z = np.load(path)
        meta.append(json.loads((L.OUT / ('fresh_n0_chunk%d.json' % c)).read_text(encoding='utf-8')))
        fresh += list(zip(z['left'], z['right']))
    return orig, fresh, meta


def n0_eval(factory, trials, gap=None):
    n, sides, bilateral_close = 0, {'L': 0, 'R': 0}, 0
    raw = {'L': 0, 'R': 0}
    values = []
    for lt, rt in trials:
        f = replay_lr(factory(), lt, rt)
        n += len(f)
        for x in f:
            values.append(round(x['total'], 4))
            ch = x['channel']
            for s in 'LR':
                if ch.startswith('LATERAL') and s in ch[8:]:
                    sides[s] += 1
        if gap is not None:
            p = same_side_pairs(lt, rt, gap)
            raw['L'] += p['L']
            raw['R'] += p['R']
    ticks = sum(lt.size for lt, _ in trials)
    minutes = ticks * DT / 60
    return {'ticks': ticks, 'minutes': minutes, 'false_events': n, 'per_minute': n / minutes,
            'upper95_per_minute': poisson(n, minutes), 'trigger_sides': sides,
            'raw_same_side_pairs': raw if gap is not None else None, 'firing_totals': values[:12]}


def n0_structure(trials):
    """Same-side minimum gap and bilateral close pairs in a set of N0 traces."""
    gaps = {'L': [], 'R': []}
    bil = 0
    both = 0
    nL = nR = 0
    for lt, rt in trials:
        idx = {}
        for side, tr in (('L', lt), ('R', rt)):
            prev = np.concatenate([[tr[0]], tr[:-1]])
            idx[side] = np.flatnonzero(tr - DECAY * prev >= 0.5)
            gaps[side] += np.diff(idx[side]).tolist()
        nL += idx['L'].size
        nR += idx['R'].size
        sl, sr = set(idx['L'].tolist()), set(idx['R'].tolist())
        both += len(sl & sr)
        for t in sl:
            bil += sum(1 for d in range(-4, 5) if (t + d) in sr)
    ticks = sum(lt.size for lt, _ in trials)
    return {'spikes_L': nL, 'spikes_R': nR, 'rate_L_hz': nL / (ticks * DT), 'rate_R_hz': nR / (ticks * DT),
            'same_side_min_gap': {s: int(min(g)) if g else None for s, g in gaps.items()},
            'same_side_gaps_le_8': {s: int(sum(1 for x in g if x <= 8)) for s, g in gaps.items()},
            'same_side_gaps_le_10': {s: int(sum(1 for x in g if x <= 10)) for s, g in gaps.items()},
            'same_side_gaps_le_12': {s: int(sum(1 for x in g if x <= 12)) for s, g in gaps.items()},
            'same_tick_bilateral': both, 'same_tick_expected_independent': nL * nR / ticks,
            'bilateral_pairs_within_4': bil, 'bilateral_within_4_expected_independent': nL * nR * 9 / ticks}


def n1_sets():
    a = np.load(N4 / 'n1.npz')
    m = json.loads((N4 / 'n1.json').read_text(encoding='utf-8'))
    data = np.load(N1_DIR / 'trials.npz')
    meta = json.loads((N1_DIR / 'trials_meta.json').read_text(encoding='utf-8'))
    trials = []
    for t, tm in zip(m['trials'], meta['trials']):
        s0, s1, r0 = t['first_step'], t['end_step'], t['record_first_step']
        lt = traces_from_spikes(a['spk_L'][s0:s1])[r0 - s0:]
        rt = traces_from_spikes(a['spk_R'][s0:s1])[r0 - s0:]
        assert np.array_equal(lt + rt, data['%d_dnp01' % t['index']]), 'N1 rebuild mismatch'
        trials.append({'index': t['index'], 'kind': tm['kind'], 'click': tm['click_tick'],
                       'window': data['%d_window' % t['index']], 'window_start': tm['window_start'],
                       'left': lt, 'right': rt})
    return trials


def n1_eval(factory, trials):
    per = {}
    detail = []
    for t in trials:
        f = replay_lr(factory(), t['left'], t['right'])
        inside = [x for x in f if t['window'][x['tick']]]
        c = per.setdefault(t['kind'], {'trials': 0, 'fired': 0, 'lat': [], 'sides': {}, 'onset_lat': []})
        c['trials'] += 1
        if inside:
            x = inside[0]
            c['fired'] += 1
            side = x['channel'][8:] if x['channel'].startswith('LATERAL') else 'summed'
            c['sides'][side] = c['sides'].get(side, 0) + 1
            if t['click'] is not None:
                c['lat'].append((x['tick'] - t['click']) * DT)
            c['onset_lat'].append((x['tick'] - t['window_start']) * DT)
            detail.append({'index': t['index'], 'kind': t['kind'], 'tick': x['tick'], 'channel': x['channel'],
                           'spikes': x['spikes']})
    out = {}
    for k, c in per.items():
        out[k] = {'trials': c['trials'], 'fired': c['fired'], 'trigger_sides': c['sides'],
                  'median_latency_from_click_s': med(c['lat']), 'p95_latency_from_click_s': pct(c['lat'], 95),
                  'median_latency_from_onset_s': med(c['onset_lat'])}
    return out, detail


# ------------------------------------------------------------------ human sessions ---
def load_session(path):
    rows = [json.loads(line) for line in (path / 'ticks.jsonl').open(encoding='utf-8')]
    eps = {}
    for r in rows:
        eps.setdefault(r['episode'], []).append(r)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    strikes = json.loads((path / 'strikes.json').read_text(encoding='utf-8'))
    return eps, manifest, strikes


def row_motor(r):
    from game.action import MotorState
    n = r['neural']
    return MotorState(n['dnp01_left'], n['dnp01_right'], n['dna02_left'], n['dna02_right'], np.zeros(1))


def reproduce(eps, manifest):
    from game.session import build_policy
    snaps, mism = {}, 0
    for ep, rows in eps.items():
        p = build_policy(manifest['config'], ROOT)[0]
        p.reset()
        s = {0: copy.deepcopy(p)}
        for i, r in enumerate(rows):
            if r['neural']['brain_stepped']:
                a = p.decide(row_motor(r))
                mism += a.escape != r['action']['escape']
                if a.escape:
                    s[i + 1] = copy.deepcopy(p)
        snaps[ep] = s
    return snaps, mism


def segments(eps):
    out = []
    for ep, rows in eps.items():
        start = 0
        for i, r in enumerate(rows):
            if r['action']['escape'] and r['neural']['brain_stepped']:
                out.append((ep, start, i))
                start = i + 1
        if start < len(rows):
            out.append((ep, start, None))
    return out


DECODER_STATE = ('threshold', 'fast_threshold', 'persistence_samples', 'dual_path',
                 'sustained_window_samples', '_window', '_streak', '_channel', 'spec',
                 '_prev', '_last', '_pair', '_sample', '_now', '_values', 'last_trigger')


def synced(factory, snapshot, rows, start):
    p = factory()
    p.__dict__.update({k: copy.deepcopy(v) for k, v in snapshot.__dict__.items() if k not in DECODER_STATE})
    if hasattr(p, 'spec'):
        p._last = {'L': None, 'R': None}
        p._pair = {'L': None, 'R': None}
        p._sample = 0
        p._prev = ({'L': rows[start - 1]['neural']['dnp01_left'],
                    'R': rows[start - 1]['neural']['dnp01_right']} if start > 0
                   else {'L': 0.0, 'R': 0.0})
    elif getattr(p, 'sustained_window_samples', None) is not None:
        p._window.clear()
    p._streak = 0
    return p


def human_eval(factory, sess):
    eps, snaps, strikes = sess['eps'], sess['snaps'], sess['strikes']
    segs = []
    for ep, a, e in segments(eps):
        rows = eps[ep]
        p = synced(factory, snaps[ep][a], rows, a)
        stop = e if e is not None else len(rows) - 1
        fire = None
        for i in range(a, stop + 1):
            if rows[i]['neural']['brain_stepped'] and p.decide(row_motor(rows[i])).escape:
                trig = getattr(p, 'last_trigger', None)
                spikes = None
                if trig is not None:
                    spikes = {s: [a + x for x in v] for s, v in trig['pair'].items()}
                fire = {'row': i, 'channel': p.criterion_diagnostics()['escape_trigger_channel']
                        if hasattr(p, 'criterion_diagnostics') else 'SINGLE_SAMPLE', 'spike_rows': spikes}
                break
        segs.append({'episode': ep, 'start': a, 'recorded_escape': e, 'fire': fire})
    return segs


def summarise_human(segs, sess, name):
    eps = sess['eps']
    out = {'recorded_escapes': 0, 'fired_no_later': 0, 'earlier': 0, 'later_or_none': 0,
           'lead_ticks': [], 'hover': {'n': 0, 'fired_no_later': 0, 'lead_ticks': []},
           'strike_phase': {'n': 0, 'fired_no_later': 0, 'lead_ticks': []},
           'fires_without_recorded_escape': 0, 'trigger_channels': {}}
    for s in segs:
        f, e = s['fire'], s['recorded_escape']
        if f is not None:
            out['trigger_channels'][f['channel']] = out['trigger_channels'].get(f['channel'], 0) + 1
        if e is None:
            out['fires_without_recorded_escape'] += f is not None
            continue
        rows = eps[s['episode']]
        kind = 'strike_phase' if rows[e]['swatter']['phase'] in STRIKE_PHASES else 'hover'
        out['recorded_escapes'] += 1
        out[kind]['n'] += 1
        if f is not None and f['row'] <= e:
            out['fired_no_later'] += 1
            out[kind]['fired_no_later'] += 1
            out['earlier'] += f['row'] < e
            out['lead_ticks'].append(e - f['row'])
            out[kind]['lead_ticks'].append(e - f['row'])
        else:
            out['later_or_none'] += 1
    for k in ('hover', 'strike_phase'):
        out[k]['median_lead_s'] = None if not out[k]['lead_ticks'] else med(out[k]['lead_ticks']) * DT
    out['median_lead_s'] = None if not out['lead_ticks'] else med(out['lead_ticks']) * DT
    # Direct strikes: latency from the click (exact first firing in the click's segment).
    lat = []
    for st in sess['strikes']:
        rows = eps[st['episode']]
        idx = {r['tick']: k for k, r in enumerate(rows)}
        c, r = idx[st['start_tick']], idx[st['resolved_tick']]
        if st.get('escape_preexisting'):
            continue
        sg = next(x for x in segs if x['episode'] == st['episode'] and x['start'] <= c
                  and (x['recorded_escape'] is None or x['recorded_escape'] >= c))
        f = sg['fire']
        if f is not None and f['row'] <= r:
            lat.append({'latency_s': (f['row'] - c) * DT, 'channel': f['channel'],
                        'spike_rows': f['spike_rows'], 'click_row': c})
        else:
            lat.append({'latency_s': None, 'exact': sg['recorded_escape'] is None or sg['recorded_escape'] > r})
    post = [x['latency_s'] for x in lat if x['latency_s'] is not None and x['latency_s'] >= 0]
    out['direct_strikes'] = {'n': len(lat), 'fired_before_click': sum(1 for x in lat if x['latency_s'] is not None
                                                                     and x['latency_s'] < 0),
                             'fired_after_click': len(post), 'not_fired_or_later': sum(1 for x in lat
                                                                                       if x['latency_s'] is None),
                             'median_after_click_s': med(post), 'mean_after_click_s': None if not post else
                             float(np.mean(post)), 'strikes': lat}
    del out['lead_ticks']
    for k in ('hover', 'strike_phase'):
        del out[k]['lead_ticks']
    return out


def special_cases(factory, sessions):
    """Far perched approach, voluntary takeoff, slow-close (synced and clean start)."""
    out = {}
    s = sessions['strict_n2']
    rows = s['eps'][1]
    seg = next(x for x in s['segs_cache'][id(factory)] if x['episode'] == 1 and x['start'] <= 2434
               and (x['recorded_escape'] or 10 ** 9) >= 2434)
    f = seg['fire']
    out['far_perched'] = {'segment_start_row': seg['start'], 'fire': f,
                          'fires_in_bout_2434_2528': f is not None and 2434 <= f['row'] <= 2528}
    n = sessions['n2b']
    rows = n['eps'][1]
    k = next(i for i, r in enumerate(rows) if any(e['type'] == 'voluntary_takeoff' for e in r['lifecycle']['events']))
    seg = next(x for x in n['segs_cache'][id(factory)] if x['episode'] == 1 and x['start'] <= k - 50
               and (x['recorded_escape'] or 10 ** 9) >= k - 50)
    f = seg['fire']
    out['voluntary_takeoff'] = {'takeoff_row': k, 'fire': f,
                                'fires_within_1s_before_to_0_5s_after': f is not None and k - 50 <= f['row'] <= k + 25}
    rows = n['eps'][5]
    idx = {r['tick']: j for j, r in enumerate(rows)}
    seg = next(x for x in n['segs_cache'][id(factory)] if x['episode'] == 5 and x['start'] <= idx[610]
               and (x['recorded_escape'] or 10 ** 9) >= idx[610])
    out['slow_close_synced'] = {'segment_start_tick': rows[seg['start']]['tick'],
                                'fire_tick': None if seg['fire'] is None else rows[seg['fire']['row']]['tick'],
                                'fire': seg['fire']}
    p = factory()
    p.reset()
    if hasattr(p, 'spec'):
        p._prev = {'L': rows[idx[609]]['neural']['dnp01_left'], 'R': rows[idx[609]]['neural']['dnp01_right']}
    clean = None
    for i in range(idx[610], idx[670] + 1):
        if p.decide(row_motor(rows[i])).escape:
            clean = rows[i]['tick']
            break
    out['slow_close_clean_start_fire_tick'] = clean
    # Chase before the tick-589 N2b escape: the segment after the previous recorded escape.
    seg = next(x for x in n['segs_cache'][id(factory)] if x['episode'] == 5 and x['recorded_escape'] == idx[589])
    out['chase_before_589'] = {'segment_start_tick': rows[seg['start']]['tick'],
                               'fire_tick': None if seg['fire'] is None else rows[seg['fire']['row']]['tick'],
                               'lead_ticks_vs_589': None if seg['fire'] is None else idx[589] - seg['fire']['row']}
    return out


def evaluate():
    frozen = json.loads(L.FROZEN.read_text(encoding='utf-8'))
    factories = L.all_factories()
    specs = {s['name']: s for s in frozen['candidates']}
    orig, fresh, fresh_meta = n0_sets()
    print('N0 original trials %d, fresh trials %d' % (len(orig), len(fresh)), flush=True)
    result = {'label': 'M1.8-N4B1 lateralized DNp01 readout validation; research only',
              'frozen_candidates_sha256': sha256(L.FROZEN), 'frozen_utc': frozen['frozen_utc'],
              'fresh_n0_chunks': fresh_meta,
              'n0_structure': {'original': n0_structure(orig), 'fresh': n0_structure(fresh)}}
    print('N0 structure', json.dumps(result['n0_structure']), flush=True)
    n1 = n1_sets()
    sessions = {}
    for k, path in SESSIONS.items():
        eps, manifest, strikes = load_session(path)
        snaps, mism = reproduce(eps, manifest)
        sessions[k] = {'eps': eps, 'snaps': snaps, 'strikes': strikes, 'segs_cache': {}}
        result.setdefault('human_reproduction_mismatches', {})[k] = mism
    rows = {}
    for name, factory in factories.items():
        spec = specs.get(name)
        gap = None if spec is None else spec['max_gap']
        e_orig = n0_eval(factory, orig, gap)
        e_fresh = n0_eval(factory, fresh, gap)
        k = e_orig['false_events'] + e_fresh['false_events']
        mins = e_orig['minutes'] + e_fresh['minutes']
        combined = {'minutes': mins, 'false_events': k, 'per_minute': k / mins,
                    'upper95_per_minute': poisson(k, mins)}
        n1s, n1d = n1_eval(factory, n1)
        hum = {}
        for sk, sess in sessions.items():
            segs = human_eval(factory, sess)
            sess['segs_cache'][id(factory)] = segs
            hum[sk] = summarise_human(segs, sess, name)
        spec_cases = special_cases(factory, sessions)
        rows[name] = {'spec': spec, 'n0_original': e_orig, 'n0_fresh': e_fresh, 'n0_combined': combined,
                      'n1': n1s, 'n1_triggers': n1d, 'human': hum, 'cases': spec_cases}
        s, m = n1s['strong_direct'], n1s['medium_committed']
        hs = hum['n2b']['direct_strikes']
        print('%-52s N0 %d/%.0fmin fresh %d/%.0fmin comb up95 %.4f | S %d %.2f/%.2f M %d %.2f/%.2f | '
              'w %d g %d a %d | far %s vol %s slow %s/%s chase589 %s | N2b lead %s strikes %s' % (
                  name[:52], e_orig['false_events'], e_orig['minutes'], e_fresh['false_events'],
                  e_fresh['minutes'], combined['upper95_per_minute'],
                  s['fired'], s['median_latency_from_click_s'] or -1, s['p95_latency_from_click_s'] or -1,
                  m['fired'], m['median_latency_from_click_s'] or -1, m['p95_latency_from_click_s'] or -1,
                  n1s['weak_approach']['fired'], n1s['glancing_pass']['fired'], n1s['aborted_approach']['fired'],
                  spec_cases['far_perched']['fires_in_bout_2434_2528'],
                  spec_cases['voluntary_takeoff']['fires_within_1s_before_to_0_5s_after'],
                  spec_cases['slow_close_synced']['fire_tick'], spec_cases['slow_close_clean_start_fire_tick'],
                  spec_cases['chase_before_589']['lead_ticks_vs_589'],
                  hum['n2b']['median_lead_s'], [None if x['latency_s'] is None else round(x['latency_s'], 2)
                                                for x in hs['strikes']]), flush=True)
    result['candidates'] = rows
    (L.OUT / 'evaluation.json').write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')
    print('written', L.OUT / 'evaluation.json')


# ------------------------------------------------------------------ closed loop ---
def closed_loop():
    from game.session import Session, load_config
    import tools.n2_closed_loop as C
    config = load_config(ROOT / 'game_room_config.json')
    Lp = L.lateral_class()
    specs = {s['key']: s for s in L.candidate_specs()}
    refs = L.reference_policies()
    factories = {'legacy': refs['legacy summed single-sample 1.45'],
                 'N2b': refs['N2b: FAST 2.10 OR current-H + 3-of-5']}
    for key in ('A_spike', 'B_spike', 'C_spike', 'D_spike'):
        factories[key] = (lambda s=specs[key]: Lp(s))
    probe = Session(config, policy=factories['legacy'](), seed=1, mode='evaluation')
    brain = probe.brain
    probe.close()
    results, started = {}, time.perf_counter()

    def run(name, fn, *a):
        row = {label: fn(config, make(), *a[:1], brain, *a[1:]) for label, make in factories.items()}
        results.setdefault(name, []).append(row)
        print('%-34s %s  %.0fs' % (name, ' | '.join('%s pre %d post %s' % (
            k, r['escapes_before_click'], r['first_escape_latency_from_click_s']) for k, r in row.items()),
            time.perf_counter() - started), flush=True)

    for seed in C.PERCH_SEEDS:
        for offset in ((0.0, 0.0), (40.0, -30.0)):
            run('A_perched_committed_strike', C.scenario_a_perched_strike, seed, offset)
    run('A_perched_hover_m1_8_a', C.scenario_a_perched_hover, 255)
    for seed in (11, 12, 13, 14, 15, 16):
        for offset in ((20.0, 10.0), (-45.0, 30.0)):
            run('B_airborne_committed_strike', C.scenario_b_airborne_strike, seed, offset)
    for seed in (21, 22, 23):
        for start, speed in ((700.0, 260.0), (600.0, 150.0), (500.0, 90.0)):
            run('C_hover_approach', C.scenario_c_hover_approach, seed, start, speed)
    for seed in (101, 255, 4242):
        run('D_no_player', C.scenario_d_no_player, seed, 9000)
    report = {'label': 'M1.8-N4B1 research-only closed-loop ROOM runs (tools/ policies only)',
              'summary': {k: C.aggregate(v) for k, v in results.items()}, 'scenarios': results,
              'wall_seconds': time.perf_counter() - started}
    (L.OUT / 'closed_loop.json').write_text(json.dumps(report, indent=1, default=float) + '\n', encoding='utf-8')
    print('written', L.OUT / 'closed_loop.json')


def run(mode):
    if mode == 'mechanism':
        mechanism()
    elif mode == 'evaluate':
        evaluate()
    else:
        closed_loop()
