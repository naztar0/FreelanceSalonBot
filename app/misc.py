import logging
from pathlib import Path
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from app import config


app_dir: Path = Path(__file__).parent.parent
temp_dir = app_dir / "temp"

logging.basicConfig(level=logging.WARNING)

bot = Bot(config.TG_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

media_chat = 'https://t.me/masters_media0'
media_chat_id = -1001458527895
portfolio_chat = 'https://t.me/masters_portfolio'
portfolio_chat_id = -1001314538317
opencage_api_url = "https://api.opencagedata.com/geocode/v1/json"

way_for_pay_url = "https://api.wayforpay.com/api"
way_for_pay_merchant_domain_name = "www.t.me/AdvancedAdsBot"

tariff = 100

role_buttons = ("Клиент", "Мастер")
client_buttons = ("Заказать услугу", "Мои услуги")
master_buttons = ("Мои заявки", "Подписки", "Портфолио", "Местоположение", "Оплата подписок", "Пополнить балланс")
back_button = "⬅ Назад"
next_button = "Далее ➡"
save_changes = "🆗 Закончить выбор"
renew_subscription = "Продлить подписку"

categories = ("Парикмахерские услуги", "Визаж / Уход за лицом", "Ногтевой сервис", "Омоложение", "Уход за телом", "Удаление волос", "Тату / Пирсинг / Татуаж", "Брови / Ресницы")

subcategories = (("Женская стрижка", "Мужская стрижка", "Укладка", "Окрашивание волос", "Реконструкция волос", "Наращивание волос", "Другое"),
                 ("Дневной макияж", "Макияж для фотосессии", "Вечерний макияж", "Свадебный макияж", "Боди арт", "Уколы Красоты", "Апаратное Омоложение", "Пилинг лица", "Массаж лица", "Чистка лица", "Выравнивание рельефа и цвета", "Лечение кожи лица", "Другое"),
                 ("Маникюр", "Педикюр"),
                 ("Плазмолифтинг", "Мезотерапия", "Уколы Botox/Dysport", "Аппаратное омоложение", "Биоревитализация", "Лазерная шлифовка лица", "Контурная пластика", "Лазерная шлифовка лица", "Подтяжка лица мезонитями"),
                 ("Уход за кожей тела", "Коррекция фигуры", "Массаж и SPA"),
                 ("Депиляция", "Эпиляция", "Лазерная эпиляция", "Шугаринг", "Фотоэпиляция", "Эпиляция нитью", "Мужская эпиляция", "Другое"),
                 ("Тату", "Пирсинг", "Татуаж", "Удаление татуажа", "Другое"),
                 ("Наращивание ресниц", "Покраска бровей", "Моделирование бровей", "Ламинирование ресниц", "Ламинирование бровей", "Другое"))

# subcategories_count = 54

month_names = ("января", "февраля", "марта", "апреля", "мая", "июня",
               "июля", "августа", "сентября", "октября", "ноября", "декабря")
times = ('10:00', '10:30', '11:00', '11:30', '12:00', '12:30', '13:00', '13:30', '14:00', '14:30',
         '15:00', '15:30', '16:00', '16:30', '17:00', '17:30', '18:00', '18:30', '19:00', '19:30')
