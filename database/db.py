import aiosqlite
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from config import settings

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = settings.database_path):
        self.db_path = db_path

    async def init(self) -> None:
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER DEFAULT 0,
                    referred_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id TEXT UNIQUE NOT NULL,
                    prompt TEXT NOT NULL,
                    artist TEXT,
                    instrumental INTEGER DEFAULT 0,
                    lyrics TEXT,
                    status TEXT DEFAULT 'PENDING',
                    audio_url TEXT,
                    duration REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Ensure column exists if table was created previously without it
            try:
                await db.execute("ALTER TABLE generations ADD COLUMN artist TEXT")
            except Exception:
                pass

            await db.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        referred_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch an existing user or insert a new one with initial credits."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    # Update username/first_name in case they changed
                    await db.execute(
                        "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                        (username, first_name, user_id),
                    )
                    await db.commit()
                    return dict(row)

            # Insert new user with initial credits
            # Avoid self-referrals
            valid_referrer = referred_by if referred_by and referred_by != user_id else None

            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, balance, referred_by)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    first_name,
                    settings.initial_user_credits,
                    valid_referrer,
                ),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                new_row = await cursor.fetchone()
                return dict(new_row)

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def change_balance(self, user_id: int, delta: int) -> int:
        """Add or subtract user balance. Returns new balance."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                (delta, user_id),
            )
            await db.commit()
            async with db.execute(
                "SELECT balance FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                res = await cursor.fetchone()
                return res[0] if res else 0

    async def record_generation(
        self,
        user_id: int,
        task_id: str,
        prompt: str,
        artist: Optional[str] = None,
        instrumental: bool = False,
        lyrics: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO generations (user_id, task_id, prompt, artist, instrumental, lyrics, status)
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (user_id, task_id, prompt, artist, int(instrumental), lyrics),
            )
            await db.commit()

    async def update_generation_status(
        self,
        task_id: str,
        status: str,
        audio_url: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE generations
                SET status = ?, audio_url = coalesce(?, audio_url), duration = coalesce(?, duration)
                WHERE task_id = ?
                """,
                (status, audio_url, duration, task_id),
            )
            await db.commit()

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics: total generations count, success count, referral count."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM generations WHERE user_id = ?", (user_id,)
            ) as cursor:
                total_gens = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM generations WHERE user_id = ? AND status = 'SUCCESS'",
                (user_id,),
            ) as cursor:
                success_gens = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)
            ) as cursor:
                referrals_count = (await cursor.fetchone())[0]

            return {
                "total_generations": total_gens,
                "success_generations": success_gens,
                "referrals_count": referrals_count,
            }


db = Database()
