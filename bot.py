import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ReplyKeyboardRemove
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
    "🤖 БОТЫ": "БОТЫ", "📚 МАНУАЛЫ": "МАНУАЛЫ", "✍️ ПОДПИСИ": "ПОДПИСИ",
    "📲 СИМКИ": "СИМКИ", "🛠 УСЛУГИ": "УСЛУГИ", "🔵 ВК АККАУНТЫ": "АККАУНТЫ ВК",
    "✈️ ТГ АККАУНТЫ": "АККАУНТЫ ТГ", "🟣 ВБ АККАУНТЫ": "АККАУНТЫ ВБ", "🔵 ОЗОН": "ОЗОН"
}

# --- КЛАВИАТУРЫ ---
def get_main_inline_kb(user_id):
    kb = [
        [InlineKeyboardButton(text="🛒 Каталог товаров", callback_data="open_catalog")],
        [InlineKeyboardButton(text="ℹ️ Информация", callback_data="info"), 
         InlineKeyboardButton(text="🆘 Поддержка", url="https://t.me/MOl_t2")]
    ]
    if user_id in ADMIN_IDS:
        kb.append([InlineKeyboardButton(text="⚙️ Админ-панель", callback_data="back_to_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def catalog_inline():
    kb = [[InlineKeyboardButton(text=name, callback_data=f"cat_{val}")] for name, val in CATEGORIES.items()]
    kb.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="to_main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ХЭНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Удаляем обычную клавиатуру, если она была
    welcome_text = (
        f"👋 **Привет!**\n\n"
        f"Добро пожаловать в **{SHOP_NAME}**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Мы предоставляем лучшие цифровые решения, аккаунты и услуги на рынке.\n\n"
        "🚀 Выберите нужный раздел ниже:"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    await message.answer("📍 Главное меню:", reply_markup=get_main_inline_kb(message.from_user.id))

@dp.callback_query(F.data == "to_main_menu")
async def to_main_menu_callback(callback: CallbackQuery):
    welcome_text = (
        f"👋 **Добро пожаловать в {SHOP_NAME}**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Выберите нужный раздел:"
    )
    await callback.message.edit_text(welcome_text, parse_mode="Markdown", reply_markup=get_main_inline_kb(callback.from_user.id))

@dp.callback_query(F.data == "info")
async def show_info(callback: CallbackQuery):
    info_text = (
        f"ℹ️ **ИНФОРМАЦИЯ О {SHOP_NAME}**\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "• **Гарантия:** Мы несем полную ответственность за проданные товары.\n"
        "• **Скорость:** Выдача товара происходит мгновенно или в кратчайшие сроки.\n"
        "• **Поддержка:** Если возникли вопросы, наш саппорт всегда на связи.\n\n"
        "✅ Выбирая нас, вы выбираете качество!"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="to_main_menu")]])
    await callback.message.edit_text(info_text, parse_mode="Markdown", reply_markup=kb)

@dp.callback_query(F.data == "open_catalog")
async def open_catalog(callback: CallbackQuery):
    await callback.message.edit_text(f"📁 **{SHOP_NAME} | КАТЕГОРИИ:**", reply_markup=catalog_inline(), parse_mode="Markdown")

# --- АДМИН-ЛОГИКА (УПРАВЛЕНИЕ) ---
@dp.callback_query(F.data == "back_to_admin")
async def admin_menu(callback: CallbackQuery):
    if callback.from_user.id in ADMIN_IDS:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add")],
            [InlineKeyboardButton(text="🗑 Удалить товар", callback_data="admin_delete_list")],
            [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="to_main_menu")]
        ])
        await callback.message.edit_text(f"🛠 **УПРАВЛЕНИЕ {SHOP_NAME}**", reply_markup=kb, parse_mode="Markdown")

# --- (Тут остается остальная логика категорий, просмотра и удаления из предыдущего кода) ---
# [Для краткости я не дублирую функции удаления и FSM, они остаются такими же, как в прошлом ответе]

@dp.callback_query(F.data.startswith("cat_"))
async def list_products(callback: CallbackQuery):
    cat = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT id, name FROM products WHERE category=?", (cat,))
    prods = cur.fetchall(); conn.close()
    
    if not prods:
        await callback.answer("⚠️ В этой категории пусто", show_alert=True); return

    kb = [[InlineKeyboardButton(text=f"🔹 {p[1]}", callback_data=f"view_{p[0]}")] for p in prods]
    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="open_catalog")])
    await callback.message.edit_text(f"📦 **{SHOP_NAME} | {cat}**", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_"))
async def view_item(callback: CallbackQuery):
    p_id = callback.data.split("_")[1]
    conn = sqlite3.connect("shop.db"); cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (p_id,)); p = cur.fetchone(); conn.close()
    
    text = (f"💎 **{p[2]}**\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n{p[3]}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
            f"💵 Стоимость: **${p[5]}** или **⭐️ {p[4]}**")
    kb = [
        [InlineKeyboardButton(text="💳 Оплатить Звездами", callback_data=f"stars_pay_{p[0]}")],
        [InlineKeyboardButton(text="🪙 CryptoBot (USDT)", callback_data=f"crypto_pay_{p[0]}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"cat_{p[1]}")]
    ]
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
