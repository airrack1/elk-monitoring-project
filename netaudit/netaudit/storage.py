"""Engagement persistence.

Each engagement is a single JSON file under the workspace (default
~/.netaudit/engagements). Plain files keep the data portable, diff-able, and
easy to back up per the evidence-retention requirement.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from .models import Engagement


def workspace_dir() -> Path:
    base = os.environ.get("NETAUDIT_HOME", str(Path.home() / ".netaudit"))
    return Path(base)


def engagements_dir() -> Path:
    d = workspace_dir() / "engagements"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(eng_id: str) -> Path:
    return engagements_dir() / f"{eng_id}.json"


def save(eng: Engagement) -> Path:
    path = _path_for(eng.id)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(eng.to_dict(), indent=2), encoding="utf-8")
    tmp.replace(path)  # atomic write
    return path


def load(eng_id: str) -> Engagement:
    path = _path_for(eng_id)
    if not path.exists():
        # allow loading by name as a convenience
        match = _find_by_name(eng_id)
        if match is None:
            raise FileNotFoundError(f"No engagement with id/name '{eng_id}'")
        path = match
    data = json.loads(path.read_text(encoding="utf-8"))
    return Engagement.from_dict(data)


def _find_by_name(name: str) -> Optional[Path]:
    for path in engagements_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("name") == name:
            return path
    return None


def list_all() -> List[dict]:
    out = []
    for path in sorted(engagements_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(data)
    return out
