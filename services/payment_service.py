import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.db import db
from services.referral import get_referral_tier, calculate_referral_reward

logger = logging.getLogger(__name__)


async def process_successful_payment(bot: Bot, payment_id: str) -> bool:
    """
    Atomically processes a successful payment:
    1. Updates payment status to 'succeeded' in SQLite (idempotent).
    2. Credits user's paid generation balance.
    3. Calculates referral bonus according to referrer's tiered level (2%-20%) and credits gift balance.
    4. Sends Telegram notifications to user and referrer (even if user closed the app).
    Returns True if processed for the first time, False if already processed.
    """
    record = await db.mark_payment_succeeded(payment_id)
    if not record:
        logger.info("Payment %s has already been processed or not found.", payment_id)
        return False

    user_id = record["user_id"]
    credits_to_add = record["credits"]
    amount = record["amount"]

    # Credit user paid balance
    await db.add_paid_balance(user_id, credits_to_add)
    user_updated = await db.get_user(user_id)
    new_total = user_updated["total_balance"] if user_updated else credits_to_add
    paid_bal = user_updated["paid_balance"] if user_updated else credits_to_add
    gift_bal = user_updated["gift_balance"] if user_updated else 0

    logger.info(
        "User %s credited with +%s paid generations for payment %s. New total: %s",
        user_id,
        credits_to_add,
        payment_id,
        new_total,
    )

    # Referral reward according to tiered level (2% to 20%)
    user = await db.get_user(user_id)
    if user and user.get("referred_by"):
        referrer_id = user["referred_by"]
        referrer_stats = await db.get_user_stats(referrer_id)
        ref_count = referrer_stats["referrals_count"]
        tier_info = get_referral_tier(ref_count)
        percent = tier_info["percent"]

        bonus_fraction = calculate_referral_reward(credits_to_add, percent)
        reward_result = await db.add_referral_reward(referrer_id, bonus_fraction)

        logger.info(
            "Referrer %s (Tier %s, %s%%) earned +%s ref credits. Transferred: %s, remaining ref_bal: %s",
            referrer_id,
            tier_info["level"],
            percent,
            bonus_fraction,
            reward_result["transferred"],
            reward_result["referral_balance"],
        )

        try:
            msg_lines = [
                "🎁 <b>Реферальное вознаграждение!</b>\n",
                f"Ваш приглашённый друг приобрёл <b>{credits_to_add}</b> генераций.",
                f"Ваш уровень: <b>{tier_info['title']} ({percent}%)</b>",
                f"Начислено в реферальную копилку: <b>+{bonus_fraction:g}</b> генераций.",
            ]
            if reward_result["transferred"] > 0:
                msg_lines.append(
                    f"\n🎉 <b>Копилка достигла целого числа!</b>\n"
                    f"<b>+{reward_result['transferred']}</b> целых генераций переведено в <b>🎁 Подарочные</b>!\n"
                    f"Остаток в копилке: <b>{reward_result['referral_balance']:g}</b>."
                )
            else:
                needed = round(1.0 - reward_result["referral_balance"], 2)
                msg_lines.append(
                    f"Всего в копилке: <b>{reward_result['referral_balance']:g} / 1.0</b> "
                    f"<i>(до целой генерации осталось {needed:g})</i>."
                )
            msg_lines.append("\nСпасибо, что приглашаете авторов!")

            await bot.send_message(
                chat_id=referrer_id,
                text="\n".join(msg_lines),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.debug("Failed to notify referrer %s: %s", referrer_id, e)

    # Notify user in Telegram (even if they navigated away or cleared dialog)
    success_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать музыку", callback_data="menu_create"),
            ],
            [
                InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu_profile"),
            ],
        ]
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Оплата {int(amount)} ₽ успешно зачислена!</b>\n\n"
                f"⚡ Вам начислено: <b>+{credits_to_add} платных генераций</b>\n"
                f"💰 <b>Всего генераций:</b> <b>{new_total}</b>\n"
                f"├── 💳 Платные: {paid_bal}\n"
                f"└── 🎁 Подарочные: {gift_bal}\n\n"
                "Приступайте к созданию новых треков прямо сейчас 🎧"
            ),
            reply_markup=success_kb,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Could not send payment notification to user %s: %s", user_id, e)

    return True


async def process_canceled_payment(payment_id: str) -> None:
    """Marks payment as canceled."""
    await db.mark_payment_canceled(payment_id)
    logger.info("Payment %s marked as canceled.", payment_id)
