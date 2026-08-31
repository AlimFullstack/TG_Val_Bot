from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import PRODUCTION, TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from context import AppContext
from db import Database
from handlers import admin, chat, dm
from jobs import process_deadlines
from middleware import ContextMiddleware
from settings import DB_PATH, load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("tgbot")


async def main() -> None:
    config = load_config()
    db = Database(DB_PATH)
    await db.connect()
    await db.ensure_super_admin(config.super_admin_id)

    api = (
        TelegramAPIServer.from_base(config.api_base)
        if config.api_base
        else PRODUCTION
    )
    session_kwargs: dict = {"api": api}
    if config.proxy_url:
        session_kwargs["proxy"] = config.proxy_url
    session = AiohttpSession(**session_kwargs)

    if config.api_base:
        logger.info("Using Telegram API base: %s", config.api_base)
    if config.proxy_url:
        logger.info("Using proxy: %s", config.proxy_url)

    bot = Bot(token=config.bot_token, session=session)
    me = await bot.get_me()
    ctx = AppContext(db=db, config=config, bot_username=me.username or "")

    dp = Dispatcher(storage=MemoryStorage())
    dp.update.middleware(ContextMiddleware(ctx))
    dp.include_router(admin.router)
    dp.include_router(dm.router)
    dp.include_router(chat.router)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        process_deadlines,
        "interval",
        minutes=1,
        args=[bot, ctx],
        id="deadlines",
        replace_existing=True,
    )
    scheduler.start()

    logger.info("Bot @%s started", ctx.bot_username)
    try:
        await dp.start_polling(
            bot,
            allowed_updates=[
                "message",
                "callback_query",
                "chat_member",
                "my_chat_member",
            ],
        )
    finally:
        scheduler.shutdown(wait=False)
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
