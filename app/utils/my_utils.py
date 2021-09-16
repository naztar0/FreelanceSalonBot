import json
import requests
import hmac
import time
from typing import Optional
from contextlib import suppress
from asyncio import sleep
from datetime import datetime
from math import cos, radians
from aiogram import types, helper
from aiogram.types import ReplyKeyboardMarkup as RKM, InlineKeyboardMarkup as IKM
from aiogram.types import KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton
from aiogram.utils import exceptions, callback_data
from app import misc, config
from app.utils.database_connection import DatabaseConnection


class CallbackFuncs:
    NEW_ORDER_CATEGORIES = 0x00
    NEW_ORDER_SUBCATEGORIES = 0x01
    CLIENT_ACCEPT_ORDER = 0x02
    MASTER_ACCEPT_ORDER = 0x03
    MASTER_CATEGORIES = 0x04
    CHANGE_CATEGORY = 0x06
    CHOOSE_DAY = 0x07
    CHOOSE_TIME = 0x08
    CHOOSE_PRICE = 0x09
    CHOOSE_PRICE_SUBMIT = 0x0a


class ReplyKeyboardMarkup(RKM):
    def __bool__(self):
        return bool(self.keyboard)


class InlineKeyboardMarkup(IKM):
    def __bool__(self):
        return bool(self.inline_keyboard)


class ButtonSet(helper.Helper):
    mode = helper.HelperMode.lowercase
    REMOVE = helper.Item()
    START = helper.Item()
    BACK = helper.Item()
    CLIENT = helper.Item()
    MASTER = helper.Item()
    SEND_LOCATION = helper.Item()
    SAVE_CHANGES = helper.Item()
    EDIT = helper.Item()
    NEXT = helper.Item()
    RENEW_SUBSCRIPTION = helper.Item()
    INL_CLIENT_ACCEPT_ORDER = helper.Item()
    INL_MASTER_ACCEPT_ORDER = helper.Item()
    INL_PRICE = helper.Item()
    INL_CLIENT_CATEGORIES = helper.Item()
    INL_MASTER_CATEGORIES = helper.Item()

    def __new__(cls, btn_set: helper.Item = None, args=None, row_width=1):
        if btn_set == cls.REMOVE:
            return ReplyKeyboardRemove()
        key = ReplyKeyboardMarkup(resize_keyboard=True, row_width=row_width)
        ikey = InlineKeyboardMarkup(row_width=row_width)
        if btn_set == cls.BACK:
            key.add(KeyboardButton(misc.back_button))
        elif btn_set == cls.START:
            key.add(*(KeyboardButton(x) for x in misc.role_buttons))
        elif btn_set == cls.CLIENT:
            key.add(*(KeyboardButton(x) for x in misc.client_buttons))
            key.add(KeyboardButton(misc.back_button))
        elif btn_set == cls.MASTER:
            key.row_width = 2
            key.add(*(KeyboardButton(x) for x in misc.master_buttons))
            key.add(KeyboardButton(misc.back_button))
        elif btn_set == cls.SAVE_CHANGES:
            key.add(*(KeyboardButton(x) for x in (misc.save_changes, misc.back_button)))
        elif btn_set == cls.EDIT:
            key.add(*(KeyboardButton(x) for x in ('Изменить', misc.back_button)))
        elif btn_set == cls.NEXT:
            key.add(*(KeyboardButton(x) for x in (misc.back_button, misc.next_button)))
        elif btn_set == cls.RENEW_SUBSCRIPTION:
            key.add(*(KeyboardButton(x) for x in (misc.renew_subscription, misc.back_button)))
        elif btn_set == cls.SEND_LOCATION:
            key.add(KeyboardButton('Отправить моё местоположение', request_location=True))
            key.add(KeyboardButton(misc.back_button))
        elif btn_set == cls.INL_CLIENT_ACCEPT_ORDER:
            ikey.add(InlineKeyboardButton('Согласиться', callback_data=set_callback(CallbackFuncs.CLIENT_ACCEPT_ORDER, args)))
        elif btn_set == cls.INL_MASTER_ACCEPT_ORDER:
            ikey.add(InlineKeyboardButton('Выполнить', callback_data=set_callback(CallbackFuncs.MASTER_ACCEPT_ORDER, args)))
        elif btn_set == cls.INL_PRICE:
            ikey.add(*(types.InlineKeyboardButton(sym + '$' * (x + 1), callback_data=set_callback(CallbackFuncs.CHOOSE_PRICE, 2 ** x)) for x, sym in enumerate(args)))
            ikey.add(types.InlineKeyboardButton(misc.next_button, callback_data=set_callback(CallbackFuncs.CHOOSE_PRICE_SUBMIT, None)))
        elif btn_set == cls.INL_CLIENT_CATEGORIES:
            ikey.add(*(types.InlineKeyboardButton(cat, callback_data=set_callback(CallbackFuncs.NEW_ORDER_CATEGORIES, x)) for x, cat in enumerate(misc.categories)))
        elif btn_set == cls.INL_MASTER_CATEGORIES:
            ikey.add(*(types.InlineKeyboardButton(f'{sub} ({args[x]})', callback_data=set_callback(CallbackFuncs.MASTER_CATEGORIES, x)) for x, sub in enumerate(misc.categories)))
        return key or ikey


