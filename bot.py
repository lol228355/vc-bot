import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, ReplyKeyboardRemove)

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8530587228:AAHZyvz5zs1MwipU7lMJiLDc20zGNVZCkAw"
ADMIN_IDS = [8663017094, 8119723042]
SHOP_NAME = "𝗠𝗢𝗜 𝗦𝗵𝗢𝗣"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    # Таблица категорий
    cur.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    # Таблица товаров
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cat_id INTEGER,
        name TEXT,
        description TEXT,
        price_stars INTEGER,
        price_usd REAL
    )""")
    conn.commit()
    conn.close()

# --- СОСТОЯНИЯ (FSM) ---
class AddCategory(StatesGroup):
    name = State()

class AddProduct(StatesGroup):
    cat_id = State()
    name = State()
    description = State()
    price_stars = State()
    price_usd = State()

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    kb = [[InlineKeyboardButton(text="🛒 КАТАЛОГ", callback_data="open_catalog")],
          [InlineKeyboardButton(text="ℹ️ Инфо", callback_data="info"), 
           InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/MOl_t2")]]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ГЛАВНОЕ МЕНЮ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(f"👋 Добро пожаловать в **{SHOP_NAME}**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\nВыберите раздел:", 
                         parse_mode="Markdown", reply_markup=get_main_kb(message.from_user.id))

@dp.callback_query(F.data == "to_main")
async def to_main(callback: CallbackQuery):
    await callback.message.edit_text(f"👋 Добро пожаловать в **{SHOP_NAME}**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\nВыберите раздел:", 
                                     parse_mode="Markdown", reply_markup=get_main_kb(callback.from_user.id))

# --- ЛОГИКА КАТАЛОГА (ДЛЯ ПОЛЬЗОВАТЕЛЕЙ) ---
@dp.callback_query(F.data == "open_catalog")
async def open_catalog(callback: CallbackQuery):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall(); conn.close()
    if not cats:
        await callback.answer("❌ Магазин пока пуст!", show_alert=True); return
    
    kb = [[InlineKeyboardButton(text=f"📂 {c[1]}", callback_data=f"usercat_{c[0]}")] for c in cats]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")])
    await callback.message.edit_text(f"📁 **{SHOP_NAME} | КАТЕГОРИИ:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("usercat_"))
async def list_prods(callback: CallbackQuery):
    cat_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT id, name FROM products WHERE cat_id=?", (cat_id,)); prods = cur.fetchall(); conn.close()
    if not prods:
        await callback.answer("В этой категории нет товаров", show_alert=True); return
    
    kb = [[InlineKeyboardButton(text=f"🔹 {p[1]}", callback_data=f"view_{p[0]}")] for p in prods]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="open_catalog")])
    await callback.message.edit_text("📦 Выберите товар:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("view_"))
async def view_item(callback: CallbackQuery):
    p_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (p_id,)); p = cur.fetchone(); conn.close()
    text = (f"💎 **{p[2]}**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n{p[3]}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💵 Цена: **${p[5]}** или **⭐️ {p[4]}**")
    kb = [[InlineKeyboardButton(text="💳 Купить", callback_data=f"buy_{p[0]}")],
          [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"usercat_{p[1]}")]]
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- АДМИН-ПАНЕЛЬ (УПРАВЛЕНИЕ) ---
@dp.callback_query(F.data == "admin_main")
async def admin_main(callback: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="📁 Создать категорию", callback_data="add_cat")],
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_prod")],
        [InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="del_cat_list")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="to_main")]
    ]
    await callback.message.edit_text("🛠 **ПАНЕЛЬ АДМИНИСТРАТОРА**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# Добавление категории
@dp.callback_query(F.data == "add_cat")
async def add_cat_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите название для **новой категории** (например: АККАУНТЫ ТГ):")
    await state.set_state(AddCategory.name)

@dp.message(StateFilter(AddCategory.name))
async def add_cat_finish(msg: Message, state: FSMContext):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("INSERT INTO categories (name) VALUES (?)", (msg.text,)); conn.commit(); conn.close()
    await msg.answer(f"✅ Категория **{msg.text}** создана!")
    await state.clear()

# Добавление товара
@dp.callback_query(F.data == "add_prod")
async def add_prod_start(callback: CallbackQuery, state: FSMContext):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall(); conn.close()
    if not cats:
        await callback.answer("Сначала создайте категорию!", show_alert=True); return
    
    kb = [[InlineKeyboardButton(text=c[1], callback_data=f"setcat_{c[0]}")] for c in cats]
    await callback.message.edit_text("📌 Выберите категорию для товара:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await state.set_state(AddProduct.cat_id)

@dp.callback_query(StateFilter(AddProduct.cat_id), F.data.startswith("setcat_"))
async def add_prod_cat(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=callback.data.split("_")[1])
    await callback.message.answer("📝 Введите **Название** товара:")
    await state.set_state(AddProduct.name)

@dp.message(StateFilter(AddProduct.name))
async def add_prod_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text)
    await msg.answer("📝 Введите **Описание**:")
    await state.set_state(AddProduct.description)

@dp.message(StateFilter(AddProduct.description))
async def add_prod_desc(msg: Message, state: FSMContext):
    await state.update_data(description=msg.text)
    await msg.answer("💰 Цена в **Звездах**:")
    await state.set_state(AddProduct.price_stars)

@dp.message(StateFilter(AddProduct.price_stars))
async def add_prod_stars(msg: Message, state: FSMContext):
    await state.update_data(price_stars=int(msg.text))
    await msg.answer("💵 Цена в **USD** (через точку):")
    await state.set_state(AddProduct.price_usd)

@dp.message(StateFilter(AddProduct.price_usd))
async def add_prod_finish(msg: Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("INSERT INTO products (cat_id, name, description, price_stars, price_usd) VALUES (?, ?, ?, ?, ?)",
                (d['cat_id'], d['name'], d['description'], d['price_stars'], float(msg.text.replace(",","."))))
    conn.commit(); conn.close()
    await msg.answer("✅ Товар добавлен!")
    await state.clear()

# Удаление категории (вместе с товарами)
@dp.callback_query(F.data == "del_cat_list")
async def del_cat_list(callback: CallbackQuery):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall(); conn.close()
    kb = [[InlineKeyboardButton(text=f"🗑 {c[1]}", callback_data=f"delcat_{c[0]}")] for c in cats]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")])
    await callback.message.edit_text("Выберите категорию для **полного удаления**:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data.startswith("delcat_"))
async def del_cat_exec(callback: CallbackQuery):
    cid = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("DELETE FROM categories WHERE id=?", (cid,))
    cur.execute("DELETE FROM products WHERE cat_id=?", (cid,))
    conn.commit(); conn.close()
    await callback.answer("Удалено"); await del_cat_list(callback)

# --- ЗАПУСК ---
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
