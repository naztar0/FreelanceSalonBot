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
    form_text = State()
    media = State()


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


async def media_handler(message, state, callback):
    data = await state.get_data()
    if message.text == misc.next_button:
        await callback(message, state)
    elif message.photo:
        data['photo'].append(message.photo[-1].file_id)
        await state.update_data({'photo': data['photo']})
    elif message.video:
        data['video'].append(message.video.file_id)
        await state.update_data({'video': data['video']})
    else:
        if message.document:
            await message.reply("Отправьте медиа как фото или видео, а не как файл")
        else:
            await message.reply("Это не фото или видео")


async def start_menu(message):
    await message.answer("Выберите как вы будете пользоваться ботом", reply_markup=ButtonSet(ButtonSet.START))


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
    await message.answer(f"Приветствие для мастеров, бла бла бла", parse_mode='Markdown', reply_markup=ButtonSet(ButtonSet.MASTER, row_width=2))


async def create_order(message):
    await NewOrder.category.set()
    await message.answer("Заказ услуги", reply_markup=ButtonSet(ButtonSet.BACK))
    await message.answer("Выберите категорию и подкатегорию услуги", reply_markup=ButtonSet(ButtonSet.INL_CLIENT_CATEGORIES))


async def perform_order(message, order_id):
    selectQuery = "SELECT client_id FROM orders WHERE ID=(%s)"
    selectPortfolioQuery = "SELECT portfolio, ST_X(location), ST_Y(location) FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [order_id])
        client_id = cursor.fetchone()[0]
        cursor.execute(selectPortfolioQuery, [message.chat.id])
        portfolio, *location = cursor.fetchone()
    if not portfolio:
        portfolio = "отсутствует"
    address = get_location(location[0], location[1], 'ru') or "недоступно"
    await bot.send_message(client_id, "Мастер [{0}](tg://user?id={1}) готов взяться за ваш заказ!\n*Адрес:* {2}\n[Портфолио]({3}/{4})"
                           .format(esc_md(message.chat.full_name), message.chat.id, esc_md(address), misc.portfolio_chat, esc_md(portfolio)),
                           reply_markup=ButtonSet(ButtonSet.INL_CLIENT_ACCEPT_ORDER, {'order_id': order_id, 'master_id': message.chat.id}), parse_mode='Markdown')
    await message.edit_reply_markup()
    await message.reply("Вы отослали свою кандидатуру клиенту по этому заказу.\nЕсли клиент выберет вас, то скоро с вами свяжется.")


