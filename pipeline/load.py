"""Load: write transformed rows into PostgreSQL without creating duplicates.

For each source, inside ONE transaction for the whole run:
  1. COPY the clean rows into a temporary staging table.
  2. Reject staging rows whose parent row does not exist (for example an
     item pointing to an unknown order) and save them to etl.rejected_rows.
  3. Upsert into the target table with INSERT ... ON CONFLICT (primary key).
     - new key            -> inserted
     - key exists, changed -> updated
     - key exists, same    -> untouched (the WHERE ... IS DISTINCT FROM skips it)

Running the same files again therefore inserts 0 rows and updates 0 rows.
If anything fails, the whole run is rolled back, so the tables never hold a
half-loaded state.
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg import sql

from .config import Source
from .transform import Transformed


@dataclass
class LoadStats:
    source_file: str
    sha256: str
    rows_read: int
    exact_duplicates_dropped: int
    rows_rejected: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int


def _save_transform_rejects(cur: psycopg.Cursor, run_id: int, t: Transformed) -> None:
    if not t.rejected:
        return
    with cur.copy(
        "COPY etl.rejected_rows (run_id, source_file, row_number, reason, raw_record) FROM STDIN"
    ) as copy:
        for r in t.rejected:
            copy.write_row((run_id, t.extracted.source.file_name, r.row_number, r.reason,
                            psycopg.types.json.Jsonb(r.raw)))


def _stage(cur: psycopg.Cursor, source: Source, t: Transformed) -> sql.Identifier:
    staging = sql.Identifier(f"stg_{source.table}")
    cols = list(source.columns)
    # same column types as the target table, plus the CSV row number
    cur.execute(
        sql.SQL(
            "CREATE TEMP TABLE {stg} ON COMMIT DROP AS "
            "SELECT NULL::integer AS _row_number, {cols} FROM olist.{tbl} WITH NO DATA"
        ).format(
            stg=staging,
            cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
            tbl=sql.Identifier(source.table),
        )
    )
    copy_sql = sql.SQL("COPY {stg} (_row_number, {cols}) FROM STDIN").format(
        stg=staging, cols=sql.SQL(", ").join(map(sql.Identifier, cols))
    )
    with cur.copy(copy_sql) as copy:
        for row in t.clean[["_row_number", *cols]].itertuples(index=False, name=None):
            copy.write_row(row)
    return staging


def _reject_orphans(cur: psycopg.Cursor, run_id: int, source: Source, staging: sql.Identifier) -> int:
    rejected = 0
    for child_cols, parent_table, parent_cols in source.references:
        match = sql.SQL(" AND ").join(
            sql.SQL("p.{pc} = s.{cc}").format(pc=sql.Identifier(pc), cc=sql.Identifier(cc))
            for cc, pc in zip(child_cols, parent_cols)
        )
        reason = f"unknown_{parent_table}_reference:{','.join(child_cols)}"
        cur.execute(
            sql.SQL(
                """
                WITH orphans AS (
                    DELETE FROM {stg} s
                    WHERE NOT EXISTS (SELECT 1 FROM olist.{parent} p WHERE {match})
                    RETURNING s.*
                )
                INSERT INTO etl.rejected_rows (run_id, source_file, row_number, reason, raw_record)
                SELECT %s, %s, _row_number, %s, to_jsonb(orphans) - '_row_number'
                FROM orphans
                """
            ).format(stg=staging, parent=sql.Identifier(parent_table), match=match),
            (run_id, source.file_name, reason),
        )
        rejected += cur.rowcount
    return rejected


def _upsert(cur: psycopg.Cursor, run_id: int, source: Source, staging: sql.Identifier) -> tuple[int, int]:
    cols = list(source.columns)
    non_key = [c for c in cols if c not in source.primary_key]
    target = sql.Identifier("olist", source.table)
    query = sql.SQL(
        """
        INSERT INTO {target} AS t ({cols}, last_run_id)
        SELECT {cols}, %s FROM {stg}
        ON CONFLICT ({pk}) DO UPDATE
            SET {assignments}, last_run_id = EXCLUDED.last_run_id
            WHERE ({t_cols}) IS DISTINCT FROM ({ex_cols})
        RETURNING (xmax = 0) AS inserted
        """
    ).format(
        target=target,
        stg=staging,
        cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
        pk=sql.SQL(", ").join(map(sql.Identifier, source.primary_key)),
        assignments=sql.SQL(", ").join(
            sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in non_key
        ),
        t_cols=sql.SQL(", ").join(sql.SQL("t.{c}").format(c=sql.Identifier(c)) for c in non_key),
        ex_cols=sql.SQL(", ").join(sql.SQL("EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in non_key),
    )
    cur.execute(query, (run_id,))
    flags = [row[0] for row in cur.fetchall()]
    inserted = sum(flags)
    return inserted, len(flags) - inserted


def load_source(cur: psycopg.Cursor, run_id: int, t: Transformed) -> LoadStats:
    source = t.extracted.source
    _save_transform_rejects(cur, run_id, t)
    staging = _stage(cur, source, t)
    orphans = _reject_orphans(cur, run_id, source, staging)
    inserted, updated = _upsert(cur, run_id, source, staging)
    loadable = len(t.clean) - orphans
    stats = LoadStats(
        source_file=source.file_name,
        sha256=t.extracted.sha256,
        rows_read=t.rows_read,
        exact_duplicates_dropped=t.exact_duplicates_dropped,
        rows_rejected=len(t.rejected) + orphans,
        rows_inserted=inserted,
        rows_updated=updated,
        rows_unchanged=loadable - inserted - updated,
    )
    cur.execute(
        """
        INSERT INTO etl.file_loads (run_id, source_file, file_sha256, rows_read,
            exact_duplicates_dropped, rows_rejected, rows_inserted, rows_updated, rows_unchanged)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (run_id, stats.source_file, stats.sha256, stats.rows_read, stats.exact_duplicates_dropped,
         stats.rows_rejected, stats.rows_inserted, stats.rows_updated, stats.rows_unchanged),
    )
    return stats
