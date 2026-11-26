"""In-process per-printer serialization; does not coordinate external clients."""

from threading import RLock

_registry_guard = RLock()
_locks: dict[tuple[str, int], RLock] = {}


def printer_lock(host: str, port: int) -> RLock:
    key = (host.strip().casefold(), port)
    with _registry_guard:
        return _locks.setdefault(key, RLock())