async def accept_order(message, order_id, master_id, client_id):
    updateQuery = "UPDATE orders SET master_id=(%s) WHERE ID=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(updateQuery, [(master_id, order_id)])
        conn.commit()
    await bot.send_message(master_id, f"[Клиент](tg://user?id={client_id}) выбрал Вас своим мастером! Можете с ним связаться.", parse_mode='Markdown')
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
    await message.answer(f"Пост опубликован\nКогда мастер заинтересуется Вашим заказом, Вы будете уведомлены.",
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
    await message.answer("Вы можете изменить местоположение.\n"
                         "Отправьте местоположение, в радиусе которого вы хотели бы получать заказы.\n"
                         "Либо отправьте текущее местоположение, нажав на кнопку ниже", reply_markup=ButtonSet(ButtonSet.SEND_LOCATION))


async def master_categories(message, start=False):
    selectQuery = "SELECT categories FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        result = cursor.fetchone()[0] or '[]'
    result = json.loads(result)
    _, count = count_categories(result)
    if not start:
        await message.edit_reply_markup(ButtonSet(ButtonSet.INL_MASTER_CATEGORIES, count))
        return
    await Subscriptions.change.set()
    await message.answer("Выбор подписок", reply_markup=ButtonSet(ButtonSet.SAVE_CHANGES))
    await message.answer("Выберите категории и подкатегории, на которые хотите подписаться",
                         reply_markup=ButtonSet(ButtonSet.INL_MASTER_CATEGORIES, count))


async def master_subcategories(message, cat_num):
    selectQuery = "SELECT categories FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        result = cursor.fetchone()[0] or '[]'
    result = json.loads(result)
    key = types.InlineKeyboardMarkup()
    start_shift = 0
    for subs in misc.subcategories[:cat_num]:
        start_shift += len(subs)
    for i, sub in enumerate(misc.subcategories[cat_num]):
        sym, add = "❌ ", True
        if str(i + start_shift) in result:
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
    can_pay = "Чтобы продлить подписку нажмите на кнопку ниже"
    if pay_date:
        active_until = datetime.strftime(pay_date, '%d.%m.%Y')
    if count == 0:
        can_pay = "Подпишитесь хотя-бы на одну категорию, чтобы получать заказы"
    elif balance < count * misc.tariff:
        can_pay = "У вас недостаточно средств на баллансе чтобы продлить подписку"
    else:
        key = ButtonSet(ButtonSet.RENEW_SUBSCRIPTION)
        await Subs_pay.pay.set()
    await message.answer(f"*Ваш балланс:* {balance} грн.\n*Стоимость подписки:* {count * misc.tariff} грн.\n"
                         f"*Подписка активна до:* {active_until}\n\n*{can_pay}*", parse_mode='Markdown', reply_markup=key)


async def save_portfolio(message, state):
    data = await state.get_data()
    await state.finish()
    message_id = medias_len = 0
    if data['photo'] and data['video']:
        medias_len = -1  # just not 1
    elif data['photo']:
        medias_len = len(data['photo'])
    elif data['video']:
        medias_len = len(data['video'])

    if medias_len:
        if medias_len == 1:
            if data['photo']:
                message_id = (await bot.send_photo(misc.portfolio_chat_id, data['photo'][0], caption=data['form_text'])).message_id
            elif data['video']:
                message_id = (await bot.send_video(misc.portfolio_chat_id, data['video'][0], caption=data['form_text'])).message_id
        else:
            medias_wrapped = []
            if data['photo']:
                medias_wrapped += [types.InputMediaPhoto(data['photo'][0], caption=data['form_text'])] \
                               + [types.InputMediaPhoto(x) for x in data['photo'][1:]]
            if data['video']:
                if not data['photo']:
                    medias_wrapped += [types.InputMediaVideo(data['video'][0], caption=data['form_text'])]
                medias_wrapped += [types.InputMediaVideo(x) for x in data['video'][1:]]
            message_id = (await bot.send_media_group(misc.portfolio_chat_id, medias_wrapped))[0].message_id
    else:
        message_id = (await bot.send_message(misc.portfolio_chat_id, data['form_text'])).message_id

    updateQuery = "UPDATE masters SET portfolio=(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(updateQuery, [(message_id, message.chat.id)])
        conn.commit()
    await state.finish()
    await message.answer("Портфолио сохранено", reply_markup=ButtonSet(ButtonSet.MASTER))


async def top_up_balance(message):
    await Top_up_balance.amount.set()
    await message.answer("Введите сумму на которую хотите пополнить баланс", reply_markup=ButtonSet(ButtonSet.BACK))


@dp.message_handler(commands=['start'])
async def handle_text(message: types.Message):
    await start_menu(message)


@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
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
    elif message.text == misc.master_buttons[0]:
        await master_orders(message)
    elif message.text == misc.master_buttons[1]:
        await master_categories(message, True)
    elif message.text == misc.master_buttons[2]:
        await master_portfolio(message)
    elif message.text == misc.master_buttons[3]:
        await master_location(message)
    elif message.text == misc.master_buttons[4]:
        await get_master_subs(message)
    elif message.text == misc.master_buttons[5]:
        await top_up_balance(message)


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
    await callback_query.message.answer(
        "Отправьте местоположение, в радиусе которого вы хотели бы получить услугу.\n"
        "Либо отправьте текущее местоположение, нажав на кнопку ниже", reply_markup=ButtonSet(ButtonSet.SEND_LOCATION))


@dp.message_handler(content_types=['text', 'location'], state=NewOrder.location)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.CLIENT) or not message.location:
        return
    x, y = message.location.latitude, message.location.longitude
    await state.update_data({'x': x, 'y': y})
    now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days = [now + timedelta(x) for x in range(8)]
    key = types.InlineKeyboardMarkup(row_width=2)
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


async def client_choose_time(callback_query, state, time):
    h, m = time.split(':')
    seconds = int(h) * 3600 + int(m) * 60
    args = ('❌ ' for _ in range(3))
    data = await state.get_data()
    await state.update_data({'time': time, 'timestamp': data['timestamp'] + seconds})
    await NewOrder.next()
    await callback_query.message.delete()
    await callback_query.message.answer("Выберите ценовые категории", reply_markup=ButtonSet(ButtonSet.INL_PRICE, args))


