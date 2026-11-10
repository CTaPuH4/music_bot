from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Optional, Dict, Iterable

# Primary 24 artists shown in 3-column grid on Step 1
POPULAR_ARTISTS = [
    {"id": "skrip", "name": "Скриптонит", "style": "тягучий блюз-трэп, фирменный грув, живые барабаны, темная атмосфера", "aliases": ["скриптонит", "скрип", "skriptonit", "skrip"]},
    {"id": "morgenshtern", "name": "MORGENSHTERN", "style": "энергичный трэп, мощный 808 бас, дерзкий флоу, клубный бэнгер", "aliases": ["моргенштерн", "морген", "morgenshtern", "morgen"]},
    {"id": "oxxxymiron", "name": "Oxxxymiron", "style": "быстрый техничный грайм, сложная рифмовка, плотный бит, интеллектуальный хип-хоп", "aliases": ["оксимирон", "окси", "oxxxymiron", "oxxxy", "мирон"]},
    {"id": "basta", "name": "Баста", "style": "лиричный русский рэп, гитарные переборы, хриплый душевный вокал", "aliases": ["баста", "ноггано", "василий вакуленко", "basta"]},
    {"id": "tape", "name": "Big Baby Tape", "style": "трэп, мемфис-рэп, напористый флоу, мощный перегруженный 808 бас", "aliases": ["биг бейби тейп", "тейп", "big baby tape", "tape"]},
    {"id": "kizaru", "name": "Kizaru", "style": "классический мемфис-хип-хоп, расслабленный флоу, мрачный атмосферный трэп", "aliases": ["кизару", "kizaru", "олег"]},
    {"id": "kreed", "name": "Егор Крид", "style": "мелодичный поп-хип-хоп, современный коммерческий поп, гладкий вокал", "aliases": ["егор крид", "крид", "kreed", "egor kreed"]},
    {"id": "buda", "name": "OG Buda", "style": "детройт-рэп, оффбит флоу, остроумные панчлайны, быстрый напористый бит", "aliases": ["ог буда", "буда", "og buda", "buda"]},
    {"id": "face", "name": "Face", "style": "минималистичный трэп, эмоциональный речитатив, драйвовый молодежный флоу", "aliases": ["фейс", "face", "иван дремин"]},
    {"id": "eljay", "name": "Элджей", "style": "клубный хаус-рэп, неоновый дип-хаус, заедающий припев, автотюн", "aliases": ["элджей", "sayonaraboy", "eljay", "allj"]},
    {"id": "pharaoh", "name": "Pharaoh", "style": "мрачный клауд-рэп, дед-династия, холодный меланхоличный саунд, шепчущий флоу", "aliases": ["фараон", "фара", "pharaoh", "глеб"]},
    {"id": "tfest", "name": "T-Fest", "style": "мелодичный трэп, высокий эмоциональный вокал, гитарные акустические элементы", "aliases": ["т-фест", "тифест", "t-fest", "tfest"]},
    {"id": "miyagi", "name": "Miyagi", "style": "глубокий регги-хип-хоп, атмосферный саунд, плотный качающий грув", "aliases": ["мияги", "miyagi", "эндшпиль", "hajime"]},
    {"id": "saluki", "name": "Saluki", "style": "экспериментальный кинематографичный хип-хоп, сложный продакшн, живые инструменты", "aliases": ["салуки", "saluki", "сеня"]},
    {"id": "instasamka", "name": "INSTASAMKA", "style": "дерзкий поп-трэп, глянцевый бит, ироничный речитатив, клубный кач", "aliases": ["инстасамка", "самка", "instasamka", "даша"]},
    {"id": "jigan", "name": "Джиган", "style": "клубный хип-хоп, плотный танцевальный кач, уверенный бархатный речитатив", "aliases": ["джиган", "geegun", "jigan"]},
    {"id": "mot", "name": "Мот", "style": "лиричный соул-хип-хоп, R&B, танцевальный поп, мелодичные припевы", "aliases": ["мот", "mot", "матвей"]},
    {"id": "lone", "name": "L'One", "style": "мотивирующий стадионный хип-хоп, эпичные трубы и барабаны, энергичный флоу", "aliases": ["леван", "лван", "l'one", "lone"]},
    {"id": "guf", "name": "Guf", "style": "классический московский андеграунд-рэп, неторопливый размеренный флоу, житейская лирика", "aliases": ["гуф", "guf", "леша"]},
    {"id": "husky", "name": "Husky", "style": "экспрессивный авангардный хип-хоп, шаманский надрывный речитатив, индустриальный бит", "aliases": ["хаски", "husky", "дима"]},
    {"id": "noize", "name": "Noize MC", "style": "фристайл-рок-хип-хоп, живой гаражный панк, остросоциальные стихи, акустическая гитара", "aliases": ["нойз", "нойз эмси", "noize mc", "noize", "иван алексеев"]},
    {"id": "markul", "name": "Markul", "style": "мелодичный лондонский грайм-поп, электронный саунд, мягкий автотюн", "aliases": ["маркул", "markul", "марк"]},
    {"id": "gone_fludd", "name": "GONE.Fludd", "style": "яркий психоделический поп-трэп, комиксовый драйв, быстрый игривый речитатив", "aliases": ["гон флад", "флад", "gone.fludd", "gone fludd", "саша"]},
    {"id": "soda_luv", "name": "SODA LUV", "style": "агрессивный трэп, низкий хриплый голос, перегруженный бас, мем-панчи", "aliases": ["сода лав", "сода", "soda luv", "sodaluv"]},
]

