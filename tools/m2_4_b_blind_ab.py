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
- Amendment 1 (before any session): policy identity is NOT revealed after individual sessions. Each block holds one
  A and one B, so revealing one session would reveal its partner, and per-session feedback lets the player learn
  behavioural signatures. Identity stays hidden until all 30 sessions are rated; `reveal` then locks the ratings
  (hashes + read-only), verifies the key and every commitment and decodes the assignments.
- Player-visible output is neutral ("Session 07 / 30"). Everything the game process writes to stdout / stderr
  (including warnings and error text) goes to a private per-attempt log; session files store only the commitment,
  never the policy.

Private outputs (git-ignored, under artifacts/m2_4_b/): the key, per-session results with ratings, logs, recordings,
the ratings lock and the reveal record.

    python tools/m2_4_b_blind_ab.py manifest     (one-time; creates the key and the public manifest)
    python tools/m2_4_b_blind_ab.py play         (next unplayed session; ratings; "Response saved. Policy identity
                                                  remains blinded."; asks whether to continue)
    python tools/m2_4_b_blind_ab.py status       (progress only; never shows assignments)
    python tools/m2_4_b_blind_ab.py reveal       (only after 30 / 30 rated sessions: lock, verify, decode)
    python tools/m2_4_b_blind_ab.py analyze      (after reveal; refuses a partial set)
    python tools/m2_4_b_blind_ab.py smoke        (headless check of both policy paths; does not touch the manifest)

Test-only options: --sandbox DIR relocates the manifest and every private file to DIR (synthetic key; never the real
manifest); --headless-seconds S (sandbox only) runs sessions headless for S seconds of active play.
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
LOGS = PRIVATE / 'logs'
LOCK_FILE = PRIVATE / 'ratings_lock.json'
REVEAL_FILE = PRIVATE / 'reveal.json'
HEADLESS_SECONDS = None
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
    print('manifest written:', MANIFEST, 'sha256', hashlib.sha256(MANIFEST.read_bytes()).hexdigest())
    print('private key written to', KEY_FILE, '(git-ignored; do not open before the end)')


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
class _PrivateOutput:
    """Send everything written to stdout / stderr (Python and C level) to a private log while the game runs."""

    def __init__(self, path):
        self.path = Path(path)

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        sys.stdout.flush()
        sys.stderr.flush()
        self.f = open(self.path, 'a', encoding='utf-8')
        self.saved = (os.dup(1), os.dup(2), sys.stdout, sys.stderr)
        os.dup2(self.f.fileno(), 1)
        os.dup2(self.f.fileno(), 2)
        sys.stdout = sys.stderr = self.f
        return self

    def __exit__(self, *exc):
        if exc[0] is not None:
            import traceback
            traceback.print_exception(*exc, file=self.f)
        self.f.flush()
        d1, d2, so, se = self.saved
        os.dup2(d1, 1)
        os.dup2(d2, 2)
        os.close(d1)
        os.close(d2)
        sys.stdout, sys.stderr = so, se
        self.f.close()
        return True             # never propagate: an error message could name the policy


def run_game(policy_letter, world_seed, record_dir, active_seconds=ACTIVE_SECONDS, headless=False, press_h=False):
    """One session of the unchanged ROOM game with the chosen policy.

    Returns (metrics, recording path, error text, blind audit). Must be called inside _PrivateOutput for real play."""
    if headless:
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
        # The neural HUD shows policy-class-specific diagnostics; it stays off for the whole blind test. Assignments
        # from the H key (or anything else) are ignored.
        show_neural = property(lambda self: False, lambda self, value: None)

        def _restart(self):
            self._metrics.restart()
            super()._restart()

    recorder = HumanSessionRecorder(record_dir, config_file=config_path) if record_dir is not None else None
    app, err, audit = None, None, {}
    app_module.Session = session_factory
    try:
        app = BlindApp(config, fullscreen=not headless, seed=world_seed, mode='play', recorder=recorder,
                       ecology_enabled=None)
        app._metrics = SessionMetrics(app.session, active_seconds)
        caption = pygame.display.get_caption()[0]
        if press_h:              # test only: the H key is the normal way to open the neural HUD
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h, scancode=pygame.KSCAN_H, mod=0,
                                                 unicode='h', repeat=False))
        app.run(max_seconds=None if not headless else active_seconds * 6 + 30)
        audit = {'window_caption': caption,
                 'neural_hud_visible_at_end': bool(app.show_neural), 'h_key_injected': press_h}
    except Exception as e:      # recorded privately, never shown to the player
        err = '%s: %s' % (type(e).__name__, e)
    finally:
        app_module.Session = original_session
        if app is not None and getattr(app, 'session', None) is not None:
            app.session.close()
        pygame.quit()
    metrics = app._metrics.summary() if app is not None and hasattr(app, '_metrics') else None
    path = None if recorder is None else str(Path(recorder.path)).replace('\\', '/')
    if app is not None:
        run_game.last_check = {'policy_class': type(app.session.policy).__name__, **audit}
    return metrics, path, err, audit


