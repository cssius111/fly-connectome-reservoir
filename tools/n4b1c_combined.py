"""M1.8-N4B1C research: combined lateral (Rule A / B) + summed N2b DNp01 readout.

Research only. No production runtime, configuration, calibration record or policy
observation is changed, and DNp04 is not used.

Reproduction environment
* This tool lives on the research branch (wip/m1-4-enclosure), whose runtime has no N2b.
* The rejected N2b runtime is taken from the archival snapshot `archive/m1-8-n2b-rejected`
  (commit 2c30617), checked out as a detached worktree (default
  artifacts/worktrees/n2b-rejected, override with N2B_WORKTREE). The tool verifies the
  worktree HEAD and that it is clean, then puts it first on sys.path so `game.*` and the
  N4B1 helper tools come from the archive. The archive branch is never modified.
* Data (brain, N0/N1 re-simulations, human sessions, N4B1 fresh N0) are read from this
  repository's git-ignored artifacts and results folders.

Candidates are frozen in tools/n4b1c_candidates.py; `freeze` records its sha256, and every
other mode refuses to run if it has changed.

    python tools/n4b1c_combined.py freeze
    python tools/n4b1c_combined.py holdout --chunk 0 --trials 150     # chunks 0..3 in parallel
    python tools/n4b1c_combined.py evaluate
    python tools/n4b1c_combined.py closed-loop
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MAIN = Path(__file__).resolve().parent.parent
N2B = Path(os.environ.get('N2B_WORKTREE', MAIN / 'artifacts/worktrees/n2b-rejected')).resolve()
ARCHIVE_COMMIT = '2c306174d7bdb4e74b6c5517519ae695bd90cf44'
OUT = MAIN / 'artifacts/m1_8_n4b1c'
FROZEN = OUT / 'frozen_candidates.json'
CANDIDATES_FILE = MAIN / 'tools/n4b1c_candidates.py'
N0_COMMIT = '3d41113'
HOLDOUT_SEED_BASE = 210000          # N0 4000-4149, loom 5000-5149, N1 6000-10059, N4B1 30000-60149
HOLDOUT_OFFSET_SEED_ADD = 616161    # N0 used encoder_seed, N4B1 encoder_seed + 424242 + chunk
DT = 0.02
STRIKE_PHASES = ('windup', 'active', 'commit', 'fast_swing', 'active_contact')


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_worktree():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=N2B, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=N2B, text=True).strip()
    if head != ARCHIVE_COMMIT or dirty:
        raise SystemExit('N2b worktree %s must be clean at %s (HEAD %s, dirty %r)'
                         % (N2B, ARCHIVE_COMMIT, head, dirty[:200]))
    return head


if __name__ == '__main__':
    _mode = sys.argv[1] if len(sys.argv) > 1 else ''
    os.environ.setdefault('NUMBA_NUM_THREADS', '2' if _mode == 'holdout' else '4')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    verify_worktree()
    sys.path.insert(0, str(N2B))

import numpy as np  # noqa: E402


def load_candidates():
    spec = importlib.util.spec_from_file_location('n4b1c_candidates', CANDIDATES_FILE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_frozen():
    if not FROZEN.exists():
        raise SystemExit('run `freeze` first')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if sha256(CANDIDATES_FILE) != frozen['candidates_module_sha256']:
        raise SystemExit('tools/n4b1c_candidates.py changed after the freeze')
    return frozen


def archive_modules():
    """N4B1 helpers from the archive worktree, pointed at this repository's data."""
    from tools import n4b1_lateral as L
    from tools import n4b1_analysis as A
    assert Path(L.__file__).resolve().is_relative_to(N2B), L.__file__
    A.ROOT = MAIN
    A.N4 = MAIN / 'artifacts/m1_8_n4'
    A.N1_DIR = MAIN / 'artifacts/m1_8_loom_robustness'
    A.SESSIONS = {'strict_n2': MAIN / 'results/game/sessions/20260923T005351.731330Z-38255ec8',
                  'n2b': MAIN / 'results/game/sessions/20260924T000111.561327Z-c337a721'}
    L.OUT = MAIN / 'artifacts/m1_8_n4b1'           # N4B1 fresh N0 chunks (development data)
    return L, A


