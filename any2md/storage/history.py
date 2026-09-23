"""Recent conversion history — persisted to a JSON file."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

HISTORY_MAX = 50


@dataclass
class HistoryEntry:
    entry_id: str
    input_filename: str
    input_path: str
    output_path: str
    direction: str        # e.g. "PDF → Markdown"
    status: str           # "done" | "error"
    timestamp: str        # ISO 8601
    error_message: str = ""

    @property
    def timestamp_display(self) -> str:
        try:
            dt = datetime.fromisoformat(self.timestamp)
            return dt.strftime("%b %d, %H:%M")
        except ValueError:
            return self.timestamp


class HistoryStore:
    """JSON-backed recent conversion history."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        if data_dir is None:
            data_dir = Path.home() / ".any2md"
        self._path = data_dir / "history.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[HistoryEntry] = self._load()

    # ──────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────

    def add(self, entry: HistoryEntry) -> None:
        # Remove duplicates for same output path
        self._entries = [e for e in self._entries if e.output_path != entry.output_path]
        self._entries.insert(0, entry)
        self._entries = self._entries[:HISTORY_MAX]
        self._save()

    def get_all(self) -> list[HistoryEntry]:
        return list(self._entries)

    def remove(self, entry_id: str) -> None:
        self._entries = [e for e in self._entries if e.entry_id != entry_id]
        self._save()

    def clear(self) -> None:
        self._entries = []
        self._save()

    # ──────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────

    def _load(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [HistoryEntry(**item) for item in data]
        except Exception:
            return []

    def _save(self) -> None:
        try:
            self._path.write_text(
                json.dumps([asdict(e) for e in self._entries], indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass  # History is non-critical
