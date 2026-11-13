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
    """Displays available generation packages and pricing with active promo discounts applied."""
    user_id = event.from_user.id
    db_tariffs = await db.get_all_tariffs()
    tariffs_raw = db_tariffs if db_tariffs else TARIFF_PACKAGES

    active_discount = await db.get_user_active_discount(user_id)

    tariffs_to_show = []
    discount_banner = ""

    if active_discount:
        ddata = active_discount.get("discount_data") or {}
        dmode = ddata.get("discount_mode") or ddata.get("type", "fixed")
        rem_str = active_discount.get("remaining_time_str", "24 ч.")
        max_disc = 0

        for t in tariffs_raw:
            t_copy = dict(t)
            if dmode == "fixed":
                pct = int(ddata.get("percent", 0))
            else:
                packs_map = ddata.get("packs", {})
                pct = int(packs_map.get(t["id"], 0))

            if pct > 0:
                orig_price = float(t["price"])
                disc_price = max(1, round(orig_price * (1 - pct / 100)))
                t_copy["original_price"] = orig_price
                t_copy["price"] = disc_price
                t_copy["discount_percent"] = pct
                t_copy["badge"] = format_per_track_badge(disc_price, t.get("credits", 1))
                if pct > max_disc:
                    max_disc = pct
            else:
                t_copy["discount_percent"] = 0
                t_copy["badge"] = format_per_track_badge(t.get("price", 0), t.get("credits", 1))
            tariffs_to_show.append(t_copy)

        active_code = active_discount.get("code")
        code_tag = f"«{active_code}»" if active_code else ""
        if dmode == "fixed":
            pct_val = ddata.get("percent", max_disc)
            discount_banner = (
                f"🔥 <b>У вас действует промокод {code_tag}: скидка {pct_val}% на всё!</b>\n"
                f"⏳ <i>Осталось времени: {rem_str} (скидка действует на 1 покупку)</i>\n\n"
            )
        else:
            discount_banner = (
                f"🔥 <b>У вас действует промокод {code_tag} со скидкой на тарифы!</b>\n"
                f"⏳ <i>Осталось времени: {rem_str} (скидка действует на 1 покупку)</i>\n\n"
            )
    else:
        tariffs_to_show = [dict(t) for t in tariffs_raw]

    tariff_lines = []
    for t in tariffs_to_show:
        badge = t.get("badge")
        if not badge or "Тест" in badge:
            badge = format_per_track_badge(t.get("price", 0), t.get("credits", 1))

        if t.get("discount_percent") and t["discount_percent"] > 0:
            tariff_lines.append(
                f"{t['emoji']} <b>{t['title']}</b> — <s>{int(t['original_price'])} ₽</s> <b>{int(t['price'])} ₽</b> "
                f"<i>(-{t['discount_percent']}%, {badge})</i>"
            )
        else:
            tariff_lines.append(
                f"{t['emoji']} <b>{t['title']}</b> — <b>{int(t['price'])} ₽</b> <i>({badge})</i>"
            )
    tariffs_summary = "\n".join(tariff_lines)

    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        f"{discount_banner}"
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
    """Initiates payment creation via YooKassa API with discount calculations and pending invoice cancellation."""
    pack_id = callback.data.split(":")[1]
    pack = await db.get_tariff(pack_id) or get_tariff_by_id(pack_id)

    if not pack:
        await callback.answer("Выбранный пакет не найден.", show_alert=True)
        return

    user_id = callback.from_user.id

    # Automatically cancel stale pending payments for user so old invoices don't hang around
    await db.cancel_user_pending_payments(user_id)

    # Check for active discount
    active_discount = await db.get_user_active_discount(user_id)
    final_price = float(pack["price"])
    activation_id = None
    discount_note = ""

    if active_discount:
        ddata = active_discount.get("discount_data") or {}
        dmode = ddata.get("discount_mode") or ddata.get("type", "fixed")
        if dmode == "fixed":
            pct = int(ddata.get("percent", 0))
        else:
            packs_map = ddata.get("packs", {})
            pct = int(packs_map.get(pack["id"], 0))

        if pct > 0:
            final_price = max(1.0, float(round(final_price * (1 - pct / 100))))
            activation_id = active_discount["id"]
            discount_note = f"🏷 <b>Скидка:</b> -{pct}% (<s>{int(pack['price'])} ₽</s>)\n"

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
            amount_rub=final_price,
            description=description,
            return_url=return_url,
            metadata={
                "user_id": user_id,
                "credits": pack["credits"],
                "pack_id": pack["id"],
                "activation_id": activation_id,
            },
        )
    except YooKassaError as exc:
        logger.error("Failed to create YooKassa payment: %s", exc)
        await callback.answer("Не удалось создать счет на оплату. Попробуйте позже.", show_alert=True)
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
        amount=final_price,
        credits=pack["credits"],
        promo_activation_id=activation_id,
    )

    pack_per_track = format_per_track_badge(final_price, pack["credits"])

    text = (
        f"🧾 <b>Счет на оплату готов!</b>\n\n"
        f"📦 <b>Тариф:</b> {pack['title']}\n"
        f"⚡ <b>Количество:</b> +{pack['credits']} генераций\n"
        f"{discount_note}"
        f"💰 <b>Сумма к оплате:</b> <b>{int(final_price)} ₽</b> <i>({pack_per_track})</i>\n\n"
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
        await callback.answer("Не удалось проверить статус оплаты. Попробуйте еще раз через несколько секунд.", show_alert=True)
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