# ------------------------------------------------------------------ freeze ---
def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    if FROZEN.exists():
        print('already frozen', sha256(FROZEN))
        return
    cand = load_candidates()
    body = {'label': 'M1.8-N4B1C frozen candidates (combined lateral + summed DNp01)',
            'frozen_before_holdout': True,
            'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'candidates': cand.specs(),
            'candidates_module': 'tools/n4b1c_candidates.py',
            'candidates_module_sha256': sha256(CANDIDATES_FILE),
            'n2b_archive_commit': ARCHIVE_COMMIT,
            'n2b_room_config_sha256': sha256(N2B / 'game_room_config.json'),
            'holdout_protocol': {'config_commit': N0_COMMIT, 'seed_base': HOLDOUT_SEED_BASE,
                                 'seeds': 'seed_base + chunk * 10000 + i, chunks 0-3, i < 150',
                                 'offset_rng': 'default_rng(encoder_seed + %d + chunk)'
                                               % HOLDOUT_OFFSET_SEED_ADD,
                                 'offset_radius': [30.0, 170.0], 'ticks_per_trial': 1400,
                                 'protocol': 'tools/calibrate_escape._trial, fixed fly, no loom'},
            'development_data_already_inspected': ['original N0 70 min (4000-4149)',
                                                   'N4B1 fresh N0 280 min (30000-60149)',
                                                   'N1 300 trials', 'both human sessions']}
    FROZEN.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
    print('frozen', FROZEN, sha256(FROZEN))


# ------------------------------------------------------------------ holdout ---
def holdout(chunk, trials):
    frozen = check_frozen()
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    config = json.loads(subprocess.check_output(['git', 'show', N0_COMMIT + ':game_room_config.json'],
                                                cwd=MAIN, text=True))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=MAIN)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + HOLDOUT_OFFSET_SEED_ADD + chunk)
    left, right, seeds = [], [], []
    started = time.perf_counter()
    for i in range(trials):
        seed = HOLDOUT_SEED_BASE + chunk * 10000 + i
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        t = _trial(session, policy, seed, (np.cos(angle) * radius, np.sin(angle) * radius), 1400, None)
        left.append(t['left'])
        right.append(t['right'])
        seeds.append(seed)
        if (i + 1) % 10 == 0:
            print('  chunk %d: %d/%d  %.0fs' % (chunk, i + 1, trials, time.perf_counter() - started),
                  flush=True)
    session.close()
    np.savez_compressed(OUT / ('holdout_chunk%d.npz' % chunk), left=np.stack(left), right=np.stack(right),
                        seeds=np.array(seeds))
    (OUT / ('holdout_chunk%d.json' % chunk)).write_text(json.dumps({
        'chunk': chunk, 'trials': trials, 'seeds': [seeds[0], seeds[-1]],
        'frozen_candidates_sha256': sha256(FROZEN),
        'candidates_module_sha256': frozen['candidates_module_sha256'],
        'numba_threads': int(os.environ['NUMBA_NUM_THREADS']), 'config_commit': N0_COMMIT,
        'wall_seconds': time.perf_counter() - started}) + '\n', encoding='utf-8')
    print('chunk %d written' % chunk)


# ------------------------------------------------------------------ evaluation helpers ---
def path_kind(channel):
    """Trigger path of a firing channel string."""
    if channel is None:
        return None
    parts = channel.split('+')
    kinds = []
    for p in parts:
        if p.startswith('LATERAL'):
            kinds.append('lateral')
        elif p in ('FAST', 'SUSTAINED'):
            kinds.append('N2b ' + p)
        else:
            kinds.append(p)
    return '+'.join(kinds)


