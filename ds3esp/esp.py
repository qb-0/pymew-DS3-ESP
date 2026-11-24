from __future__ import annotations

from collections import Counter

import pymew as pm

from . import offsets as off
from .camera import Camera
from .config import Config
from .entities import Category, Entity, Scanner
from .game import GameContext
from .toggles import Toggles

COLORS = {
    Category.ENEMY: pm.color.get((255, 60, 60, 235)),
    Category.NPC: pm.color.get((90, 210, 110, 220)),
    Category.ITEM: pm.color.get((255, 205, 60, 235)),
    Category.PICKUP: pm.color.get((80, 215, 235, 235)),
    Category.HUMAN: pm.color.get((255, 130, 220, 235)),
}
SHADOW = pm.color.get((0, 0, 0, 255))
DIM = pm.color.get((255, 255, 255, 150))
BAR = pm.color.get((240, 60, 60, 255))
DEBUG_TEXT = pm.color.get((235, 235, 235, 220))

BOX_HEIGHT = {
    Category.ENEMY: 185.0,
    Category.NPC: 185.0,
    Category.ITEM: 45.0,
    Category.PICKUP: 30.0,
    Category.HUMAN: 170.0,
}

BAR_CATEGORIES = (Category.ENEMY, Category.NPC)
CULL_MARGIN = 400.0


class Renderer:
    def __init__(self, cfg: Config):
        self.d = pm.draw
        self.min_box_px = float(cfg.min_box_px)
        self.debug = cfg.debug

    def draw(
        self,
        camera: Camera,
        entities: list[Entity],
        width: int,
        height: int,
        toggles: Toggles,
    ) -> None:
        if not toggles.esp:
            return
        for entity in entities:
            if entity.category is Category.PLAYER:
                continue
            self._draw_entity(camera, entity, float(width), float(height), toggles)

    def _draw_entity(
        self,
        camera: Camera,
        entity: Entity,
        width: float,
        height: float,
        toggles: Toggles,
    ) -> None:
        loc = entity.loc
        distance = camera.distance(loc.x, loc.y, loc.z)
        if toggles.max_dist > 0 and distance > toggles.max_dist * 100.0:
            return
        font_size = float(toggles.font_size)

        if entity.half_height > 0:
            base_z = loc.z - entity.half_height
            top_z = loc.z + entity.half_height
        else:
            base_z = loc.z
            top_z = loc.z + BOX_HEIGHT.get(entity.category, 40.0)

        feet = camera.project(loc.x, loc.y, base_z, width, height)
        head = camera.project(loc.x, loc.y, top_z, width, height)
        if feet is None or head is None:
            return

        feet_x, feet_y, _ = feet
        head_x, head_y, _ = head
        if feet_x < -CULL_MARGIN or feet_x > width + CULL_MARGIN or feet_y < -CULL_MARGIN or feet_y > height + CULL_MARGIN:
            return

        color = COLORS.get(entity.category, DIM)
        label = f"{entity.label}  {distance / 100.0:.0f}m"
        top = pm.vec2(head_x, head_y)
        bottom = pm.vec2(feet_x, feet_y)
        if bottom.y < top.y:
            top, bottom = bottom, top
        box_height = bottom.y - top.y

        if box_height < self.min_box_px or not toggles.boxes:
            self._dot(feet_x, feet_y, color)
            if toggles.labels:
                self._text(label, feet_x + 6, feet_y - font_size * 0.5, font_size, color, "left")
            return

        show_bar = toggles.hp_bar and entity.category in BAR_CATEGORIES
        ratio = 0.35
        if entity.half_height > 0 and entity.radius > 0:
            ratio = entity.radius / entity.half_height

        box = self.d.entity_box_from_points(
            top,
            bottom,
            color,
            ratio=ratio,
            style="corner",
            fill=0.0,
            thick=1.5,
            outline=True,
            outline_color=SHADOW,
            outline_thick=1.0,
        )

        if show_bar:
            value = max(0.0, min(entity.hp / off.HEALTH_FULL, 1.0))
            box.add_bar(
                "left",
                BAR,
                value=value,
                thick=4.0,
                gap=2.0,
                outline=True,
                outline_color=SHADOW,
                outline_thick=1.0,
            )

        if toggles.labels:
            box.add_text(
                "top",
                label,
                color,
                size=font_size,
                gap=2.0,
                outline=True,
                outline_color=SHADOW,
                outline_thick=2.0,
            )

        if toggles.snaplines:
            box.add_snapline(
                "bottom",
                color,
                source="bottom",
                style="dashed",
                spacing=8.0,
                outline=True,
                outline_color=SHADOW,
                outline_thick=1.0,
            )

        box.draw()

    def _dot(self, x: float, y: float, color: int) -> None:
        self.d.circle(x, y, 3.0, SHADOW)
        self.d.circle(x, y, 2.0, color)

    def _text(self, text: str, x: float, y: float, size: float, color: int, align: str) -> None:
        self.d.text(text, x + 1, y + 1, size, SHADOW, align)
        self.d.text(text, x, y, size, color, align)

    def draw_status(
        self,
        height: int,
        scanner: Scanner,
        camera: Camera | None,
        ctx: GameContext,
    ) -> None:
        if not self.debug:
            return

        counts = count_categories(scanner.entities)
        camera_text = "camera: none"
        if camera is not None:
            camera_text = f"camera {camera.x:.0f},{camera.y:.0f},{camera.z:.0f} fov {camera.fov:.0f}"
        lines = [
            f"entities {len(scanner.entities)}  E {counts[Category.ENEMY]} N {counts[Category.NPC]} "
            f"I {counts[Category.ITEM]} P {counts[Category.PICKUP]} H {counts[Category.HUMAN]}",
            f"scan {scanner.scan_ms:.1f} ms  interval {scanner.scan_interval * 1000:.0f} ms",
            camera_text,
            ctx.describe(),
        ]
        text_h = self.d.measure_text(lines, 14.0).y
        self.d.text(lines, 12.0, height - 12.0 - text_h, 14.0, DEBUG_TEXT)


def count_categories(entities: list[Entity]) -> Counter[Category]:
    return Counter(entity.category for entity in entities)
