from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    username         TEXT,
    niche            TEXT,
    tone             TEXT,
    services         TEXT,
    onboarded        INTEGER NOT NULL DEFAULT 0,
    generations_used INTEGER NOT NULL DEFAULT 0,
    premium_until    TEXT,
    created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS generations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    user_input TEXT,
    result     TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    plan        TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    provider    TEXT NOT NULL,
    external_id TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL,
    paid_at     TEXT
);
CREATE INDEX IF NOT EXISTS payments_external ON payments (provider, external_id);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class User:
    user_id: int
    username: str | None
    niche: str | None
    tone: str | None
    services: str | None
    onboarded: bool
    generations_used: int
    premium_until: datetime | None

    @property
    def is_premium(self) -> bool:
        return self.premium_until is not None and self.premium_until > datetime.now(UTC)


@dataclass
class Payment:
    id: int
    user_id: int
    plan: str
    amount: int
    provider: str
    external_id: str | None
    status: str

    @property
    def is_paid(self) -> bool:
        return self.status == "paid"


def _payment(row: aiosqlite.Row) -> Payment:
    return Payment(
        id=row["id"],
        user_id=row["user_id"],
        plan=row["plan"],
        amount=row["amount"],
        provider=row["provider"],
        external_id=row["external_id"],
        status=row["status"],
    )


class Database:
    def __init__(self, path: str) -> None:
        self._path = path

    async def init(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def get_or_create_user(self, user_id: int, username: str | None) -> User:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
                (user_id, username, _now()),
            )
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            await db.commit()
        user = await self.get_user(user_id)
        assert user is not None
        return user

    async def get_user(self, user_id: int) -> User | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
        if row is None:
            return None
        premium_until = datetime.fromisoformat(row["premium_until"]) if row["premium_until"] else None
        return User(
            user_id=row["user_id"],
            username=row["username"],
            niche=row["niche"],
            tone=row["tone"],
            services=row["services"],
            onboarded=bool(row["onboarded"]),
            generations_used=row["generations_used"],
            premium_until=premium_until,
        )

    async def save_profile(self, user_id: int, niche: str, tone: str, services: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, created_at) VALUES (?, ?)", (user_id, _now())
            )
            await db.execute(
                "UPDATE users SET niche = ?, tone = ?, services = ?, onboarded = 1 WHERE user_id = ?",
                (niche, tone, services, user_id),
            )
            await db.commit()

    async def reserve_generation(self, user_id: int, free_limit: int) -> bool:
        """Атомарно списывает одну генерацию; False — лимит исчерпан и премиума нет."""
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "UPDATE users SET generations_used = generations_used + 1 "
                "WHERE user_id = ? AND (generations_used < ? OR premium_until > ?)",
                (user_id, free_limit, _now()),
            )
            await db.commit()
            return cur.rowcount == 1

    async def refund_generation(self, user_id: int) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE users SET generations_used = MAX(generations_used - 1, 0) WHERE user_id = ?",
                (user_id,),
            )
            await db.commit()

    async def log_generation(self, user_id: int, kind: str, user_input: str, result: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO generations (user_id, kind, user_input, result, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, kind, user_input, result, _now()),
            )
            await db.commit()

    async def grant_premium(self, user_id: int, days: int) -> datetime:
        until = datetime.now(UTC) + timedelta(days=days)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "UPDATE users SET premium_until = ? WHERE user_id = ?", (until.isoformat(), user_id)
            )
            await db.commit()
        return until

    async def get_setting(self, key: str) -> str | None:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
        return str(row[0]) if row else None

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()

    async def create_payment(self, user_id: int, plan: str, amount: int, provider: str) -> Payment:
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "INSERT INTO payments (user_id, plan, amount, provider, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, plan, amount, provider, _now()),
            )
            await db.commit()
            assert cur.lastrowid is not None
            payment_id = cur.lastrowid
        payment = await self.get_payment(payment_id)
        assert payment is not None
        return payment

    async def set_payment_external_id(self, payment_id: int, external_id: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("UPDATE payments SET external_id = ? WHERE id = ?", (external_id, payment_id))
            await db.commit()

    async def get_payment(self, payment_id: int) -> Payment | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)) as cur:
                row = await cur.fetchone()
        return _payment(row) if row else None

    async def get_payment_by_external_id(self, provider: str, external_id: str) -> Payment | None:
        async with aiosqlite.connect(self._path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE provider = ? AND external_id = ?", (provider, external_id)
            ) as cur:
                row = await cur.fetchone()
        return _payment(row) if row else None

    async def mark_payment_paid(self, payment_id: int) -> bool:
        """True, если платёж только что переведён в paid (защита от повторных вебхуков)."""
        async with aiosqlite.connect(self._path) as db:
            cur = await db.execute(
                "UPDATE payments SET status = 'paid', paid_at = ? WHERE id = ? AND status != 'paid'",
                (_now(), payment_id),
            )
            await db.commit()
            return cur.rowcount == 1

    async def stats(self) -> dict[str, int]:
        async with aiosqlite.connect(self._path) as db:

            async def scalar(sql: str, params: tuple[object, ...] = ()) -> int:
                async with db.execute(sql, params) as cur:
                    row = await cur.fetchone()
                return int(row[0] or 0) if row else 0

            return {
                "users": await scalar("SELECT COUNT(*) FROM users"),
                "onboarded": await scalar("SELECT COUNT(*) FROM users WHERE onboarded = 1"),
                "generations": await scalar("SELECT COUNT(*) FROM generations"),
                "premium": await scalar("SELECT COUNT(*) FROM users WHERE premium_until > ?", (_now(),)),
                "paid": await scalar("SELECT COUNT(*) FROM payments WHERE status = 'paid'"),
                "revenue": await scalar("SELECT SUM(amount) FROM payments WHERE status = 'paid'"),
            }