def replay(policy, left, right, A):
    policy.reset()
    out = []
    for t in range(left.size):
        a = policy.decide(A.motor(left[t], right[t]))
        if a.escape:
            ch = policy.criterion_diagnostics()['escape_trigger_channel'] \
                if hasattr(policy, 'criterion_diagnostics') else 'SINGLE_SAMPLE'
            trig = getattr(policy, 'last_trigger', None)
            out.append({'tick': t, 'channel': ch, 'pair': None if trig is None else trig.get('pair')})
    return out


def poisson_upper(k, minutes):
    from scipy.stats import chi2
    return float(chi2.ppf(0.95, 2 * k + 2) / 2 / minutes)


def n0_eval(factory, trials, A):
    events, paths, sides, back_to_back = 0, Counter(), Counter(), 0
    for lt, rt in trials:
        f = replay(factory(), lt, rt, A)
        events += len(f)
        for x in f:
            paths[path_kind(x['channel'])] += 1
            for s in 'LR':
                if x['channel'] and ('LATERAL_' in x['channel']) and s in x['channel'].split('+')[0][8:]:
                    sides[s] += 1
        back_to_back += sum(1 for a, b in zip(f, f[1:]) if b['tick'] - a['tick'] <= 21)
    minutes = sum(lt.size for lt, _ in trials) * DT / 60
    return {'minutes': minutes, 'false_events': events, 'per_minute': events / minutes,
            'upper95_per_minute': poisson_upper(events, minutes), 'paths': dict(paths),
            'lateral_sides': dict(sides), 'refire_at_refractory_expiry': back_to_back}


def n1_eval(factory, trials, A):
    per, first_paths = {}, {}
    for t in trials:
        f = replay(factory(), t['left'], t['right'], A)
        inside = [x for x in f if t['window'][x['tick']]]
        c = per.setdefault(t['kind'], {'trials': 0, 'fired': 0, 'lat': []})
        c['trials'] += 1
        if inside:
            c['fired'] += 1
            if t['click'] is not None:
                c['lat'].append((inside[0]['tick'] - t['click']) * DT)
            first_paths.setdefault(t['kind'], Counter())[path_kind(inside[0]['channel'])] += 1
    out = {}
    for k, c in per.items():
        out[k] = {'trials': c['trials'], 'fired': c['fired'],
                  'median_s': float(np.median(c['lat'])) if c['lat'] else None,
                  'p95_s': float(np.percentile(c['lat'], 95)) if c['lat'] else None,
                  'first_path': dict(first_paths.get(k, {}))}
    return out


def load_sessions(A):
    sessions = {}
    for k, path in A.SESSIONS.items():
        eps, manifest, strikes = A.load_session(path)
        snaps, mism = A.reproduce(eps, manifest)
        sessions[k] = {'eps': eps, 'snaps': snaps, 'strikes': strikes, 'segs_cache': {},
                       'reproduction_mismatches': mism}
    return sessions


def hover_table(sessions, segs_by_name):
    """Per recorded hover escape: each candidate's first firing in the synced segment."""
    out = {}
    for sk, sess in sessions.items():
        rows_out = []
        names = list(segs_by_name)
        ref = segs_by_name[names[0]][sk]
        for j, seg in enumerate(ref):
            e = seg['recorded_escape']
            if e is None:
                continue
            rows = sess['eps'][seg['episode']]
            if rows[e]['swatter']['phase'] in STRIKE_PHASES:
                continue
            row = {'episode': seg['episode'], 'recorded_escape_row': e, 'segment_start': seg['start']}
            for n in names:
                f = segs_by_name[n][sk][j]['fire']
                row[n] = None if f is None else {'row': f['row'], 'lead_ticks': e - f['row'],
                                                 'path': path_kind(f['channel']),
                                                 'spike_rows': f.get('spike_rows')}
            rows_out.append(row)
        out[sk] = rows_out
    return out


