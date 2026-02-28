import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# --- КОНФИГУРАЦИЯ ---
API_TOKEN = '8787002063:AAEDatXPIS2F_cmmOehGf4WcXB9wvgDReTM'
ADMIN_ID = 8663017094  # Замените на ваш числовой ID (можно узнать у @userinfobot)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Временная база данных (в реальном проекте лучше использовать SQLite/PostgreSQL)
users_db = {} 

# --- КЛАВИАТУРЫ ---
def get_main_kb(user_id):
    builder = ReplyKeyboardBuilder()
    builder.button(text="💳 Сдать ВК")
    
    # Кнопка админа видна только админу
    if user_id == ADMIN_ID:
        builder.button(text="⚙️ Админ-панель")
    
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def get_admin_kb():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Посмотреть баланс")
    builder.button(text="🔄 Обнулить")
    builder.button(text="🚫 Забанить")
    builder.button(text="⬅️ Назад")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Это бот для сдачи аккаунтов ВК.",
        reply_markup=get_main_kb(message.from_user.id)
    )

# Логика кнопки "Сдать ВК"
@dp.message(F.text == "💳 Сдать ВК")
async def process_sell_vk(message: types.Message):
    await message.answer("Привет! Напиши свой номер в формате +79999999...")

# Логика админ-панели
@dp.message(F.text == "⚙️ Админ-панель")
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Вы вошли в режим администратора:", reply_markup=get_admin_kb())
    else:
        await message.answer("У вас нет прав доступа.")

@dp.message(F.text == "💰 Посмотреть баланс")
async def check_balance(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Баланс системы: 100.000 руб. (пример)")

@dp.message(F.text == "🔄 Обнулить")
async def reset_data(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Данные успешно обнулены!")

@dp.message(F.text == "🚫 Забанить")
async def ban_user(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Введите ID пользователя для блокировки:")

@dp.message(F.text == "⬅️ Назад")
async def go_back(message: types.Message):
    await message.answer("Вы вернулись в главное меню", reply_markup=get_main_kb(message.from_user.id))

# --- ЗАПУСК ---
async def main():
    await dp.start_polling(bot)

if name == "main":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
