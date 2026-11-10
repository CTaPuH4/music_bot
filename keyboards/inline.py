from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, Dict, Iterable

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

# Curated genres matching Treblo's vocabulary with Russian display names
GENRES_CATALOG = [
    {"id": "pop", "name": "Поп", "tag": "pop", "emoji": "✨"},
    {"id": "hiphop", "name": "Рэп / Хип-хоп", "tag": "hip hop", "emoji": "🎤"},
    {"id": "rock", "name": "Рок", "tag": "rock", "emoji": "🎸"},
    {"id": "electronic", "name": "Электроника / EDM", "tag": "electronic", "emoji": "⚡"},
    {"id": "phonk", "name": "Фонк", "tag": "phonk", "emoji": "🏎"},
    {"id": "lofi", "name": "Lo-Fi", "tag": "lofi", "emoji": "☕"},
    {"id": "synthwave", "name": "Синтвейв / 80-е", "tag": "synthwave", "emoji": "🌆"},
    {"id": "rnb", "name": "R&B / Соул", "tag": "r&b", "emoji": "🎷"},
    {"id": "house", "name": "Дип-хаус / Клуб", "tag": "deep house", "emoji": "🪩"},
    {"id": "indie", "name": "Инди / Альтернатива", "tag": "indie", "emoji": "🌿"},
    {"id": "punk", "name": "Панк / Поп-панк", "tag": "punk rock", "emoji": "🔥"},
    {"id": "chanson", "name": "Шансон / Бард", "tag": "chanson", "emoji": "🎻"},
    {"id": "metal", "name": "Метал", "tag": "metal", "emoji": "🤘"},
    {"id": "ambient", "name": "Эмбиент / Саундтрек", "tag": "ambient", "emoji": "🌌"},
]


def get_artist_by_id(artist_id: str) -> Optional[Dict[str, str]]:
    for artist in POPULAR_ARTISTS:
        if artist["id"] == artist_id:
            return artist
    return None


def get_genre_by_id(genre_id: str) -> Optional[Dict[str, str]]:
    for genre in GENRES_CATALOG:
        if genre["id"] == genre_id:
            return genre
    return None


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать музыку", callback_data="menu_create"),
            ],
            [
                InlineKeyboardButton(text="👤 Профиль и баланс", callback_data="menu_profile"),
                InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu_help"),
            ],
        ]
    )


def get_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать музыку", callback_data="menu_create"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в меню", callback_data="menu_main"),
            ],
        ]
    )


def get_artists_keyboard() -> InlineKeyboardMarkup:
    """Builds an inline keyboard with popular Russian artists (2 per row) + skip & cancel."""
    buttons = []
    row = []

    for artist in POPULAR_ARTISTS:
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

    # Add 'Without artist' and 'Back to menu'
    buttons.append([
        InlineKeyboardButton(
            text="🚫 Без артиста (Свой стиль)",
            callback_data="gen_artist:none",
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад в меню",
            callback_data="menu_main",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_genres_keyboard(selected_ids: Iterable[str]) -> InlineKeyboardMarkup:
    """
    Builds a multi-select genre keyboard (2 per row).
    Shows checkmarks on selected genres.
    Requires at least 2 genres to proceed.
    """
    selected_set = set(selected_ids)
    buttons = []
    row = []

    for genre in GENRES_CATALOG:
        is_selected = genre["id"] in selected_set
        prefix = "✅ " if is_selected else ""
        button_text = f"{prefix}{genre['emoji']} {genre['name']}"

        row.append(
            InlineKeyboardButton(
                text=button_text,
                callback_data=f"gen_genre_toggle:{genre['id']}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Action button based on selection count
    count = len(selected_set)
    if count >= 2:
        action_button = InlineKeyboardButton(
            text=f"✅ Готово: продолжить ({count}) ➡️",
            callback_data="gen_genres_confirm",
        )
    else:
        needed = 2 - count
        action_button = InlineKeyboardButton(
            text=f"🔘 Выберите ещё {needed} жанр{'а' if needed == 2 else ''}",
            callback_data="gen_genres_need_more",
        )

    buttons.append([action_button])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад к артистам", callback_data="gen_back:to_artist"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="gen_cancel"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_prompt_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад к жанрам", callback_data="gen_back:to_genres"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="gen_cancel"),
            ]
        ]
    )


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
                InlineKeyboardButton(text="◀️ Назад к описанию", callback_data="gen_back:to_prompt"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="gen_cancel"),
            ],
        ]
    )


def get_lyrics_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад к формату", callback_data="gen_back:to_mode"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="gen_cancel"),
            ]
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
                InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="menu_topup"),
            ],
            [
                InlineKeyboardButton(text="👥 Реферальная программа", callback_data="menu_referral"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в меню", callback_data="menu_main"),
            ],
        ]
    )


def get_referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="menu_profile"),
                InlineKeyboardButton(text="◀️ В главное меню", callback_data="menu_main"),
            ],
        ]
    )


def format_per_track_badge(price: float, credits: int) -> str:
    """Formats price per track (e.g. '100 ₽ за трек' or '0.7 ₽ за трек')."""
    if credits <= 0:
        return ""
    per_track = price / credits
    if per_track.is_integer():
        return f"{int(per_track)} ₽ за трек"
    val = round(per_track, 2)
    return f"{val:g} ₽ за трек"


TARIFF_PACKAGES = [
    {
        "id": "pack_5",
        "title": "5 генераций",
        "credits": 5,
        "price": 10.0,
        "emoji": "🥉",
        "badge": "2 ₽ за трек",
    },
    {
        "id": "pack_15",
        "title": "15 генераций",
        "credits": 15,
        "price": 10.0,
        "emoji": "🥈",
        "badge": "0.7 ₽ за трек",
    },
    {
        "id": "pack_50",
        "title": "50 генераций",
        "credits": 50,
        "price": 10.0,
        "emoji": "🥇",
        "badge": "0.2 ₽ за трек",
    },
    {
        "id": "pack_150",
        "title": "150 генераций",
        "credits": 150,
        "price": 10.0,
        "emoji": "👑",
        "badge": "0.07 ₽ за трек",
    },
]


def get_tariff_by_id(tariff_id: str) -> Optional[Dict[str, Any]]:
    for t in TARIFF_PACKAGES:
        if t["id"] == tariff_id:
            return t
    return None


def get_tariffs_keyboard(
    tariffs: Optional[list[Dict[str, Any]]] = None
) -> InlineKeyboardMarkup:
    buttons = []
    items = tariffs if tariffs else TARIFF_PACKAGES
    for t in items:
        badge = t.get("badge")
        if not badge or "Тест" in badge:
            badge = format_per_track_badge(t.get("price", 0), t.get("credits", 1))

        buttons.append([
            InlineKeyboardButton(
                text=f"{t['emoji']} {t['title']} — {int(t['price'])} ₽ ({badge})",
                callback_data=f"buy_pack:{t['id']}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="menu_profile"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_keyboard(payment_url: str, payment_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Оплатить через ЮKassa", url=payment_url),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить оплату",
                    callback_data=f"pay_check:{payment_id}",
                ),
            ],
            [
                InlineKeyboardButton(text="◀️ К тарифам", callback_data="menu_topup"),
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
