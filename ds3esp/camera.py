from __future__ import annotations

import math

from . import offsets as off
from .process import GameProcess, is_valid_ptr
from .structs import CameraPOV


class Camera:
    __slots__ = (
        "x",
        "y",
        "z",
        "pitch",
        "yaw",
        "roll",
        "fov",
        "fwd",
        "right",
        "up",
    )

    def __init__(self, location, rotation, fov: float):
        self.x, self.y, self.z = location.x, location.y, location.z
        self.pitch, self.yaw, self.roll = rotation.x, rotation.y, rotation.z
        self.fov = fov
        self.fwd, self.right, self.up = self._axes()

    @classmethod
    def read(cls, proc: GameProcess, manager: int) -> Camera | None:
        if not is_valid_ptr(manager):
            return None

        pov = proc.read(
            manager + off.CAMERA_MANAGER_CAMERA_CACHE + off.CAMERA_CACHE_ENTRY_POV,
            CameraPOV,
        )
        if pov is None or (pov.location.x == 0 and pov.location.y == 0 and pov.location.z == 0):
            return None

        return cls(pov.location, pov.rotation, float(pov.fov))

    def _axes(self):
        pitch = math.radians(self.pitch)
        yaw = math.radians(self.yaw)
        roll = math.radians(self.roll)
        sp, cp = math.sin(pitch), math.cos(pitch)
        sy, cy = math.sin(yaw), math.cos(yaw)
        sr, cr = math.sin(roll), math.cos(roll)

        fwd = (cp * cy, cp * sy, sp)
        right = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, sr * cp)
        up = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
        return fwd, right, up

    def distance(self, wx: float, wy: float, wz: float) -> float:
        dx, dy, dz = wx - self.x, wy - self.y, wz - self.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def project(self, wx: float, wy: float, wz: float, sw: float, sh: float) -> tuple[float, float, float] | None:
        dx, dy, dz = wx - self.x, wy - self.y, wz - self.z
        fx, fy, fz = self.fwd
        depth = dx * fx + dy * fy + dz * fz
        if depth < 1.0:
            return None

        rx, ry, rz = self.right
        ux, uy, uz = self.up
        x = dx * rx + dy * ry + dz * rz
        y = dx * ux + dy * uy + dz * uz

        fov = self.fov
        if fov <= 1.0 or fov > 170.0:
            fov = 90.0
        scale = (sw * 0.5) / (depth * math.tan(math.radians(fov) * 0.5))
        return (sw * 0.5 + x * scale, sh * 0.5 - y * scale, depth)
