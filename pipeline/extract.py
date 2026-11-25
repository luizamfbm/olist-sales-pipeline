"""Extract: read a source CSV exactly as it is, with every value as text.

Reading everything as text means pandas never guesses a type (for example,
turning zip code "01310" into the number 1310). Typing happens in transform.py,
where every failure is recorded instead of silently becoming NaN.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import Source


class MissingFileError(FileNotFoundError):
    pass


class SchemaError(ValueError):
    pass


@dataclass
class Extracted:
    source: Source
    path: Path
    sha256: str
    frame: pd.DataFrame  # all columns as str, empty cells as "", plus a _row_number column


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract(source: Source, data_dir: Path) -> Extracted:
    path = data_dir / source.file_name
    if not path.exists():
        raise MissingFileError(f"{source.file_name} not found in {data_dir}")

    frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    frame = frame.rename(columns=source.renames)

    missing = [c for c in source.columns if c not in frame.columns]
    if missing:
        raise SchemaError(f"{source.file_name} is missing columns: {missing}")

    frame = frame[list(source.columns)].copy()
    # 1 = first data row after the header; used to point at rejected rows
    frame.insert(0, "_row_number", range(1, len(frame) + 1))
    return Extracted(source=source, path=path, sha256=file_sha256(path), frame=frame)
