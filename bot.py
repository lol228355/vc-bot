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
    # Таблица юзеров
    db_query('''CREATE TABLE IF NOT EXISTS users 
                (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, is_banned INTEGER DEFAULT 0)''')
    # Таблица услуг
    db_query('CREATE TABLE IF NOT EXISTS my_services (s_id INTEGER PRIMARY KEY, name TEXT, my_price REAL)')
    # Таблица заказов
    db_query('''CREATE TABLE IF NOT EXISTS orders 
                (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, order_id_site TEXT, service_name TEXT, qty INTEGER, cost REAL)''')

def is_user_banned(user_id):
    res = db_query("SELECT is_banned FROM users WHERE id=?", (user_id,), True)
    return res[0][0] == 1 if res else False

# --- ГЛАВНОЕ МЕНЮ ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    if is_user_banned(message.chat.id):
        bot.send_message(message.chat.id, "❌ **Доступ ограничен.** Вы заблокированы.", parse_mode="Markdown")
        return

    if not db_query("SELECT id FROM users WHERE id=?", (message.chat.id,), True):
        db_query("INSERT INTO users (id, balance, is_banned) VALUES (?, 0, 0)", (message.chat.id,))
    
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # Кнопки сверху
    markup.row("📦 Каталог", "👤 Профиль")
    markup.row("📋 Мои заказы")
    
    welcome = (
        "💎 **Добро пожаловать в SMM Store!**\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Лучшие цены на накрутку здесь. Выберите раздел меню ниже."
    )
    if message.from_user.id in ADMIN_IDS:
        welcome += "\n\n🛠 **Админ-команды:** `/add`, `/del`, `/ban`, `/unban`, `/give`, `/take`, `/broadcast`, `/stats`"
        
    bot.send_message(message.chat.id, welcome, reply_markup=markup, parse_mode="Markdown")

# --- МОИ ЗАКАЗЫ ---
@bot.message_handler(func=lambda m: m.text == "📋 Мои заказы")
def my_orders(message):
    if is_user_banned(message.chat.id): return
    orders = db_query("SELECT order_id_site, service_name, qty, cost FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10", (message.chat.id,), True)
    
    if not orders:
        bot.send_message(message.chat.id, "🛒 **У вас пока нет заказов.**\nСамое время что-нибудь заказать!", parse_mode="Markdown")
        return
    
    msg = "📋 **Ваши последние 10 заказов:**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for o in orders:
        msg += f"🔹 **ID:** `{o[0]}` | {o[1]}\n┗ Кол-во: {o[2]} шт. | Цена: {round(o[3], 2)} руб.\n\n"
    
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

# --- ПРОФИЛЬ ---
@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    if is_user_banned(message.chat.id): return
    res = db_query("SELECT balance FROM users WHERE id=?", (message.chat.id,), True)
    bal = res[0][0] if res else 0
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("➕ Пополнить баланс", callback_data="start_deposit"))
    
    text = (
        f"👤 **Ваш личный кабинет**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🆔 ID: `{message.chat.id}`\n"
        f"💰 Баланс: `{round(bal, 2)}` **руб.**\n"
    )
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

# --- АДМИН-ЛОГИКА ---
@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id not in ADMIN_IDS: return
    u_cnt = db_query("SELECT COUNT(*) FROM users", fetch=True)[0][0]
    o_cnt = db_query("SELECT COUNT(*) FROM orders", fetch=True)[0][0]
    bot.send_message(message.chat.id, f"📊 **Статистика:**\nЮзеров: {u_cnt}\nВсего заказов: {o_cnt}")

@bot.message_handler(commands=['add'])
def admin_add(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, s_id, price = message.text.split()
        all_s = requests.post(API_URL_VING, data={'key': API_KEY_VING, 'action': 'services'}).json()
        info = next((s for s in all_s if str(s['service']) == s_id), None)
        if info:
            db_query("INSERT OR REPLACE INTO my_services (s_id, name, my_price) VALUES (?, ?, ?)", (s_id, info['name'], float(price)))
            bot.send_message(message.chat.id, f"✅ Добавлено: **{info['name']}** за {price}р")
    except: bot.send_message(message.chat.id, "Формат: `/add ID цена`")

@bot.message_handler(commands=['broadcast'])
def admin_broadcast(message):
    if message.from_user.id not in ADMIN_IDS: return
    text = message.text.replace('/broadcast ', '')
    users = db_query("SELECT id FROM users", fetch=True)
    for u in users:
        try: bot.send_message(u[0], f"📢 **Внимание!**\n\n{text}", parse_mode="Markdown")
        except: continue
    bot.send_message(message.chat.id, "✅ Рассылка завершена.")

@bot.message_handler(commands=['give'])
def admin_give(message):
    if message.from_user.id not in ADMIN_IDS: return
    try:
        _, u_id, amt = message.text.split()
        db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (float(amt), u_id))
        bot.send_message(message.chat.id, f"✅ Выдали {amt} руб юзеру {u_id}")
    except: pass

