"""Account Manager: CRUD for Roblox accounts with encrypted credentials."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .config import DB_PATH, ensure_data_dir
from .crypto import decrypt, encrypt


@dataclass
class Account:
    """A single Roblox account."""

    id: Optional[int] = None
    username: str = ""
    password: str = ""  # stored encrypted
    cookie: str = ""  # .ROBLOSECURITY cookie, stored encrypted
    display_name: str = ""
    note: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_launched: Optional[datetime] = None

    @property
    def label(self) -> str:
        return self.display_name or self.username or f"Account {self.id}"


class AccountStore:
    """SQLite-backed account store. Credentials are encrypted at rest."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DB_PATH
        ensure_data_dir()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA temp_store = MEMORY")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    password TEXT,
                    cookie TEXT,
                    display_name TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_launched TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_accounts_username ON accounts(username)"
            )
            conn.commit()

    # ------------------------------------------------------------------ CRUD

    def add(self, account: Account) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO accounts
                (username, password, cookie, display_name, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account.username,
                    encrypt(account.password),
                    encrypt(account.cookie),
                    account.display_name,
                    account.note,
                    now,
                    now,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get(self, account_id: int) -> Optional[Account]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        return self._row_to_account(row) if row else None

    def list(self) -> list[Account]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM accounts ORDER BY lower(username) ASC"
            ).fetchall()
        return [self._row_to_account(r) for r in rows]

    def update(self, account_id: int, **fields) -> bool:
        allowed = {"username", "password", "cookie", "display_name", "note"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        if "password" in updates:
            updates["password"] = encrypt(updates["password"])
        if "cookie" in updates:
            updates["cookie"] = encrypt(updates["cookie"])
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [account_id]
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE accounts SET {set_clause} WHERE id = ?", values
            )
            conn.commit()
            return cur.rowcount > 0

    def delete(self, account_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
            conn.commit()
            return cur.rowcount > 0

    def mark_launched(self, account_id: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                "UPDATE accounts SET last_launched = ?, updated_at = ? WHERE id = ?",
                (now, now, account_id),
            )
            conn.commit()

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _row_to_account(row: sqlite3.Row) -> Account:
        return Account(
            id=row["id"],
            username=row["username"],
            password=decrypt(row["password"]) or "",
            cookie=decrypt(row["cookie"]) or "",
            display_name=row["display_name"] or "",
            note=row["note"] or "",
            created_at=_parse(row["created_at"]),
            updated_at=_parse(row["updated_at"]),
            last_launched=_parse(row["last_launched"]),
        )


def _parse(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
