"""tools/stop_rotation_audit.py: sample alignment, reversal spins and session selection.

The tool is read-only. These tests build small synthetic recordings in which the paddle stays
at a fixed position and only its apparent half-size and axis change.
"""
import json
import math
from pathlib import Path
import tempfile
import unittest

from tools.stop_rotation_audit import audit, input_fingerprint, sessions

DT = 0.02
DISTANCE = math.hypot(300.0, 320.0)


def recording(folder, phases, half, orientation, mode='play', episodes=None):
    """Write a recording whose row t carries the Retina angle of row t-1's geometry."""
    folder.mkdir(parents=True)
    manifest = {'tick_seconds': DT, 'mode': mode, 'config_version': 26,
                'config': {'swatter': {'directional': {'tilt_geometry': 'elevation_aware_tilt_v1'}},
                           'policy': {'escape_decoder': {}}}}
    (folder/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    with (folder/'ticks.jsonl').open('w', encoding='utf-8') as handle:
        for t, phase in enumerate(phases):
            seen = half[max(t - 1, 0)]
            handle.write(json.dumps({
                'episode': episodes[t] if episodes else 1,
                'fly': {'alive': True, 'x': 0.0, 'y': 0.0}, 'lifecycle': {'airborne': True},
                'swatter': {'phase': phase, 'orientation': orientation[t], 'x': 300.0, 'y': 0.0, 'height': 320.0},
                'retina': {'theta': 2*math.atan(seen/DISTANCE)}, 'event_flags': {'escape_onset': False}}) + '\n')
    with (folder/'inputs.jsonl').open('w', encoding='utf-8') as handle:
        for t in range(len(phases)):
            handle.write(json.dumps({'kind': 'tick', 'pointer': [300.0, 0.0], 'wall_seconds': t*DT}) + '\n')
    return manifest


class TestStopRotationAudit(unittest.TestCase):
    def test_growth_before_the_approach_phase_is_not_attributed_to_hover(self):
        phases = ['recovery']*20 + ['approach']*20
        half = [80.0]*15 + [80.0 + 2*k for k in range(1, 6)] + [90.0]*20
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'s'
            result = audit(folder, recording(folder, phases, half, [0.0]*40))
        self.assertEqual(result['episodes'], [])

    def test_last_hover_sample_before_commit_is_kept_and_a_reversal_spin_is_labelled(self):
        phases = ['approach']*55 + ['commit']*5
        half = [80.0]*52 + [82.0, 84.0, 86.0] + [86.0]*5
        orientation = [0.0]*45 + [math.pi*k/9 for k in range(1, 10)] + [math.pi]*6
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'s'
            result = audit(folder, recording(folder, phases, half, orientation))
        [episode] = result['episodes']
        self.assertEqual((episode['tick'], episode['ticks']), (53, 3))
        self.assertTrue(episode['transient'])
        self.assertTrue(episode['reversal'])
        self.assertAlmostEqual(episode['net_axis_degrees'], 0.0, places=6)

    def test_baseline_exclusion_stays_inside_the_episode(self):
        # A size-driven episode right after a restart must not remove hover samples of the
        # previous episode from the baseline.
        half = [80.0]*61 + [82.0, 84.0, 86.0] + [86.0]*56
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)/'s'
            result = audit(folder, recording(folder, ['approach']*120, half, [0.0]*120,
                                             episodes=[1]*60 + [2]*60))
        [episode] = result['episodes']
        self.assertEqual((episode['episode'], episode['tick']), (2, 62))
        self.assertEqual(sum(cell[0] for cell in result['groups']['baseline hover']), 2)

    def test_blind_test_recordings_are_refused(self):
        with self.assertRaises(SystemExit):
            list(sessions([Path('artifacts/m2_4_b/sessions')]))

    def test_input_fingerprint_ignores_wall_clock_time(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'a', Path(d)/'b'
            for folder in (a, b):
                recording(folder, ['approach']*5, [80.0]*5, [0.0]*5)
            lines = (b/'inputs.jsonl').read_text(encoding='utf-8').splitlines()
            shifted = [json.dumps({**json.loads(line), 'wall_seconds': 99.0}) for line in lines]
            (b/'inputs.jsonl').write_text('\n'.join(shifted) + '\n', encoding='utf-8')
            self.assertEqual(input_fingerprint(a), input_fingerprint(b))


if __name__ == '__main__':
    unittest.main()
