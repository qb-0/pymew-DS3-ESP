from __future__ import annotations


class Toggles:
    def __init__(self, font: str = ""):
        self.esp = True
        self.boxes = True
        self.labels = True
        self.hp_bar = True
        self.snaplines = False
        self.max_dist = 0.0
        self.font = font
        self.font_size = 16
        self.font_dirty = False
        self.npc = True
        self.items = True
        self.pickups = True
        self.humans = True
        self.god = False
        self.onehit = False
        self.freeze = False
        self.freeze_radius = 8.0
