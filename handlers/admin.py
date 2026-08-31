from __future__ import annotations

import time
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Message

from context import AppContext
from formatting import format_profile_fields, format_user_label
from resolve import resolve_target_user
from services import telegram_chat

router = Router(name="admin")


def _fmt_ts(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


async def _require_admin(message: Message, ctx: AppContext) -> bool:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Команда доступна только в личных сообщениях с ботом.")
        return False
    user = message.from_user
    if not user or not await ctx.db.is_admin(user.id):
        await message.answer("Недостаточно прав.")
        return False
    return True


async def _require_super(message: Message, ctx: AppContext) -> bool:
    if not await _require_admin(message, ctx):
        return False
    user = message.from_user
    if not user or user.id != ctx.config.super_admin_id:
        await message.answer("Команда только для супер-админа.")
        return False
    return True


@router.message(Command("admin_info"), F.chat.type == ChatType.PRIVATE)
async def cmd_admin_info(message: Message, ctx: AppContext) -> None:
    if not await _require_admin(message, ctx):
        return
    target = await resolve_target_user(ctx.db, message)
    if not target:
        await message.answer("Укажите пользователя: /admin_info @user или user_id (или реплай).")
        return
    user_id, username = target
    row = await ctx.db.get_user(user_id)
    if row and row["username"]:
        username = row["username"]

    lines = [
        f"Служебная информация: {format_user_label(username, user_id)}",
        f"user_id: {user_id}",
        f"Анкета завершена: {_fmt_ts(row['anketa_completed_at'] if row else None)}",
        "",
        "Входы в группы:",
    ]
    memberships = await ctx.db.get_memberships(user_id)
    if not memberships:
        lines.append("(нет)")
    else:
        for m in memberships:
            lines.append(
                f"- chat {m['chat_id']}: вход {_fmt_ts(m['joined_at'])}, "
                f"muted={bool(m['muted'])}, deadline={_fmt_ts(m['deadline_at'])}"
            )

    lines.append("")
    lines.append("Кики:")
    kicks = await ctx.db.get_kicks(user_id)
    if not kicks:
        lines.append("(нет)")
    else:
        for k in kicks[:20]:
            lines.append(
                f"- chat {k['chat_id']}: {_fmt_ts(k['kicked_at'])} ({k['reason']})"
            )

    answers = await ctx.db.get_answers(user_id)
    lines.append("")
    lines.append("Анкета:")
    block = format_profile_fields(answers)
    lines.append(block if block else "(пусто)")

    lines.append("")
    lines.append("История правок:")
    history = await ctx.db.get_answer_history(user_id)
    if not history:
        lines.append("(нет)")
    else:
        for h in history[:30]:
            lines.append(
                f"- {_fmt_ts(h['edited_at'])} {h['question_id']}: "
                f"{h['old_value']!r} -> {h['new_value']!r}"
            )

    await message.answer("\n".join(lines))


@router.message(Command("reset_anketa"), F.chat.type == ChatType.PRIVATE)
async def cmd_reset_anketa(message: Message, bot: Bot, ctx: AppContext) -> None:
    if not await _require_admin(message, ctx):
        return
    target = await resolve_target_user(ctx.db, message)
    if not target:
        await message.answer("Укажите пользователя: /reset_anketa @user")
        return
    user_id, _ = target
    await ctx.db.clear_anketa(user_id)
    deadline = time.time() + ctx.config.deadline_hours * 3600
    memberships = await ctx.db.get_memberships(user_id)
    for m in memberships:
        chat_id = int(m["chat_id"])
        try:
            await telegram_chat.mute_member(bot, chat_id, user_id)
        except Exception:
            pass
        await ctx.db.set_member_muted(user_id, chat_id, True, deadline_at=deadline)
    await message.answer(f"Анкета сброшена, пользователь {user_id} снова в mute.")


@router.message(Command("force_kick"), F.chat.type == ChatType.PRIVATE)
async def cmd_force_kick(message: Message, bot: Bot, ctx: AppContext) -> None:
    if not await _require_admin(message, ctx):
        return
    target = await resolve_target_user(ctx.db, message)
    if not target:
        await message.answer("Укажите пользователя: /force_kick @user")
        return
    user_id, _ = target
    memberships = await ctx.db.get_memberships(user_id)
    if not memberships:
        await message.answer("Нет известных групп для этого пользователя.")
        return
    kicked = 0
    for m in memberships:
        chat_id = int(m["chat_id"])
        try:
            await telegram_chat.kick_member(bot, chat_id, user_id)
            await ctx.db.add_kick(user_id, chat_id, "force")
            await ctx.db.delete_member(user_id, chat_id)
            kicked += 1
        except Exception:
            continue
    await message.answer(f"Кик выполнен в группах: {kicked}")


@router.message(Command("stats"), F.chat.type == ChatType.PRIVATE)
async def cmd_stats(message: Message, ctx: AppContext) -> None:
    if not await _require_admin(message, ctx):
        return
    s = await ctx.db.stats()
    await message.answer(
        "Статистика\n"
        f"В mute: {s['muted']}\n"
        f"Анкет заполнено: {s['completed']}\n"
        f"Киков за 24ч: {s['kicks_24h']}\n"
        f"Известных чатов: {s['chats']}"
    )


@router.message(Command("make_admin"), F.chat.type == ChatType.PRIVATE)
async def cmd_make_admin(message: Message, ctx: AppContext) -> None:
    if not await _require_super(message, ctx):
        return
    target = await resolve_target_user(ctx.db, message)
    if not target:
        await message.answer("Укажите пользователя: /make_admin @user или user_id")
        return
    user_id, _ = target
    await ctx.db.add_admin(user_id, message.from_user.id)  # type: ignore[union-attr]
    await message.answer(f"Пользователь {user_id} добавлен в whitelist админов.")


@router.message(Command("remove_admin"), F.chat.type == ChatType.PRIVATE)
async def cmd_remove_admin(message: Message, ctx: AppContext) -> None:
    if not await _require_super(message, ctx):
        return
    target = await resolve_target_user(ctx.db, message)
    if not target:
        await message.answer("Укажите пользователя: /remove_admin @user или user_id")
        return
    user_id, _ = target
    if user_id == ctx.config.super_admin_id:
        await message.answer("Нельзя снять супер-админа.")
        return
    ok = await ctx.db.remove_admin(user_id)
    if ok:
        await message.answer(f"Пользователь {user_id} удалён из whitelist.")
    else:
        await message.answer("Пользователь не был в whitelist.")
