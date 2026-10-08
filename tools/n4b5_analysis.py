"""M1.8-N4B5 research: paddle visual-geometry review (offline analyses).

Research only. No runtime, configuration, Retina, World, encoder, brain, decoder or policy
change; N4B1C is not reopened. WORLD state is used offline to recompute the Retina's theta
under candidate apparent-size formulas (tools/n4b5_geometry.py).

Alignment (N4B4): the Retina of tick t is projected from the world state stored at tick t-1
(rows hold the post-tick state), and theta_dot is the finite difference of consecutive
projections.

Modes:

    python tools/n4b5_analysis.py verify      # G0 reproduces every recorded theta
    python tools/n4b5_analysis.py analytic    # synthetic straight passes under a parked paddle
    python tools/n4b5_analysis.py events      # decomposition of the N4B4 events and human episode 5
    python tools/n4b5_analysis.py freeze      # hash-freeze tools/n4b5_geometry.py
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from tools import n4b5_geometry as G  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b5'
N4B4 = ROOT / 'artifacts/m1_8_n4b4'
SESSIONS = {'strict_n2': '20260923T005351.731330Z-38255ec8', 'n2b': '20260924T000111.561327Z-c337a721'}
DT = 0.02
FROZEN_FILE = OUT / 'frozen_geometry.json'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def state_room(row):
    fx, fy = row['fly'][0], row['fly'][1]
    px, py, h, _, _, face, orient = row['paddle']
    return {'fx': fx, 'fy': fy, 'px': px, 'py': py, 'height': h, 'face': face, 'orientation': orient}


def state_session(row):
    f, s = row['fly'], row['swatter']
    return {'fx': f['x'], 'fy': f['y'], 'px': s['x'], 'py': s['y'], 'height': s['height'],
            'face': s['face'], 'orientation': s['orientation']}


def th(name, s):
    return G.theta(name, s['fx'], s['fy'], s['px'], s['py'], s['height'], s['face'], s['orientation'])


def session_rows(name):
    rows = [json.loads(line) for line in open(ROOT / 'results/game/sessions' / name / 'ticks.jsonl', encoding='utf-8')]
    eps = {}
    for r in rows:
        eps.setdefault(r['episode'], []).append(r)
    cfg = json.loads((ROOT / 'results/game/sessions' / name / 'manifest.json').read_text(encoding='utf-8'))['config']
    return eps, cfg


# ------------------------------------------------------------------ verify ---
def verify():
    out = {'room': {}, 'sessions': {}}
    worst = 0.0
    for f in sorted(glob.glob(str(N4B4 / '*_seed*.json'))):
        m = json.loads(Path(f).read_text(encoding='utf-8'))
        rows = m['rows']
        err = max(abs(th('G0_current', state_room(rows[i - 1])) - rows[i]['theta']) for i in range(1, len(rows)))
        out['room'][Path(f).stem] = err
        worst = max(worst, err)
    for sess, name in SESSIONS.items():
        eps, cfg = session_rows(name)
        sw = cfg['swatter']
        assert sw['paddle_radius'] == G.PADDLE_RADIUS and sw['edge_on_factor'] == G.EDGE_ON \
            and sw['directional']['tilt_anisotropy'] == G.ANISOTROPY
        e = 0.0
        for rows in eps.values():
            for i in range(1, len(rows)):
                e = max(e, abs(th('G0_current', state_session(rows[i - 1])) - rows[i]['retina']['theta']))
        out['sessions'][sess] = e
        worst = max(worst, e)
    out['max_abs_error'] = worst
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'verify.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print('G0 reproduction: %d ROOM replays, 2 sessions; max abs theta error %.3g' % (len(out['room']), worst))


# ------------------------------------------------------------------ analytic ---
def synthetic_pass(name, offset, cross_deg, speed=200.0, height=320.0, face=0.0, orientation=0.0, span=600.0):
    """Fly flying straight past a parked paddle at (0, 0); closest horizontal distance
    `offset`; flight direction at `cross_deg` to the paddle orientation axis."""
    d = math.radians(cross_deg)
    ux, uy = math.cos(orientation + d), math.sin(orientation + d)
    nx, ny = -uy, ux
    n = int(2 * span / speed / DT) + 1
    thetas, halfs, ranges = [], [], []
    for k in range(n):
        s = -span + k * speed * DT
        fx, fy = nx * offset + ux * s, ny * offset + uy * s
        thetas.append(G.theta(name, fx, fy, 0.0, 0.0, height, face, orientation))
        halfs.append(G.half_size(name, fx, fy, 0.0, 0.0, height, face, orientation))
        ranges.append(math.sqrt(fx * fx + fy * fy + height * height))
    thetas = np.array(thetas)
    td = np.diff(thetas) / DT
    # range-only theta_dot with the half-size frozen at each step's start
    hr = np.array(halfs)
    rr = np.array(ranges)
    td_range = (2 * np.arctan(hr[:-1] / rr[1:]) - 2 * np.arctan(hr[:-1] / rr[:-1])) / DT
    td_size = td - td_range
    return {'max_theta_dot': float(td.max()), 'max_theta_dot_size_term': float(td_size.max()),
            'max_theta_dot_range_term': float(td_range.max()), 'max_one_tick_size_jump': float(np.abs(np.diff(2 * np.arctan(hr / rr)) - (2 * np.arctan(hr[:-1] / rr[1:]) - 2 * np.arctan(hr[:-1] / rr[:-1]))).max()),
            'theta_min': float(thetas.min()), 'theta_max': float(thetas.max())}


def analytic():
    offsets = (0.0, 2.0, 5.0, 10.0, 25.0, 50.0, 100.0, 150.0, 200.0, 300.0)
    crosses = (0.0, 45.0, 90.0)
    res = {}
    for name in G.CANDIDATES:
        res[name] = {}
        for c in crosses:
            for o in offsets:
                res[name]['cross%d_offset%d' % (c, o)] = synthetic_pass(name, o, c)
    # Strike-like reference: face ramps 0 -> 1 while height drops 320 -> 24 above a fixed fly
    strike = {}
    for name in G.CANDIDATES:
        rows = []
        for off in (30.0, 100.0, 170.0):
            ths = []
            for k in range(26):
                q = k / 25
                h = 320 - (320 - 24) * q
                ths.append(G.theta(name, off, 0.0, 0.0, 0.0, h, q, 0.0))
            rows.append({'offset': off, 'theta_start': ths[0], 'theta_end': ths[-1],
                         'max_theta_dot': float(np.max(np.diff(ths)) / DT)})
        strike[name] = rows
    out = {'passes': res, 'strike_like': strike,
           'note': 'speed 200 units/s, paddle at height 320, face 0, parked; 20 ms samples'}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'analytic.json').write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    for name in G.CANDIDATES:
        print(name)
        for c in crosses:
            line = ['%4d:%.2f/%.2f' % (o, res[name]['cross%d_offset%d' % (c, o)]['max_theta_dot'],
                                        res[name]['cross%d_offset%d' % (c, o)]['max_theta_dot_size_term']) for o in offsets]
            print('  cross %2d  offset:max_td/size_td ' % c + ' '.join(line))
        print('  strike-like', [(r['offset'], round(r['theta_start'], 3), round(r['theta_end'], 3), round(r['max_theta_dot'], 2)) for r in strike[name]])


# ------------------------------------------------------------------ events ---
def event_series(rows, i, state_fn, theta_key, n=12):
    """Per-candidate theta_dot at the event sample and its decomposition (G0)."""
    out = {}
    for name in G.CANDIDATES:
        cur = th(name, state_fn(rows[i - 1]))
        prev = th(name, state_fn(rows[i - 2]))
        win = [(th(name, state_fn(rows[j - 1])) - th(name, state_fn(rows[j - 2]))) / DT for j in range(i - n + 1, i + 1)]
        out[name] = {'theta': cur, 'theta_dot': (cur - prev) / DT, 'max_theta_dot_last_12': max(win)}
    dec = {k: 0.0 for k in ('range', 'bearing', 'orientation', 'face', 'total')}
    for j in range(i - 9, i + 1):
        d = G.decompose(state_fn(rows[j - 2]), state_fn(rows[j - 1]))
        for k in dec:
            dec[k] += d[k]
    s = state_fn(rows[i - 1])
    out['G0_decomposition_last_10_samples'] = dec
    out['elevation_deg'] = G.elevation_deg(s['fx'], s['fy'], s['px'], s['py'], s['height'])
    out['recorded_theta'] = rows[i][theta_key] if theta_key else rows[i]['retina']['theta']
    return out


def events():
    a = json.loads((N4B4 / 'analysis.json').read_text(encoding='utf-8'))
    res = {'room_events': [], 'episode5': []}
    for e in a['events']:
        m = json.loads((N4B4 / ('%s_seed%d.json' % (e['source'], e['seed']))).read_text(encoding='utf-8'))
        rows = m['rows']
        i = {r['tick']: k for k, r in enumerate(rows)}[e['tick']]
        rec = event_series(rows, i, state_room, 'theta')
        rec.update({'source': e['source'], 'seed': e['seed'], 'tick': e['tick'],
                    'regime': e['expansion_regime'], 'class': e['class'], 'drive_peak': e['drive_peak_200ms']})
        res['room_events'].append(rec)
    eps, _ = session_rows(SESSIONS['n2b'])
    rows = eps[5]
    idx = {r['tick']: k for k, r in enumerate(rows)}
    for t in range(600, 681):
        i = idx[t]
        cand = {name: (th(name, state_session(rows[i - 1])) - th(name, state_session(rows[i - 2]))) / DT
                for name in G.CANDIDATES}
        d = G.decompose(state_session(rows[i - 2]), state_session(rows[i - 1]))
        s = state_session(rows[i - 1])
        res['episode5'].append({'tick': t, 'recorded_theta_dot': rows[i]['retina']['theta_dot'], 'theta_dot': cand,
                                'G0_step_decomposition': d,
                                'elevation_deg': G.elevation_deg(s['fx'], s['fy'], s['px'], s['py'], s['height']),
                                'phase': rows[i]['swatter']['phase']})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'events.json').write_text(json.dumps(res, indent=1) + '\n', encoding='utf-8')
    print('%-14s %5s %5s %-24s %5s | %s' % ('source', 'seed', 'tick', 'regime', 'elev',
                                           ' '.join('%8s' % c[:8] for c in G.CANDIDATES)) + ' | G0 10-sample: range bearing orient face')
    for r in res['room_events']:
        d = r['G0_decomposition_last_10_samples']
        print('%-14s %5d %5d %-24s %5.0f | %s | %+.3f %+.3f %+.3f %+.3f' % (
            r['source'][:14], r['seed'], r['tick'], r['regime'], r['elevation_deg'],
            ' '.join('%8.2f' % r[c]['max_theta_dot_last_12'] for c in G.CANDIDATES),
            d['range'], d['bearing'], d['orientation'], d['face']))
    print('episode 5 (theta_dot per candidate):')
    for r in res['episode5']:
        if 608 <= r['tick'] <= 628 or r['tick'] >= 663:
            d = r['G0_step_decomposition']
            print('  %d %-8s elev %3.0f rec %+6.2f | %s | range %+.4f bearing %+.4f orient %+.4f face %+.4f' % (
                r['tick'], r['phase'][:8], r['elevation_deg'], r['recorded_theta_dot'],
                ' '.join('%+6.2f' % r['theta_dot'][c] for c in G.CANDIDATES), d['range'], d['bearing'],
                d['orientation'], d['face']))


def freeze():
    if FROZEN_FILE.exists():
        print('already frozen', sha256(FROZEN_FILE))
        return
    body = {'label': 'M1.8-N4B5 frozen paddle apparent-size candidates (research only)',
            'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'candidates': list(G.CANDIDATES), 'geometry_module_sha256': sha256(ROOT / 'tools/n4b5_geometry.py'),
            'evaluated_before_freeze': ['G0 reproduction of recorded thetas', 'synthetic straight passes',
                                        'decomposition of the 21 N4B4 events and human episode 5 (descriptive)'],
            'evaluated_after_freeze': ['N1 re-simulation (300 trials)', 'both human sessions, open-loop re-simulation',
                                       'fixed-fly N0 (invariance check)', 'no-player ROOM closed loop (83 runs)'],
            'primary_hypothesis': 'G3_elevation_aware (minimal geometric change: identical to G0 at low elevation)',
            'geometry_findings_before_freeze': [
                'G0 size-term theta_dot under a parked paddle grows as 1/offset: 6.86 rad/s at 0 and 2.52 at 10 units '
                '(crossing 90 deg, 200 units/s), against 0.13 for pure range change',
                'G4 alters strike-like stimuli (episode-5 strike and synthetic strike), so it is kept as a geometric '
                'reference, not as a runtime candidate'],
            'runtime_candidate_criteria (all must hold, N4B1C decoder unchanged)': [
                'synthetic overhead passes: size-term theta_dot <= 2 x the range-only theta_dot at every offset',
                'N1 strong_direct and medium_committed: N4B1C detects 60 / 60 each; median latency within +0.02 s of G0',
                'human direct strikes: every strike still produces an N4B1C firing by resolution; median latency after '
                'the click within +0.02 s of G0',
                'far perched non-contact approach: no N4B1C firing',
                'fixed-fly N0: identical N4B1C events (static paddle)',
                'no-player ROOM (83 runs): category C (foreshortening-driven) escapes reduced; category A unchanged; '
                'category B (inappropriate) below the provisional 0.1/min working criterion',
                'weak / glancing / aborted N1, hover bouts and self-approach escapes: reported descriptively; large '
                'losses on self-approach (category D) must be explained geometrically']}
    OUT.mkdir(parents=True, exist_ok=True)
    FROZEN_FILE.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
    print('frozen', sha256(FROZEN_FILE))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('verify', 'analytic', 'events', 'freeze'))
    args = ap.parse_args()
    {'verify': verify, 'analytic': analytic, 'events': events, 'freeze': freeze}[args.mode]()


if __name__ == '__main__':
    main()
