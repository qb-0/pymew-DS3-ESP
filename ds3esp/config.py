from __future__ import annotations

import configparser
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class Config:
    exe: str = "Darksiders3-Win64-Shipping.exe"
    font: str = ""
    min_box_px: int = 20
    scan_ms: int = 200
    debug: bool = False
    fps: int = 0
    exit_key: str = "end"

    @classmethod
    def load(cls, path: Path) -> "Config":
        config = cls()
        if not path.is_file():
            return config

        parser = configparser.ConfigParser()
        parser.read(path)
        if not parser.has_section("esp"):
            return config
        section = parser["esp"]
        for item in fields(cls):
            if item.name not in section:
                continue
            current = getattr(config, item.name)
            value: object
            if isinstance(current, bool):
                value = section.getboolean(item.name)
            elif isinstance(current, int):
                value = section.getint(item.name)
            else:
                value = section[item.name]
            setattr(config, item.name, value)
        return config
