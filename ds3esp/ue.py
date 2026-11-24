from __future__ import annotations

import sys
from array import array
from typing import Callable

import pymew as pm

from . import offsets as off
from .process import GameNotReady, GameProcess, is_valid_ptr
from .structs import (
    FactionAffiliation,
    FactionSettings,
    ULevel,
    UStructInfo,
    UWorld,
)

FNAME_BLOCK_BITS = 14
FNAME_BLOCK_SIZE = 1 << FNAME_BLOCK_BITS
FNAME_BLOCK_MASK = FNAME_BLOCK_SIZE - 1
FNAME_ENTRY_TEXT = 0x10
FNAME_ENTRY_READ = 0x10 + 0x100

MAX_CLASS_DEPTH = 40
MAX_LEVELS = 4096
MAX_ACTORS = 1_000_000
MAX_OBJECTS = 5_000_000
MAX_AFFILIATIONS = 512

Progress = Callable[[int, int], None] | None


def u64_values(raw: bytes) -> array:
    values = array("Q")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    return values


class ClassInfo:
    __slots__ = ("name", "size", "super")

    def __init__(self, name: str, size: int, super_: int):
        self.name = name
        self.size = size
        self.super = super_


class FNamePool:
    def __init__(self, proc: GameProcess):
        self.proc = proc
        self._cache: dict[int, str] = {}
        self._alloc = proc.read(proc.base + off.G_NAMES, pm.mem.ptr)
        if not is_valid_ptr(self._alloc):
            raise GameNotReady("GNames is not readable (wrong module base?)")

    def get(self, index: int) -> str:
        if index < 0:
            return ""
        cached = self._cache.get(index)
        if cached is not None:
            return cached

        name = ""
        proc = self.proc
        block = proc.read(self._alloc + (index >> FNAME_BLOCK_BITS) * 8, pm.mem.ptr)
        if is_valid_ptr(block):
            entry = proc.read(block + (index & FNAME_BLOCK_MASK) * 8, pm.mem.ptr)
            if is_valid_ptr(entry):
                buf = proc.read(entry, pm.mem.bytes(FNAME_ENTRY_READ))
                if buf is None:
                    buf = proc.read(entry, pm.mem.bytes(0x40))
                if buf and len(buf) > FNAME_ENTRY_TEXT:
                    name = self._decode(buf)
        self._cache[index] = name
        return name

    @staticmethod
    def _decode(buf: bytes) -> str:
        text = buf[FNAME_ENTRY_TEXT:]
        if buf[0] & 1:
            end = 0
            while end + 1 < len(text) and not (text[end] == 0 and text[end + 1] == 0):
                end += 2
            return text[:end].decode("utf-16-le", "ignore")
        return text.split(b"\x00", 1)[0].decode("utf-8", "ignore")


