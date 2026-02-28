import telebot
import requests
import sqlite3
from telebot import types

# ================= НАСТРОЙКИ =================
API_KEY_VING = 'cdlFcWjrPF7pOwJeXjhELoGYGxsVCZTrvlS396wH8QXg2XlRquw9Z7NCyi5W'
BOT_TOKEN = '8799904851:AAGRmbHUBjGqdBHiwk0sGIxeZwS9sB8nRsI'
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
    # Добавлена колонка is_banned (0 - ок, 1 - забанен)
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
    db_query('CREATE TABLE IF NOT EXISTS my_services (s_id INTEGER PRIMARY KEY, name TEXT, my_price REAL)')

# Проверка на бан перед любым действием
def is_user_banned(user_id):
    res = db_query("SELECT is_banned FROM users WHERE id=?", (user_id,), True)
    return res[0][0] == 1 if res else False

# --- ГЛАВНОЕ МЕНЮ ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    if is_user_banned(message.chat.id):
        bot.send_message(message.chat.id, "❌ Вы заблокированы в этом боте.")
        return

    if not db_query("SELECT id FROM users WHERE id=?", (message.chat.id,), True):
        db_query("INSERT INTO users (id, balance, is_banned) VALUES (?, 0, 0)", (message.chat.id,))
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📦 Каталог услуг", "👤 Профиль")
    
    welcome = "👋 Добро пожаловать!"
    if message.from_user.id in ADMIN_IDS:
        welcome += "\n\n🔑 **Админ-панель:**\n/add [ID] [Цена] | /del [ID]\n/ban [ID] | /unban [ID]\n/give [ID] [Сумма] | /take [ID] [Сумма]\n/broadcast [Текст] | /stats"
        
    bot.send_message(message.chat.id, welcome, reply_markup=markup, parse_mode="Markdown")

# --- ПРОФИЛЬ ---
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    if is_user_banned(message.chat.id): return
    res = db_query("SELECT balance FROM users WHERE id=?", (message.chat.id,), True)
    bal = res[0][0] if res else 0
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="start_deposit"))
    bot.send_message(message.chat.id, f"👤 **Ваш профиль**\n\n🆔 ID: `{message.chat.id}`\n💰 Баланс: **{round(bal, 2)} руб.**", 
                     reply_markup=markup, parse_mode="Markdown")

