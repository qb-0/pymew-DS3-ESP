from __future__ import annotations

import sys
from pathlib import Path

import pymew as pm

from ds3esp.cheats import Cheats
from ds3esp.config import Config
from ds3esp.entities import Scanner
from ds3esp.esp import Renderer
from ds3esp.game import GameContext
from ds3esp.menu import Menu
from ds3esp.process import EspError, GameNotReady, GameProcess
from ds3esp.toggles import Toggles
from ds3esp.ue import UnrealEngine

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "darksiders3.cfg"
HINT = pm.color.get((255, 255, 255, 130))


def load_font(path: str, size: int) -> pm._Font | None:
    if not path:
        return None
    try:
        return pm.draw.load_font(path, size)
    except (pm.errors.Error, ValueError):
        return None


def run_overlay(cfg: Config, ctx: GameContext, scanner: Scanner, game: GameProcess, toggles: Toggles) -> None:
    monitor_refresh = 144
    monitors = pm.utils.monitors()
    if monitors:
        monitor_refresh = min(max(monitors[0].refresh, 60), 240)
    fps = cfg.fps or monitor_refresh

    renderer = Renderer(cfg)
    cheats = Cheats(game)
    font = None

    def refresh_font() -> None:
        nonlocal font
        new_font = load_font(toggles.font, toggles.font_size)
        if font is not None:
            font.close()
        font = new_font
        pm.draw.set_font(font)

    try:
        with pm.overlay.open(
            target=game.pid,
            fps=fps,
            title="Darksiders III ESP",
            exit_key=cfg.exit_key or None,
            track=True,
            log_level="error",
            imgui_bundle=True,
            imgui_key="insert",
        ) as ov:
            menu = Menu(toggles, cfg)

            refresh_font()

            while ov.loop():
                if not game.alive():
                    break
                if toggles.font_dirty:
                    toggles.font_dirty = False
                    refresh_font()
                scanner.update()
                frozen = cheats.apply(toggles, scanner.entities)
                camera = ctx.camera()
                width = ov.width()
                height = ov.height()
                if camera is not None:
                    renderer.draw(camera, scanner.entities, width, height, toggles)
                renderer.draw_status(height, scanner, camera, ctx)
                if ov.imgui_active():
                    menu.draw(ov, scanner, frozen)
                else:
                    pm.draw.text("INSERT  MENU", width - 14.0, height - 26.0, 14.0, HINT, "right")
    finally:
        if font is not None:
            font.close()


def main() -> int:
    cfg = Config.load(CONFIG_PATH)

    try:
        game = GameProcess.attach(cfg.exe)
    except EspError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with game:
        try:
            ue = UnrealEngine(game)
        except GameNotReady as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        ctx = GameContext.create(ue)
        toggles = Toggles(cfg.font)
        scanner = Scanner(ue, ctx, toggles, scan_ms=cfg.scan_ms)
        scanner.scan_all()

        run_overlay(cfg, ctx, scanner, game, toggles)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
