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
                "UPDATE users SET niche = ?, tone = ?, services = ?, onboarded = 1 WHERE user_id = ?",
                (niche, tone, services, user_id),
            )
            await db.commit()

    async def log_generation(self, user_id: int, kind: str, user_input: str, result: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO generations (user_id, kind, user_input, result, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, kind, user_input, result, _now()),
            )
            await db.execute(
                "UPDATE users SET generations_used = generations_used + 1 WHERE user_id = ?",
                (user_id,),
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
            }
