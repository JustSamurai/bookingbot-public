"""Основная цепочка: текстовые сообщения пользователя."""
import asyncio
import logging

from vkbottle import Callback, Keyboard
from vkbottle.bot import BotLabeler, Message

from handlers.common import (
    BUTTON_STATES,
    FLOW,
    PROFILE_STEPS,
    PROMPTS,
    RESTART_HINT,
    begin_booking,
)
from handlers.reporter import send_main_application
from keyboards.generator import locations_keyboard
from keyboards.registry import get_snapshot
from utils.parsers import parse_time_slot
from utils.profile import save_profile
from utils.rules import MAIN_STATE_RULE, StartCommandRule
from utils.session import Session, user_lock
from utils.validators import DASHES, validate_field

logger = logging.getLogger(__name__)

user_text_labeler = BotLabeler()


# ─────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────
@user_text_labeler.message(StartCommandRule())
async def start_handler(message: Message) -> None:
    async with user_lock(message.from_id):
        text, keyboard = await begin_booking(message.from_id)
    await message.answer(text, keyboard=keyboard)


# ─────────────────────────────────────────────────────────────
# Все остальные текстовые шаги основной цепочки
# ─────────────────────────────────────────────────────────────
@user_text_labeler.message(MAIN_STATE_RULE)
async def handle_text_input(message: Message) -> None:
    vk_id = message.from_id
    text = (message.text or "").strip()

    async with user_lock(vk_id):
        sess = await Session.load(vk_id)
        state = sess.state
        logger.debug("[MAIN TEXT] vk_id=%s state=%s", vk_id, state)

        if state in FLOW:
            await _handle_flow_step(message, sess, text)
        elif state == "datetime":
            await _handle_datetime(message, sess, text)
        elif state == "comment":
            await _handle_comment(message, sess, text)
        elif state in BUTTON_STATES:
            await message.answer(
                "👆 Выберите вариант кнопками под сообщением выше.\n"
                "Чтобы начать заново — напишите /start"
            )
        else:
            logger.warning("Неизвестное состояние %r у vk_id=%s, сбрасываю", state, vk_id)
            await message.answer(f"⚠️ Произошла ошибка состояния. {RESTART_HINT}")
            await Session(vk_id).save("main_menu")


# ── Анкета и данные мероприятия ──────────────────────────────
async def _handle_flow_step(message: Message, sess: Session, text: str) -> None:
    state = sess.state
    value, error = validate_field(state, text)
    if error:
        await message.answer(error)
        return

    if state in PROFILE_STEPS:
        sess.user[state] = value
    else:
        sess.event_info[state] = value

    # Последний шаг анкеты — сохраняем профиль в БД
    if state == "division":
        sess.user["vk_id"] = sess.vk_id
        await asyncio.to_thread(save_profile, sess.user)

        if sess.data.pop("is_editing", False):
            await Session(sess.vk_id).save("main_menu")
            keyboard = (
                Keyboard(inline=True)
                .add(Callback("📅 Начать бронирование", {"action": "start_new_booking"}))
                .get_json()
            )
            await message.answer("✅ Профиль успешно обновлён!")
            await message.answer(
                "Теперь можно бронировать аудитории.\nНапиши /start или нажми кнопку ниже.",
                keyboard=keyboard,
            )
            return

        sess.data["bookings"] = []
        sess.data["current_booking"] = None

    # Следующий шаг
    index = FLOW.index(state)
    if index + 1 < len(FLOW):
        next_state = FLOW[index + 1]
        await sess.save(next_state)
        await message.answer(PROMPTS[next_state])
        return

    # После списка участников — выбор корпуса
    locations = get_snapshot().sorted_locations()
    if not locations:
        await Session(sess.vk_id).save("main_menu")
        await message.answer(
            "⚠️ Список помещений пока пуст. Обратитесь к администратору."
        )
        return

    await sess.save("location")
    await message.answer(
        "🏛️ Теперь выберите корпус или локацию:",
        keyboard=locations_keyboard(locations),
    )


# ── Дата и время ─────────────────────────────────────────────
async def _handle_datetime(message: Message, sess: Session, text: str) -> None:
    slot, error = parse_time_slot(text)
    if error:
        await message.answer(error)
        return

    booking = sess.data.get("current_booking")
    if not booking or not booking.get("room"):
        await message.answer(f"⚠️ Данные текущего бронирования не найдены. {RESTART_HINT}")
        return

    booking["datetime_text"] = slot.text
    sess.data.setdefault("bookings", []).append(booking)
    sess.data["current_booking"] = None

    equipment = ", ".join(booking.get("equipment") or []) or "— ничего не выбрано"
    preview = (
        "➕ Добавлена бронь:\n"
        f"• {booking.get('location', 'Не указано')} — {booking.get('room', 'Не указано')}\n"
        f"• Оборудование: {equipment}\n"
        f"• Время: {slot.text}\n\n"
        "Хотите добавить ещё одну аудиторию в эту заявку?"
    )
    keyboard = (
        Keyboard(inline=True)
        .add(Callback("➕ Ещё одно помещение", {"action": "add_another"}))
        .row()
        .add(Callback("✅ Всё готово, оставить комментарий", {"action": "comment"}))
        .get_json()
    )
    await sess.save("wait_decision")
    await message.answer(preview, keyboard=keyboard)


# ── Комментарий и отправка ───────────────────────────────────
async def _handle_comment(message: Message, sess: Session, text: str) -> None:
    if len(text) > 500:
        await message.answer("❌ Комментарий слишком длинный (максимум 500 символов).")
        return
    if not sess.data.get("bookings"):
        await message.answer(f"⚠️ В заявке нет ни одного помещения. {RESTART_HINT}")
        return

    sess.event_info["comment"] = "—" if (not text or text in DASHES) else text

    ticket = await send_main_application(message.ctx_api, sess)
    # В любом случае возвращаем пользователя в главное меню с чистой сессией
    await Session(sess.vk_id).save("main_menu")

    if ticket is None:
        await message.answer(
            "❌ Не удалось отправить заявку модераторам. "
            "Попробуйте позже: напишите /start и заполните заявку заново."
        )
        return

    await message.answer(
        f"🚀 Заявка №{ticket} успешно отправлена на рассмотрение!\n"
        "Ожидайте ответа от администратора в личных сообщениях.\n\n"
        "Для создания новой заявки напишите /start"
    )
