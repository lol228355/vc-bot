import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiocryptopay import AioCryptoPay, Networks

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8530587228:AAHZyvz5zs1MwipU7lMJiLDc20zGNVZCkAw"
CRYPTO_BOT_TOKEN = "ВСТАВЬ_ТОКЕН_ИЗ_CRYPTO_BOT" 
ADMIN_IDS = [8663017094, 8119723042]
SHOP_NAME = "𝗠𝗢𝗜 𝗦𝗵𝗢𝗣"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- БАЗА ДАННЫХ ---
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

class AddProduct(StatesGroup):
    category = State(); name = State(); description = State(); price_stars = State(); price_usd = State()

CATEGORIES = {
    "🤖 БОТЫ": "БОТЫ",
    "📚 МАНУАЛЫ": "МАНУАЛЫ",
    "✍️ ПОДПИСИ": "ПОДПИСИ",
    "📲 СИМКИ": "СИМКИ",
    "🛠 УСЛУГИ": "УСЛУГИ",
    "🔵 ВК АККАУНТЫ": "АККАУНТЫ ВК",
    "✈️ ТГ АККАУНТЫ": "АККАУНТЫ ТГ",
    "🟣 ВБ АККАУНТЫ": "АККАУНТЫ ВБ",
    "🔵 ОЗОН": "ОЗОН"
}

# --- КЛАВИАТУРЫ ---
def get_main_menu(user_id):
    buttons = [
        [KeyboardButton(text="🛒 Каталог товаров")],
        [KeyboardButton(text="ℹ️ Информация"), KeyboardButton(text="🆘 Поддержка")]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton(text="⚙️ Админ-панель")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def catalog_inline():
    kb = []
    for display_name, callback_data in CATEGORIES.items():
        kb.append([InlineKeyboardButton(text=display_name, callback_data=f"cat_{callback_data}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ОБРАБОТКА КОМАНД ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        f"Добро пожаловать в **{SHOP_NAME}**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Лучший сервис цифровых товаров к вашим услугам.\n\n"
        "👇 Используйте меню для выбора:"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=get_main_menu(message.from_user.id))

@dp.message(F.text == "🛒 Каталог товаров")
async def show_catalog_root(message: Message):
    await message.answer(f"📁 **{SHOP_NAME} | КАТЕГОРИИ:**", reply_markup=catalog_inline(), parse_mode="Markdown")

# --- АДМИН-ПАНЕЛЬ ---
@dp.message(F.text == "⚙️ Админ-панель")
async def admin_menu(message: Message):
    if message.from_user.id in ADMIN_IDS:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete_list")]
        ])
        await message.answer(f"🛠 **УПРАВЛЕНИЕ {SHOP_NAME}**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "admin_delete_list")
async def admin_delete_list(callback: CallbackQuery):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT id, name, category FROM products"); prods = cur.fetchall(); conn.close()
    if not prods:
        await callback.answer("Список товаров пуст", show_alert=True); return
    
    kb = []
    for p in prods:
        kb.append([InlineKeyboardButton(text=f"❌ {p[2]} | {p[1]}", callback_data=f"del_{p[0]}")])
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_admin")])
    await callback.message.edit_text("🗑 **Выберите товар для удаления:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("del_"))
async def delete_product(callback: CallbackQuery):
    p_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (p_id,)); conn.commit(); conn.close()
    await callback.answer("✅ Товар удален", show_alert=True)
    await admin_delete_list(callback)

@dp.callback_query(F.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
        [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete_list")]
    ])
    await callback.message.edit_text(f"🛠 **УПРАВЛЕНИЕ {SHOP_NAME}**", reply_markup=kb, parse_mode="Markdown")

# --- ЛОГИКА ДОБАВЛЕНИЯ (FSM) ---
@dp.callback_query(F.data == "admin_add")
async def start_add(callback: CallbackQuery, state: FSMContext):
    kb = [[InlineKeyboardButton(text=c, callback_data=f"setcat_{c}")] for c in CATEGORIES.values()]
    await callback.message.edit_text("📌 **Выберите категорию:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")
    await state.set_state(AddProduct.category)

@dp.callback_query(StateFilter(AddProduct.category), F.data.startswith("setcat_"))
async def set_category(callback: CallbackQuery, state: FSMContext):
    cat = callback.data.split("_")[1]
    await state.update_data(category=cat)
    await callback.message.answer(f"✅ Категория: {cat}\n\n📝 Введите **Название** товара:")
    await state.set_state(AddProduct.name)

@dp.message(StateFilter(AddProduct.name))
async def set_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("📝 Введите **Описание**:")
    await state.set_state(AddProduct.description)

@dp.message(StateFilter(AddProduct.description))
async def set_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("💰 Цена в **Звездах**:")
    await state.set_state(AddProduct.price_stars)

@dp.message(StateFilter(AddProduct.price_stars))
async def set_stars(message: Message, state: FSMContext):
    try:
        await state.update_data(price_stars=int(message.text))
        await message.answer("💵 Цена в **USD** (через точку, напр. 2.5):")
        await state.set_state(AddProduct.price_usd)
    except: await message.answer("Введите целое число!")

@dp.message(StateFilter(AddProduct.price_usd))
async def finish_add(message: Message, state: FSMContext):
    try:
        data = await state.get_data()
        usd = float(message.text.replace(",", "."))
        conn = sqlite3.connect("shop.db"); cur = conn.cursor()
        cur.execute("INSERT INTO products (category, name, description, price_stars, price_usd) VALUES (?, ?, ?, ?, ?)",
                    (data['category'], data['name'], data['description'], data['price_stars'], usd))
        conn.commit(); conn.close()
        await message.answer(f"🌟 **Товар добавлен в {SHOP_NAME}!**", parse_mode="Markdown")
        await state.clear()
    except: await message.answer("Введите число!")

# --- ПОКАЗ ТОВАРОВ ---
@dp.callback_query(F.data.startswith("cat_"))
async def list_products(callback: CallbackQuery):
    cat = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT id, name FROM products WHERE category=?", (cat,))
    prods = cur.fetchall(); conn.close()
    
    if not prods:
        await callback.answer("⚠️ В этой категории пусто", show_alert=True); return

    kb = [[InlineKeyboardButton(text=f"🔹 {p[1]}", callback_data=f"view_{p[0]}")] for p in prods]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")])
    await callback.message.edit_text(f"📦 **{SHOP_NAME} | {cat}**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_"))
async def view_item(callback: CallbackQuery):
    p_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (p_id,)); p = cur.fetchone(); conn.close()
    
    text = (
        f"💎 **{p[2]}**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"{p[3]}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"💵 Стоимость: **${p[5]}** или **⭐️ {p[4]}**"
    )
    kb = [
        [InlineKeyboardButton(text="💳 Оплатить Звездами", callback_data=f"stars_pay_{p[0]}")],
        [InlineKeyboardButton(text="🪙 CryptoBot (USDT)", callback_data=f"crypto_pay_{p[0]}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat_{p[1]}")]
    ]
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data == "to_main")
async def go_back(callback: CallbackQuery):
    await callback.message.edit_text(f"📁 **{SHOP_NAME} | КАТЕГОРИИ:**", reply_markup=catalog_inline(), parse_mode="Markdown")

# --- ЗАПУСК ---
async def main():
    init_db()
    print(f"{SHOP_NAME} работает!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
