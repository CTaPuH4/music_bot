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
    get_admin_sub_keyboard,
    get_admin_broadcast_confirm_keyboard,
    get_admin_tariffs_keyboard,
    get_admin_cancel_keyboard,
    get_admin_artists_list_keyboard,
    get_admin_artist_card_keyboard,
    get_admin_artist_delete_confirm_keyboard,
    get_admin_artist_popularity_choice_keyboard,
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
