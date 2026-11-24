from __future__ import annotations

import pymew as pm
from imgui_bundle import imgui

from .config import Config
from .entities import Scanner
from .toggles import Toggles

ACCENT = imgui.ImVec4(0.95, 0.55, 0.18, 1.0)
TEXT = imgui.ImVec4(0.91, 0.93, 0.97, 1.0)
MUTED = imgui.ImVec4(0.55, 0.58, 0.66, 1.0)
ONLINE = imgui.ImVec4(0.40, 0.86, 0.56, 1.0)

FONT_SCALE = 1.25
ITEM_WIDTH = 220.0
WINDOW_POS = imgui.ImVec2(40.0, 40.0)
WINDOW_SIZE = imgui.ImVec2(360.0, 0.0)

VISUALS = (
    ("esp", "ESP", "Master switch for all ESP drawing"),
    ("boxes", "Boxes", "Draw boxes around entities"),
    ("labels", "Names", "Show names and distances"),
    ("hp_bar", "HP bars", "Show health bars"),
    ("snaplines", "Snaplines", "Draw lines to the bottom of the screen"),
)


class Menu:
    def __init__(self, toggles: Toggles, cfg: Config):
        self.toggles = toggles
        self.exit_key = (cfg.exit_key or "insert").upper()
        fonts = [""] + pm.draw.fonts()
        if toggles.font and toggles.font not in fonts:
            fonts.insert(0, toggles.font)
        self.fonts = fonts
        self.font_labels = ["Default" if not font else font for font in fonts]
        self._apply_style()

    def _apply_style(self) -> None:
        imgui.style_colors_dark()
        style = imgui.get_style()
        style.font_scale_main = FONT_SCALE
        style.scale_all_sizes(FONT_SCALE)
        style.window_padding = imgui.ImVec2(16.0, 14.0)
        style.frame_padding = imgui.ImVec2(9.0, 5.0)
        style.item_spacing = imgui.ImVec2(11.0, 9.0)
        style.window_rounding = 8.0
        style.frame_rounding = 5.0
        style.grab_rounding = 5.0
        style.window_border_size = 1.0
        style.frame_border_size = 0.0

        colors = {
            imgui.Col_.text: TEXT,
            imgui.Col_.text_disabled: MUTED,
            imgui.Col_.window_bg: imgui.ImVec4(0.05, 0.06, 0.08, 0.95),
            imgui.Col_.title_bg: imgui.ImVec4(0.10, 0.11, 0.14, 0.98),
            imgui.Col_.title_bg_active: imgui.ImVec4(0.13, 0.14, 0.18, 0.99),
            imgui.Col_.border: imgui.ImVec4(0.95, 0.55, 0.18, 0.35),
            imgui.Col_.frame_bg: imgui.ImVec4(0.13, 0.14, 0.18, 1.0),
            imgui.Col_.frame_bg_hovered: imgui.ImVec4(0.20, 0.22, 0.27, 1.0),
            imgui.Col_.frame_bg_active: imgui.ImVec4(0.24, 0.26, 0.32, 1.0),
            imgui.Col_.checkbox_selected_bg: imgui.ImVec4(0.55, 0.30, 0.08, 1.0),
            imgui.Col_.check_mark: ACCENT,
            imgui.Col_.separator: imgui.ImVec4(1.0, 1.0, 1.0, 0.12),
        }
        for index, color in colors.items():
            style.set_color_(index, color)

    def draw(self, ov: pm.Overlay, scanner: Scanner, frozen: int = 0) -> None:
        imgui.set_next_window_pos(WINDOW_POS, imgui.Cond_.first_use_ever)
        imgui.set_next_window_size(WINDOW_SIZE, imgui.Cond_.first_use_ever)
        expanded, _ = imgui.begin("Darksiders III ESP", None, imgui.WindowFlags_.no_resize)
        if expanded:
            self._header()
            self._section("VISUALS")
            for attribute, label, key in VISUALS:
                self._toggle(label, attribute, key)
            imgui.set_next_item_width(ITEM_WIDTH)
            _, self.toggles.max_dist = imgui.slider_float("Max distance", self.toggles.max_dist, 0.0, 500.0, "%.0f m")
            imgui.set_item_tooltip("0 = no limit")
            imgui.set_next_item_width(ITEM_WIDTH)
            _, self.toggles.font_size = imgui.slider_int("Font size", self.toggles.font_size, 8, 40)
            imgui.set_item_tooltip("ESP label text size")
            if imgui.is_item_deactivated_after_edit():
                self.toggles.font_dirty = True
            imgui.set_next_item_width(ITEM_WIDTH)
            index = self.fonts.index(self.toggles.font) if self.toggles.font in self.fonts else 0
            changed, selected = imgui.combo("Font", index, self.font_labels, 12)
            if changed:
                self.toggles.font = self.fonts[selected]
                self.toggles.font_dirty = True
            self._section("FILTERS")
            self._toggle("NPCs", "npc", "Friendly characters")
            self._toggle("Items", "items", "Items and objects")
            self._toggle("Pickups", "pickups", "Pickup blueprints")
            self._toggle("Humans", "humans", "Collectible humans")
            self._section("CHEATS")
            self._toggle("One-hit kill", "onehit", "Enemies stay at 0.1% health")
            self._toggle("God mode", "god", "Keeps health at full")
            if self.toggles.god:
                imgui.same_line()
                imgui.text_colored(ONLINE, "ACTIVE")
            self._toggle("Freeze aura", "freeze", "Holds nearby enemies in place")
            if self.toggles.freeze:
                imgui.same_line()
                imgui.text_colored(ONLINE, f"{frozen} frozen")
            imgui.indent()
            imgui.begin_disabled(not self.toggles.freeze)
            imgui.set_next_item_width(ITEM_WIDTH)
            _, self.toggles.freeze_radius = imgui.slider_float("Radius", self.toggles.freeze_radius, 1.0, 50.0, "%.0f m")
            imgui.end_disabled()
            imgui.unindent()
            imgui.spacing()
            imgui.separator()
            imgui.text_disabled(f"{ov.fps()} fps   {len(scanner.entities)} objects   {scanner.scan_ms:.1f} ms")
            imgui.text_disabled(f"INSERT menu   {self.exit_key} quit")
        imgui.end()

    def _header(self) -> None:
        imgui.text_colored(ACCENT, "DARKSIDERS III")
        imgui.same_line()
        imgui.text_disabled("ESP")
        pos = imgui.get_cursor_screen_pos()
        width = imgui.get_content_region_avail().x
        draw = imgui.get_window_draw_list()
        draw.add_rect_filled(
            imgui.ImVec2(pos.x, pos.y),
            imgui.ImVec2(pos.x + width, pos.y + 2.0),
            imgui.get_color_u32(ACCENT),
            1.0,
        )
        imgui.dummy(imgui.ImVec2(0.0, 6.0))

    def _section(self, label: str) -> None:
        imgui.spacing()
        imgui.text_colored(ACCENT, label)

    def _toggle(self, label: str, attribute: str, tooltip: str = "") -> None:
        _, value = imgui.checkbox(label, getattr(self.toggles, attribute))
        setattr(self.toggles, attribute, value)
        if tooltip:
            imgui.set_item_tooltip(tooltip)
