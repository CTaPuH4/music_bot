import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import settings
from database.db import db, get_msk_now, MSK_TZ
from keyboards.inline import TARIFF_PACKAGES, get_tariff_by_id, format_per_track_badge
from keyboards.admin import (
    get_admin_main_keyboard,
    get_admin_sub_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_admin_tariffs_keyboard,
    get_admin_cancel_keyboard,
    get_admin_artists_list_keyboard,
    get_admin_artist_card_keyboard,
    get_admin_artist_delete_confirm_keyboard,
    get_admin_artist_popularity_choice_keyboard,
    get_admin_promos_menu_keyboard,
    get_admin_promo_type_keyboard,
    get_admin_promo_discount_mode_keyboard,
    get_admin_promo_duration_keyboard,
    get_admin_promo_confirm_keyboard,
    get_admin_promos_list_keyboard,
    get_admin_promo_card_keyboard,
)
from services.admin_alerts import check_treblo_credits_and_alert, extract_treblo_credits
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
    sub_enabled = await db.is_subscription_check_enabled()

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
            reply_markup=get_admin_main_keyboard(sub_enabled=sub_enabled),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_admin_main_keyboard(sub_enabled=sub_enabled),
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

    await callback.answer("Запрашиваю баланс API генераций...")
    res = await check_treblo_credits_and_alert(callback.bot, force=True)

    credits_int = extract_treblo_credits(res) if isinstance(res, dict) else None

    if credits_int is not None:
        approx_tracks = max(0, credits_int // 100)
        status_emoji = "🟢" if credits_int >= 500 else ("🟡" if credits_int > 0 else "🔴")

        detail_lines = []
        if isinstance(res, dict) and ("num_credits" in res or "num_credits_payg" in res):
            sub_c = res.get("num_credits", 0)
            payg_c = res.get("num_credits_payg", 0)
            detail_lines.append(f"• Подписка: <b>{sub_c}</b>")
            detail_lines.append(f"• Дополнительные (PAYG): <b>{payg_c}</b>")
            detail_str = "\n" + "\n".join(detail_lines) + "\n"
        else:
            detail_str = ""

        text = (
            f"{status_emoji} <b>Баланс API генераций:</b>\n\n"
            f"Всего: <b>{credits_int}</b> кредитов\n"
            f"{detail_str}\n"
            f"Хватит примерно на: <b>~{approx_tracks} треков</b>\n\n"
            f"<i>(Порог предупреждения в боте: {settings.treblo_low_credits_threshold} кредитов)</i>"
        )
    else:
        err = res.get("error") if isinstance(res, dict) else None
        err_msg = err or "Не удалось распарсить баланс"
        text = f"⚠️ <b>Ответ API генераций:</b> {err_msg}"

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_menu"),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# FEATURE 0.5: MANDATORY CHANNEL SUBSCRIPTION MANAGEMENT
# ---------------------------------------------------------
@admin_router.callback_query(F.data == "admin_sub_menu")
async def show_sub_settings_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()

    sub_enabled = await db.is_subscription_check_enabled()
    channel_info = await db.get_required_channel()
    channel = channel_info.get("channel") or "не задан"
    channel_url = channel_info.get("url") or "не задана"

    status_str = "🟢 <b>ВКЛЮЧЕНА</b>" if sub_enabled else "🔴 <b>ВЫКЛЮЧЕНА</b>"

    text = (
        "📢 <b>Обязательная подписка на канал</b>\n\n"
        f"• Текущий статус: {status_str}\n"
        f"• Канал (username/ID): <code>{channel}</code>\n"
        f"• Ссылка на канал: <code>{channel_url}</code>\n\n"
        "<i>Когда функция включена, пользователь не может генерировать музыку, "
        "пока не подпишется на указанный канал. Администраторы бота проходят без проверки.</i>\n\n"
        "💡 <b>Важно:</b> убедитесь, что бот добавлен в канал (желательно администратором), "
        "чтобы иметь возможность проверять подписчиков."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_sub_keyboard(sub_enabled=sub_enabled),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_sub_toggle")
async def toggle_sub_check(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()

    cur_enabled = await db.is_subscription_check_enabled()
    new_enabled = not cur_enabled
    await db.set_subscription_check_enabled(new_enabled)

    ch_info = await db.get_required_channel()
    has_channel = bool(ch_info.get("channel"))

    if new_enabled:
        if not has_channel:
            await callback.answer("⚠️ Проверка включена, но канал ещё не задан! Нажмите «✏️ Изменить канал».", show_alert=True)
        else:
            await callback.answer("✅ Проверка подписки включена!", show_alert=False)
    else:
        await callback.answer("🔴 Проверка подписки выключена!", show_alert=False)

    await show_sub_settings_menu(callback, state)


@admin_router.callback_query(F.data == "admin_sub_edit_channel")
async def edit_sub_channel(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_sub_channel)
    text = (
        "✏️ <b>Настройка канала обязательной подписки</b>\n\n"
        "Отправьте юзернейм публичного канала (например: <code>@trivela_music</code>) "
        "или числовой ID канала (например: <code>-1001234567890</code>).\n\n"
        "<i>Бот должен состоять в этом канале, чтобы иметь возможность проверять подписку пользователей.</i>"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_sub_menu"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_sub_channel)
async def process_sub_channel(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    raw_channel = message.text.strip()
    if not raw_channel:
        await message.answer("Пожалуйста, отправьте юзернейм канала (@channel) или его числовой ID.")
        return

    if not raw_channel.startswith("@") and not raw_channel.startswith("-") and not raw_channel.isdigit():
        raw_channel = "@" + raw_channel

    await db.set_required_channel(raw_channel)
    await state.clear()

    access_status = "✅ Канал сохранён!"
    try:
        param = int(raw_channel) if (raw_channel.startswith("-") and raw_channel[1:].isdigit()) else raw_channel
        chat = await message.bot.get_chat(param)
        title = getattr(chat, "title", raw_channel)
        access_status = f"✅ Канал «{title}» успешно подключен и проверен!"
    except Exception as e:
        access_status = f"⚠️ Канал <code>{raw_channel}</code> сохранён, но бот пока не смог до него достучаться ({e}). Убедитесь, что бот добавлен в канал!"

    await message.answer(
        f"{access_status}\n\nВозвращаюсь в меню настройки подписки...",
        parse_mode="HTML",
    )

    sub_enabled = await db.is_subscription_check_enabled()
    ch_info = await db.get_required_channel()
    channel = ch_info.get("channel") or "не задан"
    channel_url = ch_info.get("url") or "не задана"
    status_str = "🟢 <b>ВКЛЮЧЕНА</b>" if sub_enabled else "🔴 <b>ВЫКЛЮЧЕНА</b>"

    text = (
        "📢 <b>Обязательная подписка на канал</b>\n\n"
        f"• Текущий статус: {status_str}\n"
        f"• Канал (username/ID): <code>{channel}</code>\n"
        f"• Ссылка на канал: <code>{channel_url}</code>\n\n"
        "<i>Когда функция включена, пользователь не может генерировать музыку, "
        "пока не подпишется на указанный канал.</i>"
    )
    await message.answer(
        text,
        reply_markup=get_admin_sub_keyboard(sub_enabled=sub_enabled),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data == "admin_sub_edit_url")
async def edit_sub_channel_url(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.set_state(AdminStates.waiting_for_sub_channel_url)
    text = (
        "🔗 <b>Настройка ссылки на канал</b>\n\n"
        "Отправьте прямую ссылку на канал или пригласительную ссылку-инвайт "
        "(например: <code>https://t.me/trivela_music</code> или <code>https://t.me/+joinchat...</code>):"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_sub_menu"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_sub_channel_url)
async def process_sub_channel_url(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    url = message.text.strip()
    if not url.startswith("http"):
        url = "https://" + url

    await db.set_setting("required_channel_url", url)
    await state.clear()

    await message.answer(
        f"✅ Ссылка <code>{url}</code> успешно сохранена!\n\nВозвращаюсь в меню...",
        parse_mode="HTML",
    )

    sub_enabled = await db.is_subscription_check_enabled()
    ch_info = await db.get_required_channel()
    channel = ch_info.get("channel") or "не задан"
    channel_url = ch_info.get("url") or "не задана"
    status_str = "🟢 <b>ВКЛЮЧЕНА</b>" if sub_enabled else "🔴 <b>ВЫКЛЮЧЕНА</b>"

    text = (
        "📢 <b>Обязательная подписка на канал</b>\n\n"
        f"• Текущий статус: {status_str}\n"
        f"• Канал (username/ID): <code>{channel}</code>\n"
        f"• Ссылка на канал: <code>{channel_url}</code>\n\n"
        "<i>Когда функция включена, пользователь не может генерировать музыку, "
        "пока не подпишется на указанный канал.</i>"
    )
    await message.answer(
        text,
        reply_markup=get_admin_sub_keyboard(sub_enabled=sub_enabled),
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


# ---------------------------------------------------------
# FEATURE 4: DYNAMIC ARTISTS MANAGEMENT & REORDERING
# ---------------------------------------------------------
@admin_router.callback_query(F.data.startswith("admin_artists:"))
async def show_admin_artists_list(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    parts = callback.data.split(":")
    tab = parts[1] if len(parts) > 1 else "popular"
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    artists = await db.get_artists_by_tab(tab)
    total_count = len(artists)
    tab_name = "⭐ Популярные (сетка 1-го шага)" if tab == "popular" else "📋 Расширенный список"

    text = (
        f"🎤 <b>Управление артистами базы</b>\n\n"
        f"Раздел: <b>{tab_name}</b> (Всего: <b>{total_count}</b>)\n\n"
        "Нажмите на любого артиста, чтобы <b>переместить его выше/ниже</b>, "
        "изменить описание стиля или удалить.\n"
        "Используйте кнопку <b>«➕ Добавить артиста»</b> для ввода нового."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_artists_list_keyboard(artists=artists, tab=tab, page=page),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_artists_noop")
async def admin_artists_noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_artist_view:"))
async def show_admin_artist_card(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    await state.clear()
    parts = callback.data.split(":")
    artist_id = parts[1]
    tab = parts[2] if len(parts) > 2 else "popular"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    artist = await db.get_artist_by_id(artist_id)
    if not artist:
        await callback.answer("Артист не найден в базе данных.", show_alert=True)
        return

    group_artists = await db.get_artists_by_tab(tab)
    total_in_group = len(group_artists)

    position = 1
    for idx, a in enumerate(group_artists, start=1):
        if a["id"] == artist_id:
            position = idx
            break

    is_first = (position <= 1)
    is_last = (position >= total_in_group)
    aliases_str = ", ".join(artist.get("aliases", [])) if artist.get("aliases") else "<i>нет</i>"
    section_label = "⭐ Популярные (сетка 1-го шага)" if artist.get("is_popular") else "📋 Расширенный список"

    text = (
        f"🎤 <b>Карточка артиста: {artist['name']}</b>\n\n"
        f"📍 Позиция в списке: <b>#{position}</b> из {total_in_group}\n"
        f"📂 Категория: <b>{section_label}</b>\n\n"
        f"📝 <b>Стиль для нейросети:</b>\n"
        f"<i>«{artist['style']}»</i>\n\n"
        f"🔍 <b>Алиасы для поиска:</b> {aliases_str}\n\n"
        "<i>Нажимайте «⬆️ Поднять выше» или «⬇️ Опустить ниже», чтобы изменить очерёдность кнопок:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_artist_card_keyboard(
            artist_id=artist_id,
            is_popular=bool(artist.get("is_popular")),
            is_first=is_first,
            is_last=is_last,
            tab=tab,
            page=page,
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_artist_move:"))
async def process_artist_move(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    artist_id = parts[1]
    direction = parts[2]  # "up" or "down"
    tab = parts[3] if len(parts) > 3 else "popular"
    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 1

    swapped = await db.swap_artist_order(artist_id, direction)
    if not swapped:
        await callback.answer("Перемещение в эту сторону невозможно.", show_alert=True)
        return

    await callback.answer("Позиция обновлена!")

    artist = await db.get_artist_by_id(artist_id)
    if not artist:
        return

    group_artists = await db.get_artists_by_tab(tab)
    total_in_group = len(group_artists)

    position = 1
    for idx, a in enumerate(group_artists, start=1):
        if a["id"] == artist_id:
            position = idx
            break

    is_first = (position <= 1)
    is_last = (position >= total_in_group)
    aliases_str = ", ".join(artist.get("aliases", [])) if artist.get("aliases") else "<i>нет</i>"
    section_label = "⭐ Популярные (сетка 1-го шага)" if artist.get("is_popular") else "📋 Расширенный список"

    text = (
        f"🎤 <b>Карточка артиста: {artist['name']}</b>\n\n"
        f"📍 Позиция в списке: <b>#{position}</b> из {total_in_group}\n"
        f"📂 Категория: <b>{section_label}</b>\n\n"
        f"📝 <b>Стиль для нейросети:</b>\n"
        f"<i>«{artist['style']}»</i>\n\n"
        f"🔍 <b>Алиасы для поиска:</b> {aliases_str}\n\n"
        "<i>Нажимайте «⬆️ Поднять выше» или «⬇️ Опустить ниже», чтобы изменить очерёдность кнопок:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_artist_card_keyboard(
            artist_id=artist_id,
            is_popular=bool(artist.get("is_popular")),
            is_first=is_first,
            is_last=is_last,
            tab=tab,
            page=page,
        ),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data.startswith("admin_artist_toggle_pop:"))
async def process_artist_toggle_popular(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    artist_id = parts[1]
    tab = parts[2] if len(parts) > 2 else "popular"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    artist = await db.get_artist_by_id(artist_id)
    if not artist:
        await callback.answer("Артист не найден.", show_alert=True)
        return

    curr_pop = bool(artist.get("is_popular"))
    new_pop = not curr_pop
    new_tab = "popular" if new_pop else "extended"

    dest_artists = await db.get_artists_by_tab(new_tab)
    new_order = len(dest_artists) + 1

    await db.update_artist(artist_id, is_popular=new_pop, display_order=new_order)
    await callback.answer("Категория артиста успешно изменена!")

    artists = await db.get_artists_by_tab(new_tab)
    tab_name = "⭐ Популярные (сетка 1-го шага)" if new_tab == "popular" else "📋 Расширенный список"

    text = (
        f"🎤 <b>Управление артистами базы</b>\n\n"
        f"Раздел: <b>{tab_name}</b> (Всего: <b>{len(artists)}</b>)\n\n"
        f"Артист <b>{artist['name']}</b> перемещён в раздел «{tab_name}»."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_artists_list_keyboard(artists=artists, tab=new_tab, page=1),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data.startswith("admin_artist_del_prompt:"))
async def process_artist_delete_prompt(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    artist_id = parts[1]
    tab = parts[2] if len(parts) > 2 else "popular"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    artist = await db.get_artist_by_id(artist_id)
    if not artist:
        await callback.answer("Артист не найден.", show_alert=True)
        return

    text = (
        f"⚠️ <b>Подтверждение удаления артиста</b>\n\n"
        f"Вы действительно хотите удалить артиста <b>{artist['name']}</b> из базы?\n"
        "Он перестанет отображаться в кнопках и в поиске."
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_artist_delete_confirm_keyboard(artist_id, tab, page),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_artist_del_confirm:"))
async def process_artist_delete_confirm(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    artist_id = parts[1]
    tab = parts[2] if len(parts) > 2 else "popular"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    await db.delete_artist(artist_id)
    await callback.answer("Артист удалён!", show_alert=True)

    artists = await db.get_artists_by_tab(tab)
    tab_name = "⭐ Популярные (сетка 1-го шага)" if tab == "popular" else "📋 Расширенный список"

    text = (
        f"🎤 <b>Управление артистами базы</b>\n\n"
        f"Раздел: <b>{tab_name}</b> (Всего: <b>{len(artists)}</b>)\n\n"
        "Артист успешно удалён из базы."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_artists_list_keyboard(artists=artists, tab=tab, page=page),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data.startswith("admin_artist_edit_style:"))
async def process_artist_edit_style_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    artist_id = parts[1]
    tab = parts[2] if len(parts) > 2 else "popular"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    artist = await db.get_artist_by_id(artist_id)
    if not artist:
        await callback.answer("Артист не найден.", show_alert=True)
        return

    await state.update_data(
        edit_artist_id=artist_id,
        edit_artist_name=artist["name"],
        edit_tab=tab,
        edit_page=page,
    )
    await state.set_state(AdminStates.waiting_for_artist_edit_style)

    text = (
        f"✏️ <b>Редактирование стиля артиста: {artist['name']}</b>\n\n"
        f"Текущее описание:\n<i>«{artist['style']}»</i>\n\n"
        "Отправьте <b>новое описание стиля для нейросети</b> сообщением в чат:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard(f"admin_artist_view:{artist_id}:{tab}:{page}"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_artist_edit_style)
async def process_artist_new_style_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    new_style = message.text.strip()
    if len(new_style) < 3:
        await message.answer("⚠️ Описание стиля слишком короткое. Введите подробнее:")
        return

    data = await state.get_data()
    artist_id = data.get("edit_artist_id")
    artist_name = data.get("edit_artist_name", "Артист")
    tab = data.get("edit_tab", "popular")
    page = data.get("edit_page", 1)

    await state.clear()
    if not artist_id:
        await message.answer("Ошибка сессии. Перейдите в /admin.")
        return

    await db.update_artist(artist_id, style=new_style)

    await message.answer(
        f"✅ <b>Стиль для «{artist_name}» обновлён!</b>\n\n"
        f"Новое описание:\n<i>«{new_style}»</i>",
        reply_markup=get_admin_cancel_keyboard(f"admin_artist_view:{artist_id}:{tab}:{page}"),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# ADD NEW ARTIST WIZARD
# ---------------------------------------------------------
@admin_router.callback_query(F.data.startswith("admin_artist_add"))
async def start_add_artist(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    tab = parts[1] if len(parts) > 1 else "popular"
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1

    await state.clear()
    await state.update_data(add_tab=tab, add_page=page)
    await state.set_state(AdminStates.waiting_for_artist_name)

    text = (
        "➕ <b>Добавление нового артиста (Шаг 1 из 3)</b>\n\n"
        "Введите <b>имя исполнителя</b> (так, как оно будет отображаться на кнопке в Telegram):\n"
        "<i>Например: Drake, MACAN или Linkin Park</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard(f"admin_artists:{tab}:{page}"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_artist_name)
async def process_new_artist_name(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    name = message.text.strip()
    if len(name) < 2:
        await message.answer("⚠️ Имя артиста слишком короткое. Введите корректное имя:")
        return

    await state.update_data(new_artist_name=name)
    await state.set_state(AdminStates.waiting_for_artist_style)

    data = await state.get_data()
    tab = data.get("add_tab", "popular")
    page = data.get("add_page", 1)

    text = (
        f"➕ <b>Добавление артиста: {name} (Шаг 2 из 3)</b>\n\n"
        "Введите <b>описание стиля для нейросети</b> (жанры, инструменты, подача, вокал, темп):\n"
        "<i>Например: мелодичный трэп, R&B, автотюн, ночной вайб, глубокий 808 бас</i>"
    )

    await message.answer(
        text,
        reply_markup=get_admin_cancel_keyboard(f"admin_artists:{tab}:{page}"),
        parse_mode="HTML",
    )


@admin_router.message(AdminStates.waiting_for_artist_style)
async def process_new_artist_style(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    style = message.text.strip()
    if len(style) < 3:
        await message.answer("⚠️ Описание стиля слишком короткое. Введите подробнее:")
        return

    await state.update_data(new_artist_style=style)
    await state.set_state(AdminStates.waiting_for_artist_aliases)

    data = await state.get_data()
    name = data.get("new_artist_name", "")
    tab = data.get("add_tab", "popular")
    page = data.get("add_page", 1)

    text = (
        f"➕ <b>Добавление артиста: {name} (Шаг 3 из 3)</b>\n\n"
        "Введите <b>псевдонимы / алиасы для поиска</b> через запятую:\n"
        "<i>Например: дрейк, drake, champagne papi</i>\n\n"
        "Или отправьте <b>«-»</b>, если дополнительные алиасы не нужны."
    )

    await message.answer(
        text,
        reply_markup=get_admin_cancel_keyboard(f"admin_artists:{tab}:{page}"),
        parse_mode="HTML",
    )


@admin_router.message(AdminStates.waiting_for_artist_aliases)
async def process_new_artist_aliases(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return

    raw_aliases = message.text.strip()
    aliases = []
    if raw_aliases != "-":
        aliases = [a.strip().lower() for a in raw_aliases.split(",") if a.strip()]

    data = await state.get_data()
    name = data.get("new_artist_name", "")
    aliases.append(name.lower())
    aliases = list(dict.fromkeys(aliases))  # deduplicate

    await state.update_data(new_artist_aliases=aliases)

    text = (
        f"⭐ <b>Куда добавить артиста «{name}»?</b>\n\n"
        "• <b>В популярные:</b> артист появится прямо в сетке кнопок на Шаге 1.\n"
        "• <b>В расширенный список:</b> артист будет доступен по кнопке «📋 Показать всех артистов» и по поиску сообщением."
    )

    await message.answer(
        text,
        reply_markup=get_admin_artist_popularity_choice_keyboard(),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data.startswith("admin_artist_create_pop:"))
async def process_new_artist_finish(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    is_pop = callback.data.split(":")[1] == "1"
    data = await state.get_data()
    name = data.get("new_artist_name")
    style = data.get("new_artist_style")
    aliases = data.get("new_artist_aliases", [])

    await state.clear()

    if not name or not style:
        await callback.answer("Ошибка сессии добавления артиста.", show_alert=True)
        return

    artist_id = await db.add_artist(
        name=name,
        style=style,
        aliases=aliases,
        is_popular=is_pop,
    )

    tab = "popular" if is_pop else "extended"
    tab_title = "⭐ Популярные (сетка 1-го шага)" if is_pop else "📋 Расширенный список"

    text = (
        f"🎉 <b>Артист успешно добавлен!</b>\n\n"
        f"🎤 <b>Имя:</b> {name}\n"
        f"📂 <b>Категория:</b> {tab_title}\n"
        f"📝 <b>Стиль:</b> <i>«{style}»</i>\n"
        f"🔍 <b>Алиасы:</b> {', '.join(aliases)}\n\n"
        "Артист моментально доступен пользователям при создании трека!"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard(f"admin_artists:{tab}:1"),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------
# PROMO CODES ADMIN MANAGEMENT
# ---------------------------------------------------------
@admin_router.callback_query(F.data == "admin_promos")
async def show_admin_promos_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    promos = await db.get_all_promo_codes()
    active_count = sum(1 for p in promos if p.get("is_active"))
    total_count = len(promos)

    text = (
        "🎟 <b>Управление промокодами</b>\n\n"
        f"📊 Всего промокодов: <b>{total_count}</b> (активных: <b>{active_count}</b>)\n\n"
        "Здесь вы можете создать новые промокоды со скидкой или бонусом генераций, "
        "а также просмотреть текущие промокоды и статистику их использований."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_promos_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_promo_create")
async def start_promo_creation(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    await state.clear()
    await state.set_state(AdminStates.waiting_for_promo_type)
    text = (
        "🎟 <b>Создание промокода (Шаг 1 из 5)</b>\n\n"
        "Выберите, какую награду даёт промокод:\n\n"
        "• <b>Процент скидки:</b> уменьшает цену при покупке пакетов генераций.\n"
        "• <b>Генерации (бонус):</b> моментально начисляет подарочные генерации на баланс."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_promo_type_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_promo_type:"))
async def process_promo_type_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    p_type = callback.data.split(":")[1]
    await state.update_data(promo_type=p_type)

    if p_type == "credits":
        await state.set_state(AdminStates.waiting_for_promo_credits_amount)
        text = (
            "🎵 <b>Количество бонусных генераций (Шаг 2 из 5)</b>\n\n"
            "Введите целое положительное число генераций, которые получит пользователь при активации промокода (например: <code>10</code>, <code>25</code>, <code>50</code>):"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
    else:
        # Discount mode selection
        await state.set_state(AdminStates.waiting_for_promo_discount_mode)
        text = (
            "📊 <b>Способ применения скидки (Шаг 2 из 5)</b>\n\n"
            "Выберите тип скидки:\n\n"
            "• <b>Фиксированный % (на все):</b> единый процент скидки для всех тарифов.\n"
            "• <b>Для каждого тарифа отдельно:</b> возможность задать разный процент на каждый пакет (например, 0% на дешёвый и 40% на самый дорогой)."
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_promo_discount_mode_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_promo_disc_mode:"))
async def process_promo_discount_mode_choice(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    d_mode = callback.data.split(":")[1]
    await state.update_data(discount_mode=d_mode)

    if d_mode == "fixed":
        await state.set_state(AdminStates.waiting_for_promo_fixed_percent)
        text = (
            "🎯 <b>Фиксированный процент скидки (Шаг 2 из 5)</b>\n\n"
            "Введите размер скидки в процентах от <b>1</b> до <b>99</b>% (например: <code>15</code>, <code>30</code>):\n\n"
            "⚠️ <i>100% указывать запрещено.</i>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
    else:
        # Custom mode per pack
        db_tariffs = await db.get_all_tariffs()
        tariffs = db_tariffs if db_tariffs else TARIFF_PACKAGES
        await state.update_data(
            custom_tariffs=[dict(t) for t in tariffs],
            custom_pack_index=0,
            custom_packs_discounts={},
        )
        await state.set_state(AdminStates.waiting_for_promo_custom_pack)
        first_t = tariffs[0]
        text = (
            f"🎛 <b>Настройка скидки для тарифа 1 из {len(tariffs)}</b>\n\n"
            f"Пакет: {first_t['emoji']} <b>{first_t['title']}</b> ({int(first_t['price'])} ₽)\n\n"
            "Введите процент скидки для этого тарифа (от <b>0</b> до <b>99</b>%):\n"
            "<i>(0 означает отсутствие скидки на этот пакет)</i>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_promo_fixed_percent)
async def process_promo_fixed_percent_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip().replace("%", "")
    try:
        val = int(raw)
    except ValueError:
        await message.answer("⚠️ Введите целое число от 1 до 99 (например: 20):", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    if val == 100:
        await message.answer("❌ <b>100% указывать запрещено!</b>\nСкидка должна быть в пределах от 1 до 99%.\nПопробуйте ещё раз:", parse_mode="HTML", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return
    if val < 1 or val > 99:
        await message.answer("❌ Процент должен быть от 1 до 99%. Введите число заново:", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    await state.update_data(fixed_percent=val)
    await state.set_state(AdminStates.waiting_for_promo_duration)
    await message.answer(
        "⏱ <b>Срок действия промокода (Шаг 3 из 5)</b>\n\n"
        "Выберите, до какого момента промокод будет доступен для активации:\n\n"
        "<i>(После того как пользователь активирует промокод, у него будет ровно 24 часа на совершение 1 покупки по скидке)</i>",
        reply_markup=get_admin_promo_duration_keyboard(),
        parse_mode="HTML",
    )


@admin_router.message(AdminStates.waiting_for_promo_custom_pack)
async def process_promo_custom_pack_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip().replace("%", "")
    try:
        val = int(raw)
    except ValueError:
        await message.answer("⚠️ Введите целое число от 0 до 99:", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    if val == 100:
        await message.answer("❌ <b>100% указывать запрещено!</b>\nВведите от 0 до 99%:", parse_mode="HTML", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return
    if val < 0 or val > 99:
        await message.answer("❌ Процент должен быть в диапазоне от 0 до 99%. Попробуйте заново:", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    data = await state.get_data()
    tariffs = data.get("custom_tariffs", [])
    idx = data.get("custom_pack_index", 0)
    discounts = data.get("custom_packs_discounts", {})

    cur_t = tariffs[idx]
    discounts[cur_t["id"]] = val
    next_idx = idx + 1

    if next_idx < len(tariffs):
        await state.update_data(custom_pack_index=next_idx, custom_packs_discounts=discounts)
        next_t = tariffs[next_idx]
        text = (
            f"🎛 <b>Настройка скидки для тарифа {next_idx + 1} из {len(tariffs)}</b>\n\n"
            f"Пакет: {next_t['emoji']} <b>{next_t['title']}</b> ({int(next_t['price'])} ₽)\n\n"
            "Введите процент скидки для этого тарифа (от <b>0</b> до <b>99</b>%):\n"
            "<i>(0 означает отсутствие скидки на этот пакет)</i>"
        )
        await message.answer(text, reply_markup=get_admin_cancel_keyboard("admin_promos"), parse_mode="HTML")
    else:
        # Check if at least one tariff has percent > 0
        if not any(v > 0 for v in discounts.values()):
            await state.update_data(custom_pack_index=0, custom_packs_discounts={})
            first_t = tariffs[0]
            await message.answer(
                "❌ <b>Ошибка:</b> хотя бы на один тариф должна быть скидка больше 0%!\n"
                "Давайте настроим скидки заново.\n\n"
                f"Пакет: {first_t['emoji']} <b>{first_t['title']}</b> ({int(first_t['price'])} ₽)\n"
                "Введите процент скидки (0-99%):",
                reply_markup=get_admin_cancel_keyboard("admin_promos"),
                parse_mode="HTML",
            )
            return

        await state.update_data(custom_packs_discounts=discounts)
        await state.set_state(AdminStates.waiting_for_promo_duration)
        await message.answer(
            "⏱ <b>Срок действия промокода (Шаг 3 из 5)</b>\n\n"
            "Выберите, до какого момента промокод будет доступен для активации:\n\n"
            "<i>(После того как пользователь активирует промокод, у него будет ровно 24 часа на совершение 1 покупки по скидке)</i>",
            reply_markup=get_admin_promo_duration_keyboard(),
            parse_mode="HTML",
        )


@admin_router.message(AdminStates.waiting_for_promo_credits_amount)
async def process_promo_credits_amount_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    try:
        val = int(raw)
    except ValueError:
        await message.answer("⚠️ Введите целое положительное число (например: 15):", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    if val <= 0:
        await message.answer("❌ Количество генераций должно быть больше 0. Попробуйте заново:", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    await state.update_data(credits_amount=val)
    await state.set_state(AdminStates.waiting_for_promo_duration)
    await message.answer(
        "⏱ <b>Срок действия промокода (Шаг 3 из 5)</b>\n\n"
        "Выберите, до какого момента промокод будет доступен для активации:",
        reply_markup=get_admin_promo_duration_keyboard(),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data.startswith("admin_promo_dur:"))
async def process_promo_duration_preset(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return
    dur_key = callback.data.split(":")[1]

    if dur_key == "manual":
        await state.set_state(AdminStates.waiting_for_promo_custom_date)
        text = (
            "✏️ <b>Ввод даты окончания вручную (Шаг 3 из 5)</b>\n\n"
            "Введите дату и время окончания действия промокода по Московскому времени (МСК) в формате:\n"
            "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
            "<i>Пример: 31.12.2026 23:59</i>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    now = get_msk_now()
    if dur_key == "1h":
        exp_dt = now + timedelta(hours=1)
    elif dur_key == "3h":
        exp_dt = now + timedelta(hours=3)
    elif dur_key == "5h":
        exp_dt = now + timedelta(hours=5)
    elif dur_key == "12h":
        exp_dt = now + timedelta(hours=12)
    elif dur_key == "24h":
        exp_dt = now + timedelta(hours=24)
    elif dur_key == "3d":
        exp_dt = now + timedelta(days=3)
    elif dur_key == "7d":
        exp_dt = now + timedelta(days=7)
    elif dur_key == "30d":
        exp_dt = now + timedelta(days=30)
    else:
        exp_dt = now + timedelta(hours=24)

    exp_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
    await state.update_data(expires_at=exp_str)
    await state.set_state(AdminStates.waiting_for_promo_max_activations)

    text = (
        "👥 <b>Количество активаций (Шаг 4 из 5)</b>\n\n"
        f"Выбран срок до: <b>{exp_dt.strftime('%d.%m.%Y %H:%M')} (МСК)</b>\n\n"
        "Введите максимальное количество пользователей, которые смогут активировать этот промокод (целое положительное число, например: <code>100</code>):"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_promos"),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.message(AdminStates.waiting_for_promo_custom_date)
async def process_promo_custom_date_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    try:
        parsed_dt = datetime.strptime(text, "%d.%m.%Y %H:%M").replace(tzinfo=MSK_TZ)
    except ValueError:
        await message.answer(
            "⚠️ <b>Неверный формат даты!</b>\n\n"
            "Введите дату и время строго в формате <code>ДД.ММ.ГГГГ ЧЧ:ММ</code> (например: <code>31.12.2026 23:59</code>):",
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
        return

    now = get_msk_now()
    if parsed_dt <= now:
        await message.answer(
            "⚠️ <b>Дата окончания должна быть в будущем!</b>\n"
            f"Текущее московское время: {now.strftime('%d.%m.%Y %H:%M')}.\n\n"
            "Пожалуйста, введите дату заново:",
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
        return

    exp_str = parsed_dt.strftime("%Y-%m-%d %H:%M:%S")
    await state.update_data(expires_at=exp_str)
    await state.set_state(AdminStates.waiting_for_promo_max_activations)

    await message.answer(
        "👥 <b>Количество активаций (Шаг 4 из 5)</b>\n\n"
        f"Выбран срок до: <b>{parsed_dt.strftime('%d.%m.%Y %H:%M')} (МСК)</b>\n\n"
        "Введите максимальное количество пользователей, которые смогут активировать промокод (например: <code>100</code>):",
        reply_markup=get_admin_cancel_keyboard("admin_promos"),
        parse_mode="HTML",
    )


@admin_router.message(AdminStates.waiting_for_promo_max_activations)
async def process_promo_max_activations_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw = (message.text or "").strip()
    try:
        val = int(raw)
    except ValueError:
        await message.answer("⚠️ Введите целое положительное число (например: 100):", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    if val <= 0:
        await message.answer("❌ Количество должно быть больше 0. Попробуйте заново:", reply_markup=get_admin_cancel_keyboard("admin_promos"))
        return

    await state.update_data(max_activations=val)
    await state.set_state(AdminStates.waiting_for_promo_code_text)

    text = (
        "🔤 <b>Текст промокода (Шаг 5 из 5)</b>\n\n"
        "Введите секретный код промокода, который будут вводить пользователи.\n\n"
        "⚠️ <b>Правила:</b>\n"
        "• Пробелы строго запрещены!\n"
        "• Регистр имеет значение (например, <code>MUSIC2026</code> и <code>music2026</code> — разные коды).\n"
        "• Разрешены русские и английские буквы, цифры и символы.\n"
        "• Длина от 2 до 50 символов."
    )
    await message.answer(
        text,
        reply_markup=get_admin_cancel_keyboard("admin_promos"),
        parse_mode="HTML",
    )


@admin_router.message(AdminStates.waiting_for_promo_code_text)
async def process_promo_code_text_input(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    raw_code = (message.text or "").strip()

    if not raw_code:
        await message.answer("⚠️ Введите текст промокода:")
        return

    if " " in raw_code or "\t" in raw_code or "\n" in raw_code:
        await message.answer(
            "❌ <b>Промокод не должен содержать пробелов!</b>\n\n"
            "Пожалуйста, введите промокод заново без пробелов:",
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
        return

    if len(raw_code) < 2 or len(raw_code) > 50:
        await message.answer(
            "❌ Длина промокода должна быть от 2 до 50 символов. Попробуйте заново:",
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
        return

    existing = await db.get_promo_code_by_code(raw_code)
    if existing:
        await message.answer(
            "❌ <b>Промокод с таким текстом уже существует в базе данных!</b>\n\n"
            "Придумайте другой промокод:",
            reply_markup=get_admin_cancel_keyboard("admin_promos"),
            parse_mode="HTML",
        )
        return

    await state.update_data(code=raw_code)
    await state.set_state(AdminStates.waiting_for_promo_confirm)

    data = await state.get_data()
    p_type = data.get("promo_type")
    max_act = data.get("max_activations")
    exp_str = data.get("expires_at", "")
    try:
        exp_formatted = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except Exception:
        exp_formatted = exp_str

    if p_type == "credits":
        reward_desc = f"🎁 <b>+{data.get('credits_amount')}</b> подарочных генераций"
        promo_type_name = "Бонусные генерации"
        fair_note = "Начисляются сразу на баланс при активации."
    else:
        promo_type_name = "Скидка на пополнение"
        d_mode = data.get("discount_mode")
        db_tariffs = await db.get_all_tariffs()
        tariffs = db_tariffs if db_tariffs else TARIFF_PACKAGES

        lines = []
        if d_mode == "fixed":
            pct = int(data.get("fixed_percent", 0))
            for t in tariffs:
                orig_pr = float(t["price"])
                disc_pr = max(1, round(orig_pr * (1 - pct / 100)))
                per_track = format_per_track_badge(disc_pr, t.get("credits", 1))
                lines.append(
                    f"  • {t['emoji']} <b>{t['title']}</b>: <s>{int(orig_pr)} ₽</s> ➔ <b>{int(disc_pr)} ₽</b> "
                    f"<i>(-{pct}%, {per_track})</i>"
                )
            reward_desc = f"🏷 <b>Скидка {pct}% на все тарифы (итоговые цены для пользователя):</b>\n" + "\n".join(lines)
        else:
            packs_map = data.get("custom_packs_discounts", {})
            for t in tariffs:
                orig_pr = float(t["price"])
                pct = int(packs_map.get(t["id"], 0))
                if pct > 0:
                    disc_pr = max(1, round(orig_pr * (1 - pct / 100)))
                    per_track = format_per_track_badge(disc_pr, t.get("credits", 1))
                    lines.append(
                        f"  • {t['emoji']} <b>{t['title']}</b>: <s>{int(orig_pr)} ₽</s> ➔ <b>{int(disc_pr)} ₽</b> "
                        f"<i>(-{pct}%, {per_track})</i>"
                    )
                else:
                    per_track = format_per_track_badge(orig_pr, t.get("credits", 1))
                    lines.append(
                        f"  • {t['emoji']} <b>{t['title']}</b>: <b>{int(orig_pr)} ₽</b> <i>(без скидки, {per_track})</i>"
                    )
            reward_desc = "🏷 <b>Дифференцированная скидка (итоговые цены для пользователя):</b>\n" + "\n".join(lines)

        fair_note = "Ровно 24 часа с момента ввода (на 1 покупку)."

    confirm_text = (
        "📋 <b>Проверьте данные нового промокода:</b>\n\n"
        f"🎟 <b>Код:</b> <code>{raw_code}</code>\n"
        f"📌 <b>Тип:</b> {promo_type_name}\n"
        f"🎁 <b>Вознаграждение:</b>\n{reward_desc}\n\n"
        f"⏱ <b>Доступен для активации до:</b> <b>{exp_formatted} (МСК)</b>\n"
        f"👥 <b>Лимит активаций:</b> <b>{max_act}</b> человек (по 1 разу на пользователя)\n"
        f"⏳ <b>Срок действия скидки:</b> {fair_note}\n\n"
        "<b>Вы точно уверены, что хотите создать этот промокод?</b>"
    )

    await message.answer(
        confirm_text,
        reply_markup=get_admin_promo_confirm_keyboard(),
        parse_mode="HTML",
    )


@admin_router.callback_query(F.data == "admin_promo_confirm_create")
async def process_promo_confirm_create(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        return

    data = await state.get_data()
    code = data.get("code")
    p_type = data.get("promo_type")
    max_act = data.get("max_activations", 100)
    expires_at = data.get("expires_at")

    if not code or not p_type or not expires_at:
        await state.clear()
        await callback.answer("Ошибка сессии создания промокода.", show_alert=True)
        return

    if p_type == "credits":
        db_type = "credits"
        reward_data = {"credits": data.get("credits_amount", 0)}
    else:
        d_mode = data.get("discount_mode", "fixed")
        if d_mode == "fixed":
            db_type = "discount_fixed"
            reward_data = {
                "discount_mode": "fixed",
                "percent": data.get("fixed_percent", 0),
            }
        else:
            db_type = "discount_custom"
            reward_data = {
                "discount_mode": "custom",
                "packs": data.get("custom_packs_discounts", {}),
            }

    promo_id = await db.create_promo_code(
        code=code,
        promo_type=db_type,
        reward_data=reward_data,
        max_activations=max_act,
        expires_at=expires_at,
    )
    await state.clear()

    finish_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔎 Посмотреть промокод", callback_data=f"admin_promo_card:{promo_id}:1"),
            ],
            [
                InlineKeyboardButton(text="📋 К списку промокодов", callback_data="admin_promo_list:1"),
                InlineKeyboardButton(text="◀️ Меню промокодов", callback_data="admin_promos"),
            ],
        ]
    )

    await callback.message.edit_text(
        f"🎉 <b>Промокод «{code}» успешно создан и активен!</b>\n\n"
        "Пользователи могут вводить его в профиле и получать скидки или генерации.",
        reply_markup=finish_kb,
        parse_mode="HTML",
    )
    await callback.answer("Промокод создан!")


PROMOS_PER_PAGE = 6


@admin_router.callback_query(F.data.startswith("admin_promo_list:"))
async def show_admin_promos_list(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.split(":")[1])
    promos = await db.get_all_promo_codes()

    total_pages = max(1, (len(promos) + PROMOS_PER_PAGE - 1) // PROMOS_PER_PAGE)
    page = max(1, min(page, total_pages))

    start = (page - 1) * PROMOS_PER_PAGE
    page_promos = promos[start : start + PROMOS_PER_PAGE]

    text = (
        f"📋 <b>Список промокодов (Стр. {page}/{total_pages})</b>\n\n"
        "🟢 — активен | 🔴 — деактивирован\n"
        "Нажмите на промокод для просмотра подробностей и управления:"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_promos_list_keyboard(page_promos, page, total_pages),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data == "admin_promo_noop")
async def callback_admin_promo_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_promo_card:"))
async def show_admin_promo_card(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    promo_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    promo = await db.get_promo_code_by_id(promo_id)
    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    now = get_msk_now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    is_active = bool(promo.get("is_active"))
    cur_act = promo.get("current_activations", 0)
    max_act = promo.get("max_activations", 0)
    expires_at = promo.get("expires_at", "")

    # Status detection
    if not is_active:
        status_str = "🔴 <b>Деактивирован администратором</b>"
    elif expires_at <= now_str:
        status_str = "⏳ <b>Истёк срок действия</b>"
    elif cur_act >= max_act:
        status_str = "🏁 <b>Лимит активаций исчерпан</b>"
    else:
        status_str = "🟢 <b>Активен (доступен для ввода)</b>"

    p_type = promo.get("promo_type")
    rdata = promo.get("reward_data") or {}

    if p_type == "credits":
        type_str = "Бонусные генерации"
        reward_str = f"🎁 +{rdata.get('credits', 0)} генераций"
    elif p_type == "discount_fixed":
        type_str = "Фиксированная скидка"
        pct = int(rdata.get("percent", 0))
        db_tariffs = await db.get_all_tariffs()
        tariffs = db_tariffs if db_tariffs else TARIFF_PACKAGES
        lines = []
        for t in tariffs:
            orig_pr = float(t["price"])
            disc_pr = max(1, round(orig_pr * (1 - pct / 100)))
            per_track = format_per_track_badge(disc_pr, t.get("credits", 1))
            lines.append(
                f"  • {t['emoji']} <b>{t['title']}</b>: <s>{int(orig_pr)} ₽</s> ➔ <b>{int(disc_pr)} ₽</b> "
                f"<i>(-{pct}%, {per_track})</i>"
            )
        reward_str = f"🏷 <b>-{pct}% на все тарифы (цены для пользователя):</b>\n" + "\n".join(lines)
    else:
        type_str = "Дифференцированная скидка"
        db_tariffs = await db.get_all_tariffs()
        tariffs = db_tariffs if db_tariffs else TARIFF_PACKAGES
        packs_map = rdata.get("packs", {})
        lines = []
        for t in tariffs:
            orig_pr = float(t["price"])
            pct = int(packs_map.get(t["id"], 0))
            if pct > 0:
                disc_pr = max(1, round(orig_pr * (1 - pct / 100)))
                per_track = format_per_track_badge(disc_pr, t.get("credits", 1))
                lines.append(
                    f"  • {t['emoji']} <b>{t['title']}</b>: <s>{int(orig_pr)} ₽</s> ➔ <b>{int(disc_pr)} ₽</b> "
                    f"<i>(-{pct}%, {per_track})</i>"
                )
            else:
                per_track = format_per_track_badge(orig_pr, t.get("credits", 1))
                lines.append(
                    f"  • {t['emoji']} <b>{t['title']}</b>: <b>{int(orig_pr)} ₽</b> <i>(без скидки, {per_track})</i>"
                )
        reward_str = "🏷 <b>Дифференцированная скидка (цены для пользователя):</b>\n" + "\n".join(lines)

    try:
        exp_formatted = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
    except Exception:
        exp_formatted = expires_at

    text = (
        f"🎟 <b>Промокод:</b> <code>{promo['code']}</code>\n\n"
        f"📊 <b>Статус:</b> {status_str}\n"
        f"📌 <b>Тип:</b> {type_str}\n"
        f"🎁 <b>Награда:</b>\n{reward_str}\n\n"
        f"👥 <b>Использования:</b> <b>{cur_act} / {max_act}</b> чел.\n"
        f"⏱ <b>Действует до:</b> {exp_formatted} (МСК)\n"
        f"📅 <b>Создан:</b> {promo.get('created_at', '')}\n\n"
        "💡 <i>При деактивации промокода запрещаются новые активации. Пользователи, уже успевшие активировать его, сохраняют свою 24ч скидку.</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_admin_promo_card_keyboard(promo_id, is_active=is_active, page=page),
        parse_mode="HTML",
    )
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_promo_deact:"))
async def process_admin_promo_deact(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split(":")
    promo_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 1

    await db.deactivate_promo_code(promo_id)
    await callback.answer("⛔ Промокод деактивирован. Новые активации заблокированы.", show_alert=True)

    # Re-render card with updated status
    promo = await db.get_promo_code_by_id(promo_id)
    if promo:
        await show_admin_promo_card(callback)
