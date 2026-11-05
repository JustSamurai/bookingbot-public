"""Отправка заявки «Пуск» модераторам и ответ пользователю с правилами."""
import asyncio
import logging
from typing import Optional

from vkbottle import PhotoMessageUploader

import config
from database.user_db import ORDER_SEND_FAILED, create_order, set_order_status
from keyboards.generator import moderation_keyboard
from utils.formatters import format_pusk_application
from utils.session import Session
from utils.vk_helpers import clip

logger = logging.getLogger(__name__)


async def _upload_rules_photo(api) -> Optional[str]:
    path = config.RULES_PHOTO
    if not path.is_file():
        logger.warning("Картинка с правилами не найдена: %s", path)
        return None
    try:
        return await PhotoMessageUploader(api).upload(file_source=str(path))
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось загрузить %s", path.name)
        return None


async def send_pusk_application(api, sess: Session) -> bool:
    """Сохраняет заявку, шлёт карточку модераторам и подтверждение пользователю."""
    vk_id = sess.vk_id
    booking = sess.data.get("pusk_booking") or {}
    user = sess.user
    event_info = sess.event_info

    ticket = await asyncio.to_thread(
        create_order,
        vk_id,
        "pusk",
        {"user": user, "event_info": event_info, "booking": booking},
    )

    try:
        await api.messages.send(
            peer_id=config.ADMIN_PEER_ID,
            message=clip(format_pusk_application(ticket, user, event_info, booking, vk_id)),
            keyboard=moderation_keyboard(vk_id, ticket),
            random_id=0,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить заявку «Пуск» №%s модераторам", ticket)
        await asyncio.to_thread(set_order_status, ticket, ORDER_SEND_FAILED)
        await api.messages.send(
            peer_id=vk_id,
            message="❌ Произошла ошибка при отправке заявки. Попробуйте позже или напишите /start",
            random_id=0,
        )
        return False

    text = (
        f"🚀 Заявка №{ticket} на Молодёжное пространство «Пуск» успешно отправлена!\n"
        "Ожидайте решения модератора."
    )
    attachment = await _upload_rules_photo(api)
    try:
        await api.messages.send(peer_id=vk_id, message=text, attachment=attachment, random_id=0)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось отправить пользователю картинку, шлю без неё")
        await api.messages.send(peer_id=vk_id, message=text, random_id=0)
    return True
