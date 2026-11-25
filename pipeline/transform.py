"""Transform: clean and type one extracted file.

Rules, in order:
  1. Trim spaces; empty cells become NULL.
  2. Exact duplicate rows (every column equal) are dropped and counted.
     They carry no new information, so keeping one copy loses nothing.
  3. Each value is cast to its target type. A row is rejected (not loaded,
     but saved to etl.rejected_rows with the reason) when:
       - a required column is empty
       - a value cannot be cast (bad number, bad date, bad state code)
       - a money value is negative or has more than 2 decimal places
  4. Rows that share a primary key but have different content are ALL
     rejected. With two different versions of the same order item we cannot
     know which one is true, and picking one would silently change totals.

Money is parsed with Decimal, never float, so 0.10 + 0.20 is exactly 0.30.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from .extract import Extracted

MONEY_RE = re.compile(r"^\d+(\.\d{1,2})?$")
INT_RE = re.compile(r"^\d+(\.0+)?$")     # also accepts "40.0", common in spreadsheet exports
STATE_RE = re.compile(r"^[A-Z]{2}$")
TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass
class Rejected:
    row_number: int
    reason: str
    raw: dict[str, str]


@dataclass
class Transformed:
    extracted: Extracted
    rows_read: int
    exact_duplicates_dropped: int
    clean: pd.DataFrame          # typed values, plus _row_number
    rejected: list[Rejected]


def _cast_column(values: pd.Series, col_type: str, col: str) -> tuple[pd.Series, pd.Series]:
    """Return (typed values, error reason per row or None)."""
    present = values.notna()
    errors = pd.Series([None] * len(values), index=values.index, dtype=object)

    if col_type == "text":
        return values, errors

    if col_type == "status":
        return values.str.lower(), errors

    if col_type == "state":
        upper = values.str.upper()
        bad = present & ~upper.fillna("").str.match(STATE_RE)
        errors[bad] = f"invalid_state:{col}"
        return upper, errors

    if col_type == "int":
        ok = values.fillna("").str.match(INT_RE)
        bad = present & ~ok
        errors[bad] = f"invalid_integer:{col}"
        typed = pd.Series(
            [int(float(v)) if isinstance(v, str) and good else None for v, good in zip(values, ok)],
            index=values.index, dtype=object,
        )
        return typed, errors

    if col_type == "money":
        ok = values.fillna("").str.match(MONEY_RE)
        bad = present & ~ok
        errors[bad] = f"invalid_amount:{col}"
        typed = pd.Series(
            [Decimal(v) if isinstance(v, str) and good else None for v, good in zip(values, ok)],
            index=values.index, dtype=object,
        )
        return typed, errors

    if col_type == "timestamp":
        parsed = pd.to_datetime(values, format=TIMESTAMP_FORMAT, errors="coerce")
        bad = present & parsed.isna()
        errors[bad] = f"invalid_timestamp:{col}"
        typed = pd.Series(
            [None if pd.isna(v) else v.to_pydatetime() for v in parsed],
            index=values.index, dtype=object,
        )
        return typed, errors

    raise ValueError(f"unknown column type {col_type!r} for {col}")


def transform(extracted: Extracted) -> Transformed:
    source = extracted.source
    business_cols = list(source.columns)
    frame = extracted.frame.copy()
    rows_read = len(frame)

    # 1. trim, empty -> NULL
    for col in business_cols:
        frame[col] = frame[col].str.strip().replace("", None)

    # 2. exact duplicates
    dup_mask = frame.duplicated(subset=business_cols, keep="first")
    exact_duplicates = int(dup_mask.sum())
    frame = frame[~dup_mask]

    raw_view = frame[business_cols].fillna("")
    reasons = pd.Series([None] * len(frame), index=frame.index, dtype=object)

    def add_reasons(new: pd.Series) -> None:
        # keep the first reason found for each row
        fill = reasons.isna() & new.notna()
        reasons[fill] = new[fill]

    # 3a. required columns
    for col in source.required:
        missing = frame[col].isna()
        add_reasons(pd.Series(f"missing_required:{col}", index=frame.index).where(missing))

    # 3b. types
    typed = pd.DataFrame(index=frame.index)
    typed["_row_number"] = frame["_row_number"]
    for col, col_type in source.columns.items():
        values, errors = _cast_column(frame[col], col_type, col)
        typed[col] = values
        add_reasons(errors)

    # 4. same key, different content
    valid = reasons.isna()
    key_dup = typed[valid].duplicated(subset=source.primary_key, keep=False)
    conflicting_idx = key_dup[key_dup].index
    reasons[conflicting_idx] = "conflicting_duplicate_key"

    rejected_mask = reasons.notna()
    rejected = [
        Rejected(
            row_number=int(frame.at[idx, "_row_number"]),
            reason=str(reasons[idx]),
            raw=raw_view.loc[idx].to_dict(),
        )
        for idx in frame.index[rejected_mask]
    ]
    clean = typed[~rejected_mask].reset_index(drop=True)
    # make sure NaN never reaches the database as a value
    clean = clean.astype(object).where(clean.notna(), None)

    return Transformed(
        extracted=extracted,
        rows_read=rows_read,
        exact_duplicates_dropped=exact_duplicates,
        clean=clean,
        rejected=rejected,
    )
