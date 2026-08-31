from __future__ import annotations

import time

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import ChatMemberUpdated, Message

from context import AppContext
from formatting import format_info_card, welcome_keyboard
from resolve import resolve_target_user
from services import telegram_chat
from services.notify import notify_admins_join

router = Router(name="chat")


def _is_join(event: ChatMemberUpdated) -> bool:
    old = event.old_chat_member.status
    new = event.new_chat_member.status
    return old in {"left", "kicked"} and new in {"member", "restricted"}


@router.my_chat_member()
async def on_bot_chat_member(event: ChatMemberUpdated, ctx: AppContext) -> None:
    chat = event.chat
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return
    await ctx.db.upsert_chat(chat.id, chat.title)


@router.chat_member()
async def on_user_join(event: ChatMemberUpdated, bot: Bot, ctx: AppContext) -> None:
    if not _is_join(event):
        return
    chat = event.chat
    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        return

    user = event.new_chat_member.user
    if user.is_bot:
        return

    await ctx.db.upsert_chat(chat.id, chat.title)
    await ctx.db.upsert_user(user.id, user.username)

    if await ctx.db.anketa_completed(user.id):
        try:
            await telegram_chat.unmute_member(bot, chat.id, user.id)
        except Exception:
            pass
        now = time.time()
        await ctx.db.upsert_member(
            user.id,
            chat.id,
            joined_at=now,
            deadline_at=None,
            muted=False,
        )
        return

    now = time.time()
    deadline = now + ctx.config.deadline_hours * 3600
    try:
        await telegram_chat.mute_member(bot, chat.id, user.id)
    except Exception:
        pass

    await ctx.db.upsert_member(
        user.id,
        chat.id,
        joined_at=now,
        deadline_at=deadline,
        muted=True,
    )

    hours = ctx.config.deadline_hours
    text = ctx.config.texts.get("welcome", "").format(hours=hours)
    start_label = ctx.config.texts.get("start_button", "Начать")
    kb = welcome_keyboard(ctx.bot_username, chat.id, start_label)
    try:
        msg = await bot.send_message(chat.id, text, reply_markup=kb)
        await ctx.db.set_welcome_message(user.id, chat.id, msg.message_id)
    except Exception:
        pass

    await notify_admins_join(
        bot,
        ctx.db,
        ctx.config,
        user_id=user.id,
        username=user.username,
        chat_id=chat.id,
        chat_title=chat.title,
    )


@router.message(Command("info"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE}))
async def cmd_info(message: Message, ctx: AppContext) -> None:
    target = await resolve_target_user(ctx.db, message)
    if target is None:
        if message.from_user:
            user_id, username = message.from_user.id, message.from_user.username
            await ctx.db.upsert_user(user_id, username)
        else:
            return
    else:
        user_id, username = target
        row = await ctx.db.get_user(user_id)
        if row and row["username"]:
            username = row["username"]

    answers = await ctx.db.get_answers(user_id)
    text = format_info_card(
        username=username,
        user_id=user_id,
        answers=answers,
    )
    await message.answer(text)
