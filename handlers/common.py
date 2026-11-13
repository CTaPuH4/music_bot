import html
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database.db import db, get_msk_now
from keyboards.inline import (
    get_main_menu_keyboard,
    get_profile_keyboard,
    get_referral_keyboard,
    get_help_keyboard,
    get_promo_input_cancel_keyboard,
    get_promo_replace_keyboard,
)
from keyboards.reply import get_main_reply_keyboard
from services.referral import get_referral_tier, format_referral_tiers_table
from states.promo import UserPromoStates

logger = logging.getLogger(__name__)
common_router = Router()


@common_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Check for referral in start parameter, e.g. /start ref_123456
    referrer_id = None
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            potential_ref = int(args[1].replace("ref_", ""))
            if potential_ref != user_id:
                referrer_id = potential_ref
        except ValueError:
            pass

    user = await db.get_or_create_user(
        user_id=user_id,
        username=username,
        first_name=first_name,
        referred_by=referrer_id,
    )

    safe_name = html.escape(first_name or 'друг')
    welcome_text = (
        f"👋 <b>Привет, {safe_name}!</b>\n\n"
        f"Я бот для создания полноценной музыки с помощью <b>искусственного интеллекта</b> 🎧\n\n"
        f"✨ <b>Что я умею:</b>\n"
        f"• Создавать музыку любых жанров по текстовому описанию (промту)\n"
        f"• Генерировать песни с вокалом и AI-стихами\n"
        f"• Писать инструментальные треки без слов\n"
        f"• Записывать треки с вашим собственным текстом\n\n"
        f"💰 Ваш баланс: <b>{user['total_balance']}</b> генераций\n\n"
        f"Воспользуйтесь кнопками внизу экрана или отправьте описание трека прямо в чат!"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_reply_keyboard(),
        parse_mode="HTML",
    )


@common_router.callback_query(F.data == "menu_help")
@common_router.message(Command("help"))
@common_router.message(F.text.in_({"ℹ️ Помощь", "ℹ️ Инструкция"}))
async def cmd_help(event: Message | CallbackQuery) -> None:
    help_text = (
        "📖 <b>Инструкция по созданию музыки:</b>\n\n"
        "Создание трека состоит из 4 простых шагов:\n\n"
        "1️⃣ <b>Артист-референс:</b>\n"
        "Выберите исполнителя, чью манеру и вокальный стиль вы хотите придать треку "
        "(MACAN, ANNA ASTI, Баста, Цой, Король и Шут и др.), либо нажмите <i>«Без артиста»</i> для уникального стиля.\n\n"
        "2️⃣ <b>Жанры (минимум 2):</b>\n"
        "Отметьте хотя бы 2 жанра из списка (например, <i>Рок + Электроника</i> или <i>Lo-Fi + R&B</i>). "
        "Смешивание стилей задаёт многослойное профессиональное звучание.\n\n"
        "3️⃣ <b>Текст песни (Lyrics):</b>\n"
        "• <b>Auto (ИИ напишет текст):</b> нейросеть сама сочинит стихи и исполнит песню.\n"
        "• <b>Свой текст:</b> загрузите свои стихи или куплеты.\n"
        "• <b>Инструментал:</b> чистая музыка без вокала.\n\n"
        "4️⃣ <b>Идея трека (для режима Auto):</b>\n"
        "Опишите, о чём и в каком стиле написать текст (например: <i>«напиши текст в стиле скриптонита про ночной город»</i>).\n\n"
        "⏱ <b>Время ожидания:</b> 1–2 минуты. Бот пришлёт готовый MP3 файл с обложкой."
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            help_text,
            reply_markup=get_help_keyboard(),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            help_text,
            reply_markup=get_help_keyboard(),
            parse_mode="HTML",
        )


