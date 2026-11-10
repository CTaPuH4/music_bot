import asyncio
import logging
from typing import Optional

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from config import settings
from database.db import db
from keyboards.admin import (
    get_admin_main_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_admin_tariffs_keyboard,
    get_admin_cancel_keyboard,
)
from services.admin_alerts import check_treblo_credits_and_alert
from services.treblo import treblo_client
from states.admin import AdminStates

logger = logging.getLogger(__name__)
admin_router = Router()


def is_admin(user_id: int) -> bool:
    """Checks if user Telegram ID is listed in ADMIN_IDS."""
    return user_id in settings.admin_ids_list


# ---------------------------------------------------------
# ADMIN MAIN MENU
# ---------------------------------------------------------
@admin_router.message(Command("admin"))
@admin_router.callback_query(F.data == "admin_menu")
async def show_admin_panel(event: Message | CallbackQuery, state: FSMContext) -> None:
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, Message):
            await event.answer("⛔ У вас нет доступа к панели администратора.")
        else:
            await event.answer("⛔ Доступ запрещён", show_alert=True)
        return

    await state.clear()
    stats = await db.get_system_stats()

    text = (
        "👑 <b>Панель администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['users_count']}</b>\n"
        f"🎵 Генераций всего: <b>{stats['total_generations']}</b> <i>(успешных: {stats['success_generations']})</i>\n"
        f"💳 Оплаченных счетов: <b>{stats['payments_count']}</b>\n"
        f"💰 Выручка с платежей: <b>{stats['revenue_rub']:.0f} ₽</b>\n\n"
        "Выберите раздел для управления:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_admin_main_keyboard(),
            parse_mode="HTML",
        )


@admin_router.callback_query(F.data == "admin_close")
async def close_admin_panel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.message.delete()
    await callback.answer("Админ-панель закрыта")


