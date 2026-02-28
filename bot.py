import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, 
                           CallbackQuery, ReplyKeyboardRemove)

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8530587228:AAFCmNgjzl-6SkL1D-l5ixG6_Bf8kl7oVZA"
ADMIN_IDS = [8663017094, 8119723042]
SHOP_NAME = "𝗠𝗢𝗜 𝗦𝗵𝗢𝗣"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY, 
        username TEXT, 
        reg_date TEXT, 
        balance REAL DEFAULT 0.0,
        purchases INTEGER DEFAULT 0
    )""")
    cur.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)")
    cur.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INTEGER, name TEXT, 
        description TEXT, price_stars INTEGER, price_usd REAL
    )""")
    conn.commit()
    conn.close()

def get_or_create_user(user_id, username):
    conn = sqlite3.connect("shop.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cur.fetchone()
    if not user:
        reg_date = datetime.now().strftime("%d.%m.%Y")
        cur.execute("INSERT INTO users (id, username, reg_date) VALUES (?, ?, ?)", 
                    (user_id, username or "Пользователь", reg_date))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
    conn.close()
    return user

# --- КЛАВИАТУРЫ ---

def get_profile_kb(user_id):
    kb = [
        [InlineKeyboardButton(text="🛒 КАТАЛОГ", callback_data="open_catalog")],
        [InlineKeyboardButton(text="💰 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="🎟 Промокод", callback_data="promo")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info"),
         InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/MOl_t2")]
    ]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ОСНОВНЫЕ ХЭНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_data = get_or_create_user(message.from_user.id, message.from_user.first_name)
    profile_text = (
        f"╔═══════════════════╗\n"
        f"║      👤 ВАШ ПРОФИЛЬ      \n"
        f"╚═══════════════════╝\n\n"
        f"👤 Пользователь: **{user_data[1]}**\n"
        f"🆔 ID: `{user_data[0]}`\n"
        f"📅 Регистрация: {user_data[2]}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс: {user_data[3]:.2f}$\n"
        f"🛍 Покупок: {user_data[4]}\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    await message.answer(profile_text, parse_mode="Markdown", reply_markup=get_profile_kb(message.from_user.id))

@dp.callback_query(F.data == "to_main")
async def back_to_profile(callback: CallbackQuery):
    user_data = get_or_create_user(callback.from_user.id, callback.from_user.first_name)
    profile_text = (
        f"╔═══════════════════╗\n"
        f"║      👤 ВАШ ПРОФИЛЬ      \n"
        f"╚═══════════════════╝\n\n"
        f"👤 Пользователь: **{user_data[1]}**\n"
        f"🆔 ID: `{user_data[0]}`\n"
        f"📅 Регистрация: {user_data[2]}\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Баланс: {user_data[3]:.2f}$\n"
        f"🛍 Покупок: {user_data[4]}\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(profile_text, parse_mode="Markdown", reply_markup=get_profile_kb(callback.from_user.id))

@dp.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery):
    info_text = (
        f"ℹ️ **ИНФОРМАЦИЯ {SHOP_NAME}**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "• **О нас:** Лучший шоп скриптов и аккаунтов.\n"
        "• **Гарантия:** 24 часа на проверку любого товара.\n"
        "• **Пополнение:** Автоматическое через CryptoBot или Stars.\n\n"
        "📍 Мы работаем для вас!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]])
    await callback.message.edit_text(info_text, parse_mode="Markdown", reply_markup=kb)

# --- КАТАЛОГ ---

@dp.callback_query(F.data == "open_catalog")
async def open_catalog(callback: CallbackQuery):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall(); conn.close()
    if not cats:
        await callback.answer("❌ В магазине еще нет категорий!", show_alert=True); return
    
    kb = [[InlineKeyboardButton(text=f"📂 {c[1]}", callback_data=f"usercat_{c[0]}")] for c in cats]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")])
    await callback.message.edit_text(f"📁 **{SHOP_NAME} | КАТЕГОРИИ:**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("usercat_"))
async def list_prods(callback: CallbackQuery):
    cat_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT id, name FROM products WHERE cat_id=?", (cat_id,)); prods = cur.fetchall(); conn.close()
    if not prods:
        await callback.answer("В этой категории пусто", show_alert=True); return
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

# --- АДМИН-ПАНЕЛЬ ---

@dp.callback_query(F.data == "admin_main")
async def admin_main(callback: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="📁 Создать категорию", callback_data="add_cat")],
        [InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_prod")],
        [InlineKeyboardButton(text="🗑 Удалить категорию", callback_data="del_cat_list")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main")]
    ]
    await callback.message.edit_text("🛠 **ПАНЕЛЬ АДМИНИСТРАТОРА**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

class AddCategory(StatesGroup): name = State()
class AddProduct(StatesGroup): cat_id = State(); name = State(); description = State(); price_stars = State(); price_usd = State()

@dp.callback_query(F.data == "add_cat")
async def add_cat_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("⌨️ Введите название для новой категории:")
    await state.set_state(AddCategory.name)

@dp.message(StateFilter(AddCategory.name))
async def add_cat_finish(msg: Message, state: FSMContext):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("INSERT INTO categories (name) VALUES (?)", (msg.text,)); conn.commit(); conn.close()
    await msg.answer(f"✅ Категория **{msg.text}** создана!")
    await state.clear()

@dp.callback_query(F.data == "add_prod")
async def add_prod_start(callback: CallbackQuery, state: FSMContext):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall(); conn.close()
    if not cats:
        await callback.answer("Сначала создайте категорию!", show_alert=True); return
    kb = [[InlineKeyboardButton(text=c[1], callback_data=f"setcat_{c[0]}")] for c in cats]
    await callback.message.edit_text("📌 Выберите категорию:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
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
    await msg.answer("💵 Цена в **USD** (напр. 1.5):")
    await state.set_state(AddProduct.price_usd)

@dp.message(StateFilter(AddProduct.price_usd))
async def add_prod_finish(msg: Message, state: FSMContext):
    d = await state.get_data()
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("INSERT INTO products (cat_id, name, description, price_stars, price_usd) VALUES (?, ?, ?, ?, ?)",
                (d['cat_id'], d['name'], d['description'], d['price_stars'], float(msg.text.replace(",","."))))
    conn.commit(); conn.close()
    await msg.answer("✅ Товар успешно добавлен!")
    await state.clear()

@dp.callback_query(F.data == "del_cat_list")
async def del_cat_list(callback: CallbackQuery):
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM categories"); cats = cur.fetchall(); conn.close()
    kb = [[InlineKeyboardButton(text=f"🗑 {c[1]}", callback_data=f"delcat_{c[0]}")] for c in cats]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_main")])
    await callback.message.edit_text("Выберите категорию для удаления:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

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
    print(f"--- Бот {SHOP_NAME} запущен ---")
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
