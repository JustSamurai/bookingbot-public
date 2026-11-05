"""Цепочка «Пуск»: нажатия inline-кнопок."""
import logging
import re
from typing import Awaitable, Callable, Dict, Optional, Set

from vkbottle import Callback, Keyboard
from vkbottle.bot import BotLabeler, MessageEvent

import config
from keyboards.generator import (
    EQUIPMENT_PAGE_SIZE,
    equipment_keyboard,
    page_caption,
    paginate,
)
from keyboards.registry import Room, get_snapshot
from utils.formatters import format_pusk_preview
from utils.session import Session, user_lock
from utils.vk_helpers import answer_event, edit_or_send

from .reporter import send_pusk_application

logger = logging.getLogger(__name__)

pusk_callback_labeler = BotLabeler()

DATETIME_PROMPT = (
    "🕒 Пожалуйста, введите в чат дату и время бронирования.\n\n"
    "Пример формата: 07.03.2026 с 14:00 до 16:30"
)

# Какие кнопки в каких состояниях актуальны
ACTION_STATES: Dict[str, Set[str]] = {
    "pusk_equipment": {"pusk_description", "pusk_equipment"},
    "pusk_eq_page": {"pusk_equipment"},
    "pusk_toggle_eq": {"pusk_equipment"},
    "pusk_confirm_eq": {"pusk_equipment"},
    "pusk_back_to_description": {"pusk_equipment"},
    "pusk_visitors_yes": {"pusk_visitors_question"},
    "pusk_visitors_no": {"pusk_visitors_question"},
    "pusk_add_visitor_bulk": {"pusk_visitors_list"},
    "pusk_finish_visitors": {"pusk_visitors_list"},
    "pusk_consent_yes": {"pusk_personal_data"},
    "pusk_consent_no": {"pusk_personal_data"},
    "pusk_send": {"pusk_confirm"},
    "pusk_cancel": {"pusk_confirm"},
}

Handler = Callable[[MessageEvent, Session, dict], Awaitable[None]]


def is_pusk_room(room_name: str) -> bool:
    """Аудитория «Пуск» определяется по слову «Пуск» в названии (е/ё и регистр не важны)."""
    normalized = (room_name or "").lower().replace("ё", "е")
    return bool(re.search(rf"\b{re.escape(config.PUSK_ROOM_MARKER)}\b", normalized))


def _int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _description(booking: dict) -> str:
    return (
        f"📌 {booking.get('room')}\n"
        f"📍 {booking.get('location')}\n\n"
        "Пространство для мероприятий, репетиций, встреч и творческих активностей.\n\n"
        "Нажмите кнопку, чтобы выбрать оборудование."
    )


def _description_keyboard() -> str:
    return (
        Keyboard(inline=True)
        .add(Callback("🛠 Выбрать оборудование", {"action": "pusk_equipment"}))
        .row()
        .add(Callback("← Назад к аудиториям", {"action": "back_to_rooms"}))
        .get_json()
    )


async def _reset_to_menu(sess: Session) -> None:
    await Session(sess.vk_id).save("main_menu")


# ─────────────────────────────────────────────────────────────
# Точка входа: вызывается основной цепочкой после выбора «Пуска»
# ─────────────────────────────────────────────────────────────
async def start_pusk_flow(event: MessageEvent, sess: Session, room: Room) -> None:
    booking = {
        "location": room.location_name,
        "location_id": room.location_id,
        "room": room.name,
        "room_id": room.id,
        "equipment": [],
        "visitors": [],
        "event_name": sess.event_info.get("event"),
        "comment": None,
        "participants_count": None,
        "personal_data_consent": False,
    }
    sess.data["pusk_booking"] = booking
    await sess.save("pusk_description")
    await edit_or_send(event, _description(booking), _description_keyboard())


# ─────────────────────────────────────────────────────────────
# Экран оборудования
# ─────────────────────────────────────────────────────────────
async def _show_equipment(event: MessageEvent, sess: Session, page: int = 0) -> None:
    booking = sess.data.get("pusk_booking") or {}
    room = get_snapshot().rooms.get(_int(booking.get("room_id")) or -1)
    if not room:
        await _reset_to_menu(sess)
        await edit_or_send(event, "⚠️ Помещение не найдено (список мог обновиться). Напишите /start")
        return

    _, page, pages = paginate(room.equipment, page, EQUIPMENT_PAGE_SIZE)
    text = "🛠 Выберите необходимое оборудование:"
    if not room.equipment:
        text += "\n\nДля этого помещения нет оборудования — нажмите «Подтвердить»."
    keyboard = equipment_keyboard(
        room,
        booking.get("equipment", []),
        page,
        toggle="pusk_toggle_eq",
        page_action="pusk_eq_page",
        confirm="pusk_confirm_eq",
        back="pusk_back_to_description",
    )
    await edit_or_send(event, text + page_caption(page, pages), keyboard)


# ─────────────────────────────────────────────────────────────
# Обработчики
# ─────────────────────────────────────────────────────────────
async def on_equipment(event: MessageEvent, sess: Session, payload: dict) -> None:
    await sess.save("pusk_equipment")
    await _show_equipment(event, sess)


async def on_eq_page(event: MessageEvent, sess: Session, payload: dict) -> None:
    await _show_equipment(event, sess, _int(payload.get("p")) or 0)


