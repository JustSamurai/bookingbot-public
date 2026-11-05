"""CRUD-операции модераторов над локациями, аудиториями и оборудованием."""
import functools
import logging
import sqlite3
from typing import Optional, Tuple

from database.connection import connect

logger = logging.getLogger(__name__)


def _guard(title: str):
    """Превращает любое исключение в понятное сообщение для чата модераторов."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Ошибка админ-операции: %s", title)
                return f"❌ Ошибка {title}: {exc}"

        return wrapper

    return decorator


def _find_one(
    conn: sqlite3.Connection, table: str, marker: str, label: str
) -> Tuple[Optional[sqlite3.Row], Optional[str]]:
    """Ищет запись по ID или по точному названию. table — только внутренние константы."""
    if marker.isdigit():
        rows = conn.execute(
            f"SELECT id, name FROM {table} WHERE id = ?", (int(marker),)
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT id, name FROM {table} WHERE name = ?", (marker,)
        ).fetchall()

    if not rows:
        return None, f"❌ {label} '{marker}' не найден(а) в базе!"
    if len(rows) > 1:
        return None, (
            f"⚠️ Найдено несколько записей с названием '{marker}'. "
            "Укажите ID (его видно в /list)."
        )
    return rows[0], None


# ──────────────────────────────────────────────────────────────
# READ
# ──────────────────────────────────────────────────────────────
@_guard("генерации карты базы")
def list_data() -> str:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT l.id AS loc_id, l.name AS loc_name,
                   r.id AS room_id, r.name AS room_name,
                   e.id AS eq_id, e.name AS eq_name,
                   re.count AS eq_count
            FROM locations l
            LEFT JOIN rooms r ON r.locations_id = l.id
            LEFT JOIN rooms_equipment re ON re.room_id = r.id
            LEFT JOIN equipment e ON re.equipment_id = e.id
            ORDER BY l.name, l.id, r.id, e.name
            """
        ).fetchall()

    if not rows:
        return "📭 База данных полностью пуста."

    tree: dict = {}
    for row in rows:
        loc = tree.setdefault(row["loc_id"], {"name": row["loc_name"], "rooms": {}})
        if row["room_id"] is None:
            continue
        room = loc["rooms"].setdefault(
            row["room_id"], {"name": row["room_name"], "equipment": []}
        )
        if row["eq_id"] is not None:
            room["equipment"].append(
                {"id": row["eq_id"], "name": row["eq_name"], "count": row["eq_count"]}
            )

    out = ["🗺️ ПОЛНАЯ КАРТА БАЗЫ ДАННЫХ:"]
    for loc_id, loc in tree.items():
        out.append(f"\n📍 [ID: {loc_id}] Корпус: {loc['name']}")
        out.append("═" * 25)
        if not loc["rooms"]:
            out.append(" └─ (Нет кабинетов)")
            continue
        for room_id, room in loc["rooms"].items():
            out.append(f" 🚪 [ID: {room_id}] Кабинет: {room['name']}")
            if not room["equipment"]:
                out.append(" └─ 🔹 (Нет оборудования)")
                continue
            for eq in room["equipment"]:
                try:
                    count = int(eq["count"]) if eq["count"] else 1
                except (TypeError, ValueError):
                    count = 1
                suffix = f" (кол-во: {count})" if count > 1 else ""
                out.append(f" └─ 🔹 [ID: {eq['id']}] {eq['name']}{suffix}")
    return "\n".join(out)


