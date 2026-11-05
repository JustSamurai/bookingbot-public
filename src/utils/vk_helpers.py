"""Мелкие помощники для работы с VK API."""
import json
import logging
import re
from typing import List, Optional

from vkbottle.bot import Message, MessageEvent

logger = logging.getLogger(__name__)

SAFE_LIMIT = 4000  # лимит VK — 4096 символов на сообщение

_MENTION_RE = re.compile(r"^\s*\[(?:club|public)\d+\|[^\]]*\]\s*[,:]?\s*", re.I)

START_COMMANDS = {"/start", "start", "начать"}


def is_start_command(text: Optional[str]) -> bool:
    return (text or "").strip().lower() in START_COMMANDS


def strip_mention(text: Optional[str]) -> str:
    """Убирает «[club123|@bot]» в начале сообщения из беседы."""
    return _MENTION_RE.sub("", text or "").strip()


def clip(text: str, limit: int = SAFE_LIMIT) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def split_text(text: str, limit: int = SAFE_LIMIT) -> List[str]:
    chunks: List[str] = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


async def answer_long(message: Message, text: str) -> None:
    for chunk in split_text(text):
        await message.answer(chunk)


async def answer_event(event: MessageEvent, snackbar: Optional[str] = None) -> None:
    """Обязательный ответ на нажатие callback-кнопки (иначе у кнопки крутится загрузка)."""
    params = {}
    if snackbar:
        params["event_data"] = json.dumps(
            {"type": "show_snackbar", "text": snackbar[:90]}, ensure_ascii=False
        )
    try:
        await event.ctx_api.messages.send_message_event_answer(
            event_id=event.event_id,
            user_id=event.user_id,
            peer_id=event.peer_id,
            **params,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось ответить на событие кнопки")


async def edit_or_send(
    event: MessageEvent, text: str, keyboard: Optional[str] = None
) -> None:
    """Редактирует сообщение с кнопкой; если не вышло — отправляет новое."""
    try:
        await event.ctx_api.messages.edit(
            peer_id=event.peer_id,
            conversation_message_id=event.conversation_message_id,
            message=clip(text),
            keyboard=keyboard,
        )
    except Exception:  # noqa: BLE001
        logger.exception("messages.edit не удался, отправляю новое сообщение")
        await event.ctx_api.messages.send(
            peer_id=event.peer_id,
            message=clip(text),
            keyboard=keyboard,
            random_id=0,
        )
