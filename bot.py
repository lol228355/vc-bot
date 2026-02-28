import telebot
import requests
import sqlite3
from telebot import types

# ================= НАСТРОЙКИ =================
# Твой API ключ с сайта vingboost.ru
API_KEY_VING = 'cdlFcWjrPF7pOwJeXjhELoGYGxsVCZTrvlS396wH8QXg2XlRquw9Z7NCyi5W'

# Токен твоего Телеграм-бота
BOT_TOKEN = '8799904851:AAGRmbHUBjGqdBHiwk0sGIxeZwS9sB8nRsI'

# Токен от @CryptoBot (Crypto Pay)
CRYPTO_TOKEN = '540404:AA2Rex1G8gtM1zNSPWa3pADmtHbWx4B2bI8'

# Ссылка на API сайта
API_URL_VING = 'https://vingboost.ru/api/v2'

# Твоя наценка (1.5 = +50% к цене сайта). 
# Например, если на сайте услуга стоит 100р, в боте она будет стоить 150р.
MARGIN = 1.5 
# =============================================

bot = telebot.TeleBot(BOT_TOKEN)
user_steps = {}

# --- РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
    conn.commit()
    conn.close()

def get_balance(user_id):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    if not res:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (id, balance) VALUES (?, ?)", (user_id, 0))
        conn.commit()
        conn.close()
        return 0
    return res[0]

def update_balance(user_id, amount):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

# --- ФУНКЦИЯ ДЛЯ СВЯЗИ С VINGBOOST ---
def ving_api(payload):
    payload['key'] = API_KEY_VING
    try:
        response = requests.post(API_URL_VING, data=payload)
        return response.json()
    except:
        return {"error": "Ошибка связи с сервером Vingboost"}

# --- ГЛАВНОЕ МЕНЮ ---
@bot.message_handler(commands=['start'])
def start(message):
    init_db()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📦 Каталог услуг", "👤 Профиль")
    markup.add("💳 Пополнить баланс")
    bot.send_message(message.chat.id, "🚀 Добро пожаловать! Здесь можно заказать автоматическую накрутку.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "👤 Профиль")
def profile(message):
    bal = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"👤 **Ваш профиль:**\n\n🆔 ID: `{message.from_user.id}`\n💰 Баланс: {round(bal, 2)} USDT", parse_mode="Markdown")

# --- СИСТЕМА ОПЛАТЫ (CRYPTOBOT) ---
@bot.message_handler(func=lambda m: m.text == "💳 Пополнить баланс")
def deposit_init(message):
    msg = bot.send_message(message.chat.id, "Введите сумму пополнения в USDT (например: 5):")
    bot.register_next_step_handler(msg, deposit_create)

def deposit_create(message):
    try:
        amount = float(message.text)
        headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
        payload = {'asset': 'USDT', 'amount': amount, 'description': 'Пополнение SMM'}
        res = requests.post('https://pay.crypt.bot/api/createInvoice', headers=headers, json=payload).json()
        
        if res['ok']:
            pay_url = res['result']['pay_url']
            inv_id = res['result']['invoice_id']
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Оплатить через CryptoBot", url=pay_url))
            markup.add(types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{inv_id}_{amount}"))
            bot.send_message(message.chat.id, f"Счет на {amount} USDT создан!", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "Ошибка CryptoBot. Проверьте токен в настройках.")
    except:
        bot.send_message(message.chat.id, "Введите числовое значение.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_'))
def check_pay(call):
    _, inv_id, amount = call.data.split('_')
    headers = {'Crypto-Pay-API-Token': CRYPTO_TOKEN}
    res = requests.get('https://pay.crypt.bot/api/getInvoices', headers=headers, params={'invoice_ids': inv_id}).json()
    
    if res['ok'] and res['result']['items'][0]['status'] == 'paid':
        update_balance(call.message.chat.id, float(amount))
        bot.edit_message_text(f"✅ Успех! Баланс пополнен на {amount} USDT!", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Оплата не найдена или еще обрабатывается.", show_alert=True)

# --- ВИТРИНА И ЗАКАЗ ---
@bot.message_handler(func=lambda m: m.text == "📦 Каталог услуг")
def show_categories(message):
    services = ving_api({'action': 'services'})
    if not isinstance(services, list):
        bot.send_message(message.chat.id, "Ошибка получения данных с сайта.")
        return

    cats = {}
    for s in services:
        if s['category'] not in cats: cats[s['category']] = s['service']
    
    markup = types.InlineKeyboardMarkup()
    for name, s_id in cats.items():
        markup.add(types.InlineKeyboardButton(name, callback_data=f"cat_{s_id}"))
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def show_services(call):
    ref_id = call.data[4:]
    all_s = ving_api({'action': 'services'})
    target_cat = next(s['category'] for s in all_s if str(s['service']) == ref_id)
    
    markup = types.InlineKeyboardMarkup()
    for s in all_s:
        if s['category'] == target_cat:
            price = round(float(s['rate']) * MARGIN, 2)
            markup.add(types.InlineKeyboardButton(f"{s['name']} — {price} USDT/1к", callback_data=f"sel_{s['service']}_{price}"))
    bot.edit_message_text(f"Услуги {target_cat}:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('sel_'))
def ask_link(call):
    _, s_id, price = call.data.split('_')
    user_steps[call.message.chat.id] = {'s_id': s_id, 'price': float(price)}
    msg = bot.send_message(call.message.chat.id, "🔗 Введите ссылку (URL) для накрутки:")
    bot.register_next_step_handler(msg, ask_qty)

def ask_qty(message):
    user_steps[message.chat.id]['link'] = message.text
    # Находим лимиты для этой услуги
    all_s = ving_api({'action': 'services'})
    s_id = user_steps[message.chat.id]['s_id']
    info = next(s for s in all_s if str(s['service']) == s_id)
    
    msg = bot.send_message(message.chat.id, f"🔢 Введите количество (Мин: {info['min']}, Макс: {info['max']}):")
    bot.register_next_step_handler(msg, process_order)

def process_order(message):
    chat_id = message.chat.id
    try:
        qty = int(message.text)
        data = user_steps[chat_id]
        total_cost = (data['price'] / 1000) * qty
        user_bal = get_balance(chat_id)

        if user_bal < total_cost:
            bot.send_message(chat_id, f"❌ Недостаточно средств. Нужно: {round(total_cost, 2)} USDT")
            return

        # Пытаемся купить на сайте
        res = ving_api({'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty})
        
        if 'order' in res:
            update_balance(chat_id, -total_cost) # Списываем у юзера
            bot.send_message(chat_id, f"✅ Заказ принят! ID на сайте: {res['order']}\nС вашего баланса списано: {round(total_cost, 2)} USDT")
        else:
            bot.send_message(chat_id, f"❌ Ошибка: {res.get('error', 'Недостаточно средств на основном аккаунте')}")
    except:
        bot.send_message(chat_id, "⚠️ Ошибка. Попробуйте снова.")

if __name__ == '__main__':
    print("Бот успешно запущен!")
    bot.infinity_polling()
