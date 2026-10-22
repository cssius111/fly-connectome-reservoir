"""M1.8-N4B1 research: lateralized DNp01 readout validation.

Research only. No runtime file, configuration, calibration record, policy observation,
Retina, encoder, brain, noise model, lifecycle, physics or recorder is changed. The
candidate policies below live only in this tool.

Hypothesis: the summed DNp01 readout (dnp01_left + dnp01_right) destroys lateral
structure. A threat drives one DNp01 cell repeatedly; spontaneous activity is one
independent noise-driven spike per cell. The candidates therefore look for repeated
evidence on ONE side. Both inputs, `dnp01_left` and `dnp01_right`, are already part of
the policy observation; nothing is added to it.

Frozen candidate family (written to artifacts/m1_8_n4b1/frozen_candidates.json, with its
sha256, before the fresh N0 data are generated; the fresh-N0 mode refuses to run without
it and records its hash):

* spike form, primary. Per side, the DNp01 spike count of each sample is recovered from
  that side's own trace, `s_t = trace_t - decay * trace_{t-1}` (flybrain.Trace, +1 per
  spike; exact to about 1e-7). A side "qualifies" on a sample that holds a new spike on that
  side while that same side's previous spike is at most `max_gap` samples earlier, both
  spikes after the last escape or reset. A left spike followed by a right spike never
  counts. "Within W ms" means the second spike is at most W ms after the first:
      A: 60 ms  (gap <= 3 samples)     B: 80 ms  (gap <= 4; this is the N4A rule)
      C: 100 ms (gap <= 5)             D: 120 ms (gap <= 6)
      E: 160 ms (gap <= 8)
* trace form, secondary: max(dnp01_left, dnp01_right) >= 1 + decay**gap - 1e-4, the
  smallest per-side trace two same-side spikes `gap` samples apart can produce
  (A 1.5487, B 1.4493, C 1.3678, D 1.3011, E 1.2017). It is a superset of the spike form
  because older spikes also add to the trace.

Common semantics: the runtime FixedEscapePolicy is subclassed, so strength, side,
steering, alert state, saccades and the 0.4 s refractory are unchanged runtime code; only
the trigger differs. No firing during refractory; the spike form needs the qualifying
spike on the current sample, so a pair completed during refractory never fires later.

Modes:

    python tools/n4b1_lateral.py freeze
    python tools/n4b1_lateral.py fresh-n0 --chunk 0 --trials 150   # chunks 0..3 in parallel
    python tools/n4b1_lateral.py mechanism
    python tools/n4b1_lateral.py evaluate
    python tools/n4b1_lateral.py closed-loop
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'artifacts/m1_8_n4b1'
FROZEN = OUT / 'frozen_candidates.json'
N0_COMMIT = '3d41113'

if __name__ == '__main__':
    _mode = sys.argv[1] if len(sys.argv) > 1 else ''
    os.environ.setdefault('NUMBA_NUM_THREADS', '2' if _mode == 'fresh-n0' else '4')
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

import numpy as np  # noqa: E402

DT = 0.02
DECAY = float(np.float32(np.exp(-0.2)))
GAPS = {'A': 3, 'B': 4, 'C': 5, 'D': 6, 'E': 8}
FRESH_SEED_BASE = 30000          # original N0 used 4000-4149, its loom arm 5000-5149, N1 6000-10059
FRESH_OFFSET_SEED_ADD = 424242   # original N0 offsets used default_rng(encoder_seed)


def candidate_specs():
    out = []
    for key, gap in GAPS.items():
        out.append({'name': '%s spike: same side twice within %d ms (gap <= %d)' % (key, gap * 20, gap),
                    'key': key + '_spike', 'form': 'spike', 'max_gap': gap})
    for key, gap in GAPS.items():
        out.append({'name': '%s trace: max(L, R) >= %.4f' % (key, 1 + DECAY ** gap - 1e-4),
                    'key': key + '_trace', 'form': 'trace', 'max_gap': gap,
                    'threshold': round(1 + DECAY ** gap - 1e-4, 6)})
    return out


# ------------------------------------------------------------------ policies ---
def base_policy():
    from game.session import build_policy, load_config
    return build_policy(load_config(ROOT / 'game_room_config.json'), ROOT)[0]


_BASE = []


def fresh_base():
    if not _BASE:
        _BASE.append(base_policy())
    p = copy.deepcopy(_BASE[0])
    p.reset()
    return p


def copy_base_params(dst, src):
    for name in ('refractory_ticks', 'tick_seconds', 'forward_bias', 'turn_gain',
                 'alert_threshold', 'steering_alpha', 'alert_saccade_strength',
                 'saccade_interval_ticks', 'alert_dwell_ticks'):
        setattr(dst, name, getattr(src, name))


def lateral_class():
    from game.action import FixedEscapePolicy

    class LateralPolicy(FixedEscapePolicy):
        """Research-only: FixedEscapePolicy with a same-side DNp01 trigger."""

        def __init__(self, spec):
            self.spec = dict(spec)
            base = fresh_base()
            super().__init__(base.threshold, 0.4, DT)
            copy_base_params(self, base)

        def reset(self):
            super().reset()
            # Unknown previous sample: no spike is inferred on the first observed sample
            # (recorded N0/N1 segments begin after a settle period; at an episode start the
            # trace is 0 and callers may set it explicitly).
            self._prev = {'L': None, 'R': None}
            self._last = {'L': None, 'R': None}
            self._pair = {'L': None, 'R': None}
            self._sample = 0
            self._now = {'L': False, 'R': False}
            self._values = {'L': 0.0, 'R': 0.0}
            self.last_trigger = None

        def _observe(self, motor):
            for side, v in (('L', motor.dnp01_left), ('R', motor.dnp01_right)):
                prev = self._prev[side]
                spike = prev is not None and v - DECAY * prev >= 0.5
                self._now[side] = False
                if spike:
                    last = self._last[side]
                    self._now[side] = last is not None and self._sample - last <= self.spec['max_gap']
                    if self._now[side]:
                        self._pair[side] = (last, self._sample)
                    self._last[side] = self._sample
                self._prev[side] = v
                self._values[side] = v

        def _trigger_channel(self, total):
            if self.spec['form'] == 'spike':
                sides = [s for s in 'LR' if self._now[s]]
            else:
                sides = [s for s in 'LR' if self._values[s] >= self.spec['threshold']]
            if not sides:
                return None
            return 'LATERAL_' + ''.join(sides)

        def decide(self, motor):
            self._observe(motor)
            action = super().decide(motor)
            if action.escape:
                self.last_trigger = {'sample': self._sample, 'channel': self._channel,
                                     'last_spike': dict(self._last),
                                     'pair': {s: self._pair[s] for s in 'LR' if self._now[s]}}
                # Evidence from before an escape cannot pair with later spikes.
                self._last = {'L': None, 'R': None}
            self._sample += 1
            return action

        def criterion_diagnostics(self):
            return {'escape_decoder': 'research_lateral_' + self.spec['key'],
                    'escape_trigger_channel': self._channel}

    return LateralPolicy


def reference_policies():
    """legacy (76806f0), strict N2 (FAST 2.20 OR 1.45 x3) and N2b (working tree)."""
    from game.action import FixedEscapePolicy
    from game.session import build_policy
    baseline = json.loads(subprocess.check_output(
        ['git', 'show', '76806f0:game_room_config.json'], cwd=ROOT, text=True))

    def strict():
        b = fresh_base()
        p = FixedEscapePolicy(b.threshold, 0.4, DT, fast_threshold=2.20, persistence_samples=3)
        copy_base_params(p, b)
        return p
    return {'legacy summed single-sample 1.45': lambda: build_policy(baseline, ROOT)[0],
            'strict N2: FAST 2.20 OR 1.45 x3': strict,
            'N2b: FAST 2.10 OR current-H + 3-of-5': fresh_base}


def all_factories():
    L = lateral_class()
    out = dict(reference_policies())
    for spec in candidate_specs():
        out[spec['name']] = (lambda s=spec: L(s))
    return out


# ------------------------------------------------------------------ freeze ---
def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    if FROZEN.exists():
        print('already frozen:', FROZEN, hashlib.sha256(FROZEN.read_bytes()).hexdigest())
        return
    body = {'label': 'M1.8-N4B1 frozen lateralized DNp01 candidate family',
            'frozen_before_fresh_n0': True,
            'frozen_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'decay_per_sample': DECAY, 'candidates': candidate_specs(),
            'fresh_n0_protocol': {'config_commit': N0_COMMIT, 'seed_base': FRESH_SEED_BASE,
                                  'offset_rng': 'default_rng(encoder_seed + %d)' % FRESH_OFFSET_SEED_ADD,
                                  'offset_radius': [30.0, 170.0], 'ticks_per_trial': 1400,
                                  'protocol': 'tools/calibrate_escape._trial, fixed fly, no loom'}}
    FROZEN.write_text(json.dumps(body, indent=1) + '\n', encoding='utf-8')
    print('frozen', FROZEN, hashlib.sha256(FROZEN.read_bytes()).hexdigest())


# ------------------------------------------------------------------ fresh N0 ---
def fresh_n0(chunk, trials):
    if not FROZEN.exists():
        raise SystemExit('run `freeze` first: the candidate family must be frozen before fresh N0')
    frozen_hash = hashlib.sha256(FROZEN.read_bytes()).hexdigest()
    from game.session import Session
    from tools.calibrate_escape import RecordingPolicy, _trial
    config = json.loads(subprocess.check_output(['git', 'show', N0_COMMIT + ':game_room_config.json'],
                                                cwd=ROOT, text=True))
    policy = RecordingPolicy()
    session = Session(config, policy=policy, root=ROOT)
    session.world.collisions_enabled = False
    session.world.fly_motion_enabled = False
    rng = np.random.default_rng(int(config['encoder']['encoder_seed']) + FRESH_OFFSET_SEED_ADD + chunk)
    left, right, seeds, drive_max = [], [], [], 0.0
    started = time.perf_counter()
    for i in range(trials):
        seed = FRESH_SEED_BASE + chunk * 10000 + i
        angle = float(rng.uniform(0, 2 * np.pi))
        radius = float(rng.uniform(30.0, 170.0))
        t = _trial(session, policy, seed, (np.cos(angle) * radius, np.sin(angle) * radius), 1400, None)
        left.append(t['left'])
        right.append(t['right'])
        seeds.append(seed)
        d = session.encoder.last_drive or {}
        drive_max = max(drive_max, max(d.values()) if d else 0.0)
        if (i + 1) % 10 == 0:
            print('  chunk %d: %d/%d  %.0fs' % (chunk, i + 1, trials, time.perf_counter() - started),
                  flush=True)
    session.close()
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / ('fresh_n0_chunk%d.npz' % chunk), left=np.stack(left),
                        right=np.stack(right), seeds=np.array(seeds))
    (OUT / ('fresh_n0_chunk%d.json' % chunk)).write_text(json.dumps({
        'chunk': chunk, 'trials': trials, 'seeds': [seeds[0], seeds[-1]],
        'frozen_candidates_sha256': frozen_hash, 'numba_threads': int(os.environ['NUMBA_NUM_THREADS']),
        'config_commit': N0_COMMIT, 'wall_seconds': time.perf_counter() - started,
        'last_trial_drive_max': drive_max}) + '\n', encoding='utf-8')
    print('chunk %d written' % chunk)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mode', choices=('freeze', 'fresh-n0', 'mechanism', 'evaluate', 'closed-loop'))
    ap.add_argument('--chunk', type=int, default=0)
    ap.add_argument('--trials', type=int, default=150)
    args = ap.parse_args()
    if args.mode == 'freeze':
        freeze()
    elif args.mode == 'fresh-n0':
        fresh_n0(args.chunk, args.trials)
    else:
        from tools.n4b1_analysis import run  # noqa: E402
        run(args.mode)
