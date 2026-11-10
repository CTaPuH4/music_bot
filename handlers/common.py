import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database.db import db
from keyboards.inline import (
    get_main_menu_keyboard,
    get_profile_keyboard,
    get_referral_keyboard,
    get_help_keyboard,
)
from services.referral import get_referral_tier, format_referral_tiers_table

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

    welcome_text = (
        f"👋 <b>Привет, {first_name or 'друг'}!</b>\n\n"
        f"Я бот для генерации полноценной музыки с помощью <b>Treblo Melodia v3 API</b> 🎧\n\n"
        f"✨ <b>Что я умею:</b>\n"
        f"• Создавать музыку любых жанров по текстовому описанию (промту)\n"
        f"• Генерировать песни с вокалом и AI-стихами\n"
        f"• Писать инструментальные треки без слов\n"
        f"• Записывать треки с вашим собственным текстом\n\n"
        f"💰 Ваш баланс: <b>{user['total_balance']}</b> генераций\n\n"
        f"Нажмите кнопку ниже или отправьте мне текстовое описание трека прямо в чат!"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML",
    )


@common_router.callback_query(F.data == "menu_help")
@common_router.message(Command("help"))
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
        "3️⃣ <b>Идея и тема песни:</b>\n"
        "Опишите настроение, сюжет, тему или инструменты (например: <i>«Ночной неоновый город, воспоминания о лете, глубокий бас»</i>).\n\n"
        "4️⃣ <b>Формат вокала:</b>\n"
        "• <b>С вокалом (AI текст):</b> нейросеть сама сочинит стихи и исполнит песню.\n"
        "• <b>Без слов:</b> чистая инструментальная минусовка.\n"
        "• <b>Свой текст:</b> загрузите свои стихи или куплеты.\n\n"
        "⏱ <b>Время ожидания:</b> 1–2 минуты. Бот пришлёт готовый MP3 файл с обложкой.\n\n"
        "💡 <i>На каждом шаге доступна кнопка «◀️ Назад», чтобы скорректировать выбор.</i>"
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
async def show_profile(event: Message | CallbackQuery) -> None:
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

    text = (
        f"👤 <b>Ваш профиль:</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        f"💰 <b>Всего генераций:</b> <b>{total}</b>\n"
        f"├── 💳 Платные: <b>{paid}</b>\n"
        f"└── 🎁 Подарочные: <b>{gift}</b>\n\n"
        f"🎵 Всего создано треков: <b>{stats['total_generations']}</b>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_profile_keyboard(),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_profile_keyboard(),
            parse_mode="HTML",
        )


@common_router.callback_query(F.data == "menu_referral")
@common_router.message(Command("ref"))
@common_router.message(Command("referral"))
async def callback_referral(event: Message | CallbackQuery) -> None:
    user_id = event.from_user.id
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

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        "Приглашайте друзей создавать музыку и получайте пожизненный процент "
        "подарочных генераций с каждого их пополнения баланса!\n\n"
        "📊 <b>Ваш партнёрский статус:</b>\n"
        f"• Приглашено друзей: <b>{ref_count}</b> чел.\n"
        f"• Текущий уровень: <b>{tier_info['title']} ({tier_info['percent']}%)</b>\n"
        f"{progress_text}\n\n"
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
        f"Бот для генерации музыки с помощью <b>Treblo Melodia v3</b> 🎧\n\n"
        f"💰 Ваш баланс: <b>{total_balance}</b> генераций\n\n"
        "Выберите действие ниже или отправьте мне текстовое описание трека прямо в чат!"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()
