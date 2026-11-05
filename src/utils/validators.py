import re
from typing import Any, Optional, Tuple

DASHES = {"-", "—", "–"}


def validate_phone(phone: str) -> str:
    """Возвращает 11 цифр (начиная с 7 или 8) либо пустую строку."""
    digits = re.sub(r"\D", "", phone or "")
    if re.match(r"^(7|8)\d{10}$", digits):
        return digits
    return ""


def validate_field(state: str, text: str) -> Tuple[Any, Optional[str]]:
    """
    Проверяет ответ пользователя на шаге анкеты / заявки.
    Возвращает (значение, None) или (None, текст_ошибки).
    """
    if not text:
        return None, "❌ Пожалуйста, отправьте ответ текстом."

    limit = 1500 if state == "list_people" else 300
    if len(text) > limit:
        return None, f"❌ Слишком длинный ответ (максимум {limit} символов)."

    if state == "name":
        if len(text) < 3:
            return None, "❌ Слишком короткое ФИО. Введите ФИО полностью."
        return text, None

    if state == "age":
        if not text.isdigit() or not (14 <= int(text) <= 80):
            return None, "❌ Возраст должен быть числом от 14 до 80. Попробуйте ещё раз."
        return int(text), None

    if state == "phone":
        digits = validate_phone(text)
        if not digits:
            return None, "❌ Ошибка в номере. Введите 11 цифр, начиная с 8 или 7."
        return digits, None

    if state == "division" and text in DASHES:
        return "", None  # «-» означает «нет объединения»

    return text, None
