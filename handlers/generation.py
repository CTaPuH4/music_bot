import asyncio
import io
import logging
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
    get_artist_by_id,
    get_genres_keyboard,
    get_genre_by_id,
    get_prompt_input_keyboard,
    get_mode_selection_keyboard,
    get_lyrics_input_keyboard,
    get_cancel_keyboard,
    get_after_generation_keyboard,
    get_main_menu_keyboard,
)
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


# ---------------------------------------------------------
# STEP 1: Artist Selection
# ---------------------------------------------------------
@generation_router.message(Command("create"))
@generation_router.callback_query(F.data == "menu_create")
async def start_creation(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Step 1: Choose artist reference or skip."""
    await state.clear()
    await state.set_state(GenerationStates.waiting_for_artist)

    text = (
        "🎙 <b>Шаг 1 из 4: Выберите артиста-референс</b>\n\n"
        "Выберите исполнителя, чей стиль и звучание послужат ориентиром для вашего трека, "
        "или нажмите <b>«Без артиста»</b> для своего уникального стиля:"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(
            text,
            reply_markup=get_artists_keyboard(),
            parse_mode="HTML",
        )
        await event.answer()
    else:
        await event.answer(
            text,
            reply_markup=get_artists_keyboard(),
            parse_mode="HTML",
        )


@generation_router.callback_query(F.data == "gen_cancel")
async def cancel_creation(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "❌ Создание трека отменено. Вы в главном меню.",
        reply_markup=get_main_menu_keyboard(),
    )
    await callback.answer()


# ---------------------------------------------------------
# STEP BACK NAVIGATION
# ---------------------------------------------------------
@generation_router.callback_query(F.data == "gen_back:to_artist")
async def step_back_to_artist(callback: CallbackQuery, state: FSMContext) -> None:
    """Step back from genre selection to artist selection."""
    await state.set_state(GenerationStates.waiting_for_artist)
    text = (
        "🎙 <b>Шаг 1 из 4: Выберите артиста-референс</b>\n\n"
        "Выберите исполнителя, чей стиль и звучание послужат ориентиром для вашего трека, "
        "или нажмите <b>«Без артиста»</b> для своего уникального стиля:"
    )
    await callback.message.edit_text(
        text,
        reply_markup=get_artists_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@generation_router.callback_query(F.data == "gen_back:to_genres")
async def step_back_to_genres(callback: CallbackQuery, state: FSMContext) -> None:
    """Step back from prompt input to genre selection."""
    await state.set_state(GenerationStates.waiting_for_genres)
    data = await state.get_data()
    selected_genres = data.get("selected_genres", [])
    artist_name = data.get("artist_name")
    artist_label = f"<b>{artist_name}</b>" if artist_name else "Без артиста"

    genres_text = format_genres_display(selected_genres)
    selected_status = (
        f"Выбрано: <b>{genres_text}</b> ({len(selected_genres)})"
        if selected_genres
        else "Выбрано: <i>пока ничего не выбрано</i>"
    )

    text = (
        f"🎙 <b>Артист:</b> {artist_label}\n\n"
        "🎧 <b>Шаг 2 из 4: Выберите жанры (минимум 2)</b>\n"
        f"{selected_status}\n\n"
        "<i>Нажимайте на кнопки, чтобы отметить или снять жанры:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_genres_keyboard(selected_genres),
        parse_mode="HTML",
    )
    await callback.answer()


@generation_router.callback_query(F.data == "gen_back:to_prompt")
async def step_back_to_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    """Step back from mode selection to prompt input."""
    await state.set_state(GenerationStates.waiting_for_prompt)
    data = await state.get_data()
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    selected_genres = data.get("selected_genres", [])
    current_prompt = data.get("prompt", "")

    artist_label = (
        f"<b>{artist_name}</b> ({artist_style})" if artist_name else "Без артиста"
    )
    genres_display = format_genres_display(selected_genres)

    text = (
        f"🎙 <b>Артист:</b> {artist_label}\n"
        f"🎧 <b>Жанры:</b> {genres_display}\n\n"
        f"Текущая идея: <i>«{current_prompt}»</i>\n\n"
        "✍️ <b>Шаг 3 из 4:</b> Вы можете изменить описание трека новым сообщением ниже 👇"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_prompt_input_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@generation_router.callback_query(F.data == "gen_back:to_mode")
async def step_back_to_mode(callback: CallbackQuery, state: FSMContext) -> None:
    """Step back from custom lyrics input to mode selection."""
    await state.set_state(GenerationStates.waiting_for_mode)
    data = await state.get_data()
    prompt = data.get("prompt", "")
    artist_name = data.get("artist_name")
    selected_genres = data.get("selected_genres", [])

    artist_display = f"<b>{artist_name}</b>" if artist_name else "Без артиста"
    genres_display = format_genres_display(selected_genres)

    text = (
        f"🎵 <b>Идея трека:</b> <i>«{prompt}»</i>\n"
        f"🎙 <b>Артист-референс:</b> {artist_display}\n"
        f"🎧 <b>Жанры:</b> {genres_display}\n\n"
        "⚙️ <b>Шаг 4 из 4: Выберите формат трека:</b>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_mode_selection_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------
# STEP 1 CALLBACK: Artist Chosen -> Move to Genres (STEP 2)
# ---------------------------------------------------------
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
        artist_label = "Без артиста (свой стиль)"
    else:
        artist = get_artist_by_id(artist_id)
        if artist:
            await state.update_data(
                artist_id=artist_id,
                artist_name=artist["name"],
                artist_style=artist["style"],
            )
            artist_label = f"<b>{artist['name']}</b> ({artist['style']})"
        else:
            await state.update_data(
                artist_id=None,
                artist_name=None,
                artist_style=None,
            )
            artist_label = "Без артиста"

    # Move to Genre Selection (Step 2)
    await state.set_state(GenerationStates.waiting_for_genres)
    data = await state.get_data()
    selected_genres = data.get("selected_genres", [])

    text = (
        f"🎙 <b>Артист:</b> {artist_label}\n\n"
        "🎧 <b>Шаг 2 из 4: Выберите жанры (минимум 2)</b>\n"
        "Выбрано: <i>пока ничего не выбрано</i>\n\n"
        "<i>Нажимайте на кнопки, чтобы отметить нужные жанры:</i>"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_genres_keyboard(selected_genres),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------
# STEP 2 CALLBACKS: Genres Multi-select
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

    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    artist_label = (
        f"<b>{artist_name}</b> ({artist_style})" if artist_name else "Без артиста"
    )

    genres_text = format_genres_display(selected_genres)
    selected_status = (
        f"Выбрано: <b>{genres_text}</b> ({len(selected_genres)})"
        if selected_genres
        else "Выбрано: <i>пока ничего не выбрано</i>"
    )

    text = (
        f"🎙 <b>Артист:</b> {artist_label}\n\n"
        "🎧 <b>Шаг 2 из 4: Выберите жанры (минимум 2)</b>\n"
        f"{selected_status}\n\n"
        "<i>Нажимайте на кнопки, чтобы отметить или снять жанры:</i>"
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

    existing_prompt = data.get("prompt")
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    artist_label = (
        f"<b>{artist_name}</b> ({artist_style})" if artist_name else "Без артиста"
    )
    genres_display = format_genres_display(selected_genres)

    # If prompt was already provided via quick message:
    if existing_prompt:
        await state.set_state(GenerationStates.waiting_for_mode)
        text = (
            f"🎵 <b>Идея трека:</b> <i>«{existing_prompt}»</i>\n"
            f"🎙 <b>Артист-референс:</b> {artist_label}\n"
            f"🎧 <b>Жанры:</b> {genres_display}\n\n"
            "⚙️ <b>Шаг 4 из 4: Выберите формат трека:</b>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_mode_selection_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Normal flow: move to prompt input (Step 3)
    await state.set_state(GenerationStates.waiting_for_prompt)

    text = (
        f"🎙 <b>Артист:</b> {artist_label}\n"
        f"🎧 <b>Жанры:</b> {genres_display}\n\n"
        "✍️ <b>Шаг 3 из 4: Опишите идею трека:</b>\n"
        "О чём должна быть песня, какое настроение, сюжет или инструменты?\n"
        "<i>Например:</i> «Медленный ночной неоновый трек про поездку на авто и воспоминания»\n\n"
        "Напишите текст сообщением ниже 👇"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_prompt_input_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------------------------------------------------------
# STEP 3: Prompt Text Input
# ---------------------------------------------------------
@generation_router.message(GenerationStates.waiting_for_prompt)
async def process_prompt(message: Message, state: FSMContext) -> None:
    prompt_text = message.text.strip()
    if not prompt_text:
        await message.answer("Пожалуйста, отправьте текстовое описание трека.")
        return

    if len(prompt_text) < 3:
        await message.answer(
            "Слишком короткий промт. Опишите чуть подробнее (хотя бы тему или настроение)."
        )
        return

    await state.update_data(prompt=prompt_text)
    data = await state.get_data()
    artist_name = data.get("artist_name")
    selected_genres = data.get("selected_genres", [])

    await state.set_state(GenerationStates.waiting_for_mode)

    artist_display = f"<b>{artist_name}</b>" if artist_name else "Без артиста"
    genres_display = format_genres_display(selected_genres)

    text = (
        f"🎵 <b>Идея трека:</b> <i>«{prompt_text}»</i>\n"
        f"🎙 <b>Артист-референс:</b> {artist_display}\n"
        f"🎧 <b>Жанры:</b> {genres_display}\n\n"
        "⚙️ <b>Шаг 4 из 4: Выберите формат трека:</b>"
    )

    await message.answer(
        text,
        reply_markup=get_mode_selection_keyboard(),
        parse_mode="HTML",
    )


# ---------------------------------------------------------
# STEP 4: Mode Selection (Vocal AI / Instrumental / Custom Lyrics)
# ---------------------------------------------------------
@generation_router.callback_query(
    GenerationStates.waiting_for_mode, F.data.startswith("gen_mode:")
)
async def process_mode_selection(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]
    data = await state.get_data()
    prompt = data.get("prompt")
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    selected_genres = data.get("selected_genres", [])

    if not prompt:
        await callback.message.edit_text(
            "Произошла ошибка сессии. Пожалуйста, начните заново.",
            reply_markup=get_main_menu_keyboard(),
        )
        await state.clear()
        await callback.answer()
        return

    if mode == "custom_lyrics":
        await state.set_state(GenerationStates.waiting_for_lyrics)
        artist_display = f" (в стиле <b>{artist_name}</b>)" if artist_name else ""
        genres_display = format_genres_display(selected_genres)

        await callback.message.edit_text(
            f"🎵 <b>Идея:</b> <i>«{prompt}»</i>{artist_display}\n"
            f"🎧 <b>Жанры:</b> {genres_display}\n\n"
            "✍️ Теперь отправьте <b>текст песни</b> (стихи, куплеты, припев) сообщением в чат:",
            reply_markup=get_lyrics_input_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Either vocal_ai or instrumental
    instrumental = mode == "instrumental"
    await callback.answer()
    await callback.message.delete()
    await state.clear()

    await execute_generation(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        user_id=callback.from_user.id,
        prompt=prompt,
        instrumental=instrumental,
        artist_name=artist_name,
        artist_style=artist_style,
        selected_genre_ids=selected_genres,
        lyrics=None,
    )


@generation_router.message(GenerationStates.waiting_for_lyrics)
async def process_lyrics(message: Message, state: FSMContext) -> None:
    lyrics_text = message.text.strip()
    if not lyrics_text:
        await message.answer("Пожалуйста, отправьте текст песни или нажмите Отмена.")
        return

    data = await state.get_data()
    prompt = data.get("prompt")
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")
    selected_genres = data.get("selected_genres", [])
    await state.clear()

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


# Quick prompt handler: if user sends text directly in idle state (no FSM state)
@generation_router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def handle_quick_prompt(message: Message, state: FSMContext) -> None:

    prompt_text = message.text.strip()
    if len(prompt_text) < 3:
        return

    await state.update_data(prompt=prompt_text)
    await state.set_state(GenerationStates.waiting_for_artist)

    text = (
        f"🎵 <b>Принята идея:</b> <i>«{prompt_text}»</i>\n\n"
        "🎙 Теперь выберите <b>артиста-референс</b> или нажмите «Без артиста»:"
    )

    await message.answer(
        text,
        reply_markup=get_artists_keyboard(),
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
        "🎸 Без слов (Инструментал)"
        if instrumental
        else ("✍️ Свой текст" if lyrics else "🎤 С вокалом (AI текст)")
    )
    artist_label = artist_name if artist_name else "Оригинальный стиль"

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

    status_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🚀 <b>Запуск генерации...</b>\n\n"
            f"🎵 <b>Идея:</b> <i>{prompt}</i>\n"
            f"🎙 <b>Референс:</b> {artist_label}\n"
            f"🎧 <b>Жанры:</b> {genre_names_str}\n"
            f"⚙️ <b>Режим:</b> {mode_label}\n\n"
            f"⏳ Отправляем задачу в <b>Treblo Melodia v3</b>..."
        ),
        parse_mode="HTML",
    )

    task_id = None
    try:
        # Build tags for Treblo API
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
                    await status_msg.edit_text(
                        f"🎵 <b>Генерация в процессе...</b>\n\n"
                        f"Идея: <i>«{prompt}»</i>\n"
                        f"Референс: {artist_label}\n"
                        f"Жанры: {genre_names_str}\n"
                        f"Режим: {mode_label}\n\n"
                        f"⚡ Нейросеть сочиняет трек и аранжировку... (1-2 мин)",
                        parse_mode="HTML",
                    )
            except Exception as e:
                logger.debug("Failed to edit status message: %s", e)

        # Poll Treblo until complete
        generation_result = await treblo_client.poll_until_complete(
            task_id=task_id,
            status_callback=on_status_update,
        )

        audio_url = generation_result.get("audio_url")
        if not audio_url:
            raise TrebloAPIError("Treblo не вернул ссылку на аудиофайл.")

        image_url = generation_result.get("image_url")
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

        # Clean short title from prompt
        track_title = prompt[:35] + ("..." if len(prompt) > 35 else "")

        caption_lines = [
            f"🎵 <b>{track_title}</b>",
            f"🎙 Референс: {artist_label}",
            f"🎧 Жанры: {genre_names_str}",
            f"⚙️ Режим: {mode_label}",
        ]
        if duration:
            minutes = int(duration // 60)
            seconds = int(duration % 60)
            caption_lines.append(f"⏱ Длительность: {minutes}:{seconds:02d}")

        gen_lyrics = generation_result.get("lyrics")
        if gen_lyrics and not instrumental:
            preview_lyrics = gen_lyrics[:250].strip()
            if len(gen_lyrics) > 250:
                preview_lyrics += "..."
            caption_lines.append(f"\n📜 <b>Текст трека:</b>\n<i>{preview_lyrics}</i>")

        caption_text = "\n".join(caption_lines)

        audio_file = BufferedInputFile(
            audio_bytes, filename=f"treblo_track_{task_id[:8]}.mp3"
        )
        thumb_file = (
            BufferedInputFile(thumb_bytes, filename="cover.webp")
            if thumb_bytes
            else None
        )

        performer_name = f"{artist_name} (AI)" if artist_name else "Treblo AI"

        await bot.send_audio(
            chat_id=chat_id,
            audio=audio_file,
            thumbnail=thumb_file,
            title=track_title,
            performer=performer_name,
            duration=int(duration) if duration else None,
            caption=caption_text,
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
                "🚨 <b>КРИТИЧЕСКИЙ АЛЕРТ: Закончились кредиты Treblo API!</b>\n\n"
                f"Пользователь <code>{user_id}</code> не смог сгенерировать трек.\n"
                "Срочно пополните баланс на https://treblo.com",
            )
        except Exception:
            pass

        await status_msg.edit_text(
            "⚠️ <b>Внимание:</b> На сервисе Treblo временно закончились кредиты API. "
            "Пожалуйста, свяжитесь с администратором.\nВаш баланс не списан.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )

    except TrebloTimeoutError as e:
        logger.error("Treblo timeout: %s", e)
        # Refund credit
        if deducted_from:
            await db.refund_generation_credit(user_id, balance_type=deducted_from, cost=cost)
        if task_id:
            await db.update_generation_status(task_id, "FAILURE")
        await status_msg.edit_text(
            "⏱ <b>Время ожидания трека истекло.</b>\n"
            "Сервер Treblo перегружен или обрабатывает задачу слишком долго.\n"
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
            f"❌ <b>Ошибка генерации:</b>\n{str(e)[:200]}\n\n"
            "Потраченная попытка возвращена на ваш баланс. Попробуйте еще раз или измените промт.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )
