#!/usr/bin/env python
import logging
import json
from contextlib import suppress
from datetime import datetime, timedelta
from app import config, misc
from app.misc import bot, dp
from app.utils.my_utils import *
from app.utils.database_connection import DatabaseConnection

from aiogram import executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils import exceptions, parts


class NewOrder(StatesGroup):
    category = State()
    location = State()
    date = State()
    time = State()
    price = State()
    form_text_media = State()


class Portfolio(StatesGroup):
    view = State()
    text = State()
    media = State()


class NewLocation(StatesGroup): change = State()
class Subscriptions(StatesGroup): change = State()
class Top_up_balance(StatesGroup): amount = State()
class Subs_pay(StatesGroup): pay = State()


async def _back(message, state, key):
    if message.text == misc.back_button:
        await state.finish()
        await message.answer("Отменено", reply_markup=ButtonSet(key))
        return True


async def media_handler(message, state):
    data = await state.get_data()
    media = MediaGroup(data)
    if message.photo:
        media.add(photo=message.photo[-1].file_id)
        await state.update_data(media.to_dict)
    elif message.video:
        media.add(video=message.video.file_id)
        await state.update_data(media.to_dict)
    else:
        if message.document:
            await message.reply("Отправьте медиа как фото или видео, а не как файл")
        else:
            await message.reply("Это не фото или видео")


async def start_menu(message):
    await message.answer("Выберете кто вы 😇\n👉 Клиент - желаете найти и записаться на бьюти услугу\n"
                         "👉 Мастер - желаете найти клиентов для ваших прекрасных работ😃.",
                         reply_markup=ButtonSet(ButtonSet.START, row_width=2))


async def create_master(message):
    existsQuery = "SELECT EXISTS (SELECT ID FROM masters WHERE user_id=(%s))"
    insertQuery = "INSERT INTO masters (user_id) VALUES (%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(existsQuery, [message.chat.id])
        exists = cursor.fetchone()[0]
        if not exists:
            cursor.execute(insertQuery, [message.chat.id])
            conn.commit()
    await message.answer(f"QSalon поможет вам найти новых клиентов.\n👉заполните внимательно свой профиль\n"
                         f"👉выберете категории которые вам подходят и заявки от клиентов будут приходить к вам автоматически!\n\n"
                         f"Как это работает?\nВы заполняете свое портфолио и вам приходят запросы от клиентов в соответствии с вашим профилем.\n\n"
                         f"Есть вопросы? администратор @rivikate",
                         parse_mode='Markdown', reply_markup=ButtonSet(ButtonSet.MASTER_1, row_width=2))


async def create_order(message):
    await NewOrder.category.set()
    await message.answer("Заказ услуги", reply_markup=ButtonSet(ButtonSet.BACK))
    await message.answer("Выберите категорию и подкатегорию услуги", reply_markup=ButtonSet(ButtonSet.INL_CLIENT_CATEGORIES))


async def perform_order(message, order_id):
    selectQuery = "SELECT client_id, master_id FROM orders WHERE ID=(%s)"
    selectPortfolioQuery = "SELECT portfolio, ST_X(location), ST_Y(location) FROM masters WHERE user_id=(%s)"
    updateMessageQuery = "UPDATE orders SET message_id=(%s) WHERE ID=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [order_id])
        client_id, master_id = cursor.fetchone()
        if not master_id:
            cursor.execute(selectPortfolioQuery, [message.chat.id])
            portfolio, *location = cursor.fetchone()
            cursor.executemany(updateMessageQuery, [(message.message_id, order_id)])
            conn.commit()
    await message.edit_reply_markup()
    if master_id:
        await message.reply("Мастер на этот заказ уже нашелся")
        return
    portfolio = portfolio or "отсутствует"
    username = '@' + esc_md(message.chat.username) if message.chat.username else ''
    address = get_location(location[0], location[1], 'ru') or "недоступно"
    geolocation = f"https://google.com/maps/place/{location[0]},{location[1]}"
    await bot.send_message(client_id, "Мастер [{0}](tg://user?id={1}) {2} готов взяться за ваш заказ!\n*Адрес:* [{3}]({4})\n[Портфолио]({5}/{6})"
                           .format(esc_md(message.chat.full_name), message.chat.id, username, esc_md(address), geolocation, misc.portfolio_chat, esc_md(portfolio)),
                           reply_markup=ButtonSet(ButtonSet.INL_CLIENT_ACCEPT_ORDER, {'order_id': order_id, 'master_id': message.chat.id}), parse_mode='Markdown')
    await message.reply("Вы отослали свою кандидатуру клиенту по этому заказу.\nЕсли клиент выберет вас, то скоро с вами свяжется.")


async def accept_order(message, order_id, master_id, client):
    updateQuery = "UPDATE orders SET master_id=(%s) WHERE ID=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(updateQuery, [(master_id, order_id)])
        conn.commit()
    username = '@' + esc_md(client.username) if client.username else ''
    await bot.send_message(master_id, f"[Клиент](tg://user?id={client.id}) {username} выбрал Вас своим мастером! Можете с ним связаться.", parse_mode='Markdown')
    await message.edit_reply_markup()
    await message.answer(f"Вы выбрали [мастера](tg://user?id={master_id})! Можете с ним связаться.", parse_mode='Markdown')


async def save_order(message, state):
    data = await state.get_data()
    await state.finish()
    insertQuery = "INSERT INTO orders (client_id, category, location, datetime) VALUES (%s, %s, ST_GeomFromText(%s), %s)"
    getLastId = "SELECT LAST_INSERT_ID()"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(insertQuery, [(message.chat.id, data['category'], loc_str(data['x'], data['y']), datetime.fromtimestamp(data['timestamp']))])
        conn.commit()
        cursor.execute(getLastId)
        form_id = cursor.fetchone()[0]
    await message.answer(f"Ура🥳 заявка создана!\nТеперь подходящие мастера и салоны оповещены, в ближайшее время вам поступят "
                         f"предложения от них сюда в бот QSalon ✌\nХороших процедур и настроения☺",
                         parse_mode='Markdown', reply_markup=ButtonSet(ButtonSet.CLIENT))
    await bulk_mailing(data, form_id)


async def master_location(message):
    selectQuery = "SELECT ST_X(location), ST_Y(location) FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        result = cursor.fetchone()
    if not result[0] or not result[1]:
        await message.answer("Местоположение не задано")
    else:
        await bot.send_location(message.chat.id, result[0], result[1])
    await NewLocation.change.set()
    await message.answer("Укажите адрес вашего салона:\n👉 ТЕКУЩЕЕ МЕСТО , тогда нажмите кнопку ниже «отправить мою локацию»\n"
                         "👉 ДРУГОЕ  МЕСТО, тогда нажмите «скрепочка» – Location – выберете на карте локацию и нажмите Send location»",
                         reply_markup=ButtonSet(ButtonSet.SEND_LOCATION))


async def master_categories(message, start=False):
    master = Master(message.chat.id)
    list_cats = count_list_categories(master.categories)[1]
    if master.is_active_sub:
        button_set = ButtonSet.INL_MASTER_CATEGORIES_SQUEEZE
    else:
        button_set = ButtonSet.INL_MASTER_CATEGORIES
    if not start:
        await message.edit_reply_markup(ButtonSet(button_set, list_cats))
        return
    await Subscriptions.change.set()
    await message.answer("Выбор подписок", reply_markup=ButtonSet(ButtonSet.SAVE_CHANGES))
    await message.answer("У вас первый месяц подписки бесплатно 🤗😀\nНаши символические цены в месяц:\n"
                         "👉 1 категория - 190 грн\n👉 2 категории - 380 грн\n👉 3 категории и больше - 460 грн\n\n"
                         "Выберете категории и подкатегории которые вам подходят👌",
                         reply_markup=ButtonSet(button_set, list_cats))


async def master_subcategories(message, cat_num):
    master = Master(message.chat.id)
    key = types.InlineKeyboardMarkup()
    start_shift = 0
    for subs in misc.subcategories[:cat_num]:
        start_shift += len(subs)
    for i, sub in enumerate(misc.subcategories[cat_num]):
        sym, add = "❌ ", True
        if str(i + start_shift) in master.categories:
            sym, add = "✅ ", False
        key.add(types.InlineKeyboardButton(sym + sub, callback_data=set_callback(
            CallbackFuncs.CHANGE_CATEGORY, {'sub_num': i + start_shift, 'cat_num': cat_num, 'add': add})))
    key.add(types.InlineKeyboardButton('⬅ Назад к категориям', callback_data=set_callback(CallbackFuncs.CHANGE_CATEGORY, None)))
    with suppress(exceptions.MessageNotModified):
        await message.edit_reply_markup(key)


async def get_master_subs(message):
    selectQuery = "SELECT categories_count, balance, pay_date FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        result = cursor.fetchone()
    count, balance, pay_date = result
    key = None
    active_until = 'неактивна'
    can_pay = "👉 Чтобы ПРОДЛИТЬ ПОДПИСКУ нажмите кнопку снизу «продлить» 😉"
    price = get_subs_price(count)
    if pay_date:
        active_until = datetime.strftime(pay_date, '%d.%m.%Y')
    if count == 0:
        can_pay = "Подпишитесь хотя-бы на одну категорию, чтобы получать заказы"
    elif balance < price and pay_date:
        can_pay = "У вас недостаточно средств на баллансе чтобы продлить подписку на следующий месяц 😚"
    else:
        key = ButtonSet(ButtonSet.RENEW_SUBSCRIPTION)
        await Subs_pay.pay.set()
    await message.answer(f"*Ваш балланс:* {balance} грн.\n*Стоимость подписки:* {price} грн.\n"
                         f"*Подписка активна до:* {active_until}\n\n*{can_pay}*\n\n"
                         f"Есть вопросы? администратор @rivikate", parse_mode='Markdown', reply_markup=key)


async def save_portfolio(message, state):
    data = await state.get_data()
    await state.finish()
    col = 'portfolio' if data['p_or_s'] == 1 else 'salon'
    selectQuery = f"SELECT {col} FROM masters WHERE user_id=(%s)"
    selectDataQuery = "SELECT data FROM portfolios WHERE id=(%s)"
    last_data = None
    media = MediaGroup(data)
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        last_id = cursor.fetchone()
        if last_id: last_id = last_id[0]
        if data.get('only_text') or data.get('only_media'):
            cursor.execute(selectDataQuery, [last_id])
            last_data = json.loads(cursor.fetchone()[0])
    if data.get('only_text'):
        media.add(photo=last_data['photo'], video=last_data['video'])
    elif data.get('only_media'):
        media.add(text=last_data['text'])
    media_post = None

    if media.photo or media.video:
        if not media.is_media_group:
            if media.photo:
                media_post = await bot.send_photo(misc.portfolio_chat_id, media.photo[0], caption=media.text)
            elif media.video:
                media_post = await bot.send_video(misc.portfolio_chat_id, media.video[0], caption=media.text)
        else:
            media_post = await send_media_group(bot, misc.portfolio_chat_id, media)
    elif media.text:
        media_post = await bot.send_message(misc.portfolio_chat_id, media.text)

    insertQuery = "INSERT INTO portfolios (id, data) VALUES (%s, %s)"
    updateQuery = f"UPDATE masters SET {col}=(%s) WHERE user_id=(%s)"
    deleteQuery = "DELETE FROM portfolios WHERE id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(insertQuery, [(media_post.message_id, json.dumps(data, separators=(',', ':')))])
        cursor.executemany(updateQuery, [(media_post.message_id, message.chat.id)])
        cursor.execute(deleteQuery, [last_id])
        conn.commit()
    await state.finish()
    await message.answer("Сохранено", reply_markup=ButtonSet(ButtonSet.MASTER_2))


async def top_up_balance(message):
    await Top_up_balance.amount.set()
    await message.answer("Введите сумму на которую хотите пополнить баланс", reply_markup=ButtonSet(ButtonSet.BACK))


@dp.message_handler(commands=['start'])
async def handle_text(message: types.Message):
    await start_menu(message)


@dp.message_handler(content_types=['photo', 'video'])
async def handle_text(message: types.Message):
    if message.forward_from_message_id:
        await handle_forwarded_posts(message)


