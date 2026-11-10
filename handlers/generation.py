import asyncio
import html
import io
import logging
import re
from typing import Optional, List, Dict

import httpx
from aiogram import Router, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
)

from config import settings
from database.db import db
from keyboards.inline import (
    get_artists_keyboard,
    get_all_artists_keyboard,
    get_artist_by_id,
    find_artist_by_name,
    get_genres_keyboard,
    get_genre_by_id,
    get_mode_selection_keyboard,
    get_after_generation_keyboard,
    get_main_menu_keyboard,
    get_subscription_gate_keyboard,
)
from services.subscription import check_user_subscription
from services.treblo import (
    treblo_client,
    TrebloAPIError,
    TrebloCreditsError,
    TrebloTimeoutError,
)
from states.generation import GenerationStates

logger = logging.getLogger(__name__)
generation_router = Router()


def format_genres_display(genre_ids: List[str]) -> str:
    """Format list of genre IDs into human-readable string with emojis."""
    names = []
    for gid in genre_ids:
        g = get_genre_by_id(gid)
        if g:
            names.append(f"{g['emoji']} {g['name']}")
    return ", ".join(names) if names else "Не выбраны"


INTERJECTIONS = {
    "ой", "ой-ой", "да", "да-да", "е", "ее", "е-е", "йоу", "йо", "у", "у-у", "а", "ага",
    "ла", "ла-ла", "на", "на-на", "хей", "эй", "оу", "oh", "yeah", "yo", "hey", "ah",
    "intro", "outro", "verse", "chorus", "hook", "bridge", "skit",
}


def generate_track_title(
    lyrics: Optional[str] = None,
    prompt: Optional[str] = None,
    instrumental: bool = False,
    api_title: Optional[str] = None,
) -> str:
    """
    Generates a smart track title as Treblo / Suno does on their website:
    - If API returned title: use it.
    - If instrumental or no lyrics: 'Instrumental'
    - If lyrics exist: extracts hook from [Chorus] / [Hook] or first meaningful line
    """
    if api_title and isinstance(api_title, str) and api_title.strip():
        return api_title.strip().strip('"').strip('«»').strip("'")

    if instrumental or not lyrics or not lyrics.strip():
        return "Instrumental"

    clean_lyrics = lyrics.strip()
    lines = [line.strip() for line in clean_lyrics.splitlines() if line.strip()]

    # 1. Search for Chorus / Hook first
    chorus_lines = []
    in_chorus = False
    for line in lines:
        if re.match(r"^\[?(Chorus|Припев|Hook|Хук)\]?:?", line, re.IGNORECASE):
            in_chorus = True
            continue
        if in_chorus:
            if line.startswith("[") or (line.endswith(":") and any(sec in line.lower() for sec in ["куплет", "verse", "bridge", "бридж", "outro", "аутро"])):
                break
            chorus_lines.append(line)

    candidate = None
    if chorus_lines:
        for cl in chorus_lines:
            cleaned = re.sub(r"[^\w\s-]", "", cl).strip()
            words = cleaned.split()
            if len(words) >= 1:
                non_interjection = [w for w in words if w.lower() not in INTERJECTIONS]
                if non_interjection:
                    candidate = cl
                    break

    # 2. If no chorus hook found, search meaningful lines from start
    if not candidate:
        for line in lines:
            if line.startswith("[") and line.endswith("]"):
                continue
            if line.endswith(":") and any(sec in line.lower() for sec in ["интро", "вступление", "куплет", "verse", "intro"]):
                continue
            cleaned = re.sub(r"[^\w\s-]", "", line).strip()
            words = cleaned.split()
            if len(words) >= 1:
                non_interjection = [w for w in words if w.lower() not in INTERJECTIONS]
                if non_interjection:
                    candidate = line
                    break

    # 3. Fallback to prompt if no candidate found
    if not candidate:
        if prompt and prompt != "Инструментальный трек":
            p = prompt.strip()
            if " про " in p.lower():
                candidate = p.split(" про ", 1)[1]
            elif " о " in p.lower():
                candidate = p.split(" о ", 1)[1]
            else:
                candidate = p
        else:
            return "Instrumental"

    # Clean candidate into a title
    title = candidate.strip().strip('"').strip('«»').strip("'").strip("[](){}.,!?:;")
    title = re.sub(r"[,!?:;]+$", "", title).strip()

    if len(title) > 35:
        title = title[:35].rsplit(" ", 1)[0]

    if title:
        title = title[0].upper() + title[1:]

    return title or "Instrumental"


# ---------------------------------------------------------
# STEP 1: Artist Selection
# ---------------------------------------------------------
@generation_router.message(Command("create"))
@generation_router.message(F.text.in_({"🎵 Создать музыку", "🎵 Создать трек"}))
@generation_router.callback_query(F.data == "menu_create")
async def start_creation(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Step 1: Choose artist reference or skip."""
    user_id = event.from_user.id
    bot = event.bot

    # Subscription check
    is_subscribed, ch_name, ch_url = await check_user_subscription(bot, user_id)
    if not is_subscribed:
        gate_text = (
            "🔒 <b>Доступ ограничен</b>\n\n"
            "Для создания музыки необходимо подписаться на наш официальный Telegram-канал.\n\n"
            "Подпишись на канал и нажми кнопку <b>«✅ Проверить подписку»</b>, чтобы продолжить 👇"
        )
        url_to_use = ch_url or (f"https://t.me/{ch_name.lstrip('@')}" if ch_name and not ch_name.startswith("-") else "")
        kb = get_subscription_gate_keyboard(url_to_use)
        if isinstance(event, CallbackQuery):
            await event.answer()
            await event.message.answer(gate_text, reply_markup=kb, parse_mode="HTML")
        else:
            await event.answer(gate_text, reply_markup=kb, parse_mode="HTML")
        return

    await state.clear()
    await state.set_state(GenerationStates.waiting_for_artist)

    text = (
        "🎤 <b>Шаг 1 — артист-референс</b>\n\n"
        "Выбери артиста, в стиле которого сделать трек. Кнопки — те, что точно есть в базе.\n"
        "Можно вписать своего сообщением — если голосовой модели нет, бот подскажет.\n\n"
        "Или «⏭ Без артиста» — тогда стиль зададут только жанры."
    )

    popular_artists = await db.get_popular_artists()
    kb = get_artists_keyboard(popular_artists)

    if isinstance(event, CallbackQuery):
        await event.answer()
        await event.message.answer(
            text,
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await event.answer(
            text,
            reply_markup=kb,
            parse_mode="HTML",
        )


@generation_router.callback_query(F.data == "sub_check_verify")
async def verify_user_subscription(callback: CallbackQuery, state: FSMContext) -> None:
    """Re-checks user subscription when user clicks '✅ Проверить подписку' button."""
    is_subscribed, ch_name, ch_url = await check_user_subscription(callback.bot, callback.from_user.id)
    if not is_subscribed:
        await callback.answer(
            "❌ Вы ещё не подписались на канал! Пожалуйста, подпишитесь и попробуйте снова.",
            show_alert=True,
        )
        return

    await callback.answer("✅ Подписка подтверждена!", show_alert=False)

    await state.clear()
    await state.set_state(GenerationStates.waiting_for_artist)

    text = (
        "🎤 <b>Шаг 1 — артист-референс</b>\n\n"
        "Выбери артиста, в стиле которого сделать трек. Кнопки — те, что точно есть в базе.\n"
        "Можно вписать своего сообщением — если голосовой модели нет, бот подскажет.\n\n"
        "Или «⏭ Без артиста» — тогда стиль зададут только жанры."
    )

    popular_artists = await db.get_popular_artists()
    kb = get_artists_keyboard(popular_artists)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")


@generation_router.callback_query(
    GenerationStates.waiting_for_artist, F.data == "gen_artists_all"
)
async def show_all_artists(callback: CallbackQuery) -> None:
    text = (
        "📋 <b>Все доступные артисты в базе:</b>\n\n"
        "Выбери исполнителя из расширенного списка ниже или отправь его имя сообщением в чат 👇"
    )
    all_artists = await db.get_all_artists()
    await callback.message.edit_text(
        text,
        reply_markup=get_all_artists_keyboard(all_artists),
        parse_mode="HTML",
    )
    await callback.answer()


@generation_router.callback_query(
    GenerationStates.waiting_for_artist, F.data == "gen_artists_popular"
)
async def show_popular_artists(callback: CallbackQuery) -> None:
    text = (
        "🎤 <b>Шаг 1 — артист-референс</b>\n\n"
        "Выбери артиста, в стиле которого сделать трек. Кнопки — те, что точно есть в базе.\n"
        "Можно вписать своего сообщением — если голосовой модели нет, бот подскажет.\n\n"
        "Или «⏭ Без артиста» — тогда стиль зададут только жанры."
    )
    popular_artists = await db.get_popular_artists()
    await callback.message.edit_text(
        text,
        reply_markup=get_artists_keyboard(popular_artists),
        parse_mode="HTML",
    )
    await callback.answer()


@generation_router.message(GenerationStates.waiting_for_artist, F.text, ~F.text.startswith("/"))
async def process_artist_text_input(message: Message, state: FSMContext) -> None:
    raw_query = message.text.strip()
    artist = await db.find_artist_by_name(raw_query)
    if not artist:
        artist = find_artist_by_name(raw_query)

    if artist:
        await state.update_data(
            artist_id=artist["id"],
            artist_name=artist["name"],
            artist_style=artist["style"],
        )

        # Short confirmation message of user's choice
        await message.answer(f"🎙 Артист: <b>{artist['name']}</b>", parse_mode="HTML")

        # Move to Step 2 (Genres) as a new message without accumulated summaries
        await state.set_state(GenerationStates.waiting_for_genres)
        data = await state.get_data()
        selected_genres = data.get("selected_genres", [])

        text = (
            "🎧 <b>Шаг 2 — выбор жанров</b>\n\n"
            "Выбери минимум 2 жанра для создания уникального звучания.\n"
            "<i>Нажимай на кнопки, чтобы отметить нужные жанры:</i>"
        )
        await message.answer(
            text,
            reply_markup=get_genres_keyboard(selected_genres),
            parse_mode="HTML",
        )
    else:
        text = (
            f"⚠️ Голосовой модели для <b>«{raw_query}»</b> пока нет в базе.\n\n"
            "Выбери артиста кнопкой выше или нажми <b>«⏭ Без артиста (только жанры)»</b>."
        )
        await message.answer(text, parse_mode="HTML")


@generation_router.callback_query(
    GenerationStates.waiting_for_artist, F.data.startswith("gen_artist:")
)
async def process_artist_selection(callback: CallbackQuery, state: FSMContext) -> None:
    artist_id = callback.data.split(":")[1]

    if artist_id == "none":
        await state.update_data(
            artist_id=None,
            artist_name=None,
            artist_style=None,
        )
        confirm_text = "🎙 Артист: <b>Без артиста (только жанры)</b>"
    else:
        artist = await db.get_artist_by_id(artist_id)
        if not artist:
            artist = get_artist_by_id(artist_id)

        if artist:
            await state.update_data(
                artist_id=artist_id,
                artist_name=artist["name"],
                artist_style=artist["style"],
            )
            confirm_text = f"🎙 Артист: <b>{artist['name']}</b>"
        else:
            await state.update_data(
                artist_id=None,
                artist_name=None,
                artist_style=None,
            )
            confirm_text = "🎙 Артист: <b>Без артиста</b>"

    await callback.answer()

    # Short confirmation message of user's choice
    await callback.message.answer(confirm_text, parse_mode="HTML")

    # Move to Step 2 (Genres) as a NEW message without accumulated summaries
    await state.set_state(GenerationStates.waiting_for_genres)
    data = await state.get_data()
    selected_genres = data.get("selected_genres", [])

    text = (
        "🎧 <b>Шаг 2 — выбор жанров</b>\n\n"
        "Выбери минимум 2 жанра для создания уникального звучания.\n"
        "<i>Нажимай на кнопки, чтобы отметить нужные жанры:</i>"
    )

    await callback.message.answer(
        text,
        reply_markup=get_genres_keyboard(selected_genres),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# STEP 2: Genres Multi-select
# ---------------------------------------------------------
@generation_router.callback_query(
    GenerationStates.waiting_for_genres, F.data.startswith("gen_genre_toggle:")
)
async def process_genre_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    genre_id = callback.data.split(":")[1]
    data = await state.get_data()
    selected_genres = list(data.get("selected_genres", []))

    if genre_id in selected_genres:
        selected_genres.remove(genre_id)
    else:
        selected_genres.append(genre_id)

    await state.update_data(selected_genres=selected_genres)

    genres_text = format_genres_display(selected_genres)
    selected_status = (
        f"Выбрано: <b>{genres_text}</b> ({len(selected_genres)})"
        if selected_genres
        else "Выбрано: <i>пока ничего не выбрано</i>"
    )

    text = (
        "🎧 <b>Шаг 2 — выбор жанров</b>\n\n"
        "Выбери минимум 2 жанра для создания уникального звучания.\n\n"
        f"{selected_status}\n\n"
        "<i>Нажимай на кнопки, чтобы отметить или снять жанры:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_genres_keyboard(selected_genres),
        parse_mode="HTML",
    )
    await callback.answer()


@generation_router.callback_query(
    GenerationStates.waiting_for_genres, F.data == "gen_genres_need_more"
)
async def process_genres_need_more(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    count = len(data.get("selected_genres", []))
    await callback.answer(
        f"⚠️ Пожалуйста, выберите минимум 2 жанра! Сейчас выбрано: {count}",
        show_alert=True,
    )


@generation_router.callback_query(
    GenerationStates.waiting_for_genres, F.data == "gen_genres_confirm"
)
async def process_genres_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected_genres = data.get("selected_genres", [])

    if len(selected_genres) < 2:
        await callback.answer("⚠️ Выберите минимум 2 жанра!", show_alert=True)
        return

    await callback.answer()

    # Short confirmation message of user's choice
    genres_display = format_genres_display(selected_genres)
    await callback.message.answer(f"🎧 Жанры: <b>{genres_display}</b>", parse_mode="HTML")

    # Move to Step 3 (Format / Mode) as a NEW message without accumulated summaries
    await state.set_state(GenerationStates.waiting_for_mode)

    text = (
        "🎤 <b>Шаг 3 — текст песни (Lyrics)</b>\n\n"
        "Выбери режим:"
    )

    await callback.message.answer(
        text,
        reply_markup=get_mode_selection_keyboard(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# STEP 3: Mode Selection (Vocal AI / Instrumental / Custom Lyrics)
# ---------------------------------------------------------
@generation_router.callback_query(
    GenerationStates.waiting_for_mode, F.data.startswith("gen_mode:")
)
async def process_mode_selection(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]
    data = await state.get_data()
    existing_prompt = data.get("prompt")
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    selected_genres = data.get("selected_genres", [])

    await callback.answer()

    if mode == "vocal_ai":
        # Short confirmation message of user's choice
        await callback.message.answer("🤖 Режим: <b>Auto (ИИ напишет текст)</b>", parse_mode="HTML")

        # Automatic generation: ONLY here ask for idea if not already provided
        await state.update_data(mode="vocal_ai", instrumental=False)

        if existing_prompt:
            # Prompt already provided (e.g. via quick message), launch immediately!
            await state.clear()
            await execute_generation(
                bot=callback.bot,
                chat_id=callback.message.chat.id,
                user_id=callback.from_user.id,
                prompt=existing_prompt,
                instrumental=False,
                artist_name=artist_name,
                artist_style=artist_style,
                selected_genre_ids=selected_genres,
                lyrics=None,
            )
            return

        # Ask for idea (Step 4) without accumulated summaries
        await state.set_state(GenerationStates.waiting_for_prompt)
        text = (
            "✍️ <b>Шаг 4</b>\n\n"
            "✍️ Опиши, о чём и в каком стиле написать текст.\n"
            "Например: «напиши текст в стиле скриптонита про ночной город»"
        )
        await callback.message.answer(
            text,
            parse_mode="HTML",
        )

    elif mode == "instrumental":
        # Short confirmation message of user's choice
        await callback.message.answer("🎸 Режим: <b>Инструментал (без вокала)</b>", parse_mode="HTML")

        # Instrumental: NO idea needed! Launch immediately!
        await state.clear()
        prompt = existing_prompt or "Инструментальный трек"
        await execute_generation(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            prompt=prompt,
            instrumental=True,
            artist_name=artist_name,
            artist_style=artist_style,
            selected_genre_ids=selected_genres,
            lyrics=None,
        )

    elif mode == "custom_lyrics":
        # Short confirmation message of user's choice
        await callback.message.answer("✍️ Режим: <b>Свой текст</b>", parse_mode="HTML")

        # Custom lyrics: NO idea needed! Just ask for lyrics text!
        await state.update_data(mode="custom_lyrics", instrumental=False)
        await state.set_state(GenerationStates.waiting_for_lyrics)

        text = (
            "✍️ <b>Текст песни</b>\n\n"
            "Отправь текст песни (стихи, куплеты, припев) сообщением в чат 👇"
        )
        await callback.message.answer(
            text,
            parse_mode="HTML",
        )


# ---------------------------------------------------------
# STEP: Lyrics Input (For Custom Lyrics Mode - No Idea Needed!)
# ---------------------------------------------------------
@generation_router.message(GenerationStates.waiting_for_lyrics)
async def process_lyrics(message: Message, state: FSMContext) -> None:
    lyrics_text = message.text.strip()
    if not lyrics_text:
        await message.answer("Пожалуйста, отправьте текст песни сообщением в чат.")
        return

    if len(lyrics_text) < 5:
        await message.answer(
            "Текст песни слишком короткий. Отправьте хотя бы несколько строк (куплет или припев)."
        )
        return

    # Short confirmation message of user's choice
    await message.answer("✍️ <b>Текст песни принят!</b>", parse_mode="HTML")

    data = await state.get_data()
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    selected_genres = data.get("selected_genres", [])
    existing_prompt = data.get("prompt")

    # Use existing prompt or first line of lyrics as prompt/title
    first_line = ""
    for line in lyrics_text.splitlines():
        clean_line = line.strip()
        if clean_line:
            first_line = clean_line[:35]
            break
    prompt = existing_prompt or first_line or "Песня на свой текст"

    await state.clear()

    # Launch generation immediately! No idea step!
    await execute_generation(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        prompt=prompt,
        instrumental=False,
        artist_name=artist_name,
        artist_style=artist_style,
        selected_genre_ids=selected_genres,
        lyrics=lyrics_text,
    )


# ---------------------------------------------------------
# STEP 4: Prompt Text Input (Only for Vocal AI Mode)
# ---------------------------------------------------------
@generation_router.message(GenerationStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext) -> None:
    prompt_text = message.text.strip()
    if not prompt_text:
        await message.answer("Пожалуйста, отправьте текстовое описание трека.")
        return

    if len(prompt_text) < 3:
        await message.answer(
            "Слишком короткое описание. Опишите чуть подробнее (хотя бы настроение или сюжет)."
        )
        return

    # Short confirmation message of user's choice
    await message.answer(f"🎵 Идея: <i>«{prompt_text}»</i>", parse_mode="HTML")

    data = await state.get_data()
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    selected_genres = data.get("selected_genres", [])

    await state.clear()

    await execute_generation(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        prompt=prompt_text,
        instrumental=False,
        artist_name=artist_name,
        artist_style=artist_style,
        selected_genre_ids=selected_genres,
        lyrics=None,
    )


# Quick prompt handler: if user sends text directly in idle state (no FSM state)
@generation_router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_quick_prompt(message: Message, state: FSMContext) -> None:
    """Triggered when user sends free text without active state."""
    prompt_text = message.text.strip()
    if len(prompt_text) < 3:
        return

    # Subscription check
    is_subscribed, ch_name, ch_url = await check_user_subscription(message.bot, message.from_user.id)
    if not is_subscribed:
        gate_text = (
            "🔒 <b>Доступ ограничен</b>\n\n"
            "Для создания музыки необходимо подписаться на наш официальный Telegram-канал.\n\n"
            "Подпишись на канал и нажми кнопку <b>«✅ Проверить подписку»</b>, чтобы продолжить 👇"
        )
        url_to_use = ch_url or (f"https://t.me/{ch_name.lstrip('@')}" if ch_name and not ch_name.startswith("-") else "")
        kb = get_subscription_gate_keyboard(url_to_use)
        await message.answer(gate_text, reply_markup=kb, parse_mode="HTML")
        return

    await state.clear()
    await state.update_data(prompt=prompt_text)
    await state.set_state(GenerationStates.waiting_for_artist)

    # Short confirmation message of user's quick prompt
    await message.answer(f"🎵 Идея: <i>«{html.escape(prompt_text)}»</i>", parse_mode="HTML")

    text = (
        "🎤 <b>Шаг 1 — артист-референс</b>\n\n"
        "Выбери артиста, в стиле которого сделать трек. Кнопки — те, что точно есть в базе.\n"
        "Можно вписать своего сообщением — если голосовой модели нет, бот подскажет.\n\n"
        "Или «⏭ Без артиста» — тогда стиль зададут только жанры."
    )

    popular_artists = await db.get_popular_artists()
    await message.answer(
        text,
        reply_markup=get_artists_keyboard(popular_artists),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# EXECUTION: Treblo Melodia v3 Pipeline
# ---------------------------------------------------------
async def execute_generation(
    bot: Bot,
    chat_id: int,
    user_id: int,
    prompt: str,
    instrumental: bool,
    artist_name: Optional[str] = None,
    artist_style: Optional[str] = None,
    selected_genre_ids: Optional[List[str]] = None,
    lyrics: Optional[str] = None,
) -> None:
    """Executes the full music generation pipeline with Treblo Melodia v3 API."""
    user = await db.get_user(user_id)
    if not user:
        user = await db.get_or_create_user(user_id)

    # Check and deduct balance (gifts first, then paid)
    cost = settings.generation_cost
    deducted_from = await db.consume_generation_credit(user_id, cost=cost)
    if not deducted_from:
        total = user.get("total_balance", 0)
        paid = user.get("paid_balance", 0)
        gift = user.get("gift_balance", 0)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ <b>Недостаточно генераций на балансе!</b>\n\n"
                f"У вас осталось: <b>{total}</b> (Платные: {paid}, Подарочные: {gift})\n"
                f"Стоимость создания: <b>{cost}</b>\n\n"
                "Пополните баланс в профиле или приглашайте друзей по реферальной программе."
            ),
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    mode_label = (
        "🎸 Инструментал (без вокала)"
        if instrumental
        else ("✍️ Свой текст" if lyrics else "🤖 Auto (ИИ текст)")
    )

    # Resolve genre objects
    genre_objs = []
    if selected_genre_ids:
        for gid in selected_genre_ids:
            g = get_genre_by_id(gid)
            if g:
                genre_objs.append(g)

    genre_names_str = (
        ", ".join([f"{g['emoji']} {g['name']}" for g in genre_objs])
        if genre_objs
        else "Разнообразный"
    )

    status_lines = [
        "🚀 <b>Запуск генерации...</b>\n",
    ]
    if instrumental and prompt == "Инструментальный трек":
        pass
    elif lyrics:
        status_lines.append(f"📜 <b>Текст:</b> <i>«{html.escape(prompt)}»</i>")
    else:
        status_lines.append(f"🎵 <b>Идея:</b> <i>{html.escape(prompt)}</i>")

    if artist_name:
        status_lines.append(f"🎙 <b>Референс:</b> {html.escape(artist_name)}")
    status_lines.append(f"🎧 <b>Жанры:</b> {genre_names_str}")
    status_lines.append(f"⚙️ <b>Режим:</b> {mode_label}\n")
    status_lines.append("⏳ Отправляем задачу в нейросеть...")

    status_msg = await bot.send_message(
        chat_id=chat_id,
        text="\n".join(status_lines),
        parse_mode="HTML",
    )

    task_id = None
    try:
        # Build tags for API
        tags = [g["tag"] for g in genre_objs]
        if artist_name:
            tags.append(artist_name.lower().replace("&", "").strip())

        # Compile rich descriptive prompt for Treblo
        genre_tags_str = ", ".join([g["name"] for g in genre_objs])
        artist_clause = (
            f"в стиле {artist_name} ({artist_style}), "
            if artist_name and artist_style
            else (f"в стиле {artist_name}, " if artist_name else "")
        )
        full_prompt = f"Жанры: {genre_tags_str}. {artist_clause}{prompt}".strip()

        # Create task in Treblo
        task_id = await treblo_client.create_generation(
            prompt=full_prompt,
            instrumental=instrumental,
            lyrics=lyrics,
            tags=tags if tags else None,
        )

        await db.record_generation(
            user_id=user_id,
            task_id=task_id,
            prompt=prompt,
            artist=artist_name,
            genres=genre_names_str,
            instrumental=instrumental,
            lyrics=lyrics,
        )

        # Status update callback for polling
        async def on_status_update(new_status: str):
            try:
                if new_status in ("GENERATING", "PROCESSING"):
                    update_lines = [
                        "🎵 <b>Генерация в процессе...</b>\n",
                    ]
                    if instrumental and prompt == "Инструментальный трек":
                        pass
                    elif lyrics:
                        update_lines.append(f"Текст: <i>«{html.escape(prompt)}»</i>")
                    else:
                        update_lines.append(f"Идея: <i>«{html.escape(prompt)}»</i>")

                    if artist_name:
                        update_lines.append(f"Референс: {html.escape(artist_name)}")
                    update_lines.append(f"Жанры: {genre_names_str}")
                    update_lines.append(f"Режим: {mode_label}\n")
                    update_lines.append("⚡ Нейросеть сочиняет трек и аранжировку... (1-2 мин)")
                    await status_msg.edit_text(
                        "\n".join(update_lines),
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.debug("Failed to edit status message: %s", e)

        # Poll Treblo until complete
        generation_result = await treblo_client.poll_until_complete(
            task_id=task_id,
            status_callback=on_status_update,
        )

        audio_url = (
            generation_result.get("audio_url")
            or (generation_result.get("song_paths") and generation_result["song_paths"][0])
            or (generation_result.get("audio_paths") and generation_result["audio_paths"][0])
        )
        if not audio_url:
            raise TrebloAPIError("Не удалось получить ссылку на аудиофайл.")

        image_url = (
            generation_result.get("image_url")
            or generation_result.get("image_path")
            or generation_result.get("cover_url")
            or (generation_result.get("image_paths") and generation_result["image_paths"][0])
        )
        duration = generation_result.get("duration")

        await db.update_generation_status(
            task_id=task_id,
            status="SUCCESS",
            audio_url=audio_url,
            duration=float(duration) if duration else None,
        )

        # Download audio and thumbnail
        try:
            await status_msg.edit_text("✨ Трек готов! Загружаю аудио в Telegram...")
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=60.0) as http_client:
            audio_resp = await http_client.get(audio_url)
            audio_resp.raise_for_status()
            audio_bytes = audio_resp.content

            thumb_bytes = None
            if image_url:
                try:
                    img_resp = await http_client.get(image_url)
                    if img_resp.status_code == 200:
                        thumb_bytes = img_resp.content
                except Exception as img_err:
                    logger.warning("Failed to fetch thumbnail: %s", img_err)

        # Determine track title and authorship
        gen_lyrics = generation_result.get("lyrics") or lyrics
        api_title = generation_result.get("title")

        track_title = generate_track_title(
            lyrics=gen_lyrics,
            prompt=prompt,
            instrumental=instrumental,
            api_title=api_title,
        )

        performer_display = f"{artist_name} & Trivela" if artist_name else "Trivela"
        display_caption = f"🎶 <b>{html.escape(performer_display)} | {html.escape(track_title)}</b>"

        safe_performer = re.sub(r'[\\/*?:"<>|]', "", performer_display).strip()
        safe_title = re.sub(r'[\\/*?:"<>|]', "", track_title).strip()
        file_name = f"{safe_performer} - {safe_title}.mp3" if safe_title else f"{safe_performer}.mp3"

        audio_file = BufferedInputFile(
            audio_bytes, filename=file_name
        )
        thumb_file = (
            BufferedInputFile(thumb_bytes, filename="cover.webp")
            if thumb_bytes
            else None
        )

        await bot.send_audio(
            chat_id=chat_id,
            audio=audio_file,
            thumbnail=thumb_file,
            title=track_title,
            performer=performer_display,
            duration=int(duration) if duration else None,
            caption=display_caption,
            reply_markup=get_after_generation_keyboard(),
            parse_mode="HTML",
        )

        # Delete waiting message
        try:
            await status_msg.delete()
        except Exception:
            pass

    except TrebloCreditsError as e:
        logger.error("Treblo credits error: %s", e)
        # Refund credit
        if deducted_from:
            await db.refund_generation_credit(user_id, balance_type=deducted_from, cost=cost)
        if task_id:
            await db.update_generation_status(task_id, "FAILURE")

        # Alert admins
        try:
            from services.admin_alerts import notify_admins
            await notify_admins(
                bot,
                "🚨 <b>КРИТИЧЕСКИЙ АЛЕРТ: Закончились кредиты API генераций!</b>\n\n"
                f"Пользователь <code>{user_id}</code> не смог сгенерировать трек.\n"
                "Срочно пополните баланс в кабинете провайдера API.",
            )
        except Exception:
            pass

        await status_msg.edit_text(
            "⚠️ <b>Сервис временно перегружен:</b> "
            "Пожалуйста, повторите попытку чуть позже или обратитесь к администратору.\nВаш баланс не списан.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )

    except TrebloTimeoutError as e:
        logger.error("Generation timeout: %s", e)
        # Refund credit
        if deducted_from:
            await db.refund_generation_credit(user_id, balance_type=deducted_from, cost=cost)
        if task_id:
            await db.update_generation_status(task_id, "FAILURE")
        await status_msg.edit_text(
            "⏱ <b>Время ожидания трека истекло.</b>\n"
            "Сервер перегружен или обрабатывает задачу слишком долго.\n"
            "Ваш баланс не списан, попробуйте повторить позже.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )

    except Exception as e:
        logger.exception("Unexpected generation error: %s", e)
        # Refund credit
        if deducted_from:
            await db.refund_generation_credit(user_id, balance_type=deducted_from, cost=cost)
        if task_id:
            await db.update_generation_status(task_id, "FAILURE")
        await status_msg.edit_text(
            "😔 <b>Не удалось создать трек</b>\n\n"
            "Во время генерации произошла ошибка на стороне нейросети.\n"
            "Потраченная попытка возвращена на ваш баланс. Попробуйте ещё раз или выберите другой стиль.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )
