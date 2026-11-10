import asyncio
import io
import logging
from typing import Optional

import httpx
from aiogram import Router, F, Bot
from aiogram.filters import Command
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
    get_mode_selection_keyboard,
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


@generation_router.message(Command("create"))
@generation_router.callback_query(F.data == "menu_create")
async def start_creation(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Step 1: Choose artist reference or skip."""
    await state.clear()
    await state.set_state(GenerationStates.waiting_for_artist)

    text = (
        "🎙 <b>Шаг 1 из 3: Выберите артиста-референс</b>\n\n"
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


@generation_router.callback_query(
    GenerationStates.waiting_for_artist, F.data.startswith("gen_artist:")
)
async def process_artist_selection(callback: CallbackQuery, state: FSMContext) -> None:
    artist_id = callback.data.split(":")[1]
    data = await state.get_data()
    existing_prompt = data.get("prompt")

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

    # If prompt was already provided via quick text message:
    if existing_prompt:
        await state.set_state(GenerationStates.waiting_for_mode)
        text = (
            f"🎵 <b>Идея трека:</b> <i>«{existing_prompt}»</i>\n"
            f"🎙 <b>Артист-референс:</b> {artist_label}\n\n"
            "⚙️ <b>Шаг 3 из 3: Выберите формат трека:</b>"
        )
        await callback.message.edit_text(
            text,
            reply_markup=get_mode_selection_keyboard(),
            parse_mode="HTML",
        )
        await callback.answer()
        return

    # Normal flow: move to waiting for prompt
    await state.set_state(GenerationStates.waiting_for_prompt)

    if artist_id == "none":
        text = (
            "✨ <b>Выбран режим:</b> Без артиста (свой стиль)\n\n"
            "✍️ <b>Шаг 2 из 3: Опишите трек:</b>\n"
            "Укажите жанр, настроение, тему или инструменты.\n"
            "<i>Например:</i> «Медленный меланхоличный джаз с саксофоном и дождливым настроением»\n\n"
            "Напишите текст сообщением ниже 👇"
        )
    else:
        text = (
            f"🎙 <b>Выбран артист:</b> {artist_label}\n\n"
            "✍️ <b>Шаг 2 из 3: Опишите идею песни:</b>\n"
            "О чём должна быть песня, какое настроение или тема трека?\n"
            "<i>Например:</i> «Ночной город, скорость на трассе, воспоминания о любви»\n\n"
            "Напишите текст сообщением ниже 👇"
        )

    await callback.message.edit_text(
        text,
        reply_markup=get_cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


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

    await state.set_state(GenerationStates.waiting_for_mode)

    artist_display = f"<b>{artist_name}</b>" if artist_name else "Без артиста"
    text = (
        f"🎵 <b>Идея трека:</b> <i>«{prompt_text}»</i>\n"
        f"🎙 <b>Артист-референс:</b> {artist_display}\n\n"
        "⚙️ <b>Шаг 3 из 3: Выберите формат трека:</b>"
    )

    await message.answer(
        text,
        reply_markup=get_mode_selection_keyboard(),
        parse_mode="HTML",
    )


@generation_router.callback_query(
    GenerationStates.waiting_for_mode, F.data.startswith("gen_mode:")
)
async def process_mode_selection(callback: CallbackQuery, state: FSMContext) -> None:
    mode = callback.data.split(":")[1]
    data = await state.get_data()
    prompt = data.get("prompt")
    artist_name = data.get("artist_name")
    artist_style = data.get("artist_style")

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
        await callback.message.edit_text(
            f"🎵 <b>Промт:</b> <i>«{prompt}»</i>{artist_display}\n\n"
            "✍️ Теперь отправьте <b>текст песни</b> (стихи, куплеты, припев) сообщением в чат:",
            reply_markup=get_cancel_keyboard(),
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
    await state.clear()

    await execute_generation(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        prompt=prompt,
        instrumental=False,
        artist_name=artist_name,
        artist_style=artist_style,
        lyrics=lyrics_text,
    )


# Quick prompt handler: if user sends text directly in idle state
@generation_router.message(F.text & ~F.text.startswith("/"))
async def handle_quick_prompt(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is not None:
        return

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


async def execute_generation(
    bot: Bot,
    chat_id: int,
    user_id: int,
    prompt: str,
    instrumental: bool,
    artist_name: Optional[str] = None,
    artist_style: Optional[str] = None,
    lyrics: Optional[str] = None,
) -> None:
    """Executes the full music generation pipeline with Treblo Melodia v3 API."""
    user = await db.get_user(user_id)
    if not user:
        user = await db.get_or_create_user(user_id)

    # Check balance
    cost = settings.generation_cost
    if user["balance"] < cost:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"⚠️ <b>Недостаточно генераций на балансе!</b>\n\n"
                f"У вас осталось: <b>{user['balance']}</b>\n"
                f"Стоимость создания: <b>{cost}</b>\n\n"
                "Приглашайте друзей по реферальной ссылке или пополните баланс в профиле."
            ),
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )
        return

    # Deduct balance upfront (will refund if API fails)
    await db.change_balance(user_id, -cost)

    mode_label = (
        "🎸 Без слов (Инструментал)"
        if instrumental
        else ("✍️ Свой текст" if lyrics else "🎤 С вокалом (AI текст)")
    )
    artist_label = artist_name if artist_name else "Оригинальный стиль"

    status_msg = await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🚀 <b>Запуск генерации...</b>\n\n"
            f"🎵 <b>Идея:</b> <i>{prompt}</i>\n"
            f"🎙 <b>Референс:</b> {artist_label}\n"
            f"⚙️ <b>Режим:</b> {mode_label}\n\n"
            f"⏳ Отправляем задачу в <b>Treblo Melodia v3</b>..."
        ),
        parse_mode="HTML",
    )

    task_id = None
    try:
        # Prepare full prompt incorporating artist reference
        if artist_name and artist_style:
            full_prompt = f"В стиле {artist_name} ({artist_style}), {prompt}"
            tags = [artist_name.lower().replace("&", "").strip()]
        elif artist_name:
            full_prompt = f"В стиле {artist_name}, {prompt}"
            tags = [artist_name.lower().replace("&", "").strip()]
        else:
            full_prompt = prompt
            tags = None

        # Create task in Treblo
        task_id = await treblo_client.create_generation(
            prompt=full_prompt,
            instrumental=instrumental,
            lyrics=lyrics,
            tags=tags,
        )

        await db.record_generation(
            user_id=user_id,
            task_id=task_id,
            prompt=prompt,
            artist=artist_name,
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
        await db.change_balance(user_id, cost)
        if task_id:
            await db.update_generation_status(task_id, "FAILURE")
        await status_msg.edit_text(
            "⚠️ <b>Внимание:</b> На сервисе Treblo временно закончились кредиты API. "
            "Пожалуйста, свяжитесь с администратором.\nВаш баланс не списан.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )

    except TrebloTimeoutError as e:
        logger.error("Treblo timeout: %s", e)
        # Refund credit
        await db.change_balance(user_id, cost)
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
        await db.change_balance(user_id, cost)
        if task_id:
            await db.update_generation_status(task_id, "FAILURE")
        await status_msg.edit_text(
            f"❌ <b>Ошибка генерации:</b>\n{str(e)[:200]}\n\n"
            "Потраченная попытка возвращена на ваш баланс. Попробуйте еще раз или измените промт.",
            reply_markup=get_main_menu_keyboard(),
            parse_mode="HTML",
        )
