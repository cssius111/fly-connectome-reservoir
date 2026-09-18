"""pygame front end for the connectome-driven fly-swatter.

    python -m game.app

Controls
    mouse move   move the swatter
    left click   strike (wind-up, brief lethal window, cooldown)
    R            restart
    Space / P    pause
    H            toggle the neural HUD
    F11          fullscreen / windowed
    Esc          leave fullscreen, or quit if already windowed

The simulation runs on a fixed 20 ms tick (the connectome's own step) while
rendering runs as fast as the display allows, interpolating between ticks. The
brain is stepped inside `Session.tick`; this module only draws and collects
input, and never hands a coordinate to the fly.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("NUMBA_NUM_THREADS", "4")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import math  # noqa: E402

import pygame  # noqa: E402

from .session import ROOT, Session, load_config  # noqa: E402
from .world import StrikePhase  # noqa: E402

BG = (18, 20, 24)
GRID = (26, 29, 35)
INK = (232, 234, 238)
DIM = (140, 146, 158)
PHASE_COLOR = {StrikePhase.IDLE: (110, 118, 132),
               StrikePhase.WINDUP: (198, 150, 52),
               StrikePhase.ACTIVE: (208, 64, 58),
               StrikePhase.COOLDOWN: (78, 84, 96)}
LOOM_COLOR = (74, 134, 196)
THREAT_COLOR = (196, 112, 58)
ESCAPE_COLOR = (108, 190, 120)


class App:
    def __init__(self, config: dict, root: Path = ROOT, fullscreen: bool = False):
        self.config = config
        self.world_w = float(config["world"]["width"])
        self.world_h = float(config["world"]["height"])
        self.tick_seconds = float(config["sim"]["tick_seconds"])
        self.base_seed = int(config["sim"]["seed"])

        pygame.init()
        pygame.display.set_caption("MaleCNS fly-swatter")
        self.windowed_size = (int(self.world_w), int(self.world_h))
        self.fullscreen = False
        self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
        self.canvas = pygame.Surface(self.windowed_size)
        self.font = pygame.font.SysFont(None, 22)
        self.font_big = pygame.font.SysFont(None, 46)
        self.font_small = pygame.font.SysFont(None, 18)
        self._splash("Loading MaleCNS connectome (166,700 neurons)...")

        self.session = Session(config, root=root)
        self._splash("Compiling simulation kernels...")
        self.clock = pygame.time.Clock()
        self.show_neural = True
        self.paused = False
        self.run_index = 0
        self.accumulator = 0.0
        self.tick_ms = 0.0
        self.escape_flash = 0.0
        self.escape_vector = (0.0, 0.0)
        self.pointer_world = (self.world_w * 0.5, self.world_h * 0.2)
        self._prev = self._snapshot()
        if fullscreen:
            self._toggle_fullscreen()

    # ---- presentation helpers ---------------------------------------------
    def _splash(self, message: str) -> None:
        self.screen.fill(BG)
        font = pygame.font.SysFont(None, 34)
        text = font.render(message, True, INK)
        rect = text.get_rect(center=self.screen.get_rect().center)
        self.screen.blit(text, rect)
        pygame.display.flip()
        pygame.event.pump()

    def _toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        if self.fullscreen:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)

    def _letterbox(self):
        sw, sh = self.screen.get_size()
        scale = min(sw / self.world_w, sh / self.world_h)
        vw, vh = self.world_w * scale, self.world_h * scale
        return scale, (sw - vw) * 0.5, (sh - vh) * 0.5

    def _screen_to_world(self, pos) -> tuple[float, float]:
        scale, ox, oy = self._letterbox()
        return ((pos[0] - ox) / scale, (pos[1] - oy) / scale)

    def _snapshot(self) -> dict:
        w = self.session.world
        return {"fly": (w.fly.x, w.fly.y), "heading": w.fly.heading,
                "swatter": (w.swatter.x, w.swatter.y),
                "height": w.swatter.height, "face": w.swatter.face}

    # ---- main loop ---------------------------------------------------------
    def run(self, max_seconds: float | None = None) -> int:
        started = time.perf_counter()
        running = True
        while running:
            frame = self.clock.tick(120) / 1000.0
            frame = min(frame, 0.25)
            strike_requested = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.VIDEORESIZE and not self.fullscreen:
                    self.windowed_size = (max(640, event.w), max(360, event.h))
                    self.screen = pygame.display.set_mode(self.windowed_size, pygame.RESIZABLE)
                elif event.type == pygame.MOUSEMOTION:
                    self.pointer_world = self._screen_to_world(event.pos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    strike_requested = True
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if self.fullscreen:
                            self._toggle_fullscreen()
                        else:
                            running = False
                    elif event.key == pygame.K_F11:
                        self._toggle_fullscreen()
                    elif event.key == pygame.K_r:
                        self._restart()
                    elif event.key in (pygame.K_SPACE, pygame.K_p):
                        self.paused = not self.paused
                    elif event.key == pygame.K_h:
                        self.show_neural = not self.show_neural

            if not self.paused:
                self._advance(frame, strike_requested)
            self._draw()
            if max_seconds is not None and time.perf_counter() - started >= max_seconds:
                running = False
        pygame.quit()
        return 0

    def _restart(self) -> None:
        self.run_index += 1
        self.session.reset(self.base_seed + 1000 * self.run_index)
        self.accumulator = 0.0
        self.escape_flash = 0.0
        self._prev = self._snapshot()

    def _advance(self, frame_seconds: float, strike_requested: bool) -> None:
        self.accumulator += frame_seconds
        self.escape_flash = max(0.0, self.escape_flash - frame_seconds)
        pending_strike = strike_requested
        while self.accumulator >= self.tick_seconds:
            self.accumulator -= self.tick_seconds
            self._prev = self._snapshot()
            t0 = time.perf_counter()
            self.session.tick(pointer=self.pointer_world, strike=pending_strike)
            self.tick_ms = 0.85 * self.tick_ms + 0.15 * (time.perf_counter() - t0) * 1000.0
            pending_strike = False
            action = self.session.fly_loop.last_action
            if action.escape and action.strength > 0.0:
                self.escape_flash = 0.35
                h = self.session.world.fly.heading
                hx, hy = math.cos(h), math.sin(h)
                self.escape_vector = (-hy * action.lateral + hx * action.forward,
                                      hx * action.lateral + hy * action.forward)
        if pending_strike:
            # Click landed between ticks: don't drop it.
            self.session.world.request_strike()

    # ---- drawing -----------------------------------------------------------
    def _draw(self) -> None:
        alpha = min(1.0, self.accumulator / self.tick_seconds)
        now = self._snapshot()
        fly = self._lerp(self._prev["fly"], now["fly"], alpha)
        swat = self._lerp(self._prev["swatter"], now["swatter"], alpha)
        height = self._prev["height"] + (now["height"] - self._prev["height"]) * alpha
        face = self._prev["face"] + (now["face"] - self._prev["face"]) * alpha

        c = self.canvas
        c.fill(BG)
        for x in range(0, int(self.world_w), 80):
            pygame.draw.line(c, GRID, (x, 0), (x, self.world_h))
        for y in range(0, int(self.world_h), 80):
            pygame.draw.line(c, GRID, (0, y), (self.world_w, y))
        margin = self.config["world"]["margin"]
        pygame.draw.rect(c, (40, 44, 52), pygame.Rect(margin, margin,
                         self.world_w - 2 * margin, self.world_h - 2 * margin), 1)

        self._draw_swatter(c, swat, height, face)
        self._draw_fly(c, fly, now["heading"])
        self._draw_hud(c)
        if self.paused:
            self._center_text(c, "PAUSED", "space / P to resume")
        elif not self.session.world.fly.alive and self.session.world.splat_finished:
            st = self.session.stats
            self._center_text(c, "SPLAT", f"survived {st.survival_seconds:4.1f} s  -  R to restart")

        scale, ox, oy = self._letterbox()
        self.screen.fill((0, 0, 0))
        target = pygame.transform.smoothscale(c, (int(self.world_w * scale), int(self.world_h * scale)))
        self.screen.blit(target, (ox, oy))
        pygame.display.flip()

    @staticmethod
    def _lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)

    def _draw_swatter(self, c, pos, height, face) -> None:
        w = self.session.world
        phase = w.swatter.phase
        colour = PHASE_COLOR[phase]
        r = w.paddle_radius
        # Footprint: exactly the lethal area, so the player can aim.
        pygame.draw.circle(c, colour, (int(pos[0]), int(pos[1])), int(r), 2)
        if phase is StrikePhase.ACTIVE:
            pygame.draw.circle(c, (90, 26, 26), (int(pos[0]), int(pos[1])), int(r * 0.92))
            pygame.draw.circle(c, colour, (int(pos[0]), int(pos[1])), int(r), 3)
        # Paddle, lifted by its height and rotating edge-on -> face-on. This is
        # literally what perception.py measures as angular size.
        lift = height * 0.30
        thin = w.edge_on_factor + (1.0 - w.edge_on_factor) * face
        rect = pygame.Rect(0, 0, int(2 * r), max(4, int(2 * r * thin)))
        rect.center = (int(pos[0]), int(pos[1] - lift))
        pygame.draw.ellipse(c, (52, 58, 70), rect)
        pygame.draw.ellipse(c, colour, rect, 3)
        pygame.draw.line(c, colour, rect.center,
                         (rect.centerx + int(r * 1.5), rect.centery - int(r * 1.1)), 5)
        pygame.draw.line(c, (60, 66, 78), (int(pos[0]), int(pos[1])),
                         (rect.centerx, rect.centery), 1)

    def _draw_fly(self, c, pos, heading) -> None:
        w = self.session.world
        x, y = pos
        r = w.fly_radius
        if not w.fly.alive:
            for dx, dy, rad in ((0, 0, r * 1.9), (r * 1.5, r * 0.6, r * 0.9),
                                (-r * 1.3, r * 1.1, r * 0.7), (r * 0.4, -r * 1.6, r * 0.6)):
                pygame.draw.circle(c, (86, 28, 34), (int(x + dx), int(y + dy)), int(rad))
            pygame.draw.circle(c, (150, 44, 50), (int(x), int(y)), int(r * 0.8))
            return
        hx, hy = math.cos(heading), math.sin(heading)
        rx, ry = -hy, hx
        if self.escape_flash > 0.0:
            glow = int(r * (2.4 + 6.0 * self.escape_flash))
            pygame.draw.circle(c, ESCAPE_COLOR, (int(x), int(y)), glow, 1)
            ex, ey = self.escape_vector
            pygame.draw.line(c, ESCAPE_COLOR, (int(x), int(y)),
                             (int(x + ex * 46), int(y + ey * 46)), 2)
        wing = 1.5 * r
        for s in (1, -1):
            pts = [(x + rx * s * wing * 0.2 + hx * r * 0.2, y + ry * s * wing * 0.2 + hy * r * 0.2),
                   (x + rx * s * wing - hx * r * 0.9, y + ry * s * wing - hy * r * 0.9),
                   (x + rx * s * wing * 0.5 - hx * r * 1.7, y + ry * s * wing * 0.5 - hy * r * 1.7)]
            pygame.draw.polygon(c, (96, 104, 120), [(int(a), int(b)) for a, b in pts])
        body = [(x + hx * r * 1.7, y + hy * r * 1.7),
                (x + rx * r * 0.8, y + ry * r * 0.8),
                (x - hx * r * 1.6, y - hy * r * 1.6),
                (x - rx * r * 0.8, y - ry * r * 0.8)]
        pygame.draw.polygon(c, (36, 38, 44), [(int(a), int(b)) for a, b in body])
        pygame.draw.polygon(c, (188, 194, 206), [(int(a), int(b)) for a, b in body], 1)
        pygame.draw.circle(c, (206, 92, 84),
                           (int(x + hx * r * 1.4), int(y + hy * r * 1.4)), max(2, int(r * 0.36)))

    def _center_text(self, c, title: str, subtitle: str) -> None:
        overlay = pygame.Surface((int(self.world_w), int(self.world_h)), pygame.SRCALPHA)
        overlay.fill((10, 11, 14, 150))
        c.blit(overlay, (0, 0))
        t = self.font_big.render(title, True, INK)
        s = self.font.render(subtitle, True, DIM)
        cx, cy = int(self.world_w * 0.5), int(self.world_h * 0.5)
        c.blit(t, t.get_rect(center=(cx, cy - 16)))
        c.blit(s, s.get_rect(center=(cx, cy + 22)))

    def _draw_hud(self, c) -> None:
        st = self.session.stats
        rows = [f"time {st.survival_seconds:6.1f}s",
                f"strikes {st.strikes}", f"hits {st.hits}", f"misses {st.misses}",
                f"escapes {st.escapes}",
                f"hit rate {100 * st.hit_rate:5.1f}%", f"escape rate {100 * st.escape_rate:5.1f}%"]
        x = 14
        for i, text in enumerate(rows):
            c.blit(self.font.render(text, True, INK), (x, 12 + i * 21))
        hint = "H neural  R restart  space pause  F11 fullscreen  esc quit"
        c.blit(self.font_small.render(hint, True, DIM), (x, int(self.world_h) - 24))
        if not self.show_neural:
            return

        motor = self.session.fly_loop.last_motor
        drive = self.session.encoder.last_drive
        retina = self.session.last_retina
        diagnostics = self.session.policy_diagnostics
        threshold = diagnostics.get("escape_threshold")
        refractory = diagnostics.get("refractory_seconds")
        theta = 0.0 if retina is None else retina.theta
        theta_dot = 0.0 if retina is None else retina.theta_dot
        azimuth = 0.0 if retina is None else retina.azimuth
        lines = [f"retina theta {theta:5.2f} rad   d/dt {theta_dot:+6.2f}",
                 f"azimuth {azimuth:+5.2f}"]
        optional = []
        if threshold is not None:
            optional.append(f"threshold (sum) {threshold:4.2f}")
        if refractory is not None:
            optional.append(f"refractory {refractory:4.2f}s")
        if optional:
            lines.append("   ".join(optional))
        lines.extend([f"brain {self.tick_ms:4.2f} ms/tick   fps {self.clock.get_fps():5.1f}",
                      f"LC4 {self.session.encoder.population['threat']['used_per_side']}/side  "
                      f"LPLC2 {self.session.encoder.population['loom']['used_per_side']}/side"])

        # Reserve a right-aligned numeric column and derive height from all rows.
        # The threshold refers to summed DNp01, not either individual side.
        bar_count = 6 + int(threshold is not None)
        panel_w = 380
        panel_h = 34 + bar_count * 26 + 10 + len(lines) * 17 + 12
        px = int(self.world_w) - panel_w - 14
        py = 12
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((10, 12, 16, 190))
        c.blit(panel, (px, py))
        pygame.draw.rect(c, (52, 58, 70), pygame.Rect(px, py, panel_w, panel_h), 1)
        c.blit(self.font.render("MaleCNS-derived runtime", True, INK), (px + 12, py + 8))

        def bar(row, label, value, vmax, colour, marker=None):
            top = py + 34 + row * 26
            c.blit(self.font_small.render(label, True, DIM), (px + 12, top))
            bx, bw = px + 132, panel_w - 132 - 70
            pygame.draw.rect(c, (34, 38, 46), pygame.Rect(bx, top + 2, bw, 12))
            frac = 0.0 if vmax <= 0 else max(0.0, min(1.0, value / vmax))
            pygame.draw.rect(c, colour, pygame.Rect(bx, top + 2, int(bw * frac), 12))
            if marker is not None and vmax > 0:
                mx = bx + int(bw * max(0.0, min(1.0, marker / vmax)))
                pygame.draw.line(c, (208, 64, 58), (mx, top), (mx, top + 15), 2)
            number = self.font_small.render(f"{value:5.2f}", True, INK)
            c.blit(number, number.get_rect(topright=(px + panel_w - 12, top)))

        cap = float(self.config["encoder"]["cap"])
        left = 0.0 if motor is None else motor.dnp01_left
        right = 0.0 if motor is None else motor.dnp01_right
        dmax = max(2.0, left + right, 0.0 if threshold is None else 2.0 * threshold)
        bar(0, "LPLC2 loom L", drive.get("loomL", 0.0), cap, LOOM_COLOR)
        bar(1, "LPLC2 loom R", drive.get("loomR", 0.0), cap, LOOM_COLOR)
        bar(2, "LC4 threat L", drive.get("threatL", 0.0), cap, THREAT_COLOR)
        bar(3, "LC4 threat R", drive.get("threatR", 0.0), cap, THREAT_COLOR)
        bar(4, "DNp01 left", left, dmax, ESCAPE_COLOR)
        bar(5, "DNp01 right", right, dmax, ESCAPE_COLOR)
        if threshold is not None:
            bar(6, "DNp01 total", left + right, dmax, ESCAPE_COLOR, marker=threshold)

        info_y = py + 34 + bar_count * 26 + 10
        for i, line in enumerate(lines):
            c.blit(self.font_small.render(line, True, DIM), (px + 12, info_y + i * 17))



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Connectome-driven fly-swatter game")
    parser.add_argument("--config", type=Path, default=ROOT / "game_config.json")
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--smoke", type=float, default=None, metavar="SECONDS",
                        help="run headless for N seconds and exit (CI check)")
    args = parser.parse_args(argv)
    if args.smoke is not None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    config = load_config(args.config)
    app = App(config, fullscreen=args.fullscreen)
    return app.run(max_seconds=args.smoke)


if __name__ == "__main__":
    sys.exit(main())
