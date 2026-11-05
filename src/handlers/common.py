"""Общие для основной цепочки константы и функции."""
import asyncio
from typing import Optional, Tuple

from vkbottle import Callback, Keyboard

from database.user_db import get_user
from utils.profile import is_profile_complete, profile_from_row
from utils.session import Session

# Порядок шагов: анкета (6 шагов) → данные мероприятия (3 шага) → выбор помещения
FLOW = [
    "name",
    "age",
    "phone",
    "educational_institution",
    "student_id",
    "division",
    "event",
    "responsible",
    "list_people",
]

# Поля, которые относятся к профилю (остальные — к конкретной заявке)
PROFILE_STEPS = {"name", "age", "phone", "educational_institution", "student_id", "division"}

PROMPTS = {
    "name": "📝 Введите ваше полное ФИО:",
    "age": "🎂 Введите ваш возраст (только число):",
    "phone": "📱 Введите номер телефона (например: 89123456789 или +79123456789):",
    "educational_institution": (
        "🏫 Введите полное название учебного заведения:\n"
        "Пример: Сибирский государственный университет науки и технологий "
        "имени академика М.Ф. Решетнева"
    ),
    "student_id": (
        "📝 Введите группу, институт / должность.\n"
        "Пример: ТБ25-01, ИИТК или Специалист отдела"
    ),
    "division": (
        "👥 Введите название студенческого объединения или подразделения.\n"
        "Пример: Союз студентов, ЦСО или «-»"
    ),
    "event": "🎭 Введите полное название мероприятия:",
    "responsible": "👤 Введите ФИО и номер телефона ответственного за мероприятие:",
    "list_people": (
        "📋 Напишите список участников не из университета "
        "(если их нет — отправьте «—»):"
    ),
}

# Состояния, в которых бот ждёт нажатия кнопки, а не текста
BUTTON_STATES = {"location", "room", "equipment", "wait_decision"}

RESTART_HINT = "Напишите /start и начните бронирование заново."


async def begin_booking(vk_id: int, greet: bool = True) -> Tuple[str, Optional[str]]:
    """
    Начинает новую заявку с чистой сессией.
    Если анкета заполнена — сразу спрашивает название мероприятия,
    иначе запускает анкету. Возвращает (текст, клавиатура).
    """
    row = await asyncio.to_thread(get_user, vk_id)
    profile = profile_from_row(row, vk_id)

    if is_profile_complete(profile):
        sess = Session(
            vk_id,
            "event",
            {"user": profile, "event_info": {}, "bookings": [], "current_booking": None},
        )
        text = "🎭 Введите полное название мероприятия (что будете проводить):"
        keyboard = None
        if greet:
            text = f"👋 С возвращением, {profile['name']}!\n\n{text}"
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("✏️ Изменить анкету", {"action": "edit_profile"}))
                .get_json()
            )
    else:
        sess = Session(vk_id, "name", {"user": {"vk_id": vk_id}})
        text = "👋 Для бронирования нужно заполнить анкету.\n\n" + PROMPTS["name"]
        keyboard = None

    await sess.save()
    return text, keyboard