class Orders:
    class OrderInfo:
        id = None
        client_id = None
        master_id = None
        datetime = None
        latitude = None
        longitude = None
    CLIENT = 'client_id'
    MASTER = 'master_id'

    def __init__(self, user_id, name):
        self._select(user_id, name)
        self.orders = []
        for res in self.result:
            order = self.OrderInfo()
            order.id, order.client_id, order.master_id, order.datetime, order.latitude, order.longitude = res
            self.orders.append(order)

    def _select(self, user_id, type_):
        selectQuery = f"SELECT ID, client_id, master_id, datetime, ST_X(location), ST_Y(location) FROM orders WHERE {type_}=(%s) ORDER BY datetime"
        with DatabaseConnection() as db:
            conn, cursor = db
            cursor.execute(selectQuery, [user_id])
            result = cursor.fetchall()
        self.result = result or ()


async def delete_message(func, **kwargs):
    with suppress(exceptions.MessageCantBeDeleted,
                  exceptions.MessageToDeleteNotFound):
        await func(**kwargs)


async def send_message(func, **kwargs):
    with suppress(exceptions.BotBlocked,
                  exceptions.UserDeactivated,
                  exceptions.ChatNotFound,
                  exceptions.BadRequest):
        return await func(**kwargs)


def esc_md(s):
    if s is None:
        return ''
    if isinstance(s, str):
        if not s: return ''
        return s.replace('_', '\\_').replace('*', '\\*').replace('`', "'").replace('[', '\\[')
    if isinstance(s, dict):
        return {key: esc_md(x) for key, x in s.items()}
    if isinstance(s, list):
        return list(map(lambda x: esc_md(x), s))
    if isinstance(s, (int, float, bool)):
        return str(s)


def get_update_json(filename, key=None, value=None):
    with open(filename, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not key:
        return data
    if not value:
        return data.get(key)
    data[key] = value
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)


def set_callback(func, data):
    return callback_data.CallbackData('@', 'func', 'json', sep='&').new(func, json.dumps(data, separators=(',', ':')))


def get_callback(data):
    try:
        cd = callback_data.CallbackData('@', 'func', 'json', sep='&').parse(data)
    except ValueError:
        return
    parsed = cd.get('json')
    func = cd.get('func')
    if parsed is None or func is None or not func.isdigit():
        return
    return int(func), json.loads(parsed)


def loc_str(x: float, y: float) -> str:
    return f'POINT({x} {y})'


def get_subcategory_name(index: int) -> str:
    i = 0
    for cat, sub in enumerate(misc.subcategories):
        if len(sub) + i <= index:
            i += len(sub)
        else:
            return misc.categories[cat] + ': ' + sub[index - i]


def count_categories(subs: list) -> tuple:
    res_list = []
    res_count = i = 0
    subs = [int(x) for x in subs]
    for sub in misc.subcategories:
        sub_len = len(sub)
        subs_count = 0
        for s in subs:
            if i <= s < i + sub_len:
                subs_count += 1
        res_list.append(subs_count)
        if subs_count:
            res_count += 1
        i += sub_len
    return res_count, res_list


def get_location(latitude: float, longitude: float, lang='en', pretty=0, no_annotations=1) -> Optional[str]:
    response = requests.get(misc.opencage_api_url, params={
        'key': config.OPENCAGE_KEY,
        'q': f'{latitude},{longitude}',
        'language': lang,
        'pretty': pretty,
        'no_annotations': no_annotations,
        'roadinfo': 1
    })
    if response.status_code == 200:
        result = response.json()
        location = result['results'][0]['components']

        # if location.get('country', '') != 'Украина':
        #     return 0
        ret = list()
        ret.append(location.get('state'))
        if location.get('city'):
            ret.append(location.get('city'))
        else:
            ret.append(location.get('county'))
            ret.append(location.get('hamlet'))
        ret.append(location.get('road'))

        ret = filter(lambda x: x is not None, ret)
        ret = ', '.join(ret)
        if ret:
            return ret


