import logging
import secrets
import time
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    PreCheckoutQuery,
    LabeledPrice,
)

from config import settings
from database.db import db
from keyboards.inline import (
    TARIFF_PACKAGES,
    get_tariffs_keyboard,
    get_tariff_by_id,
    get_payment_keyboard,
    get_payment_methods_keyboard,
    get_crypto_payment_keyboard,
    get_profile_keyboard,
    get_main_menu_keyboard,
    format_per_track_badge,
)
from services.payment_service import process_successful_payment, process_canceled_payment
from services.yookassa import yookassa_client, YooKassaError
from services.cryptobot import cryptobot_client, CryptoBotError

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
        "Выберите подходящий пакет генераций музыки:\n\n"
        f"{tariffs_summary}\n\n"
        "🌐 <b>Доступные способы оплаты:</b>\n"
        "• 🇷🇺 <b>Карты РФ / СБП</b> (ЮKassa, SberPay, Mir Pay, T-Pay)\n"
        "• ⭐ <b>Telegram Stars</b> (быстрая оплата звёздами прямо в Telegram)\n"
        "• 💎 <b>Криптовалюта</b> (CryptoBot: USDT, TON, BTC и др.)\n\n"
        "<i>Нажмите на нужный пакет ниже, чтобы выбрать удобный способ оплаты:</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_tariffs_keyboard(tariffs_to_show),
            parse_mode="HTML",
        )
        try:
            await event.answer()
        except Exception:
            pass
    else:
        await event.answer(
            text,
            reply_markup=get_tariffs_keyboard(tariffs_to_show),
            parse_mode="HTML",
        )


async def _calculate_discounted_tariff(user_id: int, pack: Dict[str, Any]) -> tuple[float, Optional[int], str]:
    """Helper calculating final price in RUB with promo discounts applied."""
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

    return final_price, activation_id, discount_note


