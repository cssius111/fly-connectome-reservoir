"""M1.8-N4B1C runtime-candidate validation (lateral_dual_path_v1).

Every decision here comes from the RUNTIME policy built by `game.session.build_policy`
from the working-tree ROOM configuration; research numbers are read only for comparison.

Modes (each writes artifacts/m1_8_n4b1c_runtime/<mode>.json):

replays      original N0 (70 min), N4B1 fresh N0 (280 min), N4B1C holdout (280 min),
             all 300 N1 trials and both human sessions. Every N0 and N1 trial is also
             compared tick by tick with an independent re-implementation of the frozen
             N4B1C rule (test_game_n4b1c_decoder.reference_decisions).
closed-loop  the corrected tools/n2_closed_loop.py scenarios (zero-loom perched fixture)
             for the runtime candidate and the rejected N2b decoder, plus the required
             re-escape diagnostic with per-sample neural logging.
record       write a new runtime-candidate session recording and replay it exactly.
replay       replay one existing recording (--path, --relaxed-source); run in a process
             whose NUMBA_NUM_THREADS equals the recorded thread count.

    python tools/n4b1c_runtime_validation.py replays
    python tools/n4b1c_runtime_validation.py closed-loop
    python tools/n4b1c_runtime_validation.py record
    python tools/n4b1c_runtime_validation.py replay --path <session dir> [--relaxed-source]
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if __name__ == '__main__':
    os.environ.setdefault('NUMBA_NUM_THREADS', '4')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402

OUT = ROOT / 'artifacts/m1_8_n4b1c_runtime'
DT = 0.02
N2B_ARCHIVE = '2c306174d7bdb4e74b6c5517519ae695bd90cf44'
STRIKE_PHASES = ('windup', 'active', 'commit', 'fast_swing', 'active_contact')
LATERAL_STATE = ('lateral_window_samples', 'lateral_required_spikes', 'trace_decay', '_sample_index',
                 '_lat_prev_left', '_lat_prev_right', '_lat_last_left', '_lat_last_right',
                 '_lat_now_left', '_lat_now_right', '_pending_paths', '_trigger_paths')


def room():
    from game.session import load_config
    return load_config(ROOT / 'game_room_config.json')


_RUNTIME = []


def runtime_policy():
    """A fresh runtime policy: build_policy of the working-tree ROOM config (built once,
    then deep-copied and reset, which is equivalent to building it again)."""
    from game.session import build_policy
    if not _RUNTIME:
        _RUNTIME.append(build_policy(room(), ROOT)[0])
    p = copy.deepcopy(_RUNTIME[0])
    p.reset()
    return p


def n2b_config():
    return json.loads(subprocess.check_output(['git', 'show', N2B_ARCHIVE + ':game_room_config.json'],
                                              cwd=ROOT, text=True))


def n2b_policy():
    from game.session import build_policy
    return build_policy(n2b_config(), ROOT)[0]


def poisson_upper(k, minutes):
    from scipy.stats import chi2
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def motor(lv, rv):
    from game.action import MotorState
    return MotorState(float(lv), float(rv), 0.0, 0.0, np.zeros(1))


def replay_trace(policy, left, right):
    policy.reset()
    fires = []
    for t in range(left.size):
        if policy.decide(motor(left[t], right[t])).escape:
            d = policy.criterion_diagnostics()
            fires.append({'tick': t, 'channel': d['escape_trigger_channel'], 'paths': d['escape_trigger_paths'],
                          'left_last': d['escape_lateral_last_spike_left'],
                          'right_last': d['escape_lateral_last_spike_right']})
    return fires


def path_counts(fires):
    return dict(Counter(f['paths'] for f in fires))


# ------------------------------------------------------------------ replays ---
def replays():
    from tools import n4b1_analysis as A
    from test_game_n4b1c_decoder import reference_decisions
    research = json.loads((ROOT / 'artifacts/m1_8_n4b1c/evaluation.json').read_text(encoding='utf-8'))
    ref = research['candidates']['A OR N2b']
    orig, fresh, _ = A.n0_sets()
    hold = []
    for c in range(4):
        z = np.load(ROOT / ('artifacts/m1_8_n4b1c/holdout_chunk%d.npz' % c))
        hold += list(zip(z['left'], z['right']))
    out = {'label': 'M1.8-N4B1C runtime replays (runtime build_policy, working-tree ROOM config)',
           'decoder': runtime_policy().criterion_diagnostics()['escape_decoder'], 'n0': {}, 'n1': {}}
    mismatch_trials = 0
    for name, trials in (('original_70', orig), ('n4b1_fresh_280', fresh), ('n4b1c_holdout_280', hold)):
        fires_all, refire, sides = [], 0, Counter()
        for lt, rt in trials:
            f = replay_trace(runtime_policy(), lt, rt)
            if [x['tick'] for x in f] != reference_decisions(list(zip(lt.tolist(), rt.tolist()))):
                mismatch_trials += 1
            fires_all += f
            refire += sum(1 for a, b in zip(f, f[1:]) if b['tick'] - a['tick'] <= 21)
        minutes = sum(lt.size for lt, _ in trials) * DT / 60
        k = len(fires_all)
        out['n0'][name] = {'trials': len(trials), 'minutes': minutes, 'false_events': k,
                           'per_minute': k / minutes, 'upper95_per_minute': poisson_upper(k, minutes),
                           'paths': path_counts(fires_all), 'refire_at_refractory_expiry': refire}
    total_k = sum(v['false_events'] for v in out['n0'].values())
    total_m = sum(v['minutes'] for v in out['n0'].values())
    out['n0']['all_630'] = {'minutes': total_m, 'false_events': total_k,
                            'upper95_per_minute': poisson_upper(total_k, total_m)}
    out['n0']['research_A_or_N2b'] = {'original': ref['n0_original_dev']['false_events'],
                                      'n4b1_fresh': ref['n0_n4b1_fresh_dev']['false_events'],
                                      'holdout': ref['n0_holdout']['false_events']}
    n1 = A.n1_sets()
    per = {}
    for t in n1:
        f = replay_trace(runtime_policy(), t['left'], t['right'])
        if [x['tick'] for x in f] != reference_decisions(list(zip(t['left'].tolist(), t['right'].tolist()))):
            mismatch_trials += 1
        inside = [x for x in f if t['window'][x['tick']]]
        c = per.setdefault(t['kind'], {'trials': 0, 'fired': 0, 'lat': [], 'paths': Counter()})
        c['trials'] += 1
        if inside:
            c['fired'] += 1
            c['paths'][inside[0]['paths']] += 1
            if t['click'] is not None:
                c['lat'].append((inside[0]['tick'] - t['click']) * DT)
    for k, c in per.items():
        out['n1'][k] = {'trials': c['trials'], 'fired': c['fired'],
                        'median_s': float(np.median(c['lat'])) if c['lat'] else None,
                        'p95_s': float(np.percentile(c['lat'], 95)) if c['lat'] else None,
                        'first_paths': dict(c['paths']),
                        'research': {kk: ref['n1'][k][kk] for kk in ('fired', 'median_s', 'p95_s')}}
    out['reference_mismatch_trials'] = mismatch_trials
    out['reference_trials_checked'] = len(orig) + len(fresh) + len(hold) + len(n1)
    print('N0', json.dumps({k: (v['false_events'], round(v['upper95_per_minute'], 4), v.get('paths'))
                            for k, v in out['n0'].items() if 'minutes' in v}), flush=True)
    print('N1', json.dumps({k: (v['fired'], v['median_s'], v['p95_s']) for k, v in out['n1'].items()}), flush=True)
    print('reference mismatches', mismatch_trials, 'of', out['reference_trials_checked'], flush=True)
    out['human'] = human(A, ref)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'replays.json').write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    print('written', OUT / 'replays.json')


def runtime_synced(snapshot, rows, start):
    """Runtime candidate carrying the recorded policy's motor/refractory state at a segment
    start (the start of an episode or the sample after a recorded escape, where every
    decoder's evidence is empty). Lateral memory is empty; the previous trace values are
    the recorded values of the preceding sample (0 at an episode start)."""
    from tools import n4b1_analysis as A
    p = runtime_policy()
    skip = set(A.DECODER_STATE) | set(LATERAL_STATE)
    p.__dict__.update({k: copy.deepcopy(v) for k, v in snapshot.__dict__.items() if k not in skip})
    p._window.clear()
    p._streak = 0
    p._sample_index = 0
    p._lat_last_left = p._lat_last_right = None
    if start > 0:
        p._lat_prev_left = rows[start - 1]['neural']['dnp01_left']
        p._lat_prev_right = rows[start - 1]['neural']['dnp01_right']
    else:
        p._lat_prev_left = p._lat_prev_right = 0.0
    return p


def human(A, ref):
    A.synced = lambda factory, snapshot, rows, start: runtime_synced(snapshot, rows, start)
    sessions = {}
    for k, path in (('strict_n2', ROOT / 'results/game/sessions/20260923T005351.731330Z-38255ec8'),
                    ('n2b', ROOT / 'results/game/sessions/20260924T000111.561327Z-c337a721')):
        eps, manifest, strikes = A.load_session(path)
        snaps, mism = A.reproduce(eps, manifest)
        sessions[k] = {'eps': eps, 'snaps': snaps, 'strikes': strikes, 'segs_cache': {},
                       'reproduction_mismatches': mism}
    out = {}
    for sk, sess in sessions.items():
        segs = A.human_eval(runtime_policy, sess)
        sess['segs_cache'][id(runtime_policy)] = segs
        h = A.summarise_human(segs, sess, 'runtime')
        h['trigger_channels'] = dict(Counter(s['fire']['channel'] for s in segs if s['fire']))
        h['reproduction_mismatches'] = sess['reproduction_mismatches']
        h['research_hover_met'] = [ref['human'][sk]['hover']['fired_no_later'], ref['human'][sk]['hover']['n']]
        h['direct_strike_latencies'] = [x.get('latency_s') for x in h['direct_strikes']['strikes']]
        out[sk] = h
        print('human %s: met %d/%d hover %d/%d (research %s) strike %d/%d | strikes %s' % (
            sk, h['fired_no_later'], h['recorded_escapes'], h['hover']['fired_no_later'], h['hover']['n'],
            h['research_hover_met'], h['strike_phase']['fired_no_later'], h['strike_phase']['n'],
            h['direct_strike_latencies'][:8]), flush=True)
    cases = A.special_cases(runtime_policy, sessions)
    # Clean-start slow-close with the runtime lateral state primed from tick 609.
    rows = sessions['n2b']['eps'][5]
    idx = {r['tick']: j for j, r in enumerate(rows)}
    p = runtime_policy()
    p._lat_prev_left = rows[idx[609]]['neural']['dnp01_left']
    p._lat_prev_right = rows[idx[609]]['neural']['dnp01_right']
    clean = None
    for i in range(idx[610], idx[670] + 1):
        if p.decide(A.row_motor(rows[i])).escape:
            clean = rows[i]['tick']
            break
    cases['slow_close_clean_start_fire_tick'] = clean
    out['cases'] = cases
    out['research_cases'] = {k: ref['cases'][k] for k in ('slow_close_synced', 'slow_close_clean_start_fire_tick',
                                                          'chase_before_589')}
    print('cases: far perched in bout %s | voluntary %s | slow-close synced %s clean %s | chase589 %s' % (
        cases['far_perched']['fires_in_bout_2434_2528'],
        cases['voluntary_takeoff']['fires_within_1s_before_to_0_5s_after'],
        cases['slow_close_synced']['fire_tick'], clean, cases['chase_before_589']['fire_tick']), flush=True)
    return out


# ------------------------------------------------------------------ closed loop ---
def closed_loop():
    import tools.n2_closed_loop as C
    from game.session import Session
    config = room()
    factories = {'runtime_lateral_dual_path_v1': runtime_policy, 'rejected_N2b': n2b_policy}
    summary_orig = C.Run.summary

    def summary_with_escapes(self):
        out = summary_orig(self)
        out['escape_list'] = [{'tick': e['tick'], 'channel': e['channel'], 'encoder_drive': e['encoder_drive'],
                               'theta_dot': e['theta_dot'], 'lifecycle_mode': e['lifecycle_mode']}
                              for e in self.escapes]
        return out
    C.Run.summary = summary_with_escapes
    probe = Session(config, policy=runtime_policy(), seed=1, mode='evaluation')
    brain = probe.brain
    probe.close()
    results, started = {}, time.perf_counter()

    def run(name, fn, *a):
        row = {label: fn(config, make(), *a[:1], brain, *a[1:]) for label, make in factories.items()}
        results.setdefault(name, []).append(row)
        print('%-28s %s  %.0fs' % (name, ' | '.join('%s pre %d post %s %s' % (
            k[:12], r['escapes_before_click'], r['first_escape_latency_from_click_s'],
            r['first_escape_after_click'] and r['first_escape_after_click']['channel'])
            for k, r in row.items()), time.perf_counter() - started), flush=True)

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
    paths = {}
    for scen, rows in results.items():
        for row in rows:
            for label, r in row.items():
                p = paths.setdefault(scen, {}).setdefault(label, {'channels': Counter(), 'refire': 0, 'zero_drive': 0})
                es = r['escape_list']
                for e in es:
                    p['channels'][e['channel']] += 1
                    p['zero_drive'] += e['encoder_drive'] == 0.0
                p['refire'] += sum(1 for a, b in zip(es, es[1:]) if b['tick'] - a['tick'] <= 21)
    report = {'label': 'M1.8-N4B1C runtime closed loop (runtime candidate vs rejected N2b)',
              'summary': {k: C.aggregate(v) for k, v in results.items()},
              'channels': {s: {l: {'channels': dict(v['channels']), 'refire_at_refractory_expiry': v['refire'],
                                   'escapes_with_zero_encoder_drive': v['zero_drive']}
                               for l, v in d.items()} for s, d in paths.items()},
              'scenarios': results, 're_escape_diagnostic': re_escape_diagnostic(config, brain, factories),
              'wall_seconds': time.perf_counter() - started}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'closed_loop.json').write_text(json.dumps(report, indent=1, default=str) + '\n', encoding='utf-8')
    print('written', OUT / 'closed_loop.json')


def re_escape_diagnostic(config, brain, factories):
    """Per-sample neural logging of the airborne committed-strike scenario (the scenario
    where N4B1C research saw repeated re-escapes at refractory expiry)."""
    import tools.n2_closed_loop as C
    from game.session import dnp01_trace_decay
    decay = dnp01_trace_decay(config)
    out = {}
    for label, make in factories.items():
        events = []
        stale_total, decisions_total = [0], [0]
        for seed in (11, 12, 13, 14, 15, 16):
            for offset in ((20.0, 10.0), (-45.0, 30.0)):
                run = C.Run(config, make(), seed, brain, ecology=False)
                log = []
                prev = {'L': 0.0, 'R': 0.0}

                def step(pointer, strike=False):
                    # The brain (and the policy) steps only while the fly is alive at the
                    # start of the tick. After death Session.tick passes Action() to the
                    # world, but fly_loop.last_action keeps the last real decision, so a
                    # harness reading last_action would count stale escapes.
                    stepped = bool(run.s.world.fly.alive)
                    run.step(pointer, strike)
                    s = run.s
                    m = s.fly_loop.last_motor
                    if m is None:
                        return
                    spikes = {'L': 0, 'R': 0}
                    if stepped:
                        for side, v in (('L', m.dnp01_left), ('R', m.dnp01_right)):
                            spikes[side] = int(v - decay * prev[side] >= 0.5)
                            prev[side] = v
                    d = s.encoder.last_drive or {}
                    crit = s.policy.criterion_diagnostics()
                    log.append({'tick': run.tick - 1, 'L': m.dnp01_left, 'R': m.dnp01_right,
                                'spk_L': spikes['L'], 'spk_R': spikes['R'],
                                'stepped': stepped,
                                'escape': stepped and bool(s.fly_loop.last_action.escape),
                                'stale_last_action_escape': (not stepped) and bool(s.fly_loop.last_action.escape),
                                'channel': crit['escape_trigger_channel'],
                                'paths': crit.get('escape_trigger_paths', ''),
                                'drive': sum(d.get(k, 0.0) for k in ('loomL', 'loomR', 'threatL', 'threatR')),
                                'theta_dot': 0.0 if s.last_retina is None else s.last_retina.theta_dot,
                                'phase': str(getattr(s.world.swatter.phase, 'value', s.world.swatter.phase)),
                                'distance': math.hypot(s.world.fly.x - s.world.swatter.x,
                                                       s.world.fly.y - s.world.swatter.y)})
                try:
                    for _ in range(40):
                        step(C.PARKED)
                    for _ in range(90):
                        step((run.fly.x + offset[0], run.fly.y + offset[1]))
                    for t in range(90):
                        step((run.fly.x + offset[0], run.fly.y + offset[1]), strike=(t == 0))
                finally:
                    run.close()
                stale_total[0] += sum(r['stale_last_action_escape'] for r in log)
                decisions_total[0] += sum(r['escape'] for r in log)
                esc = [i for i, r in enumerate(log) if r['escape']]
                for a, b in zip(esc, esc[1:]):
                    gap = log[b]['tick'] - log[a]['tick']
                    if gap > 21:
                        continue
                    window = log[a + 1:b + 1]
                    new_l = sum(r['spk_L'] for r in window)
                    new_r = sum(r['spk_R'] for r in window)
                    last5 = log[max(a + 1, b - 4):b + 1]
                    residual = (log[a]['L'] + log[a]['R']) * decay ** gap
                    events.append({'seed': seed, 'offset': list(offset), 'tick': log[b]['tick'], 'gap_ticks': gap,
                                   'channel': log[b]['channel'], 'paths': log[b]['paths'],
                                   'new_spikes_since_previous_escape_L': new_l,
                                   'new_spikes_since_previous_escape_R': new_r,
                                   'spikes_in_last_5_samples': sum(r['spk_L'] + r['spk_R'] for r in last5),
                                   'summed_trace_at_refire': log[b]['L'] + log[b]['R'],
                                   'residual_from_before_previous_escape': residual,
                                   'encoder_drive_at_refire': log[b]['drive'],
                                   'encoder_drive_positive_last_5': sum(r['drive'] > 0 for r in last5),
                                   'theta_dot_at_refire': log[b]['theta_dot'],
                                   'swatter_phase': log[b]['phase'], 'distance': log[b]['distance']})
        n = len(events)
        stale = [e for e in events if e['new_spikes_since_previous_escape_L'] + e['new_spikes_since_previous_escape_R'] == 0]
        no_recent = [e for e in events if e['spikes_in_last_5_samples'] == 0]
        out[label] = {
            'genuine_escape_decisions': decisions_total[0],
            'stale_last_action_readings_after_death': stale_total[0],
            're_escapes_at_refractory_expiry': n,
            'gap_ticks': dict(Counter(e['gap_ticks'] for e in events)),
            'paths': dict(Counter(e['paths'] or e['channel'] for e in events)),
            'with_zero_new_spikes_since_previous_escape': len(stale),
            'with_zero_spikes_in_last_5_samples': len(no_recent),
            'max_residual_from_before_previous_escape': max((e['residual_from_before_previous_escape'] for e in events), default=None),
            'min_new_spikes': min((e['new_spikes_since_previous_escape_L'] + e['new_spikes_since_previous_escape_R'] for e in events), default=None),
            'median_new_spikes': float(np.median([e['new_spikes_since_previous_escape_L'] + e['new_spikes_since_previous_escape_R'] for e in events])) if events else None,
            'with_positive_encoder_drive_last_5': sum(e['encoder_drive_positive_last_5'] > 0 for e in events),
            'swatter_phases': dict(Counter(e['swatter_phase'] for e in events)),
            'median_distance': float(np.median([e['distance'] for e in events])) if events else None,
            'events': events}
        print('%s: genuine escape decisions %d, stale post-death last_action readings %d' % (
            label, decisions_total[0], stale_total[0]), flush=True)
        print('re-escape %s: %d (gaps %s, paths %s), zero new spikes %d, zero recent spikes %d, drive>0 in last 5: %d, max residual %.4f' % (
            label, n, out[label]['gap_ticks'], out[label]['paths'], len(stale), len(no_recent),
            out[label]['with_positive_encoder_drive_last_5'], out[label]['max_residual_from_before_previous_escape'] or 0), flush=True)
    return out


# ------------------------------------------------------------------ recordings ---
def record():
    from game.replay import replay_session
    from game.session import Session
    from game.session_recording import HumanSessionRecorder
    from tools.n2_closed_loop import PARKED
    OUT.mkdir(parents=True, exist_ok=True)
    rec = HumanSessionRecorder(OUT / 'recording')
    s = Session(room(), seed=255, recorder=rec)
    try:
        for _ in range(170):                     # perch (M1.8-A accepted scenario start)
            s.tick(pointer=PARKED)
        for _ in range(120):                     # paddle moved over the perched fly
            s.tick(pointer=(s.world.fly.x, s.world.fly.y))
        for t in range(260):                     # chase at hover height, then a committed strike
            fx, fy = s.world.fly.x, s.world.fly.y
            s.tick(pointer=(fx + 20.0, fy + 10.0), strike=(t == 180))
    finally:
        s.close()
    manifest = json.loads((rec.path / 'manifest.json').read_text(encoding='utf-8'))
    rows = [json.loads(l) for l in (rec.path / 'ticks.jsonl').open(encoding='utf-8')]
    diag_keys = sorted({k for r in rows for k in r['neural']['diagnostics']})
    text = (rec.path / 'ticks.jsonl').read_text(encoding='utf-8')
    forbidden = [k for k in ('escape_trigger_paths', 'escape_trigger_channel', 'escape_lateral', 'LATERAL',
                             'escape_sample_index') if k in text]
    result = replay_session(rec.path, write_report=False)
    out = {'path': str(rec.path), 'schema': manifest['recording_schema_version'],
           'config_version': manifest['config']['config_version'],
           'decoder': manifest['config']['policy']['escape_decoder']['kind'],
           'calibration_keys': sorted(manifest['calibration']), 'recorded_diagnostics_keys': diag_keys,
           'forbidden_keys_present': forbidden, 'ticks': len(rows),
           'escapes': sum(r['action']['escape'] for r in rows),
           'lifecycle_events': json.loads((rec.path / 'summary.json').read_text(encoding='utf-8'))['lifecycle']['events'],
           'replay_exact': result['exact'], 'replay_ticks_verified': result.get('ticks_verified'),
           'numba_threads': int(os.environ['NUMBA_NUM_THREADS'])}
    (OUT / 'record.json').write_text(json.dumps(out, indent=1, default=str) + '\n', encoding='utf-8')
    print(json.dumps(out, indent=1, default=str))


def replay_existing(path, relaxed):
    from game.replay import replay_session
    path = Path(path).resolve()
    strict = None
    if relaxed:
        try:
            replay_session(path, write_report=False, strict_source=True)
            strict = 'accepted'
        except ValueError as exc:
            strict = 'rejected under strict source: ' + str(exc)[:160]
    result = replay_session(path, write_report=False, strict_source=not relaxed)
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    out = {'path': str(path), 'config_version': manifest['config'].get('config_version'),
           'decoder_in_config': (manifest['config']['policy'].get('escape_decoder') or {}).get('kind'),
           'strict_source': strict if relaxed else 'required', 'exact': result['exact'],
           'ticks_verified': result.get('ticks_verified'), 'numba_threads': int(os.environ['NUMBA_NUM_THREADS'])}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ('replay_%s.json' % path.name)).write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(out))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('replays', 'closed-loop', 'record', 'replay'))
    ap.add_argument('--path')
    ap.add_argument('--relaxed-source', action='store_true')
    args = ap.parse_args()
    if args.mode == 'replays':
        replays()
    elif args.mode == 'closed-loop':
        closed_loop()
    elif args.mode == 'record':
        record()
    else:
        replay_existing(args.path, args.relaxed_source)
