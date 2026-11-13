from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any


def get_admin_main_keyboard(sub_enabled: bool = False) -> InlineKeyboardMarkup:
    sub_button_text = "🔔 Проверка подписки: ✅ ВКЛ" if sub_enabled else "🔕 Проверка подписки: ❌ ВЫКЛ"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Создать рассылку", callback_data="admin_broadcast"),
            ],
            [
                InlineKeyboardButton(text="🎁 Начислить генерации", callback_data="admin_give_credits"),
            ],
            [
                InlineKeyboardButton(text="💳 Настройка цен тарифов", callback_data="admin_prices"),
            ],
            [
                InlineKeyboardButton(text="🎟 Управление промокодами", callback_data="admin_promos"),
            ],
            [
                InlineKeyboardButton(text="🎤 Управление артистами", callback_data="admin_artists:popular:1"),
            ],
            [
                InlineKeyboardButton(text="📊 Баланс API генераций", callback_data="admin_treblo_balance"),
            ],
            [
                InlineKeyboardButton(text=sub_button_text, callback_data="admin_sub_menu"),
            ],
            [
                InlineKeyboardButton(text="❌ Закрыть админку", callback_data="admin_close"),
            ],
        ]
    )


def get_admin_sub_keyboard(sub_enabled: bool = False) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Выключить проверку подписки" if sub_enabled else "🟢 Включить проверку подписки"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=toggle_text, callback_data="admin_sub_toggle"),
            ],
            [
                InlineKeyboardButton(text="✏️ Изменить канал", callback_data="admin_sub_edit_channel"),
                InlineKeyboardButton(text="🔗 Изменить ссылку", callback_data="admin_sub_edit_url"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_menu"),
            ],
        ]
    )


def get_admin_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🚀 Подтвердить и отправить всем", callback_data="admin_broadcast_send"),
            ],
            [
                InlineKeyboardButton(text="❌ Отменить рассылку", callback_data="admin_menu"),
            ],
        ]
    )


def get_admin_tariffs_keyboard(tariffs: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    buttons = []
    for t in tariffs:
        tid = t.get("id") or t.get("tariff_id")
        price_val = t.get("price", 0)
        try:
            price_display = f"{int(price_val)} ₽"
        except Exception:
            price_display = f"{price_val} ₽"

        emoji = t.get("emoji", "💳")
        title = t.get("title", tid)
        badge = t.get("badge")
        if not badge or "Тест" in badge:
            from keyboards.inline import format_per_track_badge
            badge = format_per_track_badge(price_val, t.get("credits", 1))

        buttons.append([
            InlineKeyboardButton(
                text=f"✏️ {emoji} {title} — {price_display} ({badge})",
                callback_data=f"admin_price_edit:{tid}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_cancel_keyboard(back_callback: str = "admin_menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="◀️ Отмена", callback_data=back_callback),
            ]
        ]
    )


def get_admin_artists_list_keyboard(
    artists: List[Dict[str, Any]],
    tab: str = "popular",
    page: int = 1,
    per_page: int = 8,
) -> InlineKeyboardMarkup:
    """Builds paginated keyboard for admin artists list with tab switcher."""
    buttons = []

    # Tab switcher
    pop_tab_text = "⭐ Популярные (24)" if tab != "popular" else "✅ ⭐ Популярные"
    ext_tab_text = "📋 Расширенный" if tab != "extended" else "✅ 📋 Расширенный"

    buttons.append([
        InlineKeyboardButton(text=pop_tab_text, callback_data="admin_artists:popular:1"),
        InlineKeyboardButton(text=ext_tab_text, callback_data="admin_artists:extended:1"),
    ])

    total_artists = len(artists)
    total_pages = max(1, (total_artists + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * per_page
    page_artists = artists[start_idx : start_idx + per_page]

    # Artist buttons (2 per row for compact clean UI)
    row = []
    for idx, a in enumerate(page_artists, start=start_idx + 1):
        btn_text = f"#{idx} {a['name']}"
        row.append(
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"admin_artist_view:{a['id']}:{tab}:{page}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Pagination controls
    nav_row = []
    if page > 1:
        nav_row.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"admin_artists:{tab}:{page - 1}")
        )
    if total_pages > 1:
        nav_row.append(
            InlineKeyboardButton(
                text=f"Стр. {page}/{total_pages}",
                callback_data="admin_artists_noop",
            )
        )
    if page < total_pages:
        nav_row.append(
            InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"admin_artists:{tab}:{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)

    # Actions: Add artist & Back
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить артиста", callback_data=f"admin_artist_add:{tab}:{page}"),
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_menu"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_artist_card_keyboard(
    artist_id: str,
    is_popular: bool,
    is_first: bool,
    is_last: bool,
    tab: str,
    page: int,
) -> InlineKeyboardMarkup:
    """Builds action keyboard for a single artist card."""
    buttons = []

    # Row 1: Move order
    move_row = []
    if not is_first:
        move_row.append(
            InlineKeyboardButton(
                text="⬆️ Поднять выше",
                callback_data=f"admin_artist_move:{artist_id}:up:{tab}:{page}",
            )
        )
    if not is_last:
        move_row.append(
            InlineKeyboardButton(
                text="⬇️ Опустить ниже",
                callback_data=f"admin_artist_move:{artist_id}:down:{tab}:{page}",
            )
        )
    if move_row:
        buttons.append(move_row)

    # Row 2: Popularity toggle
    if is_popular:
        toggle_text = "📋 Перенести в расширенный список"
    else:
        toggle_text = "⭐ Сделать популярным (на 1-й экран)"
    buttons.append([
        InlineKeyboardButton(
            text=toggle_text,
            callback_data=f"admin_artist_toggle_pop:{artist_id}:{tab}:{page}",
        )
    ])

    # Row 3: Edit style
    buttons.append([
        InlineKeyboardButton(
            text="✏️ Изменить стиль для нейросети",
            callback_data=f"admin_artist_edit_style:{artist_id}:{tab}:{page}",
        )
    ])

    # Row 4: Delete
    buttons.append([
        InlineKeyboardButton(
            text="🗑 Удалить артиста",
            callback_data=f"admin_artist_del_prompt:{artist_id}:{tab}:{page}",
        )
    ])

    # Row 5: Back to list
    buttons.append([
        InlineKeyboardButton(
            text="◀️ Назад к списку артистов",
            callback_data=f"admin_artists:{tab}:{page}",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_artist_delete_confirm_keyboard(
    artist_id: str, tab: str, page: int
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Да, удалить навсегда",
                    callback_data=f"admin_artist_del_confirm:{artist_id}:{tab}:{page}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Отмена",
                    callback_data=f"admin_artist_view:{artist_id}:{tab}:{page}",
                ),
            ],
        ]
    )


def get_admin_artist_popularity_choice_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ В популярные (сетка на 1-м шаге)",
                    callback_data="admin_artist_create_pop:1",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📋 В расширенный список",
                    callback_data="admin_artist_create_pop:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Отмена",
                    callback_data="admin_artists:popular:1",
                ),
            ],
        ]
    )


