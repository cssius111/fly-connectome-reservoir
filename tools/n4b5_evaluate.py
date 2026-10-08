"""M1.8-N4B5 research: evaluation of the frozen apparent-size candidates.

Research only; reads the outputs of tools/n4b5_resim.py and scores the frozen N4B1C decoder
(unchanged; tools/n4b2_analysis.n4b1c_events) under each candidate Retina. Geometry is
offline interpretation only.

Free-flight categories (N4B4 metric split, adopted in N4B5):
* A  fixed-fly / no-drive neural false escape: encoder drive 0 in the 200 ms before;
* B  inappropriate free-flight escape: stimulus present but no near pass (>= 310 units)
     within 1.5 s if the escape is withheld (counterfactual replay), or drive 0;
* C  foreshortening-driven escape: >= 60 % of the expansion from apparent-size change,
     paddle elevation >= 60 deg;
* D  genuine self-approach escape: range closing at >= 40 units/s, < 30 % from apparent size;
* everything else is "mixed".
B is an acceptance category (provisional working criterion < 0.1/min); C and D are tracked.

    python tools/n4b5_evaluate.py            # writes artifacts/m1_8_n4b5/evaluation.json
    python tools/n4b5_evaluate.py cf-jobs    # list counterfactual jobs still needed for B
"""
from __future__ import annotations

from collections import Counter
import json
import math
import os
from pathlib import Path
import sys

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from scipy.stats import chi2  # noqa: E402

from tools import n4_diagnosis as D  # noqa: E402
from tools import n4b2_analysis as A  # noqa: E402
from tools import n4b5_geometry as G  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b5'
DT = 0.02
FOOTPRINT, NEAR = 155.0, 310.0
CANDS = G.CANDIDATES


def upper(k, minutes):
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def load(name):
    p = OUT / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def first_after(ev, t0):
    return next((t for t, _ in ev if t >= t0), None)


# ------------------------------------------------------------------ N1 ---
def n1_eval(cand):
    d = load('n1_%s.json' % cand)
    if d is None:
        return None
    meta = json.loads((D.N1_DIR / 'trials_meta.json').read_text(encoding='utf-8'))
    out = {'equal_to_recorded_g0': d['equal_to_recorded']}
    by = {}
    for t, m in zip(d['trials'], meta['trials']):
        onset = m['click_tick'] if m['click_tick'] is not None else m['window_start']
        ev = A.n4b1c_events(np.array(t['left']), np.array(t['right']))
        f = first_after(ev, onset)
        by.setdefault(t['kind'], []).append(None if f is None else f - onset)
    for k, v in by.items():
        dd = [x for x in v if x is not None]
        out[k] = {'detected': len(dd), 'n': len(v), 'median_s': float(np.median(dd)) * DT if dd else None,
                  'p95_s': float(np.percentile(dd, 95)) * DT if dd else None, 'latencies': v}
    return out


# ------------------------------------------------------------------ human ---
def human_windows():
    """Event windows from the recorded sessions (N4A definitions, by tick)."""
    win = []
    for sess, name in D.SESSIONS.items():
        eps, strikes = D.session_rows(name)
        for s in strikes:
            rows = eps[s['episode']]
            idx = {r['tick']: k for k, r in enumerate(rows)}
            c, r = idx[s['start_tick']], idx[s['resolved_tick']]
            win.append({'session': sess, 'episode': s['episode'], 'cls': 'direct_strike',
                        't0': rows[max(0, c - 25)]['tick'], 't1': rows[r]['tick'], 'anchor': s['start_tick']})
        for ep, rows in eps.items():
            seg = 0
            for i, r in enumerate(rows):
                if not (r['action']['escape'] and r['neural']['brain_stepped']):
                    continue
                b = D.bout_start(rows, i, seg)
                if b is not None:
                    cls = 'strike_escape' if r['swatter']['phase'] in D.STRIKE_PHASES else 'hover_escape'
                    win.append({'session': sess, 'episode': ep, 'cls': cls, 't0': rows[b]['tick'], 't1': r['tick'],
                                'anchor': r['tick']})
                seg = i + 1
    win.append({'session': 'n2b', 'episode': 5, 'cls': 'slow_close', 't0': 610, 't1': 670, 'anchor': 610})
    win.append({'session': 'n2b', 'episode': 5, 'cls': 'chase_before_589', 't0': 570, 't1': 589, 'anchor': 570})
    eps, _ = D.session_rows(D.SESSIONS['strict_n2'])
    rows = eps[1]
    win.append({'session': 'strict_n2', 'episode': 1, 'cls': 'far_perched', 't0': rows[2434]['tick'],
                't1': rows[2528]['tick'], 'anchor': rows[2434]['tick']})
    eps, _ = D.session_rows(D.SESSIONS['n2b'])
    rows = eps[1]
    k = next(i for i, r in enumerate(rows) if any(e['type'] == 'voluntary_takeoff' for e in r['lifecycle']['events']))
    win.append({'session': 'n2b', 'episode': 1, 'cls': 'voluntary_takeoff', 't0': rows[k - 50]['tick'],
                't1': rows[min(len(rows) - 1, k + 25)]['tick'], 'anchor': rows[k]['tick']})
    return win


