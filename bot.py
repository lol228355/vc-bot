import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# Вставь сюда свой токен от @BotFather
API_TOKEN = '7974095618:AAE-hJZamXJ4m3w5pm2IQT2D6kw7A-ZwyWM'

# Ссылка на твой index.html (обязательно HTTPS!)
# Например: 'https://username.github.io/my-guarantor-bot/'
WEBAPP_URL = 'https://lol228355.github.io/vc-bot/' 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Создаем клавиатуру с кнопкой WebApp
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🚀 Открыть Гарант", 
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ],
        [
            InlineKeyboardButton(text="📜 Правила", callback_data="rules"),
            InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/telegram")
        ]
    ])
    
    # Текст приветствия как на скриншотах (примерно)
    text = (
        f"<b>Привет, {message.from_user.first_name}!</b>\n\n"
        "Вас приветствует автоматизированный гарант-сервис <b>DoDeals!</b>\n"
        "Мы обеспечиваем безопасность сделок в Telegram.\n\n"
        "🔒 <b>Как это работает?</b>\n"
        "1. Создайте сделку в приложении.\n"
        "2. Покупатель вносит средства в холд.\n"
        "3. Продавец передает товар.\n"
        "4. Сделка закрывается автоматически.\n\n"
        "👇 <b>Нажми кнопку ниже, чтобы начать:</b>"
    )
    
    # Отправляем сообщение с красивой картинкой (если есть url) или просто текст
    # await message.answer_photo(photo="URL_КАРТИНКИ", caption=text, parse_mode="HTML", reply_markup=kb)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

# Запуск бота
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