def ask_int(prompt):
    while True:
        v = input('  %s\n  > ' % prompt).strip()
        if v in {'1', '2', '3', '4', '5', '6', '7'}:
            return int(v)
        print('  Please enter a whole number from 1 to 7.')


def ask_ratings():
    print('\nPlease rate this session.\n')
    r = {k: ask_int(q) for k, q in RATINGS}
    while True:
        v = input('  Did anything look broken, stuck or exploitable?  (y / n)\n  > ').strip().lower()
        if v in ('y', 'n'):
            r['broken_or_exploitable'] = v == 'y'
            break
    r['note'] = input('  Optional short note (press Enter to skip)\n  > ').strip()
    return r


def _utc(t=None):
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(t))


def play():
    if LOCK_FILE.exists() or REVEAL_FILE.exists():
        raise SystemExit('The ratings are locked; no further sessions can be played.')
    man, key, rows = load_key_and_rows()
    for d in (SESSIONS, RECORDINGS, LOGS):
        d.mkdir(parents=True, exist_ok=True)
    total = len(rows)
    while True:
        done = completed_sessions()
        nxt = next((r for r in rows if r['session'] not in done), None)
        if nxt is None:
            print('All %d sessions are complete and rated. Next step:  python tools/m2_4_b_blind_ab.py reveal' % total)
            return
        attempt = len(list(SESSIONS.glob('session_%02d_attempt_*.json' % nxt['session']))) + 1
        label = 'Session %02d / %d' % (nxt['session'], total)
        print('\n=== %s%s ===' % (label, '' if attempt == 1 else '  (attempt %d)' % attempt))
        print('Play normally. The session ends by itself after %.0f s of play with a live fly.' % (
            HEADLESS_SECONDS or ACTIVE_SECONDS))
        print('R restarts after a splat. Esc leaves fullscreen; Esc again quits early (an early quit is not counted).')
        input('Press Enter to start ...')
        t0 = time.time()
        log = LOGS / ('session_%02d_attempt_%d.log' % (nxt['session'], attempt))
        result = [None, None, 'launcher error', {}]
        with _PrivateOutput(log):
            result = list(run_game(nxt['policy'], nxt['world_seed'], RECORDINGS,
                                   active_seconds=HEADLESS_SECONDS or ACTIVE_SECONDS, headless=HEADLESS_SECONDS is not None,
                                   press_h=HEADLESS_SECONDS is not None))
        metrics, rec, err, audit = result
        target = HEADLESS_SECONDS or ACTIVE_SECONDS
        complete = err is None and metrics is not None and metrics['active_seconds'] >= MIN_COMPLETE_FRACTION * target
        base = {'session': nxt['session'], 'block': nxt['block'], 'position_in_block': nxt['position_in_block'],
                'world_seed': nxt['world_seed'], 'attempt': attempt, 'started_utc': _utc(t0),
                'wall_seconds': time.time() - t0, 'active_seconds_target': target, 'recording': rec,
                'private_log': str(log).replace('\\', '/'), 'error': err, 'complete': complete, 'metrics': metrics,
                'commitment': man['sessions'][nxt['session'] - 1]['commitment'], 'blind_audit': audit,
                'synthetic_test_session': HEADLESS_SECONDS is not None}
        if not complete:
            (SESSIONS / ('session_%02d_attempt_%d.json' % (nxt['session'], attempt))).write_text(
                json.dumps(dict(base, ratings=None), indent=1, default=float) + '\n', encoding='utf-8')
            print('\nThe session ended before %.0f %% of the play time, or an error occurred (details were saved '
                  'privately). It is not counted and will be offered again.' % (100 * MIN_COMPLETE_FRACTION))
        else:
            ratings = ask_ratings()
            out = dict(base, ratings=ratings, ratings_saved_utc=_utc())
            f = SESSIONS / ('session_%02d.json' % nxt['session'])
            f.write_text(json.dumps(out, indent=1, default=float) + '\n', encoding='utf-8')
            print('\nResponse saved. Policy identity remains blinded.')
        if input('\nContinue with the next session? (y / n)\n> ').strip().lower() != 'y':
            print('Stopped. Run the same command again to continue with the next unplayed session.')
            return


def status():
    man = json.loads(MANIFEST.read_text(encoding='utf-8'))
    done = completed_sessions() if SESSIONS.exists() else {}
    inc = len(list(SESSIONS.glob('session_*_attempt_*.json'))) if SESSIONS.exists() else 0
    nxt = next((s['session'] for s in man['sessions'] if s['session'] not in done), None)
    print('Completed and rated: %d / %d sessions. Incomplete attempts: %d. Next: %s. Ratings locked: %s.' % (
        len(done), len(man['sessions']), inc, 'none' if nxt is None else 'Session %02d / %d' % (nxt, len(man['sessions'])),
        'yes' if LOCK_FILE.exists() else 'no'))


