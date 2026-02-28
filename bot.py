import telebot
import requests
from telebot import types

# === ТВОИ ДАННЫЕ ===
API_KEY = 'cdlFcWjrPF7pOwJeXjhELoGYGxsVCZTrvlS396wH8QXg2XlRquw9Z7NCyi5W'
BOT_TOKEN = '8799904851:AAEkGgQ4uIjMH6SAqKBk5aWyL4Ce7uV032w'
API_URL = 'https://vingboost.ru/api/v2'

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {} # Временная память для оформления заказа

def call_vingboost(payload):
    payload['key'] = API_KEY
    try:
        response = requests.post(API_URL, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# Главное меню
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📦 Каталог услуг", "💰 Мой баланс")
    bot.send_message(message.chat.id, "Бот vingboost готов к работе!", reply_markup=markup)

# Проверка баланса аккаунта
@bot.message_handler(func=lambda m: m.text == "💰 Мой баланс")
def check_balance(message):
    res = call_vingboost({'action': 'balance'})
    if 'balance' in res:
        bot.send_message(message.chat.id, f"Ваш баланс на сайте: {res['balance']} {res['currency']}")
    else:
        bot.send_message(message.chat.id, "Ошибка: проверьте API ключ.")

# Показ категорий (исправлено: используем ID первой услуги в категории для callback)
@bot.message_handler(func=lambda m: m.text == "📦 Каталог услуг")
def show_categories(message):
    services = call_vingboost({'action': 'services'})
    if not isinstance(services, list):
        bot.send_message(message.chat.id, "❌ Не удалось загрузить услуги с сайта.")
        return

    # Группируем категории и берем ID одной услуги из каждой для передачи в кнопку
    categories_map = {}
    for s in services:
        cat_name = s['category']
        if cat_name not in categories_map:
            categories_map[cat_name] = s['service']

    markup = types.InlineKeyboardMarkup()
    for cat_name, s_id in categories_map.items():
        # Передаем "getcat_ID", чтобы вписаться в лимит 64 байта Telegram
        markup.add(types.InlineKeyboardButton(cat_name, callback_data=f"getcat_{s_id}"))
    
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=markup)

# Показ услуг внутри категории
@bot.callback_query_handler(func=lambda call: call.data.startswith('getcat_'))
def show_services_by_id(call):
    service_id_ref = call.data[7:] # Получаем ID услуги-ориентира
    all_services = call_vingboost({'action': 'services'})
    
    # Ищем название категории по этому ID
    target_category = ""
    for s in all_services:
        if str(s['service']) == service_id_ref:
            target_category = s['category']
            break
            
    markup = types.InlineKeyboardMarkup()
    for s in all_services:
        if s['category'] == target_category:
            # Текст кнопки: Название и цена за 1000 шт.
            btn_text = f"{s['name']} — {s['rate']} руб."
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"svc_{s['service']}"))
    
    bot.edit_message_text(f"Услуги в категории:\n{target_category}", call.message.chat.id, call.message.message_id, reply_markup=markup)

# Запрос ссылки после выбора услуги
@bot.callback_query_handler(func=lambda call: call.data.startswith('svc_'))
def ask_link(call):
    service_id = call.data[4:]
    user_data[call.message.chat.id] = {'service': service_id}
    
    # Ищем мин/макс для подсказки пользователю
    all_services = call_vingboost({'action': 'services'})
    min_val, max_val = 0, 0
    for s in all_services:
        if str(s['service']) == service_id:
            min_val, max_val = s['min'], s['max']
            break

    user_data[call.message.chat.id]['min'] = min_val
    user_data[call.message.chat.id]['max'] = max_val

    msg = bot.send_message(call.message.chat.id, "Пришлите ссылку (URL) для накрутки:")
    bot.register_next_step_handler(msg, ask_quantity)

# Запрос количества
def ask_quantity(message):
    chat_id = message.chat.id
    user_data[chat_id]['link'] = message.text
    
    min_v = user_data[chat_id]['min']
    max_v = user_data[chat_id]['max']
    
    msg = bot.send_message(chat_id, f"Введите количество.\n(Минимум: {min_v}, Максимум: {max_v}):")
    bot.register_next_step_handler(msg, create_order)

# Финальное создание заказа
def create_order(message):
    chat_id = message.chat.id
    try:
        quantity = int(message.text)
        s_id = user_data[chat_id]['service']
        link = user_data[chat_id]['link']
        
        # Отправляем запрос на покупку
        result = call_vingboost({
            'action': 'add',
            'service': s_id,
            'link': link,
            'quantity': quantity
        })
        
        if 'order' in result:
            bot.send_message(chat_id, f"✅ Заказ №{result['order']} успешно создан!")
        else:
            error_msg = result.get('error', 'Недостаточно средств или неверные данные')
            bot.send_message(chat_id, f"❌ Ошибка: {error_msg}")
            
    except ValueError:
        bot.send_message(chat_id, "⚠️ Нужно ввести число. Попробуйте заказать заново.")

if __name__ == '__main__':
    print("Бот запущен!")
    bot.infinity_polling()