@dp.message_handler(content_types=['text'], state=NewOrder.price)
async def handle_text(message: types.Message, state: FSMContext):
    await _back(message, state, ButtonSet.CLIENT)


async def client_choose_price(callback_query, state, price):
    data = await state.get_data()
    price_flags = data.get('price') or 0
    price_flags ^= price
    await state.update_data({'price': price_flags})
    args = ('✅ ' if price_flags & 2 ** x else '❌ ' for x in range(3))
    await callback_query.message.edit_reply_markup(ButtonSet(ButtonSet.INL_PRICE, args))


async def client_submit_price(callback_query, state):
    data = await state.get_data()
    if not data.get('price'):
        await callback_query.answer("Выберите ценовую категорию!", show_alert=True)
        return
    await NewOrder.next()
    await callback_query.message.delete()
    await callback_query.message.answer("Напишите дополнительную информацио для мастера, либо нажмите «Далее ➡»",
                                        reply_markup=ButtonSet(ButtonSet.NEXT, row_width=2))


@dp.message_handler(content_types=['text'], state=NewOrder.form_text)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.CLIENT):
        return
    if len(message.text) > 600:
        await message.answer("Слишком длинный текст, попробуйте снова")
        return
    await state.update_data({'form_text': message.text if message.text != misc.next_button else '', 'photo': [], 'video': []})
    await NewOrder.next()
    await message.answer("👉 Теперь можете загрузить медиа файлы к вашей публикации (не больше 6 фото или 1 видео)\n\n"
                         "После загрузки всех медиафайлов нажмите «Далее ➡»")


@dp.message_handler(content_types=types.ContentType.ANY, state=NewOrder.media)
async def message_handler(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.CLIENT):
        return
    await media_handler(message, state, save_order)


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


async def update_subs_count(callback_query, state):
    await state.finish()
    await callback_query.message.edit_reply_markup()
    selectQuery = "SELECT categories, categories_count FROM masters WHERE user_id=(%s)"
    updateQuery = "UPDATE masters SET categories_count=(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [callback_query.message.chat.id])
        categories, old_count = cursor.fetchone()
    categories = json.loads(categories) if categories else []
    new_count = count_categories(categories)[0]
    answer = ''
    if old_count == new_count:
        answer = "Изменения сохранены"
    else:
        with DatabaseConnection() as db:
            conn, cursor = db
            cursor.executemany(updateQuery, [(new_count, callback_query.message.chat.id)])
            conn.commit()
        diff = abs(old_count - new_count)
        if old_count > new_count:
            answer = f"Вы отписались от категорий: {diff}\nСтоимость подписки уменьшилась на " \
                     f"{diff * misc.tariff} грн. и теперь составляет {new_count * misc.tariff} грн."
        elif old_count < new_count:
            answer = f"Вы подписались на категории: {diff}\nСтоимость подписки увеличилась на " \
                     f"{diff * misc.tariff} грн. и теперь составляет {new_count * misc.tariff} грн."
    await callback_query.message.answer(answer, reply_markup=ButtonSet(ButtonSet.MASTER))


async def client_orders(message):
    orders = Orders(message.from_user.id, Orders.CLIENT)
    reply = ''
    for i, order in enumerate(orders.orders, start=1):
        master = f"[мастер](tg://user?id={order.master_id})" if order.master_id else "_мастер пока не найден_"
        # address = get_location(order.latitude, order.longitude, 'ru') or "Адрес на карте"
        reply += f"*{i}.* {order.datetime.strftime('%d.%m %H:%M')} {master}\n" \
                 f"[Адрес на карте](https://google.com/maps/place/{order.latitude},{order.longitude})\n" \
                 f"\\[/11{order.id}] ➖ 📝 *изменить*\n" \
                 f"\\[/12{order.id}] ➖ ❌ *удалить*\n➖➖➖➖\n"
    if not reply:
        reply = "У вас пока нет заказов"
    reply_parts = parts.safe_split_text(reply, split_separator='➖➖➖➖')
    for part in reply_parts:
        await message.answer(part, parse_mode='Markdown', disable_web_page_preview=True)


