import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Библиотека для работы с CryptoBot
from aiocryptopay import AioCryptoPay, Networks

# --- НАСТРОЙКИ ---
BOT_TOKEN = "8675832127:AAEKUIKC_YY_-nLGLywg-Vwzt8dQnx2hClQ" # <-- Вставьте токен вашего основного бота сюда
CRYPTO_TOKEN = "540404:AA2Rex1G8gtM1zNSPWa3pADmtHbWx4B2bI8"
ADMIN_IDS = [8119723042, 8663017094]
SUPPORT_USERNAME = "MOl_t2"

# Инициализация CryptoBot (используем MAIN_NET для реальных платежей)
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)

# --- КЛАВИАТУРЫ ---

main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🛍 Магазин")],
        [KeyboardButton(text="💳 Пополнить"), KeyboardButton(text="ℹ️ Информация")],
        [KeyboardButton(text="💬 Поддержка")]
    ],
    resize_keyboard=True
)

profile_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💰 Реферальная программа", callback_data="ref_program")],
        [InlineKeyboardButton(text="📱 Мои аккаунты", callback_data="my_accounts")],
        [InlineKeyboardButton(text="📊 История пополнений", callback_data="dep_history")],
        [InlineKeyboardButton(text="📦 История заказов", callback_data="order_history")]
    ]
)

shop_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Telegram Accounts", callback_data="cat_tg")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")]
    ]
)

support_inline_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        # Ссылка теперь ведет на указанного вами человека
        [InlineKeyboardButton(text="👨‍💻 Техподдержка", url=f"https://t.me/{SUPPORT_USERNAME}")]
    ]
)

# --- ОБРАБОТЧИКИ ---

dp = Dispatcher()

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    await message.answer("Добро пожаловать! Выберите действие в меню ниже 👇", reply_markup=main_kb)

@dp.message(F.text == "👤 Профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    
    # Простая проверка на админа (для отображения статуса)
    status = "👑 Администратор" if user_id in ADMIN_IDS else "👤 Пользователь"
    
    text = (
        f"👤 <b>Профиль {message.from_user.first_name}</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
        f"💰 Баланс: 0.0 руб.\n"
        f"📅 Дата регистрации: {current_time}\n"
        f"✅ Активен\n"
        f"{status}"
    )
    await message.answer(text, reply_markup=profile_inline_kb)

@dp.message(F.text == "🛍 Магазин")
async def show_shop(message: Message):
    await message.answer("🛍 <b>Выберите категорию:</b>", reply_markup=shop_inline_kb)

@dp.message(F.text == "ℹ️ Информация")
async def show_info(message: Message):
    text = (
        "🛒 <b>Твой бот для покупки дешёвых аккаунтов</b>\n\n"
        "💼 <b>Информация:</b>\n\n"
        "<blockquote>● <u>Физ. аккаунт</u> – это твой личный аккаунт, который никогда ни кем не использовался до покупки, он не имеет спамблока и других сессий.\n\n"
        "● <u>Аккаунт с отлегой</u> – то же самое, что и \"физический аккаунт\", но он более старый, чем старше аккаунт - тем он дольше проживет.</blockquote>\n\n"
        f"<b>1.</b> Что делать, если слетел аккаунт? – пишите поддержке, и указывайте проблему: @{SUPPORT_USERNAME}\n\n"
        "<b>2.</b> Что делать, если баланс после оплаты не пришел? – не переживайте, баланс мы пополняем вручную, и он не приходит сразу, для этого нужно время. (в основном от 15 минут до 3-х часов)\n\n"
        "<b>3.</b> Что делать, если аккаунт с автовыдачей не выдался? – пишите нашей тех.поддержке, и указывайте номер телефона купленного аккаунта\n\n"
        "<b>4.</b> Время работы тех.поддержки:\n\n"
        "<blockquote>Пн-Пт: 8:00 – 22:00\n"
        "Сб-Вс: 11:00 – 23:00</blockquote>\n\n"
        "<b>Удачных покупок!</b>"
    )
    await message.answer(text)

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

@dp.message(F.text == "💳 Пополнить")
async def cmd_deposit(message: Message):
    # Пример создания счета в CryptoBot на 1 USDT
    try:
        invoice = await crypto.create_invoice(asset='USDT', amount=1.0)
        
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить 1 USDT", url=invoice.bot_invoice_url)]
        ])
        
        await message.answer(
            "💳 <b>Пополнение баланса</b>\n\n"
            "Нажмите на кнопку ниже, чтобы оплатить через CryptoBot:",
            reply_markup=pay_kb
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при создании счета: {e}")

async def main():
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот успешно запущен!")
    
    try:
        await dp.start_polling(bot)
    finally:
        # Корректно закрываем сессию CryptoBot при остановке скрипта
        await bot.session.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
