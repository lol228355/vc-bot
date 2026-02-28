import telebot
import requests
from telebot import types

# === ТВОИ ДАННЫЕ ===
API_KEY = 'cdlFcWjrPF7pOwJeXjhELoGYGxsVCZTrvlS396wH8QXg2XlRquw9Z7NCyi5W'
BOT_TOKEN = '8799904851:AAEkGgQ4uIjMH6SAqKBk5aWyL4Ce7uV032w'
API_URL = 'https://vingboost.ru/api/v2'

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {} # Хранилище для процесса оформления заказа

def call_vingboost(payload):
    payload['key'] = API_KEY
    try:
        response = requests.post(API_URL, data=payload)
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# Стартовое меню
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📦 Каталог услуг", "💰 Мой баланс")
    bot.send_message(message.chat.id, "Бот vingboost готов! Выбирайте услугу и накрутка начнется автоматически.", reply_markup=markup)

# Просмотр баланса
@bot.message_handler(func=lambda m: m.text == "💰 Мой баланс")
def check_balance(message):
    res = call_vingboost({'action': 'balance'})
    if 'balance' in res:
        bot.send_message(message.chat.id, f"Ваш текущий баланс на сайте: {res['balance']} {res['currency']}")
    else:
        bot.send_message(message.chat.id, "Не удалось получить баланс. Проверьте API ключ.")

# Получение категорий
@bot.message_handler(func=lambda m: m.text == "📦 Каталог услуг")
def show_categories(message):
    services = call_vingboost({'action': 'services'})
    if not isinstance(services, list):
        bot.send_message(message.chat.id, "Ошибка загрузки услуг.")
        return

    # Собираем уникальные категории
    categories = sorted(list(set([s['category'] for s in services])))
    
    markup = types.InlineKeyboardMarkup()
    for cat in categories:
        # Telegram ограничивает длину данных в кнопке (callback_data) до 64 байт
        short_name = cat[:50] 
        markup.add(types.InlineKeyboardButton(cat, callback_data=f"cat_{short_name}"))
    
    bot.send_message(message.chat.id, "Выберите соцсеть или категорию:", reply_markup=markup)

# Список услуг в выбранной категории
@bot.callback_query_handler(func=lambda call: call.data.startswith('cat_'))
def show_services(call):
    cat_name = call.data[4:]
    all_services = call_vingboost({'action': 'services'})
    
    markup = types.InlineKeyboardMarkup()
    for s in all_services:
        if s['category'].startswith(cat_name):
            # Показываем название и цену за 1000 шт
            btn_text = f"{s['name']} — {s['rate']} руб."
            markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"svc_{s['service']}"))
    
    bot.edit_message_text("Выберите нужную услугу:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# Шаг 1 покупки: Запрос ссылки
@bot.callback_query_handler(func=lambda call: call.data.startswith('svc_'))
def ask_link(call):
    service_id = call.data[4:]
    user_data[call.message.chat.id] = {'service': service_id}
    
    msg = bot.send_message(call.message.chat.id, "Пришлите ссылку на профиль/пост:")
    bot.register_next_step_handler(msg, ask_quantity)

# Шаг 2 покупки: Запрос количества
def ask_quantity(message):
    user_data[message.chat.id]['link'] = message.text
    msg = bot.send_message(message.chat.id, "Сколько штук накрутить? (Введите число):")
    bot.register_next_step_handler(msg, create_order)

# Шаг 3: Отправка заказа в API
def create_order(message):
    chat_id = message.chat.id
    try:
        quantity = int(message.text)
        s_id = user_data[chat_id]['service']
        link = user_data[chat_id]['link']
        
        # Финальный запрос на покупку
        result = call_vingboost({
            'action': 'add',
            'service': s_id,
            'link': link,
            'quantity': quantity
        })
        
        if 'order' in result:
            bot.send_message(chat_id, f"✅ Успешно! Заказ создан. ID: {result['order']}")
        else:
            bot.send_message(chat_id, f"❌ Ошибка: {result.get('error', 'Недостаточно средств или неверная ссылка')}")
            
    except ValueError:
        bot.send_message(chat_id, "⚠️ Ошибка: Введите количество цифрами.")

if __name__ == '__main__':
    print("Бот запущен и готов покупать услуги!")
    bot.infinity_polling()
