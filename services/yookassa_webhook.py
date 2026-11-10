import asyncio
import logging
from typing import Optional
from aiohttp import web
from aiogram import Bot

from config import settings
from database.db import db
from services.payment_service import process_successful_payment, process_canceled_payment
from services.yookassa import yookassa_client

logger = logging.getLogger(__name__)


async def yookassa_webhook_handler(request: web.Request) -> web.Response:
    """
    Handles incoming HTTP POST webhook notifications from YooKassa:
    - Event 'payment.succeeded'
    - Event 'payment.canceled'
    """
    bot: Bot = request.app["bot"]

    try:
        data = await request.json()
    except Exception as exc:
        logger.warning("Invalid JSON in YooKassa webhook request: %s", exc)
        return web.Response(status=400, text="Bad Request")

    event = data.get("event")
    obj = data.get("object", {})
    payment_id = obj.get("id")

    logger.info("Received YooKassa webhook: event=%s, payment_id=%s", event, payment_id)

    if not payment_id:
        return web.Response(status=200, text="OK")

    if event == "payment.succeeded":
        # Independently verify status with YooKassa API for bulletproof security
        try:
            verified = await yookassa_client.get_payment(payment_id)
            if verified.get("status") == "succeeded":
                await process_successful_payment(bot, payment_id)
            else:
                logger.warning(
                    "Webhook reported succeeded, but API returned %s for payment %s",
                    verified.get("status"),
                    payment_id,
                )
        except Exception as exc:
            logger.error("Failed to verify payment %s with YooKassa API: %s. Background poller will retry safely.", payment_id, exc)

    elif event == "payment.canceled":
        await process_canceled_payment(payment_id)

    return web.Response(status=200, text="OK")


async def background_payments_poller(bot: Bot) -> None:
    """
    Safety net background worker:
    1. Periodically checks pending payments in DB against YooKassa API.
    2. Periodically checks Treblo API balance and alerts admins if credits are low.
    """
    logger.info(
        "Background poller started (payments interval: %s sec)",
        settings.background_poller_interval_sec,
    )

    last_treblo_check = 0.0

    while True:
        try:
            # Check Treblo API balance every 10 minutes (or on startup)
            now = asyncio.get_event_loop().time()
            if now - last_treblo_check > 600 or last_treblo_check == 0.0:
                last_treblo_check = now
                try:
                    from services.admin_alerts import check_treblo_credits_and_alert
                    await check_treblo_credits_and_alert(bot)
                except Exception as e:
                    logger.debug("Treblo balance background check: %s", e)

            # Periodically mark abandoned pending payments older than 2 hours as canceled
            try:
                await db.cleanup_stale_payments(max_age_hours=2)
            except Exception as e:
                logger.debug("Cleanup stale payments error: %s", e)

            # Check YooKassa pending payments
            if yookassa_client.is_configured:
                pending_payments = await db.get_pending_payments(limit=30)
                for p in pending_payments:
                    pid = p["payment_id"]
                    try:
                        payment_info = await yookassa_client.get_payment(pid)
                        status = payment_info.get("status")

                        if status == "succeeded":
                            logger.info("Background poller discovered successful payment %s", pid)
                            await process_successful_payment(bot, pid)
                        elif status == "canceled":
                            logger.info("Background poller discovered canceled payment %s", pid)
                            await process_canceled_payment(pid)
                    except Exception as err:
                        err_str = str(err)
                        if "429" in err_str:
                            logger.warning(
                                "YooKassa rate limit (429) hit in background poller. Backing off for 60s..."
                            )
                            await asyncio.sleep(60)
                            break
                        logger.debug("Background poller check error for %s: %s", pid, err)

                    # Pacing: avoid sending bursts of requests (max ~4-5 req/sec to stay well under YooKassa limits)
                    await asyncio.sleep(0.25)
        except Exception as exc:
            logger.error("Unexpected error in background payments poller: %s", exc)

        await asyncio.sleep(settings.background_poller_interval_sec)


async def start_webhook_server(bot: Bot) -> Optional[web.AppRunner]:
    """Starts the aiohttp HTTP server to receive YooKassa webhook notifications."""
    if not settings.webhook_enabled:
        logger.info("YooKassa Webhook server is disabled in config.")
        return None

    app = web.Application()
    app["bot"] = bot
    app.router.add_post(settings.webhook_path, yookassa_webhook_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)

    try:
        await site.start()
        logger.info(
            "YooKassa Webhook server listening at http://%s:%s%s",
            settings.webhook_host,
            settings.webhook_port,
            settings.webhook_path,
        )
        return runner
    except Exception as exc:
        logger.warning(
            "Could not start webhook server on %s:%s: %s (Background poller will still process payments!)",
            settings.webhook_host,
            settings.webhook_port,
            exc,
        )
        return None
