"""Основная цепочка: нажатия inline-кнопок пользователя."""
import logging
from typing import Awaitable, Callable, Dict, Optional, Set

from vkbottle.bot import BotLabeler, MessageEvent

from handlers.common import PROMPTS, RESTART_HINT, begin_booking
from keyboards.generator import (
    equipment_keyboard,
    locations_keyboard,
    page_caption,
    paginate,
    rooms_keyboard,
    LIST_PAGE_SIZE,
    EQUIPMENT_PAGE_SIZE,
)
from keyboards.registry import get_snapshot
from pusk_coworking.handlers_callback import is_pusk_room, start_pusk_flow
from utils.session import Session, user_lock
from utils.vk_helpers import answer_event, edit_or_send

logger = logging.getLogger(__name__)

user_callback_labeler = BotLabeler()

# Какие кнопки в каких состояниях ещё актуальны (None — в любом).
# Нажатие на «старую» кнопку из прошлого сообщения не ломает диалог.
ACTION_STATES: Dict[str, Optional[Set[str]]] = {
    "cancel": None,
    "edit_profile": None,
    "start_new_booking": None,
    "add_another": {"wait_decision"},
    "comment": {"wait_decision"},
    "loc_page": {"location"},
    "select_location": {"location"},
    "back_to_locations": {"room"},
    "room_page": {"room"},
    "select_room": {"room"},
    # back_to_rooms нажимают и с экрана оборудования, и с описания «Пуска»
    "back_to_rooms": {"equipment", "pusk_description"},
    "eq_page": {"equipment"},
    "toggle_eq": {"equipment"},
    "confirm_eq": {"equipment"},
}

Handler = Callable[[MessageEvent, Session, dict], Awaitable[None]]


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def _lost(event: MessageEvent) -> None:
    await edit_or_send(event, f"⚠️ Данные заявки не найдены. {RESTART_HINT}")


# ─────────────────────────────────────────────────────────────
# Экраны
# ─────────────────────────────────────────────────────────────
async def _show_locations(event: MessageEvent, sess: Session, text: str, page: int = 0) -> None:
    locations = get_snapshot().sorted_locations()
    if not locations:
        await Session(sess.vk_id).save("main_menu")
        await edit_or_send(event, "⚠️ Список помещений пока пуст. Обратитесь к администратору.")
        return
    _, page, pages = paginate(locations, page, LIST_PAGE_SIZE)
    await edit_or_send(event, text + page_caption(page, pages), locations_keyboard(locations, page))


async def _show_rooms(event: MessageEvent, location_id: int, page: int = 0) -> bool:
    location = get_snapshot().locations.get(location_id)
    if not location:
        return False
    _, page, pages = paginate(location.rooms, page, LIST_PAGE_SIZE)
    text = f"📍 Выбрана локация: {location.name}\n\n🚪 Выберите аудиторию:"
    if not location.rooms:
        text = f"📍 Локация: {location.name}\n\nВ этом корпусе пока нет аудиторий."
    await edit_or_send(event, text + page_caption(page, pages), rooms_keyboard(location, page))
    return True


async def _show_equipment(event: MessageEvent, sess: Session, page: int = 0) -> None:
    booking = sess.data.get("current_booking") or {}
    room = get_snapshot().rooms.get(_int(booking.get("room_id")) or -1)
    if not room:
        await _lost(event)
        return

    _, page, pages = paginate(room.equipment, page, EQUIPMENT_PAGE_SIZE)
    text = f"🚪 Аудитория: {room.name} ({room.location_name})\n\n🛠️ Выберите необходимое оборудование:"
    if not room.equipment:
        text += "\n\nВ этой аудитории нет оборудования для выбора — нажмите «Подтвердить»."
    keyboard = equipment_keyboard(
        room,
        booking.get("equipment", []),
        page,
        toggle="toggle_eq",
        page_action="eq_page",
        confirm="confirm_eq",
        back="back_to_rooms",
        cancel="cancel",
    )
    await edit_or_send(event, text + page_caption(page, pages), keyboard)


# ─────────────────────────────────────────────────────────────
# Обработчики действий
# ─────────────────────────────────────────────────────────────
async def on_cancel(event: MessageEvent, sess: Session, payload: dict) -> None:
    await Session(sess.vk_id).save("main_menu")
    await edit_or_send(event, "❌ Действие отменено.\n\nЧтобы начать заново, напишите /start")


async def on_edit_profile(event: MessageEvent, sess: Session, payload: dict) -> None:
    new_sess = Session(sess.vk_id, "name", {"user": {"vk_id": sess.vk_id}, "is_editing": True})
    await new_sess.save()
    await edit_or_send(event, "✏️ Редактирование анкеты.\n\n" + PROMPTS["name"])


async def on_start_new_booking(event: MessageEvent, sess: Session, payload: dict) -> None:
    text, keyboard = await begin_booking(sess.vk_id, greet=False)
    await edit_or_send(event, text, keyboard)


async def on_add_another(event: MessageEvent, sess: Session, payload: dict) -> None:
    sess.data["current_booking"] = None
    await sess.save("location")
    await _show_locations(event, sess, "🏛️ Выберите корпус / локацию для новой брони:")


