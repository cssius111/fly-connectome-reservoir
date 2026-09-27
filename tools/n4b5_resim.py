"""M1.8-N4B5 research: re-simulation under candidate paddle apparent-size formulas.

Research only. No file of the runtime is changed. Inside a research process only,
`World.visual_half_size` (read solely by `RetinaProjector.project`) is replaced by one of the
frozen candidates in tools/n4b5_geometry.py. The Retina therefore changes, and nothing else
does. With G0 every mode must reproduce its original record exactly, and this is checked.

The N4B1C decoder is the frozen runtime (e3c55b3), replayed with its own FixedEscapePolicy
(tools/n4b2_analysis.n4b1c_events) or run live in the ROOM mode.

    # Human sessions, open loop: Retina recomputed from the recorded world states.
    python tools/n4b5_resim.py human --cand G3_elevation_aware                   (both sessions; 8 Numba threads)
    # N1 (300 scripted fixed-fly trials, config 76806f0, 4 threads).
    python tools/n4b5_resim.py n1 --cand G3_elevation_aware
    # No-player ROOM closed loop under the live runtime (thread count of the source run).
    python tools/n4b5_resim.py room --cand G3_elevation_aware --source n4b3_holdout --seed 7401 [--suppress TICK]
    # Original fixed-fly N0 arm (150 trials, 4 threads).
    python tools/n4b5_resim.py n0 --cand G3_elevation_aware
    # Everything for the given candidates, in parallel lanes.
    python tools/n4b5_resim.py all --cands G0_current,G1_isotropic,G3_elevation_aware --lanes 8
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

MAIN = Path(__file__).resolve().parent.parent
OUT = MAIN / 'artifacts/m1_8_n4b5'
FROZEN = OUT / 'frozen_geometry.json'
SESSIONS = {'strict_n2': '20260923T005351.731330Z-38255ec8', 'n2b': '20260924T000111.561327Z-c337a721'}
N1_COMMIT = '76806f0'
PARKED = (1920.0, 388.8)


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('human', 'n1', 'n0', 'room', 'all'))
    p.add_argument('--cand')
    p.add_argument('--cands')
    p.add_argument('--source')
    p.add_argument('--seed', type=int)
    p.add_argument('--suppress', type=int)
    p.add_argument('--noise-offset', type=int, default=0)
    p.add_argument('--lanes', type=int, default=8)
    p.add_argument('--room-cands', default='G1_isotropic,G3_elevation_aware')
    return p.parse_args()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_frozen():
    f = json.loads(FROZEN.read_text(encoding='utf-8'))
    if sha256(MAIN / 'tools/n4b5_geometry.py') != f['geometry_module_sha256']:
        raise SystemExit('tools/n4b5_geometry.py changed after the freeze')
    return f


def patch_world(world_cls, cand):
    """Replace World.visual_half_size in this process only."""
    from tools import n4b5_geometry as G

    def visual_half_size(self):
        sw, fly = self.swatter, self.fly
        a = self.directional['tilt_anisotropy'] if self.directional else 0.0
        if not self.directional and cand != 'G1_isotropic':
            raise RuntimeError('candidate needs the directional configuration')
        return G.half_size(cand, fly.x, fly.y, sw.x, sw.y, sw.height, sw.face, sw.orientation,
                           r=self.paddle_radius, e=self.edge_on_factor, a=a)
    world_cls.visual_half_size = property(visual_half_size)


# ------------------------------------------------------------------ human ---
def run_human(cand, noise_offset=0):
    import numpy as np
    from tools import n4b5_geometry as G
    from game.fly import build_brain
    from game.perception import Retina, RetinalEncoder
    out = {}
    for sess, name in SESSIONS.items():
        path = MAIN / 'results/game/sessions' / name
        manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        if int(os.environ['NUMBA_NUM_THREADS']) != int(manifest['runtime']['numba_threads']):
            raise SystemExit('run with NUMBA_NUM_THREADS=%d' % manifest['runtime']['numba_threads'])
        config = manifest['config']
        sw_cfg = config['swatter']
        brain = build_brain(config, MAIN)
        encoder = RetinalEncoder(brain, config)
        dt = float(config['sim']['tick_seconds'])
        l_idx, r_idx = int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0])
        seeds = {json.loads(line)['episode']: json.loads(line)['seed'] for line in (path / 'episodes.jsonl').open(encoding='utf-8')}
        rows = [json.loads(line) for line in (path / 'ticks.jsonl').open(encoding='utf-8')]
        eps = {}
        for r in rows:
            eps.setdefault(r['episode'], []).append(r)
        decay = np.float32(np.exp(-dt / float(config['brain']['trace_tau_seconds'])))
        sess_out = {}
        exact_rows = total_rows = 0
        for ep, er in eps.items():
            # noise_offset != 0 draws a different brain-noise realization with the same input
            # (a variability control; the recorded run used offset 0).
            brain.reset(int(seeds[ep]) + 977 + noise_offset)

            def cand_theta(k):
                f, s = er[k]['fly'], er[k]['swatter']
                return G.theta(cand, f['x'], f['y'], s['x'], s['y'], s['height'], s['face'], s['orientation'],
                               r=sw_cfg['paddle_radius'], e=sw_cfg['edge_on_factor'],
                               a=sw_cfg['directional']['tilt_anisotropy'])
            thetas, theta_dots = [], []
            for i, r in enumerate(er):
                if i == 0:
                    # Row 0's Retina comes from the unrecorded post-reset state; scale the recorded
                    # value by the candidate / G0 ratio at the first recorded state.
                    th = r['retina']['theta'] * cand_theta(0) / G.theta(
                        'G0_current', er[0]['fly']['x'], er[0]['fly']['y'], er[0]['swatter']['x'], er[0]['swatter']['y'],
                        er[0]['swatter']['height'], er[0]['swatter']['face'], er[0]['swatter']['orientation'])
                    if cand == 'G0_current':
                        th = r['retina']['theta']
                    td = 0.0
                else:
                    th = cand_theta(i - 1)
                    td = (th - thetas[-1]) / dt
                thetas.append(th)
                theta_dots.append(td)
            tl = tr = np.float32(0.0)
            lefts, rights, stepped_ticks = [], [], []
            for i, r in enumerate(er):
                if not r['neural']['brain_stepped']:
                    continue
                inject = encoder.inject(Retina(thetas[i], theta_dots[i], r['retina']['azimuth']))
                fired = np.asarray(brain.step(inject=inject))
                tl = np.float32(tl * decay)
                tr = np.float32(tr * decay)
                if np.any(fired == l_idx):
                    tl = np.float32(tl + np.float32(1.0))
                if np.any(fired == r_idx):
                    tr = np.float32(tr + np.float32(1.0))
                lefts.append(float(tl))
                rights.append(float(tr))
                stepped_ticks.append(r['tick'])
                total_rows += 1
                exact_rows += (float(tl) == r['neural']['dnp01_left'] and float(tr) == r['neural']['dnp01_right'])
            sess_out[str(ep)] = {'ticks': stepped_ticks, 'left': lefts, 'right': rights,
                                 'theta': [thetas[i] for i, r in enumerate(er) if r['neural']['brain_stepped']],
                                 'theta_dot': [theta_dots[i] for i, r in enumerate(er) if r['neural']['brain_stepped']]}
        out[sess] = {'episodes': sess_out, 'dnp01_rows_equal_to_recorded': exact_rows, 'stepped_rows': total_rows}
        print('%s noise%d %s: DNp01 equal to recorded on %d / %d stepped rows' % (cand, noise_offset, sess, exact_rows, total_rows), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    suffix = '' if noise_offset == 0 else '_noise%d' % noise_offset
    (OUT / ('human_%s%s.json' % (cand, suffix))).write_text(json.dumps(out) + '\n', encoding='utf-8')


# ------------------------------------------------------------------ N1 ---
def run_n1(cand):
    import numpy as np
    from game.session import Session
    from game.world import World
    from tools.calibrate_escape import RecordingPolicy
    from tools.loom_robustness_study import run_trial, DT
    patch_world(World, cand)
    config = json.loads(subprocess.check_output(['git', 'show', N1_COMMIT + ':game_room_config.json'], cwd=MAIN, text=True))
    data = np.load(MAIN / 'artifacts/m1_8_loom_robustness/trials.npz')
    settle = max(40, round(config['swatter'].get('physical', {}).get('calibration_settle_seconds', 0.8) / DT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=MAIN)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + 991)
    classes = ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass', 'aborted_approach')
    trials, idx, equal = [], 0, 0
    started = time.perf_counter()
    for ci, kind in enumerate(classes):
        for i in range(60):
            base = len(policy.history)
            t = run_trial(session, policy, 6000 + ci * 1000 + i, kind, rng, settle)
            hist = policy.history[-t['ticks']:]
            left = [m.dnp01_left for m in hist]
            right = [m.dnp01_right for m in hist]
            eq = bool(np.array_equal(t['dnp01'], data['%d_dnp01' % idx]))
            equal += eq
            trials.append({'index': idx, 'kind': kind, 'click_tick': t['click_tick'], 'left': left, 'right': right,
                           'theta': t['theta'].tolist(), 'theta_dot': t['theta_dot'].tolist(),
                           'committed': t['committed'].tolist(), 'equal_to_recorded_g0': eq})
            idx += 1
        print('  %s %s done (%d equal to recorded)  %.0fs' % (cand, kind, equal, time.perf_counter() - started), flush=True)
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ('n1_%s.json' % cand)).write_text(json.dumps({'cand': cand, 'trials': trials, 'equal_to_recorded': equal,
                                                        'numba_threads': int(os.environ['NUMBA_NUM_THREADS'])}) + '\n',
                                             encoding='utf-8')
    print('%s N1 written: %d / 300 identical to the recorded G0 run' % (cand, equal))


# ------------------------------------------------------------------ N0 ---
def run_n0(cand):
    """Original fixed-fly N0 arm (150 x 1400 ticks, seeds 4000-4149, config 3d41113, 4 threads).
    Encoder drive is zero inside every recorded window whatever the candidate, but the paddle's
    move to its hover position during the settle phase can differ, so the brain state at the
    window start is not guaranteed identical; events are compared statistically."""
    import numpy as np
    from game.session import Session
    from game.world import World
    from tools.calibrate_escape import RecordingPolicy, _trial
    patch_world(World, cand)
    config = json.loads(subprocess.check_output(['git', 'show', '3d41113:game_room_config.json'], cwd=MAIN, text=True))
    raw = np.load(MAIN / 'artifacts/m1_8_no_loom_calibration/raw.npz')['null']
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=MAIN)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']))
    trials, equal, max_drive = [], 0, 0.0
    for i in range(150):
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        t = _trial(session, policy, 4000 + i, (np.cos(angle) * radius, np.sin(angle) * radius), 1400, None)
        equal += bool(np.array_equal(t['total'], raw[i * 1400:(i + 1) * 1400]))
        d = session.encoder.last_drive or {}
        max_drive = max(max_drive, max(d.values()) if d else 0.0)
        trials.append({'seed': 4000 + i, 'left': t['left'].tolist(), 'right': t['right'].tolist()})
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / ('n0_%s.json' % cand)).write_text(json.dumps({'cand': cand, 'trials': trials, 'equal_to_recorded': equal,
                                                        'last_tick_max_drive': max_drive}) + '\n', encoding='utf-8')
    print('%s N0 written: %d / 150 identical to the recorded G0 arm' % (cand, equal))


# ------------------------------------------------------------------ ROOM ---
def run_room(cand, source, seed, suppress=None):
    from tools import n4b2_record as R
    from tools import n4b4_replay as P
    rec = P.load_record(source, seed)
    if int(os.environ['NUMBA_NUM_THREADS']) != rec['threads']:
        raise SystemExit('run with NUMBA_NUM_THREADS=%d' % rec['threads'])
    R.verify_runtime_worktree()
    sys.path.insert(0, str(R.RUNTIME_WORKTREE))
    import numpy as np
    from game.session import Session, build_policy, load_config
    from game.world import World
    patch_world(World, cand)
    config = load_config(R.RUNTIME_WORKTREE / 'game_room_config.json')
    policy, _ = build_policy(config, root=R.RUNTIME_WORKTREE)
    ref = {'tick': 0}
    active = P.Suppress(policy, ref, suppress, P.SUPPRESS_TICKS) if suppress is not None else policy
    session = Session(config, policy=active, seed=seed, mode='evaluation', root=R.RUNTIME_WORKTREE)
    drec = R.DNRecorder(session.brain, session.encoder)
    until = rec['ticks'] if suppress is None else min(rec['ticks'], suppress + P.HORIZON_TICKS)
    rows = []
    for t in range(until):
        ref['tick'] = t
        n_before = len(drec.spikes)
        session.tick(pointer=PARKED, strike=False)
        stepped = len(drec.spikes) > n_before
        motor = session.fly_loop.last_motor
        action = session.fly_loop.last_action if stepped else None
        fly, sw, lc = session.world.fly, session.world.swatter, session.world.lifecycle
        r = session.last_retina
        rows.append({'tick': t, 'stepped': stepped, 'theta': float(r.theta), 'theta_dot': float(r.theta_dot),
                     'azimuth': float(r.azimuth),
                     'dnp01_left': None if motor is None else float(motor.dnp01_left),
                     'dnp01_right': None if motor is None else float(motor.dnp01_right),
                     'policy_escape': bool(stepped and policy.criterion_diagnostics()['escape_trigger_channel'] != 'NONE'
                                           and policy.refractory_remaining == policy.refractory_ticks),
                     'world_escape': bool(action is not None and action.escape),
                     'paths': policy.criterion_diagnostics()['escape_trigger_paths'],
                     'behavior_state': policy.diagnostics().get('behavior_state'),
                     'lifecycle_mode': None if lc is None else str(lc.mode),
                     'saccade_kind': str(session.world.saccades.kind),
                     'motion': None if motor is None else [motor.motion.forward_speed, motor.motion.lateral_speed,
                                                          motor.motion.yaw_rate, motor.motion.saccade_remaining],
                     'fly': [fly.x, fly.y, fly.vx, fly.vy, fly.heading],
                     'paddle': [sw.x, sw.y, sw.height, sw.vx, sw.vy, sw.face, sw.orientation],
                     'visual_half_size': float(session.world.visual_half_size),
                     'lethal': bool(session.world.lethal), 'hits': int(session.stats.hits)})
    session.close()
    sp, se, dr = drec.window(0, len(drec.spikes))
    stepped_idx = [i for i, row in enumerate(rows) if row['stepped']]
    esc = [row['tick'] for row in rows if row['policy_escape']]
    check = None
    if cand == 'G0_current' and suppress is None:
        check = {'escape_ticks_equal_to_recorded': esc == rec['escape_ticks']}
    name = 'room_%s_%s_seed%d%s' % (cand, source, seed, '' if suppress is None else '_cf%d' % suppress)
    np.savez_compressed(OUT / (name + '.npz'), spikes=sp, sensory=se, drive=dr, stepped_ticks=np.array(stepped_idx))
    meta = {'cand': cand, 'source': source, 'seed': seed, 'suppress_event_tick': suppress, 'threads': rec['threads'],
            'escape_ticks': esc, 'check': check, 'suppressed_escape_ticks': None if suppress is None else active.suppressed,
            'rows': rows}
    meta.update(drec.panel_meta())
    (OUT / (name + '.json')).write_text(json.dumps(meta) + '\n', encoding='utf-8')
    print('%s: %d escapes %s' % (name, len(esc), esc))


# ------------------------------------------------------------------ all ---
def run_all(cands, room_cands, lanes):
    from tools import n4b4_replay as P
    inv = json.loads((MAIN / 'artifacts/m1_8_n4b4/inventory.json').read_text(encoding='utf-8'))
    jobs = []
    for c in cands:
        if not (OUT / ('human_%s.json' % c)).exists():
            jobs.append((['human', '--cand', c], 8))
        if not (OUT / ('n1_%s.json' % c)).exists():
            jobs.append((['n1', '--cand', c], 4))
    for c in room_cands:
        for r in inv['runs']:
            if not (OUT / ('room_%s_%s_seed%d.json' % (c, r['source'], r['seed']))).exists():
                jobs.append((['room', '--cand', c, '--source', r['source'], '--seed', str(r['seed'])], r['threads']))
    print('%d jobs' % len(jobs), flush=True)
    procs = []
    while jobs or procs:
        while jobs and len(procs) < lanes:
            args, th = jobs.pop(0)
            env = dict(os.environ, NUMBA_NUM_THREADS=str(th), SDL_VIDEODRIVER='dummy')
            log = open(OUT / ('log_%s.txt' % '_'.join(a.replace('--', '') for a in args)), 'w')
            procs.append((subprocess.Popen([sys.executable, __file__] + args, env=env, stdout=log,
                                           stderr=subprocess.STDOUT), log, args))
        time.sleep(2)
        for p in list(procs):
            if p[0].poll() is not None:
                p[1].close()
                procs.remove(p)
                print('done rc=%s %s' % (p[0].returncode, ' '.join(p[2])), flush=True)


if __name__ == '__main__':
    ARGS = _args()
    sys.path.insert(0, str(MAIN))
    check_frozen()
    if ARGS.mode == 'all':
        run_all(ARGS.cands.split(','), ARGS.room_cands.split(',') if ARGS.room_cands else [], ARGS.lanes)
    else:
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        if ARGS.mode == 'human':
            run_human(ARGS.cand, ARGS.noise_offset)
        elif ARGS.mode == 'n1':
            run_n1(ARGS.cand)
        elif ARGS.mode == 'n0':
            run_n0(ARGS.cand)
        else:
            run_room(ARGS.cand, ARGS.source, ARGS.seed, ARGS.suppress)