# ──────────────────────────────────────────────────────────────
# CREATE
# ──────────────────────────────────────────────────────────────
@_guard("добавления")
def insert_data(table_type: str, arguments: str) -> str:
    arguments = (arguments or "").strip()
    if not arguments:
        return "⚠️ Вы не передали параметры для добавления!"

    with connect() as conn:
        # --- локация ---
        if table_type == "loc":
            if conn.execute(
                "SELECT 1 FROM locations WHERE name = ?", (arguments,)
            ).fetchone():
                return f"⚠️ Локация '{arguments}' уже существует."
            cursor = conn.execute("INSERT INTO locations (name) VALUES (?)", (arguments,))
            return f"✅ Локация '{arguments}' успешно добавлена. (ID: {cursor.lastrowid})"

        # --- комната ---
        if table_type == "room":
            if "|" not in arguments:
                return "⚠️ Формат: /insert room ID_Корпуса (или Имя) | Номер кабинета"
            loc_marker, room_name = [p.strip() for p in arguments.split("|", 1)]
            if not room_name:
                return "⚠️ Не указано название кабинета."

            loc_row, error = _find_one(conn, "locations", loc_marker, "Локация")
            if error:
                return error

            if conn.execute(
                "SELECT 1 FROM rooms WHERE name = ? AND locations_id = ?",
                (room_name, loc_row["id"]),
            ).fetchone():
                return f"⚠️ Кабинет '{room_name}' уже есть в корпусе '{loc_row['name']}'."

            cursor = conn.execute(
                "INSERT INTO rooms (name, locations_id) VALUES (?, ?)",
                (room_name, loc_row["id"]),
            )
            return (
                f"✅ Комната '{room_name}' успешно привязана к корпусу "
                f"'{loc_row['name']}'. (ID комнаты: {cursor.lastrowid})"
            )

        # --- оборудование ---
        if table_type == "eq":
            parts = [p.strip() for p in arguments.split("|")]
            if len(parts) < 2 or not parts[0] or not parts[1]:
                return (
                    "⚠️ Формат: /insert eq ID_Кабинета | Название оборудования | Кол-во"
                )
            room_marker, eq_name = parts[0], parts[1]

            quantity = 1
            if len(parts) > 2 and parts[2]:
                try:
                    quantity = max(1, int(parts[2]))
                except ValueError:
                    return "⚠️ Ошибка! Количество оборудования должно быть целым числом."

            room_row, error = _find_one(conn, "rooms", room_marker, "Кабинет")
            if error:
                return error

            eq_row = conn.execute(
                "SELECT id FROM equipment WHERE name = ?", (eq_name,)
            ).fetchone()
            if eq_row:
                eq_id = eq_row["id"]
            else:
                eq_id = conn.execute(
                    "INSERT INTO equipment (name) VALUES (?)", (eq_name,)
                ).lastrowid

            conn.execute(
                """
                INSERT INTO rooms_equipment (room_id, equipment_id, count)
                VALUES (?, ?, ?)
                ON CONFLICT(room_id, equipment_id)
                DO UPDATE SET count = COALESCE(count, 0) + excluded.count
                """,
                (room_row["id"], eq_id, quantity),
            )
            return (
                f"✅ В кабинет '{room_row['name']}' (ID: {room_row['id']}) добавлено "
                f"оборудование '{eq_name}' (ID: {eq_id}) в количестве {quantity} шт."
            )

    return "⚠️ Неизвестный тип таблицы! Используйте: loc, room, eq"


