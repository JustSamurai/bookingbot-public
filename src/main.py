import logging
import os
import sys

from colorama import Fore, Style, init as colorama_init
from vkbottle.bot import Bot

import config
from database.schema import init_db
from handlers.admin import admin_labeler
from handlers.admin_callback import admin_callback_labeler
from handlers.admin_text import admin_text_labeler
from handlers.user_callback import user_callback_labeler
from handlers.user_text import user_text_labeler
from keyboards.registry import reload_registry
from pusk_coworking import register_pusk_module

colorama_init(autoreset=True)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s:%(lineno)d | %(message)s",
)
logger = logging.getLogger("booking-bot")


def _configure_vkbottle_logger() -> None:
    """vkbottle пишет через loguru — выставляем тот же уровень."""
    try:
        from vkbottle import logger as vk_logger

        vk_logger.remove()
        vk_logger.add(sys.stderr, level=LOG_LEVEL)
    except Exception:  # noqa: BLE001 — не критично, если логгер другой
        pass


def build_bot() -> Bot:
    bot = Bot(token=config.TOKEN_MAIN)

    # ВАЖНО: порядок загрузки определяет приоритет текстовых обработчиков.
    # 1. Комментарий модератора (ждёт после нажатия «Одобрить/Отклонить»)
    bot.labeler.load(admin_text_labeler)
    # 2. CRUD-команды в чате модераторов
    bot.labeler.load(admin_labeler)
    # 3. Дополнительная цепочка «Пуск» (состояния pusk_*)
    register_pusk_module(bot)
    # 4. Основная цепочка: /start и остальные шаги
    bot.labeler.load(user_text_labeler)

    # Обработчики кнопок не конкурируют: каждый отвечает только за свои action
    bot.labeler.load(admin_callback_labeler)
    bot.labeler.load(user_callback_labeler)
    return bot


def main() -> None:
    _configure_vkbottle_logger()

    init_db()          # создаёт недостающие таблицы/колонки, данные не трогает
    reload_registry()  # корпуса, аудитории, оборудование

    if not config.RULES_PHOTO.is_file():
        logger.warning("Файл %s не найден — «Пуск» будет работать без картинки правил", config.RULES_PHOTO.name)

    bot = build_bot()
    print(f"{Fore.GREEN}{Style.BRIGHT}🚀 БОТ УСПЕШНО ЗАПУЩЕН И ГОТОВ К РАБОТЕ!!!")
    bot.run_forever()


if __name__ == "__main__":
    main()
