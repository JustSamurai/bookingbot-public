"""Разбор пользовательского ввода: дата/время и список посетителей."""
import re
from dataclasses import dataclass
from datetime import date, time
from typing import Dict, List, Optional, Tuple

FORMAT_HINT = (
    "Пожалуйста, отправьте сообщение строго по шаблону:\n"
    "07.03.2026 с 14:00 до 16:30"
)

_SLOT_RE = re.compile(
    r"(\d{1,2})\.(\d{1,2})\.(\d{4})\D+?(\d{1,2}):(\d{2})\D+?(\d{1,2}):(\d{2})"
)


@dataclass(frozen=True)
class TimeSlot:
    day: date
    start: time
    end: time

    @property
    def date_str(self) -> str:
        return self.day.strftime("%d.%m.%Y")

    @property
    def start_str(self) -> str:
        return self.start.strftime("%H:%M")

    @property
    def end_str(self) -> str:
        return self.end.strftime("%H:%M")

    @property
    def text(self) -> str:
        return f"{self.date_str} с {self.start_str} до {self.end_str}"


def parse_time_slot(
    text: str, today: Optional[date] = None
) -> Tuple[Optional[TimeSlot], Optional[str]]:
    """Возвращает (TimeSlot, None) или (None, текст_ошибки)."""
    match = _SLOT_RE.search(text or "")
    if not match:
        return None, f"❌ Неверный формат даты или времени.\n\n{FORMAT_HINT}"

    d, mo, y, h1, m1, h2, m2 = (int(x) for x in match.groups())
    try:
        slot = TimeSlot(date(y, mo, d), time(h1, m1), time(h2, m2))
    except ValueError:
        return None, (
            "❌ Введены несуществующие дата или время.\n"
            "Проверьте данные и попробуйте ещё раз."
        )

    if slot.start >= slot.end:
        return None, "❌ Время окончания не может быть раньше или равно времени начала!"
    if slot.day < (today or date.today()):
        return None, "❌ Нельзя бронировать прошедшую дату."
    return slot, None


_EMPTY_INSTITUTE = {"-", "—", "нет", ""}


def parse_visitors(text: str) -> Tuple[List[Dict], List[str]]:
    """
    Строки вида «ФИО, возраст, учебное заведение, институт (или -)».
    Возвращает (посетители, ошибки). Если есть ошибки — список нужно отправить заново.
    """
    lines = [line.strip() for line in (text or "").split("\n") if line.strip()]
    visitors: List[Dict] = []
    errors: List[str] = []

    for index, line in enumerate(lines, start=1):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 4:
            errors.append(
                f"Строка {index}: должно быть ровно 4 элемента через запятую "
                "(ФИО, возраст, вуз, институт)."
            )
            continue

        name, age_str, institution, institute_str = parts

        if len(name) < 5:
            errors.append(f"Строка {index} ({name}): ФИО слишком короткое.")
            continue
        if not age_str.isdigit() or not (10 <= int(age_str) <= 80):
            errors.append(
                f"Строка {index} ({name}): возраст должен быть числом от 10 до 80."
            )
            continue
        if len(institution) < 2:
            errors.append(
                f"Строка {index} ({name}): слишком короткое название учебного заведения."
            )
            continue

        institute = None if institute_str.lower() in _EMPTY_INSTITUTE else institute_str
        visitors.append(
            {
                "name": name,
                "age": int(age_str),
                "institution": institution,
                "institute": institute,
            }
        )

    if not lines:
        errors.append("Вы отправили пустое сообщение.")
    return visitors, errors