@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message, state: FSMContext):
    if message.text == misc.back_button:
        await start_menu(message)
    elif message.text == misc.role_buttons[0]:
        await message.answer("Добро пожаловать к нам!", reply_markup=ButtonSet(ButtonSet.CLIENT))
    elif message.text == misc.role_buttons[1]:
        await create_master(message)
    elif message.text == misc.client_buttons[0]:
        await create_order(message)
    elif message.text == misc.client_buttons[1]:
        await client_orders(message)
    elif message.text == misc.master_buttons_1[0]:
        await master_orders(message)
    elif message.text == misc.master_buttons_1[1]:
        await master_profile(message)
    elif message.text == misc.master_buttons_1[2]:
        await get_master_subs(message)
    elif message.text == misc.master_buttons_1[3]:
        await top_up_balance(message)
    elif message.text == misc.master_buttons_2[0]:
        await master_categories(message, True)
    elif message.text == misc.master_buttons_2[1]:
        await master_portfolio(message, state, 1)
    elif message.text == misc.master_buttons_2[2]:
        await master_portfolio(message, state, 2)
    elif message.text == misc.master_buttons_2[3]:
        await master_location(message)
    elif message.text == misc.master_buttons_2[4]:
        await message.answer("Выберите кнопку", reply_markup=ButtonSet(ButtonSet.MASTER_1))
    elif message.text[0] == '/' and message.text[1:].isdigit():
        await handle_orders_operations(message)
    elif message.forward_from_message_id:
        await handle_forwarded_posts(message)


@dp.message_handler(content_types=['text'], state=NewOrder.category)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.CLIENT):
        return


async def client_categories(callback_query, cat_num):
    start_shift = 0
    for subs in misc.subcategories[:cat_num]:
        start_shift += len(subs)
    subs = misc.subcategories[cat_num]
    key = types.InlineKeyboardMarkup()
    for i, sub in enumerate(subs):
        key.add(types.InlineKeyboardButton(sub, callback_data=set_callback(CallbackFuncs.NEW_ORDER_SUBCATEGORIES, i + start_shift)))
    key.add(types.InlineKeyboardButton('⬅ Назад к категориям', callback_data=set_callback(CallbackFuncs.NEW_ORDER_SUBCATEGORIES, None)))
    await callback_query.message.edit_reply_markup(key)


async def client_subcategories(callback_query, state, sub_num):
    if sub_num is None:
        await callback_query.message.edit_reply_markup(ButtonSet(ButtonSet.INL_CLIENT_CATEGORIES))
        return
    await callback_query.message.delete()
    await state.update_data({'category': sub_num})
    await NewOrder.next()
    await callback_query.message.answer(f"ВЫБЕРЕТЕ МЕСТО в радиусе {misc.radius} км от которого вы хотите получить услугу😉:\n\n"
                                        "👉 ТЕКУЩЕЕ МЕСТО , тогда нажмите кнопку ниже «отправить мою локацию»\n"
                                        "👉 Любое ДРУГОЕ МЕСТО, тогда нажмите «скрепочка» – Location – выберете на карте локацию и нажмите Send location»",
                                        reply_markup=ButtonSet(ButtonSet.SEND_LOCATION))


@dp.message_handler(content_types=['text', 'location'], state=NewOrder.location)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.CLIENT) or not message.location:
        return
    x, y = message.location.latitude, message.location.longitude
    await state.update_data({'x': x, 'y': y})
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [now + timedelta(x) for x in range(8)]
    key = types.InlineKeyboardMarkup(row_width=1)
    key.add(types.InlineKeyboardButton('На ближайшее время', callback_data=set_callback(CallbackFuncs.CHOOSE_DAY, 0)))
    for day in days:
        key.insert(types.InlineKeyboardButton(f'{day.day} {misc.month_names[day.month - 1]}',
                                              callback_data=set_callback(CallbackFuncs.CHOOSE_DAY, int(day.timestamp()))))
    await NewOrder.next()
    await message.answer("Идём дальше", reply_markup=ButtonSet(ButtonSet.BACK))
    await message.answer("Выберите желаемую дату", reply_markup=key)


@dp.message_handler(content_types=['text'], state=NewOrder.date)
async def handle_text(message: types.Message, state: FSMContext):
    await _back(message, state, ButtonSet.CLIENT)


async def client_choose_day(callback_query, state, timestamp):
    if timestamp == 0:
        now = datetime.now()
        if now.minute < 30:
            nearest = now.replace(minute=30)
        else:
            nearest = now.replace(hour=now.hour + 1 if now.hour < 23 else 0, minute=0)
        await state.update_data({'timestamp': nearest.timestamp()})
        await NewOrder.next()
        await client_choose_time(callback_query, state, None, True)
        return
    await state.update_data({'timestamp': timestamp})
    key = types.InlineKeyboardMarkup(row_width=2)
    for t in misc.times:
        key.insert(types.InlineKeyboardButton(t, callback_data=set_callback(CallbackFuncs.CHOOSE_TIME, t)))
    await NewOrder.next()
    await callback_query.message.delete()
    await callback_query.message.answer("Выберите желаемое время", reply_markup=key)


