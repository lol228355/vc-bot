import requests
import telebot
from telebot import types

# --- ⚙️ НАСТРОЙКИ (ЗАПОЛНИ ЭТО) ---
BOT_TOKEN = "8094711584:AAEb3DDLCgeLAnTPJWks78GNkLdSjntL3-o"
CRYPTO_PAY_TOKEN = "514479:AAb64Swo8pexGV3iVkgI4MqdlYYsg22BhOZ"

# Список ID администраторов, которым разрешено пользоваться ботом
# Свой ID можно узнать у бота @userinfobot
ADMIN_IDS = [8379364188, 8119723042] 

# --- 🛠 НАСТРОЙКА API ---
CRYPTO_API_URL = "https://pay.crypt.bot/api/"
HEADERS = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}

bot = telebot.TeleBot(BOT_TOKEN)

# Функция проверки прав доступа
def is_admin(user_id):
    return user_id in ADMIN_IDS

# --- 💰 ФУНКЦИИ CRYPTO BOT ---

def create_invoice(amount: float):
    """Создать ссылку на оплату (входящий платеж)"""
    url = f"{CRYPTO_API_URL}createInvoice"
    payload = {"asset": "USDT", "amount": str(amount), "description": "Admin Deposit"}
    res = requests.post(url, headers=HEADERS, json=payload).json()
    if res.get("ok"): return res["result"]["pay_url"]
    raise Exception(res.get("error", {}).get("name"))

def create_check(amount: float):
    """Создать чек (выходящий платеж/выплата)"""
    url = f"{CRYPTO_API_URL}createCheck"
    payload = {"asset": "USDT", "amount": str(amount)}
    res = requests.post(url, headers=HEADERS, json=payload).json()
    if res.get("ok"): return res["result"]["bot_check_url"]
    raise Exception(res.get("error", {}).get("name"))

# --- 🤖 ЛОГИКА БОТА ---

@bot.message_handler(commands=["start"])
def start(message):
    if not is_admin(message.from_user.id):
        return # Бот просто игнорирует не-админов

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💎 Создать счет (Ввод)", "🎁 Создать чек (Вывод)")
    bot.send_message(
        message.chat.id, 
        "🛠 **Панель управления Crypto Pay**\nВыберите действие:", 
        reply_markup=markup, 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "💎 Создать счет (Ввод)")
def ask_invoice(message):
    msg = bot.send_message(message.chat.id, "Введите сумму для создания счета (USDT):")
    bot.register_next_step_handler(msg, proc_invoice)

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text == "🎁 Создать чек (Вывод)")
def ask_check(message):
    msg = bot.send_message(message.chat.id, "Введите сумму для создания чека (USDT):")
    bot.register_next_step_handler(msg, proc_check)

def proc_invoice(message):
    try:
        amount = float(message.text.replace(",", "."))
        url = create_invoice(amount)
        bot.send_message(message.chat.id, f"✅ **Счет готов:**\n{url}", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

def proc_check(message):
    try:
        amount = float(message.text.replace(",", "."))
        url = create_check(amount)
        bot.send_message(message.chat.id, f"✅ **Чек создан:**\n{url}", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}\n(Проверьте баланс приложения)")

# --- ЗАПУСК ---
if __name__ == "__main__":
    bot.remove_webhook()
    print("Админ-бот запущен!")
    bot.infinity_polling()
