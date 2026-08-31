from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "bot.sqlite3"
CONFIG_PATH = ROOT / "config.yaml"


@dataclass
class Question:
    id: str
    prompt: str
    type: str
    required: bool = True
    max_length: int | None = None
    options: list[str] = field(default_factory=list)
    skippable: bool = False
    columns: int = 1


@dataclass
class AppConfig:
    bot_token: str
    super_admin_id: int
    deadline_hours: int
    reminder_hours_before: int
    texts: dict[str, str]
    questions: list[Question]
    proxy_url: str | None = None
    api_base: str | None = None

    def question_by_id(self, question_id: str) -> Question | None:
        for q in self.questions:
            if q.id == question_id:
                return q
        return None

    def question_index(self, question_id: str) -> int:
        for i, q in enumerate(self.questions):
            if q.id == question_id:
                return i
        return -1


def encode_chat_payload(chat_id: int) -> str:
    """Telegram start payload: A-Za-z0-9_-, max 64 chars."""
    s = str(chat_id)
    if s.startswith("-"):
        return f"g_m{s[1:]}"
    return f"g_{s}"


def decode_chat_payload(payload: str) -> int | None:
    if not payload.startswith("g_"):
        return None
    body = payload[2:]
    try:
        if body.startswith("m"):
            return -int(body[1:])
        return int(body)
    except ValueError:
        return None


def load_config() -> AppConfig:
    load_dotenv(ROOT / ".env")
    token = os.getenv("BOT_TOKEN", "").strip()
    super_raw = os.getenv("SUPER_ADMIN_ID", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is missing in .env")
    if not super_raw:
        raise RuntimeError("SUPER_ADMIN_ID is missing in .env")

    with CONFIG_PATH.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    questions: list[Question] = []
    for item in raw.get("questions", []):
        questions.append(
            Question(
                id=str(item["id"]),
                prompt=str(item["prompt"]).strip(),
                type=str(item.get("type", "text")),
                required=bool(item.get("required", True)),
                max_length=item.get("max_length"),
                options=list(item.get("options") or []),
                skippable=bool(item.get("skippable", not item.get("required", True))),
                columns=int(item.get("columns") or 1),
            )
        )
    if not questions:
        raise RuntimeError("config.yaml has no questions")

    texts = {k: str(v).strip() for k, v in (raw.get("texts") or {}).items()}
    proxy = os.getenv("PROXY_URL", "").strip() or None
    api_base = os.getenv("TELEGRAM_API_BASE", "").strip().rstrip("/") or None
    return AppConfig(
        bot_token=token,
        super_admin_id=int(super_raw),
        deadline_hours=int(raw.get("deadline_hours", 48)),
        reminder_hours_before=int(raw.get("reminder_hours_before", 6)),
        texts=texts,
        questions=questions,
        proxy_url=proxy,
        api_base=api_base,
    )
