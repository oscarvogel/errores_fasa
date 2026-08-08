import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import get_settings

settings = get_settings()


def _connect():
    path = Path(settings.sync_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_sync_store():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS remote_errors (
                branch_id INTEGER NOT NULL,
                branch_name TEXT NOT NULL,
                remote_id INTEGER NOT NULL,
                fecha_hora TEXT,
                nro_error INTEGER,
                payload TEXT NOT NULL,
                synced_at TEXT NOT NULL,
                PRIMARY KEY (branch_id, remote_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sync_status (
                branch_id INTEGER PRIMARY KEY,
                branch_name TEXT NOT NULL,
                last_remote_id INTEGER NOT NULL DEFAULT 0,
                last_success_at TEXT,
                last_attempt_at TEXT,
                last_error TEXT,
                last_imported INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.commit()


def get_last_remote_id(branch_id: int) -> int:
    init_sync_store()
    with _connect() as conn:
        row = conn.execute(
            "SELECT last_remote_id FROM sync_status WHERE branch_id = ?", (branch_id,)
        ).fetchone()
        return int(row[0]) if row else 0


def save_remote_errors(branch_id: int, branch_name: str, rows: list[dict]) -> int:
    init_sync_store()
    now = datetime.now().isoformat(timespec="seconds")
    imported = 0
    with _connect() as conn:
        for row in rows:
            remote_id = int(row["id_error"])
            payload = json.dumps(row, ensure_ascii=False, default=str)
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO remote_errors
                (branch_id, branch_name, remote_id, fecha_hora, nro_error, payload, synced_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_id,
                    branch_name,
                    remote_id,
                    str(row.get("fecha_hora") or ""),
                    row.get("nro_error"),
                    payload,
                    now,
                ),
            )
            imported += cursor.rowcount
        conn.commit()
    return imported


def mark_sync_success(branch_id: int, branch_name: str, last_remote_id: int, imported: int):
    init_sync_store()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_status
            (branch_id, branch_name, last_remote_id, last_success_at, last_attempt_at, last_error, last_imported)
            VALUES (?, ?, ?, ?, ?, NULL, ?)
            ON CONFLICT(branch_id) DO UPDATE SET
                branch_name = excluded.branch_name,
                last_remote_id = MAX(sync_status.last_remote_id, excluded.last_remote_id),
                last_success_at = excluded.last_success_at,
                last_attempt_at = excluded.last_attempt_at,
                last_error = NULL,
                last_imported = excluded.last_imported
            """,
            (branch_id, branch_name, last_remote_id, now, now, imported),
        )
        conn.commit()


def mark_sync_error(branch_id: int, branch_name: str, error: str):
    init_sync_store()
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_status
            (branch_id, branch_name, last_remote_id, last_attempt_at, last_error, last_imported)
            VALUES (?, ?, 0, ?, ?, 0)
            ON CONFLICT(branch_id) DO UPDATE SET
                branch_name = excluded.branch_name,
                last_attempt_at = excluded.last_attempt_at,
                last_error = excluded.last_error,
                last_imported = 0
            """,
            (branch_id, branch_name, now, error[:1000]),
        )
        conn.commit()


def get_sync_status(branch_id: int | None = None):
    init_sync_store()
    with _connect() as conn:
        if branch_id is None:
            rows = conn.execute("SELECT * FROM sync_status ORDER BY branch_name").fetchall()
            return [dict(row) for row in rows]
        row = conn.execute(
            "SELECT * FROM sync_status WHERE branch_id = ?", (branch_id,)
        ).fetchone()
        return dict(row) if row else None


def get_remote_errors(branch_id: int | None = None) -> list[dict]:
    init_sync_store()
    with _connect() as conn:
        if branch_id is None:
            rows = conn.execute(
                "SELECT branch_id, branch_name, remote_id, payload FROM remote_errors"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT branch_id, branch_name, remote_id, payload FROM remote_errors WHERE branch_id = ?",
                (branch_id,),
            ).fetchall()

    result = []
    for row in rows:
        item = json.loads(row["payload"])
        item["_id"] = f"branch:{row['branch_id']}:{row['remote_id']}"
        item["origen_id"] = row["branch_id"]
        item["origen"] = row["branch_name"]
        item["id_error_origen"] = row["remote_id"]
        result.append(item)
    return result


def get_remote_error(branch_id: int, remote_id: int) -> dict | None:
    init_sync_store()
    with _connect() as conn:
        row = conn.execute(
            "SELECT branch_name, payload FROM remote_errors WHERE branch_id = ? AND remote_id = ?",
            (branch_id, remote_id),
        ).fetchone()
    if not row:
        return None
    item = json.loads(row["payload"])
    item["_id"] = f"branch:{branch_id}:{remote_id}"
    item["origen_id"] = branch_id
    item["origen"] = row["branch_name"]
    item["id_error_origen"] = remote_id
    return item
