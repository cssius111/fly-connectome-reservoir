"""M1.8-N4B3 research: DN-panel recordings with internal motion state.

Research only. No runtime file, configuration, calibration record, brain parameter,
encoder parameter, noise setting or policy observation is changed. The brain's `step` runs
unchanged; the N4B2 DNRecorder wrapper (tools/n4b2_record.py) reads the DN panel spikes,
sensory counts and encoder drive after each step.

Compared with N4B2, ROOM rows also store the whitelisted MotionState the policy observed
(forward_speed, lateral_speed, yaw_rate, saccade_remaining), and offline-only geometry
(fly velocity, paddle position, height and velocity) for interpreting whether expansion is
self-generated. Nothing recorded here reaches a policy.

    # ROOM no-player free flight under the accepted N4B1C runtime (detached worktree).
    python tools/n4b3_record.py room --set dev --seed 7301          # development, before the freeze
    python tools/n4b3_record.py room --set holdout --seed 7401      # refuses to run before the freeze

    # Fixed-fly no-loom holdout (refuses to run before the freeze).
    python tools/n4b3_record.py n0 --chunk 0                        # chunks 0..3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

MAIN = Path(__file__).resolve().parent.parent
OUT = MAIN / 'artifacts/m1_8_n4b3'
FROZEN = OUT / 'frozen_criteria.json'
CRITERIA_FILE = MAIN / 'tools/n4b3_criteria.py'
N0_COMMIT = '3d41113'
# Non-overlapping with every earlier N0 set (4000-4149, 5000-5149, 6000-10059,
# 30000-60149, 210000-240149, 310000-340149).
N0_SEED_BASE = 410000
N0_OFFSET_ADD = 818181
ROOM_SETS = {'dev': range(7301, 7400), 'holdout': range(7401, 7600)}
PARKED = (1920.0, 388.8)


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('room', 'n0'))
    p.add_argument('--set', choices=tuple(ROOM_SETS))
    p.add_argument('--seed', type=int)
    p.add_argument('--ticks', type=int, default=9000)
    p.add_argument('--chunk', type=int, default=0)
    p.add_argument('--trials', type=int, default=150)
    return p.parse_args()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


ARGS = _args() if __name__ == '__main__' else None
sys.path.insert(0, str(MAIN))
from tools import n4b2_record as R  # noqa: E402  (panel, recorder, runtime worktree check)

if ARGS is not None:
    os.environ.setdefault('NUMBA_NUM_THREADS', '2')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    if ARGS.mode == 'room':
        R.verify_runtime_worktree()
        sys.path.insert(0, str(R.RUNTIME_WORKTREE))

import numpy as np  # noqa: E402


def check_frozen():
    if not FROZEN.exists():
        raise SystemExit('freeze the N4B3 criteria first (tools/n4b3_analysis.py freeze)')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if sha256(CRITERIA_FILE) != frozen['criteria_module_sha256']:
        raise SystemExit('tools/n4b3_criteria.py changed after the freeze')
    return frozen


def run_room(which, seed, ticks):
    if seed not in ROOM_SETS[which]:
        raise SystemExit('seed %d is not in the %s range' % (seed, which))
    frozen = check_frozen() if which == 'holdout' else None
    if which == 'dev' and FROZEN.exists():
        raise SystemExit('development ROOM data must be generated before the freeze')
    out = OUT / ('room_%s_seed%d.npz' % (which, seed))
    if out.exists():
        raise SystemExit('%s exists' % out)
    from game.session import Session, build_policy, load_config
    config = load_config(R.RUNTIME_WORKTREE / 'game_room_config.json')
    policy, source = build_policy(config, root=R.RUNTIME_WORKTREE)
    session = Session(config, policy=policy, seed=seed, mode='evaluation', root=R.RUNTIME_WORKTREE)
    rec = R.DNRecorder(session.brain, session.encoder)
    rows, motion = [], []
    started = time.perf_counter()
    for t in range(ticks):
        n_before = len(rec.spikes)
        session.tick(pointer=PARKED, strike=False)
        if len(rec.spikes) == n_before:
            continue                     # only brain-stepped ticks are kept
        motor = session.fly_loop.last_motor
        action = session.fly_loop.last_action
        m = motor.motion
        r = session.last_retina
        fly, sw, lc = session.world.fly, session.world.swatter, session.world.lifecycle
        motion.append([m.forward_speed, m.lateral_speed, m.yaw_rate, m.saccade_remaining])
        rows.append({
            'tick': t, 'alive': bool(fly.alive),
            'theta': float(r.theta), 'theta_dot': float(r.theta_dot), 'azimuth': float(r.azimuth),
            'dnp01_left': float(motor.dnp01_left), 'dnp01_right': float(motor.dnp01_right),
            'escape': bool(action.escape),
            'channel': (policy.criterion_diagnostics().get('escape_trigger_channel')
                        if action.escape else None),
            'behavior_state': policy.diagnostics().get('behavior_state'),
            'lifecycle_mode': None if lc is None else str(lc.mode),
            'events': [e['type'] for e in lc.events] if lc is not None else [],
            # WORLD values: offline interpretation only.
            'fly': [float(fly.x), float(fly.y), float(fly.vx), float(fly.vy), float(fly.heading)],
            'paddle': [float(sw.x), float(sw.y), float(sw.height), float(sw.vx), float(sw.vy)]})
        if (t + 1) % 1000 == 0:
            print('  room %s %d: %d/%d  %.0fs' % (which, seed, t + 1, ticks, time.perf_counter() - started),
                  flush=True)
    session.close()
    sp, se, dr = rec.window(0, len(rec.spikes))
    assert sp.shape[0] == len(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, spikes=sp, sensory=se, drive=dr, motion=np.array(motion))
    meta = {'set': which, 'seed': seed, 'ticks': ticks, 'stepped': len(rows),
            'runtime_commit': R.RUNTIME_COMMIT,
            'room_config_sha256': sha256(R.RUNTIME_WORKTREE / 'game_room_config.json'),
            'calibration_origin': getattr(source, 'origin', str(source)),
            'motion_keys': ['forward_speed', 'lateral_speed', 'yaw_rate', 'saccade_remaining'],
            'pointer': list(PARKED), 'numba_threads': int(os.environ['NUMBA_NUM_THREADS']),
            'wall_seconds': time.perf_counter() - started, 'record_tool_sha256': sha256(__file__),
            'rows': rows}
    if frozen is not None:
        meta['frozen_criteria_sha256'] = sha256(FROZEN)
    meta.update(rec.panel_meta())
    (OUT / ('room_%s_seed%d.json' % (which, seed))).write_text(json.dumps(meta) + '\n', encoding='utf-8')
    print('room %s %d written: %d stepped, %d runtime escapes'
          % (which, seed, len(rows), sum(r['escape'] for r in rows)))


def run_n0(chunk, trials):
    check_frozen()
    out = OUT / ('n0_holdout_chunk%d.npz' % chunk)
    if out.exists():
        raise SystemExit('%s exists' % out)
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    config = json.loads(subprocess.check_output(['git', 'show', N0_COMMIT + ':game_room_config.json'],
                                                cwd=MAIN, text=True))
    decay = float(np.exp(-float(config['sim']['tick_seconds']) / float(config['brain']['trace_tau_seconds'])))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=MAIN)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rec = R.DNRecorder(session.brain, session.encoder)
    i01 = [rec.types.index('DNp01'), rec.types.index('DNp01') + 1]
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + N0_OFFSET_ADD + chunk)
    spikes, sensory, drive, motion, seeds, exact = [], [], [], [], [], []
    started = time.perf_counter()
    for i in range(trials):
        seed = N0_SEED_BASE + chunk * 10000 + i
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        begin = len(rec.spikes)
        t = _trial(session, policy, seed, (np.cos(angle) * radius, np.sin(angle) * radius), 1400, None)
        sp, se, dr = rec.window(begin, len(rec.spikes))
        tl = R.trace_from_spikes(sp[:, i01[0]], decay)[-1400:]
        tr = R.trace_from_spikes(sp[:, i01[1]], decay)[-1400:]
        exact.append(bool(np.array_equal(tl, t['left']) and np.array_equal(tr, t['right'])))
        mo = [[h.motion.forward_speed, h.motion.lateral_speed, h.motion.yaw_rate, h.motion.saccade_remaining]
              for h in policy.history[-1400:]]
        spikes.append(sp[-1400:])
        sensory.append(se[-1400:])
        drive.append(dr[-1400:])
        motion.append(mo)
        seeds.append(seed)
        del rec.spikes[:], rec.sensory[:], rec.drive[:]
        if (i + 1) % 10 == 0:
            print('  n0 holdout chunk %d: %d/%d exact %d  %.0fs' % (chunk, i + 1, trials, sum(exact),
                                                                  time.perf_counter() - started), flush=True)
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, spikes=np.stack(spikes), sensory=np.stack(sensory), drive=np.stack(drive),
                        motion=np.array(motion), seeds=np.array(seeds), exact=np.array(exact))
    meta = {'chunk': chunk, 'trials': trials, 'seeds': [seeds[0], seeds[-1]],
            'offset_rng': 'default_rng(encoder_seed + %d + chunk)' % N0_OFFSET_ADD,
            'config_commit': N0_COMMIT, 'protocol': 'tools/calibrate_escape._trial, fixed fly, no loom',
            'numba_threads': int(os.environ['NUMBA_NUM_THREADS']), 'exact_trials': int(sum(exact)),
            'max_encoder_drive': float(np.max(drive)), 'frozen_criteria_sha256': sha256(FROZEN),
            'wall_seconds': time.perf_counter() - started, 'record_tool_sha256': sha256(__file__)}
    meta.update(rec.panel_meta())
    (OUT / ('n0_holdout_chunk%d.json' % chunk)).write_text(json.dumps(meta, indent=1) + '\n', encoding='utf-8')
    print('n0 holdout chunk %d written: exact %d / %d' % (chunk, sum(exact), trials))


if __name__ == '__main__':
    if ARGS.mode == 'room':
        if ARGS.set is None or ARGS.seed is None:
            raise SystemExit('--set and --seed are required for room')
        run_room(ARGS.set, ARGS.seed, ARGS.ticks)
    else:
        run_n0(ARGS.chunk, ARGS.trials)
