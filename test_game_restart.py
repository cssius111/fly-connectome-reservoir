"""Restart through the event loop, not only direct calls to _restart()."""
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
from game.app import App
from game.session import Session
from test_game import CONFIG, shared_brain


class TestRestart(unittest.TestCase):
    def make_app(self):
        self.addCleanup(pygame.quit)
        session = Session(CONFIG, brain=shared_brain())
        with patch("game.app.Session", return_value=session):
            app = App(CONFIG)
        app.clock = Mock()
        app.clock.tick.return_value = 20
        app.clock.get_fps.return_value = 50
        app._draw = Mock()
        return app

    def run_events(self, app, events):
        # Exercise the exact run-loop event branch, followed by normal ticks.
        with patch("pygame.event.get", side_effect=[events, [], [], [pygame.event.Event(pygame.QUIT)]]):
            app.run()

    def test_r_after_splat_revives_and_advances_new_seed(self):
        app = self.make_app()
        app.session.world.fly.alive = False
        app.session.world.stats.hits = 1
        app.session.world.splat_elapsed = 2
        self.run_events(app, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)])
        self.assertEqual(app.run_index, 1)
        self.assertTrue(app.session.world.fly.alive)
        self.assertEqual(app.session.stats.hits, 0)
        self.assertEqual(app.session.seed, app.base_seed + 1000)
        self.assertGreater(app.session.ticks, 0)

    def test_r_also_resumes_a_paused_game(self):
        app = self.make_app()
        app.paused = True
        self.run_events(app, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r)])
        self.assertFalse(app.paused)
        self.assertGreater(app.session.ticks, 0)

    def test_physical_r_works_when_translated_key_is_unknown(self):
        app = self.make_app()
        self.run_events(app, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UNKNOWN,
                                                scancode=pygame.KSCAN_R)])
        self.assertEqual(app.run_index, 1)

    def test_enter_is_an_explicit_restart_alternative(self):
        for key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            with self.subTest(key=key):
                app = self.make_app()
                self.run_events(app, [pygame.event.Event(pygame.KEYDOWN, key=key)])
                self.assertEqual(app.run_index, 1)

    def test_old_frame_strike_does_not_leak_into_restarted_episode(self):
        app = self.make_app()
        self.run_events(app, [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1),
                             pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r),
                             pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1)])
        self.assertEqual(app.session.stats.strikes, 0)

    def test_held_restart_repeat_does_not_keep_resetting(self):
        app = self.make_app()
        self.run_events(app, [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r),
                             pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, repeat=True)])
        self.assertEqual(app.run_index, 1)

    def test_game_controls_disable_text_composition_at_start_and_refocus(self):
        with patch("pygame.key.stop_text_input") as stop:
            app = self.make_app()
            self.run_events(app, [pygame.event.Event(pygame.WINDOWFOCUSGAINED)])
        self.assertGreaterEqual(stop.call_count, 2)


class TestShortcutsSurviveTextInputState(unittest.TestCase):
    """Every documented shortcut must work from the physical key alone."""

    def make_app(self):
        return TestRestart.make_app(self)

    def press(self, app, key, scancode=None):
        event = (pygame.event.Event(pygame.KEYDOWN, key=key) if scancode is None
                 else pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UNKNOWN, scancode=scancode))
        TestRestart.run_events(self, app, [event])

    def test_hud_pause_and_fullscreen_respond_to_keysym_and_scancode(self):
        for scancode in (None, "physical"):
            with self.subTest(scancode=scancode):
                app = self.make_app()
                self.press(app, pygame.K_h, pygame.KSCAN_H if scancode else None)
                self.assertFalse(app.show_neural)
                self.press(app, pygame.K_SPACE, pygame.KSCAN_SPACE if scancode else None)
                self.assertTrue(app.paused)
                self.press(app, pygame.K_p, pygame.KSCAN_P if scancode else None)
                self.assertFalse(app.paused)
                with patch.object(App, "_toggle_fullscreen") as toggle:
                    self.press(app, pygame.K_F11, pygame.KSCAN_F11 if scancode else None)
                self.assertEqual(toggle.call_count, 1)

    def test_escape_leaves_fullscreen_first_then_quits(self):
        app = self.make_app()
        app.fullscreen = True
        with patch.object(App, "_toggle_fullscreen") as toggle:
            self.press(app, pygame.K_ESCAPE, pygame.KSCAN_ESCAPE)
        self.assertEqual(toggle.call_count, 1)
        app = self.make_app()
        # A quit consumes only the first queued batch, so run() returns early.
        with patch("pygame.event.get", side_effect=[[pygame.event.Event(
                pygame.KEYDOWN, key=pygame.K_UNKNOWN, scancode=pygame.KSCAN_ESCAPE)]]):
            self.assertEqual(app.run(), 0)

    def test_unmapped_keys_are_ignored(self):
        app = self.make_app()
        self.press(app, pygame.K_q)
        self.assertEqual((app.run_index, app.paused, app.show_neural), (0, False, True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
