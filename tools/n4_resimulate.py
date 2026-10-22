"""M1.8-N4A research: exact, instrumented re-simulation of recorded runs.

Research only. No runtime file, configuration, calibration record, brain parameter,
encoder parameter or policy observation is changed. The brain's own `step` runs unchanged;
this tool only observes it:

* before each step it reads the DNp01 voltages and the spikes of the previous step, and
  computes the synaptic input into each DNp01 cell split by source (the encoder's chosen
  LC4/LPLC2 cells, other excitatory partners, inhibitory partners);
* it reads the step's noise draw from a deep copy of the brain's random generator, so the
  brain's own stream is untouched and the copy draws exactly the same numbers;
* after the step it records which DNp01 cells fired, the LC4/LPLC2 sensory spike counts,
  and the spikes of every descending neuron (offline exploratory data only; nothing is
  wired into any policy).

Every re-simulated run is verified against its recording: the DNp01 trace recomputed from
the re-simulated spikes must equal the recorded DNp01 values exactly.

Datasets (each needs its own process, because the Numba thread count is fixed at import):

    python tools/n4_resimulate.py --dataset n0        # 150 x 1400-tick N0 arm, 4 threads
    python tools/n4_resimulate.py --dataset n1        # 300 N1 trials, 4 threads
    python tools/n4_resimulate.py --dataset session --session results/game/sessions/<id>
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset', choices=('n0', 'n1', 'session'), required=True)
    p.add_argument('--session', type=Path)
    p.add_argument('--out', type=Path, default=ROOT / 'artifacts/m1_8_n4')
    return p.parse_args()


ARGS = _args() if __name__ == '__main__' else None
if ARGS is not None:
    # The recorded runs used these thread counts; the float summation order in the
    # synaptic propagation depends on it.
    if ARGS.dataset == 'session':
        manifest = json.loads((ARGS.session / 'manifest.json').read_text(encoding='utf-8'))
        os.environ['NUMBA_NUM_THREADS'] = str(manifest['runtime']['numba_threads'])
    else:
        os.environ['NUMBA_NUM_THREADS'] = '4'
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402
from scipy import sparse  # noqa: E402

N0_COMMIT = '3d41113'
N1_COMMIT = '76806f0'


def config_at(commit):
    text = subprocess.check_output(['git', 'show', commit + ':game_room_config.json'],
                                   cwd=ROOT, text=True)
    return json.loads(text)


class Probe:
    """Observer around FlyBrain.step (CPU, batch 1)."""

    def __init__(self, brain, encoder):
        self.b = brain
        self.watch = np.array([int(brain.groups['escape_L'][0]), int(brain.groups['escape_R'][0])])
        W = sparse.csc_matrix((brain.weights, brain.indices, brain.indptr),
                              shape=(brain.n, brain.n)).tocsr()
        self.rows = np.asarray(W[self.watch].toarray(), np.float64)   # (2, n) incoming
        self.enc_mask = np.zeros(brain.n, bool)
        self.channel = {}
        for ch, label in (('loom', 'LPLC2'), ('threat', 'LC4')):
            for s in 'LR':
                idx = np.asarray(encoder._fd.cells[ch][s])
                self.enc_mask[idx] = True
                self.channel[label + '_' + s] = idx
        self.chan_mask = {k: np.isin(np.arange(brain.n), v) for k, v in self.channel.items()}
        self.dn = brain.cells(['descending_neuron'])
        self.dn_mask = np.zeros(brain.n, bool)
        self.dn_mask[self.dn] = True
        self.encoder = encoder
        self.cols = ('v_old_L', 'v_old_R', 'v_pre_L', 'v_pre_R', 'cur_enc_L', 'cur_enc_R',
                     'cur_exc_L', 'cur_exc_R', 'cur_inh_L', 'cur_inh_R', 'kick_L', 'kick_R',
                     'spk_L', 'spk_R', 'LPLC2_L', 'LPLC2_R', 'LC4_L', 'LC4_R',
                     'drive_loomL', 'drive_loomR', 'drive_threatL', 'drive_threatR',
                     'model_mismatch')
        self.data = []
        self.dn_steps, self.dn_cells = [], []
        self.spike_partners = []

    def step(self, original, inject):
        b = self.b
        prev = np.asarray(b.fired, np.int64)
        w = self.rows[:, prev]
        gain = float(b.gain)
        enc = self.enc_mask[prev]
        cur_enc = gain * w[:, enc].sum(1)
        rest = w[:, ~enc]
        cur_exc = gain * np.where(rest > 0, rest, 0).sum(1)
        cur_inh = gain * np.where(rest < 0, rest, 0).sum(1)
        v_old = np.asarray(b.v[self.watch, 0], np.float64).copy()
        kick = copy.deepcopy(b.rng).random((b.n, 1))[self.watch, 0] < b.noise_hz * b.dt
        fired = original(inject=inject)
        spiked = np.isin(self.watch, fired)
        v_pre = v_old * float(b.decay) + cur_enc + cur_exc + cur_inh + float(b.tonic) \
            + kick * float(b.noise_amp)
        v_new = np.asarray(b.v[self.watch, 0], np.float64)
        mismatch = int(np.any((~spiked) & (np.abs(v_new - v_pre) > 1e-4)) or
                       np.any(spiked & (v_pre < 1.0 - 1e-4)))
        drive = self.encoder.last_drive
        fset = fired
        self.data.append((*v_old, *v_pre, *cur_enc, *cur_exc, *cur_inh, *kick.astype(float),
                          *spiked.astype(float),
                          *(float(self.chan_mask[k][fset].sum()) for k in
                            ('LPLC2_L', 'LPLC2_R', 'LC4_L', 'LC4_R')),
                          drive.get('loomL', 0.0), drive.get('loomR', 0.0),
                          drive.get('threatL', 0.0), drive.get('threatR', 0.0), mismatch))
        step_index = len(self.data) - 1
        dn = fset[self.dn_mask[fset]]
        if dn.size:
            self.dn_steps.append(np.full(dn.size, step_index, np.int32))
            self.dn_cells.append(dn.astype(np.int32))
        for side in (0, 1):
            if spiked[side]:
                contrib = w[side] * gain
                top = np.argsort(-np.abs(contrib))[:12]
                self.spike_partners.append({
                    'step': step_index, 'side': 'LR'[side],
                    'v_old': float(v_old[side]), 'kick': bool(kick[side]),
                    'cur_enc': float(cur_enc[side]), 'cur_exc': float(cur_exc[side]),
                    'cur_inh': float(cur_inh[side]),
                    'partners': [[int(prev[j]), float(contrib[j])] for j in top if contrib[j] != 0]})
        return fired

    def attach(self, brain):
        original = brain.step

        def hooked(eye_drive=None, inject=()):
            if eye_drive is not None:
                raise RuntimeError('eye drive is not used by the game and is not instrumented')
            return self.step(original, inject)
        brain.step = hooked

    def arrays(self):
        a = np.array(self.data, dtype=np.float64)
        out = {c: a[:, i] for i, c in enumerate(self.cols)}
        out['dn_steps'] = np.concatenate(self.dn_steps) if self.dn_steps else np.zeros(0, np.int32)
        out['dn_cells'] = np.concatenate(self.dn_cells) if self.dn_cells else np.zeros(0, np.int32)
        return out


def trace_from_spikes(spk_l, spk_r, decay):
    """Recompute the recorded DNp01 trace (flybrain.Trace: float32, +1 per spike)."""
    d = np.float32(decay)
    tl = tr = np.float32(0.0)
    out_l, out_r = np.empty(spk_l.size), np.empty(spk_l.size)
    for i in range(spk_l.size):
        tl = np.float32(tl * d)
        tr = np.float32(tr * d)
        if spk_l[i]:
            tl = np.float32(tl + np.float32(1.0))
        if spk_r[i]:
            tr = np.float32(tr + np.float32(1.0))
        out_l[i], out_r[i] = float(tl), float(tr)
    return out_l, out_r


def trace_decay(config):
    return float(np.exp(-float(config['sim']['tick_seconds'])
                        / float(config['brain']['trace_tau_seconds'])))


def save(out_dir, name, probe, meta):
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / (name + '.npz'), **probe.arrays())
    meta['dn_cell_types'] = {int(i): str(probe.b.cell_type[i]) for i in probe.dn}
    meta['dn_cell_sides'] = {int(i): str(probe.b.side[i]) for i in probe.dn}
    meta['spike_partners'] = probe.spike_partners
    meta['partner_types'] = {int(j): [str(probe.b.cell_type[j]), str(probe.b.side[j]),
                                      str(probe.b.superclass[j]) if probe.b.superclass is not None else '']
                             for sp in probe.spike_partners for j, _ in sp['partners']}
    meta['numba_threads'] = int(os.environ['NUMBA_NUM_THREADS'])
    (out_dir / (name + '.json')).write_text(json.dumps(meta, default=lambda o: o.item()) + '\n',
                                            encoding='utf-8')


def run_n0(out_dir):
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    config = config_at(N0_COMMIT)
    raw = np.load(ROOT / 'artifacts/m1_8_no_loom_calibration/raw.npz')['null']
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    probe = Probe(session.fly_loop.brain, session.encoder)
    probe.attach(session.fly_loop.brain)
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']))
    decay = trace_decay(config)
    trials, exact, started = [], 0, time.perf_counter()
    for i in range(150):
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        begin = len(probe.data)
        t = _trial(session, policy, 4000 + i, (np.cos(angle) * radius, np.sin(angle) * radius),
                   1400, None)
        end = len(probe.data)
        a = np.array(probe.data[begin:end])
        spk_l, spk_r = a[:, probe.cols.index('spk_L')], a[:, probe.cols.index('spk_R')]
        tl, tr = trace_from_spikes(spk_l, spk_r, decay)
        total = (tl + tr)[-1400:]
        ok = bool(np.array_equal(total, t['total'])
                  and np.array_equal(total, raw[i * 1400:(i + 1) * 1400]))
        exact += ok
        trials.append({'index': i, 'seed': 4000 + i, 'offset_radius': radius,
                       'first_step': begin, 'record_first_step': end - 1400, 'end_step': end,
                       'exact': ok})
        if (i + 1) % 10 == 0:
            print('  N0 %d/150 exact %d  %.0fs' % (i + 1, exact, time.perf_counter() - started),
                  flush=True)
    session.close()
    save(out_dir, 'n0', probe, {'dataset': 'n0', 'config_commit': N0_COMMIT, 'trials': trials,
                                'exact_trials': exact})
    print('N0 exact', exact, '/ 150')


def run_n1(out_dir):
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy
    from tools.loom_robustness_study import run_trial, DT
    config = config_at(N1_COMMIT)
    data = np.load(ROOT / 'artifacts/m1_8_loom_robustness/trials.npz')
    settle = max(40, round(config['swatter'].get('physical', {})
                           .get('calibration_settle_seconds', 0.8) / DT))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    probe = Probe(session.fly_loop.brain, session.encoder)
    probe.attach(session.fly_loop.brain)
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + 991)
    decay = trace_decay(config)
    classes = ('strong_direct', 'medium_committed', 'weak_approach', 'glancing_pass',
               'aborted_approach')
    trials, exact, idx, started = [], 0, 0, time.perf_counter()
    for ci, kind in enumerate(classes):
        for i in range(60):
            begin = len(probe.data)
            t = run_trial(session, policy, 6000 + ci * 1000 + i, kind, rng, settle)
            end = len(probe.data)
            a = np.array(probe.data[begin:end])
            tl, tr = trace_from_spikes(a[:, probe.cols.index('spk_L')],
                                       a[:, probe.cols.index('spk_R')], decay)
            n = t['ticks']
            total = (tl + tr)[-n:]
            ok = bool(np.array_equal(total, t['dnp01'])
                      and np.array_equal(total, data['%d_dnp01' % idx]))
            exact += ok
            trials.append({'index': idx, 'kind': kind, 'seed': 6000 + ci * 1000 + i,
                           'first_step': begin, 'record_first_step': end - n, 'end_step': end,
                           'ticks': n, 'click_tick': t['click_tick'], 'exact': ok})
            idx += 1
        print('  N1 %s done, exact %d/%d  %.0fs' % (kind, exact, idx, time.perf_counter() - started),
              flush=True)
    session.close()
    save(out_dir, 'n1', probe, {'dataset': 'n1', 'config_commit': N1_COMMIT, 'trials': trials,
                                'exact_trials': exact, 'settle_ticks': settle})
    print('N1 exact', exact, '/ 300')


def run_session(path, out_dir):
    from game.fly import build_brain
    from game.perception import Retina, RetinalEncoder
    manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
    config = manifest['config']
    brain = build_brain(config, ROOT)
    encoder = RetinalEncoder(brain, config)
    probe = Probe(brain, encoder)
    probe.attach(brain)
    decay = trace_decay(config)
    seeds = {json.loads(l)['episode']: json.loads(l)['seed']
             for l in (path / 'episodes.jsonl').open(encoding='utf-8')}
    rows = [json.loads(l) for l in (path / 'ticks.jsonl').open(encoding='utf-8')]
    episodes = {}
    for r in rows:
        episodes.setdefault(r['episode'], []).append(r)
    ep_meta, exact_rows, stepped_rows, sensory_exact = [], 0, 0, 0
    for ep, er in episodes.items():
        brain.reset(int(seeds[ep]) + 977)
        begin = len(probe.data)
        row_step = []
        for r in er:
            if not r['neural']['brain_stepped']:
                row_step.append(-1)
                continue
            ret = r['retina']
            inject = encoder.inject(Retina(ret['theta'], ret['theta_dot'], ret['azimuth']))
            brain.step(inject=inject)
            row_step.append(len(probe.data) - 1)
        a = np.array(probe.data[begin:])
        tl, tr = trace_from_spikes(a[:, probe.cols.index('spk_L')],
                                   a[:, probe.cols.index('spk_R')], decay)
        for k, r in zip(row_step, er):
            if k < 0:
                continue
            stepped_rows += 1
            j = k - begin
            exact_rows += (tl[j] == r['neural']['dnp01_left'] and tr[j] == r['neural']['dnp01_right'])
            s = r['sensory_spikes']
            sensory_exact += (a[j, probe.cols.index('LPLC2_L')] == s['LPLC2_left']
                              and a[j, probe.cols.index('LPLC2_R')] == s['LPLC2_right']
                              and a[j, probe.cols.index('LC4_L')] == s['LC4_left']
                              and a[j, probe.cols.index('LC4_R')] == s['LC4_right'])
        ep_meta.append({'episode': ep, 'seed': seeds[ep], 'first_step': begin,
                        'row_step': row_step})
        print('  episode %d: %d rows' % (ep, len(er)), flush=True)
    name = 'session_' + path.name
    save(out_dir, name, probe, {'dataset': 'session', 'session': path.name, 'episodes': ep_meta,
                                'stepped_rows': stepped_rows, 'dnp01_exact_rows': exact_rows,
                                'sensory_exact_rows': sensory_exact})
    print('session %s: DNp01 exact %d / %d stepped rows, sensory spikes exact %d'
          % (path.name, exact_rows, stepped_rows, sensory_exact))


if __name__ == '__main__':
    if ARGS.dataset == 'n0':
        run_n0(ARGS.out)
    elif ARGS.dataset == 'n1':
        run_n1(ARGS.out)
    else:
        run_session(ARGS.session.resolve(), ARGS.out)