def human_eval(cand, windows, suffix=''):
    d = load('human_%s%s.json' % (cand, suffix))
    if d is None:
        return None
    out = {'dnp01_rows_equal_to_recorded': {s: [v['dnp01_rows_equal_to_recorded'], v['stepped_rows']] for s, v in d.items()}}
    per = {}
    total = 0
    for sess, v in d.items():
        for ep, e in v['episodes'].items():
            total += len(A.n4b1c_events(np.array(e['left']), np.array(e['right'])))
    out['episode_open_loop_firings'] = total
    for w in windows:
        e = d[w['session']]['episodes'][str(w['episode'])]
        ticks = e['ticks']
        i0 = next(i for i, t in enumerate(ticks) if t >= w['t0'])
        i1 = max(i for i, t in enumerate(ticks) if t <= w['t1'])
        ev = A.n4b1c_events(np.array(e['left'][i0:i1 + 1]), np.array(e['right'][i0:i1 + 1]))
        first = None if not ev else ticks[i0 + ev[0][0]]
        per.setdefault(w['cls'], []).append({'first_tick': first, 'anchor': w['anchor'], 't1': w['t1'],
                                             'rel_anchor_s': None if first is None else (first - w['anchor']) * DT})
    ds = per['direct_strike']
    fired = [x for x in ds if x['first_tick'] is not None]
    after = [x['rel_anchor_s'] for x in fired if x['rel_anchor_s'] >= 0]
    out['direct_strikes'] = {'fired': len(fired), 'n': len(ds), 'before_click': sum(x['rel_anchor_s'] < 0 for x in fired),
                             'median_after_click_s': float(np.median(after)) if after else None,
                             'per_event_s': [x['rel_anchor_s'] for x in ds]}
    for cls in ('hover_escape', 'strike_escape'):
        v = per[cls]
        met = [x for x in v if x['first_tick'] is not None and x['first_tick'] <= x['anchor']]
        out[cls] = {'met_no_later_than_recorded': len(met), 'fired_in_window': sum(x['first_tick'] is not None for x in v),
                    'n': len(v)}
    for cls in ('slow_close', 'chase_before_589', 'far_perched', 'voluntary_takeoff'):
        out[cls] = per[cls][0]['first_tick']
    return out


# ------------------------------------------------------------------ N0 ---
def n0_eval(cand):
    d = load('n0_%s.json' % cand)
    if d is None:
        return None
    ev = sum(len(A.n4b1c_events(np.array(t['left']), np.array(t['right']))) for t in d['trials'])
    return {'events': ev, 'minutes': 70.0, 'upper95_per_min': upper(ev, 70.0), 'equal_to_recorded_g0': d['equal_to_recorded']}


# ------------------------------------------------------------------ ROOM ---
def geometry(row):
    fx, fy, fvx, fvy, _ = row['fly']
    px, py, ph, pvx, pvy = row['paddle'][:5]
    dx, dy = px - fx, py - fy
    dh = math.hypot(dx, dy)
    rng = math.sqrt(dh * dh + ph * ph)
    return dh, rng, -(dx * (fvx - pvx) + dy * (fvy - pvy)) / rng, math.degrees(math.atan2(ph, dh))


