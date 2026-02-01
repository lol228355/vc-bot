import os
import requests
import telebot
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Получаем токены из переменных окружения (или используем значения по умолчанию)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8536964721:AAFG0my1nunosT9DVj_kDNmGJeqGGtl34f4")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "523740:AAq1IVJp1MnbToje9z2iJdzBTyv0c8CCXsY")

bot = telebot.TeleBot(BOT_TOKEN)

# URL основного мейннета Crypto Pay. 
# Если используешь тестовый токен, замени на https://testnet-pay.crypt.bot/api/createInvoice
CRYPTO_API_URL = "https://pay.crypt.bot/api/createInvoice"
HEADERS = {
    "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN
}

def create_invoice(amount: float):
    payload = {
        "asset": "USDT",
        "amount": str(amount), # API часто просит передавать числа в виде строки
        "description": "Пополнение баланса",
        "allow_comments": False,
        "allow_anonymous": False
    }

    try:
        response = requests.post(CRYPTO_API_URL, headers=HEADERS, json=payload, timeout=10)
        data = response.json()

        if not data.get("ok"):
            print(f"Ошибка API: {data}")
            raise Exception(data.get("error", {}).get("name", "Unknown error"))

        return data["result"]["pay_url"]
    except requests.exceptions.RequestException as e:
        print(f"Ошибка запроса: {e}")
        raise

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "Введите сумму числом (например: 25.5), и я создам счет для оплаты в USDT."
    )

@bot.message_handler(func=lambda m: True)
def handle_amount(message):
    try:
        # Заменяем запятую на точку и конвертируем в число
        amount_text = message.text.replace(",", ".")
        amount = float(amount_text)
        
        if amount <= 0:
            bot.send_message(message.chat.id, "Сумма должна быть больше нуля.")
            return

        pay_url = create_invoice(amount)

        bot.send_message(
            message.chat.id,
            f"Счет на {amount} USDT создан:\n\n{pay_url}",
            parse_mode="Markdown"
        )

    except ValueError:
        bot.send_message(message.chat.id, "Пожалуйста, введите корректное число.")
    except Exception as e:
        bot.send_message(message.chat.id, "Произошла ошибка при создании счета. Попробуйте позже.")
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
