"""M1.8-N4B2 research: record descending-neuron (DN) spikes for offline readout analysis.

Research only. No runtime file, configuration, calibration record, brain parameter,
encoder parameter, noise setting or policy observation is changed. The brain's own `step`
runs unchanged; a thin wrapper only reads, after each step, which cells of a fixed DN
panel fired, the LC4/LPLC2 sensory spike counts per side, and the encoder drive. Nothing
recorded here reaches any policy.

DN panel: every descending neuron that receives direct weight >= 0.03 from the encoder's
chosen LC4/LPLC2 cells (26 cells, 13 bilateral types). It is computed from the frozen graph
and stored with every output file.

Modes (one process per chunk, because the Numba thread count is fixed at import):

    # Development N0 re-simulations (seeds and offsets of the existing N4B1 fresh N0 and
    # N4B1C holdout); every trial is verified bit-exact against the recorded DNp01 traces.
    python tools/n4b2_record.py n0 --set n4b1_fresh --chunk 0      # chunks 0..3
    python tools/n4b2_record.py n0 --set n4b1c_holdout --chunk 0   # chunks 0..3

    # NEW independent N0 holdout; refuses to run unless the N4B2 criteria are frozen.
    python tools/n4b2_record.py n0 --set n4b2_holdout --chunk 0    # chunks 0..3

    # ROOM free flight with no player (paddle parked at its spawn point) under the
    # accepted N4B1C runtime, taken from a clean detached worktree of
    # feature/m1-8-n4b1c-runtime. Candidate readouts are evaluated later in shadow mode.
    python tools/n4b2_record.py room --seed 7101 --ticks 9000
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
OUT = MAIN / 'artifacts/m1_8_n4b2'
RUNTIME_COMMIT = 'e3c55b36084cd1d05e5f38d0b178aed0b9a59ddf'
RUNTIME_WORKTREE = Path(os.environ.get('N4B1C_WORKTREE',
                                       MAIN / 'artifacts/worktrees/n4b1c-runtime-detached')).resolve()
N0_COMMIT = '3d41113'
PANEL_MIN_WEIGHT = 0.03
FROZEN = OUT / 'frozen_criteria.json'
CRITERIA_FILE = MAIN / 'tools/n4b2_criteria.py'

# Seeds and offset generators. The first two reproduce existing development data exactly.
N0_SETS = {
    'n4b1_fresh': {'seed_base': 30000, 'offset_add': 424242,
                   'reference': 'artifacts/m1_8_n4b1/fresh_n0_chunk%d.npz'},
    'n4b1c_holdout': {'seed_base': 210000, 'offset_add': 616161,
                      'reference': 'artifacts/m1_8_n4b1c/holdout_chunk%d.npz'},
    # Non-overlapping with N0 4000-4149, loom 5000-5149, N1 6000-10059, N4B1 30000-60149,
    # N4B1C 210000-240149, the closed-loop seeds and the human-session seeds.
    'n4b2_holdout': {'seed_base': 310000, 'offset_add': 717171, 'reference': None},
}


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('n0', 'room'))
    p.add_argument('--set', choices=tuple(N0_SETS))
    p.add_argument('--chunk', type=int, default=0)
    p.add_argument('--trials', type=int, default=150)
    p.add_argument('--seed', type=int)
    p.add_argument('--ticks', type=int, default=9000)
    return p.parse_args()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_runtime_worktree():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=RUNTIME_WORKTREE, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain'], cwd=RUNTIME_WORKTREE,
                                    text=True).strip()
    if head != RUNTIME_COMMIT or dirty:
        raise SystemExit('runtime worktree %s must be clean at %s (HEAD %s, dirty %r)'
                         % (RUNTIME_WORKTREE, RUNTIME_COMMIT, head, dirty[:200]))


ARGS = _args() if __name__ == '__main__' else None
if ARGS is not None:
    os.environ.setdefault('NUMBA_NUM_THREADS', '2' if ARGS.mode == 'n0' else '4')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    if ARGS.mode == 'room':
        verify_runtime_worktree()
        CODE = RUNTIME_WORKTREE
    else:
        CODE = MAIN
    sys.path.insert(0, str(CODE))

import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402


def encoder_cells(encoder):
    return {label + '_' + s: np.asarray(encoder._fd.cells[ch][s])
            for ch, label in (('loom', 'LPLC2'), ('threat', 'LC4')) for s in 'LR'}


def dn_panel(brain, encoder, min_weight=PANEL_MIN_WEIGHT):
    """DN cells with direct weight >= min_weight from the chosen encoder cells."""
    W = sparse.csc_matrix((brain.weights, brain.indices, brain.indptr),
                          shape=(brain.n, brain.n)).tocsr()
    dn = brain.cells(['descending_neuron'])
    chosen = np.concatenate(list(encoder_cells(encoder).values()))
    total = np.asarray(W[dn][:, chosen].sum(1)).ravel()
    keep = dn[total >= min_weight]
    order = np.lexsort((np.array([str(brain.side[c]) for c in keep]),
                        np.array([str(brain.cell_type[c]) for c in keep])))
    keep = keep[order]
    return keep, [str(brain.cell_type[c]) for c in keep], [str(brain.side[c]) for c in keep]


class DNRecorder:
    """Wraps brain.step; after each step stores panel spikes, sensory counts and drive."""

    def __init__(self, brain, encoder):
        self.brain, self.encoder = brain, encoder
        self.panel, self.types, self.sides = dn_panel(brain, encoder)
        self.slot = np.full(brain.n, -1, np.int64)
        self.slot[self.panel] = np.arange(self.panel.size)
        cells = encoder_cells(encoder)
        self.sensory_keys = ('LPLC2_L', 'LPLC2_R', 'LC4_L', 'LC4_R')
        self.sensory_masks = []
        for k in self.sensory_keys:
            m = np.zeros(brain.n, bool)
            m[cells[k]] = True
            self.sensory_masks.append(m)
        self.spikes, self.sensory, self.drive = [], [], []
        original = brain.step

        def hooked(eye_drive=None, inject=()):
            fired = original(eye_drive=eye_drive, inject=inject)
            f = np.asarray(fired, np.int64)
            row = np.zeros(self.panel.size, bool)
            s = self.slot[f]
            row[s[s >= 0]] = True
            self.spikes.append(row)
            self.sensory.append([int(m[f].sum()) for m in self.sensory_masks])
            d = encoder.last_drive or {}
            self.drive.append([float(d.get(k, 0.0)) for k in ('loomL', 'loomR', 'threatL', 'threatR')])
            return fired
        brain.step = hooked

    def window(self, begin, end):
        return (np.array(self.spikes[begin:end], bool), np.array(self.sensory[begin:end], np.int16),
                np.array(self.drive[begin:end], np.float32))

    def panel_meta(self):
        return {'panel_cells': [int(c) for c in self.panel], 'panel_types': self.types,
                'panel_sides': self.sides, 'panel_min_weight': PANEL_MIN_WEIGHT,
                'sensory_keys': list(self.sensory_keys),
                'drive_keys': ['loomL', 'loomR', 'threatL', 'threatR']}


def trace_from_spikes(spk, decay):
    """flybrain.Trace arithmetic (float32, +1 per spike) for one cell."""
    d = np.float32(decay)
    t = np.float32(0.0)
    out = np.empty(spk.size)
    for i in range(spk.size):
        t = np.float32(t * d)
        if spk[i]:
            t = np.float32(t + np.float32(1.0))
        out[i] = float(t)
    return out


def check_frozen():
    if not FROZEN.exists():
        raise SystemExit('the N4B2 criteria must be frozen (tools/n4b2_analysis.py freeze) '
                         'before the new holdout is generated')
    frozen = json.loads(FROZEN.read_text(encoding='utf-8'))
    if sha256(CRITERIA_FILE) != frozen['criteria_module_sha256']:
        raise SystemExit('tools/n4b2_criteria.py changed after the freeze')
    return frozen


def run_n0(name, chunk, trials):
    spec = N0_SETS[name]
    frozen = check_frozen() if spec['reference'] is None else None
    out_path = OUT / ('n0_%s_chunk%d.npz' % (name, chunk))
    if spec['reference'] is None and out_path.exists():
        raise SystemExit('%s exists: the holdout is generated once' % out_path)
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    config = json.loads(subprocess.check_output(['git', 'show', N0_COMMIT + ':game_room_config.json'],
                                                cwd=MAIN, text=True))
    decay = float(np.exp(-float(config['sim']['tick_seconds']) / float(config['brain']['trace_tau_seconds'])))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=MAIN)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rec = DNRecorder(session.brain, session.encoder)
    i01 = [rec.types.index('DNp01'), rec.types.index('DNp01') + 1]
    assert [rec.sides[i] for i in i01] == ['L', 'R']
    ref = None
    if spec['reference'] is not None:
        ref = np.load(MAIN / (spec['reference'] % chunk))
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + spec['offset_add'] + chunk)
    spikes, sensory, drive, seeds, radii, exact = [], [], [], [], [], []
    started = time.perf_counter()
    for i in range(trials):
        seed = spec['seed_base'] + chunk * 10000 + i
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        begin = len(rec.spikes)
        t = _trial(session, policy, seed, (np.cos(angle) * radius, np.sin(angle) * radius), 1400, None)
        end = len(rec.spikes)
        sp, se, dr = rec.window(begin, end)
        # Traces run over the whole trial (settle included); keep the recorded 1400 ticks.
        tl = trace_from_spikes(sp[:, i01[0]], decay)[-1400:]
        tr = trace_from_spikes(sp[:, i01[1]], decay)[-1400:]
        ok = bool(np.array_equal(tl, t['left']) and np.array_equal(tr, t['right']))
        if ref is not None:
            ok = ok and bool(ref['seeds'][i] == seed and np.array_equal(tl, ref['left'][i])
                             and np.array_equal(tr, ref['right'][i]))
        exact.append(ok)
        spikes.append(sp[-1400:])
        sensory.append(se[-1400:])
        drive.append(dr[-1400:])
        seeds.append(seed)
        radii.append(radius)
        del rec.spikes[:], rec.sensory[:], rec.drive[:]
        if (i + 1) % 10 == 0:
            print('  %s chunk %d: %d/%d exact %d  %.0fs' % (name, chunk, i + 1, trials, sum(exact),
                                                           time.perf_counter() - started), flush=True)
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, spikes=np.stack(spikes), sensory=np.stack(sensory),
                        drive=np.stack(drive), seeds=np.array(seeds), radii=np.array(radii),
                        exact=np.array(exact))
    meta = {'set': name, 'chunk': chunk, 'trials': trials, 'seeds': [seeds[0], seeds[-1]],
            'offset_rng': 'default_rng(encoder_seed + %d + chunk)' % spec['offset_add'],
            'config_commit': N0_COMMIT, 'protocol': 'tools/calibrate_escape._trial, fixed fly, no loom',
            'numba_threads': int(os.environ['NUMBA_NUM_THREADS']),
            'exact_trials': int(sum(exact)),
            'exact_reference': spec['reference'] % chunk if spec['reference'] else 'own policy history',
            'max_encoder_drive': float(np.max(drive)), 'wall_seconds': time.perf_counter() - started,
            'code_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=MAIN, text=True).strip(),
            'record_tool_sha256': sha256(__file__)}
    if frozen is not None:
        meta['frozen_criteria_sha256'] = sha256(FROZEN)
        meta['criteria_module_sha256'] = frozen['criteria_module_sha256']
    meta.update(rec.panel_meta())
    (OUT / ('n0_%s_chunk%d.json' % (name, chunk))).write_text(json.dumps(meta, indent=1) + '\n',
                                                              encoding='utf-8')
    print('%s chunk %d written: exact %d / %d' % (name, chunk, sum(exact), trials))


PARKED = (1920.0, 388.8)   # swatter spawn point (tools/n2_closed_loop.py): no pointer command


def run_room(seed, ticks):
    """No-player ROOM free flight under the accepted runtime; per-tick recording."""
    from game.session import Session, build_policy, load_config
    config = load_config(RUNTIME_WORKTREE / 'game_room_config.json')
    policy, source = build_policy(config, root=RUNTIME_WORKTREE)
    session = Session(config, policy=policy, seed=seed, mode='evaluation', root=RUNTIME_WORKTREE)
    rec = DNRecorder(session.brain, session.encoder)
    rows = []
    started = time.perf_counter()
    for t in range(ticks):
        n_before = len(rec.spikes)
        ev = session.tick(pointer=PARKED, strike=False)
        stepped = len(rec.spikes) > n_before
        motor = session.fly_loop.last_motor
        action = session.fly_loop.last_action
        r = session.last_retina
        fly = session.world.fly
        sw = session.world.swatter
        lc = session.world.lifecycle
        events = [e['type'] for e in lc.events] if lc is not None else []
        rows.append({
            'tick': t, 'stepped': stepped, 'alive': bool(fly.alive),
            'theta': None if r is None else float(r.theta),
            'theta_dot': None if r is None else float(r.theta_dot),
            'azimuth': None if r is None else float(r.azimuth),
            'dnp01_left': None if motor is None else float(motor.dnp01_left),
            'dnp01_right': None if motor is None else float(motor.dnp01_right),
            'escape': bool(action.escape) and stepped,
            'channel': (policy.criterion_diagnostics().get('escape_trigger_channel')
                        if (action.escape and stepped and hasattr(policy, 'criterion_diagnostics')) else None),
            'lifecycle_mode': None if lc is None else str(lc.mode),
            'events': events,
            # WORLD geometry: offline interpretation only.
            'fly_xyz': [float(fly.x), float(fly.y), float(getattr(fly, 'z', 0.0))],
            'swatter_xy': [float(sw.x), float(sw.y)]})
        if (t + 1) % 1000 == 0:
            print('  room seed %d: %d/%d  %.0fs' % (seed, t + 1, ticks, time.perf_counter() - started),
                  flush=True)
    session.close()
    stepped_idx = [i for i, row in enumerate(rows) if row['stepped']]
    sp, se, dr = rec.window(0, len(rec.spikes))
    if sp.shape[0] != len(stepped_idx):
        raise RuntimeError('brain steps (%d) do not match stepped ticks (%d)' % (sp.shape[0], len(stepped_idx)))
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / ('room_seed%d.npz' % seed), spikes=sp, sensory=se, drive=dr,
                        stepped_ticks=np.array(stepped_idx))
    meta = {'seed': seed, 'ticks': ticks, 'stepped_ticks': len(stepped_idx),
            'runtime_commit': RUNTIME_COMMIT, 'runtime_worktree': str(RUNTIME_WORKTREE),
            'room_config_sha256': sha256(RUNTIME_WORKTREE / 'game_room_config.json'),
            'calibration_source': str(source.path) if hasattr(source, 'path') else str(source),
            'pointer': list(PARKED), 'numba_threads': int(os.environ['NUMBA_NUM_THREADS']),
            'wall_seconds': time.perf_counter() - started, 'record_tool_sha256': sha256(__file__),
            'rows': rows}
    meta.update(rec.panel_meta())
    (OUT / ('room_seed%d.json' % seed)).write_text(json.dumps(meta) + '\n', encoding='utf-8')
    print('room seed %d written: %d stepped ticks, %d runtime escapes'
          % (seed, len(stepped_idx), sum(r['escape'] for r in rows)))


if __name__ == '__main__':
    if ARGS.mode == 'n0':
        if ARGS.set is None:
            raise SystemExit('--set is required for n0')
        run_n0(ARGS.set, ARGS.chunk, ARGS.trials)
    else:
        if ARGS.seed is None:
            raise SystemExit('--seed is required for room')
        run_room(ARGS.seed, ARGS.ticks)