async def master_orders(message):
    orders = Orders(message.from_user.id, Orders.MASTER)
    reply = ''
    for i, order in enumerate(orders.orders, start=1):
        reply += f"*{i}.* {order.datetime.strftime('%d.%m %H:%M')} [клиент](tg://user?id={order.client_id})\n" \
                 f"[Адрес на карте](https://google.com/maps/place/{order.latitude},{order.longitude})\n" \
                 f"\\[/22{order.id}] ➖ ❌ *удалить*\n➖➖➖➖\n"
    if not reply:
        reply = "У вас пока нет заказов"
    reply_parts = parts.safe_split_text(reply, split_separator='➖➖➖➖')
    for part in reply_parts:
        await message.answer(part, parse_mode='Markdown', disable_web_page_preview=True)


async def master_portfolio(message):
    selectQuery = "SELECT portfolio FROM masters WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        portfolio = cursor.fetchone()[0]
    await Portfolio.view.set()
    answer = f"[Портфолио]({misc.portfolio_chat}/{portfolio})" if portfolio else "Портфолио отсутствует"
    await message.answer(answer, parse_mode='Markdown', reply_markup=ButtonSet(ButtonSet.EDIT))


@dp.message_handler(content_types=['text'], state=Subscriptions.change)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER):
        return
    if message.text == misc.save_changes:
        await state.finish()
        await message.answer("Сохранено", reply_markup=ButtonSet(ButtonSet.MASTER))


@dp.message_handler(content_types=['text'], state=Portfolio.view)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER):
        return
    await Portfolio.next()
    await message.answer("Отправьте текст портфолио", reply_markup=ButtonSet(ButtonSet.BACK))


@dp.message_handler(content_types=['text'], state=Portfolio.text)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER):
        return
    if len(message.text) > 1000:
        await message.answer("Слишком длинный текст, попробуйте снова")
        return
    await state.update_data({'form_text': message.text, 'photo': [], 'video': []})
    await Portfolio.next()
    await message.answer("👉 Теперь можете загрузить медиа файлы к вашей публикации (не больше 6 фото или 1 видео)\n\n"
                         "После загрузки всех медиафайлов нажмите «Далее ➡»", reply_markup=ButtonSet(ButtonSet.NEXT, row_width=2))


@dp.message_handler(content_types=types.ContentType.ANY, state=Portfolio.media)
async def message_handler(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER):
        return
    await media_handler(message, state, save_portfolio)


@dp.message_handler(content_types=['text', 'location'], state=NewLocation.change)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER) or not message.location:
        return
    x, y = message.location.latitude, message.location.longitude
    updateQuery = "UPDATE masters SET location=ST_GeomFromText(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.executemany(updateQuery, [(loc_str(x, y), message.chat.id)])
        conn.commit()
    await state.finish()
    await message.answer("Местоположение сохранено", reply_markup=ButtonSet(ButtonSet.MASTER))


@dp.message_handler(content_types=['text'], state=Subs_pay.pay)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER) or message.text != "Продлить подписку":
        return
    selectQuery = "SELECT categories_count, balance, pay_date FROM masters WHERE user_id=(%s)"
    updateQuery = "UPDATE masters SET balance=(%s), pay_date=(%s) WHERE user_id=(%s)"
    with DatabaseConnection() as db:
        conn, cursor = db
        cursor.execute(selectQuery, [message.chat.id])
        result = cursor.fetchone()
        count, balance, pay_date = result
        if not pay_date:
            pay_date = datetime.now()
        active_until = pay_date + timedelta(days=30)
        cursor.executemany(updateQuery, [(balance - (count * misc.tariff), active_until, message.chat.id)])
        conn.commit()
    await state.finish()
    await message.answer("Подписка успешно продлена", reply_markup=ButtonSet(ButtonSet.MASTER))


@dp.message_handler(content_types=['text'], state=Top_up_balance.amount)
async def handle_text(message: types.Message, state: FSMContext):
    if await _back(message, state, ButtonSet.MASTER):
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
    await message.answer(f"Ваш баланс будет пополнен на {amount} грн.", reply_markup=ButtonSet(ButtonSet.MASTER))
    await message.answer("Чтобы оплатить используйте кнопку ниже.\nПосле оплаты бот автоматически обработает платёж.", reply_markup=key)


@dp.callback_query_handler(lambda callback_query: True)
async def callback_inline(callback_query: types.CallbackQuery):
    data = get_callback(callback_query.data)
    if data is None: return
    func, data = data
    if func == CallbackFuncs.CLIENT_ACCEPT_ORDER:
        await accept_order(callback_query.message, data['order_id'], data['master_id'], callback_query.message.chat.id)
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
