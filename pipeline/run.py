"""Run the pipeline end to end.

    python -m pipeline.run --data-dir data
    python -m pipeline.run --data-dir data --results-dir results

Steps:
  1. Create the schema if needed and open a run in etl.pipeline_runs.
  2. Extract and transform ALL files first. A missing file or a missing column
     stops the run before anything is written to the business tables.
  3. Load every file in one transaction (parents before children), then run
     the data quality checks.
  4. Commit and mark the run as success. On any error: roll back, mark the
     run as failed with the error message, and exit with code 1.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg import sql

from .config import SOURCES, db_settings
from .extract import extract
from .load import LoadStats, load_source
from .quality import run_checks
from .queries import export_results
from .transform import transform

SCHEMA_SQL = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
# any fixed number works; it only has to be the same for every run
PIPELINE_LOCK_ID = 2026_10


@dataclass
class RunResult:
    run_id: int
    status: str
    file_stats: list[LoadStats] = field(default_factory=list)
    dq: list[tuple[str, int, str]] = field(default_factory=list)
    error: str | None = None


def ensure_database(settings: dict[str, str]) -> None:
    """Create the target database on first run, so setup is one command."""
    admin = {**settings, "dbname": "postgres"}
    with psycopg.connect(**admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings["dbname"],)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings["dbname"])))


def ensure_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        # schema creation is not concurrency-safe on its own; serialize it
        cur.execute("SELECT pg_advisory_lock(%s)", (PIPELINE_LOCK_ID + 1,))
        try:
            cur.execute(SCHEMA_SQL.read_text())
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", (PIPELINE_LOCK_ID + 1,))


def run_pipeline(data_dir: Path, dbname: str | None = None) -> RunResult:
    settings = db_settings(dbname)
    ensure_database(settings)

    # Log connection: autocommit, so the run record survives a rollback
    with psycopg.connect(**settings, autocommit=True) as log_conn:
        ensure_schema(log_conn)
        run_id = log_conn.execute(
            "INSERT INTO etl.pipeline_runs (status, data_dir) VALUES ('running', %s) RETURNING run_id",
            (str(data_dir),),
        ).fetchone()[0]
        result = RunResult(run_id=run_id, status="running")

        try:
            transformed = [transform(extract(source, data_dir)) for source in SOURCES]

            with psycopg.connect(**settings) as conn:
                with conn.transaction(), conn.cursor() as cur:
                    # two runs at the same time would wait for each other
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", (PIPELINE_LOCK_ID,))
                    for t in transformed:
                        result.file_stats.append(load_source(cur, run_id, t))
                    result.dq = run_checks(cur, run_id)

            result.status = "success"
            log_conn.execute(
                "UPDATE etl.pipeline_runs SET status = 'success', finished_at = now() WHERE run_id = %s",
                (run_id,),
            )
        except Exception as exc:  # record every failure, then re-raise
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            log_conn.execute(
                "UPDATE etl.pipeline_runs SET status = 'failed', finished_at = now(), error = %s "
                "WHERE run_id = %s",
                (result.error, run_id),
            )
            raise
    return result


def print_summary(result: RunResult) -> None:
    print(f"\nRun {result.run_id}: {result.status.upper()}")
    header = f"{'file':<36}{'read':>9}{'dup':>6}{'rejected':>10}{'inserted':>10}{'updated':>9}{'unchanged':>11}"
    print(header)
    print("-" * len(header))
    for s in result.file_stats:
        print(f"{s.source_file:<36}{s.rows_read:>9}{s.exact_duplicates_dropped:>6}{s.rows_rejected:>10}"
              f"{s.rows_inserted:>10}{s.rows_updated:>9}{s.rows_unchanged:>11}")
    if result.dq:
        print("\nData quality findings:")
        for name, count, _ in result.dq:
            print(f"  {name:<42}{count:>7}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Olist sales pipeline")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--results-dir", type=Path, help="export Q1-Q3 results as CSV here")
    parser.add_argument("--dbname", help="database name (default: $PGDATABASE or 'olist')")
    args = parser.parse_args(argv)

    try:
        result = run_pipeline(args.data_dir, args.dbname)
    except Exception as exc:
        print(f"Run FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print_summary(result)
    if args.results_dir:
        with psycopg.connect(**db_settings(args.dbname)) as conn:
            counts = export_results(conn, args.results_dir)
        print(f"\nResults written to {args.results_dir}/")
        for name, n in counts.items():
            print(f"  {name}.csv: {n} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
