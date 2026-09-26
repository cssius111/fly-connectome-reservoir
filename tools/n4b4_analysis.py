"""M1.8-N4B4 research: interpretation of the accepted N4B1C runtime's no-player free-flight
escapes.

Research only. Reads the deterministic reconstructions and counterfactual replays written by
tools/n4b4_replay.py, and reference data from earlier milestones (N0, N1). WORLD geometry,
Retina and encoder values are used offline only, to interpret events; nothing here is a
runtime gate or a policy input, and N4B1C is not retuned.

Classification rules (fixed before the events were inspected):

Neural cause, from the 10 samples (200 ms) up to and including the escape sample:
* noise-like: encoder drive < 1e-6 on every sample (as in fixed-fly N0 false triggers);
* low-drive: peak summed drive < 0.05;
* weak/glancing-like: peak drive 0.05-0.4 (N1 weak / glancing / aborted peaks 0.1-0.4);
* committed-like: peak drive >= 0.4 (N1 strong / medium saturate at 0.8 per channel).

Behaviour class, from the counterfactual replay in which the escape is withheld:
* A, collision-like approach: not noise-like, and without the escape the fly passes
  directly under the paddle footprint (horizontal distance < paddle radius + fly radius =
  155 units) within 1.5 s;
* B, near pass (acceptable sensitivity): not noise-like, and the fly comes within
  2 x 155 units within 1.5 s but not under the footprint;
* C, pathological false alarm: noise-like, or the fly never comes within 310 units in the
  1.5 s without the escape.

A parked paddle hovers at 320 units and is never lethal, so physical contact is impossible
in every case; A means the fly would fly beneath a large overhead object, the closest the
no-player scene comes to a collision course.

    python tools/n4b4_analysis.py       # writes artifacts/m1_8_n4b4/analysis.json and figures
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

OUT = ROOT / 'artifacts/m1_8_n4b4'
DT = 0.02
FOOTPRINT = 144.0 + 11.0          # paddle radius + fly radius (runtime ROOM config)
NEAR = 2 * FOOTPRINT
WINDOW_S = 1.5
PRE = 10                          # samples before the escape used for the neural cause
N0_SENSORY_MAX = 22               # N4A: spontaneous LC4+LPLC2 spikes per side per tick never exceed 22


def load(name):
    meta = json.loads((OUT / (name + '.json')).read_text(encoding='utf-8'))
    arr = np.load(OUT / (name + '.npz'))
    return meta, arr


def trace_spikes(tr, decay=np.float32(np.exp(-0.2))):
    """Spikes inferred from a DNp01 trace exactly as the runtime does (>= 0.5 jump)."""
    out = [False]
    for a, b in zip(tr[:-1], tr[1:]):
        out.append(b - float(decay) * a >= 0.5)
    return np.array(out)


def geometry(row):
    fx, fy, fvx, fvy, heading = row['fly']
    px, py, ph, pvx, pvy = row['paddle'][:5]
    dx, dy = px - fx, py - fy                       # fly -> paddle
    dh = math.hypot(dx, dy)
    rng = math.sqrt(dh * dh + ph * ph)
    rel_vx, rel_vy = fvx - pvx, fvy - pvy
    range_rate = -(dx * rel_vx + dy * rel_vy) / rng
    speed = math.hypot(fvx, fvy)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (dx * fvx + dy * fvy) / (dh * speed))))) if speed > 1e-9 and dh > 1e-9 else None
    direction = None if ang is None else ('toward' if ang < 45 else 'across' if ang <= 135 else 'away')
    # Constant-velocity extrapolation of the horizontal miss distance.
    v2 = rel_vx ** 2 + rel_vy ** 2
    t_star = ((dx * rel_vx + dy * rel_vy) / v2) if v2 > 1e-12 else None
    miss = None if t_star is None else math.hypot(dx - rel_vx * max(t_star, 0), dy - rel_vy * max(t_star, 0))
    return {'horizontal_distance': dh, 'range_3d': rng, 'range_rate': range_rate, 'paddle_height': ph,
            'paddle_speed': math.hypot(pvx, pvy), 'fly_speed': speed, 'heading_to_paddle_angle_deg': ang,
            'direction': direction, 'time_to_closest_s': t_star, 'extrapolated_miss_distance': miss}


def path_after(rows, t0, n):
    out = []
    for r in rows[t0 + 1:t0 + 1 + n]:
        g = geometry(r)
        out.append((r['tick'], g['horizontal_distance'], g['range_3d'], r['theta']))
    return out


def expansion_sources(rows, i, n=PRE):
    """Split the theta change over the n samples up to the escape into the part caused by
    3D range change and the part caused by apparent paddle half-size change
    (World.visual_half_size: face and directional tilt foreshortening). Offline only."""
    def th(h, rng):
        return 2.0 * math.atan(h / rng)
    # The Retina of row j is projected from the world state stored in row j - 1 (rows hold the
    # post-tick state), so the theta change at row j comes from rows j - 2 -> j - 1.
    by_range = by_size = 0.0
    pos_range = pos_size = 0.0
    max_err = 0.0
    for j in range(max(2, i - n + 1), i + 1):
        a, b = rows[j - 2], rows[j - 1]
        max_err = max(max_err, abs(th(b['visual_half_size'], geometry(b)['range_3d']) - rows[j]['theta']))
        ra, rb = geometry(a)['range_3d'], geometry(b)['range_3d']
        ha, hb = a['visual_half_size'], b['visual_half_size']
        dr = th(ha, rb) - th(ha, ra)
        ds = th(hb, rb) - th(ha, rb)
        by_range += dr
        by_size += ds
        pos_range += max(dr, 0.0)
        pos_size += max(ds, 0.0)
    total_pos = pos_range + pos_size
    return {'theta_change_from_range': by_range, 'theta_change_from_apparent_size': by_size,
            'theta_reconstruction_max_error': max_err,
            'expansion_share_from_apparent_size': (pos_size / total_pos) if total_pos > 0 else None}


def classify_neural(drive_peak):
    if drive_peak < 1e-6:
        return 'noise-like'
    if drive_peak < 0.05:
        return 'low-drive'
    if drive_peak < 0.4:
        return 'weak/glancing-like'
    return 'committed-like'


def event_record(ev, fact, fact_arr, cf, cf_arr):
    rows = fact['rows']
    tick_index = {r['tick']: i for i, r in enumerate(rows)}
    i = tick_index[ev['tick']]
    r = rows[i]
    assert r['policy_escape'] and r['world_escape'], ev
    g = geometry(rows[i - 1])        # the world state the escape sample's Retina was projected from
    stepped = list(fact_arr['stepped_ticks'])
    k = stepped.index(i)                              # index into spikes/sensory/drive
    drive = fact_arr['drive'][max(0, k - PRE + 1):k + 1].sum(1)
    sens = fact_arr['sensory'][max(0, k - PRE + 1):k + 1]
    sens_l = sens[:, 0] + sens[:, 2]
    sens_r = sens[:, 1] + sens[:, 3]
    types, sides = fact['panel_types'], fact['panel_sides']
    jl = [j for j, (t, s) in enumerate(zip(types, sides)) if t == 'DNp01' and s == 'L'][0]
    jr = [j for j, (t, s) in enumerate(zip(types, sides)) if t == 'DNp01' and s == 'R'][0]
    sp = fact_arr['spikes']
    lo = max(0, k - 25)
    spikes_l = [int(stepped[x] - i) for x in range(lo, k + 1) if sp[x, jl]]
    spikes_r = [int(stepped[x] - i) for x in range(lo, k + 1) if sp[x, jr]]
    prev_esc = [rr['tick'] for rr in rows[:i] if rr['policy_escape']]
    drive_peak = float(drive.max()) if drive.size else 0.0
    theta_hist = [rows[x]['theta_dot'] for x in range(max(0, i - 5), i + 1)]
    # ---- counterfactual (escape withheld)
    cf_rows = cf['rows']
    ci = {rr['tick']: j for j, rr in enumerate(cf_rows)}[ev['tick']]
    horizon = int(WINDOW_S / DT)
    cf_path = path_after(cf_rows, ci, horizon)
    f_path = path_after(rows, i, horizon)
    cf_min = min(p[1] for p in cf_path) if cf_path else None
    f_min = min(p[1] for p in f_path) if f_path else None
    cf_t_min = None if not cf_path else (min(cf_path, key=lambda p: p[1])[0] - ev['tick']) * DT
    cf_theta_max = max(p[3] for p in cf_path) if cf_path else None
    cf_lethal = any(rr['lethal'] for rr in cf_rows[ci:ci + horizon + 1])
    cf_hits = max(rr['hits'] for rr in cf_rows[ci:ci + horizon + 1])
    neural = classify_neural(drive_peak)
    if neural == 'noise-like' or cf_min is None or cf_min >= NEAR:
        cls = 'C'
    elif cf_min < FOOTPRINT:
        cls = 'A'
    else:
        cls = 'B'
    m = r['motion'] or [None] * 4
    return {
        'source': ev['source'], 'seed': ev['seed'], 'tick': ev['tick'], 'paths': r['paths'],
        'channel': ev['channel'], 'lifecycle_mode': r['lifecycle_mode'],
        'saccade_kind_before': rows[i - 1]['saccade_kind'],
        'saccade_remaining_before': (rows[i - 1]['motion'] or [0, 0, 0, 0])[3],
        'elevation_deg': math.degrees(math.atan2(g['paddle_height'], g['horizontal_distance'])),
        'range_receding': g['range_rate'] > 0,
        **expansion_sources(rows, i),
        'behavior_state_before': rows[i - 1]['behavior_state'],
        'reconstruction_exact': fact['check']['exact'], 'counterfactual_pre_divergence_exact': cf['check']['exact'],
        'suppressed_escape_ticks': cf['suppressed_escape_ticks'],
        # geometry (offline)
        **g, 'theta': r['theta'], 'theta_dot': r['theta_dot'], 'azimuth': r['azimuth'],
        'theta_dot_last_6': theta_hist,
        'tau_s': (r['theta'] / r['theta_dot']) if r['theta_dot'] > 1e-9 else None,
        'visual_half_size': r['visual_half_size'], 'paddle_face': r['paddle'][5],
        'forward_speed': m[0], 'lateral_speed': m[1], 'yaw_rate': m[2], 'saccade_remaining': m[3],
        # neural (the policy saw only DNp01 traces)
        'dnp01_left': r['dnp01_left'], 'dnp01_right': r['dnp01_right'],
        'dnp01_sum': r['dnp01_left'] + r['dnp01_right'],
        'dnp01_spikes_L_rel': spikes_l, 'dnp01_spikes_R_rel': spikes_r,
        'samples_since_previous_escape': None if not prev_esc else i - tick_index[prev_esc[-1]],
        'drive_peak_200ms': drive_peak, 'sensory_peak_L': int(sens_l.max()), 'sensory_peak_R': int(sens_r.max()),
        'volley_above_n0_envelope': bool(max(sens_l.max(), sens_r.max()) > N0_SENSORY_MAX),
        'neural_cause': neural,
        # counterfactual (simulator evidence only)
        'factual_min_horizontal_1_5s': f_min, 'counterfactual_min_horizontal_1_5s': cf_min,
        'counterfactual_time_of_min_s': cf_t_min, 'counterfactual_theta_max_1_5s': cf_theta_max,
        'counterfactual_lethal_window': cf_lethal, 'counterfactual_hits': cf_hits,
        'counterfactual_outcome': ('under paddle footprint' if cf_min is not None and cf_min < FOOTPRINT else
                                   'near pass' if cf_min is not None and cf_min < NEAR else 'safely separated'),
        'class': cls,
        # Post-hoc descriptor (defined after inspecting the events; not a preregistered class):
        # where the expansion came from.
        'expansion_regime': (
            'overhead foreshortening' if (sh := expansion_sources(rows, i)['expansion_share_from_apparent_size']) is not None
            and sh >= 0.6 and math.degrees(math.atan2(g['paddle_height'], g['horizontal_distance'])) >= 60
            else 'self-approach' if g['range_rate'] <= -40 and (sh is None or sh < 0.3) else 'mixed'),
        'factual_path': f_path, 'counterfactual_path': cf_path,
    }


def reference_sets():
    """Neural-pattern references: N1 classes and fixed-fly N0 N4B1C false triggers."""
    from tools import n4b2_analysis as A
    ref = {}
    n1 = A.n1_segments()
    for cls in ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach'):
        peaks, sens = [], []
        for s in [x for x in n1 if x.cls == cls]:
            ev = A.n4b1c_events(s.trace_l, s.trace_r)
            t = next((t for t, _ in ev if t >= s.anchors['onset']), None)
            if t is None:
                continue
            peaks.append(float(s.drive[max(0, t - PRE + 1):t + 1].sum(1).max()))
            ss = s.sensory[max(0, t - PRE + 1):t + 1]
            sens.append(int(max((ss[:, 0] + ss[:, 2]).max(), (ss[:, 1] + ss[:, 3]).max())))
        ref['n1_' + cls] = {'n_fired': len(peaks), 'drive_peak_median': float(np.median(peaks)) if peaks else None,
                            'drive_peak_range': [float(min(peaks)), float(max(peaks))] if peaks else None,
                            'sensory_peak_median': float(np.median(sens)) if sens else None}
    n0 = A.n0_original() + A.n0_chunks('n4b1_fresh')[0] + A.n0_chunks('n4b1c_holdout')[0]
    evs = []
    for s in n0:
        for t, lab in A.n4b1c_events(s.trace_l, s.trace_r):
            ss = s.sensory[max(0, t - PRE + 1):t + 1]
            evs.append({'segment': s.name, 'sample': t, 'paths': lab,
                        'drive_peak': float(s.drive[max(0, t - PRE + 1):t + 1].sum(1).max()),
                        'sensory_peak': int(max((ss[:, 0] + ss[:, 2]).max(), (ss[:, 1] + ss[:, 3]).max()))})
    ref['n0_n4b1c_false_triggers'] = evs
    return ref


def review_set(events):
    """Strongest 4 and weakest 4 by encoder drive peak, every class B / C event, and ambiguous
    cases (counterfactual closest distance within 25 units of a class boundary)."""
    def key(e):
        return (e['source'], e['seed'], e['tick'])
    order = sorted(events, key=lambda e: e['drive_peak_200ms'])
    picks = {}
    for e in order[-4:]:
        picks.setdefault(key(e), []).append('strongest drive')
    for e in order[:4]:
        picks.setdefault(key(e), []).append('weakest drive')
    for e in events:
        if e['class'] in ('B', 'C'):
            picks.setdefault(key(e), []).append('class ' + e['class'])
        d = e['counterfactual_min_horizontal_1_5s']
        if d is not None and (abs(d - FOOTPRINT) < 25 or abs(d - NEAR) < 25):
            picks.setdefault(key(e), []).append('ambiguous (near a class boundary)')
    threads = {'n4b2_dev': 2, 'n4b2_holdout': 2, 'runtime_validation': 4}
    out = []
    for e in events:
        if key(e) in picks:
            cmd = ('NUMBA_NUM_THREADS=%d python tools/n4b4_replay.py replay --source %s --seed %d'
                   % (threads.get(e['source'], 1), e['source'], e['seed']))
            out.append({'source': e['source'], 'seed': e['seed'], 'tick': e['tick'], 'why': picks[key(e)],
                        'replay': cmd, 'counterfactual': cmd + ' --suppress %d' % e['tick'],
                        'figure': 'artifacts/m1_8_n4b4/figures/event_%s_%d_%d.png' % key(e)})
    return out


def main():
    inv = json.loads((OUT / 'inventory.json').read_text(encoding='utf-8'))
    events = []
    checks = {}
    for ev in inv['events']:
        fname = '%s_seed%d' % (ev['source'], ev['seed'])
        fact, farr = load(fname)
        cf, carr = load('%s_cf%d' % (fname, ev['tick']))
        checks[fname] = fact['check']
        events.append(event_record(ev, fact, farr, cf, carr))
    for s in (101, 255):
        m, _ = load('runtime_validation_seed%d' % s)
        checks['runtime_validation_seed%d' % s] = m['check']
    minutes = inv['minutes']
    counts = Counter(e['class'] for e in events)
    from scipy.stats import chi2

    def upper(k):
        return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)
    rates = {c: {'events': counts.get(c, 0), 'per_min': counts.get(c, 0) / minutes, 'upper95_per_min': upper(counts.get(c, 0))}
             for c in 'ABC'}
    rates['all'] = {'events': len(events), 'per_min': len(events) / minutes, 'upper95_per_min': upper(len(events))}
    result = {'label': 'M1.8-N4B4 free-flight escape interpretation (research only, offline)',
              'minutes': minutes, 'runs': len(inv['runs']), 'reconstruction_checks': checks,
              'events': events, 'class_counts': dict(counts), 'rates': rates,
              'neural_counts': dict(Counter(e['neural_cause'] for e in events)),
              'outcome_counts': dict(Counter(e['counterfactual_outcome'] for e in events)),
              'direction_counts': dict(Counter(e['direction'] for e in events)),
              'path_counts': dict(Counter(e['paths'] for e in events)),
              'references': reference_sets()}
    result['review_set'] = review_set(events)
    regimes = Counter(e['expansion_regime'] for e in events)
    result['regime_counts'] = dict(regimes)
    result['regime_by_class'] = {'%s|%s' % k: v for k, v in Counter((e['expansion_regime'], e['class']) for e in events).items()}
    # Proposed metric split (section 6 of the report).
    n0_events, n0_minutes = 4, 1190.0      # N4B1C on all fixed-fly N0: dev 630 min (3), N4B2 holdout (0), N4B3 holdout (1)
    result['proposed_metrics'] = {
        'no_loom_neural_false_escapes': {'events': n0_events, 'minutes': n0_minutes, 'per_min': n0_events / n0_minutes,
                                         'upper95_per_min': float(chi2.ppf(0.95, 2 * n0_events + 2) / 2 / n0_minutes)},
        'free_flight_inappropriate_escapes (class C)': rates['C'],
        'free_flight_visual_model_artifact_escapes (overhead foreshortening)': {
            'events': regimes.get('overhead foreshortening', 0),
            'per_min': regimes.get('overhead foreshortening', 0) / minutes,
            'upper95_per_min': upper(regimes.get('overhead foreshortening', 0))},
        'free_flight_self_approach_escapes (legitimate looming)': {
            'events': regimes.get('self-approach', 0), 'per_min': regimes.get('self-approach', 0) / minutes,
            'upper95_per_min': upper(regimes.get('self-approach', 0))},
        'free_flight_all_escapes': rates['all']}
    (OUT / 'analysis.json').write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')
    print('events', len(events), 'classes', dict(counts), 'rates', {k: round(v['per_min'], 4) for k, v in rates.items()})
    print('neural', result['neural_counts'], 'outcome', result['outcome_counts'], 'direction', result['direction_counts'])
    print('all reconstructions exact:', all(c['exact'] for c in checks.values()))


if __name__ == '__main__':
    main()
