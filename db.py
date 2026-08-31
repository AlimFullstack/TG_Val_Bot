from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    anketa_completed_at REAL
);

CREATE TABLE IF NOT EXISTS members (
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    joined_at REAL NOT NULL,
    deadline_at REAL,
    muted INTEGER NOT NULL DEFAULT 0,
    reminder_sent INTEGER NOT NULL DEFAULT 0,
    welcome_message_id INTEGER,
    PRIMARY KEY (user_id, chat_id)
);

CREATE TABLE IF NOT EXISTS answers (
    user_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (user_id, question_id)
);

CREATE TABLE IF NOT EXISTS answer_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    question_id TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    edited_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS awards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    given_by INTEGER NOT NULL,
    given_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS kicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    kicked_at REAL NOT NULL,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anketa_progress (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    question_index INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS admin_alerts (
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, chat_id, admin_id)
);

CREATE TABLE IF NOT EXISTS activity_daily (
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    msg_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, chat_id, day)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def ensure_super_admin(self, user_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, user_id, time.time()),
        )
        await self.conn.commit()

    async def is_admin(self, user_id: int) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
        )
        return await cur.fetchone() is not None

    async def list_admins(self) -> list[int]:
        cur = await self.conn.execute("SELECT user_id FROM admins")
        rows = await cur.fetchall()
        return [int(r["user_id"]) for r in rows]

    async def add_admin(self, user_id: int, added_by: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO admins (user_id, added_by, added_at) VALUES (?, ?, ?)",
            (user_id, added_by, time.time()),
        )
        await self.conn.commit()

    async def remove_admin(self, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM admins WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def upsert_chat(self, chat_id: int, title: str | None) -> None:
        await self.conn.execute(
            """
            INSERT INTO chats (chat_id, title) VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title
            """,
            (chat_id, title or ""),
        )
        await self.conn.commit()

    async def get_chat(self, chat_id: int) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT * FROM chats WHERE chat_id = ?", (chat_id,)
        )
        return await cur.fetchone()

    async def upsert_user(self, user_id: int, username: str | None) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, anketa_completed_at)
            VALUES (?, ?, NULL)
            ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
            """,
            (user_id, username),
        )
        await self.conn.commit()

    async def anketa_completed(self, user_id: int) -> bool:
        cur = await self.conn.execute(
            "SELECT anketa_completed_at FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cur.fetchone()
        return row is not None and row["anketa_completed_at"] is not None

    async def mark_anketa_completed(self, user_id: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, anketa_completed_at)
            VALUES (?, NULL, ?)
            ON CONFLICT(user_id) DO UPDATE SET anketa_completed_at = excluded.anketa_completed_at
            """,
            (user_id, time.time()),
        )
        await self.conn.commit()

    async def clear_anketa(self, user_id: int) -> None:
        await self.conn.execute("DELETE FROM answers WHERE user_id = ?", (user_id,))
        await self.conn.execute(
            "UPDATE users SET anketa_completed_at = NULL WHERE user_id = ?",
            (user_id,),
        )
        await self.conn.execute(
            "DELETE FROM anketa_progress WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()

    async def upsert_member(
        self,
        user_id: int,
        chat_id: int,
        *,
        joined_at: float,
        deadline_at: float | None,
        muted: bool,
        welcome_message_id: int | None = None,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO members (
                user_id, chat_id, joined_at, deadline_at, muted,
                reminder_sent, welcome_message_id
            ) VALUES (?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                joined_at = excluded.joined_at,
                deadline_at = excluded.deadline_at,
                muted = excluded.muted,
                reminder_sent = 0,
                welcome_message_id = COALESCE(excluded.welcome_message_id, members.welcome_message_id)
            """,
            (
                user_id,
                chat_id,
                joined_at,
                deadline_at,
                1 if muted else 0,
                welcome_message_id,
            ),
        )
        await self.conn.commit()

    async def set_welcome_message(
        self, user_id: int, chat_id: int, message_id: int
    ) -> None:
        await self.conn.execute(
            """
            UPDATE members SET welcome_message_id = ?
            WHERE user_id = ? AND chat_id = ?
            """,
            (message_id, user_id, chat_id),
        )
        await self.conn.commit()

    async def set_member_muted(
        self, user_id: int, chat_id: int, muted: bool, deadline_at: float | None = None
    ) -> None:
        if deadline_at is None:
            await self.conn.execute(
                "UPDATE members SET muted = ? WHERE user_id = ? AND chat_id = ?",
                (1 if muted else 0, user_id, chat_id),
            )
        else:
            await self.conn.execute(
                """
                UPDATE members
                SET muted = ?, deadline_at = ?, reminder_sent = 0
                WHERE user_id = ? AND chat_id = ?
                """,
                (1 if muted else 0, deadline_at, user_id, chat_id),
            )
        await self.conn.commit()

    async def unmute_member(self, user_id: int, chat_id: int) -> None:
        await self.conn.execute(
            """
            UPDATE members
            SET muted = 0, deadline_at = NULL, reminder_sent = 1
            WHERE user_id = ? AND chat_id = ?
            """,
            (user_id, chat_id),
        )
        await self.conn.commit()

    async def get_muted_memberships(self, user_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM members WHERE user_id = ? AND muted = 1",
            (user_id,),
        )
        return await cur.fetchall()

    async def get_member(self, user_id: int, chat_id: int) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT * FROM members WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        return await cur.fetchone()

    async def get_memberships(self, user_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM members WHERE user_id = ? ORDER BY joined_at DESC",
            (user_id,),
        )
        return await cur.fetchall()

    async def due_reminders(self, now: float, reminder_before_sec: float) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT * FROM members
            WHERE muted = 1
              AND reminder_sent = 0
              AND deadline_at IS NOT NULL
              AND deadline_at - ? <= ?
              AND deadline_at > ?
            """,
            (reminder_before_sec, now, now),
        )
        return await cur.fetchall()

    async def due_kicks(self, now: float) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT * FROM members
            WHERE muted = 1
              AND deadline_at IS NOT NULL
              AND deadline_at <= ?
            """,
            (now,),
        )
        return await cur.fetchall()

    async def mark_reminder_sent(self, user_id: int, chat_id: int) -> None:
        await self.conn.execute(
            """
            UPDATE members SET reminder_sent = 1
            WHERE user_id = ? AND chat_id = ?
            """,
            (user_id, chat_id),
        )
        await self.conn.commit()

    async def delete_member(self, user_id: int, chat_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM members WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        await self.conn.commit()

    async def add_kick(
        self, user_id: int, chat_id: int, reason: str
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO kicks (user_id, chat_id, kicked_at, reason)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, chat_id, time.time(), reason),
        )
        await self.conn.commit()

    async def get_kicks(self, user_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            "SELECT * FROM kicks WHERE user_id = ? ORDER BY kicked_at DESC",
            (user_id,),
        )
        return await cur.fetchall()

    async def set_progress(
        self, user_id: int, question_index: int, chat_id: int | None
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO anketa_progress (user_id, chat_id, question_index)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                chat_id = COALESCE(excluded.chat_id, anketa_progress.chat_id),
                question_index = excluded.question_index
            """,
            (user_id, chat_id, question_index),
        )
        await self.conn.commit()

    async def get_progress(self, user_id: int) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT * FROM anketa_progress WHERE user_id = ?",
            (user_id,),
        )
        return await cur.fetchone()

    async def clear_progress(self, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM anketa_progress WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()

    async def set_answer(self, user_id: int, question_id: str, value: str) -> None:
        cur = await self.conn.execute(
            "SELECT value FROM answers WHERE user_id = ? AND question_id = ?",
            (user_id, question_id),
        )
        old = await cur.fetchone()
        old_value = old["value"] if old else None
        if old_value != value:
            await self.conn.execute(
                """
                INSERT INTO answer_history (user_id, question_id, old_value, new_value, edited_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, question_id, old_value, value, time.time()),
            )
        await self.conn.execute(
            """
            INSERT INTO answers (user_id, question_id, value) VALUES (?, ?, ?)
            ON CONFLICT(user_id, question_id) DO UPDATE SET value = excluded.value
            """,
            (user_id, question_id, value),
        )
        await self.conn.commit()

    async def delete_answer(self, user_id: int, question_id: str) -> None:
        cur = await self.conn.execute(
            "SELECT value FROM answers WHERE user_id = ? AND question_id = ?",
            (user_id, question_id),
        )
        old = await cur.fetchone()
        if old:
            await self.conn.execute(
                """
                INSERT INTO answer_history (user_id, question_id, old_value, new_value, edited_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, question_id, old["value"], None, time.time()),
            )
            await self.conn.execute(
                "DELETE FROM answers WHERE user_id = ? AND question_id = ?",
                (user_id, question_id),
            )
            await self.conn.commit()

    async def get_answers(self, user_id: int) -> dict[str, str]:
        cur = await self.conn.execute(
            "SELECT question_id, value FROM answers WHERE user_id = ?",
            (user_id,),
        )
        rows = await cur.fetchall()
        return {r["question_id"]: r["value"] for r in rows}

    async def get_answer_history(self, user_id: int) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT * FROM answer_history
            WHERE user_id = ?
            ORDER BY edited_at DESC
            """,
            (user_id,),
        )
        return await cur.fetchall()

    async def add_award(self, user_id: int, title: str, given_by: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO awards (user_id, title, given_by, given_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, title, given_by, time.time()),
        )
        await self.conn.commit()

    async def remove_award(self, user_id: int, title: str) -> bool:
        cur = await self.conn.execute(
            """
            DELETE FROM awards
            WHERE id = (
                SELECT id FROM awards
                WHERE user_id = ? AND title = ?
                ORDER BY given_at DESC
                LIMIT 1
            )
            """,
            (user_id, title),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_awards(self, user_id: int) -> list[str]:
        cur = await self.conn.execute(
            "SELECT title FROM awards WHERE user_id = ? ORDER BY given_at",
            (user_id,),
        )
        rows = await cur.fetchall()
        return [r["title"] for r in rows]

    async def save_admin_alert(
        self, user_id: int, chat_id: int, admin_id: int, message_id: int
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO admin_alerts (user_id, chat_id, admin_id, message_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id, admin_id) DO UPDATE SET
                message_id = excluded.message_id
            """,
            (user_id, chat_id, admin_id, message_id),
        )
        await self.conn.commit()

    async def get_admin_alerts(
        self, user_id: int, chat_id: int
    ) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT * FROM admin_alerts
            WHERE user_id = ? AND chat_id = ?
            """,
            (user_id, chat_id),
        )
        return await cur.fetchall()

    async def get_user(self, user_id: int) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        return await cur.fetchone()

    async def find_user_by_username(self, username: str) -> aiosqlite.Row | None:
        uname = username.lstrip("@").lower()
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE lower(username) = ?",
            (uname,),
        )
        return await cur.fetchone()

    async def stats(self) -> dict[str, Any]:
        muted = await (
            await self.conn.execute("SELECT COUNT(*) AS c FROM members WHERE muted = 1")
        ).fetchone()
        completed = await (
            await self.conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE anketa_completed_at IS NOT NULL"
            )
        ).fetchone()
        day_ago = time.time() - 86400
        kicks = await (
            await self.conn.execute(
                "SELECT COUNT(*) AS c FROM kicks WHERE kicked_at >= ?",
                (day_ago,),
            )
        ).fetchone()
        chats = await (
            await self.conn.execute("SELECT COUNT(*) AS c FROM chats")
        ).fetchone()
        return {
            "muted": int(muted["c"]),
            "completed": int(completed["c"]),
            "kicks_24h": int(kicks["c"]),
            "chats": int(chats["c"]),
        }

    async def increment_activity(self, user_id: int, chat_id: int, day: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO activity_daily (user_id, chat_id, day, msg_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, chat_id, day) DO UPDATE SET
                msg_count = msg_count + 1
            """,
            (user_id, chat_id, day),
        )
        await self.conn.commit()

    async def get_activity_last_days(
        self,
        user_id: int,
        days: list[str],
        chat_id: int | None = None,
    ) -> dict[str, int]:
        if not days:
            return {}
        placeholders = ",".join("?" * len(days))
        if chat_id is None:
            cur = await self.conn.execute(
                f"""
                SELECT day, SUM(msg_count) AS c
                FROM activity_daily
                WHERE user_id = ? AND day IN ({placeholders})
                GROUP BY day
                """,
                (user_id, *days),
            )
        else:
            cur = await self.conn.execute(
                f"""
                SELECT day, msg_count AS c
                FROM activity_daily
                WHERE user_id = ? AND chat_id = ? AND day IN ({placeholders})
                """,
                (user_id, chat_id, *days),
            )
        rows = await cur.fetchall()
        return {str(r["day"]): int(r["c"]) for r in rows}
