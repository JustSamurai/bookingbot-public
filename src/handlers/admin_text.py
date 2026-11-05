"""Комментарий модератора к решению по заявке."""
import asyncio
import logging

from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from database.user_db import claim_order, get_order
from handlers.moderation_state import PENDING, get_pending
from utils.formatters import format_order_processed
from utils.vk_helpers import clip, strip_mention

logger = logging.getLogger(__name__)

admin_text_labeler = BotLabeler()

CANCEL_WORDS = {"отмена", "/cancel"}


class ModeratorCommentRule(ABCRule[Message]):
    """Модератор нажал кнопку в этом чате и теперь пишет комментарий."""

    async def check(self, message: Message) -> bool:
        if get_pending(message.peer_id, message.from_id) is None:
            return False
        text = strip_mention(message.text)
        if not text:
            return False
        # Команды (/list, /insert …) остаются командами, кроме /cancel
        return not text.startswith("/") or text.lower() in CANCEL_WORDS


@admin_text_labeler.message(ModeratorCommentRule())
async def process_moderator_comment(message: Message) -> None:
    key = (message.peer_id, message.from_id)
    pending = PENDING.pop(key, None)  # забираем сразу — повторно не сработает
    if pending is None:
        return

    text = strip_mention(message.text)
    if text.lower() in CANCEL_WORDS:
        await message.answer(
            f"↩️ Решение по заявке №{pending.ticket_number} отменено. "
            "Нажмите кнопку на карточке заявки ещё раз."
        )
        return

    comment = "Без комментария" if text in ("-", "—") else text[:1000]
    status = pending.status
    ticket = pending.ticket_number

    # Атомарно фиксируем решение: если другой модератор успел раньше — claim вернёт False
    claimed = await asyncio.to_thread(claim_order, ticket, status, message.from_id, comment)
    if not claimed:
        await message.answer(f"⚠️ Заявка №{ticket} уже была обработана другим модератором.")
        return

    order = await asyncio.to_thread(get_order, ticket)
    if order is None:  # теоретически невозможно, но на всякий случай
        await message.answer(f"❌ Заявка №{ticket} пропала из базы.")
        return

    # 1. Уведомление заявителя
    delivered = True
    try:
        await message.ctx_api.messages.send(
            peer_id=order["vk_id"],
            message=(
                f"🔔 Обновление по вашей заявке №{ticket}\n\n"
                f"Статус: Заявка {status}\n"
                f"📝 Комментарий модератора: {comment}"
            ),
            random_id=0,
        )
    except Exception:  # noqa: BLE001
        delivered = False
        logger.exception("Не удалось уведомить пользователя %s о заявке №%s", order["vk_id"], ticket)

    # 2. Обновление карточки в чате модераторов
    try:
        updated = format_order_processed(order, status, comment, message.from_id)
        await message.ctx_api.messages.edit(
            peer_id=pending.peer_id,
            conversation_message_id=pending.conversation_message_id,
            message=clip(updated),
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось обновить карточку заявки №%s", ticket)

    # 3. Итог модератору
    result = (
        f"✅ Заявка №{ticket}: {status}.\n"
        f"Комментарий: {comment}\n"
    )
    result += (
        "Решение отправлено заявителю."
        if delivered
        else "⚠️ Не удалось доставить сообщение заявителю (возможно, у него закрыты ЛС). "
        "Свяжитесь с ним лично."
    )
    await message.answer(result)
