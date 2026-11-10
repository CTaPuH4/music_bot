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
from handlers.admin import admin_router
from handlers.common import common_router
from handlers.generation import generation_router
from handlers.payments import payments_router
from services.yookassa_webhook import start_webhook_server, background_payments_poller

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


def setup_dispatcher() -> Dispatcher:
    """Creates and configures the main Aiogram Dispatcher with routers in proper priority order."""
    dp = Dispatcher(storage=MemoryStorage())
    # Admin router must be first to give admin commands and states top priority
    dp.include_router(admin_router)
    dp.include_router(common_router)
    dp.include_router(generation_router)
    dp.include_router(payments_router)
    return dp


async def main() -> None:
    logger.info("Initializing Telegram Music Bot...")

    if settings.bot_token == "YOUR_BOT_TOKEN" or not settings.bot_token:
        logger.warning(
            "BOT_TOKEN is not configured in .env! Please set BOT_TOKEN from @BotFather."
        )

    if settings.treblo_api_key == "YOUR_TREBLO_API_KEY" or not settings.treblo_api_key:
        logger.warning(
            "TREBLO_API_KEY is not configured in .env! Please set your music generation API key."
        )

    # Initialize SQLite database
    await db.init()

    # Initialize bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = setup_dispatcher()

    # Set Telegram menu commands
    try:
        commands = [
            BotCommand(command="create", description="🎵 Создать музыку по промту"),
            BotCommand(command="profile", description="👤 Баланс и профиль"),
            BotCommand(command="topup", description="💳 Пополнить баланс"),
            BotCommand(command="help", description="ℹ️ Инструкция и примеры"),
            BotCommand(command="start", description="🔄 Перезапустить бота"),
        ]
        await bot.set_my_commands(commands)
    except Exception as e:
        logger.warning("Could not set bot commands: %s", e)

    # Start YooKassa Webhook server and background poller safety net
    webhook_runner = None
    if settings.webhook_enabled:
        webhook_runner = await start_webhook_server(bot)

    poller_task = asyncio.create_task(background_payments_poller(bot))

    logger.info("Bot is starting polling...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        if poller_task:
            poller_task.cancel()
        if webhook_runner:
            await webhook_runner.cleanup()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shut down.")
