import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import settings
from database.db import db
from handlers.common import common_router
from handlers.generation import generation_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("music_bot")


async def set_bot_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="create", description="🎵 Создать музыку по промту"),
        BotCommand(command="profile", description="👤 Баланс и профиль"),
        BotCommand(command="help", description="ℹ️ Инструкция и примеры"),
        BotCommand(command="start", description="🔄 Перезапустить бота"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    logger.info("Initializing Telegram Music Bot...")

    if settings.bot_token == "YOUR_BOT_TOKEN" or not settings.bot_token:
        logger.warning(
            "BOT_TOKEN is not configured in .env! Please set BOT_TOKEN from @BotFather."
        )

    if settings.treblo_api_key == "YOUR_TREBLO_API_KEY" or not settings.treblo_api_key:
        logger.warning(
            "TREBLO_API_KEY is not configured in .env! Please set your Treblo API key from https://treblo.com"
        )

    # Initialize SQLite database
    await db.init()

    # Initialize bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Include routers
    dp.include_router(common_router)
    dp.include_router(generation_router)

    # Set Telegram menu commands
    try:
        await set_bot_commands(bot)
    except Exception as e:
        logger.warning("Could not set bot commands: %s", e)

    logger.info("Bot is starting polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shut down.")
