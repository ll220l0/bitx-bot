from aiogram.fsm.state import StatesGroup, State

class LeadState(StatesGroup):
    name = State()
    company = State()
    service = State()
    budget = State()
    contact = State()
    details = State()
