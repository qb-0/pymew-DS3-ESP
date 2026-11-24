import pymew as pm


class EspError(RuntimeError):
    pass


class GameNotReady(EspError):
    pass


def is_valid_ptr(value: int) -> bool:
    return 0x10000 < value < 0x7FFFFFFFFFFF


class GameProcess:
    def __init__(self, proc: pm.Process, base: int):
        self.p = proc
        self.base = base

    @classmethod
    def attach(cls, exe: str) -> "GameProcess":
        try:
            proc = pm.mem.open(exe)
        except pm.errors.Error as exc:
            raise EspError(f"cannot open {exe!r}: {exc} - is the game running?") from exc

        try:
            base = proc.base(module=exe)
        except pm.errors.Error as exc:
            proc.close()
            raise EspError(f"module {exe!r} not found in pid {proc.pid()}: {exc}") from exc

        if not is_valid_ptr(base):
            proc.close()
            raise EspError(f"implausible module base {base:#x} for {exe!r}")
        return cls(proc, base)

    @property
    def pid(self) -> int:
        return self.p.pid()

    def alive(self) -> bool:
        return self.p.alive()

    def close(self) -> None:
        self.p.close()

    def __enter__(self) -> "GameProcess":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def read(self, address: int, desc):
        if not is_valid_ptr(address):
            return None
        try:
            return self.p.read(address, desc)
        except pm.errors.Error:
            return None

    def read_bytes(self, address: int, size: int):
        return self.read(address, pm.mem.bytes(size))

    def write(self, address: int, value) -> bool:
        if not is_valid_ptr(address):
            return False
        try:
            return self.p.write(address, value) > 0
        except pm.errors.Error:
            return False
