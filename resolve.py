from __future__ import annotations

import re
from typing import TYPE_CHECKING

from aiogram.types import Message, User

if TYPE_CHECKING:
    from db import Database


USERNAME_RE = re.compile(r"^@?([A-Za-z0-9_]{5,})$")


async def resolve_target_user(
    db: Database,
    message: Message,
    raw_arg: str | None = None,
) -> tuple[int, str | None] | None:
    """Resolve user from reply, @username, or numeric id."""
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        if not u.is_bot:
            await db.upsert_user(u.id, u.username)
            return u.id, u.username

    text = (raw_arg or "").strip()
    if not text and message.text:
        parts = message.text.split(maxsplit=1)
        text = parts[1].strip() if len(parts) > 1 else ""

    if not text:
        return None

    if text.lstrip("-").isdigit():
        user_id = int(text)
        row = await db.get_user(user_id)
        return user_id, (row["username"] if row else None)

    m = USERNAME_RE.match(text)
    if m:
        username = m.group(1)
        row = await db.find_user_by_username(username)
        if row:
            return int(row["user_id"]), row["username"]
        return None

    return None


def display_name(user: User) -> str:
    if user.username:
        return f"@{user.username}"
    return user.full_name or str(user.id)
