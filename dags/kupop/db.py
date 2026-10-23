"""Load: สร้างตารางและ UPSERT ลง PostgreSQL ปลายทาง (Airflow connection: kupop_db)"""
import json
import math

from airflow.providers.postgres.hooks.postgres import PostgresHook
from psycopg2.extras import execute_values

CONN_ID = "kupop_db"

DDL = """
CREATE TABLE IF NOT EXISTS admission_stats (
    source            TEXT NOT NULL,
    academic_year     INT  NOT NULL,
    source_record_id  TEXT NOT NULL,
    campus            TEXT,
    faculty           TEXT,
    program_name      TEXT,
    major_key         TEXT,
    project           TEXT,
    seats             INT,
    applicants        INT,
    enrolled          INT,
    min_score         NUMERIC(8,4),
    max_score         NUMERIC(8,4),
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source, academic_year, source_record_id)
);
CREATE TABLE IF NOT EXISTS program_summary (
    campus            TEXT NOT NULL,
    major_key         TEXT NOT NULL,
    faculty           TEXT,
    program_name      TEXT,
    sources           TEXT,
    n_sources         INT,
    n_source_rows     INT,
    latest_tcas_year  INT,
    applicants        INT,
    seats_r3          INT,
    competition_ratio NUMERIC(10,2),
    min_score         NUMERIC(8,4),
    max_score         NUMERIC(8,4),
    applicants_2567   INT,
    enrolled_2567     INT,
    seats_2570        INT,
    n_projects_2570   INT,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (campus, major_key)
);
CREATE TABLE IF NOT EXISTS dq_quarantine (
    id                SERIAL PRIMARY KEY,
    run_id            TEXT,
    source            TEXT,
    academic_year     INT,
    source_record_id  TEXT,
    reason            TEXT,
    payload           JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id            TEXT PRIMARY KEY,
    started_at        TIMESTAMPTZ,
    finished_at       TIMESTAMPTZ,
    status            TEXT,
    dq_branch         TEXT,
    sources_ok        TEXT,
    sources_failed    TEXT,
    rows_extracted    INT,
    rows_loaded       INT,
    rows_quarantined  INT,
    details           JSONB
);
"""

STATS_COLS = ["source", "academic_year", "source_record_id", "campus", "faculty", "program_name",
              "major_key", "project", "seats", "applicants", "enrolled", "min_score", "max_score"]
SUMMARY_COLS = ["campus", "major_key", "faculty", "program_name", "sources", "n_sources", "n_source_rows",
                "latest_tcas_year", "applicants", "seats_r3", "competition_ratio", "min_score", "max_score",
                "applicants_2567", "enrolled_2567", "seats_2570", "n_projects_2570"]
INT_COLS = {"academic_year", "seats", "applicants", "enrolled", "n_sources", "n_source_rows",
            "latest_tcas_year", "seats_r3", "applicants_2567", "enrolled_2567", "seats_2570", "n_projects_2570"}


def hook() -> PostgresHook:
    return PostgresHook(postgres_conn_id=CONN_ID)


def ensure_schema():
    with hook().get_conn() as conn, conn.cursor() as cur:
        cur.execute(DDL)


def _clean(value, col):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if col in INT_COLS:
        return int(value)
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def _rows(df, cols):
    return [tuple(_clean(r[c], c) for c in cols) for r in df.to_dict("records")]


def upsert(table: str, df, cols, key_cols) -> int:
    if df is None or df.empty:
        return 0
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in key_cols)
    ts = "loaded_at" if table == "admission_stats" else "updated_at"
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES %s "
           f"ON CONFLICT ({', '.join(key_cols)}) DO UPDATE SET {updates}, {ts} = now()")
    with hook().get_conn() as conn, conn.cursor() as cur:
        execute_values(cur, sql, _rows(df, cols), page_size=500)
    return len(df)


def upsert_stats(df) -> int:
    return upsert("admission_stats", df, STATS_COLS, ["source", "academic_year", "source_record_id"])


def upsert_summary(df) -> int:
    return upsert("program_summary", df, SUMMARY_COLS, ["campus", "major_key"])


def read_stats():
    return hook().get_pandas_df("SELECT * FROM admission_stats")


def insert_quarantine(run_id: str, bad) -> int:
    if bad is None or bad.empty:
        return 0
    rows = [(run_id, r["source"], _clean(r["academic_year"], "academic_year"), r["source_record_id"], r["reason"],
             json.dumps({k: _clean(v, k) for k, v in r.items()}, ensure_ascii=False, default=str))
            for r in bad.to_dict("records")]
    with hook().get_conn() as conn, conn.cursor() as cur:
        execute_values(cur, "INSERT INTO dq_quarantine (run_id, source, academic_year, source_record_id, reason, payload) "
                            "VALUES %s", rows)
    return len(rows)


def save_run(record: dict):
    cols = list(record)
    vals = [json.dumps(v, ensure_ascii=False, default=str) if c == "details" else v for c, v in record.items()]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "run_id")
    with hook().get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"INSERT INTO pipeline_runs ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
                    f"ON CONFLICT (run_id) DO UPDATE SET {updates}", vals)