async def on_toggle_eq(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.setdefault("pusk_booking", {})
    room = get_snapshot().rooms.get(_int(booking.get("room_id")) or -1)
    equipment = None
    if room:
        equipment = next((e for e in room.equipment if e.id == _int(payload.get("e"))), None)
    if equipment:
        selected = booking.setdefault("equipment", [])
        if equipment.name in selected:
            selected.remove(equipment.name)
        else:
            selected.append(equipment.name)
        await sess.save()
    await _show_equipment(event, sess, _int(payload.get("p")) or 0)


async def on_confirm_eq(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.setdefault("pusk_booking", {})
    if not booking.get("equipment"):
        booking["equipment"] = ["Без оборудования"]

    await sess.save("pusk_visitors_question")
    keyboard = (
        Keyboard(inline=True)
        .add(Callback("✅ Да, известны", {"action": "pusk_visitors_yes"}))
        .add(Callback("❌ Нет", {"action": "pusk_visitors_no"}))
        .get_json()
    )
    await edit_or_send(
        event,
        "Известны ли заранее посетители мероприятия?\n"
        "(ФИО, возраст, учебное заведение, институт)",
        keyboard,
    )


async def on_back_to_description(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.get("pusk_booking") or {}
    await sess.save("pusk_description")
    await edit_or_send(event, _description(booking), _description_keyboard())


async def on_visitors_yes(event: MessageEvent, sess: Session, payload: dict) -> None:
    sess.data.setdefault("pusk_booking", {})["visitors"] = []
    await sess.save("pusk_visitors_bulk")
    await edit_or_send(
        event,
        "📋 Введите список посетителей по шаблону:\n"
        "ФИО, Возраст, Учебное заведение, Институт\n\n"
        "Каждого нового посетителя пишите с новой строки.\n"
        "Если института нет (другой вуз/школа), вместо него поставьте прочерк «-».\n\n"
        "Пример:\n"
        "Иванов Иван Иванович, 20, МГУ, Физфак\n"
        "Петров Петр Петрович, 17, Школа №1, -",
    )


async def on_visitors_no(event: MessageEvent, sess: Session, payload: dict) -> None:
    sess.data.setdefault("pusk_booking", {})["visitors"] = []
    await sess.save("pusk_datetime")
    await edit_or_send(event, DATETIME_PROMPT)


async def on_add_visitor_bulk(event: MessageEvent, sess: Session, payload: dict) -> None:
    await sess.save("pusk_visitors_bulk")
    await edit_or_send(
        event,
        "📋 Отправьте новый список посетителей в том же формате:\n"
        "ФИО, Возраст, Учебное заведение, Институт (или -)",
    )


async def on_finish_visitors(event: MessageEvent, sess: Session, payload: dict) -> None:
    await sess.save("pusk_datetime")
    await edit_or_send(event, DATETIME_PROMPT)


async def on_consent_yes(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.setdefault("pusk_booking", {})
    booking["personal_data_consent"] = True

    keyboard = (
        Keyboard(inline=True)
        .add(Callback("✅ Отправить на одобрение", {"action": "pusk_send"}))
        .row()
        .add(Callback("❌ Отменить", {"action": "pusk_cancel"}))
        .get_json()
    )
    await sess.save("pusk_confirm")
    await edit_or_send(
        event, format_pusk_preview(sess.user, sess.event_info, booking), keyboard
    )


async def on_consent_no(event: MessageEvent, sess: Session, payload: dict) -> None:
    await _reset_to_menu(sess)
    await edit_or_send(
        event,
        "❌ Без согласия на обработку персональных данных заявку отправить невозможно.\n\n"
        "Бронирование отменено.",
    )


async def on_send(event: MessageEvent, sess: Session, payload: dict) -> None:
    booking = sess.data.get("pusk_booking") or {}
    # Убираем кнопки с сообщения-сводки, чтобы их нельзя было нажать повторно
    await edit_or_send(event, format_pusk_preview(sess.user, sess.event_info, booking))

    await send_pusk_application(event.ctx_api, sess)
    await _reset_to_menu(sess)


async def on_cancel(event: MessageEvent, sess: Session, payload: dict) -> None:
    await _reset_to_menu(sess)
    await edit_or_send(event, "❌ Бронирование «Пуск» отменено.")


HANDLERS: Dict[str, Handler] = {
    "pusk_equipment": on_equipment,
    "pusk_eq_page": on_eq_page,
    "pusk_toggle_eq": on_toggle_eq,
    "pusk_confirm_eq": on_confirm_eq,
    "pusk_back_to_description": on_back_to_description,
    "pusk_visitors_yes": on_visitors_yes,
    "pusk_visitors_no": on_visitors_no,
    "pusk_add_visitor_bulk": on_add_visitor_bulk,
    "pusk_finish_visitors": on_finish_visitors,
    "pusk_consent_yes": on_consent_yes,
    "pusk_consent_no": on_consent_no,
    "pusk_send": on_send,
    "pusk_cancel": on_cancel,
}


@pusk_callback_labeler.raw_event("message_event", dataclass=MessageEvent, blocking=False)
async def pusk_callback_handler(event: MessageEvent) -> None:
    payload = event.payload or {}
    action = payload.get("action")
    if action not in HANDLERS:
        return  # не наша кнопка

    logger.debug("[PUSK CALLBACK] user=%s action=%s", event.user_id, action)

    async with user_lock(event.user_id):
        sess = await Session.load(event.user_id)

        if sess.state not in ACTION_STATES[action]:
            await answer_event(event, "Эта кнопка уже неактуальна. Напишите /start")
            return

        await answer_event(event)
        try:
            await HANDLERS[action](event, sess, payload)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в обработчике кнопки %s", action)
            await edit_or_send(event, "⚠️ Что-то пошло не так. Напишите /start и начните заново.")
