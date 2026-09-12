"""Persisted filter preferences, kept next to the SQLite cache so repeat
sessions against the same dump set reopen with the same scope."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def config_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.stem + ".filters.json")


def load_filters(db_path: Path) -> dict[str, Any] | None:
    path = config_path(db_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def save_filters(db_path: Path, data: dict[str, Any]) -> None:
    path = config_path(db_path)
    try:
        path.write_text(json.dumps(data, indent=2))
    except OSError:
        pass
