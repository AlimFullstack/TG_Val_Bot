from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from context import AppContext
from services import telegram_chat

logger = logging.getLogger(__name__)


async def process_deadlines(bot: Bot, ctx: AppContext) -> None:
    now = time.time()
    remind_before = ctx.config.reminder_hours_before * 3600
    hours = ctx.config.reminder_hours_before

    for row in await ctx.db.due_reminders(now, remind_before):
        user_id = int(row["user_id"])
        chat_id = int(row["chat_id"])
        dm_text = ctx.config.texts.get("reminder_dm", "").format(hours=hours)
        group_text = ctx.config.texts.get("reminder_group", "").format(hours=hours)

        try:
            await bot.send_message(user_id, dm_text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass

        welcome_id = row["welcome_message_id"]
        try:
            if welcome_id:
                await bot.send_message(
                    chat_id,
                    group_text,
                    reply_to_message_id=int(welcome_id),
                )
            else:
                await bot.send_message(chat_id, group_text)
        except (TelegramForbiddenError, TelegramBadRequest):
            pass

        await ctx.db.mark_reminder_sent(user_id, chat_id)

    for row in await ctx.db.due_kicks(now):
        user_id = int(row["user_id"])
        chat_id = int(row["chat_id"])
        try:
            await telegram_chat.kick_member(bot, chat_id, user_id)
            await ctx.db.add_kick(user_id, chat_id, "timeout")
            await ctx.db.delete_member(user_id, chat_id)
            logger.info("Kicked user %s from chat %s (timeout)", user_id, chat_id)
        except Exception as exc:
            logger.warning("Kick failed user=%s chat=%s: %s", user_id, chat_id, exc)
            # Avoid tight retry loop on permanent errors: mark reminder and push deadline
            await ctx.db.mark_reminder_sent(user_id, chat_id)
