"""
database.py — Modern Security Bot
Async SQLite layer using aiosqlite.
All CRUD operations are centralised here so cogs stay clean.
"""

import aiosqlite
import os
from typing import Optional
from datetime import datetime, timezone

DB_PATH = os.getenv("DB_PATH", "modern_security.db")


class Database:
    """Singleton-style async database wrapper."""

    def __init__(self):
        self.db_path = DB_PATH

    # ──────────────────────────────────────────────────────────────────
    # INITIALISATION
    # ──────────────────────────────────────────────────────────────────

    async def initialize(self):
        """Create all tables if they don't already exist."""
        async with aiosqlite.connect(self.db_path) as db:
            # config — per-guild settings
            await db.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    guild_id            INTEGER PRIMARY KEY,
                    log_channel_id      INTEGER DEFAULT NULL,
                    mod_role_id         INTEGER DEFAULT NULL,
                    mute_role_id        INTEGER DEFAULT NULL,
                    automod_enabled     INTEGER DEFAULT 1,
                    anti_spam_enabled   INTEGER DEFAULT 1,
                    anti_link_enabled   INTEGER DEFAULT 0,
                    bad_words_enabled   INTEGER DEFAULT 1,
                    auto_punish_enabled INTEGER DEFAULT 1
                )
            """)

            # warnings
            await db.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    guild_id     INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason       TEXT    NOT NULL,
                    timestamp    TEXT    NOT NULL
                )
            """)

            # cases — immutable audit log
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cases (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id     INTEGER NOT NULL,
                    user_id      INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    action       TEXT    NOT NULL,
                    reason       TEXT    NOT NULL,
                    timestamp    TEXT    NOT NULL
                )
            """)

            # trust_scores — composite PK (user + guild)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trust_scores (
                    user_id  INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    score    INTEGER DEFAULT 100,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)

            # reports
            await db.execute("""
                CREATE TABLE IF NOT EXISTS reports (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    reporter_id INTEGER NOT NULL,
                    target_id   INTEGER NOT NULL,
                    guild_id    INTEGER NOT NULL,
                    reason      TEXT    NOT NULL,
                    timestamp   TEXT    NOT NULL
                )
            """)

            await db.commit()
        print("✅ Database initialised successfully.")

    # ──────────────────────────────────────────────────────────────────
    # CONFIG
    # ──────────────────────────────────────────────────────────────────

    async def ensure_config(self, guild_id: int):
        """Insert a default config row for this guild if not present."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO config (guild_id) VALUES (?)",
                (guild_id,)
            )
            await db.commit()

    async def get_config(self, guild_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def set_log_channel(self, guild_id: int, channel_id: int):
        await self.ensure_config(guild_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE config SET log_channel_id = ? WHERE guild_id = ?",
                (channel_id, guild_id)
            )
            await db.commit()

    async def set_mod_role(self, guild_id: int, role_id: int):
        await self.ensure_config(guild_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE config SET mod_role_id = ? WHERE guild_id = ?",
                (role_id, guild_id)
            )
            await db.commit()

    async def set_mute_role(self, guild_id: int, role_id: int):
        await self.ensure_config(guild_id)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE config SET mute_role_id = ? WHERE guild_id = ?",
                (role_id, guild_id)
            )
            await db.commit()

    async def toggle_automod_setting(self, guild_id: int, setting: str) -> bool:
        """Toggle a boolean config column and return the new value."""
        valid = {
            "automod_enabled", "anti_spam_enabled",
            "anti_link_enabled", "bad_words_enabled", "auto_punish_enabled"
        }
        if setting not in valid:
            raise ValueError(f"Invalid automod setting: {setting!r}")
        await self.ensure_config(guild_id)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT {setting} FROM config WHERE guild_id = ?", (guild_id,)
            )
            row = await cursor.fetchone()
            current = row[0] if row else 0
            new_val = 0 if current else 1
            await db.execute(
                f"UPDATE config SET {setting} = ? WHERE guild_id = ?",
                (new_val, guild_id)
            )
            await db.commit()
            return bool(new_val)

    # ──────────────────────────────────────────────────────────────────
    # WARNINGS
    # ──────────────────────────────────────────────────────────────────

    async def add_warning(
        self, user_id: int, guild_id: int, moderator_id: int, reason: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, guild_id, moderator_id, reason,
                 datetime.now(timezone.utc).isoformat())
            )
            await db.commit()
            return cursor.lastrowid

    async def get_warnings(self, user_id: int, guild_id: int) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM warnings
                   WHERE user_id = ? AND guild_id = ?
                   ORDER BY timestamp DESC""",
                (user_id, guild_id)
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def count_warnings(self, user_id: int, guild_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM warnings WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = await cursor.fetchone()
            return row[0] if row else 0

    # ──────────────────────────────────────────────────────────────────
    # CASES
    # ──────────────────────────────────────────────────────────────────

    async def create_case(
        self, guild_id: int, user_id: int,
        moderator_id: int, action: str, reason: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO cases
                       (guild_id, user_id, moderator_id, action, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (guild_id, user_id, moderator_id, action, reason,
                 datetime.now(timezone.utc).isoformat())
            )
            await db.commit()
            return cursor.lastrowid

    async def get_case(self, case_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM cases WHERE id = ?", (case_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_cases(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM cases ORDER BY timestamp DESC"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ──────────────────────────────────────────────────────────────────
    # TRUST SCORES
    # ──────────────────────────────────────────────────────────────────

    async def get_trust_score(self, user_id: int, guild_id: int) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT score FROM trust_scores WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            row = await cursor.fetchone()
            return row[0] if row else 100

    async def update_trust_score(self, user_id: int, guild_id: int, delta: int):
        """Add/subtract from the trust score, clamped to [0, 100]."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO trust_scores (user_id, guild_id, score)
                   VALUES (?, ?, MAX(0, MIN(100, 100 + ?)))
                   ON CONFLICT(user_id, guild_id)
                   DO UPDATE SET score = MAX(0, MIN(100, score + ?))""",
                (user_id, guild_id, delta, delta)
            )
            await db.commit()

    async def set_trust_score(self, user_id: int, guild_id: int, score: int):
        score = max(0, min(100, score))
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO trust_scores (user_id, guild_id, score)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, guild_id)
                   DO UPDATE SET score = ?""",
                (user_id, guild_id, score, score)
            )
            await db.commit()

    # ──────────────────────────────────────────────────────────────────
    # REPORTS
    # ──────────────────────────────────────────────────────────────────

    async def add_report(
        self, reporter_id: int, target_id: int,
        guild_id: int, reason: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO reports
                       (reporter_id, target_id, guild_id, reason, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (reporter_id, target_id, guild_id, reason,
                 datetime.now(timezone.utc).isoformat())
            )
            await db.commit()
            return cursor.lastrowid

    async def get_all_reports(self) -> list[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM reports ORDER BY timestamp DESC"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