def reveal():
    """After 30 / 30 rated sessions: lock ratings, verify key and commitments, decode assignments."""
    man, key, rows = load_key_and_rows()
    done = completed_sessions() if SESSIONS.exists() else {}
    if len(done) != len(rows):
        raise SystemExit('Reveal refused: %d / %d sessions are complete and rated. Identity stays blinded until all '
                         'sessions are rated.' % (len(done), len(rows)))
    if not LOCK_FILE.exists():
        lock = {'label': 'M2.4-B ratings lock (written before any assignment was decoded)', 'locked_utc': _utc(),
                'files': {}}
        for r in rows:
            f = SESSIONS / ('session_%02d.json' % r['session'])
            lock['files'][f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
            os.chmod(f, 0o444)
        LOCK_FILE.write_text(json.dumps(lock, indent=1) + '\n', encoding='utf-8')
        os.chmod(LOCK_FILE, 0o444)
    lock = json.loads(LOCK_FILE.read_text(encoding='utf-8'))
    out = {'label': 'M2.4-B reveal record', 'revealed_utc': _utc(), 'key_hex': key.hex(),
           'key_sha256': hashlib.sha256(key).hexdigest(), 'manifest_key_sha256': man['key_sha256'],
           'ratings_lock_sha256': hashlib.sha256(LOCK_FILE.read_bytes()).hexdigest(), 'sessions': []}
    for r, m in zip(rows, man['sessions']):
        f = SESSIONS / ('session_%02d.json' % r['session'])
        if hashlib.sha256(f.read_bytes()).hexdigest() != lock['files'][f.name]:
            raise SystemExit('session file changed after the lock: %s' % f.name)
        d = done[r['session']]
        c = _commit(key, r['session'], r['policy'])
        if not (c == m['commitment'] == d['commitment']) or d['world_seed'] != r['world_seed']:
            raise SystemExit('commitment verification failed at session %d' % r['session'])
        out['sessions'].append({'session': r['session'], 'block': r['block'], 'position_in_block': r['position_in_block'],
                                'world_seed': r['world_seed'], 'policy': r['policy'], 'policy_label': POLICIES[r['policy']],
                                'commitment_verified': True})
    out['all_commitments_verified'] = True
    REVEAL_FILE.write_text(json.dumps(out, indent=1) + '\n', encoding='utf-8')
    print('Ratings locked (%d files). Key verified against the manifest. All %d commitments verified.' % (
        len(lock['files']), len(rows)))
    print('Assignments decoded to %s. Next step:  python tools/m2_4_b_blind_ab.py analyze' % REVEAL_FILE)


def smoke(seconds=4.0):
    """Developer check that both policy paths run and produce metrics (synthetic seed; no manifest, no recording)."""
    for letter in ('A', 'B'):
        m, rec, err, audit = run_game(letter, 41_999_999, None, active_seconds=seconds, headless=True, press_h=True)
        chk = getattr(run_game, 'last_check', {})
        print('smoke', letter, 'error', err, 'active_s', None if m is None else round(m['active_seconds'], 2),
              'ticks', None if m is None else m['total_ticks'], chk)
        want = 'ManeuverPolicy' if letter == 'B' else 'FixedEscapePolicy'
        if err or m is None or m['total_ticks'] == 0 or chk.get('policy_class') != want or chk.get('neural_hud_visible_at_end'):
            raise SystemExit('smoke failed for policy %s' % letter)


def configure_sandbox(d):
    global MANIFEST, PRIVATE, KEY_FILE, SESSIONS, RECORDINGS, LOGS, LOCK_FILE, REVEAL_FILE, TRACK
    d = Path(d).resolve()
    if d == ROOT or ROOT / 'game' in d.parents or d in (ROOT / 'artifacts/m2_4_b', ROOT / 'game/learning/m2_4_b'):
        raise SystemExit('the sandbox must be a separate test directory')
    TRACK = d
    MANIFEST = d / 'randomization_manifest.json'
    PRIVATE = d / 'private'
    KEY_FILE, SESSIONS, RECORDINGS, LOGS = PRIVATE / 'blind_key.json', PRIVATE / 'sessions', PRIVATE / 'recordings', PRIVATE / 'logs'
    LOCK_FILE, REVEAL_FILE = PRIVATE / 'ratings_lock.json', PRIVATE / 'reveal.json'


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', nargs='?', default='play', choices=('manifest', 'play', 'status', 'reveal', 'analyze', 'smoke'))
    ap.add_argument('--sandbox', type=Path, help='test only: relocate the manifest and private files')
    ap.add_argument('--headless-seconds', type=float, help='test only (requires --sandbox): headless sessions')
    a = ap.parse_args()
    if a.sandbox is not None:
        configure_sandbox(a.sandbox)
    if a.headless_seconds is not None:
        if a.sandbox is None:
            raise SystemExit('--headless-seconds is test-only and requires --sandbox')
        HEADLESS_SECONDS = a.headless_seconds
    if a.mode == 'analyze':
        import importlib.util
        spec = importlib.util.spec_from_file_location('m2_4_b_analyze', ROOT / 'tools/m2_4_b_analyze.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
    else:
        {'manifest': make_manifest, 'play': play, 'status': status, 'reveal': reveal, 'smoke': smoke}[a.mode]()