@dp.message_handler(content_types=['text'], state=NewOrder.time)
async def handle_text(message: types.Message, state: FSMContext):
    await _back(message, state, ButtonSet.CLIENT)


async def client_choose_time(callback_query, state, time, skip=False):
    if not skip:
        h, m = time.split(':')
        seconds = int(h) * 3600 + int(m) * 60
        data = await state.get_data()
        await state.update_data({'timestamp': data['timestamp'] + seconds})
    args = ('' for _ in range(3))
    await NewOrder.next()
    await callback_query.message.delete()
    await callback_query.message.answer("Выберете примерную ценовую политику бьюти услуги (можна два пункта👌). И нажмите «Далее ➡»",
                                        reply_markup=ButtonSet(ButtonSet.INL_PRICE, args))


@dp.message_handler(content_types=['text'], state=NewOrder.price)
async def handle_text(message: types.Message, state: FSMContext):
    await _back(message, state, ButtonSet.CLIENT)


async def client_choose_price(callback_query, state, price):
    data = await state.get_data()
    price_flags = data.get('price') or 0
    price_flags ^= price
    await state.update_data({'price': price_flags, 'photo': [], 'video': []})
    args = ('✅ ' if price_flags & 2 ** x else '' for x in range(3))
    await callback_query.message.edit_reply_markup(ButtonSet(ButtonSet.INL_PRICE, args))


async def client_submit_price(callback_query, state):
    data = await state.get_data()
    if not data.get('price'):
        await callback_query.answer("Выберите ценовую категорию!", show_alert=True)
        return
    await NewOrder.next()
    await callback_query.message.delete()
    await callback_query.message.answer("Можно написать:\n👉 КОММЕНТАРИЙ для мастера/салона\n"
                                        "👉 Загрузить медиа файлы например желаемый результат 🤩(не больше 3-х файлов),\n"
                                        "👉 Либо просто ПРОПУСТИТЕ и нажмите «Далее ➡»",
                                        reply_markup=ButtonSet(ButtonSet.NEXT, row_width=2))


@dp.message_handler(content_types=types.ContentTypes.ANY, state=NewOrder.form_text_media)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.CLIENT):
        return
    if message.text == misc.next_button:
        await save_order(message, state)
        return
    if message.text:
        if len(message.text) > 600:
            await message.answer("Слишком длинный текст, попробуйте снова")
            return
        await state.update_data({'text': message.text})
    else:
        await media_handler(message, state)


async def master_profile(message):
    selectQuery = "SELECT categories, portfolio, salon, location FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.from_user.id])
        result = cursor.fetchone()
    if all(result):
        reply = "Выберите кнопку"
    else:
        reply = "*Чтобы начать получать заказы, заполните профиль полностью!*\n\nОсталось заполнить:\n" \
                f"{'— Подписки на категории' if not result[0] else ''}\n" \
                f"{'— Портфолио' if not result[1] else ''}\n" \
                f"{'— Салон' if not result[2] else ''}\n" \
                f"{'— Местоположение' if not result[3] else ''}\n"
    reply += "\n\nЕсть вопросы? администратор @rivikate"
    await message.answer(reply, reply_markup=ButtonSet(ButtonSet.MASTER_2), parse_mode='Markdown')


def update_subscriptions(user_id, num, add=True):
    selectQuery = "SELECT categories FROM masters WHERE user_id=(%s)"
    updateQuery = "UPDATE masters SET categories=(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [user_id])
        result = cursor.fetchone()[0] or '[]'
        result = json.loads(result)
        if add:
            result.append(str(num))
        else:
            if str(num) in result:
                result.remove(str(num))
        cursor.executemany(updateQuery, [(json.dumps(result, separators=(',', ':')), user_id)])
        conn.commit()


