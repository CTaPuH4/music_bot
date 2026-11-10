from aiogram.fsm.state import State, StatesGroup


class GenerationStates(StatesGroup):
    waiting_for_artist = State()
    waiting_for_prompt = State()
    waiting_for_mode = State()
    waiting_for_lyrics = State()
