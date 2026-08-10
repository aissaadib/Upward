"""One-off migration: copy upward.db (SQLite) -> PostgreSQL (DATABASE_URL).

Usage:
    $env:DATABASE_URL="postgresql://user:pass@host/db"   # PowerShell
    python migrate_to_pg.py
"""
import os
import sqlite3

import app  # noqa: F401  (boots the app: creates the full PG schema on DATABASE_URL)


def main():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url.startswith("postgres"):
        print("Set DATABASE_URL to a postgresql:// URL first.")
        return 1

    src = sqlite3.connect("upward.db")
    src.row_factory = sqlite3.Row
    pg = app.db

    tables = [
        r[0] for r in src.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]

    for t in tables:
        rows = src.execute(f'SELECT * FROM "{t}"').fetchall()
        if not rows:
            print(f"{t}: 0 rows (skipped)")
            continue
        cols = [c[0] for c in src.execute(f'SELECT * FROM "{t}"').description]
        colsql = ", ".join(f'"{c}"' for c in cols)
        ph = ", ".join("?" for _ in cols)
        for row in rows:
            pg.execute(f'INSERT INTO "{t}" ({colsql}) VALUES ({ph})', tuple(row))
        if "id" in cols:
            try:
                pg.execute(
                    f"SELECT setval(pg_get_serial_sequence('{t}', 'id'), "
                    f"(SELECT MAX(id) FROM \"{t}\"))"
                )
            except Exception as e:
                print(f"{t}: sequence sync skipped ({e})")
        print(f"{t}: {len(rows)} rows copied")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())