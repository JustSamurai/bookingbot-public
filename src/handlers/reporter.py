"""Отправка заявки основной цепочки модераторам."""
import asyncio
import logging
from typing import Optional

import config
from database.user_db import ORDER_SEND_FAILED, create_order, set_order_status
from keyboards.generator import moderation_keyboard
from utils.formatters import format_application
from utils.session import Session
from utils.vk_helpers import clip

logger = logging.getLogger(__name__)


async def send_main_application(api, sess: Session) -> Optional[int]:
    """Сохраняет заявку и отправляет карточку в чат модераторов. Возвращает номер или None."""
    user = sess.user
    event_info = sess.event_info
    bookings = sess.data.get("bookings") or []

    ticket = await asyncio.to_thread(
        create_order,
        sess.vk_id,
        "main",
        {"user": user, "event_info": event_info, "bookings": bookings},
    )

    try:
        await api.messages.send(
            peer_id=config.ADMIN_PEER_ID,
            message=clip(format_application(ticket, user, event_info, bookings)),
            keyboard=moderation_keyboard(sess.vk_id, ticket),
            random_id=0,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить заявку №%s в чат %s", ticket, config.ADMIN_PEER_ID)
        await asyncio.to_thread(set_order_status, ticket, ORDER_SEND_FAILED)
        return None

    return ticket
