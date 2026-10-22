"""M1.8-N4B3 research: selective DNp04 threat readout.

Research only. No runtime, configuration, calibration, policy-whitelist, Retina, encoder,
brain, noise, lifecycle, physics or recorder change. Candidate readouts are evaluated
offline in shadow mode. Their inputs are restricted to what a policy could legally observe:
DNp01 and DNp04 spike trains (inferred from their traces) and the whitelisted MotionState.
Geometry, Retina and LC4/LPLC2 values are used only to label and interpret events.

The frozen N4B1C runtime decoder is the reference (tools/n4b2_analysis.n4b1c_events, the
runtime's own FixedEscapePolicy from the detached worktree at e3c55b3).

Modes:

    python tools/n4b3_analysis.py dev       # development evaluation of the whole family -> dev.json
    python tools/n4b3_analysis.py freeze    # hash-freeze tools/n4b3_criteria.py
    python tools/n4b3_analysis.py holdout   # frozen criteria on the new N0 + ROOM holdout -> holdout.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import glob
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('NUMBA_NUM_THREADS', '1')
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from tools import n4_diagnosis as D  # noqa: E402
from tools import n4b2_analysis as A  # noqa: E402
from tools import n4b3_criteria as K  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b3'
FROZEN_FILE = OUT / 'frozen_criteria.json'
TICKS_PER_MIN = 3000
DT = 0.02
N1_CLASSES = ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ================================================================== data ===
def zero_motion(n):
    return np.zeros((n, 4))


def with_motion(seg, motion):
    seg.motion = motion
    return seg


def n0_dev():
    segs = A.n0_original() + A.n0_chunks('n4b1_fresh')[0] + A.n0_chunks('n4b1c_holdout')[0]
    return [with_motion(s, zero_motion(s.n)) for s in segs]     # fixed fly: MotionState is zero


def n0_holdout():
    segs, files = [], sorted(glob.glob(str(OUT / 'n0_holdout_chunk*.npz')))
    for f in files:
        d = np.load(f)
        meta = json.loads(Path(f[:-4] + '.json').read_text(encoding='utf-8'))
        assert meta['panel_cells'] == [int(c) for c in A.CELLS]
        if meta['exact_trials'] != meta['trials']:
            raise SystemExit('%s not exact' % f)
        for i in range(d['spikes'].shape[0]):
            sp = d['spikes'][i]
            s = A.Seg('n0h_%d' % int(d['seeds'][i]), 'N0', sp,
                      A.C.trace(sp[:, A.IDX['DNp01']['L']]).astype(np.float64),
                      A.C.trace(sp[:, A.IDX['DNp01']['R']]).astype(np.float64),
                      d['sensory'][i], d['drive'][i], info={'seed': int(d['seeds'][i])})
            segs.append(with_motion(s, d['motion'][i]))
    return segs, files


def room_n4b3(which, seeds=None):
    """N4B3 ROOM runs (with MotionState)."""
    segs = []
    files = sorted(glob.glob(str(OUT / ('room_%s_seed*.npz' % which))))
    for f in files:
        seed = int(Path(f).stem.split('seed')[1])
        if seeds is not None and seed not in seeds:
            continue
        d = np.load(f)
        meta = json.loads(Path(f[:-4] + '.json').read_text(encoding='utf-8'))
        assert meta['panel_cells'] == [int(c) for c in A.CELLS]
        rows = meta['rows']
        tl = np.array([r['dnp01_left'] for r in rows])
        tr = np.array([r['dnp01_right'] for r in rows])
        s = A.Seg('room_%s_%d' % (which, seed), 'ROOM', d['spikes'], tl, tr, d['sensory'], d['drive'],
                  info={'seed': seed, 'rows': rows, 'set': which,
                        'runtime_escapes': [i for i, r in enumerate(rows) if r['escape']]})
        segs.append(with_motion(s, d['motion']))
    return segs


def room_n4b2_dev():
    """N4B2 development ROOM runs (no MotionState recorded: usable for neural gates only)."""
    segs = A.room_segments(A.ROOM_DEV_SEEDS)
    for s in segs:
        s.motion = None
    return segs


def session_motion():
    mot = {}
    for sess, name in D.SESSIONS.items():
        for line in open(ROOT / 'results/game/sessions' / name / 'policy_observations.jsonl', encoding='utf-8'):
            o = json.loads(line)
            m = o['observation']['motion']
            mot[(sess, o['episode'], o['tick'])] = (m['forward_speed'], m['lateral_speed'], m['yaw_rate'],
                                                   m['saccade_remaining'])
    return mot


def human():
    hs, eps = A.session_segments()
    mot = session_motion()
    for (sess, ep), e in eps.items():
        e['motion'] = np.array([mot[(sess, ep, r['tick'])] for r in e['rows']])
    # Event segments: rebuild motion from the episode rows they came from.
    for s in hs:
        e = eps[(s.info['session'], s.info['episode'])]
        tick_index = {r['tick']: j for j, r in enumerate(e['rows'])}
        rows = D.session_rows(D.SESSIONS[s.info['session']])[0][s.info['episode']]
        r0, r1 = s.info['rows']
        ticks = [rows[k]['tick'] for k in range(r0, r1 + 1) if rows[k]['neural']['brain_stepped']]
        idx = [tick_index[t] for t in ticks]
        assert len(idx) == s.n
        s.motion = e['motion'][idx]
        s.info['episode_index'] = idx
    return hs, eps


def n1():
    return [with_motion(s, zero_motion(s.n)) for s in A.n1_segments()]


# ================================================================== evaluation ===
def events(seg, crit):
    return K.evaluate(crit, seg.spikes, seg.trace_l, seg.trace_r, seg.motion,
                      A.IDX, lambda l, r: A.n4b1c_events(l, r))


def first_after(ev, t0):
    for t, lab in ev:
        if t >= t0:
            return t, lab
    return None, None


def background(segs, crit):
    minutes = sum(s.n for s in segs) / TICKS_PER_MIN
    ev = []
    for s in segs:
        for t, lab in events(s, crit):
            ev.append((s, t, lab))
    return {'minutes': minutes, 'events': len(ev), 'per_min': len(ev) / minutes if minutes else None,
            'upper95_per_min': A.poisson_upper(len(ev), minutes) if minutes else None}, ev


def positives(n1segs, hs, eps, crit):
    out = {}
    for cls in N1_CLASSES:
        lat = []
        for s in n1segs:
            if s.cls != cls:
                continue
            t, _ = first_after(events(s, crit), s.anchors['onset'])
            lat.append(None if t is None else t - s.anchors['onset'])
        d = [x for x in lat if x is not None]
        out['n1_' + cls] = {'detected': len(d), 'n': len(lat),
                            'median_s': float(np.median(d)) * DT if d else None,
                            'p95_s': float(np.percentile(d, 95)) * DT if d else None}
    ds = [s for s in hs if s.cls == 'human_direct_strike']
    v = []
    for s in ds:
        ev = events(s, crit)
        v.append(None if not ev else ev[0][0] - s.anchors['click'])
    d = [x for x in v if x is not None]
    after = [x for x in d if x >= 0]
    out['direct_strikes'] = {'fired': len(d), 'n': len(ds), 'before_click': sum(x < 0 for x in d),
                             'median_after_click_s': float(np.median(after)) * DT if after else None}
    for cls in ('human_hover_escape', 'human_strike_escape'):
        segs = [s for s in hs if s.cls == cls]
        leads = []
        for s in segs:
            ev = events(s, crit)
            t = ev[0][0] if ev else None
            leads.append(None if t is None or t > s.anchors['escape'] else s.anchors['escape'] - t)
        d = [x for x in leads if x is not None]
        out[cls] = {'met': len(d), 'n': len(segs), 'median_lead_samples': float(np.median(d)) if d else None}
    for cls, base in (('slow_close', 610), ('chase_before_589', 570), ('far_perched_reference', None),
                      ('voluntary_takeoff_reference', None)):
        s = [x for x in hs if x.cls == cls][0]
        ev = events(s, crit)
        out[cls] = [(t + base if base else t, lab) for t, lab in ev][:3]
    total = 0
    for key, e in eps.items():
        seg = A.Seg('ep', 'ep', e['spikes'], e['tl'], e['tr'], None, None)
        seg.motion = e['motion']
        total += len(events(seg, crit))
    out['episode_open_loop_firings'] = total
    return out


def room_event_context(seg, t):
    """Offline characterization of one ROOM event (interpretation only)."""
    rows, m = seg.info['rows'], seg.motion
    r = rows[t]
    fx, fy, fvx, fvy, heading = r['fly']
    px, py, ph, pvx, pvy = r['paddle']
    dx, dy = fx - px, fy - py
    rng = math.sqrt(dx * dx + dy * dy + ph * ph)
    fly_rr = (dx * fvx + dy * fvy) / rng
    pad_rr = -(dx * pvx + dy * pvy) / rng
    h0 = max(0, t - 25)
    l1, r1 = A.lr(seg.spikes, 'DNp01')
    return {'seed': seg.info['seed'], 'sample': t, 'tick': r['tick'], 'lifecycle_mode': r['lifecycle_mode'],
            'forward_speed': float(m[t, 0]), 'lateral_speed': float(m[t, 1]), 'yaw_rate': float(m[t, 2]),
            'saccade_remaining': float(m[t, 3]),
            'max_abs_yaw_last_0_5s': float(np.max(np.abs(m[h0:t + 1, 2]))),
            'saccade_in_last_0_5s': bool(np.any(m[h0:t + 1, 3] > 0)),
            'mean_forward_last_0_5s': float(np.mean(m[h0:t + 1, 0])),
            'dnp01_spikes_L_R_last_0_5s': [int(l1[h0:t + 1].sum()), int(r1[h0:t + 1].sum())],
            'theta': r['theta'], 'theta_dot': r['theta_dot'], 'azimuth': r['azimuth'],
            'range_3d': rng, 'range_rate_from_fly': fly_rr, 'range_rate_from_paddle': pad_rr,
            'runtime_escape_within_20': any(abs(t - k) <= 20 for k in seg.info['runtime_escapes'])}


def human_event_context(eps, sess, ep, j, motion):
    e = eps[(sess, ep)]
    r = e['rows'][j]
    f, sw = r['fly'], r['swatter']
    dx, dy = f['x'] - sw['x'], f['y'] - sw['y']
    rng = math.sqrt(dx * dx + dy * dy + sw['height'] ** 2)
    h0 = max(0, j - 25)
    return {'session': sess, 'episode': ep, 'tick': r['tick'], 'phase': sw['phase'],
            'forward_speed': float(motion[j, 0]), 'lateral_speed': float(motion[j, 1]),
            'yaw_rate': float(motion[j, 2]), 'saccade_remaining': float(motion[j, 3]),
            'max_abs_yaw_last_0_5s': float(np.max(np.abs(motion[h0:j + 1, 2]))),
            'saccade_in_last_0_5s': bool(np.any(motion[h0:j + 1, 3] > 0)),
            'mean_forward_last_0_5s': float(np.mean(motion[h0:j + 1, 0])),
            'theta': r['retina']['theta'], 'theta_dot': r['retina']['theta_dot'],
            'range_3d': rng, 'range_rate_from_fly': (dx * f['vx'] + dy * f['vy']) / rng,
            'range_rate_from_paddle': -(dx * sw['vx'] + dy * sw['vy']) / rng,
            'paddle_speed': sw['speed'], 'perched': r['ecology'].get('landing_perching')}


def self_motion_study(room_segs, eps):
    """Every ungated DNp04 pair event in free flight vs in the human sessions."""
    base = K.FAMILY['DNp04 pair (N4B2, ungated)']
    room = []
    for s in room_segs:
        for t, lab in events(s, base):
            c = room_event_context(s, t)
            c['side'] = lab
            room.append(c)
    hum = []
    for (sess, ep), e in eps.items():
        seg = A.Seg('ep', 'ep', e['spikes'], e['tl'], e['tr'], None, None)
        seg.motion = e['motion']
        for t, lab in events(seg, base):
            c = human_event_context(eps, sess, ep, t, e['motion'])
            c['side'] = lab
            hum.append(c)
    return room, hum


def summarize_contexts(rows, keys):
    out = {}
    for k in keys:
        v = np.array([r[k] for r in rows], float)
        out[k] = None if v.size == 0 else {'min': float(v.min()), 'p25': float(np.percentile(v, 25)),
                                           'median': float(np.median(v)), 'p75': float(np.percentile(v, 75)),
                                           'max': float(v.max())}
    return out


CONTEXT_KEYS = ('forward_speed', 'lateral_speed', 'yaw_rate', 'max_abs_yaw_last_0_5s', 'mean_forward_last_0_5s',
                'theta', 'theta_dot', 'range_3d', 'range_rate_from_fly', 'range_rate_from_paddle')


# ================================================================== modes ===
def dev():
    t0 = time.perf_counter()
    n0 = n0_dev()
    rooms = room_n4b3('dev')
    rooms_b2 = room_n4b2_dev()
    n1s = n1()
    hs, eps = human()
    result = {'label': 'M1.8-N4B3 development evaluation (research only, offline)',
              'n0_minutes': sum(s.n for s in n0) / TICKS_PER_MIN,
              'room_dev_minutes': sum(s.n for s in rooms) / TICKS_PER_MIN,
              'room_n4b2_dev_minutes': sum(s.n for s in rooms_b2) / TICKS_PER_MIN,
              'room_dev_seeds': [s.info['seed'] for s in rooms], 'family': K.FAMILY, 'results': {}}
    print('loaded %.0fs; N0 %.0f min, ROOM dev %.0f min' % (time.perf_counter() - t0, result['n0_minutes'],
                                                         result['room_dev_minutes']), flush=True)
    for name, crit in K.FAMILY.items():
        b0, _ = background(n0, crit)
        br, ev = background(rooms, crit)
        row = {'n0': b0, 'room_dev': br,
               'room_dev_events': [room_event_context(s, t) | {'label': lab} for s, t, lab in ev]}
        if not K.uses_motion(crit):
            row['room_n4b2_dev'] = background(rooms_b2, crit)[0]
        row['positives'] = positives(n1s, hs, eps, crit)
        result['results'][name] = row
        p = row['positives']
        print('%-44s N0 %2d | ROOM %2d/%.0f min | slow %s | weak %d | hover %d | direct %.2f | ep %d' % (
            name, b0['events'], br['events'], br['minutes'], p['slow_close'][:1], p['n1_weak_approach']['detected'],
            p['human_hover_escape']['met'], p['direct_strikes']['median_after_click_s'] or -1,
            p['episode_open_loop_firings']), flush=True)
    room_ev, hum_ev = self_motion_study(rooms, eps)
    result['self_motion'] = {'room_events': room_ev, 'human_events': hum_ev,
                             'room_summary': summarize_contexts(room_ev, CONTEXT_KEYS),
                             'human_summary': summarize_contexts(hum_ev, CONTEXT_KEYS)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'dev.json').write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')
    print('wrote dev.json %.0fs' % (time.perf_counter() - t0))


def freeze():
    if FROZEN_FILE.exists():
        print('already frozen', sha256(FROZEN_FILE))
        return
    if not K.FROZEN:
        raise SystemExit('tools/n4b3_criteria.py FROZEN is empty')
    if glob.glob(str(OUT / 'n0_holdout_chunk*.npz')) or glob.glob(str(OUT / 'room_holdout_seed*.npz')):
        raise SystemExit('holdout data exist; the freeze must precede them')
    body = {'label': 'M1.8-N4B3 frozen selective DNp04 criteria (research only)',
            'frozen_before_holdout': True, 'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'criteria': {k: K.FAMILY[k] for k in K.FROZEN}, 'frozen_names': list(K.FROZEN),
            'rationale': K.FROZEN_RATIONALE,
            'criteria_module': 'tools/n4b3_criteria.py', 'criteria_module_sha256': sha256(ROOT / 'tools/n4b3_criteria.py'),
            'analysis_module_sha256': sha256(__file__), 'record_module_sha256': sha256(ROOT / 'tools/n4b3_record.py'),
            'runtime_reference_commit': A.RUNTIME_COMMIT,
            'holdout_protocol': {
                'n0': 'tools/n4b3_record.py n0, chunks 0-3 x 150 trials x 1400 ticks = 280 min, seeds 410000 + chunk * 10000 + i, offsets default_rng(encoder_seed + 818181 + chunk), config 3d41113, fixed fly, no loom',
                'room': 'tools/n4b3_record.py room --set holdout, seeds 7401-7440 x 9000 ticks = 120 min, no player, parked paddle, runtime e3c55b3'},
            'development_data': ['N0 630 min (original, N4B1 fresh, N4B1C holdout)', 'ROOM N4B3 dev seeds 7301-7324 (72 min)',
                                 'ROOM N4B2 dev seeds 7101-7104 (12 min, neural gates only)', 'N1 300 trials',
                                 'both human sessions'],
            'not_used_for_design': ['N4B2 ROOM holdout seeds 7201-7212', 'N4B2 N0 holdout seeds 310000-340149']}
    FROZEN_FILE.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
    print('frozen', sha256(FROZEN_FILE))


def holdout():
    frozen = json.loads(FROZEN_FILE.read_text(encoding='utf-8'))
    if sha256(ROOT / 'tools/n4b3_criteria.py') != frozen['criteria_module_sha256']:
        raise SystemExit('tools/n4b3_criteria.py changed after the freeze')
    n0h, files = n0_holdout()
    rooms = room_n4b3('holdout')
    for s in rooms:
        pass
    for f in files + sorted(glob.glob(str(OUT / 'room_holdout_seed*.json'))):
        meta = json.loads(Path(f if f.endswith('.json') else f[:-4] + '.json').read_text(encoding='utf-8'))
        if meta.get('frozen_criteria_sha256') != sha256(FROZEN_FILE):
            raise SystemExit('%s not generated under the current freeze' % f)
    names = ['N4B1C (frozen runtime)', 'DNp04 pair (N4B2, ungated)'] + [n for n in frozen['frozen_names']
                                                                         if n not in ('N4B1C (frozen runtime)',
                                                                                      'DNp04 pair (N4B2, ungated)')]
    result = {'label': 'M1.8-N4B3 holdout (research only)', 'frozen_criteria_sha256': sha256(FROZEN_FILE),
              'n0_minutes': sum(s.n for s in n0h) / TICKS_PER_MIN,
              'room_minutes': sum(s.n for s in rooms) / TICKS_PER_MIN,
              'room_seeds': [s.info['seed'] for s in rooms],
              'max_n0_encoder_drive': float(max(np.max(s.drive) for s in n0h)),
              'runtime_replay_matches': all([t for t, _ in A.n4b1c_events(s.trace_l, s.trace_r)]
                                            == s.info['runtime_escapes'] for s in rooms),
              'results': {}}
    for name in names:
        crit = K.FAMILY[name]
        b0, _ = background(n0h, crit)
        br, ev = background(rooms, crit)
        comb = {'minutes': b0['minutes'] + br['minutes'], 'events': b0['events'] + br['events']}
        comb['upper95_per_min'] = A.poisson_upper(comb['events'], comb['minutes'])
        result['results'][name] = {'n0': b0, 'room': br, 'combined': comb,
                                   'room_events': [room_event_context(s, t) | {'label': lab} for s, t, lab in ev]}
        print('%-44s N0 %d/%.0f (up %.4f) | ROOM %d/%.0f (%.3f/min, up %.3f) | combined up %.4f' % (
            name, b0['events'], b0['minutes'], b0['upper95_per_min'], br['events'], br['minutes'],
            br['per_min'], br['upper95_per_min'], comb['upper95_per_min']))
    room_ev, _ = self_motion_study(rooms, {})
    result['self_motion_room_events'] = room_ev
    result['self_motion_room_summary'] = summarize_contexts(room_ev, CONTEXT_KEYS)
    (OUT / 'holdout.json').write_text(json.dumps(result, indent=1, default=float) + '\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('dev', 'freeze', 'holdout'))
    args = ap.parse_args()
    {'dev': dev, 'freeze': freeze, 'holdout': holdout}[args.mode]()


if __name__ == '__main__':
    main()
