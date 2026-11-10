import logging
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from database.db import db
from keyboards.inline import (
    get_main_menu_keyboard,
    get_profile_keyboard,
)

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
        f"💰 Ваш баланс: <b>{user['balance']}</b> генераций\n\n"
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
        "📖 <b>Как создать идеальный трек:</b>\n\n"
        "1️⃣ Нажмите <b>«🎵 Создать музыку»</b> или просто напишите описание песни в чат.\n"
        "2️⃣ Укажите жанр, инструменты, темп и настроение трека.\n"
        "3️⃣ Выберите режим:\n"
        "   • <b>С вокалом (AI текст):</b> нейросеть сама сочинит слова песни.\n"
        "   • <b>Без слов:</b> чистая музыка/минусовка.\n"
        "   • <b>Свой текст:</b> пришлите свои стихи или куплеты.\n\n"
        "⏱ Генерация обычно занимает <b>от 1 до 2 минут</b>.\n"
        "После завершения вы получите готовый MP3 файл!"
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            help_text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            help_text,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )


@common_router.callback_query(F.data == "menu_examples")
async def callback_examples(callback: CallbackQuery) -> None:
    examples_text = (
        "💡 <b>Примеры классных промтов для музыки:</b>\n\n"
        "🎸 <i>«Энергичный поп-рок 2000-х с драйвовыми гитарами и мощным припевом про путешествие к морю»</i>\n\n"
        "🎧 <i>«Chill lofi hip-hop beat with warm rhodes piano, vinyl crackle and smooth bass, relaxing study vibe»</i>\n\n"
        "⚡ <i>«Агрессивный phonk с перегруженным 808 басом, ковбеллом и темным ночным настроением дрифта»</i>\n\n"
        "🌌 <i>«Кинематографичный оркестровый саундтрек в стиле Hans Zimmer с глубокими струнными и эпическими барабанами»</i>\n\n"
        "Скопируйте любой пример или придумайте свой!"
    )
    await callback.message.edit_text(
        examples_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


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
    bot_info = await event.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        f"👤 <b>Ваш профиль:</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"💰 Баланс: <b>{user['balance']}</b> генераций\n"
        f"🎵 Всего создано треков: <b>{stats['total_generations']}</b>\n"
        f"👥 Приглашено друзей: <b>{stats['referrals_count']}</b>\n\n"
        f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>"
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
async def callback_referral(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"

    text = (
        "👥 <b>Реферальная программа</b>\n\n"
        "Приглашайте друзей создавать музыку в боте!\n\n"
        "🎁 <b>Условия (в разработке):</b>\n"
        "• За каждого друга вы получаете бонусные генерации\n"
        "• Процент от пополнений баланса вашими рефералами\n\n"
        f"🔗 <b>Ваша персональная ссылка:</b>\n<code>{ref_link}</code>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_profile_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@common_router.callback_query(F.data == "menu_topup")
async def callback_topup(callback: CallbackQuery) -> None:
    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        "Модуль платежной системы находится в процессе подключения.\n"
        "Скоро здесь будет доступна оплата через Telegram Stars, банковские карты и криптовалюту!"
    )
    await callback.answer("Модуль платежей скоро появится!", show_alert=True)
    await callback.message.edit_text(
        text,
        reply_markup=get_profile_keyboard(),
        parse_mode="HTML",
    )