async def update_subs_count(message, state):
    await state.finish()
    selectQuery = "SELECT categories, categories_count FROM masters WHERE user_id=(%s)"
    updateQuery = "UPDATE masters SET categories_count=(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.from_user.id])
        categories, old_count = cursor.fetchone()
    categories = json.loads(categories) if categories else []
    new_count = count_list_categories(categories)[0]
    answer = ''
    if old_count == new_count or (old_count >= len(misc.tariffs) and new_count >= len(misc.tariffs)):
        answer = "Изменения сохранены"
    else:
        with DatabaseConnection() as db:
            conn, cursor = db
            cursor.executemany(updateQuery, [(new_count, message.from_user.id)])
            conn.commit()
        diff = abs(old_count - new_count)
        if old_count > new_count:
            answer = f"Вы отписались от категорий: {diff}\n"
        elif old_count < new_count:
            answer = f"Вы подписались на категории: {diff}\n"
        answer += f"Стоимость подписки теперь составляет {get_subs_price(new_count)} грн."
    await message.answer(answer, reply_markup=ButtonSet(ButtonSet.MASTER_2))


async def client_orders(message):
    orders = Orders(message.from_user.id, Orders.CLIENT)
    reply = ''
    for order in orders.orders:
        master = f"[мастер](tg://user?id={order.master_id})" if order.master_id else "_мастер пока не найден_"
        reply += f"*{order.id}.* {order.datetime.strftime('%d.%m %H:%M')} {master}\n" \
                 f"[Адрес на карте](https://google.com/maps/place/{order.latitude},{order.longitude})\n" \
                 f"\\[/11{order.id}] ➖ ❌ *удалить*\n➖➖➖➖\n"
    if not reply:
        reply = "У вас пока нет заказов"
    reply_parts = parts.safe_split_text(reply, split_separator='➖➖➖➖')
    for part in reply_parts:
        await message.answer(part, parse_mode='Markdown', disable_web_page_preview=True)


async def master_orders(message):
    orders = Orders(message.from_user.id, Orders.MASTER)
    reply = ''
    for order in orders.orders:
        reply += f"*{order.id}.* {order.datetime.strftime('%d.%m %H:%M')} [клиент](tg://user?id={order.client_id})\n" \
                 f"\\[/21{order.id}] ➖ ❌ *удалить*\n" \
                 f"\\[/22{order.id}] ➖ ℹ *подробнее*\n➖➖➖➖\n"
    if not reply:
        reply = "У вас пока нет заказов"
    reply_parts = parts.safe_split_text(reply, split_separator='➖➖➖➖')
    for part in reply_parts:
        await message.answer(part, parse_mode='Markdown', disable_web_page_preview=True)


async def master_portfolio(message, state, p_or_s):
    col = 'portfolio' if p_or_s == 1 else 'salon'
    selectQuery = f"SELECT {col} FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        portfolio = cursor.fetchone()[0]
    await Portfolio.view.set()
    if p_or_s == 1:
        answer = f"[Портфолио]({misc.portfolio_chat}/{portfolio})" if portfolio else "Портфолио отсутствует"
    else:
        answer = f"[Салон]({misc.portfolio_chat}/{portfolio})" if portfolio else "Информация о салоне отсутствует"
    await state.update_data({'p_or_s': p_or_s})
    button_set = ButtonSet.EDIT
    if portfolio:
        button_set = ButtonSet.EDIT_PART if p_or_s == 1 else ButtonSet.EDIT_PART_SALON
    await message.answer(answer, parse_mode='Markdown', reply_markup=ButtonSet(button_set))


@dp.message_handler(content_types=['text'], state=Subscriptions.change)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_2):
        return
    if message.text == misc.save_changes:
        await state.finish()
        await update_subs_count(message, state)
        update_active_master(message.from_user.id)


@dp.message_handler(content_types=['text'], state=Portfolio.view)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_2):
        return
    if message.text == misc.edit_buttons[2]:
        await state.update_data({'only_text': True})
    elif message.text == misc.edit_buttons[3]:
        await state.update_data({'only_media': True, 'photo': [], 'video': []})
        await Portfolio.media.set()
        await message.answer("👉 Загрузите медиа файлы (не больше 10 фото и видео)\n\n"
                             "После загрузки всех медиафайлов нажмите «Далее ➡»", reply_markup=ButtonSet(ButtonSet.NEXT, row_width=2))
        return
    await Portfolio.next()
    await message.answer("Отправьте текст для подписи вашего портфолио", reply_markup=ButtonSet(ButtonSet.BACK))


