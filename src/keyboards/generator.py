"""
Генераторы inline-клавиатур.

Ограничения VK для inline-клавиатуры: до 6 рядов и до 10 кнопок суммарно,
поэтому длинные списки разбиваются на страницы. В payload кладём только короткие
ID, а не названия (лимит payload — 255 байт).
"""
import math
from typing import List, Optional, Sequence, Tuple, TypeVar

from vkbottle import Callback, Keyboard

from keyboards.registry import Location, Room

T = TypeVar("T")

LABEL_LIMIT = 40
LIST_PAGE_SIZE = 6       # корпуса и аудитории
EQUIPMENT_PAGE_SIZE = 5  # оборудование (ещё «назад», навигация и «подтвердить»)


class _Builder:
    """Обёртка над Keyboard: row() не создаёт пустых рядов."""

    def __init__(self) -> None:
        self._kb = Keyboard(inline=True)
        self._in_row = 0

    def add(self, button: Callback) -> "_Builder":
        self._kb.add(button)
        self._in_row += 1
        return self

    def row(self) -> "_Builder":
        if self._in_row:
            self._kb.row()
            self._in_row = 0
        return self

    def json(self) -> str:
        return self._kb.get_json()


def _label(text: str) -> str:
    return text if len(text) <= LABEL_LIMIT else text[: LABEL_LIMIT - 1] + "…"


def paginate(items: Sequence[T], page: int, size: int) -> Tuple[List[T], int, int]:
    """Возвращает (элементы страницы, нормализованная страница, всего страниц)."""
    pages = max(1, math.ceil(len(items) / size))
    page = min(max(page, 0), pages - 1)
    return list(items[page * size : (page + 1) * size]), page, pages


def _nav_row(kb: _Builder, page: int, pages: int, action: str) -> None:
    if pages <= 1:
        return
    kb.row()
    if page > 0:
        kb.add(Callback("◀ Пред.", {"action": action, "p": page - 1}))
    if page < pages - 1:
        kb.add(Callback("След. ▶", {"action": action, "p": page + 1}))
    kb.row()


def page_caption(page: int, pages: int) -> str:
    return f"\n\nСтраница {page + 1} из {pages}" if pages > 1 else ""


# ──────────────────────────────────────────────────────────────
# Основная цепочка
# ──────────────────────────────────────────────────────────────
def locations_keyboard(locations: Sequence[Location], page: int = 0) -> str:
    items, page, pages = paginate(locations, page, LIST_PAGE_SIZE)
    kb = _Builder()
    for i, loc in enumerate(items):
        kb.add(Callback(_label(loc.name), {"action": "select_location", "id": loc.id}))
        if i % 2 == 1:
            kb.row()
    kb.row()
    _nav_row(kb, page, pages, "loc_page")
    kb.add(Callback("❌ Отменить", {"action": "cancel"}))
    return kb.json()


def rooms_keyboard(location: Location, page: int = 0) -> str:
    items, page, pages = paginate(location.rooms, page, LIST_PAGE_SIZE)
    kb = _Builder()
    for i, room in enumerate(items):
        kb.add(Callback(_label(room.name), {"action": "select_room", "id": room.id}))
        if i % 2 == 1:
            kb.row()
    kb.row()
    _nav_row(kb, page, pages, "room_page")
    kb.add(Callback("← Назад", {"action": "back_to_locations"}))
    kb.add(Callback("❌ Отменить", {"action": "cancel"}))
    return kb.json()


# ──────────────────────────────────────────────────────────────
# Выбор оборудования (общий для основной цепочки и «Пуска»)
# ──────────────────────────────────────────────────────────────
def equipment_keyboard(
    room: Room,
    selected: Sequence[str],
    page: int,
    *,
    toggle: str,
    page_action: str,
    confirm: str,
    back: str,
    cancel: Optional[str] = None,
) -> str:
    items, page, pages = paginate(room.equipment, page, EQUIPMENT_PAGE_SIZE)
    kb = _Builder()

    kb.add(Callback("← Назад", {"action": back}))
    if cancel:
        kb.add(Callback("❌ Отменить", {"action": cancel}))
    kb.row()

    for i, eq in enumerate(items):
        text = eq.name if eq.count <= 1 else f"{eq.name} (×{eq.count})"
        if eq.name in selected:
            text = f"✅ {text}"
        kb.add(Callback(_label(text), {"action": toggle, "e": eq.id, "p": page}))
        if i % 2 == 1:
            kb.row()
    kb.row()

    _nav_row(kb, page, pages, page_action)
    kb.add(Callback("✅ Подтвердить", {"action": confirm}))
    return kb.json()


# ──────────────────────────────────────────────────────────────
# Модерация
# ──────────────────────────────────────────────────────────────
def moderation_keyboard(user_id: int, ticket_number: int) -> str:
    payload = {"user_id": user_id, "ticket_number": ticket_number}
    return (
        Keyboard(inline=True)
        .add(Callback("✅ Одобрить", {**payload, "action": "approve"}))
        .add(Callback("❌ Отклонить", {**payload, "action": "reject"}))
        .get_json()
    )
