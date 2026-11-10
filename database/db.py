import aiosqlite
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from config import settings

logger = logging.getLogger(__name__)


def format_per_track_badge(price: float, credits: int) -> str:
    """Formats price per track (e.g. '100 ₽ за трек' or '0.7 ₽ за трек')."""
    if credits <= 0:
        return ""
    per_track = price / credits
    if per_track.is_integer():
        return f"{int(per_track)} ₽ за трек"
    val = round(per_track, 2)
    return f"{val:g} ₽ за трек"


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
                    paid_balance INTEGER DEFAULT 0,
                    gift_balance INTEGER DEFAULT 0,
                    referred_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Ensure columns exist if table was created previously without them
            try:
                await db.execute("ALTER TABLE users ADD COLUMN paid_balance INTEGER DEFAULT 0")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE users ADD COLUMN gift_balance INTEGER DEFAULT 0")
            except Exception:
                pass

            # Migrate legacy balance to gift_balance if needed
            try:
                await db.execute("""
                    UPDATE users
                    SET gift_balance = balance
                    WHERE paid_balance = 0 AND gift_balance = 0 AND balance > 0
                """)
            except Exception:
                pass

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

            try:
                await db.execute("ALTER TABLE generations ADD COLUMN genres TEXT")
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    credits INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tariffs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    credits INTEGER NOT NULL,
                    price REAL NOT NULL,
                    emoji TEXT NOT NULL,
                    badge TEXT NOT NULL
                )
            """)

            # Populate tariffs if empty
            async with db.execute("SELECT COUNT(*) FROM tariffs") as cursor:
                tariffs_count = (await cursor.fetchone())[0]

            if tariffs_count == 0:
                default_tariffs = [
                    ("pack_5", "5 генераций", 5, 10.0, "🥉", format_per_track_badge(10.0, 5)),
                    ("pack_15", "15 генераций", 15, 10.0, "🥈", format_per_track_badge(10.0, 15)),
                    ("pack_50", "50 генераций", 50, 10.0, "🥇", format_per_track_badge(10.0, 50)),
                    ("pack_150", "150 генераций", 150, 10.0, "👑", format_per_track_badge(10.0, 150)),
                ]
                await db.executemany(
                    """
                    INSERT INTO tariffs (id, title, credits, price, emoji, badge)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    default_tariffs,
                )
            else:
                # Automatically keep badges in sync as dynamic "X ₽ за трек"
                async with db.execute("SELECT id, credits, price, badge FROM tariffs") as cursor:
                    existing_tariffs = await cursor.fetchall()
                    for row in existing_tariffs:
                        tid, cr, pr, bg = row[0], row[1], row[2], row[3]
                        new_bg = format_per_track_badge(pr, cr)
                        if bg != new_bg:
                            await db.execute(
                                "UPDATE tariffs SET badge = ? WHERE id = ?",
                                (new_bg, tid),
                            )

            await db.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

    def _format_user_row(self, row: aiosqlite.Row) -> Dict[str, Any]:
        d = dict(row)
        paid = d.get("paid_balance") or 0
        gift = d.get("gift_balance") or 0
        d["paid_balance"] = paid
        d["gift_balance"] = gift
        d["total_balance"] = paid + gift
        d["balance"] = paid + gift
        return d

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
                    return self._format_user_row(row)

            # Insert new user with initial gift credits
            valid_referrer = (
                referred_by if referred_by and referred_by != user_id else None
            )

            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, balance, paid_balance, gift_balance, referred_by)
                VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    user_id,
                    username,
                    first_name,
                    settings.initial_user_credits,
                    settings.initial_user_credits,
                    valid_referrer,
                ),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                new_row = await cursor.fetchone()
                return self._format_user_row(new_row)

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._format_user_row(row) if row else None

    async def add_paid_balance(self, user_id: int, amount: int) -> int:
        """Adds to paid balance. Returns new total balance."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET paid_balance = coalesce(paid_balance, 0) + ?,
                    balance = coalesce(balance, 0) + ?
                WHERE user_id = ?
                """,
                (amount, amount, user_id),
            )
            await db.commit()
            user = await self.get_user(user_id)
            return user["total_balance"] if user else 0

    async def add_gift_balance(self, user_id: int, amount: int) -> int:
        """Adds to gift/bonus balance (referrals, promos). Returns new total balance."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET gift_balance = coalesce(gift_balance, 0) + ?,
                    balance = coalesce(balance, 0) + ?
                WHERE user_id = ?
                """,
                (amount, amount, user_id),
            )
            await db.commit()
            user = await self.get_user(user_id)
            return user["total_balance"] if user else 0

    async def consume_generation_credit(self, user_id: int, cost: int = 1) -> Optional[str]:
        """
        Deducts cost from balance. Prioritizes gift_balance first, then paid_balance.
        Returns 'gift' if deducted from gift balance,
        'paid' if deducted from paid balance,
        or None if insufficient funds.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT paid_balance, gift_balance FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                gift = row["gift_balance"] or 0
                paid = row["paid_balance"] or 0

            if gift >= cost:
                await db.execute(
                    """
                    UPDATE users
                    SET gift_balance = gift_balance - ?,
                        balance = max(0, coalesce(balance, 0) - ?)
                    WHERE user_id = ?
                    """,
                    (cost, cost, user_id),
                )
                await db.commit()
                return "gift"
            elif (gift + paid) >= cost:
                await db.execute(
                    """
                    UPDATE users
                    SET paid_balance = paid_balance - ?,
                        balance = max(0, coalesce(balance, 0) - ?)
                    WHERE user_id = ?
                    """,
                    (cost, cost, user_id),
                )
                await db.commit()
                return "paid"
            else:
                return None

    async def refund_generation_credit(
        self, user_id: int, balance_type: str = "gift", cost: int = 1
    ) -> None:
        """Refunds credit back to the appropriate balance (gift or paid)."""
        if balance_type == "paid":
            await self.add_paid_balance(user_id, cost)
        else:
            await self.add_gift_balance(user_id, cost)

    async def change_balance(self, user_id: int, delta: int) -> int:
        """Compatibility method for balance changes. Returns new total balance."""
        if delta >= 0:
            return await self.add_gift_balance(user_id, delta)
        else:
            await self.consume_generation_credit(user_id, abs(delta))
            user = await self.get_user(user_id)
            return user["total_balance"] if user else 0

    async def record_generation(
        self,
        user_id: int,
        task_id: str,
        prompt: str,
        artist: Optional[str] = None,
        genres: Optional[str] = None,
        instrumental: bool = False,
        lyrics: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO generations (user_id, task_id, prompt, artist, genres, instrumental, lyrics, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING')
                """,
                (user_id, task_id, prompt, artist, genres, int(instrumental), lyrics),
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

    async def create_payment_record(
        self,
        payment_id: str,
        user_id: int,
        amount: float,
        credits: int,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO payments (payment_id, user_id, amount, credits, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                (payment_id, user_id, amount, credits),
            )
            await db.commit()

    async def get_payment_record(self, payment_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def mark_payment_succeeded(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Marks payment as succeeded idempotently.
        Returns the payment row if it was changed to 'succeeded',
        or None if it was already processed before.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                if row["status"] == "succeeded":
                    return None  # already processed!

            await db.execute(
                """
                UPDATE payments
                SET status = 'succeeded', updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = ?
                """,
                (payment_id,),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
            ) as cursor:
                updated_row = await cursor.fetchone()
                return dict(updated_row) if updated_row else None

    async def mark_payment_canceled(self, payment_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE payments
                SET status = 'canceled', updated_at = CURRENT_TIMESTAMP
                WHERE payment_id = ?
                """,
                (payment_id,),
            )
            await db.commit()

    async def get_pending_payments(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Fetch recently created pending payments to check their status in background."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM payments
                WHERE status = 'pending'
                  AND created_at >= datetime('now', '-2 hours')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def cleanup_stale_payments(self, max_age_hours: int = 2) -> int:
        """Marks pending payments older than max_age_hours as canceled."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"""
                UPDATE payments
                SET status = 'canceled', updated_at = CURRENT_TIMESTAMP
                WHERE status = 'pending'
                  AND created_at <= datetime('now', '-{max_age_hours} hours')
                """
            )
            await db.commit()
            return cursor.rowcount

    async def get_user_pending_count(self, user_id: int, max_age_minutes: int = 15) -> int:
        """Returns the number of active pending payments created by user in the last N minutes."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"""
                SELECT COUNT(*) FROM payments
                WHERE user_id = ?
                  AND status = 'pending'
                  AND created_at >= datetime('now', '-{max_age_minutes} minutes')
                """,
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


    async def get_all_tariffs(self) -> list[Dict[str, Any]]:
        """Fetch all pricing packages from database."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tariffs ORDER BY credits ASC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_tariff(self, tariff_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific tariff package by id."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tariffs WHERE id = ?", (tariff_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_tariff_price(self, tariff_id: str, new_price: float) -> bool:
        """Update price and recalculate per-track badge for a specific tariff."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT credits FROM tariffs WHERE id = ?", (tariff_id,)) as cursor:
                row = await cursor.fetchone()
                cr = row[0] if row else 1

            new_badge = format_per_track_badge(new_price, cr)
            await db.execute(
                "UPDATE tariffs SET price = ?, badge = ? WHERE id = ?",
                (new_price, new_badge, tariff_id),
            )
            await db.commit()
            return True

    async def get_all_user_ids(self) -> list[int]:
        """Fetch all user Telegram IDs for broadcast."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_system_stats(self) -> Dict[str, Any]:
        """Calculates system-wide metrics for the admin panel."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                users_count = (await c.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM generations") as c:
                total_gens = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM generations WHERE status = 'SUCCESS'"
            ) as c:
                success_gens = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*), coalesce(SUM(amount), 0) FROM payments WHERE status = 'succeeded'"
            ) as c:
                pay_row = await c.fetchone()
                payments_count = pay_row[0]
                revenue = pay_row[1]

            return {
                "users_count": users_count,
                "total_generations": total_gens,
                "success_generations": success_gens,
                "payments_count": payments_count,
                "revenue_rub": float(revenue),
            }


db = Database()
