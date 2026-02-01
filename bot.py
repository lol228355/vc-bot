import os
import requests
import telebot
from dotenv import load_dotenv

# 1. Загружаем переменные из .env
load_dotenv()

# Получаем токены (если в .env их нет, возьмутся те, что в кавычках)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8536964721:AAFG0my1nunosT9DVj_kDNmGJeqGGtl34f4")
CRYPTO_PAY_TOKEN = os.getenv("CRYPTO_PAY_TOKEN", "523740:AAq1IVJp1MnbToje9z2iJdzBTyv0c8CCXsY")

bot = telebot.TeleBot(BOT_TOKEN)

# URL API (для теста используйте https://testnet-pay.crypt.bot/api/createInvoice)
CRYPTO_API_URL = "https://pay.crypt.bot/api/createInvoice"
HEADERS = {
    "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN
}

def create_invoice(amount: float):
    payload = {
        "asset": "USDT",
        "amount": str(amount),  # Сумма должна быть строкой
        "description": "Пополнение баланса",
        "allow_comments": False,
        "allow_anonymous": False
    }

    response = requests.post(CRYPTO_API_URL, headers=HEADERS, json=payload, timeout=10)
    data = response.json()

    if not data.get("ok"):
        print(f"Ошибка CryptoBot API: {data}")
        raise Exception(data.get("error", {}).get("name", "Unknown error"))

    return data["result"]["pay_url"]

# --- Обработчики команд ---

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Введите сумму в USDT (например: 10 или 5.5), чтобы я создал счет для оплаты."
    )

@bot.message_handler(func=lambda m: True)
def handle_amount(message):
    try:
        # Убираем пробелы и меняем запятую на точку
        clean_text = message.text.replace(",", ".").strip()
        amount = float(clean_text)

        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Сумма должна быть больше нуля.")
            return

        # Создаем счет через API
        pay_url = create_invoice(amount)

        # Отправляем ссылку пользователю
        bot.send_message(
            message.chat.id,
            f"✅ Счёт на **{amount} USDT** успешно создан!\n\nОплатите по ссылке ниже:\n{pay_url}",
            parse_mode="Markdown"
        )

    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Пожалуйста, введите число (например: 10.5).")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Произошла ошибка при создании счета.")
        print(f"Ошибка в handle_amount: {e}")

# --- Запуск бота ---

if __name__ == "__main__":
    # Исправляем ошибку 409 Conflict: удаляем вебхук перед запуском polling
    print("Удаление вебхуков...")
    bot.remove_webhook()
    
    print("Бот запущен и готов к работе!")
    bot.infinity_polling()
