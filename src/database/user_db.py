"""Работа с пользователями, состояниями диалога и заявками (orders)."""
import json
import logging
from typing import Any, Dict, Optional

from database.connection import connect

logger = logging.getLogger(__name__)

# Статусы заявок
ORDER_PENDING = "В обработке"
ORDER_APPROVED = "ОДОБРЕНА"
ORDER_REJECTED = "ОТКЛОНЕНА"
ORDER_SEND_FAILED = "Ошибка отправки"


# ──────────────────────────────────────────────────────────────
# Пользователи
# ──────────────────────────────────────────────────────────────
def get_user(vk_id: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, name, phone, student_group, institute, position,
                   division, link AS profile_link, age, educational_institution
            FROM users
            WHERE id = ?
            """,
            (vk_id,),
        ).fetchone()
    return dict(row) if row else None


def save_user(
    vk_id: int,
    *,
    name: str = "",
    age: Optional[int] = None,
    phone: str = "",
    educational_institution: str = "",
    group: str = "",
    institute: str = "",
    position: str = "",
    division: str = "",
    link: Optional[str] = None,
) -> None:
    def clean(value: Optional[str]) -> Optional[str]:
        value = (value or "").strip()
        return value or None

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, name, phone, student_group, institute, position, division,
                link, age, educational_institution
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                phone = excluded.phone,
                student_group = excluded.student_group,
                institute = excluded.institute,
                position = excluded.position,
                division = excluded.division,
                link = excluded.link,
                age = excluded.age,
                educational_institution = excluded.educational_institution
            """,
            (
                vk_id,
                clean(name),
                clean(phone),
                clean(group),
                clean(institute),
                clean(position),
                clean(division),
                link,
                age,
                clean(educational_institution),
            ),
        )
    logger.debug("Профиль пользователя %s сохранён", vk_id)


# ──────────────────────────────────────────────────────────────
# Состояние диалога
# ──────────────────────────────────────────────────────────────
def get_user_state(vk_id: int) -> Dict[str, Any]:
    """Возвращает {'state': str, 'data': dict}. Для нового пользователя — main_menu."""
    with connect() as conn:
        row = conn.execute(
            "SELECT state, data FROM user_states WHERE vk_id = ?", (vk_id,)
        ).fetchone()

    if not row:
        return {"state": "main_menu", "data": {}}

    try:
        data = json.loads(row["data"]) if row["data"] else {}
    except json.JSONDecodeError:
        logger.error("Битый JSON в user_states для vk_id=%s", vk_id)
        data = {}
    return {"state": row["state"], "data": data}


def save_user_state(vk_id: int, state: str, data: Dict[str, Any]) -> None:
    payload = json.dumps(data, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_states (vk_id, state, data, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (vk_id, state, payload),
        )
    logger.debug("[STATE] vk_id=%s state=%s keys=%s", vk_id, state, list(data.keys()))


# ──────────────────────────────────────────────────────────────
# Заявки
# ──────────────────────────────────────────────────────────────
def create_order(vk_id: int, kind: str, payload: Dict[str, Any]) -> int:
    """Создаёт заявку со снимком данных и возвращает её номер."""
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO orders (vk_id, kind, payload) VALUES (?, ?, ?)",
            (vk_id, kind, json.dumps(payload, ensure_ascii=False)),
        )
        return int(cursor.lastrowid)


def get_order(ticket: int) -> Optional[Dict[str, Any]]:
    with connect() as conn:
        row = conn.execute(
            "SELECT id, vk_id, status, kind, payload FROM orders WHERE id = ?",
            (ticket,),
        ).fetchone()
    if not row:
        return None

    order = dict(row)
    try:
        order["payload"] = json.loads(row["payload"]) if row["payload"] else {}
    except json.JSONDecodeError:
        order["payload"] = {}
    return order


def claim_order(ticket: int, status: str, moderator_id: int, comment: str) -> bool:
    """
    Атомарно выставляет решение. True — решение принято этим вызовом,
    False — заявка уже обработана (или не существует).
    """
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE orders
            SET status = ?, moderator_id = ?, moderator_comment = ?
            WHERE id = ? AND status = ?
            """,
            (status, moderator_id, comment, ticket, ORDER_PENDING),
        )
        return cursor.rowcount == 1


def set_order_status(ticket: int, status: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE orders SET status = ? WHERE id = ?", (status, ticket))
