import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.db import db
from keyboards.inline import (
    TARIFF_PACKAGES,
    get_tariffs_keyboard,
    get_tariff_by_id,
    get_payment_keyboard,
    get_profile_keyboard,
    get_main_menu_keyboard,
    format_per_track_badge,
)
from services.payment_service import process_successful_payment, process_canceled_payment
from services.yookassa import yookassa_client, YooKassaError

logger = logging.getLogger(__name__)
payments_router = Router()


@payments_router.callback_query(F.data == "menu_topup")
@payments_router.message(Command("topup"))
@payments_router.message(Command("pay"))
@payments_router.message(F.text.in_({"💳 Пополнить", "💳 Пополнить баланс"}))
async def show_tariffs(event: Message | CallbackQuery) -> None:
    """Displays available generation packages and pricing."""
    db_tariffs = await db.get_all_tariffs()
    tariffs_to_show = db_tariffs if db_tariffs else TARIFF_PACKAGES

    tariff_lines = []
    for t in tariffs_to_show:
        badge = t.get("badge")
        if not badge or "Тест" in badge:
            badge = format_per_track_badge(t.get("price", 0), t.get("credits", 1))
        tariff_lines.append(
            f"{t['emoji']} <b>{t['title']}</b> — <b>{int(t['price'])} ₽</b> <i>({badge})</i>"
        )
    tariffs_summary = "\n".join(tariff_lines)

    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        "Выберите подходящий пакет генераций музыки.\n"
        "Оплата производится онлайн через защищенный шлюз <b>ЮKassa</b> "
        "(банковские карты РФ, СБП, SberPay, Mir Pay, ЮMoney):\n\n"
        f"{tariffs_summary}\n\n"
        "<i>Нажмите на нужный пакет ниже, чтобы перейти к оплате:</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_tariffs_keyboard(tariffs_to_show),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_tariffs_keyboard(tariffs_to_show),
            parse_mode="HTML",
        )


@payments_router.callback_query(F.data.startswith("buy_pack:"))
async def handle_buy_package(callback: CallbackQuery) -> None:
    """Initiates payment creation via YooKassa API."""
    pack_id = callback.data.split(":")[1]
    pack = await db.get_tariff(pack_id) or get_tariff_by_id(pack_id)

    if not pack:
        await callback.answer("Выбранный пакет не найден.", show_alert=True)
        return

    user_id = callback.from_user.id

    # Anti-spam protection: prevent flooding YooKassa with unpaid invoices
    pending_count = await db.get_user_pending_count(user_id, max_age_minutes=15)
    if pending_count >= 3:
        await callback.answer(
            "⚠️ У вас уже есть 3 активных неоплаченных счёта.\n"
            "Пожалуйста, оплатите один из ранее созданных или подождите несколько минут.",
            show_alert=True,
        )
        return

    if not yookassa_client.is_configured:
        await callback.answer(
            "⚠️ Платёжный шлюз ЮKassa настраивается. Укажите YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env",
            show_alert=True,
        )
        return

    bot_info = await callback.bot.get_me()
    return_url = f"https://t.me/{bot_info.username}"
    description = f"Music Bot: {pack['title']} ({pack['credits']} генераций) для ID {user_id}"

    try:
        payment = await yookassa_client.create_payment(
            amount_rub=pack["price"],
            description=description,
            return_url=return_url,
            metadata={
                "user_id": user_id,
                "credits": pack["credits"],
                "pack_id": pack["id"],
            },
        )
    except YooKassaError as exc:
        logger.error("Failed to create YooKassa payment: %s", exc)
        await callback.answer(f"Ошибка создания счета: {exc}", show_alert=True)
        return

    payment_id = payment["id"]
    confirmation_url = payment.get("confirmation", {}).get("confirmation_url")

    if not confirmation_url:
        await callback.answer("Ошибка: не удалось получить ссылку на оплату.", show_alert=True)
        return

    # Record payment in database
    await db.create_payment_record(
        payment_id=payment_id,
        user_id=user_id,
        amount=pack["price"],
        credits=pack["credits"],
    )

    text = (
        f"🧾 <b>Счет на оплату готов!</b>\n\n"
        f"📦 <b>Тариф:</b> {pack['title']}\n"
        f"⚡ <b>Количество:</b> +{pack['credits']} генераций\n"
        f"💰 <b>Сумма к оплате:</b> <b>{int(pack['price'])} ₽</b>\n\n"
        "1️⃣ Нажмите кнопку <b>«💳 Оплатить через ЮKassa»</b> ниже и завершите оплату удобным способом.\n"
        "2️⃣ После успешной оплаты вернитесь в бот и нажмите <b>«🔄 Проверить оплату»</b>."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_payment_keyboard(confirmation_url, payment_id),
        parse_mode="HTML",
    )
    await callback.answer()


