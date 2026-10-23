"""M1.7.2: the line-symmetric paddle axis (game/M1_7_2_PADDLE_AXIS_DESIGN.md).

World-only tests of the gate, the line-axis rule and its invariant, and the transfer record.
v26 is the ROOM configuration of tag v1.0; v27 is the working file.
"""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import unittest

os.environ.setdefault('NUMBA_NUM_THREADS', '4')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

from game.action import NO_ACTION
from game.session import calibration_provenance, load_config, resolve_escape_threshold
from game.world import PADDLE_AXIS_HEADING, PADDLE_AXIS_LINE, World
from test_game import same_content
from tools.m1_7_2_axis_record import BASELINE_COMMIT, RECORD, SOURCE_RECORD, build_record

ROOT = Path(__file__).parent
# v27 is read from main after M3.2, because M3.3 moved the working file to v29 (versioned in
# test_game_m3_3).
ROOM = json.loads(subprocess.check_output(['git', 'show', 'b5e6021d6dc7d7636071a12a8b6eaa0952e327d4:game_room_config.json'],
                                          cwd=ROOT, text=True))
V26 = json.loads(subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':game_room_config.json'],
                                         cwd=ROOT, text=True))
DT = 0.02
FLY = (1920.0, 1080.0)


def arc(legs, radius=300.0, speed=300.0, pre=50, post=75):
    """Pointer offsets on a circle around the fly: (sign, seconds) legs, with holds."""
    pts, a = [(radius, 0.0)]*pre, 0.0
    for sign, seconds in legs:
        for _ in range(int(round(seconds/DT))):
            a += sign*speed/radius*DT
            pts.append((radius*math.cos(a), radius*math.sin(a)))
    return pts + [pts[-1]]*post


def run(config, path, orientation=math.pi/2):
    """World-only run with the fly held still; per tick: tracker, axis, half size, x, y, fold."""
    w = World(config, 7)
    w.fly_motion_enabled = False
    w.collisions_enabled = False
    w.fly.x, w.fly.y, w.fly.vx, w.fly.vy = FLY[0], FLY[1], 0.0, 0.0
    sw = w.swatter
    sw.x, sw.y, sw.vx, sw.vy = FLY[0] + path[0][0], FLY[1] + path[0][1], 0.0, 0.0
    sw.orientation = sw.attack_orientation = orientation
    rows = []
    for ox, oy in path:
        w.set_pointer(FLY[0] + ox, FLY[1] + oy)
        w.tick(DT, NO_ACTION)
        ps = w.physical_swatter
        rows.append((sw.orientation, w.paddle_axis, w.visual_half_size, sw.x, sw.y,
                     ps.line_axis_enabled and ps.line_axis_folded))
    return w, rows


def first_fold(rows):
    return next((t for t, r in enumerate(rows) if r[5]), None)


def spread(rows, index, start=0):
    values = [r[index] for r in rows[start:]]
    return math.degrees(max(values) - min(values))


class TestGate(unittest.TestCase):
    def test_room_enables_the_line_axis_and_v26_does_not(self):
        self.assertEqual(ROOM['config_version'], 27)
        self.assertEqual(ROOM['swatter']['directional']['paddle_axis'], PADDLE_AXIS_LINE)
        self.assertNotIn('paddle_axis', V26['swatter']['directional'])
        self.assertEqual(World(V26, 1).paddle_axis_mode, PADDLE_AXIS_HEADING)

    def test_unknown_mode_and_missing_physical_swatter_are_rejected(self):
        config = copy.deepcopy(ROOM)
        config['swatter']['directional']['paddle_axis'] = 'spinning'
        with self.assertRaises(ValueError):
            World(config, 1)
        config = copy.deepcopy(ROOM)
        config['swatter']['physical']['enabled'] = False
        with self.assertRaises(ValueError):
            World(config, 1)

    def test_heading_mode_uses_the_tracker_and_records_no_new_key(self):
        w, rows = run(V26, arc([(1, 1.0), (-1, 1.0)]))
        self.assertTrue(all(r[0] == r[1] for r in rows))
        self.assertNotIn('paddle_line_axis', w.physical_swatter.diagnostics())

    def test_line_mode_records_the_line_axis(self):
        w, _ = run(ROOM, arc([(1, 0.5)]))
        d = w.physical_swatter.diagnostics()
        self.assertEqual(d['paddle_line_axis'], w.paddle_axis)
        self.assertIn('paddle_line_axis_folded', d)


