from __future__ import annotations

import pymew as pm

from . import offsets as off
from .camera import Camera
from .process import GameProcess, is_valid_ptr
from .structs import APlayerController, UGameInstance, ULocalPlayer
from .ue import Progress, UnrealEngine

MAX_FACTION_DEPTH = 8


class GameContext:
    def __init__(self, ue: UnrealEngine):
        self.ue = ue
        self.proc: GameProcess = ue.proc
        self.player_controller = 0
        self.camera_manager = 0
        self.pawn = 0
        self.pawn_class = 0
        self.char_class = 0
        self.player_faction = 0
        self.faction_settings = 0
        self.affiliations: dict[tuple[int, int], int] = {}
        self.level = 0
        self._faction_chains: dict[int, tuple[int, ...]] = {}

    @classmethod
    def create(cls, ue: UnrealEngine, progress: Progress = None) -> "GameContext":
        ctx = cls(ue)
        ctx.refresh(progress)
        return ctx

    def refresh(self, progress: Progress = None) -> bool:
        ue = self.ue
        proc = self.proc

        world_data = ue.world_data()
        if world_data is None:
            return False

        game_instance = world_data.owning_game_instance
        if not is_valid_ptr(game_instance):
            return False
        instance = proc.read(game_instance, UGameInstance)
        if instance is None:
            return False
        players = instance.local_players
        if not is_valid_ptr(players.data) or players.count < 1:
            return False

        local_player = proc.read(players.data, pm.mem.ptr)
        if not is_valid_ptr(local_player):
            return False
        local = proc.read(local_player, ULocalPlayer)
        if local is None or not is_valid_ptr(local.player_controller):
            return False

        controller = proc.read(local.player_controller, APlayerController)
        if controller is None:
            return False
        pawn = controller.acknowledged_pawn
        if not is_valid_ptr(pawn):
            pawn = controller.pawn
        if not is_valid_ptr(pawn):
            return False

        self.level = world_data.persistent_level
        self.player_controller = local.player_controller
        self.camera_manager = controller.camera_manager
        self.set_pawn(pawn)
        if not self.faction_settings:
            self.resolve_factions(progress)
        return True

    def set_pawn(self, pawn: int) -> None:
        self.player_faction = self.proc.read(pawn + off.CHARGUNFIRE_FACTION, pm.mem.ptr) or 0
        if pawn == self.pawn:
            return

        self.pawn = pawn
        self.pawn_class = self.ue.class_of(pawn)
        self._faction_chains.clear()
        self.resolve_char_class()

    def resolve_char_class(self) -> int:
        cls = self.ue.ancestor_with_size(self.pawn_class, off.CHARGUNFIRE_SIZE)
        if not cls:
            cls = self.ue.find_class_by_size(off.CHARGUNFIRE_SIZE, off.ACHARACTER_SIZE)
        self.char_class = cls
        return cls

    def resolve_factions(self, progress: Progress = None) -> None:
        if not self.pawn_class:
            return
        meta = self.ue.meta_class(self.pawn_class)
        if not meta:
            return
        settings = self.ue.find_faction_settings(meta, progress)
        self.faction_settings = settings
        if settings:
            self.affiliations = self.ue.read_affiliations(settings)
            self._faction_chains.clear()

    def camera(self) -> Camera | None:
        return Camera.read(self.proc, self.camera_manager)

    def faction_chain(self, faction: int) -> tuple[int, ...]:
        if not faction:
            return ()
        cached = self._faction_chains.get(faction)
        if cached is not None:
            return cached

        chain: list[int] = []
        current = faction
        for _ in range(MAX_FACTION_DEPTH):
            if not is_valid_ptr(current):
                break
            chain.append(current)
            current = self.proc.read(current + off.UFACTION_INHERIT_AFFILIATIONS, pm.mem.ptr) or 0
        result = tuple(chain)
        self._faction_chains[faction] = result
        return result

    def affiliation(self, faction1: int, faction2: int) -> int:
        if faction1 and faction1 == faction2:
            return off.AFFILIATION_FRIENDLY
        if not self.affiliations:
            return off.AFFILIATION_NEUTRAL
        for first in self.faction_chain(faction1):
            for second in self.faction_chain(faction2):
                value = self.affiliations.get((first, second))
                if value is not None:
                    return value
        return off.AFFILIATION_NEUTRAL

    def is_hostile(self, faction: int) -> bool:
        return self.affiliation(self.player_faction, faction) == off.AFFILIATION_HOSTILE

    def describe(self) -> str:
        ue = self.ue
        char = ue.class_label(self.char_class) if self.char_class else "unknown"
        return (
            f"pawn {self.pawn:#x} ({ue.class_label(self.pawn_class)}) | "
            f"PC {self.player_controller:#x} | cam {self.camera_manager:#x} | "
            f"ACharacterGunfire {char} ({self.char_class:#x}) | "
            f"factions {len(self.affiliations)} entries"
        )
