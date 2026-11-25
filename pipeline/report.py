"""Print the run history: every run, its status, and per-file counts.

    python -m pipeline.report
    python -m pipeline.report --dbname olist_demo
"""
from __future__ import annotations

import argparse

import psycopg

from .config import db_settings

RUNS_SQL = """
SELECT r.run_id, r.status, to_char(r.started_at, 'YYYY-MM-DD HH24:MI:SS') AS started,
       round(extract(epoch FROM r.finished_at - r.started_at)::numeric, 1) AS seconds,
       COALESCE(sum(f.rows_read), 0) AS read, COALESCE(sum(f.rows_rejected), 0) AS rejected,
       COALESCE(sum(f.rows_inserted), 0) AS inserted, COALESCE(sum(f.rows_updated), 0) AS updated,
       COALESCE(sum(f.rows_unchanged), 0) AS unchanged, COALESCE(r.error, '') AS error
FROM etl.pipeline_runs r
LEFT JOIN etl.file_loads f USING (run_id)
GROUP BY r.run_id
ORDER BY r.run_id
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Show pipeline run history")
    parser.add_argument("--dbname")
    args = parser.parse_args(argv)

    with psycopg.connect(**db_settings(args.dbname)) as conn:
        rows = conn.execute(RUNS_SQL).fetchall()
        rejects = conn.execute(
            "SELECT run_id, source_file, reason, COUNT(*) FROM etl.rejected_rows "
            "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
        ).fetchall()

    print(f"{'run':>4} {'status':<8} {'started':<20}{'sec':>6}{'read':>9}{'rejected':>10}"
          f"{'inserted':>10}{'updated':>9}{'unchanged':>11}  error")
    for run_id, status, started, seconds, read, rej, ins, upd, unch, error in rows:
        print(f"{run_id:>4} {status:<8} {started:<20}{seconds or 0:>6}{read:>9}{rej:>10}"
              f"{ins:>10}{upd:>9}{unch:>11}  {error[:60]}")
    if rejects:
        print("\nRejected rows by reason:")
        for run_id, source_file, reason, n in rejects:
            print(f"  run {run_id}  {source_file:<34} {reason:<45} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
