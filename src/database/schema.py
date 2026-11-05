"""Создание таблиц (если их нет) и безопасная миграция таблицы orders."""
import logging

from database.connection import connect

logger = logging.getLogger(__name__)

TABLES = [
    """CREATE TABLE IF NOT EXISTS users (
        id                      INTEGER PRIMARY KEY,
        name                    TEXT,
        age                     INTEGER,
        phone                   TEXT,
        educational_institution TEXT,
        student_group           TEXT,
        institute               TEXT,
        position                TEXT,
        division                TEXT,
        link                    TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS user_states (
        vk_id      INTEGER  PRIMARY KEY,
        state      TEXT     NOT NULL DEFAULT 'main_menu',
        data       TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS locations (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS rooms (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT,
        locations_id INTEGER REFERENCES locations (id)
    )""",
    """CREATE TABLE IF NOT EXISTS equipment (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS rooms_equipment (
        room_id      INTEGER REFERENCES rooms (id) ON DELETE CASCADE,
        equipment_id INTEGER REFERENCES equipment (id) ON DELETE CASCADE,
        count        INTEGER,
        PRIMARY KEY (room_id, equipment_id)
    )""",
    """CREATE TABLE IF NOT EXISTS orders (
        id         INTEGER   PRIMARY KEY AUTOINCREMENT,
        vk_id      INTEGER   NOT NULL,
        status     TEXT      DEFAULT 'В обработке',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]

# Новые колонки orders: снимок заявки (JSON), тип заявки и след модерации.
# Добавляются только если их ещё нет — существующие данные не затрагиваются.
ORDER_EXTRA_COLUMNS = {
    "kind": "TEXT",
    "payload": "TEXT",
    "moderator_id": "INTEGER",
    "moderator_comment": "TEXT",
}


def init_db() -> None:
    with connect() as conn:
        for sql in TABLES:
            conn.execute(sql)

        existing = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        for column, column_type in ORDER_EXTRA_COLUMNS.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {column} {column_type}")
                logger.info("Миграция: в orders добавлена колонка %s", column)
