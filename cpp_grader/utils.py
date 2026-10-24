from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


def norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def json_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_relative(path: Path) -> Path:
    """Return a normalized relative path; reject traversal/absolute paths."""
    if path.is_absolute() or any(part in {"..", ""} for part in path.parts):
        raise ValueError(f"Unsafe relative path: {path}")
    return path


def atomic_json(path: Path, value: Any) -> None:
    json_write(path, value)
