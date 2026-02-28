import telebot
import requests
import sqlite3
from telebot import types

# ================= НАСТРОЙКИ =================
API_KEY_VING = 'cdlFcWjrPF7pOwJeXjhELoGYGxsVCZTrvlS396wH8QXg2XlRquw9Z7NCyi5W'
BOT_TOKEN = '8799904851:AAF8AfaiFdvjK1fqf3BdCb0GG7JwyEVODtg'
CRYPTO_TOKEN = '540404:AA2Rex1G8gtM1zNSPWa3pADmtHbWx4B2bI8'
API_URL_VING = 'https://vingboost.ru/api/v2'

ADMIN_IDS = [8119723042, 8663017094]
USDT_COURSE = 95.0 
# =============================================

bot = telebot.TeleBot(BOT_TOKEN)
user_steps = {}

# --- БАЗА ДАННЫХ ---
def db_query(sql, params=(), fetch=False):
    with sqlite3.connect('shop.db') as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        if fetch: return cursor.fetchall()
        conn.commit()

def init_db():
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
    db_query('''CREATE TABLE IF NOT EXISTS my_services 
                (s_id INTEGER PRIMARY KEY, name TEXT, my_price REAL, category TEXT)''')
    db_query('''CREATE TABLE IF NOT EXISTS orders 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, order_id_site TEXT, service_name TEXT, qty INTEGER, cost REAL)''')
    db_query('''CREATE TABLE IF NOT EXISTS promos 
                (code TEXT PRIMARY KEY, amount REAL)''')

def is_user_banned(user_id):
    res = db_query("SELECT is_banned FROM users WHERE id=?", (user_id,), True)
    return res[0][0] == 1 if res else False

# --- ГЛАВНОЕ МЕНЮ (INLINE) ---
def main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📦 Каталог", callback_data="open_catalog"),
        types.InlineKeyboardButton("👤 Профиль", callback_data="open_profile")
    )
    markup.add(types.InlineKeyboardButton("📋 Мои заказы", callback_data="my_orders"))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    if is_user_banned(message.chat.id): return
    
    if not db_query("SELECT id FROM users WHERE id=?", (message.chat.id,), True):
        db_query("INSERT INTO users (id, balance, is_banned) VALUES (?, 0, 0)", (message.chat.id,))
    
    welcome = (
        "✨ **SMM PREMIUM STORE** ✨\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "🚀 Лучший сервис автоматической накрутки.\n"
        "Выберите раздел ниже:"
    )
    bot.send_message(message.chat.id, welcome, reply_markup=main_menu_markup(), parse_mode="Markdown")