@bot.message_handler(commands=['ban'])
def admin_ban(message):
    if message.from_user.id not in ADMIN_IDS: return
    u_id = message.text.split()[1]
    db_query("UPDATE users SET is_banned = 1 WHERE id = ?", (u_id,))
    bot.send_message(message.chat.id, f"🚫 Забанен: {u_id}")

# --- ПОПОЛНЕНИЕ (CALLBACK) ---
@bot.callback_query_handler(func=lambda call: call.data == "start_deposit")
def deposit_step1(call):
    if is_user_banned(call.message.chat.id): return
    msg = bot.send_message(call.message.chat.id, "💰 Введите сумму в **рублях** для пополнения:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, dep_pay)

def dep_pay(message):
    try:
        rub = float(message.text)
        usdt = round(rub / USDT_COURSE, 2)
        if usdt < 0.01: usdt = 0.01
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        payload = {'asset': 'USDT', 'amount': usdt, 'description': f'Пополнение баланса'}
        res = requests.post('https://pay.crypt.bot/api/createInvoice', headers=headers, json=payload).json()
        if res['ok']:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Перейти к оплате", url=res['result']['pay_url']))
            markup.add(types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"chk_{res['result']['invoice_id']}_{rub}"))
            bot.send_message(message.chat.id, f"💵 К оплате: `{usdt}` **USDT** (~{rub} руб.)", reply_markup=markup, parse_mode="Markdown")
    except: bot.send_message(message.chat.id, "⚠️ Введите число.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('chk_'))
def chk_pay(call):
    _, inv_id, rub = call.data.split('_')
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    res = requests.get('https://pay.crypt.bot/api/getInvoices', headers=headers, params={'invoice_ids': inv_id}).json()
    if res['ok'] and res['result']['items'][0]['status'] == 'paid':
        db_query("UPDATE users SET balance = balance + ? WHERE id = ?", (float(rub), call.message.chat.id))
        bot.edit_message_text(f"💳 **Баланс пополнен на {rub} руб.!**", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    else: bot.answer_callback_query(call.id, "Оплата не найдена.", show_alert=True)

# --- КАТАЛОГ И ЗАКАЗ ---
@bot.message_handler(func=lambda m: m.text == "📦 Каталог")
def catalog(message):
    if is_user_banned(message.chat.id): return
    services = db_query("SELECT s_id, name, my_price FROM my_services", fetch=True)
    if not services:
        bot.send_message(message.chat.id, "📂 **Каталог пуст.** Админы скоро добавят услуги.", parse_mode="Markdown")
        return
    markup = types.InlineKeyboardMarkup()
    for s_id, name, price in services:
        markup.add(types.InlineKeyboardButton(f"✨ {name} | {price}₽", callback_data=f"buy_{s_id}_{price}"))
    bot.send_message(message.chat.id, "⬇️ **Выберите интересующую услугу:**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('buy_'))
def buy_start(call):
    if is_user_banned(call.message.chat.id): return
    _, s_id, price = call.data.split('_')
    user_steps[call.message.chat.id] = {'s_id': s_id, 'price': float(price)}
    bot.send_message(call.message.chat.id, "🔗 **Отправьте ссылку на профиль/пост:**", parse_mode="Markdown")
    bot.register_next_step_handler(call.message, get_q)

def get_q(message):
    user_steps[message.chat.id]['link'] = message.text
    bot.send_message(message.chat.id, "🔢 **Введите количество (цифрами):**", parse_mode="Markdown")
    bot.register_next_step_handler(message, finalize)

def finalize(message):
    try:
        qty = int(message.text)
        data = user_steps[message.chat.id]
        cost = (data['price'] / 1000) * qty
        bal = db_query("SELECT balance FROM users WHERE id=?", (message.chat.id,), True)[0][0]
        
        if bal < cost:
            bot.send_message(message.chat.id, f"❌ **Недостаточно средств.**\nНужно: `{round(cost, 2)}` руб.\nВаш баланс: `{round(bal, 2)}` руб.", parse_mode="Markdown")
            return
            
        res = requests.post(API_URL_VING, data={'key': API_KEY_VING, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}).json()
        
        if 'order' in res:
            # Списываем баланс
            db_query("UPDATE users SET balance = balance - ? WHERE id = ?", (cost, message.chat.id))
            # Сохраняем в историю заказов
            db_query("INSERT INTO orders (user_id, order_id_site, service_name, qty, cost) VALUES (?, ?, ?, ?, ?)", 
                     (message.chat.id, res['order'], "Услуга #" + str(data['s_id']), qty, cost))
            
            bot.send_message(message.chat.id, f"✅ **Заказ успешно создан!**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n🆔 ID заказа: `{res['order']}`\n💰 Списано: `{round(cost, 2)}` руб.", parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, f"❌ **Ошибка API сайта:** {res.get('error')}", parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "⚠️ **Ошибка.** Пожалуйста, введите корректное число.")

if __name__ == '__main__':
    init_db()
    print("Бот успешно запущен и оформлен!")
    bot.infinity_polling()
