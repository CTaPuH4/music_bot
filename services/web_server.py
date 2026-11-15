import logging
from typing import Optional

from aiohttp import web
from aiogram import Bot

from config import settings
from services.web_dashboard import register_dashboard_routes
from services.yookassa_webhook import yookassa_webhook_handler

logger = logging.getLogger(__name__)


async def start_web_server(bot: Bot) -> Optional[web.AppRunner]:
    """
    Unified aiohttp web server runner.
    Mounts YooKassa webhook handler and/or Admin Web Dashboard onto a single HTTP application on port 8080.
    """
    is_webhook_active = settings.webhook_enabled
    is_dashboard_active = settings.dashboard_enabled

    if not is_webhook_active and not is_dashboard_active:
        logger.info("Web server is disabled (both webhook_enabled and dashboard_enabled are False).")
        return None

    app = web.Application()
    app["bot"] = bot

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
            "Web server successfully started on http://%s:%s (Dashboard: %s, Webhook: %s)",
            host,
            port,
            "Active" if is_dashboard_active else "Off",
            "Active" if is_webhook_active else "Off",
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
