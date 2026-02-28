import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiocryptopay import AioCryptoPay, Networks

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8530587228:AAFLCfG3W9GVInOtA8nqZG-o3f9StyGc9wI"
CRYPTO_BOT_TOKEN = "ВСТАВЬ_ТОКЕН_ИЗ_CRYPTO_BOT" # Получи в @CryptoBot -> Crypto Pay
ADMIN_IDS = [8663017094, 8119723042]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- РАБОТА С БАЗОЙ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        name TEXT,
        description TEXT,
        price_stars INTEGER,
        price_usd REAL
    )""")
    conn.commit()
    conn.close()

# --- СОСТОЯНИЯ (FSM) ДЛЯ АДМИНКИ ---
class AddProduct(StatesGroup):
    category = State()
    name = State()
    description = State()
    price_stars = State()
    price_usd = State()

CATEGORIES = ["БОТЫ", "МАНУАЛЫ", "ПОДПИСИ", "СИМКИ", "УСЛУГИ", "АККАУНТЫ ВК", "АККАУНТЫ ТГ", "АККАУНТЫ ВБ", "ОЗОН"]

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    kb = []
    for cat in CATEGORIES:
        kb.append([InlineKeyboardButton(text=cat, callback_data=f"cat_{cat}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")]
    ])

# --- ХЭНДЛЕРЫ АДМИНКИ ---
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("🛠 Панель администратора:", reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_add")
async def start_add_product(callback: CallbackQuery, state: FSMContext):
    kb = []
    for cat in CATEGORIES:
        kb.append([InlineKeyboardButton(text=cat, callback_data=f"setcat_{cat}")])
    await callback.message.edit_text("Выберите категорию для нового товара:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AddProduct.category)

@dp.callback_query(StateFilter(AddProduct.category), F.data.startswith("setcat_"))
async def set_category(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.split("_")[1]
    await state.update_data(category=cat)
    await callback.message.answer(f"Категория: {cat}. Теперь введите НАЗВАНИЕ товара:")
    await state.set_state(AddProduct.name)

@dp.message(StateFilter(AddProduct.name))
async def set_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите ОПИСАНИЕ товара:")
    await state.set_state(AddProduct.description)

@dp.message(StateFilter(AddProduct.description))
async def set_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите цену в ЗВЕЗДАХ (целое число):")
    await state.set_state(AddProduct.price_stars)

@dp.message(StateFilter(AddProduct.price_stars))
async def set_stars(message: Message, state: FSMContext):
    await state.update_data(price_stars=int(message.text))
    await message.answer("Введите цену в USD для CryptoBot (например 1.5):")
    await state.set_state(AddProduct.price_usd)

@dp.message(StateFilter(AddProduct.price_usd))
async def save_product(message: Message, state: FSMContext):
    data = await state.get_data()
    price_usd = float(message.text.replace(",", "."))
    
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO products (category, name, description, price_stars, price_usd) VALUES (?, ?, ?, ?, ?)",
                (data['category'], data['name'], data['description'], data['price_stars'], price_usd))
    conn.commit()
    conn.close()
    
    await message.answer("✅ Товар успешно добавлен в каталог!")
    await state.clear()

# --- ХЭНДЛЕРЫ ПОКУПАТЕЛЯ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("🔥 Добро пожаловать в TRC Shop! Выберите категорию:", reply_markup=main_menu_kb())

@dp.callback_query(F.data.startswith("cat_"))
async def show_products(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM products WHERE category=?", (category,))
    products = cur.fetchall()
    conn.close()
    
    if not products:
        await callback.answer("В этой категории пока нет товаров.", show_alert=True)
        return

    kb = []
    for p_id, p_name in products:
        kb.append([InlineKeyboardButton(text=p_name, callback_data=f"view_{p_id}")])
    kb.append([InlineKeyboardButton(text="◀️ Назад", callback_data="to_main")])
    
    await callback.message.edit_text(f"🛒 Товары в категории {category}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "to_main")
async def to_main(callback: CallbackQuery):
    await callback.message.edit_text("Выберите категорию:", reply_markup=main_menu_kb())

@dp.callback_query(F.data.startswith("view_"))
async def view_product(callback: CallbackQuery):
    p_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (p_id,))
    p = cur.fetchone()
    conn.close()
    
    text = f"📦 **{p[2]}**\n\n{p[3]}\n\nЦена: ⭐️ {p[4]} | 💵 ${p[5]}"
    kb = [
        [InlineKeyboardButton(text="⭐️ Купить за Звезды", callback_data=f"buy_stars_{p[0]}")],
        [InlineKeyboardButton(text="🪙 Купить CryptoBot", callback_data=f"buy_crypto_{p[0]}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_{p[1]}")]
    ]
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- ПЛАТЕЖИ (Звезды) ---
@dp.callback_query(F.data.startswith("buy_stars_"))
async def buy_stars(callback: CallbackQuery):
    p_id = callback.data.split("_")[2]
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("SELECT name, description, price_stars FROM products WHERE id=?", (p_id,))
    p = cur.fetchone()
    conn.close()

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=p[0],
        description=p[1],
        payload=f"stars_{p_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=p[0], amount=p[2])]
    )

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(message: Message):
    await message.answer("✅ Оплата прошла успешно! Администраторы свяжутся с вами или выдадут товар.")
    for admin in ADMIN_IDS:
        await bot.send_message(admin, f"💰 НОВАЯ ПОКУПКА!\nПользователь: @{message.from_user.username}\nСумма: {message.successful_payment.total_amount} звезд")

# --- ЗАПУСК ---
async def main():
    init_db()
    print("Бот TRCproject запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
