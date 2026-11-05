"""Профиль заявителя: преобразование между сессией и таблицей users."""
import re
from typing import Any, Dict, Optional, Tuple

from database.user_db import save_user

REQUIRED_FIELDS = ("name", "age", "phone", "educational_institution", "student_id")


def split_student_info(text: str) -> Tuple[str, str, str]:
    """
    «ТБ25-01, ИИТК» → (группа, институт, должность).
      • группа    — содержит дефис и цифру (ТБ25-01)
      • институт  — короткое слово капсом (ИИТК, ЦСО)
      • должность — всё остальное
    """
    group = institute = ""
    positions = []
    for item in re.split(r"[,/]", text or ""):
        item = item.strip()
        if not item:
            continue
        if not group and "-" in item and any(ch.isdigit() for ch in item):
            group = item
        elif not institute and len(item) <= 6 and item.isupper():
            institute = item
        else:
            positions.append(item)
    return group, institute, ", ".join(positions)


def join_student_info(group: str, institute: str, position: str) -> str:
    return ", ".join(part for part in (group, institute, position) if part)


def profile_from_row(row: Optional[Dict[str, Any]], vk_id: int) -> Dict[str, Any]:
    """Собирает профиль для сессии из строки таблицы users."""
    if not row:
        return {"vk_id": vk_id}
    return {
        "vk_id": vk_id,
        "name": row.get("name") or "",
        "age": row.get("age"),
        "phone": row.get("phone") or "",
        "educational_institution": row.get("educational_institution") or "",
        "student_id": join_student_info(
            row.get("student_group") or "",
            row.get("institute") or "",
            row.get("position") or "",
        ),
        "division": row.get("division") or "",
    }


def is_profile_complete(profile: Dict[str, Any]) -> bool:
    return all(profile.get(key) not in (None, "", 0) for key in REQUIRED_FIELDS)


def save_profile(profile: Dict[str, Any]) -> None:
    """Синхронная запись профиля в БД (вызывать через asyncio.to_thread)."""
    vk_id = int(profile["vk_id"])
    group, institute, position = split_student_info(profile.get("student_id", ""))
    save_user(
        vk_id,
        name=str(profile.get("name", "")),
        age=profile.get("age"),
        phone=str(profile.get("phone", "")),
        educational_institution=str(profile.get("educational_institution", "")),
        group=group,
        institute=institute,
        position=position,
        division=str(profile.get("division", "")),
        link=f"https://vk.com/id{vk_id}",
    )