@dp.message_handler(content_types=['text'], state=Portfolio.text)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_2):
        return
    if len(message.text) > 1000:
        await message.answer("Слишком длинный текст, попробуйте снова")
        return
    data = await state.get_data()
    await state.update_data({'text': message.text})
    if data.get('only_text'):
        await save_portfolio(message, state)
        return
    await Portfolio.next()
    await message.answer("👉 Загрузите медиа файлы к вашему портфолио (не больше 10 фото и видео)\n\n"
                         "После загрузки всех медиафайлов нажмите «Далее ➡»", reply_markup=ButtonSet(ButtonSet.NEXT, row_width=2))


@dp.message_handler(content_types=types.ContentType.ANY, state=Portfolio.media)
async def message_handler(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_2):
        return
    if message.text == misc.next_button:
        await save_portfolio(message, state)
        update_active_master(message.from_user.id)
        return
    await media_handler(message, state)


@dp.message_handler(content_types=['text', 'location'], state=NewLocation.change)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_2) or not message.location:
        return
    x, y = message.location.latitude, message.location.longitude
    updateQuery = "UPDATE masters SET location=ST_GeomFromText(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(updateQuery, [(loc_str(x, y), message.chat.id)])
        conn.commit()
    await state.finish()
    await message.answer("Местоположение сохранено", reply_markup=ButtonSet(ButtonSet.MASTER_2))
    update_active_master(message.from_user.id)


@dp.message_handler(content_types=['text'], state=Subs_pay.pay)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_1) or message.text != "Продлить подписку":
        return
    selectQuery = "SELECT categories_count, balance, pay_date FROM masters WHERE user_id=(%s)"
    updateQuery = "UPDATE masters SET balance=(%s), pay_date=(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        count, balance, pay_date = cursor.fetchone()
        new_balance = balance - (get_subs_price(count)) if pay_date else 0
        if not pay_date or pay_date < datetime.now():
            pay_date = datetime.now()
        active_until = pay_date + timedelta(days=30)
        cursor.executemany(updateQuery, [(new_balance, active_until, message.chat.id)])
        conn.commit()
    await state.finish()
    await message.answer("Подписка успешно продлена", reply_markup=ButtonSet(ButtonSet.MASTER_1))


@dp.message_handler(content_types=['text'], state=Top_up_balance.amount)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER_1):
        return
    if not message.text.isdigit():
        await message.reply("Недействительная сумма!")
        return
    amount = int(message.text)
    if amount < 1 or amount > 1000000:
        await message.reply("Недействительная сумма!")
        return
    await state.finish()
    pay_link = way_for_pay_request_purchase(message.chat.id, amount)
    if isinstance(pay_link, tuple):
        logging.error(f"Error: {pay_link[1]}")
        await message.answer(f"Error: {pay_link[1]}")
        await message.answer("Извините, произошла ошибка, повторите попытку позже")
        return
    key = types.InlineKeyboardMarkup()
    key.add(types.InlineKeyboardButton("Оплатить", url=pay_link))
    await message.answer(f"Ваш баланс будет пополнен на {amount} грн.", reply_markup=ButtonSet(ButtonSet.MASTER_1))
    await message.answer("Чтобы оплатить используйте кнопку ниже.\nПосле оплаты бот автоматически обработает платёж.", reply_markup=key)


async def handle_orders_operations(message):
    # /11{id} - client delete
    # /21{id} - master delete
    # /22{id} - more info
    code = message.text[1:]
    order_id = int(code[2:])
    if code[0] == '1':
        if code[1] == '1':
            order = Orders(message.from_user.id, Orders.CLIENT).get(order_id)
            deleteQuery = "DELETE FROM orders WHERE ID=(%s) AND client_id=(%s)"
            with DatabaseConnection() as db:
                conn, cursor = db
                cursor.executemany(deleteQuery, [(order_id, message.from_user.id)])
                conn.commit()
            await message.answer(f"Заказ №{order_id} удален")
            if order.master_id:
                await send_message(bot.send_message, chat_id=order.master_id, text=f"[Клиент](tg://user?id={order.client_id}) отменил заказ №{order_id}", parse_mode='Markdown')
    elif code[0] == '2':
        if code[1] == '1':
            order = Orders(message.from_user.id, Orders.CLIENT).get(order_id)
            deleteQuery = "DELETE FROM orders WHERE ID=(%s) AND master_id=(%s)"
            with DatabaseConnection() as db:
                conn, cursor = db
                cursor.executemany(deleteQuery, [(order_id, message.from_user.id)])
                conn.commit()
            await message.answer(f"Заказ №{order_id} удален")
            if order.client_id:
                await send_message(bot.send_message, chat_id=order.client_id, text=f"[Мастер](tg://user?id={order.master_id}) отменил заказ №{order_id}", parse_mode='Markdown')
        elif code[1] == '2':
            selectMessageQuery = "SELECT message_id FROM orders WHERE ID=(%s)"
            with DatabaseConnection() as db:
                conn, cursor = db
                cursor.execute(selectMessageQuery, [order_id])
                message_id = cursor.fetchone()[0]
            await bot.send_message(message.chat.id, f"Заказ №{order_id} ⬆", reply_to_message_id=message_id)