class UnrealEngine:
    def __init__(self, proc: GameProcess):
        self.proc = proc
        self._names = FNamePool(proc)

        objects_addr = proc.base + off.G_OBJECTS
        self.objects_ptr = proc.read(objects_addr, pm.mem.ptr)
        self.objects_max = proc.read(objects_addr + 0x08, pm.mem.i32)
        self.objects_num = proc.read(objects_addr + 0x0C, pm.mem.i32)
        if (
            self.objects_ptr is None
            or self.objects_num is None
            or not is_valid_ptr(self.objects_ptr)
            or not 0 < self.objects_num <= MAX_OBJECTS
            or (self.objects_max or 0) < self.objects_num
        ):
            raise GameNotReady(f"GObjects implausible (ptr={self.objects_ptr}, max={self.objects_max}, " f"num={self.objects_num})")

        self._class_cache: dict[int, ClassInfo | None] = {}
        self._ancestry_cache: dict[int, tuple[str, ...]] = {}
        self._label_cache: dict[int, str] = {}
        self._object_cache: list[int] | None = None

    def reset_class_caches(self) -> None:
        self._class_cache.clear()
        self._ancestry_cache.clear()
        self._label_cache.clear()
        self._object_cache = None

    def world(self) -> int:
        value = self.proc.read(self.proc.base + off.G_WORLD, pm.mem.ptr)
        return value if value and is_valid_ptr(value) else 0

    def world_data(self) -> UWorld | None:
        world = self.world()
        return self.proc.read(world, UWorld) if world else None

    def level_actors(self) -> list[int]:
        data = self.world_data()
        if data is None:
            return []

        levels: list[int] = []
        seen: set[int] = set()

        def add_level(level: int) -> None:
            if level and level not in seen and is_valid_ptr(level):
                seen.add(level)
                levels.append(level)

        add_level(data.persistent_level)
        if is_valid_ptr(data.levels.data) and 0 < data.levels.count <= MAX_LEVELS:
            raw = self.proc.read_bytes(data.levels.data, data.levels.count * 8)
            if raw:
                for value in u64_values(raw):
                    add_level(value)

        actors: list[int] = []
        for level in levels:
            level_data = self.proc.read(level, ULevel)
            if level_data is None or not is_valid_ptr(level_data.actors.data):
                continue
            count = level_data.actors.count
            if not 0 < count <= MAX_ACTORS:
                continue
            raw = self.proc.read_bytes(level_data.actors.data, count * 8)
            if raw is None:
                continue
            for value in u64_values(raw):
                if value:
                    actors.append(value)
        return actors

    def object_pointers(self) -> list[int]:
        if self._object_cache is not None:
            return self._object_cache

        values = self.proc.read(
            self.objects_ptr,
            pm.mem.array(pm.mem.ptr, self.objects_num, stride=off.FUOBJECT_ITEM_SIZE),
        )
        if values is None:
            values = self._object_pointers_bytes()
        self._object_cache = [v for v in values if v and is_valid_ptr(v)]
        return self._object_cache

    def _object_pointers_bytes(self) -> list[int]:
        raw = self.proc.read_bytes(self.objects_ptr, self.objects_num * off.FUOBJECT_ITEM_SIZE)
        if raw is None:
            return []
        stride = off.FUOBJECT_ITEM_SIZE // 8
        return [value for value in u64_values(raw)[::stride] if value]

    def class_info(self, cls: int) -> ClassInfo | None:
        if cls in self._class_cache:
            return self._class_cache[cls]
        info = None
        if is_valid_ptr(cls):
            data = self.proc.read(cls, UStructInfo)
            if data is not None and 0 < data.size < 0x80000:
                info = ClassInfo(
                    self._names.get(data.name_index),
                    data.size,
                    data.super if is_valid_ptr(data.super) else 0,
                )
        self._class_cache[cls] = info
        return info

    def class_name(self, cls: int) -> str:
        info = self.class_info(cls)
        return info.name if info else ""

    def class_label(self, cls: int) -> str:
        cached = self._label_cache.get(cls)
        if cached is None:
            cached = short_name(self.class_name(cls) or f"{cls:#x}")
            self._label_cache[cls] = cached
        return cached

    def class_of(self, obj: int) -> int:
        value = self.proc.read(obj + off.UOBJECT_CLASS, pm.mem.ptr)
        return value if value and is_valid_ptr(value) else 0

    def meta_class(self, cls: int) -> int:
        value = self.proc.read(cls + off.UOBJECT_CLASS, pm.mem.ptr)
        return value if value and is_valid_ptr(value) else 0

    def class_size(self, cls: int) -> int:
        info = self.class_info(cls)
        return info.size if info else 0

    def super_struct(self, cls: int) -> int:
        info = self.class_info(cls)
        return info.super if info else 0

    def ancestry(self, cls: int) -> tuple[str, ...]:
        cached = self._ancestry_cache.get(cls)
        if cached is not None:
            return cached
        names: list[str] = []
        current = cls
        for _ in range(MAX_CLASS_DEPTH):
            if not current:
                break
            info = self.class_info(current)
            if info is None:
                break
            names.append(info.name)
            current = info.super
        result = tuple(names)
        self._ancestry_cache[cls] = result
        return result

    def ancestor_with_size(self, cls: int, size: int) -> int:
        current = cls
        for _ in range(MAX_CLASS_DEPTH):
            info = self.class_info(current)
            if info is None:
                return 0
            if info.size == size:
                return current
            current = info.super
        return 0

    def find_class_by_size(self, size: int, super_size: int) -> int:
        for obj in self.object_pointers():
            cls = self.class_of(obj)
            if not cls or self.class_size(cls) != size:
                continue
            sup = self.super_struct(cls)
            if sup and self.class_size(sup) == super_size:
                return cls
        return 0

    def find_faction_settings(self, meta: int, progress: Progress = None) -> int:
        objects = self.object_pointers()
        total = len(objects)
        best = 0
        best_n = 0
        step = 65536

        for index, obj in enumerate(objects):
            if progress is not None and index % step == 0:
                progress(index, total)
            cls = self.proc.read(obj + off.UOBJECT_CLASS, pm.mem.ptr)
            if not cls or self.class_size(cls) != off.UFACTIONSETTINGS_SIZE:
                continue
            sup = self.super_struct(cls)
            if not sup or self.class_size(sup) != off.UOBJECT_SIZE:
                continue
            data = self.proc.read(obj, FactionSettings)
            if data is None:
                continue
            count = data.affiliations.count
            pointer = data.affiliations.data
            if not 1 <= count <= MAX_AFFILIATIONS or not is_valid_ptr(pointer):
                continue
            if not self._valid_affiliations(pointer, count, meta):
                continue
            if count > best_n:
                best, best_n = obj, count
        if progress is not None:
            progress(total, total)
        return best

    def _valid_affiliations(self, pointer: int, count: int, meta: int) -> bool:
        for index in range(min(count, 4)):
            entry = self.proc.read(pointer + index * off.FFACTION_AFFILIATION_SIZE, FactionAffiliation)
            if entry is None or entry.affiliation > 3:
                return False
            for faction in (entry.faction1, entry.faction2):
                if not is_valid_ptr(faction):
                    return False
                if self.class_size(faction) != off.UFACTION_SIZE:
                    return False
                if self.proc.read(faction + off.UOBJECT_CLASS, pm.mem.ptr) != meta:
                    return False
        return True

    def read_affiliations(self, settings: int) -> dict[tuple[int, int], int]:
        data = self.proc.read(settings, FactionSettings)
        matrix: dict[tuple[int, int], int] = {}
        if data is None or not is_valid_ptr(data.affiliations.data):
            return matrix
        count = data.affiliations.count
        if not 0 < count <= MAX_AFFILIATIONS:
            return matrix
        for index in range(count):
            entry = self.proc.read(
                data.affiliations.data + index * off.FFACTION_AFFILIATION_SIZE,
                FactionAffiliation,
            )
            if entry is None:
                continue
            key = (entry.faction1, entry.faction2)
            matrix[key] = entry.affiliation
            matrix[(entry.faction2, entry.faction1)] = entry.affiliation
        return matrix


def short_name(name: str) -> str:
    if "." in name:
        name = name.rsplit(".", 1)[1]
    for char in "~?":
        index = name.find(char)
        if index >= 0:
            name = name[:index]
    if name.endswith("_C"):
        name = name[:-2]
    for prefix in ("Character_", "Item_"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name or "?"
