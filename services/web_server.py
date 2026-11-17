import logging
from typing import Optional

from aiohttp import web
from aiogram import Bot, Dispatcher

from config import settings
from services.web_dashboard import register_dashboard_routes
from services.yookassa_webhook import yookassa_webhook_handler

logger = logging.getLogger(__name__)


async def start_web_server(bot: Bot, dp: Optional[Dispatcher] = None) -> Optional[web.AppRunner]:
    """
    Unified aiohttp web server runner.
    Mounts Telegram webhook, YooKassa webhook handler, and/or Admin Web Dashboard onto a single HTTP application on port 8080.
    """
    is_tg_webhook = bool(settings.telegram_webhook_enabled and dp is not None)
    is_webhook_active = settings.webhook_enabled
    is_dashboard_active = settings.dashboard_enabled

    if not is_tg_webhook and not is_webhook_active and not is_dashboard_active:
        logger.info("Web server is disabled (no webhooks or dashboard enabled).")
        return None

    app = web.Application()
    app["bot"] = bot

    # Mount Telegram Webhook handler
    if is_tg_webhook:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

        tg_handler = SimpleRequestHandler(
            dispatcher=dp,
            bot=bot,
            secret_token=settings.telegram_webhook_secret or None,
        )
        tg_handler.register(app, path=settings.telegram_webhook_path)
        setup_application(app, dp, bot=bot)
        logger.info("Mounted Telegram webhook handler at %s", settings.telegram_webhook_path)

    # Mount YooKassa webhook route
    if is_webhook_active:
        app.router.add_post(settings.webhook_path, yookassa_webhook_handler)
        logger.info("Mounted YooKassa webhook handler at %s", settings.webhook_path)

    # Mount Admin Web Dashboard routes
    if is_dashboard_active:
        register_dashboard_routes(app)
        logger.info("Mounted Admin Web Dashboard routes (/dashboard, /payments, /generations, /users)")

    runner = web.AppRunner(app)
    await runner.setup()

    host = settings.dashboard_host if is_dashboard_active else settings.webhook_host
    port = settings.dashboard_port if is_dashboard_active else settings.webhook_port

    site = web.TCPSite(runner, host, port)

    try:
        await site.start()
        logger.info(
            "Web server successfully started on http://%s:%s (Dashboard: %s, YooKassa: %s, Telegram Webhook: %s)",
            host,
            port,
            "Active" if is_dashboard_active else "Off",
            "Active" if is_webhook_active else "Off",
            "Active" if is_tg_webhook else "Off",
        )
        return runner
    except Exception as exc:
        logger.warning(
            "Could not start unified web server on %s:%s: %s (Background poller will still process payments!)",
            host,
            port,
            exc,
        )
        return None
