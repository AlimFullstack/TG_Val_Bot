from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove

from settings import AppConfig, Question, encode_chat_payload

PROFILE_FIELDS: list[tuple[str, str]] = [
    ("name", "Имя"),
    ("age", "Возраст"),
    ("rank", "Ранг в пике"),
    ("valorant_nick", "Ник в валоранте"),
    ("playtime", "Всего в валоранте"),
    ("about", "Дополнительная информация"),
]


def start_url(bot_username: str, chat_id: int) -> str:
    return f"https://t.me/{bot_username}?start={encode_chat_payload(chat_id)}"


def welcome_keyboard(bot_username: str, chat_id: int, start_label: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=start_label,
                    url=start_url(bot_username, chat_id),
                )
            ]
        ]
    )


def question_keyboard(question: Question, skip_label: str) -> ReplyKeyboardMarkup | ReplyKeyboardRemove:
    if question.type == "buttons" and question.options:
        cols = max(1, question.columns)
        rows: list[list[KeyboardButton]] = []
        row: list[KeyboardButton] = []
        for opt in question.options:
            row.append(KeyboardButton(text=opt))
            if len(row) == cols:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        if question.skippable or not question.required:
            rows.append([KeyboardButton(text=skip_label)])
        return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)
    if question.skippable or not question.required:
        return ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=skip_label)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    return ReplyKeyboardRemove()


def edit_fields_keyboard(config: AppConfig) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=q.prompt, callback_data=f"edit:{q.id}")]
        for q in config.questions
    ]
    rows.append([InlineKeyboardButton(text="Готово", callback_data="edit:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_user_label(username: str | None, user_id: int) -> str:
    if username:
        return f"@{username}"
    return f"id{user_id}"


def format_profile_fields(answers: dict[str, str]) -> str:
    lines: list[str] = []
    for field_id, label in PROFILE_FIELDS:
        value = answers.get(field_id)
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)


def format_info_card(
    *,
    username: str | None,
    user_id: int,
    answers: dict[str, str],
) -> str:
    header = f"Информация о {format_user_label(username, user_id)}"
    body = format_profile_fields(answers)
    if body:
        return f"{header}\n\n{body}"
    return header


def format_admin_join_alert(
    *,
    username: str | None,
    user_id: int,
    chat_id: int,
    chat_title: str | None,
    answers: dict[str, str],
) -> str:
    lines = [
        "Новый участник",
        f"Username: {format_user_label(username, user_id)}",
        f"Группа: {chat_title or chat_id} ({chat_id})",
        "",
    ]
    block = format_profile_fields(answers)
    if block:
        lines.append(block)
    else:
        lines.append("(пока пусто)")
    return "\n".join(lines)
