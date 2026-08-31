from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from db import Database
from formatting import format_admin_join_alert
from settings import AppConfig


async def notify_admins_join(
    bot: Bot,
    db: Database,
    config: AppConfig,
    *,
    user_id: int,
    username: str | None,
    chat_id: int,
    chat_title: str | None,
) -> None:
    answers = await db.get_answers(user_id)
    text = format_admin_join_alert(
        username=username,
        user_id=user_id,
        chat_id=chat_id,
        chat_title=chat_title,
        answers=answers,
    )
    for admin_id in await db.list_admins():
        try:
            msg = await bot.send_message(admin_id, text)
            await db.save_admin_alert(user_id, chat_id, admin_id, msg.message_id)
        except (TelegramForbiddenError, TelegramBadRequest):
            continue


async def update_admin_alerts(
    bot: Bot,
    db: Database,
    config: AppConfig,
    *,
    user_id: int,
    username: str | None,
    chat_id: int | None,
    chat_title: str | None = None,
    completed: bool = False,
) -> None:
    answers = await db.get_answers(user_id)

    if completed:
        memberships = await db.get_memberships(user_id)
        for m in memberships:
            cid = int(m["chat_id"])
            chat_row = await db.get_chat(cid)
            title = chat_row["title"] if chat_row and chat_row["title"] else None
            await _edit_or_send(
                bot,
                db,
                config,
                user_id=user_id,
                username=username,
                chat_id=cid,
                chat_title=title,
                answers=answers,
            )
        return

    if chat_id is None:
        return

    chat_row = await db.get_chat(chat_id)
    title = chat_title or (chat_row["title"] if chat_row and chat_row["title"] else None)
    await _edit_or_send(
        bot,
        db,
        config,
        user_id=user_id,
        username=username,
        chat_id=chat_id,
        chat_title=title,
        answers=answers,
    )


async def _edit_or_send(
    bot: Bot,
    db: Database,
    config: AppConfig,
    *,
    user_id: int,
    username: str | None,
    chat_id: int,
    chat_title: str | None,
    answers: dict[str, str],
) -> None:
    text = format_admin_join_alert(
        username=username,
        user_id=user_id,
        chat_id=chat_id,
        chat_title=chat_title,
        answers=answers,
    )
    alerts = await db.get_admin_alerts(user_id, chat_id)
    if not alerts:
        await notify_admins_join(
            bot,
            db,
            config,
            user_id=user_id,
            username=username,
            chat_id=chat_id,
            chat_title=chat_title,
        )
        return
    for alert in alerts:
        admin_id = int(alert["admin_id"])
        try:
            await bot.edit_message_text(
                text=text,
                chat_id=admin_id,
                message_id=int(alert["message_id"]),
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            try:
                msg = await bot.send_message(admin_id, text)
                await db.save_admin_alert(user_id, chat_id, admin_id, msg.message_id)
            except (TelegramForbiddenError, TelegramBadRequest):
                continue
