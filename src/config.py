"""Конфигурация бота: токены из .env, пути к файлам и константы."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


def _load_env() -> None:
    """Ищет .env в нескольких привычных местах; берёт первый найденный."""
    candidates = (
        BASE_DIR / ".env",
        BASE_DIR / "config" / ".env",
        BASE_DIR.parent / "config" / ".env",
    )
    for path in candidates:
        if path.is_file():
            load_dotenv(dotenv_path=path)
            return
    load_dotenv()  # последняя попытка: .env в текущей рабочей папке


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"В .env не задана обязательная переменная {name}")
    return value


_load_env()

# ── Токены и идентификаторы VK ───────────────────────────────
TOKEN_MAIN = _required("VK_TOKEN_MAIN")
TOKEN_OVERDRIVE = os.getenv("VK_TOKEN_OVERDRIVE")  # тестовый токен, не обязателен
GROUP_ID = int(_required("GROUP_ID"))
ADMIN_PEER_ID = int(_required("ADMIN_PEER_ID"))  # чат модераторов

ADMIN_IDS = int(_required("ADMIN_ID"))

# ── Файлы (лежат рядом с main.py) ────────────────────────────
def _find_database() -> Path:
    """Берёт существующий файл БД рядом с main.py (поддержаны оба написания имени)."""
    for name in ("booking.db", "bookimg.db"):
        if (BASE_DIR / name).is_file():
            return BASE_DIR / name
    return BASE_DIR / "booking.db"  # файла нет — создастся новый


DATABASE_PATH = _find_database()
RULES_PHOTO = BASE_DIR / "pusk_rules.jpg"  # картинка с правилами «Пуск»

CALENDAR_URL = "vk.com/@umpsibsau-bronirovanie"

# ── Модуль «Пуск» ────────────────────────────────────────────
# Аудитория считается «Пуском», если в её названии есть этот фрагмент
# (без учёта регистра и разницы е/ё).
PUSK_ROOM_MARKER = "пуск"
