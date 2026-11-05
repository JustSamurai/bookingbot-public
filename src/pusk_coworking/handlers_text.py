"""Цепочка «Пуск»: текстовые сообщения пользователя."""
import logging

from vkbottle import Callback, Keyboard
from vkbottle.bot import BotLabeler, Message

from utils.parsers import parse_time_slot, parse_visitors
from utils.rules import PUSK_STATE_RULE
from utils.session import Session, user_lock
from utils.validators import DASHES

logger = logging.getLogger(__name__)

pusk_text_labeler = BotLabeler()

MAX_VISITORS = 40  # чтобы карточка модераторов помещалась в одно сообщение VK


@pusk_text_labeler.message(PUSK_STATE_RULE)
async def pusk_text_handler(message: Message) -> None:
    vk_id = message.from_id
    text = (message.text or "").strip()

    async with user_lock(vk_id):
        sess = await Session.load(vk_id)
        state = sess.state
        logger.debug("[PUSK TEXT] vk_id=%s state=%s", vk_id, state)

        booking = sess.data.get("pusk_booking")
        if booking is None:
            await message.answer("⚠️ Данные заявки не найдены. Напишите /start и начните заново.")
            await Session(vk_id).save("main_menu")
            return

        if state == "pusk_visitors_bulk":
            await _handle_visitors(message, sess, booking, text)
        elif state == "pusk_datetime":
            await _handle_datetime(message, sess, booking, text)
        elif state == "pusk_participants_count":
            await _handle_participants(message, sess, booking, text)
        elif state == "pusk_comment":
            await _handle_comment(message, sess, booking, text)
        else:
            # Состояния, где ждём нажатие кнопки
            await message.answer(
                "⚠️ Сейчас ожидается действие по кнопкам заявки «Пуск».\n"
                "Если хотите начать заново — напишите /start"
            )


async def _handle_visitors(message: Message, sess: Session, booking: dict, text: str) -> None:
    visitors, errors = parse_visitors(text)

    existing = booking.setdefault("visitors", [])
    if not errors and len(existing) + len(visitors) > MAX_VISITORS:
        errors.append(f"Всего можно указать не более {MAX_VISITORS} посетителей.")

    if errors:
        await message.answer(
            "❌ Обнаружены ошибки в формате ввода:\n\n"
            + "\n".join(errors)
            + "\n\nИсправьте ошибки и отправьте весь список заново по шаблону:\n"
            "ФИО, Возраст, Учебное заведение, Институт (или -)"
        )
        return

    existing.extend(visitors)

    summary = "\n".join(
        f"👤 {v['name']} ({v['age']} лет) — {v['institution']}" for v in visitors
    )
    keyboard = (
        Keyboard(inline=True)
        .add(Callback("➕ Добавить ещё (списком)", {"action": "pusk_add_visitor_bulk"}))
        .row()
        .add(Callback("✅ Завершить ввод посетителей", {"action": "pusk_finish_visitors"}))
        .get_json()
    )
    await sess.save("pusk_visitors_list")
    await message.answer(
        f"✅ Успешно добавлено посетителей: {len(visitors)}\n\n"
        f"{summary}\n\n"
        "Добавить ещё список или перейти к дате и времени?",
        keyboard=keyboard,
    )


async def _handle_datetime(message: Message, sess: Session, booking: dict, text: str) -> None:
    slot, error = parse_time_slot(text)
    if error:
        await message.answer(error)
        return

    booking["date"] = slot.date_str
    booking["start_time"] = slot.start_str
    booking["end_time"] = slot.end_str

    await sess.save("pusk_participants_count")
    await message.answer(
        "✅ Дата и время зафиксированы:\n"
        f"📅 {slot.date_str}\n"
        f"⏰ с {slot.start_str} до {slot.end_str}\n\n"
        "👥 Укажите планируемое количество участников мероприятия (только число):"
    )


async def _handle_participants(message: Message, sess: Session, booking: dict, text: str) -> None:
    if not text.isdigit() or not (1 <= int(text) <= 500):
        await message.answer("❌ Введите корректное число участников (от 1 до 500).")
        return

    booking["participants_count"] = int(text)
    await sess.save("pusk_comment")
    await message.answer(
        f"✅ Количество участников: {int(text)}\n\n"
        "📝 Введите комментарий к заявке (или отправьте «-»):\n"
        "Здесь вы можете указать любые важные детали, уточнения или особые пожелания."
    )


async def _handle_comment(message: Message, sess: Session, booking: dict, text: str) -> None:
    if len(text) > 500:
        await message.answer("❌ Комментарий слишком длинный (максимум 500 символов).")
        return

    booking["comment"] = "—" if (not text or text in DASHES) else text

    keyboard = (
        Keyboard(inline=True)
        .add(Callback("✅ Да, согласен(на)", {"action": "pusk_consent_yes"}))
        .row()
        .add(Callback("❌ Нет, не согласен(на)", {"action": "pusk_consent_no"}))
        .get_json()
    )
    await sess.save("pusk_personal_data")
    await message.answer(
        "В соответствии со статьей 9 Федерального закона от 27.07.2006 № 152-ФЗ "
        "„О персональных данных“ настоящим выражаю свое согласие на обработку "
        "моих персональных данных.",
        keyboard=keyboard,
    )
