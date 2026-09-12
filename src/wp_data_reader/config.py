"""Persisted per-dump-set settings (filters, local uploads path), kept next
to the SQLite cache so repeat sessions against the same dump set reopen with
the same preferences."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def config_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.stem + ".filters.json")


def load_settings(db_path: Path) -> dict[str, Any]:
    path = config_path(db_path)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(db_path: Path, **patch: Any) -> None:
    """Merge ``patch`` into the existing settings file rather than
    overwriting it, so independent features (filters, uploads dir) saving at
    different times don't clobber each other's keys."""
    data = load_settings(db_path)
    data.update(patch)
    path = config_path(db_path)
    try:
        path.write_text(json.dumps(data, indent=2))
    except OSError:
        pass