class TestLineAxis(unittest.TestCase):
    def test_a_reversal_spins_the_tracker_but_not_the_line_axis(self):
        path = arc([(1, 1.0), (-1, 1.0)])
        reversal = 50 + 50
        _, a = run(V26, path)
        _, b = run(ROOM, path)
        fold = first_fold(b)
        self.assertIsNotNone(fold)
        self.assertGreaterEqual(fold, reversal)
        self.assertEqual(a[:fold], b[:fold])                      # the invariant
        self.assertEqual([r[3:5] for r in a], [r[3:5] for r in b])  # the paddle moves identically
        self.assertGreater(spread(a, 0, reversal) - spread(b, 1, reversal), 90.0)

    def test_the_stop_after_an_orbit_no_longer_changes_the_apparent_size(self):
        path = arc([(1, 7.0)], speed=130.0)
        hold = len(path) - 75
        _, a = run(V26, path)
        _, b = run(ROOM, path)
        self.assertGreater(spread(a, 0, hold), 60.0)
        self.assertLess(spread(b, 1, hold), 10.0)
        size = lambda rows: max(r[2] for r in rows[hold:]) - min(r[2] for r in rows[hold:])
        self.assertGreater(size(a), 5.0)
        self.assertLess(size(b), 1.0)

    def test_a_turn_below_90_degrees_is_unchanged(self):
        pts, x, y, h = [(0.0, -400.0)]*20, 0.0, -400.0, 0.0
        for _ in range(2):
            for _ in range(50):
                x, y = x + 300.0*DT*math.cos(h), y + 300.0*DT*math.sin(h)
                pts.append((x, y))
            h += math.radians(60.0)
        _, a = run(V26, pts, orientation=0.0)
        _, b = run(ROOM, pts, orientation=0.0)
        self.assertIsNone(first_fold(b))
        self.assertEqual(a, b)

    def test_a_slow_commit_holds_the_line_axis_through_the_strike(self):
        w, _ = run(ROOM, [(300.0, 0.0)]*40)
        before = w.paddle_axis
        self.assertTrue(w.request_strike())
        self.assertEqual(w.swatter.attack_speed, 0.0)
        axes = []
        while w.swatter.phase.value != 'approach' and len(axes) < 200:
            w.tick(DT, NO_ACTION)
            axes.append(w.paddle_axis)
        self.assertGreater(len(axes), 5)
        self.assertEqual(set(axes[:-1]), {before})


class TestRecord(unittest.TestCase):
    def test_the_record_is_bound_to_the_configuration_and_its_source(self):
        record, source = load_config(ROOT/RECORD), load_config(ROOT/SOURCE_RECORD)
        self.assertEqual(record['record_kind'], 'm1-7-2-paddle-axis-transfer-provenance-v1')
        self.assertEqual(record['provenance'], calibration_provenance(ROOM))
        resolved = resolve_escape_threshold(ROOM)
        self.assertEqual(resolved.origin, RECORD)
        self.assertEqual(resolved.threshold, 1.45)
        for key in ('escape_threshold', 'escape_decoder', 'parameter_basis'):
            self.assertEqual(record[key], source[key], key)
        self.assertTrue(record['decoder_unchanged'] and record['geometry_changed'])
        self.assertEqual(record['geometry']['paddle_axis'], PADDLE_AXIS_LINE)
        self.assertTrue(same_content(ROOT/SOURCE_RECORD, record['source_record']['sha256']))
        self.assertIsNotNone(record['measurement_reuse']['calibration_trials_c2'])
        self.assertEqual(record['source_record']['provenance'], calibration_provenance(V26))

    def test_the_writer_rejects_a_change_outside_the_paddle_axis(self):
        config = copy.deepcopy(ROOM)
        config['swatter']['directional']['tilt_anisotropy'] = 0.3
        with self.assertRaises(SystemExit):
            build_record(config)


if __name__ == '__main__':
    unittest.main()
