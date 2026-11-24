from __future__ import annotations

import time
from dataclasses import dataclass
from enum import IntEnum

import pymew as pm

from . import offsets as off
from .game import GameContext
from .process import GameProcess, is_valid_ptr
from .structs import (
    ActorSnapshot,
    CapsuleDims,
    CharacterSnapshot,
    HumanSnapshot,
)
from .toggles import Toggles
from .ue import UnrealEngine


class Category(IntEnum):
    PLAYER = 1
    ENEMY = 2
    NPC = 3
    ITEM = 4
    PICKUP = 5
    HUMAN = 6


class Kind(IntEnum):
    OTHER = 0
    CHAR = 1
    ITEM = 2
    PICKUP = 3
    HUMAN = 4


CHARACTER_CATEGORIES = (Category.PLAYER, Category.ENEMY, Category.NPC)
FULL_RESCAN_SECONDS = 5.0


def at_origin(loc: pm.vec3) -> bool:
    return abs(loc.x) + abs(loc.y) + abs(loc.z) < off.ORIGIN_EPSILON


@dataclass(slots=True)
class Entity:
    address: int
    cls: int
    category: Category
    label: str
    loc: pm.vec3
    half_height: float = 0.0
    radius: float = 0.0
    hp: float = 0.0


class Scanner:
    def __init__(self, ue: UnrealEngine, ctx: GameContext, toggles: Toggles, scan_ms: int = 200):
        self.ue = ue
        self.ctx = ctx
        self.toggles = toggles
        self.proc: GameProcess = ue.proc

        self.scan_interval = max(scan_ms, 25) / 1000.0
        self.entities: list[Entity] = []
        self.scan_ms = 0.0

        self._actors: list[int] = []
        self._cursor = 0
        self._fresh: list[Entity] = []
        self._scanning = False
        self._scan_work = 0.0
        self._last_finished = 0.0
        self._kind_cache: dict[int, Kind] = {}
        self._actor_cache: dict[int, tuple[int, Kind]] = {}
        self._full_pass = False
        self._full_cache: dict[int, tuple[int, Kind]] = {}
        self._last_full = 0.0

    def scan_all(self) -> list[Entity]:
        self._begin_scan(time.perf_counter())
        while self._scanning:
            self._scan_step(time.perf_counter() + 5.0)
        return self.entities

    def update(self, budget_ms: float = 4.0) -> list[Entity]:
        now = time.perf_counter()
        if not self._scanning and now - self._last_finished >= self.scan_interval:
            self._begin_scan(now)
        if self._scanning:
            self._scan_step(now + max(budget_ms, 0.5) / 1000.0)
        self._refresh()
        return self.entities

    def _begin_scan(self, now: float) -> None:
        self._last_finished = now
        level_before = self.ctx.level
        try:
            ready = self.ctx.refresh()
        except Exception:
            ready = False

        if not ready:
            self.entities = []
            return

        if level_before and self.ctx.level and self.ctx.level != level_before:
            self.ue.reset_class_caches()
            self._kind_cache.clear()
            self._actor_cache.clear()
            self._last_full = 0.0
            self.ctx.resolve_char_class()

        self._actors = self.ue.level_actors()
        self._cursor = 0
        self._fresh = []
        self._scanning = True
        self._scan_work = 0.0
        self._full_pass = not self._actor_cache or now - self._last_full >= FULL_RESCAN_SECONDS
        if self._full_pass:
            self._full_cache = {}
            self._last_full = now
        if not self._actors:
            self._finish_scan(time.perf_counter())

    def _finish_scan(self, now: float) -> None:
        if self._full_pass:
            self._actor_cache = self._full_cache
            self._full_cache = {}
            self._full_pass = False
        self.entities = self._fresh
        self._fresh = []
        self._scanning = False
        self._last_finished = now
        self.scan_ms = self._scan_work * 1000.0

    def _scan_step(self, deadline: float) -> None:
        actors = self._actors
        count = len(actors)
        started = time.perf_counter()
        while self._cursor < count:
            entity = self._classify(actors[self._cursor])
            self._cursor += 1
            if entity is not None:
                self._fresh.append(entity)
            if time.perf_counter() >= deadline:
                break
        self._scan_work += time.perf_counter() - started
        if self._cursor >= count:
            self._finish_scan(time.perf_counter())

    def _classify(self, address: int) -> Entity | None:
        proc = self.proc
        entry = None if self._full_pass else self._actor_cache.get(address)
        if entry is None:
            cls = proc.read(address + off.UOBJECT_CLASS, pm.mem.ptr)
            if not cls:
                return None
            kind = self._kind_cache.get(cls)
            if kind is None:
                kind = self._classify_class(cls)
                self._kind_cache[cls] = kind
            entry = (cls, kind)
            if self._full_pass:
                self._full_cache[address] = entry
            else:
                self._actor_cache[address] = entry
        else:
            cls, kind = entry

        if kind is Kind.OTHER:
            return None

        root = proc.read(address + off.ACTOR_ROOT_COMPONENT, pm.mem.ptr)
        if not is_valid_ptr(root):
            return None
        loc = proc.read(root + off.SCENECOMPONENT_RELATIVE_LOCATION, pm.mem.vec3)
        if loc is None:
            return None

        if kind is Kind.CHAR:
            return self._make_character(address, cls, loc)
        if kind is Kind.ITEM:
            return self._make_item(address, cls, loc)
        if kind is Kind.PICKUP:
            return self._make_pickup(address, cls, loc)
        return self._make_human(address, cls, loc, root)

    def _classify_class(self, cls: int) -> Kind:
        ancestry = self.ue.ancestry(cls)
        if off.CLASS_CHARACTER_GUNFIRE in ancestry:
            return Kind.CHAR
        if off.CLASS_ITEM in ancestry:
            return Kind.ITEM
        if off.CLASS_PICKUP in ancestry:
            return Kind.PICKUP
        if off.CLASS_HUMAN in ancestry:
            return Kind.HUMAN
        return Kind.OTHER

    def _make_character(self, address: int, cls: int, loc: pm.vec3) -> Entity | None:
        snap = self.proc.read(address, CharacterSnapshot)
        if snap is None or snap.class_ != cls:
            return None

        if address == self.ctx.pawn:
            category = Category.PLAYER
        elif self.ctx.is_hostile(snap.faction):
            category = Category.ENEMY
        elif self.toggles.npc:
            category = Category.NPC
        else:
            return None

        half_height = 0.0
        radius = 0.0
        if is_valid_ptr(snap.capsule):
            half_height, radius = self._dims(snap.capsule)

        return Entity(
            address,
            cls,
            category,
            self.ue.class_label(cls),
            loc,
            half_height,
            radius,
            float(snap.health),
        )

    def _make_item(self, address: int, cls: int, loc: pm.vec3) -> Entity | None:
        if not self.toggles.items:
            return None
        if at_origin(loc):
            return None
        return Entity(address, cls, Category.ITEM, self.ue.class_label(cls), loc)

    def _make_pickup(self, address: int, cls: int, loc: pm.vec3) -> Entity | None:
        if not self.toggles.pickups:
            return None
        return Entity(address, cls, Category.PICKUP, self.ue.class_label(cls), loc)

    def _make_human(self, address: int, cls: int, loc: pm.vec3, root: int) -> Entity | None:
        if not self.toggles.humans:
            return None
        if at_origin(loc):
            return None

        half_height = 0.0
        radius = 0.0
        snap = self.proc.read(address, HumanSnapshot)
        if snap is not None and snap.fade_detector == root:
            half_height, radius = self._dims(root)

        return Entity(
            address,
            cls,
            Category.HUMAN,
            self.ue.class_label(cls),
            loc,
            half_height,
            radius,
        )

    def _dims(self, address: int) -> tuple[float, float]:
        dims = self.proc.read(address, CapsuleDims)
        if dims is not None and 1 < dims.half_height < 5000 and 0 < dims.radius < 5000:
            return float(dims.half_height), float(dims.radius)
        return 0.0, 0.0

    def _refresh(self) -> None:
        if not self.entities:
            return

        proc = self.proc
        keep: list[Entity] = []
        for entity in self.entities:
            category = entity.category
            if category in CHARACTER_CATEGORIES:
                snap = proc.read(entity.address, CharacterSnapshot)
                if snap is None or snap.class_ != entity.cls:
                    continue
                root = snap.root_component
                hp = float(snap.health)
                if category is not Category.PLAYER and hp <= 0:
                    continue
            else:
                snap = proc.read(entity.address, ActorSnapshot)
                if snap is None or snap.class_ != entity.cls:
                    continue
                root = snap.root_component
                hp = entity.hp

            if not is_valid_ptr(root):
                continue
            loc = proc.read(root + off.SCENECOMPONENT_RELATIVE_LOCATION, pm.mem.vec3)
            if loc is None:
                continue

            if category in (Category.ITEM, Category.HUMAN) and at_origin(loc):
                continue

            entity.loc = loc
            entity.hp = hp
            keep.append(entity)
        self.entities = keep
