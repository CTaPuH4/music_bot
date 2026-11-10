from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, Dict

POPULAR_ARTISTS = [
    {
        "id": "macan",
        "name": "MACAN",
        "style": "пацанский хип-хоп, глубокий бас, мелодичный автотюн, уличная романтика",
    },
    {
        "id": "anna_asti",
        "name": "ANNA ASTI",
        "style": "танцевальный поп, сильный эмоциональный женский вокал, клубный бит 120 bpm",
    },
    {
        "id": "miyagi",
        "name": "Miyagi & Эндшпиль",
        "style": "глубокий регги-хип-хоп, атмосферный саунд, плотный качающий грув",
    },
    {
        "id": "basta",
        "name": "Баста",
        "style": "лиричный русский рэп, гитарные переборы, хриплый душевный вокал",
    },
    {
        "id": "morgenshtern",
        "name": "MORGENSHTERN",
        "style": "энергичный трэп, мощный 808 бас, дерзкий флоу, клубный бэнгер",
    },
    {
        "id": "kish",
        "name": "Король и Шут",
        "style": "хоррор-панк-рок, драйвовые гитары, сказочная мистическая атмосфера, хоровой припев",
    },
    {
        "id": "zivert",
        "name": "Zivert",
        "style": "стильный винтажный синти-поп, фанк, диско 80-х, мягкий женский вокал",
    },
    {
        "id": "skrip",
        "name": "Скриптонит",
        "style": "тягучий блюз-трэп, фирменный грув, живые барабаны, темная атмосфера",
    },
    {
        "id": "instasamka",
        "name": "INSTASAMKA",
        "style": "дерзкий поп-трэп, глянцевый бит, ироничный речитатив, клубный кач",
    },
    {
        "id": "kino",
        "name": "Кино (Цой)",
        "style": "русский рок, советский пост-панк, пульсирующий бас, акустика и лаконичный ритм",
    },
]


def get_artist_by_id(artist_id: str) -> Optional[Dict[str, str]]:
    for artist in POPULAR_ARTISTS:
        if artist["id"] == artist_id:
            return artist
    return None


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать музыку", callback_data="menu_create"),
            ],
            [
                InlineKeyboardButton(text="👤 Профиль и баланс", callback_data="menu_profile"),
                InlineKeyboardButton(text="💡 Примеры промтов", callback_data="menu_examples"),
            ],
            [
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu_help"),
            ],
        ]
    )


def get_artists_keyboard() -> InlineKeyboardMarkup:
    """Builds an inline keyboard with popular Russian artists (2 per row) + skip & cancel."""
    buttons = []
    row = []

    for idx, artist in enumerate(POPULAR_ARTISTS):
        row.append(
            InlineKeyboardButton(
                text=f"🎙 {artist['name']}",
                callback_data=f"gen_artist:{artist['id']}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Add 'Without artist' and 'Cancel'
    buttons.append([
        InlineKeyboardButton(
            text="🚫 Без артиста (Свой стиль)",
            callback_data="gen_artist:none",
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data="gen_cancel",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_mode_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎤 С вокалом (AI текст)",
                    callback_data="gen_mode:vocal_ai",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎸 Без слов (Инструментал)",
                    callback_data="gen_mode:instrumental",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✍️ Добавить свой текст",
                    callback_data="gen_mode:custom_lyrics",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="gen_cancel",
                ),
            ],
        ]
    )


def get_after_generation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать ещё трек", callback_data="menu_create"),
                InlineKeyboardButton(text="👤 Мой баланс", callback_data="menu_profile"),
            ],
        ]
    )


def get_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать трек", callback_data="menu_create"),
            ],
            [
                InlineKeyboardButton(text="👥 Реферальная программа", callback_data="menu_referral"),
            ],
            [
                InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="menu_topup"),
            ],
        ]
    )


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="gen_cancel"),
            ]
        ]
    )
