"""One-off migration: copy upward.db (SQLite) -> PostgreSQL (DATABASE_URL).

Uses a raw SQLAlchemy psycopg2 connection (autocommit, %s placeholders)
to avoid cs50's `?` substitution breaking on values containing `?`.

Usage:
    $env:DATABASE_URL="postgresql://user:pass@host/db"   # PowerShell
    python migrate_to_pg.py
"""
import os
import sqlite3

import app  # noqa: F401  (boots the app: creates the full PG schema on DATABASE_URL)
import psycopg2  # noqa: E402


def main():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url.startswith("postgres"):
        print("Set DATABASE_URL to a postgresql:// URL first.")
        return 1

    src = sqlite3.connect("upward.db")
    src.row_factory = sqlite3.Row

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    tables = [
        r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]

    for t in tables:
        cur.execute(f'DELETE FROM "{t}"')
        rows = src.execute(f'SELECT * FROM "{t}"').fetchall()
        if not rows:
            print(f"{t}: 0 rows (skipped)")
            continue
        cols = [c[0] for c in src.execute(f'SELECT * FROM "{t}"').description]
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{t}'"
        )
        pg_cols = {r[0] for r in cur.fetchall()}
        kept = [c for c in cols if c in pg_cols]
        dropped = [c for c in cols if c not in pg_cols]
        if dropped:
            print(f"{t}: skipping columns not in PG: {dropped}")
        colsql = ", ".join(f'"{c}"' for c in kept)
        ph = ", ".join("%s" for _ in kept)
        data = [tuple(r[c] for c in kept) for r in rows]
        cur.executemany(f'INSERT INTO "{t}" ({colsql}) VALUES ({ph})', data)
        if "id" in cols:
            try:
                cur.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                    f"(SELECT MAX(id) FROM \"{t}\"))"
                )
            except Exception as e:
                print(f"{t}: sequence sync skipped ({e})")
        print(f"{t}: {len(rows)} rows copied")

    cur.close()
    conn.close()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())