# ---------------------------------------------------------
# FEATURE 0: CHECK TREBLO BALANCE
# ---------------------------------------------------------
@admin_router.callback_query(F.data == "admin_treblo_balance")
async def show_treblo_balance(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    await callback.answer("Запрашиваю баланс Treblo API...")
    res = await check_treblo_credits_and_alert(callback.bot, force=True)

    credits = (
        res.get("credits")
        or res.get("balance")
        or res.get("credits_remaining")
        or res.get("amount")
    )

    if credits is not None:
        try:
            credits_int = int(credits)
            approx_tracks = max(0, credits_int // 100)
            status_emoji = "🟢" if credits_int >= 500 else ("🟡" if credits_int > 0 else "🔴")
            text = (
                f"{status_emoji} <b>Баланс Treblo API:</b>\n\n"
                f"Остаток: <b>{credits_int}</b> кредитов\n"
                f"Хватит примерно на: <b>~{approx_tracks} треков</b>\n\n"
                f"<i>(Порог предупреждения в боте: {settings.treblo_low_credits_threshold} кредитов)</i>"
            )
        except Exception:
            text = f"📊 <b>Баланс Treblo API:</b> {credits}"
    else:
        err = res.get("error") or "Не удалось распарсить баланс"
        text = f"⚠️ <b>Ответ Treblo API:</b> {err}"

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# FEATURE 1: BROADCAST / РАССЫЛКА
# ---------------------------------------------------------
@admin_router.callback_query(F.data == "admin_broadcast")
async def start_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_broadcast_text)
    text = (
        "📢 <b>Создание рассылки пользователям</b>\n\n"
        "Отправьте текст сообщения для рассылки всем пользователям бота.\n"
        "<i>Поддерживается стандартное HTML форматирование (жирный, курсив, ссылки).</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_broadcast_text)
async def process_broadcast_text(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    text = message.html_text or message.text
    if not text or len(text.strip()) < 2:
        await message.answer("Текст сообщения слишком короткий. Попробуйте еще раз.")
        return

    await state.update_data(broadcast_text=text)
    user_ids = await db.get_all_user_ids()
    await state.update_data(recipients_count=len(user_ids))
    await state.set_state(AdminStates.confirm_broadcast)

    preview_text = (
        "📢 <b>Предпросмотр сообщения для рассылки:</b>\n"
        "────────────────────\n"
        f"{text}\n"
        "────────────────────\n"
        f"👥 <b>Всего получателей:</b> {len(user_ids)} пользователей.\n\n"
        "Нажмите кнопку ниже для подтверждения и запуска рассылки:"
    )

    await message.answer(
        preview_text,
        reply_markup=get_admin_broadcast_confirm_keyboard(),
        parse_mode="HTML",
    )


@admin_router.callback_query(AdminStates.confirm_broadcast, F.data == "admin_broadcast_send")
async def execute_broadcast(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    text = data.get("broadcast_text")
    await state.clear()

    if not text:
        await callback.message.edit_text("Текст рассылки утерян. Попробуйте снова.")
        return

    user_ids = await db.get_all_user_ids()
    total = len(user_ids)

    status_msg = await callback.message.edit_text(
        f"🚀 <b>Запуск рассылки...</b>\n\nОтправлено 0 из {total}...",
        parse_mode="HTML",
    )

    success = 0
    failed = 0

    for idx, uid in enumerate(user_ids, 1):
        try:
            await callback.bot.send_message(
                chat_id=uid,
                text=text,
                parse_mode="HTML",
            )
            success += 1
        except Exception:
            failed += 1

        # Periodic status updates & rate limiting (Telegram ~30 msgs/sec max)
        await asyncio.sleep(0.04)
        if idx % 25 == 0 or idx == total:
            try:
                await status_msg.edit_text(
                    f"🚀 <b>Рассылка в процессе:</b> {idx}/{total}\n\n"
                    f"✅ Успешно: {success}\n"
                    f"❌ Не доставлено: {failed}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    report = (
        "🎉 <b>Рассылка успешно завершена!</b>\n\n"
        f"👥 Всего адресатов: <b>{total}</b>\n"
        f"✅ Доставлено: <b>{success}</b>\n"
        f"❌ Ошибок (заблокировали бота): <b>{failed}</b>"
    )

    await status_msg.edit_text(
        report,
        reply_markup=get_admin_cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# FEATURE 2: GIVE CREDITS TO USER (GIFT BALANCE)
# ---------------------------------------------------------
@admin_router.callback_query(F.data == "admin_give_credits")
async def start_give_credits(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_user_id)
    text = (
        "🎁 <b>Начисление подарочных генераций</b>\n\n"
        "Отправьте Telegram ID пользователя, которому необходимо начислить баланс:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_user_id)
async def process_give_credits_user_id(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    raw_id = message.text.strip()
    if not raw_id.isdigit():
        await message.answer("⚠️ ID пользователя должен состоять только из цифр. Попробуйте еще раз:")
        return

    target_id = int(raw_id)
    target_user = await db.get_user(target_id)
    if not target_user:
        await message.answer(
            f"⚠️ Пользователь с ID <code>{target_id}</code> не найден в базе данных.\n"
            "Убедитесь, что он хотя бы раз запускал бота, и введите ID повторно:",
            parse_mode="HTML",
        )
        return

    await state.update_data(target_user_id=target_id)
    await state.set_state(AdminStates.waiting_for_credits_amount)

    name = target_user.get("first_name") or "Пользователь"
    total_bal = target_user.get("total_balance", 0)
    paid = target_user.get("paid_balance", 0)
    gift = target_user.get("gift_balance", 0)

    text = (
        f"👤 <b>Пользователь найден:</b> {name} (ID: <code>{target_id}</code>)\n"
        f"💰 Текущий баланс: <b>{total_bal}</b> (Платные: {paid}, Подарочные: {gift})\n\n"
        "Введите <b>количество генераций</b> для начисления (целое положительное число):"
    )
    await message.answer(text, parse_mode="HTML")


@admin_router.message(AdminStates.waiting_for_credits_amount)
async def process_give_credits_amount(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    raw_amount = message.text.strip()
    if not raw_amount.isdigit() or int(raw_amount) <= 0:
        await message.answer("⚠️ Введите корректное положительное число генераций:")
        return

    amount = int(raw_amount)
    data = await state.get_data()
    target_id = data.get("target_user_id")
    await state.clear()

    if not target_id:
        await message.answer("Ошибка сессии. Начните заново с /admin.")
        return

    # Add to gift_balance
    new_total = await db.add_gift_balance(target_id, amount)
    updated_user = await db.get_user(target_id)

    # Notify target user
    try:
        await message.bot.send_message(
            chat_id=target_id,
            text=(
                f"🎁 <b>Вам начислен подарок!</b>\n\n"
                f"Администратор начислил вам <b>+{amount} подарочных генераций</b> 🎉\n"
                f"💰 Ваш актуальный баланс: <b>{new_total}</b> генераций\n\n"
                "Приятного творчества! Нажмите /create для создания музыки 🎵"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning("Could not send credit notification to user %s: %s", target_id, e)

    # Confirm to admin
    report = (
        f"✅ <b>Генерации успешно начислены!</b>\n\n"
        f"👤 Пользователь: <code>{target_id}</code>\n"
        f"🎁 Начислено: <b>+{amount} подарочных</b>\n"
        f"💰 Новый баланс пользователя: <b>{new_total}</b> "
        f"<i>(Платные: {updated_user['paid_balance']}, Подарочные: {updated_user['gift_balance']})</i>"
    )
    await message.answer(
        report,
        reply_markup=get_admin_cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# FEATURE 3: TARIFF PRICES CONFIGURATION
# ---------------------------------------------------------
@admin_router.callback_query(F.data == "admin_prices")
async def show_admin_tariffs(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    tariffs = await db.get_all_tariffs()

    text = (
        "💳 <b>Настройка цен пакетов генераций</b>\n\n"
        "Выберите пакет, для которого хотите изменить цену в рублях:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_tariffs_keyboard(tariffs),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_price_edit:"))
async def start_edit_price(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    tariff_id = callback.data.split(":")[1]
    tariff = await db.get_tariff(tariff_id)

    if not tariff:
        await callback.answer("Пакет не найден в базе данных.", show_alert=True)
        return

    await state.update_data(edit_tariff_id=tariff_id, edit_tariff_title=tariff["title"])
    await state.set_state(AdminStates.waiting_for_tariff_price)

    text = (
        f"✏️ <b>Редактирование цены тарифа</b>\n\n"
        f"Пакет: <b>{tariff['emoji']} {tariff['title']}</b> ({tariff['credits']} генераций)\n"
        f"Текущая цена: <b>{int(tariff['price'])} ₽</b>\n\n"
        "Введите новую цену в рублях (целое число от 1 до 50000):"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_prices"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_tariff_price)
async def process_new_price(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    raw_price = message.text.strip().replace(",", ".")
    try:
        new_price = float(raw_price)
        if new_price < 1 or new_price > 50000:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Введите корректную цену в рублях (число от 1 до 50 000):")
        return

    data = await state.get_data()
    tariff_id = data.get("edit_tariff_id")
    title = data.get("edit_tariff_title", "Пакет")
    await state.clear()

    if not tariff_id:
        await message.answer("Ошибка сессии. Перейдите в /admin.")
        return

    await db.update_tariff_price(tariff_id, new_price)

    await message.answer(
        f"✅ <b>Цена успешно обновлена!</b>\n\n"
        f"Тариф: <b>{title}</b>\n"
        f"Новая цена: <b>{int(new_price)} ₽</b>\n\n"
        "Новая стоимость мгновенно отображается у всех пользователей при пополнении баланса.",
        reply_markup=get_admin_cancel_keyboard("admin_prices"),
        parse_mode="HTML",
    )
