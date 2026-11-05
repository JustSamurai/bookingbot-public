"""Тексты заявок: карточки для модераторов, итоговые карточки, превью для пользователя."""
from typing import Any, Dict, List

DASH = "—"


def _v(value: Any) -> str:
    if value is None:
        return DASH
    text = str(value).strip()
    return text or DASH


def _status_emoji(status: str) -> str:
    return "✅" if "ОДОБР" in status.upper() else "❌"


# ──────────────────────────────────────────────────────────────
# Основная цепочка (обычные аудитории)
# ──────────────────────────────────────────────────────────────
def _profile_lines(user: Dict[str, Any]) -> List[str]:
    return [
        f"ФИО: {_v(user.get('name'))}",
        f"Телефон: {_v(user.get('phone'))}",
        f"Группа, институт / должность: {_v(user.get('student_id'))}",
        f"Объединение / подразделение: {_v(user.get('division'))}",
    ]


def _bookings_lines(bookings: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    for i, b in enumerate(bookings, 1):
        equipment = ", ".join(b.get("equipment") or []) or DASH
        lines.append(f"{i}. {_v(b.get('location'))} — {_v(b.get('room'))}")
        lines.append(f"   Оборудование: {equipment}")
        lines.append(f"   Время: {_v(b.get('datetime_text'))}")
        lines.append("")
    return lines


def format_application(
    ticket: int,
    user: Dict[str, Any],
    event_info: Dict[str, Any],
    bookings: List[Dict[str, Any]],
) -> str:
    lines = [f"📄 ЗАЯВКА НА БРОНИРОВАНИЕ №{ticket}", ""]
    lines += _profile_lines(user)
    lines += [
        "",
        f"Название мероприятия: {_v(event_info.get('event'))}",
        f"Ответственный: {_v(event_info.get('responsible'))}",
        "Участники из других вузов:",
        _v(event_info.get("list_people")),
        "",
    ]
    lines += _bookings_lines(bookings)
    lines += [
        f"Комментарий: {_v(event_info.get('comment'))}",
        "",
        f"Отправитель: vk.com/id{_v(user.get('vk_id'))}",
    ]
    return "\n".join(lines)


def format_application_processed(
    ticket: int,
    user: Dict[str, Any],
    event_info: Dict[str, Any],
    bookings: List[Dict[str, Any]],
    status: str,
    comment: str,
    moderator_id: int,
) -> str:
    lines = [f"{_status_emoji(status)} ЗАЯВКА №{ticket} ОБРАБОТАНА", f"Решение: {status}", ""]
    lines += _profile_lines(user)
    lines += [
        "",
        f"Название мероприятия: {_v(event_info.get('event'))}",
        f"Ответственный: {_v(event_info.get('responsible'))}",
        "",
    ]
    lines += _bookings_lines(bookings)
    lines += [
        f"Комментарий заявителя: {_v(event_info.get('comment'))}",
        "",
        f"Комментарий модератора: {comment}",
        f"Модератор: [id{moderator_id}|Профиль]",
        "",
        f"Отправитель: vk.com/id{_v(user.get('vk_id'))}",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Цепочка «Пуск»
# ──────────────────────────────────────────────────────────────
def _visitors_text(visitors: List[Dict[str, Any]]) -> str:
    if not visitors:
        return "Не указаны"
    rows = []
    for i, v in enumerate(visitors, 1):
        institute = f", {v['institute']}" if v.get("institute") else ""
        rows.append(
            f"{i}. {_v(v.get('name'))}, {_v(v.get('age'))} лет, "
            f"{_v(v.get('institution'))}{institute}"
        )
    return "\n".join(rows)


def _pusk_place(booking: Dict[str, Any]) -> List[str]:
    return [f"🏛 {_v(booking.get('room'))}", f"📍 {_v(booking.get('location'))}"]


def _pusk_details(booking: Dict[str, Any], event_info: Dict[str, Any]) -> List[str]:
    equipment = ", ".join(booking.get("equipment") or []) or "Без оборудования"
    consent = "✅ Да" if booking.get("personal_data_consent") else "❌ Нет"
    return [
        f"🎭 Мероприятие: {_v(booking.get('event_name') or event_info.get('event'))}",
        f"📅 Дата: {_v(booking.get('date'))}",
        f"⏰ Время: с {_v(booking.get('start_time'))} до {_v(booking.get('end_time'))}",
        f"👥 Планируемое кол-во участников: {_v(booking.get('participants_count'))}",
        "",
        f"🛠 Оборудование: {equipment}",
        "",
        "👥 Посетители:",
        _visitors_text(booking.get("visitors") or []),
        "",
        f"💬 Комментарий: {_v(booking.get('comment'))}",
        f"📄 Согласие на обработку ПДн: {consent}",
    ]


def _pusk_organizer(
    user: Dict[str, Any], event_info: Dict[str, Any], vk_id: Any
) -> List[str]:
    lines = [
        "────────────────────",
        f"👤 Организатор: {_v(user.get('name'))}",
        f"📞 Телефон: {_v(user.get('phone'))}",
        f"🎂 Возраст: {_v(user.get('age'))}",
        f"🏫 Учебное заведение: {_v(user.get('educational_institution'))}",
    ]
    if _v(event_info.get("responsible")) != DASH:
        lines.append(f"🙋 Ответственный: {_v(event_info.get('responsible'))}")
    if _v(event_info.get("list_people")) not in (DASH, "-"):
        lines.append(f"📋 Участники не из университета: {_v(event_info.get('list_people'))}")
    lines.append(f"🔗 https://vk.com/id{vk_id}")
    return lines


def format_pusk_preview(
    user: Dict[str, Any], event_info: Dict[str, Any], booking: Dict[str, Any]
) -> str:
    """Сводка для проверки пользователем перед отправкой."""
    lines = ["📋 Проверьте заявку", ""]
    lines += _pusk_place(booking)
    lines.append("")
    lines += _pusk_details(booking, event_info)
    lines += ["", f"Отправитель: {_v(user.get('name'))}"]
    return "\n".join(lines)


def format_pusk_application(
    ticket: int,
    user: Dict[str, Any],
    event_info: Dict[str, Any],
    booking: Dict[str, Any],
    vk_id: Any,
) -> str:
    """Карточка для модераторов."""
    lines = [f"🆕 Заявка №{ticket}"]
    lines += _pusk_place(booking)
    lines.append("")
    lines += _pusk_details(booking, event_info)
    lines.append("")
    lines += _pusk_organizer(user, event_info, vk_id)
    return "\n".join(lines)


def format_pusk_processed(
    ticket: int,
    user: Dict[str, Any],
    event_info: Dict[str, Any],
    booking: Dict[str, Any],
    vk_id: Any,
    status: str,
    comment: str,
    moderator_id: int,
) -> str:
    lines = [f"{_status_emoji(status)} Заявка №{ticket} — {status}"]
    lines += _pusk_place(booking)
    lines.append("")
    lines += _pusk_details(booking, event_info)
    lines.append("")
    lines += _pusk_organizer(user, event_info, vk_id)
    lines += [
        "",
        f"📝 Комментарий модератора: {comment}",
        f"Модератор: [id{moderator_id}|Профиль]",
    ]
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# Универсальная итоговая карточка по заявке из БД
# ──────────────────────────────────────────────────────────────
def format_order_processed(
    order: Dict[str, Any], status: str, comment: str, moderator_id: int
) -> str:
    ticket = order["id"]
    payload: Dict[str, Any] = order.get("payload") or {}
    user = payload.get("user") or {}
    event_info = payload.get("event_info") or {}

    if not payload:  # старая заявка без снимка данных
        return (
            f"{_status_emoji(status)} ЗАЯВКА №{ticket} ОБРАБОТАНА\n"
            f"Решение: {status}\n\n"
            f"Комментарий модератора: {comment}\n"
            f"Модератор: [id{moderator_id}|Профиль]\n\n"
            f"Отправитель: vk.com/id{order.get('vk_id')}"
        )

    if order.get("kind") == "pusk":
        return format_pusk_processed(
            ticket, user, event_info, payload.get("booking") or {},
            order.get("vk_id"), status, comment, moderator_id,
        )
    return format_application_processed(
        ticket, user, event_info, payload.get("bookings") or [],
        status, comment, moderator_id,
    )
