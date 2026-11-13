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

    # Artists management
    waiting_for_artist_name = State()
    waiting_for_artist_style = State()
    waiting_for_artist_aliases = State()
    waiting_for_artist_edit_style = State()

    # Mandatory channel subscription settings
    waiting_for_sub_channel = State()
    waiting_for_sub_channel_url = State()

    # Promo codes wizard
    waiting_for_promo_type = State()
    waiting_for_promo_discount_mode = State()
    waiting_for_promo_fixed_percent = State()
    waiting_for_promo_custom_pack = State()
    waiting_for_promo_credits_amount = State()
    waiting_for_promo_duration = State()
    waiting_for_promo_custom_date = State()
    waiting_for_promo_max_activations = State()
    waiting_for_promo_code_text = State()
    waiting_for_promo_confirm = State()