# --- АДМИН-КОМАНДЫ (УПРАВЛЕНИЕ ЮЗЕРАМИ) ---
@bot.message_handler(commands=['ban'])
def admin_ban(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        u_id = message.text.split()[1]
        db_query("UPDATE users SET is_banned = 1 WHERE id = ?", (u_id,))
        bot.send_message(message.chat.id, f"🚫 Пользователь {u_id} забанен.")
    except: bot.send_message(message.chat.id, "Формат: `/ban 12345678`", parse_mode="Markdown")

@bot.message_handler(commands=['unban'])
def admin_unban(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        u_id = message.text.split()[1]
        db_query("UPDATE users SET is_banned = 0 WHERE id = ?", (u_id,))
        bot.send_message(message.chat.id, f"✅ Пользователь {u_id} разбанен.")
    except: bot.send_message(message.chat.id, "Формат: `/unban 12345678`", parse_mode="Markdown")

@bot.message_handler(commands=['give'])
def admin_give(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, u_id, amount = message.text.split()
        db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (float(amount), u_id))
        bot.send_message(message.chat.id, f"💰 Начислено {amount} руб. пользователю {u_id}")
    except: bot.send_message(message.chat.id, "Формат: `/give 12345678 500`", parse_mode="Markdown")

@bot.message_handler(commands=['take'])
def admin_take(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, u_id, amount = message.text.split()
        db_query("UPDATE users SET balance = balance - ? WHERE id = ?", (float(amount), u_id))
        bot.send_message(message.chat.id, f"📉 Списано {amount} руб. у пользователя {u_id}")
    except: bot.send_message(message.chat.id, "Формат: `/take 12345678 500`", parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if message.from_user.id not in ADMIN_IDS: return
    text = message.text.replace('/broadcast ', '')
    if not text or text == '/broadcast':
        bot.send_message(message.chat.id, "Напишите текст после команды.")
        return
    users = db_query("SELECT id FROM users", fetch=True)
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 **Рассылка:**\n\n{text}", parse_mode="Markdown")
            count += 1
        except: continue
    bot.send_message(message.chat.id, f"✅ Рассылка завершена. Получили: {count} чел.")

# --- ОСТАЛЬНЫЕ АДМИН-КОМАНДЫ (Add, Del, Stats) ---
@bot.message_handler(commands=['add'])
def admin_add(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, s_id, price = message.text.split()
        all_s = requests.post(API_URL_VING, data={'key': API_KEY_VING, 'action': 'services'}).json()
        info = next((s for s in all_s if str(s['service']) == s_id), None)
        if info:
            db_query("INSERT OR REPLACE INTO my_services (s_id, name, my_price) VALUES (?, ?, ?)", (s_id, info['name'], float(price)))
            bot.send_message(message.chat.id, f"✅ Добавлено: {info['name']}\nЦена: {price} руб.")
    except: bot.send_message(message.chat.id, "Формат: `/add [ID] [Цена]`")

@bot.message_handler(commands=['del'])
def admin_del(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        s_id = message.text.split()[1]
        db_query("DELETE FROM my_services WHERE s_id=?", (s_id,))
        bot.send_message(message.chat.id, "Удалено.")
    except: bot.send_message(message.chat.id, "Формат: `/del [ID]`")

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id not in ADMIN_IDS: return
    u_cnt = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
    s_cnt = db_query("SELECT COUNT(*) FROM my_services", fetch=True)[0][0]
    bot.send_message(message.chat.id, f"📊 Юзеров: {u_cnt}\n📦 Услуг: {s_cnt}")

# --- ПОПОЛНЕНИЕ (CALLBACK) ---
@bot.callback_query_handler(func=lambda call: call.data == "start_deposit")
def deposit_step1(call):
    if is_user_banned(call.message.chat.id): return
    msg = bot.send_message(call.message.chat.id, "Введите сумму в **рублях**:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, dep_pay)

def dep_pay(message):
    try:
        rub = float(message.text)
        usdt = round(rub / USDT_COURSE, 2)
        if usdt < 0.01: usdt = 0.01
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        payload = {'asset': 'USDT', 'amount': usdt, 'description': f'Пополнение {rub} RUB'}
        res = requests.post('https://pay.crypt.bot/api/createInvoice', headers=headers, json=payload).json()
        if res['ok']:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Оплатить", url=res['result']['pay_url']))
            markup.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"chk_{res['result']['invoice_id']}_{rub}"))
            bot.send_message(message.chat.id, f"Счет: {usdt} USDT (~{rub} руб.)", reply_markup=markup)
    except: bot.send_message(message.chat.id, "Введите число.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('chk_'))
def chk_pay(call):
    _, inv_id, rub = call.data.split('_')
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    res = requests.get('https://pay.crypt.bot/api/getInvoices', headers=headers, params={'invoice_ids': inv_id}).json()
    if res['ok'] and res['result']['items'][0]['status'] == 'paid':
        db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (float(rub), call.message.chat.id))
        bot.edit_message_text(f"✅ Баланс пополнен на {rub} руб.!", call.message.chat.id, call.message.message_id)
    else: bot.answer_callback_query(call.id, "Оплата не найдена.", show_alert=True)

# --- КАТАЛОГ И ЗАКАЗ ---
@bot.message_handler(func=lambda m: m.text == "📦 Каталог услуг")
def catalog(message):
    if is_user_banned(message.chat.id): return
    services = db_query("SELECT s_id, name, my_price FROM my_services", fetch=True)
    if not services:
        bot.send_message(message.chat.id, "Каталог пока пуст.")
        return
    markup = types.InlineKeyboardMarkup()
    for s_id, name, price in services:
        markup.add(types.InlineKeyboardButton(f"{name} — {price} руб/1к", callback_data=f"buy_{s_id}_{price}"))
    bot.send_message(message.chat.id, "Выберите услугу:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def buy_start(call):
    if is_user_banned(call.message.chat.id): return
    _, s_id, price = call.data.split('_')
    user_steps[call.message.chat.id] = {'s_id': s_id, 'price': float(price)}
    bot.send_message(call.message.chat.id, "🔗 Отправьте ссылку:")
    bot.register_next_step_handler(call.message, get_q)

def get_q(message):
    user_steps[message.chat.id]['link'] = message.text
    bot.send_message(message.chat.id, "🔢 Количество:")
    bot.register_next_step_handler(message, finalize)

def finalize(message):
    try:
        qty = int(message.text)
        data = user_steps[message.chat.id]
        cost = (data['price'] / 1000) * qty
        bal = db_query("SELECT balance FROM users WHERE id=?", (message.chat.id,), True)[0][0]
        if bal < cost:
            bot.send_message(message.chat.id, "❌ Недостаточно средств.")
            return
        res = requests.post(API_URL_VING, data={'key': API_KEY_VING, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}).json()
        if 'order' in res:
            db_query("UPDATE users SET balance = balance - ? WHERE id = ?", (cost, message.chat.id))
            bot.send_message(message.chat.id, f"✅ Заказ №{res['order']} создан!")
        else: bot.send_message(message.chat.id, f"Ошибка: {res.get('error')}")
    except: bot.send_message(message.chat.id, "Ошибка.")

if __name__ == '__main__':
    init_db()
    bot.infinity_polling()
