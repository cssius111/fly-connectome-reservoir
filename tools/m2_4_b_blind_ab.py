"""M2.4-B: blind human A/B gameplay test, N4B1C vs the frozen M2.4-A candidate (ROOM; human validation only).

Nothing is trained and neither policy is modified:

- A = the accepted N4B1C runtime policy, built exactly as the game builds it (`Session(config)` without a policy
  override);
- B = the frozen M2.4-A candidate (numpy export, parameter sha256 verified) inside the same `ManeuverPolicy` adapter
  used in training / evaluation (whitelisted observation, 11 maneuvers, 0.4 s refractory, seeded stochastic sampling).

The world, physics, lifecycle, brain and recorder are the unchanged runtime. The launcher only chooses which policy
object the `Session` receives, hides the neural HUD (its diagnostics differ by policy class), ends the session after
a fixed amount of active play and collects metrics from the unchanged tick events.

Blinding and randomisation (preregistered in `game/learning/m2_4_b/protocol.json`):

- 30 sessions = 15 blocks of 2. Each block contains one A and one B session with the SAME world seed, in an order
  derived from a secret key: order(block) = 'AB' if HMAC-SHA256(key, 'block:%d') first byte is even, else 'BA'.
  The longest possible run of one policy is 2.
- The public manifest (`game/learning/m2_4_b/randomization_manifest.json`) holds the seeds, sha256(key) and per-session
  commitments sha256(key | session | policy). The key stays in `artifacts/m2_4_b/blind_key.json` (git-ignored) until
  all sessions are complete. Publishing it later lets anyone regenerate and verify every assignment.
- The player is told the policy of a session only after that session's ratings are saved.

Private outputs (git-ignored, under artifacts/m2_4_b/): the key, per-session results with ratings, and the recordings.

    python tools/m2_4_b_blind_ab.py manifest     (one-time; creates the key and the public manifest)
    python tools/m2_4_b_blind_ab.py play         (plays the next unplayed session; asks for ratings; then reveals)
    python tools/m2_4_b_blind_ab.py status       (progress only; never shows assignments)
    python tools/m2_4_b_blind_ab.py analyze      (after all sessions; refuses a partial set)
    python tools/m2_4_b_blind_ab.py smoke        (headless check of both policy paths; does not touch the manifest)
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRACK = ROOT / 'game/learning/m2_4_b'
MANIFEST = TRACK / 'randomization_manifest.json'
PROTOCOL = TRACK / 'protocol.json'
PRIVATE = ROOT / 'artifacts/m2_4_b'
KEY_FILE = PRIVATE / 'blind_key.json'
SESSIONS = PRIVATE / 'sessions'
RECORDINGS = PRIVATE / 'recordings'
CANDIDATE_NPZ = ROOT / 'game/learning/checkpoints/m2_4_a_candidate.npz'
CANDIDATE_PARAM_SHA256 = '0692117af68e9a3d93ed0b2a966c9ab103c5b1d80f6a9f3cf2df900b555e2e66'
CANDIDATE_STATE_DICT_SHA256 = 'a8f78d393e7554e8a83c164279a055e85873ff0bfc80926da8edebafde8f84a6'
POLICIES = {'A': 'N4B1C (accepted runtime policy)', 'B': 'M2.4-A learned candidate (seed_2/ckpt_it060)'}
N_BLOCKS = 15
ACTIVE_SECONDS = 180.0          # fixed amount of play with a live fly per session
MIN_COMPLETE_FRACTION = 0.9     # below this the attempt is incomplete and the same session is replayed
STALL_SECONDS = 2.0             # airborne stall: AIRBORNE / LAND_APPROACH below 5 % of cruise speed for >= 2 s
LONG_PERCH_SECONDS = 60.0

RATINGS = [
    ('difficulty', 'How difficult was the fly to hit?  (1 = very easy ... 7 = very hard)'),
    ('naturalness', 'How natural did the fly\'s movement look?  (1 = very unnatural ... 7 = very natural)'),
    ('responsiveness', 'Did the fly appear to react to your swatter?  (1 = not at all ... 7 = clearly)'),
    ('twitchiness', 'Did the fly look overly random / twitchy?  (1 = not at all ... 7 = very; higher = worse)'),
    ('needless_escaping', 'Did the fly look like it was constantly escaping for no reason?  (1 = never ... 7 = constantly; '
                          'higher = worse)'),
]


# ----------------------------------------------------------------- randomisation ---
def _order(key: bytes, block: int) -> str:
    return 'AB' if hmac.new(key, b'block:%d' % block, hashlib.sha256).digest()[0] % 2 == 0 else 'BA'


def _commit(key: bytes, session: int, policy: str) -> str:
    return hashlib.sha256(key + b'|session:%d|policy:%s' % (session, policy.encode())).hexdigest()


def _world_seed(block: int) -> int:
    # Public and fixed; disjoint from every M2 TRAIN / EVAL seed range (TRAIN 20M-30M, EVAL 3.1M-3.99M).
    return 41_000_000 + 1000 * block


def assignments(key: bytes):
    out = []
    for b in range(1, N_BLOCKS + 1):
        for j, pol in enumerate(_order(key, b)):
            out.append({'session': 2 * (b - 1) + j + 1, 'block': b, 'position_in_block': j + 1, 'policy': pol,
                        'world_seed': _world_seed(b)})
    return out


def make_manifest():
    if MANIFEST.exists() or KEY_FILE.exists():
        raise SystemExit('manifest / key already exist; the randomisation is never regenerated')
    PRIVATE.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    KEY_FILE.write_text(json.dumps({'key_hex': key.hex(), 'note': 'Do not open until all sessions are complete.'}) + '\n',
                        encoding='utf-8')
    rows = assignments(key)
    TRACK.mkdir(parents=True, exist_ok=True)
    man = {'label': 'M2.4-B blind A/B randomisation manifest (public; assignments hidden by commitments)',
           'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'design': '%d blocks x 2 sessions; one A and one B per block, same world seed within a block; order from '
                     'HMAC-SHA256(key, "block:<b>") first byte parity (even -> AB, odd -> BA)' % N_BLOCKS,
           'key_sha256': hashlib.sha256(key).hexdigest(),
           'policies': POLICIES,
           'sessions': [{'session': r['session'], 'block': r['block'], 'position_in_block': r['position_in_block'],
                         'world_seed': r['world_seed'],
                         'commitment_A': _commit(key, r['session'], 'A') if r['policy'] == 'A' else None,
                         'commitment_B': _commit(key, r['session'], 'B') if r['policy'] == 'B' else None}
                        for r in rows]}
    # Hide which commitment slot is filled: publish one commitment per session, in a neutral field.
    for s, r in zip(man['sessions'], rows):
        s['commitment'] = _commit(key, r['session'], r['policy'])
        del s['commitment_A'], s['commitment_B']
    MANIFEST.write_text(json.dumps(man, indent=1) + '\n', encoding='utf-8')
    print('manifest written:', MANIFEST.relative_to(ROOT), 'sha256', hashlib.sha256(MANIFEST.read_bytes()).hexdigest())
    print('private key written to', KEY_FILE.relative_to(ROOT), '(git-ignored; do not open before the end)')


def load_key_and_rows():
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    key = bytes.fromhex(json.loads(KEY_FILE.read_text(encoding='utf-8'))['key_hex'])
    if hashlib.sha256(key).hexdigest() != man['key_sha256']:
        raise SystemExit('blind key does not match the public manifest')
    rows = assignments(key)
    for s, r in zip(man['sessions'], rows):
        if s['commitment'] != _commit(key, r['session'], r['policy']) or s['world_seed'] != r['world_seed']:
            raise SystemExit('manifest commitment mismatch at session %d' % r['session'])
    return man, key, rows


def completed_sessions():
    done = {}
    for f in sorted(SESSIONS.glob('session_*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        if d.get('complete') and d.get('ratings') is not None:
            done[d['session']] = d
    return done


# ----------------------------------------------------------------- policies ---
def build_learned_policy(config, seed):
    from game.learning.model import MLPPolicyModel
    from game.learning.policies import ManeuverPolicy, ModelDecision
    model = MLPPolicyModel.load(CANDIDATE_NPZ, expected_sha256=CANDIDATE_PARAM_SHA256)
    return ManeuverPolicy(ModelDecision(model, stochastic=True), float(config['sim']['tick_seconds']),
                          float(config['policy']['refractory_seconds']), seed=seed)


# ----------------------------------------------------------------- metrics ---
class SessionMetrics:
    """Objective per-session metrics from the unchanged tick events (read-only; never fed to a policy)."""

    def __init__(self, session, target_seconds):
        from game.learning.metrics import NEAR, STRIKE_PHASES, category
        self.NEAR, self.PHASES, self.category = NEAR, STRIKE_PHASES, category
        self.s = session
        self.target = target_seconds
        self.tick_s = session.tick_seconds
        self.active_ticks = self.total_ticks = 0
        self.strikes, self.open = [], None
        self.escapes = self.unnecessary = self.wall_contacts = self.perches = 0
        self.takeoffs = {'TAKEOFF_ESCAPE': 0, 'TAKEOFF_VOLUNTARY': 0}
        self.deaths = self.untracked_hits = 0
        self.world_escape_events = 0
        self.stalls = self.long_perches = 0
        self.stall_run = self.perch_run = 0
        self.mode_ticks, self.actions = {}, {}
        self.prev_contact = False
        self.done = False
        self._orig = session.tick
        session.tick = self.tick

    def _committed(self):
        return self.s.world.swatter.phase.value in self.PHASES

    def tick(self, *a, **k):
        w = self.s.world
        alive = w.fly.alive
        committed_before = self._committed()
        horizontal = math.hypot(w.swatter.x - w.fly.x, w.swatter.y - w.fly.y)
        mode_before = None if w.lifecycle is None else w.lifecycle.mode
        ev = self._orig(*a, **k)
        self.total_ticks += 1
        committed_after = self._committed()
        t = self.active_ticks * self.tick_s
        if not committed_before and committed_after:
            self.open = {'start_s': t, 'first_escape_latency_s': None, 'hit': False, 'resolved': False}
            self.strikes.append(self.open)
        if alive:
            self.active_ticks += 1
            act = self.s.fly_loop.last_action
            c = self.category(act)
            self.actions[c] = self.actions.get(c, 0) + 1
            if act.escape and act.strength > 0:
                self.escapes += 1
                if not committed_before and horizontal > self.NEAR:
                    self.unnecessary += 1
                if self.open is not None and not self.open['resolved'] and self.open['first_escape_latency_s'] is None:
                    self.open['first_escape_latency_s'] = t - self.open['start_s']
            contact = bool(w.wall_contact or w.object_contact)
            if contact and not self.prev_contact:
                self.wall_contacts += 1
            self.prev_contact = contact
            mode_after = None if w.lifecycle is None else w.lifecycle.mode
            if mode_after is not None:
                self.mode_ticks[mode_after] = self.mode_ticks.get(mode_after, 0) + 1
                if mode_before != 'TOUCHDOWN' and mode_after == 'TOUCHDOWN':
                    self.perches += 1
                if mode_after in self.takeoffs and mode_before != mode_after:
                    self.takeoffs[mode_after] += 1
                slow = math.hypot(w.fly.vx, w.fly.vy) < 0.05 * w.baseline_speed
                self.stall_run = self.stall_run + 1 if (mode_after in ('AIRBORNE', 'LAND_APPROACH') and slow) else 0
                if self.stall_run == round(STALL_SECONDS / self.tick_s):
                    self.stalls += 1
                self.perch_run = self.perch_run + 1 if mode_after in ('TOUCHDOWN', 'PERCHED') else 0
                if self.perch_run == round(LONG_PERCH_SECONDS / self.tick_s):
                    self.long_perches += 1
        if ev.escaped:
            self.world_escape_events += 1
        if ev.hit:
            if self.open is not None and not self.open['resolved']:
                self.open.update(hit=True, resolved=True, resolved_s=t)
            else:
                self.untracked_hits += 1
        elif ev.strike_resolved and self.open is not None and not self.open['resolved']:
            self.open.update(resolved=True, resolved_s=t)
        if alive and not w.fly.alive:
            self.deaths += 1
        if self.active_ticks * self.tick_s >= self.target and not self.done:
            self.done = True
            import pygame
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        return ev

    def restart(self):
        if self.open is not None and not self.open['resolved']:
            self.open['abandoned_by_restart'] = True
        self.open = None
        self.stall_run = self.perch_run = 0
        self.prev_contact = False

    def summary(self):
        res = [x for x in self.strikes if x['resolved']]
        hits = sum(x['hit'] for x in res)
        esc_success = sum(1 for x in res if not x['hit'] and x['first_escape_latency_s'] is not None)
        lat = sorted(x['first_escape_latency_s'] for x in res if x['first_escape_latency_s'] is not None)
        minutes = self.active_ticks * self.tick_s / 60
        n = sum(self.actions.values()) or 1
        return {'active_seconds': self.active_ticks * self.tick_s, 'total_ticks': self.total_ticks,
                'committed_strikes': len(self.strikes), 'resolved_strikes': len(res), 'hits': hits,
                'hit_rate_per_resolved_strike': hits / len(res) if res else None,
                'successful_escapes': esc_success, 'escape_success_per_resolved_strike': esc_success / len(res) if res else None,
                'strikes_with_escape': sum(1 for x in res if x['first_escape_latency_s'] is not None),
                'escape_latency_s_median': lat[len(lat) // 2] if lat else None, 'escape_latencies_s': lat,
                'escapes': self.escapes, 'unnecessary_escapes': self.unnecessary,
                'unnecessary_escapes_per_min': self.unnecessary / minutes if minutes else None,
                'wall_contacts': self.wall_contacts, 'wall_contacts_per_min': self.wall_contacts / minutes if minutes else None,
                'perch_events': self.perches, 'perches_per_min': self.perches / minutes if minutes else None,
                'takeoffs': self.takeoffs, 'deaths': self.deaths, 'untracked_hits': self.untracked_hits,
                'world_escape_events': self.world_escape_events,
                'lifecycle_failures': {'airborne_stalls_ge_2s': self.stalls, 'perch_bouts_ge_60s': self.long_perches},
                'lifecycle_mode_fraction': {k: v / (self.active_ticks or 1) for k, v in sorted(self.mode_ticks.items())},
                'action_distribution': {k: v / n for k, v in sorted(self.actions.items())}, 'action_counts': self.actions}


# ----------------------------------------------------------------- play ---
def run_game(policy_letter, world_seed, record_dir, headless_seconds=None):
    """One session of the unchanged ROOM game with the chosen policy. Returns (metrics, recording path, error)."""
    if headless_seconds is not None:
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    import pygame
    import game.app as app_module
    from game.session import load_config
    from game.session_recording import HumanSessionRecorder
    config_path = ROOT / 'game_room_config.json'
    config = load_config(config_path)
    policy = build_learned_policy(config, world_seed + 104_729) if policy_letter == 'B' else None
    original_session = app_module.Session

    def session_factory(cfg, **kw):
        return original_session(cfg, policy=policy, **kw) if policy is not None else original_session(cfg, **kw)

    class BlindApp(app_module.App):
        # The neural HUD shows policy-class-specific diagnostics; it stays off for the blind test.
        show_neural = property(lambda self: False, lambda self, value: None)

        def _restart(self):
            self._metrics.restart()
            super()._restart()

    recorder = HumanSessionRecorder(record_dir, config_file=config_path) if record_dir is not None else None
    app = None
    err = None
    app_module.Session = session_factory
    try:
        app = BlindApp(config, fullscreen=headless_seconds is None, seed=world_seed, mode='play', recorder=recorder,
                       ecology_enabled=None)
        app._metrics = SessionMetrics(app.session, ACTIVE_SECONDS if headless_seconds is None else headless_seconds)
        app.show_neural = True                      # the H key does this; it must have no effect
        run_game.last_check = {'policy_class': type(app.session.policy).__name__, 'neural_hud_visible': app.show_neural}
        app.run(max_seconds=None if headless_seconds is None else headless_seconds * 4)
    except Exception as e:      # an infrastructure failure is recorded, never hidden
        err = '%s: %s' % (type(e).__name__, e)
    finally:
        app_module.Session = original_session
        if app is not None and getattr(app, 'session', None) is not None:
            app.session.close()
        pygame.quit()
    metrics = app._metrics.summary() if app is not None and hasattr(app, '_metrics') else None
    path = None if recorder is None else str(Path(recorder.path).relative_to(ROOT)).replace('\\', '/')
    return metrics, path, err


def ask_int(prompt):
    while True:
        v = input('  %s\n  > ' % prompt).strip()
        if v in {'1', '2', '3', '4', '5', '6', '7'}:
            return int(v)
        print('  Please enter a whole number from 1 to 7.')


def ask_ratings():
    print('\nRatings for this session (the policy identity is revealed only after they are saved).\n')
    r = {k: ask_int(q) for k, q in RATINGS}
    while True:
        v = input('  Did anything look broken, stuck or exploitable?  (y / n)\n  > ').strip().lower()
        if v in ('y', 'n'):
            r['broken_or_exploitable'] = v == 'y'
            break
    r['note'] = input('  Optional short note (press Enter to skip)\n  > ').strip()
    return r


def play():
    man, key, rows = load_key_and_rows()
    SESSIONS.mkdir(parents=True, exist_ok=True)
    RECORDINGS.mkdir(parents=True, exist_ok=True)
    while True:
        done = completed_sessions()
        nxt = next((r for r in rows if r['session'] not in done), None)
        if nxt is None:
            print('All %d sessions are complete. Run:  python tools/m2_4_b_blind_ab.py analyze' % len(rows))
            return
        attempts = sorted(SESSIONS.glob('session_%02d_attempt_*.json' % nxt['session']))
        attempt = len(attempts) + 1
        print('\n=== Blind session %d of %d (block %d, attempt %d) ===' % (nxt['session'], len(rows), nxt['block'], attempt))
        print('Play normally. The session ends by itself after %.0f s of play with a live fly '
              '(R restarts after a splat; Esc leaves fullscreen / quits early).' % ACTIVE_SECONDS)
        input('Press Enter to start ...')
        t0 = time.time()
        metrics, rec, err = run_game(nxt['policy'], nxt['world_seed'], RECORDINGS)
        complete = err is None and metrics is not None and metrics['active_seconds'] >= MIN_COMPLETE_FRACTION * ACTIVE_SECONDS
        base = {'session': nxt['session'], 'block': nxt['block'], 'position_in_block': nxt['position_in_block'],
                'world_seed': nxt['world_seed'], 'attempt': attempt, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t0)),
                'wall_seconds': time.time() - t0, 'recording': rec, 'error': err, 'complete': complete,
                'metrics': metrics, 'policy': nxt['policy'], 'policy_label': POLICIES[nxt['policy']],
                'commitment': _commit(key, nxt['session'], nxt['policy']),
                'candidate_param_sha256': CANDIDATE_PARAM_SHA256 if nxt['policy'] == 'B' else None}
        if not complete:
            (SESSIONS / ('session_%02d_attempt_%d.json' % (nxt['session'], attempt))).write_text(
                json.dumps(dict(base, ratings=None), indent=1, default=float) + '\n', encoding='utf-8')
            print('\nSession ended early (%s). It was NOT counted; the same session will be offered again. '
                  'No policy identity is shown.' % (err or '%.0f s of %.0f s played' % ((metrics or {}).get('active_seconds', 0), ACTIVE_SECONDS)))
        else:
            ratings = ask_ratings()
            out = dict(base, ratings=ratings, ratings_saved_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            (SESSIONS / ('session_%02d.json' % nxt['session'])).write_text(json.dumps(out, indent=1, default=float) + '\n',
                                                                            encoding='utf-8')
            print('\nRatings saved.')
            print('This session\'s fly was policy %s: %s' % (nxt['policy'], POLICIES[nxt['policy']]))
            print('(strikes %d, hits %d)' % (metrics['committed_strikes'], metrics['hits']))
        if input('\nContinue with the next session? (y / n)\n> ').strip().lower() != 'y':
            print('Stopped. Re-run the same command to continue with the next unplayed session.')
            return


def status():
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    done = completed_sessions() if SESSIONS.exists() else {}
    inc = len(list(SESSIONS.glob('session_*_attempt_*.json'))) if SESSIONS.exists() else 0
    print('completed %d of %d sessions; incomplete attempts %d; next session %s' % (
        len(done), len(man['sessions']), inc, next((s['session'] for s in man['sessions'] if s['session'] not in done), None)))


def smoke(seconds=4.0):
    """Headless check that both policy paths run and produce metrics (no manifest, no recording, no ratings)."""
    for letter in ('A', 'B'):
        m, rec, err = run_game(letter, 41_999_999, None, headless_seconds=seconds)
        chk = getattr(run_game, 'last_check', {})
        print('smoke', letter, 'error', err, 'active_s', None if m is None else round(m['active_seconds'], 2),
              'ticks', None if m is None else m['total_ticks'], chk)
        want = 'ManeuverPolicy' if letter == 'B' else 'FixedEscapePolicy'
        if err or m is None or m['total_ticks'] == 0 or chk.get('policy_class') != want or chk.get('neural_hud_visible'):
            raise SystemExit('smoke failed for policy %s' % letter)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', nargs='?', default='play', choices=('manifest', 'play', 'status', 'analyze', 'smoke'))
    a = ap.parse_args()
    if a.mode == 'analyze':
        import importlib.util
        spec = importlib.util.spec_from_file_location('m2_4_b_analyze', ROOT / 'tools/m2_4_b_analyze.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
    else:
        {'manifest': make_manifest, 'play': play, 'status': status, 'smoke': smoke}[a.mode]()