@payments_router.callback_query(F.data.startswith("pay_check:"))
async def handle_check_payment(callback: CallbackQuery) -> None:
    """Checks the payment status in YooKassa and credits balance if successful."""
    payment_id = callback.data.split(":")[1]

    if not yookassa_client.is_configured:
        await callback.answer("ЮKassa не настроена в .env", show_alert=True)
        return

    try:
        payment = await yookassa_client.get_payment(payment_id)
    except YooKassaError as exc:
        logger.error("Error checking YooKassa payment: %s", exc)
        await callback.answer(f"Ошибка проверки статуса: {exc}", show_alert=True)
        return

    status = payment.get("status")

    if status == "succeeded":
        was_new = await process_successful_payment(callback.bot, payment_id)
        user_id = callback.from_user.id
        user = await db.get_user(user_id)
        current_balance = user["balance"] if user else 0

        success_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎵 Создать музыку", callback_data="menu_create"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="👤 Мой профиль", callback_data="menu_profile"
                    ),
                ],
            ]
        )

        paid_bal = user["paid_balance"] if user else 0
        gift_bal = user["gift_balance"] if user else 0
        total_bal = user["total_balance"] if user else current_balance

        if was_new:
            await callback.message.edit_text(
                f"🎉 <b>Оплата успешно завершена!</b>\n\n"
                f"💰 <b>Всего генераций:</b> <b>{total_bal}</b>\n"
                f"├── 💳 Платные: <b>{paid_bal}</b>\n"
                f"└── 🎁 Подарочные: <b>{gift_bal}</b>\n\n"
                "Спасибо за покупку! Приступайте к созданию новых треков прямо сейчас 🎧",
                reply_markup=success_kb,
                parse_mode="HTML",
            )
            await callback.answer("Баланс успешно пополнен!", show_alert=True)
        else:
            await callback.message.edit_text(
                f"✅ <b>Платёж уже был зачислен ранее.</b>\n\n"
                f"💰 <b>Всего генераций:</b> <b>{total_bal}</b>\n"
                f"├── 💳 Платные: <b>{paid_bal}</b>\n"
                f"└── 🎁 Подарочные: <b>{gift_bal}</b>",
                reply_markup=success_kb,
                parse_mode="HTML",
            )
            await callback.answer("Платёж уже обработан", show_alert=True)

    elif status in ("pending", "waiting_for_capture"):
        await callback.answer(
            "⏳ Платёж ещё обрабатывается банком. Если вы уже оплатили, подождите полминуты и нажмите ещё раз.",
            show_alert=True,
        )

    elif status == "canceled":
        await process_canceled_payment(payment_id)
        await callback.message.edit_text(
            "❌ <b>Платёж был отменён или истёк срок действия счета.</b>\n\n"
            "Вы можете выбрать подходящий тариф заново:",
            reply_markup=get_tariffs_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer("Платёж отменён", show_alert=True)

    else:
        await callback.answer(f"Текущий статус платежа: {status}", show_alert=True)