async def on_loc_page(event: MessageEvent, sess: Session, payload: dict) -> None:
    await _show_locations(event, sess, "🏛️ Выберите корпус / локацию:", _int(payload.get("p")) or 0)


async def on_select_location(event: MessageEvent, sess: Session, payload: dict) -> None:
    location = get_snapshot().locations.get(_int(payload.get("id")) or -1)
    if not location:
        await edit_or_send(event, f"⚠️ Корпус не найден (список мог обновиться). {RESTART_HINT}")
        return
    sess.data["current_booking"] = {
        "location": location.name,
        "location_id": location.id,
        "equipment": [],
    }
    await sess.save("room")
    await _show_rooms(event, location.id)


async def on_back_to_locations(event: MessageEvent, sess: Session, payload: dict) -> None:
    sess.data["current_booking"] = None
    await sess.save("location")
    await _show_locations(event, sess, "🏛️ Выберите корпус / локацию:")


async def on_room_page(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.get("current_booking") or {}
    location_id = _int(booking.get("location_id"))
    if location_id is None or not await _show_rooms(event, location_id, _int(payload.get("p")) or 0):
        await _lost(event)


async def on_select_room(event: MessageEvent, sess: Session, payload: dict) -> None:
    room = get_snapshot().rooms.get(_int(payload.get("id")) or -1)
    if not room:
        await edit_or_send(event, f"⚠️ Аудитория не найдена (список мог обновиться). {RESTART_HINT}")
        return

    sess.data["current_booking"] = {
        "location": room.location_name,
        "location_id": room.location_id,
        "room": room.name,
        "room_id": room.id,
        "equipment": [],
    }

    # Передача управления дополнительной цепочкой «Пуск»
    if is_pusk_room(room.name):
        await start_pusk_flow(event, sess, room)
        return

    await sess.save("equipment")
    await _show_equipment(event, sess)


async def on_back_to_rooms(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.get("current_booking") or {}
    location_id = _int(booking.get("location_id"))
    if location_id is None or location_id not in get_snapshot().locations:
        await _lost(event)
        return

    sess.data.pop("pusk_booking", None)
    sess.data["current_booking"] = {
        "location": booking.get("location"),
        "location_id": location_id,
        "equipment": [],
    }
    await sess.save("room")
    await _show_rooms(event, location_id)


async def on_eq_page(event: MessageEvent, sess: Session, payload: dict) -> None:
    await _show_equipment(event, sess, _int(payload.get("p")) or 0)


async def on_toggle_eq(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.get("current_booking") or {}
    room = get_snapshot().rooms.get(_int(booking.get("room_id")) or -1)
    if not room:
        await _lost(event)
        return

    equipment = next((e for e in room.equipment if e.id == _int(payload.get("e"))), None)
    page = _int(payload.get("p")) or 0
    if equipment:
        selected = booking.setdefault("equipment", [])
        if equipment.name in selected:
            selected.remove(equipment.name)
        else:
            selected.append(equipment.name)
        await sess.save()
    await _show_equipment(event, sess, page)


async def on_confirm_eq(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.get("current_booking")
    if not booking:
        await _lost(event)
        return
    if not booking.get("equipment"):
        booking["equipment"] = ["Без оборудования"]

    await sess.save("datetime")
    await edit_or_send(
        event,
        "🕒 Пожалуйста, введите в чат дату и время бронирования.\n\n"
        "Пример формата: 07.03.2026 с 14:00 до 16:30",
    )


async def on_comment(event: MessageEvent, sess: Session, payload: dict) -> None:
    await sess.save("comment")
    await edit_or_send(
        event,
        "📝 Введите комментарий к заявке (или отправьте «-»):\n"
        "Здесь вы можете указать любые важные детали, уточнения или особые пожелания.",
    )


HANDLERS: Dict[str, Handler] = {
    "cancel": on_cancel,
    "edit_profile": on_edit_profile,
    "start_new_booking": on_start_new_booking,
    "add_another": on_add_another,
    "comment": on_comment,
    "loc_page": on_loc_page,
    "select_location": on_select_location,
    "back_to_locations": on_back_to_locations,
    "room_page": on_room_page,
    "select_room": on_select_room,
    "back_to_rooms": on_back_to_rooms,
    "eq_page": on_eq_page,
    "toggle_eq": on_toggle_eq,
    "confirm_eq": on_confirm_eq,
}


# ─────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────
@user_callback_labeler.raw_event("message_event", dataclass=MessageEvent, blocking=False)
async def common_callback_handler(event: MessageEvent) -> None:
    payload = event.payload or {}
    action = payload.get("action")
    if action not in HANDLERS:
        return  # чужая кнопка — не отвечаем, ею займётся другой обработчик

    logger.debug("[MAIN CALLBACK] user=%s action=%s", event.user_id, action)

    async with user_lock(event.user_id):
        sess = await Session.load(event.user_id)

        allowed = ACTION_STATES[action]
        if allowed is not None and sess.state not in allowed:
            await answer_event(event, "Эта кнопка уже неактуальна. Напишите /start")
            return

        await answer_event(event)
        try:
            await HANDLERS[action](event, sess, payload)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в обработчике кнопки %s", action)
            await edit_or_send(event, f"⚠️ Что-то пошло не так. {RESTART_HINT}")