@common_router.callback_query(F.data == "menu_profile")
@common_router.message(Command("profile"))
@common_router.message(Command("balance"))
@common_router.message(F.text.in_({"👤 Профиль и баланс", "👤 Профиль", "👤 Баланс и профиль"}))
async def show_profile(event: Message | CallbackQuery, state: Optional[FSMContext] = None) -> None:
    if state:
        await state.clear()

    user_id = event.from_user.id
    user = await db.get_user(user_id)
    if not user:
        user = await db.get_or_create_user(
            user_id,
            event.from_user.username,
            event.from_user.first_name,
        )

    stats = await db.get_user_stats(user_id)
    total = user.get("total_balance", 0)
    paid = user.get("paid_balance", 0)
    gift = user.get("gift_balance", 0)
    ref_count = stats.get("referrals_count", 0)

    # Check active discount
    active_discount = await db.get_user_active_discount(user_id)
    discount_line = ""
    has_discount = False

    if active_discount:
        has_discount = True
        ddata = active_discount.get("discount_data") or {}
        dmode = ddata.get("discount_mode") or ddata.get("type", "fixed")
        code_text = active_discount.get("code")
        rem_str = active_discount.get("remaining_time_str", "24 ч.")

        if code_text:
            if dmode == "fixed" and ddata.get("percent"):
                disc_label = f"<code>{code_text}</code> (-{ddata.get('percent')}%)"
            else:
                disc_label = f"<code>{code_text}</code>"
        else:
            if dmode == "fixed" and ddata.get("percent"):
                disc_label = f"скидка {ddata.get('percent')}%"
            else:
                disc_label = "скидка на тарифы"

        discount_line = f"🏷 <b>Активный промокод:</b> {disc_label} <i>(осталось: {rem_str})</i>\n"

    text = (
        f"👤 <b>Ваш профиль и баланс:</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        f"💰 <b>Всего генераций:</b> <b>{total}</b>\n"
        f"├── 💳 Платные: <b>{paid}</b>\n"
        f"└── 🎁 Подарочные: <b>{gift}</b>\n\n"
        f"{discount_line}"
        f"🎵 Всего создано треков: <b>{stats['total_generations']}</b>\n"
        f"👥 Приглашено друзей: <b>{ref_count}</b>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_profile_keyboard(has_discount=has_discount),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_profile_keyboard(has_discount=has_discount),
            parse_mode="HTML",
        )