# ---------------------------------------------------------
# PROMO CODES ADMIN KEYBOARDS
# ---------------------------------------------------------
def get_admin_promos_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_promo_create"),
            ],
            [
                InlineKeyboardButton(text="📋 Список промокодов", callback_data="admin_promo_list:1"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад в админку", callback_data="admin_menu"),
            ],
        ]
    )


def get_admin_promo_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Процент скидки", callback_data="admin_promo_type:discount"),
                InlineKeyboardButton(text="🎵 Генерации (бонус)", callback_data="admin_promo_type:credits"),
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_promos"),
            ],
        ]
    )


def get_admin_promo_discount_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 Фиксированный % (на все)", callback_data="admin_promo_disc_mode:fixed"),
            ],
            [
                InlineKeyboardButton(text="🎛 Для каждого тарифа отдельно", callback_data="admin_promo_disc_mode:custom"),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data="admin_promo_create"),
            ],
        ]
    )


def get_admin_promo_duration_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏱ 1 час", callback_data="admin_promo_dur:1h"),
                InlineKeyboardButton(text="⏱ 3 часа", callback_data="admin_promo_dur:3h"),
            ],
            [
                InlineKeyboardButton(text="⏱ 5 часов", callback_data="admin_promo_dur:5h"),
                InlineKeyboardButton(text="⏱ 12 часов", callback_data="admin_promo_dur:12h"),
            ],
            [
                InlineKeyboardButton(text="⏱ 24 часа", callback_data="admin_promo_dur:24h"),
                InlineKeyboardButton(text="⏱ 3 дня", callback_data="admin_promo_dur:3d"),
            ],
            [
                InlineKeyboardButton(text="⏱ 7 дней", callback_data="admin_promo_dur:7d"),
                InlineKeyboardButton(text="⏱ 30 дней", callback_data="admin_promo_dur:30d"),
            ],
            [
                InlineKeyboardButton(text="✏️ Ввести дату вручную (МСК)", callback_data="admin_promo_dur:manual"),
            ],
            [
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_promos"),
            ],
        ]
    )


def get_admin_promo_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да, создать промокод", callback_data="admin_promo_confirm_create"),
            ],
            [
                InlineKeyboardButton(text="✏️ Заполнить заново", callback_data="admin_promo_create"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="admin_promos"),
            ],
        ]
    )


def get_admin_promos_list_keyboard(
    promos: List[Dict[str, Any]], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    buttons = []
    for p in promos:
        status_icon = "🟢" if p.get("is_active") else "🔴"
        p_type = p.get("promo_type")
        if p_type == "credits":
            type_label = f"+{p.get('reward_data', {}).get('credits', 0)} ген."
        elif p_type == "discount_fixed":
            type_label = f"-{p.get('reward_data', {}).get('percent', 0)}%"
        else:
            type_label = "Дифф. %"

        btn_text = f"{status_icon} {p['code']} ({type_label}, {p['current_activations']}/{p['max_activations']})"
        buttons.append([
            InlineKeyboardButton(text=btn_text, callback_data=f"admin_promo_card:{p['id']}:{page}")
        ])

    # Pagination
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"admin_promo_list:{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="admin_promo_noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"admin_promo_list:{page + 1}"))
    if len(nav_row) > 1:
        buttons.append(nav_row)

    buttons.append([
        InlineKeyboardButton(text="➕ Создать промокод", callback_data="admin_promo_create"),
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад в промокоды", callback_data="admin_promos"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_promo_card_keyboard(promo_id: int, is_active: bool, page: int = 1) -> InlineKeyboardMarkup:
    buttons = []
    if is_active:
        buttons.append([
            InlineKeyboardButton(text="⛔ Деактивировать промокод", callback_data=f"admin_promo_deact:{promo_id}:{page}"),
        ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Назад к списку", callback_data=f"admin_promo_list:{page}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
