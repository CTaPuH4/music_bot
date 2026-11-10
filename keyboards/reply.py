from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Persistent main menu keyboard pinned at the bottom of the Telegram screen.
    Exactly 3 buttons:
    - 🎵 Создать музыку
    - 👤 Профиль и баланс
    - ℹ️ Помощь
    """
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🎵 Создать музыку"),
            ],
            [
                KeyboardButton(text="👤 Профиль и баланс"),
                KeyboardButton(text="ℹ️ Помощь"),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