def size_share(rows, i, n=10):
    pos_r = pos_s = 0.0
    for j in range(max(2, i - n + 1), i + 1):
        a, b = rows[j - 2], rows[j - 1]
        ra, rb = geometry(a)[1], geometry(b)[1]
        ha, hb = a['visual_half_size'], b['visual_half_size']
        dr = 2 * math.atan(ha / rb) - 2 * math.atan(ha / ra)
        ds = 2 * math.atan(hb / rb) - 2 * math.atan(ha / rb)
        pos_r += max(dr, 0.0)
        pos_s += max(ds, 0.0)
    return pos_s / (pos_r + pos_s) if pos_r + pos_s > 0 else None


def room_events(cand, inv):
    events, minutes, missing = [], 0.0, []
    for r in inv['runs']:
        name = 'room_%s_%s_seed%d' % (cand, r['source'], r['seed'])
        m = load(name + '.json')
        if m is None:
            missing.append(name)
            continue
        minutes += r['ticks'] / 3000
        arr = np.load(OUT / (name + '.npz'))
        rows = m['rows']
        stepped = list(arr['stepped_ticks'])
        for t in m['escape_ticks']:
            i = {row['tick']: k for k, row in enumerate(rows)}[t]
            k = stepped.index(i)
            drive = float(arr['drive'][max(0, k - 9):k + 1].sum(1).max())
            dh, rng, rr, elev = geometry(rows[i - 1])
            share = size_share(rows, i)
            cf = load('%s_cf%d.json' % (name, t))
            cf_min = None
            if cf is not None:
                ci = {row['tick']: j for j, row in enumerate(cf['rows'])}[t]
                cf_min = min(geometry(row)[0] for row in cf['rows'][ci + 1:ci + 76])
            if drive < 1e-6:
                cat = 'A'
            elif cf_min is not None and cf_min >= NEAR:
                cat = 'B'
            elif share is not None and share >= 0.6 and elev >= 60:
                cat = 'C'
            elif rr <= -40 and (share is None or share < 0.3):
                cat = 'D'
            else:
                cat = 'mixed'
            events.append({'source': r['source'], 'seed': r['seed'], 'tick': t, 'paths': rows[i]['paths'],
                           'drive_peak': drive, 'elevation_deg': elev, 'range_rate': rr, 'horizontal_distance': dh,
                           'size_share': share, 'counterfactual_min_horizontal': cf_min,
                           'counterfactual_available': cf is not None, 'category': cat,
                           'theta_dot': rows[i]['theta_dot']})
    counts = Counter(e['category'] for e in events)
    rates = {c: {'events': counts.get(c, 0), 'per_min': counts.get(c, 0) / minutes if minutes else None,
                 'upper95_per_min': upper(counts.get(c, 0), minutes) if minutes else None} for c in ('A', 'B', 'C', 'D', 'mixed')}
    rates['all'] = {'events': len(events), 'per_min': len(events) / minutes if minutes else None,
                    'upper95_per_min': upper(len(events), minutes) if minutes else None}
    return {'minutes': minutes, 'missing_runs': len(missing), 'events': events, 'rates': rates,
            'counterfactuals_missing': sum(not e['counterfactual_available'] for e in events)}


def g0_room(inv):
    """G0 ROOM categories from the N4B4 analysis (same definitions)."""
    a = json.loads((ROOT / 'artifacts/m1_8_n4b4/analysis.json').read_text(encoding='utf-8'))
    cats = Counter()
    for e in a['events']:
        if e['neural_cause'] == 'noise-like':
            cats['A'] += 1
        elif e['counterfactual_min_horizontal_1_5s'] >= NEAR:
            cats['B'] += 1
        elif e['expansion_regime'] == 'overhead foreshortening':
            cats['C'] += 1
        elif e['expansion_regime'] == 'self-approach':
            cats['D'] += 1
        else:
            cats['mixed'] += 1
    m = inv['minutes']
    rates = {c: {'events': cats.get(c, 0), 'per_min': cats.get(c, 0) / m, 'upper95_per_min': upper(cats.get(c, 0), m)}
             for c in ('A', 'B', 'C', 'D', 'mixed')}
    rates['all'] = {'events': len(a['events']), 'per_min': len(a['events']) / m, 'upper95_per_min': upper(len(a['events']), m)}
    return {'minutes': m, 'rates': rates, 'source': 'artifacts/m1_8_n4b4/analysis.json'}


