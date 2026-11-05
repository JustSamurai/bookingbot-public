"""Кнопки «Одобрить» / «Отклонить» в чате модераторов."""
import asyncio
import logging

from vkbottle.bot import BotLabeler, MessageEvent

import config
from database.user_db import ORDER_APPROVED, ORDER_PENDING, ORDER_REJECTED, get_order
from handlers.moderation_state import PENDING, PendingDecision
from utils.vk_helpers import answer_event

logger = logging.getLogger(__name__)

admin_callback_labeler = BotLabeler()


@admin_callback_labeler.raw_event("message_event", dataclass=MessageEvent, blocking=False)
async def moderation_callback_handler(event: MessageEvent) -> None:
    payload = event.payload or {}
    action = payload.get("action")
    if action not in ("approve", "reject"):
        return  # не наша кнопка

    if event.peer_id != config.ADMIN_PEER_ID:
        await answer_event(event, "Эта кнопка доступна только в чате модераторов.")
        return

    try:
        ticket = int(payload["ticket_number"])
    except (KeyError, TypeError, ValueError):
        await answer_event(event, "Некорректная кнопка: нет номера заявки.")
        return

    order = await asyncio.to_thread(get_order, ticket)
    if not order:
        await answer_event(event, f"Заявка №{ticket} не найдена в базе.")
        return
    if order["status"] != ORDER_PENDING:
        await answer_event(event, f"Заявка №{ticket} уже обработана: {order['status']}")
        return

    await answer_event(event)

    status = ORDER_APPROVED if action == "approve" else ORDER_REJECTED
    PENDING[(event.peer_id, event.user_id)] = PendingDecision(
        ticket_number=ticket,
        status=status,
        peer_id=event.peer_id,
        conversation_message_id=event.conversation_message_id,
    )

    await event.ctx_api.messages.send(
        peer_id=event.peer_id,
        message=(
            f"📝 [id{event.user_id}|Модератор], напишите комментарий к решению "
            f"по заявке №{ticket} (статус: {status}).\n"
            "Отправьте «-», если комментарий не нужен, или «отмена», чтобы передумать."
        ),
        random_id=0,
    )