def way_for_pay_request_purchase(user_id, amount):
    date = int(time.time())
    order_reference = f'{date}_{user_id}'
    secret = config.WAY_FOR_PAY_SECRET.encode('utf-8')
    str_signature = f'{config.WAY_FOR_PAY_MERCHANT_ID};{misc.way_for_pay_merchant_domain_name};{order_reference};{date};{amount};UAH;Пополнение баланса;1;{amount}'.encode('utf-8')
    hash_signature = hmac.new(secret, str_signature, 'MD5').hexdigest()
    res = requests.post(misc.way_for_pay_url, json={
        'transactionType': 'CREATE_INVOICE',
        'merchantAccount': config.WAY_FOR_PAY_MERCHANT_ID,
        'merchantAuthType': 'SimpleSignature',
        'apiVersion': 1,
        'merchantDomainName': misc.way_for_pay_merchant_domain_name,
        'merchantTransactionSecureType': 'AUTO',
        'merchantSignature': hash_signature,
        'serviceUrl': config.WAY_FOR_PAY_SERVICE_URL,
        'orderReference': order_reference,
        'orderDate': date,
        'amount': amount,
        'currency': 'UAH',
        'productName': ['Пополнение баланса'],
        'productPrice': [amount],
        'productCount': [1],
    })
    response = json.loads(res.text)
    if response['reason'] == 'Ok':
        return response['invoiceUrl']
    else:
        return False, response['reason']


async def bulk_mailing(data, form_id):
    optimized = True  # max measurement error ~1.4 (sqrt of 2)
    r = 5  # km
    selectQuery1 = "SELECT user_id FROM (" \
                   "    SELECT " \
                   "    user_id, " \
                   "    categories, " \
                   "    @x2:=%s, @y2=%s, " \
                   "    @x1:=ST_X(location), @y1:=ST_Y(location), " \
                   "    @f1:=@x1*PI()/180, @f2:=@x2*PI()/180, " \
                   "    @d1:=(@x2-@x1)*PI()/180, @d2:=(@y2-@y1)*PI()/180, " \
                   "    @a:=SIN(@d1/2)*SIN(@d1/2)+COS(@f1)*COS(@f2)*SIN(@d2/2)*SIN(@d2/2), " \
                   "    @dist:=6371000*2*ATAN2(SQRT(@a), SQRT(1-@a)) " \
                   "    FROM masters) QA " \
                   "WHERE @dist <= %s AND categories LIKE (%s)"
    selectQuery2 = "SELECT user_id FROM masters WHERE " \
                   "ST_X(location) <= %s AND " \
                   "ST_X(location) >= %s AND " \
                   "ST_Y(location) <= %s AND " \
                   "ST_Y(location) >= %s AND " \
                   "categories LIKE (%s)"
    cat_filter = f'%"{data["category"]}"%'
    x, y = data['x'], data['y']
    latitude_dist = 111.3
    longitude_dist = cos(radians(x)) * latitude_dist
    # only for right hemisphere
    # |¯¯a¯¯|
    # |b   c|
    # |__d__|
    a = x + (r / latitude_dist)
    d = x - (r / latitude_dist)
    b = y - (r / longitude_dist)
    c = y + (r / longitude_dist)
    with DatabaseConnection() as db:
        conn, cursor = db
        if optimized:
            cursor.executemany(selectQuery2, [(a, d, c, b, cat_filter)])
        else:
            cursor.executemany(selectQuery1, [(x, y, r, cat_filter)])
        result = cursor.fetchall()
    media_post = None
    price = ''
    price_flags = data['price']
    for i in range(3):
        if price_flags & 2 ** i:
            if price: price += ', '
            price += '$' * (i + 1)
    category = get_subcategory_name(data['category'])
    form_text = esc_md(data['form_text'])
    dt = datetime.fromtimestamp(data['timestamp'])
    text = f"*Новый заказ!*\n*Категория:* {category}\n*Дата*: {dt.day} {misc.month_names[dt.month - 1]}\n" \
           f"*Время:* {data['time']}\n*Ценовая категория:* {price}\n*Комментарий:* {form_text}"
    if data['photo']:
        if len(data['photo']) == 1:
            media_post = await misc.bot.send_photo(misc.media_chat_id, data['photo'][0])
        else:
            photos = [types.InputMediaPhoto(x) for x in data['photo']]
            media_post = await misc.bot.send_media_group(misc.media_chat_id, photos)
            media_post = media_post[0]
    elif data['video']:
        media_post = await misc.bot.send_video(misc.media_chat_id, data['video'], caption=data['form_text'])
    if media_post:
        text = f'[­]({misc.media_chat}/{media_post.message_id})' + text
    for res in result:
        await send_message(misc.bot.send_message, chat_id=res[0], text=text, parse_mode='Markdown', reply_markup=ButtonSet(ButtonSet.INL_MASTER_ACCEPT_ORDER, form_id))
        await sleep(.05)


__all__ = ('ButtonSet', 'CallbackFuncs', 'delete_message', 'send_message', 'esc_md', 'set_callback', 'get_callback',
           'get_location', 'way_for_pay_request_purchase', 'loc_str', 'bulk_mailing', 'count_categories', 'Orders')