async def handle_forwarded_posts(message):
    if message.from_user.id not in misc.admins:
        return
    if message.forward_from_chat.id != misc.portfolio_chat_id:
        return
    selectQuery = "SELECT user_id FROM masters WHERE portfolio=(%s) OR salon=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(selectQuery, [(message.forward_from_message_id, message.forward_from_message_id)])
        result = cursor.fetchone()
    if not result:
        await message.answer("Не найдено мастера с таким портфолио/салоном")
        return
    await message.answer(f"Найден [мастер](tg://user?id={result[0]})\nuser\\_id: `{result[0]}`", parse_mode='Markdown')


@dp.callback_query_handler(lambda callback_query: True)
async def callback_inline(callback_query: types.CallbackQuery):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.CLIENT_ACCEPT_ORDER:
        await accept_order(callback_query.message, data['order_id'], data['master_id'], callback_query.message.chat)
    elif func == CallbackFuncs.MASTER_ACCEPT_ORDER:
        await perform_order(callback_query.message, data)


@dp.callback_query_handler(lambda callback_query: True, state=Subscriptions.change)
async def callback_inline(callback_query: types.CallbackQuery):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.MASTER_CATEGORIES:
        await master_subcategories(callback_query.message, data)
    elif func == CallbackFuncs.CHANGE_CATEGORY:
        if data:
            update_subscriptions(callback_query.message.chat.id, data['sub_num'], data['add'])
            await master_subcategories(callback_query.message, data['cat_num'])
        else:
            await master_categories(callback_query.message)


@dp.callback_query_handler(lambda callback_query: True, state=NewOrder.category)
async def callback_inline(callback_query: types.CallbackQuery, state: FSMContext):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.NEW_ORDER_CATEGORIES:
        await client_categories(callback_query, data)
    elif func == CallbackFuncs.NEW_ORDER_SUBCATEGORIES:
        await client_subcategories(callback_query, state, data)


@dp.callback_query_handler(lambda callback_query: True, state=NewOrder.date)
async def callback_inline(callback_query: types.CallbackQuery, state: FSMContext):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.CHOOSE_DAY:
        await client_choose_day(callback_query, state, data)


@dp.callback_query_handler(lambda callback_query: True, state=NewOrder.time)
async def callback_inline(callback_query: types.CallbackQuery, state: FSMContext):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.CHOOSE_TIME:
        await client_choose_time(callback_query, state, data)


@dp.callback_query_handler(lambda callback_query: True, state=NewOrder.price)
async def callback_inline(callback_query: types.CallbackQuery, state: FSMContext):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.CHOOSE_PRICE:
        await client_choose_price(callback_query, state, data)
    elif func == CallbackFuncs.CHOOSE_PRICE_SUBMIT:
        await client_submit_price(callback_query, state)


async def on_startup(_):
    await bot.set_webhook(config.WEBHOOK_URL)
    info = await bot.get_webhook_info()
    logging.warning(f'URL: {info.url}\nPending update count: {info.pending_update_count}')


async def on_shutdown(_):
    await bot.delete_webhook()


def start_pooling():
    executor.start_polling(dp, skip_updates=True)


def start_webhook():
    executor.start_webhook(dispatcher=dp, webhook_path=config.WEBHOOK_PATH,
                           on_startup=on_startup, on_shutdown=on_shutdown,
                           host=config.WEBAPP_HOST, port=config.WEBAPP_PORT,
                           skip_updates=True, print=logging.warning)