def evaluate():
    frozen = check_frozen()
    L, A = archive_modules()
    cand = load_candidates()
    factories = cand.factories()
    orig, fresh, _ = A.n0_sets()
    hold = []
    hold_meta = []
    for c in range(4):
        p = OUT / ('holdout_chunk%d.npz' % c)
        if p.exists():
            z = np.load(p)
            hold += list(zip(z['left'], z['right']))
            hold_meta.append(json.loads((OUT / ('holdout_chunk%d.json' % c)).read_text(encoding='utf-8')))
    print('N0: original %d, N4B1 fresh (development) %d, NEW holdout %d trials' % (len(orig), len(fresh), len(hold)),
          flush=True)
    n1 = A.n1_sets()
    sessions = load_sessions(A)
    print('human reproduction mismatches', {k: s['reproduction_mismatches'] for k, s in sessions.items()}, flush=True)

    # Harness check: the combined class with the lateral path disabled must equal N2b.
    comb = cand.combined_class()
    ref = factories['N2b: FAST 2.10 OR current-H + 3-of-5']
    check_trials = [(t['left'], t['right']) for t in n1] + orig[:40]
    off = lambda: comb({'key': 'lateral_off', 'max_gap': -1, 'combined': True})
    harness = all([x['tick'] for x in replay(off(), lt, rt, A)] == [x['tick'] for x in replay(ref(), lt, rt, A)]
                  for lt, rt in check_trials)
    print('harness: combined with lateral path disabled == N2b:', harness, flush=True)

    result = {'label': 'M1.8-N4B1C combined lateral + summed DNp01; research only',
              'frozen_sha256': sha256(FROZEN), 'frozen': frozen, 'holdout_chunks': hold_meta,
              'harness_combined_lateral_off_equals_n2b': harness,
              'human_reproduction_mismatches': {k: s['reproduction_mismatches'] for k, s in sessions.items()},
              'candidates': {}}
    segs_by_name = {}
    for name, factory in factories.items():
        row = {'n0_original_dev': n0_eval(factory, orig, A), 'n0_n4b1_fresh_dev': n0_eval(factory, fresh, A),
               'n0_holdout': n0_eval(factory, hold, A) if hold else None}
        dev_k = row['n0_original_dev']['false_events'] + row['n0_n4b1_fresh_dev']['false_events']
        dev_m = row['n0_original_dev']['minutes'] + row['n0_n4b1_fresh_dev']['minutes']
        row['n0_development_combined'] = {'minutes': dev_m, 'false_events': dev_k,
                                          'upper95_per_minute': poisson_upper(dev_k, dev_m)}
        if hold:
            k = dev_k + row['n0_holdout']['false_events']
            m = dev_m + row['n0_holdout']['minutes']
            row['n0_all'] = {'minutes': m, 'false_events': k, 'upper95_per_minute': poisson_upper(k, m)}
        row['n1'] = n1_eval(factory, n1, A)
        hum = {}
        segs_by_name[name] = {}
        for sk, sess in sessions.items():
            segs = A.human_eval(factory, sess)
            sess['segs_cache'][id(factory)] = segs
            segs_by_name[name][sk] = segs
            h = A.summarise_human(segs, sess, name)
            h['trigger_paths'] = dict(Counter(path_kind(s['fire']['channel']) for s in segs if s['fire']))
            hum[sk] = h
        row['human'] = hum
        row['cases'] = A.special_cases(factory, sessions)
        result['candidates'][name] = row
        s, m = row['n1']['strong_direct'], row['n1']['medium_committed']
        ho = row['n0_holdout']
        print('%-44s dev N0 %d+%d | HOLDOUT %s/%.0fmin up95 %s %s | S %d %.2f/%.2f M %d %.2f/%.2f | w %d g %d a %d'
              ' | strict hover %d/%d n2b hover %d/%d | far %s vol %s slow %s chase589 %s' % (
                  name[:44], row['n0_original_dev']['false_events'], row['n0_n4b1_fresh_dev']['false_events'],
                  None if ho is None else ho['false_events'], 0 if ho is None else ho['minutes'],
                  None if ho is None else round(ho['upper95_per_minute'], 4), None if ho is None else ho['paths'],
                  s['fired'], s['median_s'], s['p95_s'], m['fired'], m['median_s'], m['p95_s'],
                  row['n1']['weak_approach']['fired'], row['n1']['glancing_pass']['fired'],
                  row['n1']['aborted_approach']['fired'],
                  hum['strict_n2']['hover']['fired_no_later'], hum['strict_n2']['hover']['n'],
                  hum['n2b']['hover']['fired_no_later'], hum['n2b']['hover']['n'],
                  row['cases']['far_perched']['fires_in_bout_2434_2528'],
                  row['cases']['voluntary_takeoff']['fires_within_1s_before_to_0_5s_after'],
                  row['cases']['slow_close_synced']['fire_tick'], row['cases']['chase_before_589']['fire_tick']),
              flush=True)
    result['hover_escapes'] = hover_table(sessions, segs_by_name)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'evaluation.json').write_text(json.dumps(result, indent=1, default=str) + '\n', encoding='utf-8')
    print('written', OUT / 'evaluation.json')


