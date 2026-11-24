from __future__ import annotations

import pymew as pm

from . import offsets as off
from .entities import Category, Entity
from .process import GameProcess
from .toggles import Toggles

MAX_CHILDREN = 128
CHILD_BUDGET = 256


class Cheats:
    def __init__(self, proc: GameProcess):
        self.proc = proc
        self._anchors: dict[int, pm.vec3] = {}

    def apply(self, toggles: Toggles, entities: list[Entity]) -> int:
        player = next(
            (entity for entity in entities if entity.category is Category.PLAYER),
            None,
        )
        if toggles.onehit:
            self._one_hit(entities)
        if toggles.god and player is not None:
            self._god(player.address)
        radius = toggles.freeze_radius if toggles.freeze else 0.0
        return self._freeze(entities, player, radius)

    def _god(self, pawn: int) -> None:
        hp = self.proc.read(pawn + off.CHARGUNFIRE_HEALTH, pm.mem.f32)
        if hp is None or hp <= 0 or hp >= off.HEALTH_FULL:
            return
        self.proc.write(pawn + off.CHARGUNFIRE_HEALTH, pm.mem.f32(off.HEALTH_FULL))

    def _one_hit(self, entities: list[Entity]) -> None:
        for entity in entities:
            if entity.category is not Category.ENEMY or entity.hp <= 1.001:
                continue
            if self.proc.write(entity.address + off.CHARGUNFIRE_HEALTH, pm.mem.f32(1.0)):
                entity.hp = 1.0

    def _freeze(self, entities: list[Entity], player: Entity | None, radius: float) -> int:
        if radius <= 0 or player is None:
            self._anchors.clear()
            return 0

        limit = radius * 100.0
        anchors: dict[int, pm.vec3] = {}
        frozen = 0
        for entity in entities:
            if entity.category is not Category.ENEMY:
                continue
            if entity.loc.distance(player.loc) > limit:
                continue
            anchor = self._anchors.get(entity.address, entity.loc)
            anchors[entity.address] = anchor
            if self._set_actor_location(entity.address, anchor):
                entity.loc = anchor
            frozen += 1
        self._anchors = anchors
        return frozen

    def _set_actor_location(self, address: int, location: pm.vec3) -> bool:
        proc = self.proc
        root = proc.read(address + off.ACTOR_ROOT_COMPONENT, pm.mem.ptr)
        if not root:
            return False

        old = proc.read(root + off.SCENECOMPONENT_COMPONENT_TO_WORLD_TRANSLATION, pm.mem.vec3)
        if old is None:
            return False
        if not proc.write(root + off.SCENECOMPONENT_COMPONENT_TO_WORLD_TRANSLATION, location):
            return False

        parent = proc.read(root + off.SCENECOMPONENT_ATTACH_PARENT, pm.mem.ptr)
        if not parent:
            proc.write(root + off.SCENECOMPONENT_RELATIVE_LOCATION, location)

        self._move_children(root, location - old, CHILD_BUDGET)
        return True

    def _move_children(self, parent: int, delta: pm.vec3, budget: int) -> int:
        if budget <= 0:
            return budget

        proc = self.proc
        children = proc.read(parent + off.SCENECOMPONENT_ATTACH_CHILDREN, pm.mem.ptr)
        count = proc.read(parent + off.SCENECOMPONENT_ATTACH_CHILDREN + 8, pm.mem.i32)
        if children is None or count is None:
            return budget

        for index in range(min(count, MAX_CHILDREN)):
            if budget <= 0:
                return budget
            child = proc.read(children + index * 8, pm.mem.ptr)
            if not child:
                continue
            budget -= 1
            current = proc.read(
                child + off.SCENECOMPONENT_COMPONENT_TO_WORLD_TRANSLATION,
                pm.mem.vec3,
            )
            if current is not None:
                proc.write(
                    child + off.SCENECOMPONENT_COMPONENT_TO_WORLD_TRANSLATION,
                    current + delta,
                )
            budget = self._move_children(child, delta, budget)
        return budget