# ──────────────────────────────────────────────────────────────
# UPDATE
# ──────────────────────────────────────────────────────────────
@_guard("обновления")
def update_data(table_type: str, target_id: int, new_value: str) -> str:
    new_value = (new_value or "").strip()
    if not new_value:
        return "⚠️ Новое значение не может быть пустым!"

    with connect() as conn:
        if table_type == "loc":
            cursor = conn.execute(
                "UPDATE locations SET name = ? WHERE id = ?", (new_value, target_id)
            )
            if cursor.rowcount:
                return f"✅ Название локации с ID {target_id} изменено на '{new_value}'"
            return f"❓ Локация с ID {target_id} не найдена."

        if table_type == "room":
            cursor = conn.execute(
                "UPDATE rooms SET name = ? WHERE id = ?", (new_value, target_id)
            )
            if cursor.rowcount:
                return f"✅ Название комнаты с ID {target_id} изменено на '{new_value}'"
            return f"❓ Комната с ID {target_id} не найдена."

        if table_type == "eq":
            # /update eq ID_Кабинета ID_Оборудования | Новое_кол-во
            if "|" in new_value:
                parts = [p.strip() for p in new_value.split("|")]
                if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                    return (
                        "⚠️ Формат: /update eq ID_Кабинета ID_Оборудования | Новое_кол-во"
                    )
                room_id, eq_id, new_count = target_id, int(parts[0]), int(parts[1])
                if new_count < 1:
                    return "⚠️ Количество должно быть не меньше 1."

                cursor = conn.execute(
                    "UPDATE rooms_equipment SET count = ? "
                    "WHERE room_id = ? AND equipment_id = ?",
                    (new_count, room_id, eq_id),
                )
                if not cursor.rowcount:
                    return f"❌ В кабинете ID {room_id} нет оборудования с ID {eq_id}!"
                return (
                    f"✅ Количество оборудования ID {eq_id} в кабинете ID {room_id} "
                    f"изменено на {new_count} шт."
                )

            # /update eq ID_Оборудования Новое название (меняется везде)
            cursor = conn.execute(
                "UPDATE equipment SET name = ? WHERE id = ?", (new_value, target_id)
            )
            if cursor.rowcount:
                return (
                    f"✅ Название оборудования с ID {target_id} изменено на "
                    f"'{new_value}' во всех кабинетах."
                )
            return f"❓ Оборудование с ID {target_id} не найдено в справочнике."

    return "⚠️ Неизвестный тип таблицы! Используйте: loc, room, eq"


# ──────────────────────────────────────────────────────────────
# DELETE
# ──────────────────────────────────────────────────────────────
@_guard("удаления")
def delete_data(table_type: str, target_id: int, extra_arguments: str = "") -> str:
    with connect() as conn:
        if table_type == "loc":
            # У rooms.locations_id нет ON DELETE CASCADE — удаляем комнаты вручную.
            rooms_deleted = conn.execute(
                "DELETE FROM rooms WHERE locations_id = ?", (target_id,)
            ).rowcount
            cursor = conn.execute("DELETE FROM locations WHERE id = ?", (target_id,))
            if cursor.rowcount:
                return (
                    f"🗑️ Локация с ID {target_id} удалена "
                    f"(вместе с комнатами: {rooms_deleted})."
                )
            return f"❓ Локация с ID {target_id} не найдена."

        if table_type == "room":
            cursor = conn.execute("DELETE FROM rooms WHERE id = ?", (target_id,))
            if cursor.rowcount:
                return f"🗑️ Кабинет с ID {target_id} удалён (связи с техникой зачищены)."
            return f"❓ Кабинет с ID {target_id} не найден."

        if table_type == "eq":
            second = (extra_arguments or "").replace("|", "").strip()
            if second.isdigit():
                # /delete eq ID_Кабинета | ID_Оборудования — убрать только из кабинета
                cursor = conn.execute(
                    "DELETE FROM rooms_equipment WHERE room_id = ? AND equipment_id = ?",
                    (target_id, int(second)),
                )
                if cursor.rowcount:
                    return (
                        f"🗑️ Оборудование с ID {second} удалено из кабинета "
                        f"с ID {target_id}."
                    )
                return f"❓ Связь кабинета {target_id} и оборудования {second} не найдена."

            cursor = conn.execute("DELETE FROM equipment WHERE id = ?", (target_id,))
            if cursor.rowcount:
                return (
                    f"🗑️ Оборудование с ID {target_id} полностью удалено "
                    "из справочника и всех кабинетов."
                )
            return f"❓ Оборудование с ID {target_id} не найдено."

    return "⚠️ Неизвестный тип таблицы! Используйте: loc, room, eq"
