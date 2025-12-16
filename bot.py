import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# Токен от @BotFather
API_TOKEN = 'ВАШ_ТОКЕН'
# Ссылка на файл index.html (должна быть HTTPS, например GitHub Pages)
WEBAPP_URL = 'https://lol228355.github.io/vc-bot/'

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Кнопка для запуска Mini App
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Запустить гарант", web_app=WebAppInfo(url=WEBAPP_URL))],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="faq")],
        [InlineKeyboardButton(text="📢 Опубликовать объявление", url="https://t.me/")]
    ])
    
    await message.answer(
        f"Добро пожаловать, {message.from_user.first_name}!\n"
        "Запускайте приложение, чтобы создать безопасную сделку за USDT или TON 💎\n"
        "Стоимость услуги гаранта всего 2% 🔥",
        reply_markup=kb
    )

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