# ------------------------------------------------------------------ closed loop ---
def closed_loop():
    check_frozen()
    L, A = archive_modules()
    cand = load_candidates()
    import tools.n2_closed_loop as C
    from game.session import Session, load_config
    assert Path(C.__file__).resolve().is_relative_to(N2B)
    config = load_config(N2B / 'game_room_config.json')
    all_f = cand.factories()
    factories = {'A': all_f['Rule A alone: same side twice within 60 ms'],
                 'N2b': all_f['N2b: FAST 2.10 OR current-H + 3-of-5'],
                 'A_or_N2b': all_f['A OR N2b'],
                 'B_or_N2b': all_f['B OR N2b']}
    summary_orig = C.Run.summary

    def summary_with_escapes(self):
        out = summary_orig(self)
        out['escape_list'] = [{'tick': e['tick'], 'channel': e['channel'], 'encoder_drive': e['encoder_drive'],
                               'theta_dot': e['theta_dot'], 'lifecycle_mode': e['lifecycle_mode']}
                              for e in self.escapes]
        return out
    C.Run.summary = summary_with_escapes
    probe = Session(config, policy=factories['N2b'](), seed=1, mode='evaluation')
    brain = probe.brain
    probe.close()
    results, started = {}, time.perf_counter()

    def run(name, fn, *a):
        row = {label: fn(config, make(), *a[:1], brain, *a[1:]) for label, make in factories.items()}
        results.setdefault(name, []).append(row)
        print('%-30s %s  %.0fs' % (name, ' | '.join('%s pre %d post %s %s' % (
            k, r['escapes_before_click'], r['first_escape_latency_from_click_s'],
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
                p = paths.setdefault(scen, {}).setdefault(label, {'paths': Counter(), 'refire_at_expiry': 0,
                                                                   'zero_drive_escapes': 0})
                es = r['escape_list']
                for e in es:
                    p['paths'][path_kind(e['channel'])] += 1
                    p['zero_drive_escapes'] += e['encoder_drive'] == 0.0
                p['refire_at_expiry'] += sum(1 for a, b in zip(es, es[1:]) if b['tick'] - a['tick'] <= 21)
    report = {'label': 'M1.8-N4B1C research-only closed-loop ROOM runs (archived N2b runtime; tools/ policies)',
              'summary': {k: C.aggregate(v) for k, v in results.items()},
              'paths': {s: {l: {'paths': dict(v['paths']), 'refire_at_refractory_expiry': v['refire_at_expiry'],
                                'escapes_with_zero_encoder_drive': v['zero_drive_escapes']}
                            for l, v in d.items()} for s, d in paths.items()},
              'scenarios': results, 'wall_seconds': time.perf_counter() - started}
    (OUT / 'closed_loop.json').write_text(json.dumps(report, indent=1, default=float) + '\n', encoding='utf-8')
    print('written', OUT / 'closed_loop.json')


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('freeze', 'holdout', 'evaluate', 'closed-loop'))
    ap.add_argument('--chunk', type=int, default=0)
    ap.add_argument('--trials', type=int, default=150)
    args = ap.parse_args()
    if args.mode == 'freeze':
        freeze()
    elif args.mode == 'holdout':
        holdout(args.chunk, args.trials)
    elif args.mode == 'evaluate':
        evaluate()
    else:
        closed_loop()
