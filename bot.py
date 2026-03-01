import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Ваш токен от @BotFather
BOT_TOKEN = "8675832127:AAEKUIKC_YY_-nLGLywg-Vwzt8dQnx2hClQ"

# --- КЛАВИАТУРЫ ---

# Главное меню (кнопки под полем ввода)
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🛍 Магазин")],
        [KeyboardButton(text="💳 Пополнить"), KeyboardButton(text="ℹ️ Информация")],
        [KeyboardButton(text="💬 Поддержка")]
    ],
    resize_keyboard=True
)

# Инлайн-клавиатура для Профиля
profile_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💰 Реферальная программа", callback_data="ref_program")],
        [InlineKeyboardButton(text="📱 Мои аккаунты", callback_data="my_accounts")],
        [InlineKeyboardButton(text="📊 История пополнений", callback_data="dep_history")],
        [InlineKeyboardButton(text="📦 История заказов", callback_data="order_history")]
    ]
)

# Инлайн-клавиатура для Магазина
shop_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Telegram Accounts", callback_data="cat_tg")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ]
)

# Инлайн-клавиатура для Поддержки
support_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Техподдержка", url="https://t.me/meri_support")] # Замените на ваш юзернейм
    ]
)


# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

dp = Dispatcher()

# Обновленный обработчик /start с премиум-эмодзи
@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    # Используем мультистрочный текст для удобства. 
    # Внутри тегов <tg-emoji> оставлены обычные эмодзи-заглушки для старых клиентов Telegram.
    text = (
        '<tg-emoji emoji-id="6082458574934514586">✈️</tg-emoji> <b>Добро пожаловать!</b>\n\n'
        '<tg-emoji emoji-id="5262844652964303985">🛸</tg-emoji> <b>В чем же наш бот лучше других?</b>\n\n'
        '<blockquote><tg-emoji emoji-id="6082491401369559095">✔️</tg-emoji> Автоматическая выдача товаров 24/7\n'
        '<tg-emoji emoji-id="6082491401369559095">✔️</tg-emoji> Автономная работа бота\n'
        '<tg-emoji emoji-id="6082491401369559095">✔️</tg-emoji> Постоянное наличие товаров\n'
        '<tg-emoji emoji-id="6082491401369559095">✔️</tg-emoji> Гарантии на аккаунты</blockquote>\n'
        '<tg-emoji emoji-id="5382360493161725288">➖</tg-emoji><tg-emoji emoji-id="5382360493161725288">➖</tg-emoji><tg-emoji emoji-id="5382360493161725288">➖</tg-emoji><tg-emoji emoji-id="5382360493161725288">➖</tg-emoji><tg-emoji emoji-id="5382360493161725288">➖</tg-emoji><tg-emoji emoji-id="5382360493161725288">➖</tg-emoji><tg-emoji emoji-id="5382360493161725288">➖</tg-emoji>\n\n'
        'Наш канал – @meri_shop\n'
        'Наши отзывы – @reviews_meri\n'
        'Тех.поддержка – @meri_support'
    )
    # Отправляем сообщение и выводим главную клавиатуру
    await message.answer(text, reply_markup=main_kb)

# --- 1. ПРОФИЛЬ ---
@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    text = (
        f"👤 <b>Профиль {message.from_user.first_name}</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"💰 Баланс: 0.0 руб.\n"
        f"📅 Дата регистрации: {current_time}\n"
        f"✅ Активен\n"
        f"👤 Пользователь"
    )
    await message.answer(text, reply_markup=profile_inline_kb)

# --- 2. МАГАЗИН ---
@dp.message(F.text == "🛍 Магазин")
async def show_shop(message: Message):
    await message.answer("🛍 <b>Выберите категорию:</b>", reply_markup=shop_inline_kb)

# --- 3. ИНФОРМАЦИЯ ---
@dp.message(F.text == "ℹ️ Информация")
async def show_info(message: Message):
    text = (
        "🛒 <b>Твой бот для покупки дешёвых аккаунтов</b>\n\n"
        "💼 <b>Информация:</b>\n\n"
        "<blockquote>● <u>Физ. аккаунт</u> – это твой личный аккаунт, который никогда ни кем не использовался до покупки, он не имеет спамблока и других сессий.\n\n"
        "● <u>Аккаунт с отлегой</u> – то же самое, что и \"физический аккаунт\", но он более старый, чем старше аккаунт - тем он дольше проживет.</blockquote>\n\n"
        "<b>1.</b> Что делать, если слетел аккаунт? – пишите поддержке, и указывайте проблему: @meri_support\n\n"
        "<b>2.</b> Что делать, если баланс после оплаты не пришел? – не переживайте, баланс мы пополняем вручную, и он не приходит сразу, для этого нужно время. (в основном от 15 минут до 3-х часов)\n\n"
        "<b>3.</b> Что делать, если аккаунт с автовыдачей не выдался? – пишите нашей тех.поддержке, и указывайте номер телефона купленного аккаунта\n\n"
        "<b>4.</b> Время работы тех.поддержки:\n\n"
        "<blockquote>Пн-Пт: 8:00 – 22:00\n"
        "Сб-Вс: 11:00 – 23:00</blockquote>\n\n"
        "<b>Удачных покупок!</b>"
    )
    await message.answer(text)

# --- 4. ПОДДЕРЖКА ---
@dp.message(F.text == "💬 Поддержка")
async def show_support(message: Message):
    text = (
        "⚡️ Слетел аккаунт? - пиши\n"
        "⚡️ Не пришел баланс? - пиши\n"
        "⚡️ Нашел баг в боте? - пиши\n"
        "⚡️ Есть предложение по улучшению? - пиши\n\n"
        "⏰ График работы:\n"
        "Понедельник: 8:00 – 22:00\n"
        "Вторник: 8:00 – 22:00\n"
        "Среда: 8:00 – 22:00\n"
        "Четверг: 8:00 – 22:00\n"
        "Пятница: 8:00 – 00:00\n"
        "Суббота: 11:00 – 00:00\n"
        "Воскресенье: 11:00 – 22:00"
    )
    await message.answer(text, reply_markup=support_inline_kb)

# --- 5. ПОПОЛНИТЬ ---
@dp.message(F.text == "💳 Пополнить")
async def cmd_deposit(message: Message):
    await message.answer("Для пополнения баланса выберите платежную систему... (Здесь будет функционал оплаты)")


async def main():
    # Настраиваем бота на использование HTML по умолчанию
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    # Удаляем вебхуки и запускаем поллинг
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
