import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiocryptopay import CryptoPay

# --- КОНФИГ ---
BOT_TOKEN = "8675832127:AAHin9yM2xzbjclF3UqDz2k_zsoLKsiiZXY"
CRYPTO_TOKEN = "540404:AA2Rex1G8gtM1zNSPWa3pADmtHbWx4B2bI8"
ADMIN_IDS = [8663017094, 8119723042]

# Инициализация
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
crypto = CryptoPay(token=CRYPTO_TOKEN, network='mainnet')
dp = Dispatcher()

# Состояния для админки
class AdminStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_description = State()
    waiting_for_price = State()

# --- КЛАВИАТУРЫ ---

def main_kb(user_id):
    buttons = [
        [KeyboardButton(text="🛍 Магазин"), KeyboardButton(text="👤 Профиль")],
        [KeyboardButton(text="💳 Пополнить")]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton(text="👨‍💼 Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

admin_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_item")],
    [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_admin")]
])

# --- ОБРАБОТЧИКИ ---

@dp.message(F.text == "/start")
async def cmd_start(message: Message):
    # Твои премиум-эмодзи (HTML коды)
    text = (
        f'<tg-emoji emoji-id="6082458574934514586">🐸</tg-emoji> <b>Добро пожаловать!</b>\n\n'
        f'<tg-emoji emoji-id="6082458574934514586">🐸</tg-emoji> <b>В чем же наш бот лучше других?</b>\n\n'
        f'<blockquote>'
        f'<tg-emoji emoji-id="5262844652964303985">💡</tg-emoji> Автоматическая выдача товаров 24/7\n'
        f'<tg-emoji emoji-id="6082491401369559095">🐸</tg-emoji> Автономная работа бота\n'
        f'<tg-emoji emoji-id="6082491401369559095">🐸</tg-emoji> Постоянное наличие товаров\n'
        f'<tg-emoji emoji-id="6082491401369559095">🐸</tg-emoji> Гарантии на аккаунты'
        f'</blockquote>\n'
        f'<tg-emoji emoji-id="5382360493161725288">➖</tg-emoji>' * 10 + '\n\n'
        f'Наш канал – @meri_shop\n'
        f'Тех.поддержка – @MOl_t2'
    )
    await message.answer(text, reply_markup=main_kb(message.from_user.id))

# --- ЛОГИКА АДМИН-ПАНЕЛИ ---

@dp.message(F.text == "👨‍💼 Админ-панель")
async def open_admin(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("🛠 <b>Меню администратора:</b>", reply_markup=admin_kb)

@dp.callback_query(F.data == "add_item")
async def start_add(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("📝 Введите <b>название</b> аккаунта (например: TG RU +44):")
    await state.set_state(AdminStates.waiting_for_name)

@dp.message(AdminStates.waiting_for_name)
async def add_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📜 Теперь введите <b>описание</b> товара:")
    await state.set_state(AdminStates.waiting_for_description)

@dp.message(AdminStates.waiting_for_description)
async def add_desc(message: Message, state: FSMContext):
    await state.update_data(desc=message.text)
    await message.answer("💰 Введите <b>цену</b> (число в USD):")
    await state.set_state(AdminStates.waiting_for_price)

@dp.message(AdminStates.waiting_for_price)
async def add_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Пожалуйста, введите число!")
    
    data = await state.get_data()
    price = message.text
    
    # Итог добавления
    summary = (
        f"✅ <b>Товар успешно создан!</b>\n\n"
        f"📦 Название: {data['name']}\n"
        f"📝 Описание: {data['desc']}\n"
        f"💵 Цена: {price} USD"
    )
    await message.answer(summary, reply_markup=main_kb(message.from_user.id))
    await state.clear()

# --- ОПЛАТА CRYPTO BOT ---

@dp.message(F.text == "💳 Пополнить")
async def refill_balance(message: Message):
    # Пример создания инвойса на 5 USDT (можно сделать ввод суммы пользователем)
    invoice = await crypto.create_invoice(asset='USDT', amount=5.0)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить через CryptoBot", url=invoice.bot_invoice_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data=f"check_{invoice.invoice_id}")]
    ])
    
    await message.answer(
        f"<b>Пополнение баланса</b>\n\n"
        f"Сумма: 5.00 USDT\n"
        f"ID счета: <code>{invoice.invoice_id}</code>",
        reply_markup=kb
    )

@dp.callback_query(F.data == "close_admin")
async def close_admin(callback: CallbackQuery):
    await callback.message.delete()

# --- ЗАПУСК ---
async def main():
    print("Бот запущен и готов к работе!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
