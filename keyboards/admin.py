from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Any


def get_admin_main_keyboard() -> InlineKeyboardMarkup:
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
                InlineKeyboardButton(text="📊 Баланс Treblo API", callback_data="admin_treblo_balance"),
            ],
            [
                InlineKeyboardButton(text="❌ Закрыть админку", callback_data="admin_close"),
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
