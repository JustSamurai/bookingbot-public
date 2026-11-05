import sqlite3
from contextlib import contextmanager
from typing import Iterator

import config


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.DATABASE_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Соединение с авто-commit при успехе, rollback при ошибке и гарантированным close."""
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
