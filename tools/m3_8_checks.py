"""M3.8 checks P1, P2, P5, P6 and descriptives D1, D3 (game/M3_8_SACCADE_ODOR_DESIGN.md).

These are the M3.7 tools with M3.8's fresh seeds, output directory and arms. The measurements
are unchanged:
- **P1, P2, P5, D1** come from `tools/m3_7_saccades.py`:
  - protocol S on seeds 973001-973020;
  - protocol E on seeds 973301-973324.
- **P6, D3** come from `tools/m3_7_encounters.py`, on seeds 973401-973440.

P3 uses `tools/kinematics_sanity.py`, and P4 `tools/paired_free_flight_check.py` (seeds
973201-973280), both unchanged; see the design note for the commands.

**Arms.**
- **baseline.** v27 at commit 7483e51.
- **candidate.** The working ROOM configuration (v32) for protocols S and E; for the P6 runs, the
  commit given with `--candidate-commit`.

    NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py protocol-s --arm candidate --lane 0 --lanes 2
    NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py protocol-e --arm baseline
    NUMBA_NUM_THREADS=1 python tools/m3_8_checks.py encounters --arm candidate --candidate-commit SHA --lane 0 --lanes 2
    python tools/m3_8_checks.py summary --candidate-commit SHA
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from game.session import load_config  # noqa: E402
import tools.m3_7_encounters as E  # noqa: E402
import tools.m3_7_saccades as S  # noqa: E402

OUT = ROOT / 'artifacts/m3_8'
P6_TOLERANCE = 0.05


def configure(candidate_commit=None):
    S.OUT = OUT
    S.S_SEEDS = tuple(range(973001, 973021))
    S.E_SEEDS = tuple(range(973301, 973325))

    baseline = S.arm_config

    def arm_config(arm):
        if arm == 'baseline':
            return baseline('baseline')
        c = load_config(ROOT / 'game_room_config.json')
        assert c['config_version'] == 32, 'the working ROOM configuration is not the M3.8 candidate'
        return c
    S.arm_config = arm_config
    E.OUT = OUT / 'encounters'
    E.SEEDS = tuple(range(973401, 973441))
    E.COMMITS = {'baseline': '7483e51', 'candidate': candidate_commit or 'unset'}


def p6():
    summary = json.loads((OUT / 'encounters' / 'summary.json').read_text(encoding='utf-8'))
    base = summary['baseline']['odor_track_upwind_share']
    cand = summary['candidate']['odor_track_upwind_share']
    ok = cand >= base - P6_TOLERANCE
    print('P6: ODOR_TRACK upwind share baseline %.3f, candidate %.3f (pass if >= %.3f): %s' % (
        base, cand, base - P6_TOLERANCE, 'pass' if ok else 'FAIL'))
    return {'baseline': base, 'candidate': cand, 'pass': ok}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('mode', choices=('protocol-s', 'protocol-e', 'encounters', 'summary'))
    parser.add_argument('--arm', choices=S.ARMS)
    parser.add_argument('--candidate-commit')
    parser.add_argument('--lane', type=int, default=0)
    parser.add_argument('--lanes', type=int, default=1)
    args = parser.parse_args()
    configure(args.candidate_commit)
    if args.mode == 'protocol-s':
        S.protocol_s(args)
    elif args.mode == 'protocol-e':
        S.protocol_e(args)
    elif args.mode == 'encounters':
        if args.arm == 'candidate' and not args.candidate_commit:
            parser.error('the candidate encounter runs need --candidate-commit')
        E.run(args)
    else:
        S.summary(args)
        E.summary(args)
        result = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
        result['P6'] = p6()
        (OUT / 'summary.json').write_text(json.dumps(result, indent=1) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