# ---------------------------------------------------------
# USER PROMO CODES ACTIVATION
# ---------------------------------------------------------
@common_router.callback_query(F.data == "promo_enter")
async def callback_promo_enter(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompts user to enter a promo code."""
    await state.set_state(UserPromoStates.waiting_for_promo_code)
    text = (
        "🎟 <b>Активация промокода</b>\n\n"
        "Отправьте ваш секретный промокод в ответном сообщении.\n\n"
        "⚠️ <b>Важные правила:</b>\n"
        "• Промокод чувствителен к регистру (заглавные и строчные буквы различаются).\n"
        "• Пробелы не допускаются.\n"
        "• После активации скидочного промокода у вас будет ровно <b>24 часа</b>, чтобы воспользоваться скидкой на 1 покупку."
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_promo_input_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@common_router.message(UserPromoStates.waiting_for_promo_code)
async def process_user_promo_input(message: Message, state: FSMContext) -> None:
    """Validates and processes user entered promo code."""
    raw_code = (message.text or "").strip()
    if not raw_code:
        await message.answer("⚠️ Пожалуйста, введите промокод текстом:")
        return

    if " " in raw_code or "\t" in raw_code or "\n" in raw_code:
        await message.answer(
            "❌ <b>Промокод не должен содержать пробелов!</b>\n\n"
            "Пожалуйста, скопируйте и отправьте код заново без пробелов:",
            reply_markup=get_promo_input_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    promo = await db.get_promo_code_by_code(raw_code)
    if not promo or not promo.get("is_active"):
        await message.answer(
            "❌ <b>Промокод не найден или отключён.</b>\n\n"
            "Убедитесь, что вы скопировали код в точности, включая регистр букв:",
            reply_markup=get_promo_input_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    # Check global expiration
    now = get_msk_now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    if promo["expires_at"] <= now_str:
        await state.clear()
        await message.answer(
            "❌ <b>Срок действия этого промокода истёк.</b>",
            reply_markup=get_profile_keyboard(),
            parse_mode="HTML",
        )
        return

    # Check activations limit
    if promo["current_activations"] >= promo["max_activations"]:
        await state.clear()
        await message.answer(
            "❌ <b>Лимит активаций этого промокода исчерпан.</b>",
            reply_markup=get_profile_keyboard(),
            parse_mode="HTML",
        )
        return

    user_id = message.from_user.id

    # Check if already used by user
    if await db.has_user_activated_promo(user_id, promo["id"]):
        await state.clear()
        await message.answer(
            "⚠️ <b>Вы уже активировали этот промокод ранее.</b>\n"
            "Каждый промокод можно применить только 1 раз на аккаунт.",
            reply_markup=get_profile_keyboard(),
            parse_mode="HTML",
        )
        return

    # If it's a discount promo code, check if user already has an active 24h discount
    if promo["promo_type"].startswith("discount"):
        active_disc = await db.get_user_active_discount(user_id)
        if active_disc:
            # Show replacement warning and ask confirmation
            await state.set_state(UserPromoStates.confirm_replace_discount)
            await state.update_data(candidate_code=promo["code"])

            old_data = active_disc.get("discount_data") or {}
            old_mode = old_data.get("discount_mode") or old_data.get("type", "fixed")
            old_code = active_disc.get("code")
            rem_str = active_disc.get("remaining_time_str", "несколько часов")

            if old_code:
                if old_mode == "fixed" and old_data.get("percent"):
                    cur_desc = f"промокод <code>{old_code}</code> (-{old_data['percent']}%)"
                else:
                    cur_desc = f"промокод <code>{old_code}</code>"
            else:
                if old_mode == "fixed" and old_data.get("percent"):
                    cur_desc = f"скидка {old_data['percent']}%"
                else:
                    cur_desc = "скидка на тарифы"

            warn_text = (
                "⚠️ <b>У вас уже есть активный промокод на скидку!</b>\n\n"
                f"Действующий: <b>{cur_desc}</b> <i>(осталось времени: {rem_str})</i>.\n\n"
                "Промокоды не суммируются. Если вы активируете новый промокод, "
                "то действие текущего промокода прекратится, а для нового начнётся "
                "<b>новый 24-часовой период</b> действия скидки на одну покупку.\n\n"
                f"Заменить текущий промокод на <code>{promo['code']}</code>?"
            )
            await message.answer(
                warn_text,
                reply_markup=get_promo_replace_keyboard(promo["code"]),
                parse_mode="HTML",
            )
            return

    # Normal activation (credits or first discount)
    success, status_code, data = await db.activate_promo_code_for_user(user_id, promo)
    await state.clear()

    if not success:
        if status_code == "already_used":
            await message.answer("⚠️ Вы уже активировали этот промокод.", reply_markup=get_profile_keyboard())
        elif status_code == "limit_reached":
            await message.answer("❌ Лимит активаций этого промокода исчерпан.", reply_markup=get_profile_keyboard())
        elif status_code == "expired":
            await message.answer("❌ Срок действия этого промокода истёк.", reply_markup=get_profile_keyboard())
        else:
            await message.answer("❌ Не удалось активировать промокод. Попробуйте позже.", reply_markup=get_profile_keyboard())
        return

    if promo["promo_type"] == "credits":
        user = await db.get_user(user_id)
        added = data.get("credits", 0)
        await message.answer(
            f"🎉 <b>Промокод успешно активирован!</b>\n\n"
            f"🎁 Вам начислено: <b>+{added} подарочных генераций</b>\n"
            f"💰 Всего генераций на балансе: <b>{user['total_balance']}</b>\n\n"
            "Приступайте к созданию новых треков прямо сейчас 🎧",
            reply_markup=get_profile_keyboard(),
            parse_mode="HTML",
        )
    else:
        ddata = data.get("reward_data") or {}
        dmode = ddata.get("discount_mode") or ddata.get("type", "fixed")
        if dmode == "fixed":
            disc_label = f"скидка {ddata.get('percent')}% на все пакеты"
        else:
            disc_label = f"промокод <code>{promo['code']}</code> (скидка на тарифы)"

        await message.answer(
            f"🎉 <b>Промокод «{promo['code']}» успешно активирован!</b>\n\n"
            f"🏷 <b>Ваша выгода:</b> {disc_label}\n"
            "⏱ <b>Время на оплату:</b> ровно <b>24 часа</b> с этого момента (на 1 покупку).\n\n"
            "Скидка уже применена к ценам в разделе пополнения баланса!",
            reply_markup=get_profile_keyboard(has_discount=True),
            parse_mode="HTML",
        )


@common_router.callback_query(F.data.startswith("promo_replace_confirm:"))
async def process_promo_replace_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """Replaces current active discount with candidate promo code."""
    code = callback.data.split(":", 1)[1]
    promo = await db.get_promo_code_by_code(code)

    if not promo or not promo.get("is_active"):
        await state.clear()
        await callback.message.edit_text(
            "❌ Промокод не найден или срок его действия истёк.",
            reply_markup=get_profile_keyboard(),
        )
        await callback.answer()
        return

    user_id = callback.from_user.id
    success, status_code, data = await db.replace_active_discount_with_promo(user_id, promo)
    await state.clear()

    if not success:
        await callback.message.edit_text(
            f"❌ Не удалось применить промокод ({status_code}).",
            reply_markup=get_profile_keyboard(),
        )
        await callback.answer()
        return

    ddata = data.get("reward_data") or {}
    dmode = ddata.get("discount_mode") or ddata.get("type", "fixed")
    if dmode == "fixed":
        disc_label = f"скидка {ddata.get('percent')}% на все пакеты"
    else:
        disc_label = f"промокод <code>{code}</code> (скидка на тарифы)"

    await callback.message.edit_text(
        f"🎉 <b>Промокод «{code}» успешно активирован!</b>\n\n"
        "Предыдущий промокод аннулирован.\n"
        f"🏷 <b>Ваша новая выгода:</b> {disc_label}\n"
        "⏱ <b>Время на оплату:</b> ровно <b>24 часа</b> с этого момента (на 1 покупку).\n\n"
        "Цены в разделе пополнения обновлены с учётом новой скидки!",
        reply_markup=get_profile_keyboard(has_discount=True),
        parse_mode="HTML",
    )
    await callback.answer("Новая скидка активирована!")


@common_router.callback_query(F.data == "promo_replace_cancel")
async def process_promo_replace_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Cancels replacement, keeping current discount."""
    await state.clear()
    await callback.message.edit_text(
        "✅ Действие отменено. Ваша текущая скидка сохранена и продолжает действовать.",
        reply_markup=get_profile_keyboard(has_discount=True),
    )
    await callback.answer("Текущая скидка сохранена")


@common_router.callback_query(F.data == "menu_referral")
@common_router.message(Command("ref"))
@common_router.message(Command("referral"))
@common_router.message(F.text.in_({"👥 Рефералка", "👥 Реферальная программа"}))
async def callback_referral(event: Message | CallbackQuery) -> None:
    user_id = event.from_user.id
    user = await db.get_user(user_id)
    ref_bal = user.get("referral_balance", 0.0) if user else 0.0
    stats = await db.get_user_stats(user_id)
    ref_count = stats["referrals_count"]
    tier_info = get_referral_tier(ref_count)

    bot_info = await event.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    if tier_info["next_tier"]:
        progress_text = (
            f"🎯 До уровня <b>{tier_info['next_tier']['title']} ({tier_info['next_tier']['percent']}%)</b> "
            f"осталось пригласить: <b>{tier_info['needed_for_next']}</b> чел."
        )
    else:
        progress_text = "👑 <b>Вы достигли максимального уровня партнёрской программы!</b>"

    tiers_table = format_referral_tiers_table(current_level=tier_info["level"])
    needed_for_full = round(1.0 - ref_bal, 2)

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        "Приглашайте друзей создавать музыку и получайте пожизненный процент "
        "генераций с каждого их пополнения баланса!\n\n"
        "📊 <b>Ваш партнёрский статус:</b>\n"
        f"• Приглашено друзей: <b>{ref_count}</b> чел.\n"
        f"• Текущий уровень: <b>{tier_info['title']} ({tier_info['percent']}%)</b>\n"
        f"• Реферальный баланс: <b>{ref_bal:g} / 1.0</b> "
        f"<i>(до перевода в подарочные: {needed_for_full:g})</i>\n"
        f"{progress_text}\n\n"
        "💡 <i>Дробные доли от покупок копятся на реферальном балансе. Как только сумма достигает 1.0, она автоматически переносится в ваши 🎁 Подарочные генерации!</i>\n\n"
        "🏆 <b>Уровни вознаграждения (от 2% до 20%):</b>\n"
        f"{tiers_table}\n\n"
        "🔗 <b>Ваша реферальная ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "<i>Отправьте ссылку другу. При первом переходе он закрепится за вами навсегда!</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_referral_keyboard(),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_referral_keyboard(),
            parse_mode="HTML",
        )


@common_router.callback_query(F.data == "menu_main")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    total_balance = user["total_balance"] if user else 0

    text = (
        f"👋 <b>Главное меню</b>\n\n"
        f"Бот для генерации музыки с помощью <b>нейросети</b> 🎧\n\n"
        f"💰 Ваш баланс: <b>{total_balance}</b> генераций\n\n"
        "Выберите действие внизу экрана или отправьте мне текстовое описание трека прямо в чат!"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
