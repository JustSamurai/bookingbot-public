"""
Реестр помещений: корпуса → аудитории → оборудование.

Читается из БД одним снимком (3 запроса). Идентификаторы в кнопках — это ID из БД,
поэтому они стабильны между перезагрузками реестра. После любой правки через
/insert, /update, /delete реестр перечитывается автоматически.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List

from database.connection import connect

logger = logging.getLogger(__name__)

# Эти названия оборудования в списках не показываются
_HIDDEN_EQUIPMENT = {"", "-", "ничего нет"}


@dataclass(frozen=True)
class Equipment:
    id: int
    name: str
    count: int


@dataclass
class Room:
    id: int
    name: str
    location_id: int
    location_name: str
    equipment: List[Equipment] = field(default_factory=list)


@dataclass
class Location:
    id: int
    name: str
    rooms: List[Room] = field(default_factory=list)


@dataclass
class Snapshot:
    locations: Dict[int, Location] = field(default_factory=dict)
    rooms: Dict[int, Room] = field(default_factory=dict)

    def sorted_locations(self) -> List[Location]:
        return sorted(self.locations.values(), key=lambda loc: loc.name.lower())


_snapshot = Snapshot()


def get_snapshot() -> Snapshot:
    return _snapshot


def _to_int(value, default: int = 1) -> int:
    try:
        return int(value) if value else default
    except (TypeError, ValueError):
        return default


def build_snapshot() -> Snapshot:
    with connect() as conn:
        loc_rows = conn.execute("SELECT id, name FROM locations").fetchall()
        room_rows = conn.execute(
            "SELECT id, name, locations_id FROM rooms ORDER BY id"
        ).fetchall()
        eq_rows = conn.execute(
            """
            SELECT re.room_id, e.id AS eq_id, e.name, re.count
            FROM rooms_equipment re
            JOIN equipment e ON e.id = re.equipment_id
            ORDER BY e.name
            """
        ).fetchall()

    snapshot = Snapshot()
    for row in loc_rows:
        name = (row["name"] or "").strip()
        if name:
            snapshot.locations[row["id"]] = Location(row["id"], name)

    for row in room_rows:
        location = snapshot.locations.get(row["locations_id"])
        name = (row["name"] or "").strip()
        if not location or not name:
            continue
        room = Room(row["id"], name, location.id, location.name)
        location.rooms.append(room)
        snapshot.rooms[room.id] = room

    for row in eq_rows:
        room = snapshot.rooms.get(row["room_id"])
        name = (row["name"] or "").strip()
        if not room or name.lower() in _HIDDEN_EQUIPMENT:
            continue
        room.equipment.append(Equipment(row["eq_id"], name, _to_int(row["count"])))

    return snapshot


def reload_registry() -> None:
    """Синхронная загрузка (при старте бота)."""
    global _snapshot
    _snapshot = build_snapshot()
    logger.info(
        "Реестр загружен: корпусов %d, аудиторий %d",
        len(_snapshot.locations),
        len(_snapshot.rooms),
    )


async def reload_registry_async() -> None:
    """Перечитывает БД в потоке и атомарно подменяет снимок."""
    global _snapshot
    _snapshot = await asyncio.to_thread(build_snapshot)
    logger.info("Реестр обновлён после правки БД")
