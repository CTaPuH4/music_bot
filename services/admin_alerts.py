import logging
import time
from typing import Any, Dict, Optional
from aiogram import Bot

from config import settings
from services.treblo import treblo_client

logger = logging.getLogger(__name__)

# State to avoid alert spamming
_last_alert_time: float = 0.0
_last_alert_state: Optional[str] = None  # None, "low", or "empty"


async def notify_admins(bot: Bot, text: str) -> int:
    """
    Sends an HTML message to all admin Telegram IDs configured in .env.
    Returns count of successfully delivered messages.
    """
    admin_ids = settings.admin_ids_list
    if not admin_ids:
        logger.debug("No admin IDs configured in ADMIN_IDS.")
        return 0

    sent_count = 0
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
            )
            sent_count += 1
        except Exception as e:
            logger.warning("Failed to send admin notification to %s: %s", admin_id, e)

    return sent_count


def extract_treblo_credits(balance_info: Dict[str, Any]) -> Optional[int]:
    """
    Extracts integer total credit count from Treblo API response.
    Treblo /credits/balance returns {'num_credits': int, 'num_credits_payg': int}.
    Also supports fallback keys: credits, balance, credits_remaining, amount.
    """
    if not isinstance(balance_info, dict):
        return None

    # Check for Treblo's standard num_credits and num_credits_payg
    if "num_credits" in balance_info or "num_credits_payg" in balance_info:
        try:
            c1 = int(balance_info.get("num_credits") or 0)
            c2 = int(balance_info.get("num_credits_payg") or 0)
            return c1 + c2
        except (ValueError, TypeError):
            pass

    for key in ("credits", "balance", "credits_remaining", "amount", "total_credits"):
        if key in balance_info and balance_info[key] is not None:
            try:
                return int(balance_info[key])
            except (ValueError, TypeError):
                continue
    return None


async def check_treblo_credits_and_alert(bot: Bot, force: bool = False) -> Dict[str, Any]:
    """
    Checks the Treblo API account credit balance.
    If credits are low or exhausted, sends an urgent notification to all admins.
    """
    global _last_alert_time, _last_alert_state

    balance_info = await treblo_client.get_account_balance()
    if "error" in balance_info:
        logger.warning("Could not fetch Treblo credits balance: %s", balance_info)
        return balance_info

    credits_int = extract_treblo_credits(balance_info)
    if credits_int is None:
        logger.debug("Treblo balance response format: %s", balance_info)
        return balance_info

    # Normalize 'credits' key so callers can reliably read it
    balance_info["credits"] = credits_int

    now = time.time()
    min_alert_interval = 3600  # 1 hour between repetitive warnings

    if credits_int <= 0:
        current_state = "empty"
        if force or _last_alert_state != "empty" or (now - _last_alert_time > min_alert_interval):
            _last_alert_state = "empty"
            _last_alert_time = now
            text = (
                "🚨 <b>КРИТИЧЕСКИЙ АЛЕРТ: Баланс API генераций закончился!</b>\n\n"
                f"Текущий остаток: <b>{credits_int}</b> кредитов.\n"
                "Генерация треков для пользователей заблокирована до пополнения баланса.\n\n"
                "🔗 Пополните баланс в личном кабинете провайдера API."
            )
            await notify_admins(bot, text)

    elif credits_int < settings.treblo_low_credits_threshold:
        current_state = "low"
        approx_tracks = max(0, credits_int // 100)
        if force or _last_alert_state != "low" or (now - _last_alert_time > min_alert_interval):
            _last_alert_state = "low"
            _last_alert_time = now
            text = (
                "⚠️ <b>ВНИМАНИЕ: Заканчиваются кредиты API генераций!</b>\n\n"
                f"Осталось: <b>{credits_int}</b> кредитов <i>(~{approx_tracks} треков)</i>.\n"
                "Рекомендуется заблаговременно пополнить баланс, чтобы сервис не остановился.\n\n"
                "🔗 Пополните баланс в личном кабинете провайдера API."
            )
            await notify_admins(bot, text)
    else:
        _last_alert_state = "ok"

    return balance_info
