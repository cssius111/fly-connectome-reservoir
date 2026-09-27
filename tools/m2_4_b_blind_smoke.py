"""M2.4-B blinding smoke test (sandbox only; synthetic key; never the real manifest or real human responses).

Runs the real launcher as a subprocess, exactly as a player would, against a throw-away sandbox, and checks:

1. session 1 completes (headless, a few seconds of active play);
2. ratings can be saved (scripted SYNTHETIC test inputs, stored only in the sandbox);
3. the assignment stays hidden afterwards: the console shows "Response saved. Policy identity remains blinded." and
   no identity token; the session file holds only the commitment;
4. beginning session 2 reveals neither session's identity;
5. the assignment is not available through the HUD (H key injected; the neural HUD stays off; the window caption
   is neutral) or through normal console output (stdout / stderr of every command scanned for identity tokens);
6. `reveal` refuses before 30 completed sessions;
7. `reveal` succeeds only on a synthetic fully completed sandbox (30 synthetic session files) and decodes exactly
   the key's assignments after verifying every commitment; `play` then refuses.

    python tools/m2_4_b_blind_smoke.py
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = ROOT / 'tools/m2_4_b_blind_ab.py'
PY = sys.executable
FORBIDDEN = ['N4B1C', 'FixedEscapePolicy', 'ManeuverPolicy', 'learned', 'Learned', 'baseline', 'Baseline', 'checkpoint',
             'Checkpoint', 'candidate', 'Candidate', '.npz', 'M2.4-A', 'm2_4_a', 'policy A', 'policy B', 'Policy A',
             'Policy B', 'seed_2', 'ckpt']
STANDALONE_AB = re.compile(r'(?<![A-Za-z0-9_])[AB](?![A-Za-z0-9_])')


def run(args, stdin=''):
    p = subprocess.run([PY, '-W', 'ignore', str(LAUNCHER)] + args, input=stdin, capture_output=True, text=True,
                       cwd=str(ROOT), timeout=1800)
    return p.returncode, p.stdout + p.stderr


def leaks(text):
    found = [t for t in FORBIDDEN if t in text]
    found += ['standalone "%s"' % m.group(0) for m in STANDALONE_AB.finditer(text)]
    return found


def load_module(sandbox):
    spec = importlib.util.spec_from_file_location('m2_4_b_blind_ab_smoke', LAUNCHER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.configure_sandbox(sandbox)
    return m


def main():
    results = {}
    tmp = Path(tempfile.mkdtemp(prefix='m2_4_b_blind_smoke_'))
    try:
        sb1 = tmp / 'sandbox_partial'
        rc, out = run(['manifest', '--sandbox', str(sb1)])
        assert rc == 0, out
        # Session 1 and session 2 with scripted synthetic inputs: Enter, 5 ratings, n, empty note, continue y / n.
        rating_block = '\n4\n4\n4\n4\n4\nn\n\n'
        rc, out = run(['play', '--sandbox', str(sb1), '--headless-seconds', '3'], stdin=rating_block + 'y\n' + rating_block + 'n\n')
        s1 = sb1 / 'private/sessions/session_01.json'
        s2 = sb1 / 'private/sessions/session_02.json'
        d1 = json.loads(s1.read_text(encoding='utf-8')) if s1.exists() else {}
        d2 = json.loads(s2.read_text(encoding='utf-8')) if s2.exists() else {}
        results['1_session_1_completes'] = rc == 0 and bool(d1.get('complete'))
        results['2_ratings_saved'] = d1.get('ratings') is not None and d2.get('ratings') is not None
        file_text = s1.read_text(encoding='utf-8') + s2.read_text(encoding='utf-8') if s1.exists() and s2.exists() else ''
        results['3_hidden_after_save'] = (out.count('Response saved. Policy identity remains blinded.') == 2
                                          and not leaks(out) and 'policy' not in d1 and 'policy' not in d2
                                          and not [t for t in FORBIDDEN if t in file_text])
        results['4_session_2_start_reveals_nothing'] = 'Session 02 / 30' in out and 'Session 01 / 30' in out and not leaks(out)
        audits = [d1.get('blind_audit', {}), d2.get('blind_audit', {})]
        results['5_not_via_hud_or_console'] = (all(a.get('h_key_injected') and a.get('neural_hud_visible_at_end') is False
                                                   and a.get('window_caption') == 'MaleCNS fly-swatter' for a in audits)
                                               and not leaks(out))
        rc_s, out_s = run(['status', '--sandbox', str(sb1)])
        rc_r, out_r = run(['reveal', '--sandbox', str(sb1)])
        results['5b_status_output_neutral'] = rc_s == 0 and not leaks(out_s)
        results['6_reveal_refuses_before_30'] = rc_r != 0 and 'Reveal refused: 2 / 30' in out_r and not leaks(out_r)
        results['console_leak_tokens'] = leaks(out + out_s + out_r)

        # 7. synthetic fully completed sandbox
        sb2 = tmp / 'sandbox_complete'
        rc, out = run(['manifest', '--sandbox', str(sb2)])
        assert rc == 0, out
        m = load_module(sb2)
        man, key, rows = m.load_key_and_rows()
        m.SESSIONS.mkdir(parents=True, exist_ok=True)
        for r, ms in zip(rows, man['sessions']):
            (m.SESSIONS / ('session_%02d.json' % r['session'])).write_text(json.dumps({
                'session': r['session'], 'block': r['block'], 'position_in_block': r['position_in_block'],
                'world_seed': r['world_seed'], 'complete': True, 'commitment': ms['commitment'],
                'ratings': {'synthetic_test_fixture': True}, 'metrics': None, 'synthetic_test_session': True}) + '\n',
                encoding='utf-8')
        rc7, out7 = run(['reveal', '--sandbox', str(sb2)])
        rev = json.loads((sb2 / 'private/reveal.json').read_text(encoding='utf-8')) if (sb2 / 'private/reveal.json').exists() else {}
        decoded = [(x['session'], x['policy']) for x in rev.get('sessions', [])]
        expect = [(r['session'], r['policy']) for r in rows]
        rc_p, out_p = run(['play', '--sandbox', str(sb2)])
        results['7_reveal_succeeds_only_when_complete'] = (rc7 == 0 and rev.get('all_commitments_verified') is True
                                                           and decoded == expect and (sb2 / 'private/ratings_lock.json').exists()
                                                           and rc_p != 0 and 'locked' in out_p)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    ok = all(v for k, v in results.items() if k != 'console_leak_tokens') and not results['console_leak_tokens']
    for k, v in results.items():
        print('%-40s %s' % (k, v))
    print('ALL PASS' if ok else 'FAILED')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