# ---------------------------------------------------------
# STEP 1: PAYMENT METHOD SELECTION SCREEN
# ---------------------------------------------------------
@payments_router.callback_query(F.data.startswith("buy_pack:"))
async def handle_buy_package(callback: CallbackQuery) -> None:
    """Shows payment method selection: Russian Bank Cards / SBP, Telegram Stars, CryptoBot."""
    pack_id = callback.data.split(":")[1]
    pack = await db.get_tariff(pack_id) or get_tariff_by_id(pack_id)

    if not pack:
        await callback.answer("Выбранный пакет не найден.", show_alert=True)
        return

    user_id = callback.from_user.id
    final_price, activation_id, discount_note = await _calculate_discounted_tariff(user_id, pack)

    # Converted prices:
    # Telegram Stars: rate 2 (1 Star = 2 RUB)
    stars_price = max(1, round(final_price / settings.telegram_stars_rub_rate))
    # Crypto: rate 85 (1 USDT = 85 RUB)
    crypto_price = max(0.1, round(final_price / settings.cryptobot_rub_rate, 2))

    pack_per_track = format_per_track_badge(final_price, pack["credits"])

    text = (
        f"💳 <b>Оплата тарифа «{pack['title']}»</b>\n\n"
        f"⚡ <b>Количество:</b> +{pack['credits']} генераций <i>({pack_per_track})</i>\n"
        f"{discount_note}"
        f"💰 <b>Стоимость к оплате:</b>\n"
        f"• 🇷🇺 Банковская карта РФ / СБП: <b>{int(final_price)} ₽</b>\n"
        f"• ⭐ Telegram Stars: <b>{stars_price} ⭐</b>\n"
        f"• 💎 Криптовалюта (USDT, TON, BTC): <b>~{crypto_price} USDT</b>\n\n"
        f"<i>Выберите удобный способ оплаты ниже:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_payment_methods_keyboard(
            pack_id=pack["id"],
            rub_price=final_price,
            stars_price=stars_price,
            crypto_price=crypto_price,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------
# METHOD 1: YOOKASSA (RUB, Bank Cards, SBP)
# ---------------------------------------------------------
@payments_router.callback_query(F.data.startswith("pay_method:yookassa:"))
async def handle_pay_method_yookassa(callback: CallbackQuery) -> None:
    """Initiates payment via YooKassa API."""
    pack_id = callback.data.split(":")[2]
    pack = await db.get_tariff(pack_id) or get_tariff_by_id(pack_id)

    if not pack:
        await callback.answer("Пакет не найден.", show_alert=True)
        return

    user_id = callback.from_user.id
    await db.cancel_user_pending_payments(user_id)
    final_price, activation_id, discount_note = await _calculate_discounted_tariff(user_id, pack)

    if not yookassa_client.is_configured:
        await callback.answer(
            "⚠️ Платёжный шлюз ЮKassa настраивается. Выберите Telegram Stars или Криптовалюту.",
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

    await db.create_payment_record(
        payment_id=payment_id,
        user_id=user_id,
        amount=final_price,
        credits=pack["credits"],
        promo_activation_id=activation_id,
        provider="yookassa",
        currency="RUB",
    )

    pack_per_track = format_per_track_badge(final_price, pack["credits"])

    text = (
        f"🧾 <b>Счет на оплату ЮKassa готов!</b>\n\n"
        f"📦 <b>Тариф:</b> {pack['title']}\n"
        f"⚡ <b>Количество:</b> +{pack['credits']} генераций\n"
        f"{discount_note}"
        f"💰 <b>Сумма к оплате:</b> <b>{int(final_price)} ₽</b> <i>({pack_per_track})</i>\n\n"
        "1️⃣ Нажмите <b>«💳 Оплатить через ЮKassa»</b> и завершите оплату картой РФ или через СБП.\n"
        "2️⃣ После оплаты вернитесь в бот и нажмите <b>«🔄 Проверить оплату»</b>."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_payment_keyboard(confirmation_url, payment_id),
        parse_mode="HTML",
    )
    await db.update_payment_telegram_message_id(payment_id, callback.message.message_id)
    await callback.answer()


# ---------------------------------------------------------
# METHOD 2: TELEGRAM STARS (⭐ Native Telegram Payments)
# ---------------------------------------------------------
@payments_router.callback_query(F.data.startswith("pay_method:stars:"))
async def handle_pay_method_stars(callback: CallbackQuery) -> None:
    """Sends native Telegram Stars invoice."""
    pack_id = callback.data.split(":")[2]
    pack = await db.get_tariff(pack_id) or get_tariff_by_id(pack_id)

    if not pack:
        await callback.answer("Пакет не найден.", show_alert=True)
        return

    user_id = callback.from_user.id
    await db.cancel_user_pending_payments(user_id)
    final_price, activation_id, discount_note = await _calculate_discounted_tariff(user_id, pack)

    # Calculate Stars amount (rate 2)
    stars_price = max(1, round(final_price / settings.telegram_stars_rub_rate))
    payment_id = f"stars_{user_id}_{int(time.time())}_{secrets.token_hex(4)}"

    # Record pending payment in DB
    await db.create_payment_record(
        payment_id=payment_id,
        user_id=user_id,
        amount=final_price,
        credits=pack["credits"],
        promo_activation_id=activation_id,
        provider="telegram_stars",
        currency="XTR",
    )

    prices = [
        LabeledPrice(
            label=f"{pack['title']} (+{pack['credits']} треков)",
            amount=stars_price,
        )
    ]

    try:
        # Delete previous method selection message to keep chat clean
        try:
            await callback.message.delete()
        except Exception:
            pass

        invoice_msg = await callback.bot.send_invoice(
            chat_id=user_id,
            title=f"Тариф «{pack['title']}»",
            description=f"Пополнение баланса на {pack['credits']} генераций музыки в Trivela Music",
            payload=payment_id,
            currency="XTR",
            prices=prices,
            provider_token="",  # Must be empty for Telegram Stars
        )
        # Store message_id for safe deletion upon completion
        await db.update_payment_telegram_message_id(payment_id, invoice_msg.message_id)
        await callback.answer("Счет на оплату звёздами готов!")
    except Exception as exc:
        logger.error("Failed to send Telegram Stars invoice: %s", exc)
        await callback.answer(f"Не удалось выставить счет звёздами: {exc}", show_alert=True)


@payments_router.pre_checkout_query()
async def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> None:
    """
    Answers Telegram PreCheckoutQuery for Stars payments.
    STRICTLY verifies payment status: if already paid or canceled, rejects with ok=False!
    This completely prevents double charging!
    """
    payment_id = pre_checkout_query.invoice_payload
    payment = await db.get_payment_record(payment_id)

    if not payment:
        await pre_checkout_query.answer(
            ok=False,
            error_message="Счет устарел или не найден. Пожалуйста, откройте /topup и выберите тариф заново.",
        )
        return

    if payment.get("status") == "succeeded":
        await pre_checkout_query.answer(
            ok=False,
            error_message="Этот счет уже был оплачен ранее! Звёзды не списаны. Чтобы докупить генерации, выберите тариф в /topup.",
        )
        return

    if payment.get("status") == "canceled":
        await pre_checkout_query.answer(
            ok=False,
            error_message="Счет был отменен. Пожалуйста, выберите тариф заново в /topup.",
        )
        return

    await pre_checkout_query.answer(ok=True)


@payments_router.message(F.successful_payment)
async def handle_successful_stars_payment(message: Message) -> None:
    """Processes completed Telegram Stars payment and cleans up invoice message."""
    sp = message.successful_payment
    payment_id = sp.invoice_payload
    logger.info("Received successful Telegram Stars payment: %s, total_amount: %s XTR", payment_id, sp.total_amount)

    # 1. Fetch payment record to find invoice message_id and safely delete it
    payment = await db.get_payment_record(payment_id)
    if payment and payment.get("telegram_message_id"):
        try:
            await message.bot.delete_message(chat_id=message.chat.id, message_id=payment["telegram_message_id"])
        except Exception as e:
            logger.debug("Could not delete invoice message: %s", e)

    # 2. Also delete the Telegram service receipt message to keep chat clean
    try:
        await message.delete()
    except Exception:
        pass

    was_new = await process_successful_payment(message.bot, payment_id)

    if not was_new:
        user_id = message.from_user.id
        user = await db.get_user(user_id)
        current_balance = user["balance"] if user else 0
        total_bal = user["total_balance"] if user else current_balance

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
        await message.answer(
            f"✅ <b>Платёж уже был зачислен ранее.</b>\n\n"
            f"💰 <b>Всего генераций:</b> <b>{total_bal}</b>",
            reply_markup=success_kb,
            parse_mode="HTML",
        )


# ---------------------------------------------------------
# METHOD 3: CRYPTOBOT (@CryptoBot / Crypto Pay API)
# ---------------------------------------------------------
@payments_router.callback_query(F.data.startswith("pay_method:crypto:"))
async def handle_pay_method_crypto(callback: CallbackQuery) -> None:
    """Creates a CryptoBot invoice in USDT/crypto."""
    pack_id = callback.data.split(":")[2]
    pack = await db.get_tariff(pack_id) or get_tariff_by_id(pack_id)

    if not pack:
        await callback.answer("Пакет не найден.", show_alert=True)
        return

    if not cryptobot_client.is_configured:
        await callback.answer(
            "⚠️ Оплата криптовалютой временно настраивается. Пожалуйста, выберите оплату картой или Telegram Stars.",
            show_alert=True,
        )
        return

    user_id = callback.from_user.id
    await db.cancel_user_pending_payments(user_id)
    final_price, activation_id, discount_note = await _calculate_discounted_tariff(user_id, pack)

    crypto_amount = max(0.1, round(final_price / settings.cryptobot_rub_rate, 2))
    description = f"Trivela Music: {pack['title']} ({pack['credits']} треков) для ID {user_id}"

    try:
        invoice = await cryptobot_client.create_invoice(
            amount=crypto_amount,
            asset="USDT",
            description=description,
            payload=f"crypto_{user_id}_{int(time.time())}",
            expires_in=3600,
        )
    except CryptoBotError as exc:
        logger.error("Failed to create CryptoBot invoice: %s", exc)
        await callback.answer(f"Ошибка создания счета в CryptoBot: {exc}", show_alert=True)
        return

    invoice_id = invoice["invoice_id"]
    payment_id = f"cb_{invoice_id}_{user_id}"
    pay_url = invoice.get("bot_invoice_url") or invoice.get("pay_url")

    if not pay_url:
        await callback.answer("Ошибка: CryptoBot не вернул ссылку на оплату.", show_alert=True)
        return

    # Record payment in database
    await db.create_payment_record(
        payment_id=payment_id,
        user_id=user_id,
        amount=final_price,
        credits=pack["credits"],
        promo_activation_id=activation_id,
        provider="cryptobot",
        currency="USDT",
    )

    pack_per_track = format_per_track_badge(final_price, pack["credits"])

    text = (
        f"🧾 <b>Счет на оплату в CryptoBot готов!</b>\n\n"
        f"📦 <b>Тариф:</b> {pack['title']}\n"
        f"⚡ <b>Количество:</b> +{pack['credits']} генераций\n"
        f"{discount_note}"
        f"💰 <b>Сумма к оплате:</b> <b>{crypto_amount} USDT</b> <i>(~{int(final_price)} ₽ по курсу {settings.cryptobot_rub_rate:g} ₽ за 1 USDT)</i>\n\n"
        "1️⃣ Нажмите <b>«💎 Оплатить в @CryptoBot»</b> и завершите перевод.\n"
        "<i>(Вы можете оплатить как с баланса @CryptoBot, так и переводом TON, USDT, BTC с любого кошелька)</i>.\n\n"
        "2️⃣ После оплаты нажмите <b>«🔄 Проверить оплату»</b>."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_crypto_payment_keyboard(pay_url, payment_id, invoice_id),
        parse_mode="HTML",
    )
    await db.update_payment_telegram_message_id(payment_id, callback.message.message_id)
    await callback.answer()


@payments_router.callback_query(F.data.startswith("check_crypto:"))
async def handle_check_crypto_payment(callback: CallbackQuery) -> None:
    """Manually checks status of CryptoBot invoice."""
    parts = callback.data.split(":")
    payment_id = parts[1]
    invoice_id = parts[2]

    if not cryptobot_client.is_configured:
        await callback.answer("CryptoBot не настроен", show_alert=True)
        return

    invoice = await cryptobot_client.get_invoice(invoice_id)
    if not invoice:
        await callback.answer("Не удалось проверить статус счета в CryptoBot. Попробуйте через пару секунд.", show_alert=True)
        return

    status = invoice.get("status")

    if status == "paid":
        was_new = await process_successful_payment(callback.bot, payment_id)
        try:
            await callback.message.delete()
        except Exception:
            pass

        if was_new:
            await callback.answer("Оплата подтверждена!", show_alert=True)
        else:
            await callback.answer("✅ Платёж уже был зачислен ранее.", show_alert=True)

    elif status in ("active", "created"):
        await callback.answer(
            "⏳ Платёж ещё ожидает перевода в @CryptoBot. Если вы уже отправили криптовалюту, подождите подтверждения сети (обычно 15–30 секунд) и нажмите снова.",
            show_alert=True,
        )

    elif status == "expired":
        await process_canceled_payment(payment_id)
        await callback.message.edit_text(
            "❌ <b>Срок действия счета в CryptoBot истёк.</b>\n\n"
            "Вы можете выбрать тариф заново:",
            reply_markup=get_tariffs_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer("Счет истёк", show_alert=True)
    else:
        await callback.answer(f"Статус счета: {status}", show_alert=True)


@payments_router.callback_query(F.data.startswith("cancel_crypto:"))
async def handle_cancel_crypto_payment(callback: CallbackQuery) -> None:
    """Cancels a pending crypto payment."""
    parts = callback.data.split(":")
    payment_id = parts[1]
    await process_canceled_payment(payment_id)
    await callback.message.edit_text(
        "❌ <b>Счет на оплату отменён.</b>\n\n"
        "Вы можете выбрать подходящий тариф заново:",
        reply_markup=get_tariffs_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer("Счет отменён")


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
        try:
            await callback.message.delete()
        except Exception:
            pass

        if was_new:
            await callback.answer("Оплата успешно зачислена!", show_alert=True)
        else:
            await callback.answer("✅ Платёж уже был зачислен ранее.", show_alert=True)

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