# --- ОБРАБОТКА CALLBACK ---
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    uid = call.message.chat.id
    if is_user_banned(uid): return

    if call.data == "to_main":
        bot.edit_message_text("🚀 Выберите нужное действие ниже:", uid, call.message.message_id, reply_markup=main_menu_markup())

    elif call.data == "open_profile":
        res = db_query("SELECT balance FROM users WHERE id=?", (uid,), True)
        bal = res[0][0] if res else 0
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("➕ Пополнить", callback_data="start_deposit"),
                   types.InlineKeyboardButton("🎁 Промокод", callback_data="activate_promo"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="to_main"))
        
        text = f"👤 **ЛИЧНЫЙ КАБИНЕТ**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🆔 ID: `{uid}`\n💰 Баланс: `{round(bal, 2)}` **RUB**"
        bot.edit_message_text(text, uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "open_catalog":
        cats = db_query("SELECT DISTINCT category FROM my_services", fetch=True)
        if not cats:
            bot.answer_callback_query(call.id, "Каталог пока пуст!", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        for c in cats:
            markup.add(types.InlineKeyboardButton(f"📁 {c[0]}", callback_data=f"cat_{c[0]}"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="to_main"))
        bot.edit_message_text("📂 **Выберите категорию:**", uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data.startswith("cat_"):
        cat_name = call.data[4:]
        services = db_query("SELECT s_id, name, my_price FROM my_services WHERE category=?", (cat_name,), True)
        markup = types.InlineKeyboardMarkup()
        for s in services:
            markup.add(types.InlineKeyboardButton(f"{s[1]} | {s[2]}₽", callback_data=f"buy_{s[0]}_{s[2]}"))
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="open_catalog"))
        bot.edit_message_text(f"📍 **Услуги: {cat_name}**", uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "my_orders":
        orders = db_query("SELECT order_id_site, service_name, qty, cost FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,), True)
        msg = "📋 **ВАШИ ЗАКАЗЫ:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n" if orders else "🛒 Заказов еще нет."
        for o in orders:
            msg += f"🆔 `{o[0]}` | {o[1]}\n┗ {o[2]} шт. | {round(o[3],2)} RUB\n\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="to_main"))
        bot.edit_message_text(msg, uid, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif call.data == "start_deposit":
        msg = bot.send_message(uid, "💰 Введите сумму (RUB):")
        bot.register_next_step_handler(msg, process_deposit)

    elif call.data == "activate_promo":
        msg = bot.send_message(uid, "🎁 Введите промокод:")
        bot.register_next_step_handler(msg, process_promo)

    elif call.data.startswith("chk_"):
        _, inv_id, rub = call.data.split('_')
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        res = requests.get('https://pay.crypt.bot/api/getInvoices', headers=headers, params={'invoice_ids': inv_id}).json()
        if res['ok'] and res['result']['items'][0]['status'] == 'paid':
            db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (float(rub), uid))
            bot.send_message(uid, f"✅ Баланс пополнен на {rub} RUB!")
        else:
            bot.answer_callback_query(call.id, "Оплата не найдена.", show_alert=True)

    elif call.data.startswith("buy_"):
        _, s_id, price = call.data.split('_')
        user_steps[uid] = {'s_id': s_id, 'price': float(price)}
        bot.send_message(uid, "🔗 Отправьте ссылку:")
        bot.register_next_step_handler(call.message, get_order_link)

# --- ЛОГИКА ЗАКАЗА ---
def get_order_link(message):
    user_steps[message.chat.id]['link'] = message.text
    bot.send_message(message.chat.id, "🔢 Введите количество:")
    bot.register_next_step_handler(message, finalize_order)

def finalize_order(message):
    try:
        qty = int(message.text)
        data = user_steps[message.chat.id]
        cost = (data['price'] / 1000) * qty
        bal = db_query("SELECT balance FROM users WHERE id=?", (message.chat.id,), True)[0][0]
        if bal < cost:
            bot.send_message(message.chat.id, f"❌ Недостаточно средств! Нужно {round(cost,2)} RUB")
            return
        res = requests.post(API_URL_VING, data={'key': API_KEY_VING, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}).json()
        if 'order' in res:
            db_query("UPDATE users SET balance = balance - ? WHERE id = ?", (cost, message.chat.id))
            db_query("INSERT INTO orders (user_id, order_id_site, service_name, qty, cost) VALUES (?, ?, ?, ?, ?)", 
                     (message.chat.id, res['order'], f"Услуга #{data['s_id']}", qty, cost))
            bot.send_message(message.chat.id, f"✅ Заказ №{res['order']} принят!")
        else: bot.send_message(message.chat.id, f"Ошибка API: {res.get('error')}")
    except: bot.send_message(message.chat.id, "⚠️ Ошибка ввода.")

# --- ПОПОЛНЕНИЕ И ПРОМО ---
def process_deposit(message):
    try:
        rub = float(message.text)
        usdt = round(rub / USDT_COURSE, 2)
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        res = requests.post('https://pay.crypt.bot/api/createInvoice', headers=headers, json={'asset': 'USDT', 'amount': usdt}).json()
        if res['ok']:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Оплатить", url=res['result']['pay_url']))
            markup.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"chk_{res['result']['invoice_id']}_{rub}"))
            bot.send_message(message.chat.id, f"💵 Счет: {usdt} USDT (~{rub} RUB)", reply_markup=markup)
    except: bot.send_message(message.chat.id, "Введите число.")

def process_promo(message):
    code = message.text
    res = db_query("SELECT amount FROM promos WHERE code=?", (code,), True)
    if res:
        amt = res[0][0]
        db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (amt, message.chat.id))
        db_query("DELETE FROM promos WHERE code=?", (code,))
        bot.send_message(message.chat.id, f"🎁 Зачислено {amt} RUB!")
    else: bot.send_message(message.chat.id, "❌ Неверный код.")

# --- АДМИН КОМАНДЫ ---
@bot.message_handler(commands=['users'])
def admin_users(message):
    if message.from_user.id not in ADMIN_IDS: return
    users = db_query("SELECT id, balance FROM users", fetch=True)
    msg = "👥 **СПИСОК ПОЛЬЗОВАТЕЛЕЙ:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for u in users:
        msg += f"👤 ID: `{u[0]}` | Баланс: `{u[1]}₽`\n"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(commands=['add'])
def admin_add(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, s_id, price, cat = message.text.split()
        all_s = requests.post(API_URL_VING, data={'key': API_KEY_VING, 'action': 'services'}).json()
        info = next((s for s in all_s if str(s['service']) == s_id), None)
        if info:
            db_query("INSERT OR REPLACE INTO my_services (s_id, name, my_price, category) VALUES (?, ?, ?, ?)", (s_id, info['name'], float(price), cat))
            bot.send_message(message.chat.id, f"✅ Добавлено: {info['name']} ({cat})")
    except: bot.send_message(message.chat.id, "Формат: `/add ID Цена Категория`")

@bot.message_handler(commands=['promo'])
def admin_promo(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, code, amt = message.text.split()
        db_query("INSERT INTO promos (code, amount) VALUES (?, ?)", (code, float(amt)))
        bot.send_message(message.chat.id, f"🎫 Код `{code}` на {amt}₽ создан!")
    except: bot.send_message(message.chat.id, "Формат: `/promo код сумма`")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if message.from_user.id not in ADMIN_IDS: return
    txt = message.text.replace('/broadcast ', '')
    u_list = db_query("SELECT id FROM users", fetch=True)
    for u in u_list:
        try: bot.send_message(u[0], f"📢 **ОБЪЯВЛЕНИЕ:**\n\n{txt}", parse_mode="Markdown")
        except: continue
    bot.send_message(message.chat.id, "✅ Рассылка завершена.")

if __name__ == '__main__':
    init_db()
    bot.infinity_polling()
