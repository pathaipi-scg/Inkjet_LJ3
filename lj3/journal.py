"""Durable, append-only local journal used as the DB outage/recovery source."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
from typing import Any, Iterable

from .config import PROJECT_ROOT


class TransactionJournal:
    def __init__(self, path: Path | None = None):
        self.path = path or PROJECT_ROOT / "logs" / "pending_transactions.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(line + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def pending_records(self) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return ()
        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Local transaction journal is corrupt at line {line_number}.") from exc
            if not isinstance(value, dict) or not value.get("transaction_id"):
                raise ValueError(f"Local transaction journal entry {line_number} is invalid.")
            records.append(value)
        return tuple(records)


def as_iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds")
