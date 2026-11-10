from aiogram.fsm.state import State, StatesGroup


class AdminStates(StatesGroup):
    # Broadcast
    waiting_for_broadcast_text = State()
    confirm_broadcast = State()

    # Give credits
    waiting_for_user_id = State()
    waiting_for_credits_amount = State()

    # Price customization
    waiting_for_tariff_price = State()