def cf_jobs():
    inv = json.loads((ROOT / 'artifacts/m1_8_n4b4/inventory.json').read_text(encoding='utf-8'))
    thr = {r['source']: r['threads'] for r in inv['runs']}
    jobs = []
    for cand in CANDS:
        for r in inv['runs']:
            name = 'room_%s_%s_seed%d' % (cand, r['source'], r['seed'])
            m = load(name + '.json')
            if m is None:
                continue
            for t in m['escape_ticks']:
                if load('%s_cf%d.json' % (name, t)) is None:
                    jobs.append((cand, r['source'], r['seed'], t, thr[r['source']]))
    return jobs


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'cf-jobs':
        for j in cf_jobs():
            print(' '.join(str(x) for x in j))
        return
    inv = json.loads((ROOT / 'artifacts/m1_8_n4b4/inventory.json').read_text(encoding='utf-8'))
    windows = human_windows()
    res = {'label': 'M1.8-N4B5 candidate evaluation (research only, offline)', 'candidates': {}}
    for cand in CANDS:
        room = g0_room(inv) if cand == 'G0_current' else (room_events(cand, inv) if load(
            'room_%s_%s_seed%d.json' % (cand, inv['runs'][0]['source'], inv['runs'][0]['seed'])) else None)
        res['candidates'][cand] = {'n1': n1_eval(cand), 'human': human_eval(cand, windows), 'n0': n0_eval(cand),
                                   'room': room}
    # Noise-realization control: same input, different brain-noise seed (offsets 0..4).
    noise = {}
    for cand in ('G0_current', 'G1_isotropic', 'G3_elevation_aware'):
        rows = []
        for off in range(5):
            h = human_eval(cand, windows, '' if off == 0 else '_noise%d' % off)
            if h is None:
                continue
            rows.append({'noise_offset': off, 'hover_met': h['hover_escape']['met_no_later_than_recorded'],
                         'strike_met': h['strike_escape']['met_no_later_than_recorded'],
                         'direct_fired': h['direct_strikes']['fired'],
                         'direct_median_after_click_s': h['direct_strikes']['median_after_click_s'],
                         'slow_close': h['slow_close'], 'far_perched': h['far_perched'],
                         'voluntary_takeoff': h['voluntary_takeoff'],
                         'episode_firings': h['episode_open_loop_firings']})
        noise[cand] = rows
    res['human_noise_control'] = noise
    (OUT / 'evaluation.json').write_text(json.dumps(res, indent=1, default=float) + '\n', encoding='utf-8')
    for cand, r in res['candidates'].items():
        print('==', cand)
        if r['n1']:
            print('  N1 equal-to-G0 %d | ' % r['n1']['equal_to_recorded_g0'] + ' | '.join(
                '%s %d %.2f' % (k[:6], v['detected'], v['median_s'] if v['median_s'] is not None else -1)
                for k, v in r['n1'].items() if isinstance(v, dict)))
        if r['human']:
            h = r['human']
            print('  human direct %d/%d before %d median %.2f | hover met %d/%d fired %d | strike met %d/%d | slow %s chase %s far %s vol %s | ep firings %d | exact %s' % (
                h['direct_strikes']['fired'], h['direct_strikes']['n'], h['direct_strikes']['before_click'],
                h['direct_strikes']['median_after_click_s'] or -1, h['hover_escape']['met_no_later_than_recorded'],
                h['hover_escape']['n'], h['hover_escape']['fired_in_window'], h['strike_escape']['met_no_later_than_recorded'],
                h['strike_escape']['n'], h['slow_close'], h['chase_before_589'], h['far_perched'], h['voluntary_takeoff'],
                h['episode_open_loop_firings'], h['dnp01_rows_equal_to_recorded']))
        if r['n0']:
            print('  N0', r['n0'])
        if r['room']:
            print('  ROOM %.0f min' % r['room']['minutes'], {k: v['events'] for k, v in r['room']['rates'].items()},
                  'missing runs', r['room'].get('missing_runs'), 'cf missing', r['room'].get('counterfactuals_missing'))


if __name__ == '__main__':
    main()
