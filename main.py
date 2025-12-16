import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import WebAppInfo

# Вставьте сюда токен от @BotFather
TOKEN = "YOUR_BOT_TOKEN"

dp = Dispatcher()

# Команда /start
@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    # Создаем кнопку, которая открывает Web App
    kb = [
        [
            types.KeyboardButton(
                text="🤝 Создать сделку", 
                web_app=WebAppInfo(url="https://your-site-url.com/webapp") # Ссылка на ваш сайт
            )
        ]
    ]
    keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    await message.answer(
        "👋 <b>Добро пожаловать в SafeDeal!</b>\n\n"
        "Я — автоматический гарант-бот. Проводите сделки безопасно через TON или USDT.\n\n"
        "Нажмите кнопку ниже, чтобы начать.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

async def main():
    bot = Bot(TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
