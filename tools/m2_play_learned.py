"""Play the ROOM game against the frozen M2.2 learned policy (research launcher; human test only).

The accepted runtime is not modified and its default policy stays FixedEscapePolicy. This
launcher only substitutes the policy object that `game.app.App` passes to its `Session`: the
frozen learned candidate, wrapped in the same `ManeuverPolicy` adapter used in training and
evaluation (whitelisted observation, 11 maneuvers, 0.4 s refractory, seeded stochastic
sampling). World physics, flight, walls, lifecycle and brain stepping are unchanged.

    python tools/m2_play_learned.py --arena room --record --record-dir results/game/sessions
    python tools/m2_play_learned.py --smoke 3 --no-record        (headless check)

All other arguments are passed to `game.app` unchanged. Note: a recording made here cannot be
verified by `game.replay`, which rebuilds the accepted FixedEscapePolicy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main(argv=None):
    import game.app as app_module
    from game.learning.model import MLPPolicyModel
    from game.learning.policies import ManeuverPolicy, ModelDecision
    from game.session import load_config

    argv = list(sys.argv[1:] if argv is None else argv)
    ckpt = ROOT / 'game/learning/checkpoints/m2_2_candidate.npz'
    record_file = ROOT / 'game/learning/m2_2_candidate.json'
    if '--checkpoint' in argv:
        i = argv.index('--checkpoint')
        ckpt = Path(argv[i + 1])
        del argv[i:i + 2]
        expected = None
    else:
        expected = json.loads(record_file.read_text(encoding='utf-8'))['checkpoint_sha256']
    model = MLPPolicyModel.load(ckpt, expected_sha256=expected)
    config = load_config(ROOT / 'game_room_config.json')
    policy = ManeuverPolicy(ModelDecision(model, stochastic=True), float(config['sim']['tick_seconds']),
                            float(config['policy']['refractory_seconds']), seed=20260926)
    print('M2.2 learned policy: checkpoint %s (parameter sha256 %s, file sha256 %s)' % (
        ckpt.name, model.param_hash(), hashlib.sha256(ckpt.read_bytes()).hexdigest()), flush=True)
    original = app_module.Session

    def session_with_learned_policy(cfg, **kw):
        return original(cfg, policy=policy, **kw)
    app_module.Session = session_with_learned_policy
    try:
        return app_module.main(argv)
    finally:
        app_module.Session = original


if __name__ == '__main__':
    sys.exit(main())
