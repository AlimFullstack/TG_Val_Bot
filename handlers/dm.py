from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from context import AppContext
from formatting import edit_fields_keyboard, question_keyboard
from services import telegram_chat
from services.notify import update_admin_alerts
from settings import decode_chat_payload

router = Router(name="dm")


class AnketaStates(StatesGroup):
    answering = State()
    editing_value = State()


async def _ask_question(message: Message, ctx: AppContext, index: int) -> None:
    questions = ctx.config.questions
    total = len(questions)
    q = questions[index]
    skip_label = ctx.config.texts.get("skip_button", "Пропустить")
    header = f"Вопрос {index + 1} из {total}\n\n{q.prompt}"
    await message.answer(header, reply_markup=question_keyboard(q, skip_label))


async def _finish_anketa(message: Message, bot: Bot, ctx: AppContext, state: FSMContext) -> None:
    user = message.from_user
    if not user:
        return
    await ctx.db.mark_anketa_completed(user.id)
    await ctx.db.clear_progress(user.id)
    await state.clear()

    muted = await ctx.db.get_muted_memberships(user.id)
    for row in muted:
        chat_id = int(row["chat_id"])
        try:
            await telegram_chat.unmute_member(bot, chat_id, user.id)
        except Exception:
            pass
        await ctx.db.unmute_member(user.id, chat_id)

    await message.answer(
        ctx.config.texts.get("anketa_done", "Анкета сохранена."),
        reply_markup=ReplyKeyboardRemove(),
    )
    await update_admin_alerts(
        bot,
        ctx.db,
        ctx.config,
        user_id=user.id,
        username=user.username,
        chat_id=None,
        completed=True,
    )


@router.message(Command("start"), F.chat.type == ChatType.PRIVATE)
async def cmd_start(
    message: Message,
    command: CommandObject,
    state: FSMContext,
    bot: Bot,
    ctx: AppContext,
) -> None:
    user = message.from_user
    if not user:
        return
    await ctx.db.upsert_user(user.id, user.username)

    chat_id: int | None = None
    if command.args:
        chat_id = decode_chat_payload(command.args.strip())

    if await ctx.db.anketa_completed(user.id):
        if chat_id is not None:
            try:
                await telegram_chat.unmute_member(bot, chat_id, user.id)
            except Exception:
                pass
            await ctx.db.unmute_member(user.id, chat_id)
        await message.answer(
            "Анкета уже заполнена. Доступ к чату открыт.\n"
            "Чтобы изменить ответы, используйте /edit_anketa"
        )
        return

    progress = await ctx.db.get_progress(user.id)
    index = int(progress["question_index"]) if progress else 0
    if chat_id is not None:
        await ctx.db.set_progress(user.id, index, chat_id)
    elif progress is None:
        await ctx.db.set_progress(user.id, 0, None)

    prompt = ctx.config.texts.get("start_prompt", "Заполните анкету.")
    await message.answer(prompt)
    await state.set_state(AnketaStates.answering)
    await state.update_data(edit_question_id=None)
    await _ask_question(message, ctx, index)


@router.message(
    AnketaStates.answering,
    F.chat.type == ChatType.PRIVATE,
    F.text,
    ~F.text.startswith("/"),
)
async def on_anketa_answer(
    message: Message, state: FSMContext, bot: Bot, ctx: AppContext
) -> None:
    user = message.from_user
    if not user:
        return

    progress = await ctx.db.get_progress(user.id)
    index = int(progress["question_index"]) if progress else 0
    questions = ctx.config.questions
    if index < 0 or index >= len(questions):
        index = 0

    q = questions[index]
    skip_label = ctx.config.texts.get("skip_button", "Пропустить")
    text = (message.text or "").strip()

    if text == skip_label and (q.skippable or not q.required):
        await ctx.db.delete_answer(user.id, q.id)
    else:
        if q.type == "buttons":
            if text not in q.options:
                await message.answer("Выберите один из вариантов на клавиатуре.")
                return
        else:
            if not text:
                await message.answer("Отправьте текстовый ответ.")
                return
            if q.max_length and len(text) > q.max_length:
                await message.answer(
                    f"Слишком длинный ответ. Максимум {q.max_length} символов."
                )
                return
        await ctx.db.set_answer(user.id, q.id, text)

    # Update admin alerts for related muted chats
    muted = await ctx.db.get_muted_memberships(user.id)
    for row in muted:
        await update_admin_alerts(
            bot,
            ctx.db,
            ctx.config,
            user_id=user.id,
            username=user.username,
            chat_id=int(row["chat_id"]),
        )

    next_index = index + 1
    if next_index >= len(questions):
        await _finish_anketa(message, bot, ctx, state)
        return

    await ctx.db.set_progress(
        user.id,
        next_index,
        int(progress["chat_id"]) if progress and progress["chat_id"] else None,
    )
    await _ask_question(message, ctx, next_index)


@router.message(Command("edit_anketa"), F.chat.type == ChatType.PRIVATE)
async def cmd_edit_anketa(message: Message, state: FSMContext, ctx: AppContext) -> None:
    user = message.from_user
    if not user:
        return
    if not await ctx.db.anketa_completed(user.id):
        await message.answer("Сначала заполните анкету через /start")
        return
    await state.clear()
    await message.answer(
        "Выберите поле для редактирования:",
        reply_markup=edit_fields_keyboard(ctx.config),
    )


@router.callback_query(F.data == "edit:done")
async def edit_done(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Редактирование завершено.")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data.startswith("edit:"))
async def edit_pick_field(callback: CallbackQuery, state: FSMContext, ctx: AppContext) -> None:
    qid = (callback.data or "").split(":", 1)[1]
    if qid == "done":
        return
    question = ctx.config.question_by_id(qid)
    if not question:
        await callback.answer("Неизвестное поле", show_alert=True)
        return
    await state.set_state(AnketaStates.editing_value)
    await state.update_data(edit_question_id=qid)
    skip_label = ctx.config.texts.get("skip_button", "Пропустить")
    await callback.message.answer(  # type: ignore[union-attr]
        f"{question.prompt}\nОтправьте новое значение:",
        reply_markup=question_keyboard(question, skip_label),
    )
    await callback.answer()


@router.message(
    AnketaStates.editing_value,
    F.chat.type == ChatType.PRIVATE,
    F.text,
    ~F.text.startswith("/"),
)
async def on_edit_value(message: Message, state: FSMContext, ctx: AppContext) -> None:
    user = message.from_user
    if not user:
        return
    data = await state.get_data()
    qid = data.get("edit_question_id")
    question = ctx.config.question_by_id(qid) if qid else None
    if not question:
        await state.clear()
        await message.answer("Сессия редактирования сброшена.")
        return

    skip_label = ctx.config.texts.get("skip_button", "Пропустить")
    text = (message.text or "").strip()

    if text == skip_label and (question.skippable or not question.required):
        await ctx.db.delete_answer(user.id, question.id)
    else:
        if question.type == "buttons":
            if text not in question.options:
                await message.answer("Выберите один из вариантов на клавиатуре.")
                return
        else:
            if not text:
                await message.answer("Отправьте текстовый ответ.")
                return
            if question.max_length and len(text) > question.max_length:
                await message.answer(
                    f"Слишком длинный ответ. Максимум {question.max_length} символов."
                )
                return
        await ctx.db.set_answer(user.id, question.id, text)

    await state.clear()
    await message.answer("Сохранено.", reply_markup=ReplyKeyboardRemove())
    await message.answer(
        "Выберите другое поле или нажмите Готово.",
        reply_markup=edit_fields_keyboard(ctx.config),
    )