# Additional artists available in base and by text search
EXTENDED_ARTISTS = [
    {"id": "macan", "name": "MACAN", "style": "пацанский хип-хоп, глубокий бас, мелодичный автотюн, уличная романтика", "aliases": ["макан", "macan", "андрей"]},
    {"id": "anna_asti", "name": "ANNA ASTI", "style": "танцевальный поп, сильный эмоциональный женский вокал, клубный бит 120 bpm", "aliases": ["анна асти", "асти", "anna asti", "asti"]},
    {"id": "kish", "name": "Король и Шут", "style": "хоррор-панк-рок, драйвовые гитары, сказочная мистическая атмосфера, хоровой припев", "aliases": ["король и шут", "киш", "горшок", "князь", "kish"]},
    {"id": "zivert", "name": "Zivert", "style": "стильный винтажный синти-поп, фанк, диско 80-х, мягкий женский вокал", "aliases": ["зиверт", "zivert", "юля"]},
    {"id": "kino", "name": "Кино (Цой)", "style": "русский рок, советский пост-панк, пульсирующий бас, акустика и лаконичный ритм", "aliases": ["кино", "цой", "виктор цой", "kino"]},
    {"id": "korzh", "name": "Макс Корж", "style": "стадионный дворовый поп-рэп, душевный припев, акустическая гитара, рейв-дроп", "aliases": ["макс корж", "корж", "max korzh"]},
    {"id": "atl", "name": "ATL", "style": "кислотный шаманский электро-рэп, мрачный хаус-бит, глубокая поэзия", "aliases": ["атл", "atl", "сергей семак"]},
    {"id": "lsp", "name": "ЛСП", "style": "трагичный синти-поп, танцевальный меланхоличный рэп, цепляющий припев", "aliases": ["лсп", "lsp", "олег"]},
    {"id": "hammali_navai", "name": "HammAli & Navai", "style": "кальянный рэп, восточные мелодии, надрывный мужской дуэт, томный автотюн", "aliases": ["хаммали наваи", "хаммали", "наваи", "hammali", "navai"]},
    {"id": "jah_khalib", "name": "Jah Khalib", "style": "чувственный восточный R&B, глубокий бархатный вокал, романтичный хип-хоп", "aliases": ["джа халиб", "халиб", "jah khalib", "khalib"]},
]

ALL_ARTISTS = POPULAR_ARTISTS + EXTENDED_ARTISTS


def find_artist_by_name(query: str) -> Optional[Dict[str, Any]]:
    """Searches for an artist by name, ID, or alias (case-insensitive)."""
    q = query.strip().lower()
    if not q:
        return None
    for a in ALL_ARTISTS:
        if q == a["id"].lower() or q == a["name"].lower():
            return a
        for alias in a.get("aliases", []):
            if q == alias.lower():
                return a
    # Partial match
    for a in ALL_ARTISTS:
        if q in a["name"].lower() or any(q in alias.lower() for alias in a.get("aliases", [])):
            return a
    return None


def get_artist_by_id(artist_id: str) -> Optional[Dict[str, Any]]:
    for a in ALL_ARTISTS:
        if a["id"] == artist_id:
            return a
    return None

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


def get_artists_keyboard(artists: Optional[Iterable[Dict[str, Any]]] = None) -> InlineKeyboardMarkup:
    """Builds a 3-column inline keyboard with popular artists + show all + without artist."""
    buttons = []
    row = []

    artist_list = list(artists) if artists is not None else POPULAR_ARTISTS

    for artist in artist_list:
        row.append(
            InlineKeyboardButton(
                text=artist["name"],
                callback_data=f"gen_artist:{artist['id']}",
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    # Show all artists button & Without artist button
    buttons.append([
        InlineKeyboardButton(
            text="📋 Показать всех артистов",
            callback_data="gen_artists_all",
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="⏭ Без артиста (только жанры)",
            callback_data="gen_artist:none",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_all_artists_keyboard(artists: Optional[Iterable[Dict[str, Any]]] = None) -> InlineKeyboardMarkup:
    """Keyboard for extended artists list with back to popular button."""
    buttons = []
    row = []

    artist_list = list(artists) if artists is not None else ALL_ARTISTS

    for artist in artist_list:
        row.append(
            InlineKeyboardButton(
                text=artist["name"],
                callback_data=f"gen_artist:{artist['id']}",
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []

    if row:
        buttons.append(row)

    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад к популярным",
            callback_data="gen_artists_popular",
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="⏭ Без артиста (только жанры)",
            callback_data="gen_artist:none",
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
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_prompt_input_keyboard() -> Optional[InlineKeyboardMarkup]:
    return None


def get_mode_selection_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🤖 Auto - ИИ напишет текст",
                    callback_data="gen_mode:vocal_ai",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✍️ Свой текст",
                    callback_data="gen_mode:custom_lyrics",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎸 Инструментал (без вокала)",
                    callback_data="gen_mode:instrumental",
                ),
            ],
        ]
    )


def get_lyrics_input_keyboard() -> Optional[InlineKeyboardMarkup]:
    return None


def get_subscription_gate_keyboard(channel_url: str) -> InlineKeyboardMarkup:
    """Builds inline keyboard shown when user is not subscribed to mandatory channel."""
    buttons = []
    if channel_url:
        buttons.append([
            InlineKeyboardButton(text="📢 Подписаться на канал", url=channel_url),
        ])
    buttons.append([
        InlineKeyboardButton(text="✅ Проверить подписку", callback_data="sub_check_verify"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_after_generation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 Создать ещё", callback_data="menu_create"),
                InlineKeyboardButton(text="💳 Купить создания", callback_data="menu_topup"),
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
        ]
    )


def get_referral_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Назад в профиль", callback_data="menu_profile"),
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
