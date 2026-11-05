"""Дополнительная цепочка бронирования: Молодёжное пространство «Пуск»."""
from vkbottle.bot import Bot, BotLabeler

from .handlers_callback import pusk_callback_labeler
from .handlers_text import pusk_text_labeler

# Единый лейблер для всего модуля
pusk_labeler = BotLabeler()
pusk_labeler.load(pusk_text_labeler)
pusk_labeler.load(pusk_callback_labeler)


def register_pusk_module(bot: Bot) -> None:
    """Подключает модуль к боту. Вызывать ДО основного текстового лейблера."""
    bot.labeler.load(pusk_labeler)
