from __future__ import annotations

from dataclasses import dataclass

from db import Database
from settings import AppConfig


@dataclass
class AppContext:
    db: Database
    config: AppConfig
    bot_username: str = ""
