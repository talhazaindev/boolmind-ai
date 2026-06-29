#!/usr/bin/env python3
"""Apply advisor Supabase schema migration using SUPABASE_DB_URL or postgres SUPABASE_URL."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = ROOT / "supabase" / "migrations" / "001_advisor_schema.sql"
ENV_FILE = ROOT / ".env"

TABLES = ("chat_events", "failed_operations", "leads", "product_interest_analytics")


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def resolve_db_url() -> str:
    explicit = os.environ.get("SUPABASE_DB_URL", "").strip()
    if explicit:
        return explicit
    url = os.environ.get("SUPABASE_URL", "").strip()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return url
    ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if ref and password:
        return f"postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres"
    raise SystemExit(
        "Set SUPABASE_DB_URL or use postgresql://... in SUPABASE_URL for migrations."
    )


def connect(db_url: str):
    import psycopg2

    kwargs = {"sslmode": "require"}
    try:
        return psycopg2.connect(db_url, **kwargs)
    except psycopg2.OperationalError as err:
        if "could not translate host name" not in str(err) and "Network is unreachable" not in str(
            err
        ):
            raise

    ref = os.environ.get("SUPABASE_PROJECT_REF", "").strip()
    password = os.environ.get("SUPABASE_DB_PASSWORD", "").strip()
    if not ref or not password:
        import re

        m = re.match(
            r"postgresql://postgres:([^@]+)@db\.([^.]+)\.supabase\.co",
            db_url,
        )
        if m:
            password, ref = m.group(1), m.group(2)

    if not ref or not password:
        raise err

    from urllib.parse import quote

    user = f"postgres.{ref}"
    pooler_hosts = (
        "aws-1-us-east-1.pooler.supabase.com",
        "aws-0-us-east-1.pooler.supabase.com",
        "aws-0-eu-central-1.pooler.supabase.com",
    )
    last_err: Exception | None = err
    for host in pooler_hosts:
        try:
            return psycopg2.connect(
                host=host,
                port=5432,
                user=user,
                password=password,
                dbname="postgres",
                connect_timeout=10,
                sslmode="require",
            )
        except psycopg2.OperationalError as pooler_err:
            last_err = pooler_err
            if "not found" in str(pooler_err):
                continue
            raise
    raise last_err or err


def main() -> int:
    load_env(ENV_FILE)
    db_url = resolve_db_url()
    sql = MIGRATION.read_text(encoding="utf-8")

    try:
        import psycopg2  # noqa: F401
    except ImportError:
        print("Install psycopg2-binary: pip install psycopg2-binary", file=sys.stderr)
        return 1

    conn = connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = ANY(%s)
                ORDER BY table_name
                """,
                (list(TABLES),),
            )
            found = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    missing = [t for t in TABLES if t not in found]
    if missing:
        print(f"Migration ran but missing tables: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"Migration OK — tables: {', '.join(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
