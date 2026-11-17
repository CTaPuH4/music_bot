import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.utils.backoff import BackoffConfig

from config import settings
from database.db import db
from handlers.admin import admin_router
from handlers.common import common_router
from handlers.generation import generation_router
from handlers.payments import payments_router
from services.web_server import start_web_server
from services.yookassa_webhook import background_payments_poller

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
        BotCommand(command="topup", description="💳 Пополнить баланс"),
        BotCommand(command="help", description="ℹ️ Инструкция и примеры"),
        BotCommand(command="start", description="🔄 Перезапустить бота"),
    ]
    for attempt in range(5):
        try:
            await bot.set_my_commands(commands)
            logger.info("Telegram bot menu commands registered.")
            return
        except Exception as e:
            logger.warning(
                "Attempt %d/5: could not set bot commands: %s. Retrying in 10s...",
                attempt + 1,
                e,
            )
            await asyncio.sleep(10)


async def register_telegram_webhook(bot: Bot) -> None:
    webhook_url = f"{settings.dashboard_base_url.rstrip('/')}{settings.telegram_webhook_path}"
    logger.info("Registering Telegram webhook: %s", webhook_url)
    while True:
        try:
            await bot.set_webhook(
                url=webhook_url,
                secret_token=settings.telegram_webhook_secret or None,
                allowed_updates=["message", "callback_query", "pre_checkout_query"],
                drop_pending_updates=False,
            )
            logger.info("Telegram webhook successfully registered at %s", webhook_url)
            break
        except Exception as e:
            logger.warning("Failed to register Telegram webhook (%s). Retrying in 10s...", e)
            await asyncio.sleep(10)


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

    # Initialize bot and dispatcher with increased HTTP timeout (120s for media/audio uploads)
    session = AiohttpSession(timeout=120.0)
    bot = Bot(
        token=settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = setup_dispatcher()

    # Start unified Web server (Telegram Webhook + YooKassa Webhook + Admin Web Dashboard)
    web_runner = None
    if settings.webhook_enabled or settings.dashboard_enabled or settings.telegram_webhook_enabled:
        web_runner = await start_web_server(bot, dp=dp)

    # Background workers: commands registration, payments poller
    commands_task = asyncio.create_task(set_bot_commands(bot))
    poller_task = asyncio.create_task(background_payments_poller(bot))
    webhook_reg_task = None

    try:
        if settings.telegram_webhook_enabled:
            logger.info("Telegram Bot is running in WEBHOOK mode.")
            webhook_reg_task = asyncio.create_task(register_telegram_webhook(bot))
            stop_event = asyncio.Event()
            await stop_event.wait()
        else:
            logger.info("Telegram Bot is running in POLLING mode.")
            while True:
                try:
                    await bot.delete_webhook(drop_pending_updates=False)
                    await dp.start_polling(
                        bot,
                        polling_timeout=15,
                        allowed_updates=["message", "callback_query", "pre_checkout_query"],
                        backoff_config=BackoffConfig(min_delay=1.0, max_delay=3.5, factor=1.2, jitter=0.1),
                    )
                    break
                except (asyncio.CancelledError, KeyboardInterrupt):
                    break
                except Exception as e:
                    logger.error("Polling error or connection lost: %s. Reconnecting in 10s...", e)
                    await asyncio.sleep(10)
    finally:
        if webhook_reg_task:
            webhook_reg_task.cancel()
        if commands_task:
            commands_task.cancel()
        if poller_task:
            poller_task.cancel()
        if web_runner:
            await web_runner.cleanup()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot shut down.")
