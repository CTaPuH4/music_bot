import asyncio
import logging
import time
from typing import Optional
from aiohttp import web
from aiogram import Bot

from config import settings
from database.db import db
from services.payment_service import process_successful_payment, process_canceled_payment
from services.yookassa import yookassa_client
from services.cryptobot import cryptobot_client
from services.treblo import treblo_client

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


async def check_expiring_promo_reminders(bot: Bot) -> None:
    """
    Finds discount activations where remaining time is <= 2 hours,
    reminds the user that the discount will expire soon, and marks reminder_sent = 1.
    """
    try:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        pending = await db.get_pending_discount_reminders()
        for act in pending:
            act_id = act["id"]
            user_id = act["user_id"]
            ddata = act.get("discount_data") or {}
            dmode = ddata.get("discount_mode") or ddata.get("type", "fixed")

            active_code = act.get("code")
            if active_code:
                if dmode == "fixed" and ddata.get("percent"):
                    pct_str = f"промокод «{active_code}» (-{ddata.get('percent')}%)"
                else:
                    pct_str = f"промокод «{active_code}»"
            else:
                pct_str = "промокод на скидку"

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💳 Использовать скидку", callback_data="menu_topup"
                        ),
                    ],
                ]
            )

            text = (
                "⏰ <b>Ваша скидка скоро сгорит!</b>\n\n"
                f"Вы ранее активировали {pct_str}, но ещё не воспользовались им.\n"
                "До окончания действия скидки осталось <b>меньше 2 часов</b>!\n\n"
                "Успейте пополнить баланс по специальной цене, пока промокод активен:"
            )

            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode="HTML",
                )
                logger.info("Sent expiring promo reminder to user %s (activation %s)", user_id, act_id)
            except Exception as send_err:
                logger.debug("Failed to send promo reminder to %s: %s", user_id, send_err)
            finally:
                await db.mark_discount_reminder_sent(act_id)

    except Exception as exc:
        logger.debug("Error in check_expiring_promo_reminders: %s", exc)


async def background_payments_poller(bot: Bot) -> None:
    """
    Safety net background worker:
    1. Periodically checks pending payments in DB against YooKassa API.
    2. Periodically checks Treblo API balance and alerts admins if credits are low.
    """
    logger.info(
        "Background poller started (payments interval: %s sec, uptime interval: %s sec)",
        settings.background_poller_interval_sec,
        settings.uptime_check_interval_sec,
    )

    last_treblo_check = 0.0
    last_uptime_check = 0.0
    last_cleanup_check = 0.0

    while True:
        try:
            now = asyncio.get_event_loop().time()

            # Record health/uptime metrics for Bot and Treblo API (configurable interval, default 5 min)
            if now - last_uptime_check >= settings.uptime_check_interval_sec or last_uptime_check == 0.0:
                last_uptime_check = now
                try:
                    # 1. Record bot heartbeat
                    await db.record_uptime_check("bot", "UP", latency_ms=0.0)

                    # 2. Ping Treblo API and record latency
                    t_start = time.perf_counter()
                    bal_res = await treblo_client.get_account_balance()
                    t_latency = round((time.perf_counter() - t_start) * 1000, 1)

                    if isinstance(bal_res, dict) and "error" in bal_res and bal_res.get("status_code") != 200:
                        err_msg = str(bal_res.get("error"))
                        await db.record_uptime_check("treblo_api", "DOWN", latency_ms=t_latency, error_message=err_msg)
                    else:
                        await db.record_uptime_check("treblo_api", "UP", latency_ms=t_latency)
                except Exception as up_exc:
                    logger.debug("Uptime check error: %s", up_exc)
                    await db.record_uptime_check("treblo_api", "DOWN", latency_ms=0.0, error_message=str(up_exc))

            # Clean up old uptime logs older than 14 days (runs every 6 hours)
            if now - last_cleanup_check >= 21600 or last_cleanup_check == 0.0:
                last_cleanup_check = now
                try:
                    await db.cleanup_old_uptime_logs(days=14)
                except Exception:
                    pass

            # Check Treblo API balance every 10 minutes (or on startup)
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

            # Check expiring promo discount reminders (push 2 hours before expiration)
            try:
                await check_expiring_promo_reminders(bot)
            except Exception as e:
                logger.debug("Expiring promo reminders check: %s", e)

            # Check pending payments (YooKassa & CryptoBot)
            pending_payments = await db.get_pending_payments(limit=30)
            for p in pending_payments:
                pid = p["payment_id"]
                provider = p.get("provider") or "yookassa"

                if provider == "cryptobot" and cryptobot_client.is_configured:
                    try:
                        # Extract invoice_id from payment_id (e.g. cb_123456_940290714)
                        parts = pid.split("_")
                        invoice_id = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
                        if invoice_id:
                            inv = await cryptobot_client.get_invoice(invoice_id)
                            if inv:
                                st = inv.get("status")
                                if st == "paid":
                                    logger.info("Background poller discovered successful CryptoBot payment %s", pid)
                                    await process_successful_payment(bot, pid)
                                elif st == "expired":
                                    logger.info("Background poller discovered expired CryptoBot payment %s", pid)
                                    await process_canceled_payment(pid)
                    except Exception as err:
                        logger.debug("CryptoBot background check error for %s: %s", pid, err)

                elif provider == "yookassa" and yookassa_client.is_configured:
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

                # Pacing: avoid sending bursts of requests
                await asyncio.sleep(0.25)
        except Exception as exc:
            logger.error("Unexpected error in background payments poller: %s", exc)

        await asyncio.sleep(settings.background_poller_interval_sec)


async def start_webhook_server(bot: Bot) -> Optional[web.AppRunner]:
    """Starts the unified aiohttp HTTP server (Webhook + Web Dashboard). Kept for backward compatibility."""
    from services.web_server import start_web_server
    return await start_web_server(bot)
