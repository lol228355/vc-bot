import asyncio, logging, sqlite3, re, html
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== НАСТРОЙКИ ====================
# Вставь сюда свой токен
TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY"
# ID админов (через запятую)
ADMIN_IDS = [8448843727, 8227071592]
# Ссылка на канал выплат
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"

# Настройка логов
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Словарь активных чатов: {user_id: admin_id, admin_id: user_id}
active_chats = {}

# ==================== БАЗА ДАННЫХ ====================
DB_NAME = "bot.db"

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            numbers TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.commit()

init_db()

def add_to_queue(uid, numbers):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("REPLACE INTO queue (user_id, numbers) VALUES (?, ?)", (uid, "\n".join(numbers)))
        conn.commit()

def get_user_queue(uid):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        # Ищем заявку за последние 16 минут
        cur.execute("SELECT numbers, id FROM queue WHERE user_id = ? AND ts > datetime('now', '-16 minutes')", (uid,))
        return cur.fetchone()

def queue_pos(row_id):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM queue WHERE id <= ? AND ts > datetime('now', '-16 minutes')", (row_id,))
        pos = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM queue WHERE ts > datetime('now', '-16 minutes')")
        total = cur.fetchone()[0]
        return pos, total

def clean_old_queue():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM queue WHERE ts < datetime('now', '-16 minutes')")
        conn.commit()

async def cleaner_task():
    while True:
        await asyncio.sleep(180)
        clean_old_queue()

# ==================== КЛАВИАТУРЫ ====================

# Главное меню пользователя
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📱 Сдать номера"), KeyboardButton(text="📊 Мои номера")],
    [KeyboardButton(text="✅ Я тут"), KeyboardButton(text="❓ Инфо")]
], resize_keyboard=True)

# Меню админа во время работы
admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💰 Номер взят")],
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

# Меню пользователя во время чата с админом
chat_user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

# Инлайн кнопка в инфо
info_btn = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="💸 Канал с выплатами", url=PAYOUT_CHANNEL)
]])

# ==================== ХЭНДЛЕРЫ ====================

class Form(StatesGroup):
    waiting_numbers = State()

@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    
    # Если юзер нажал старт во время чата - возвращаем его в контекст чата
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ У вас активный чат с админом!", reply_markup=chat_user_menu)

    row = get_user_queue(m.from_user.id)
    info = ""
    if row:
        p, t = queue_pos(row[1])
        info = f"\n\n📋 <b>Твоя очередь: #{p} из {t}</b>"

    await m.answer(f"""<b>💎 AndronWork — ВЦ 2025</b>

👋 Привет, {html.escape(m.from_user.first_name)}!

💵 <b>ВЦ по 5$ | 15 мин | Без холда</b>
🚀 Быстрые выплаты после стоп-ворка

👇 Жми кнопки ниже:{info}""", reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "❓ Инфо")
async def cmd_info(m: types.Message):
    await m.answer(f"""ℹ️ <b>Информация</b>

1️⃣ Жми <b>«📱 Сдать номера»</b>
2️⃣ Жди, пока админ возьмёт заявку
3️⃣ Получи выплату после <b>СТОП-ВОРКА</b>

🔗 <a href="{PAYOUT_CHANNEL}">Ссылка на канал выплат</a>""", 
    parse_mode="HTML", reply_markup=info_btn)

@dp.message(F.text == "✅ Я тут")
async def cmd_here(m: types.Message):
    if m.from_user.id in active_chats:
        return await m.answer("✅ Ты на связи с админом!", reply_markup=chat_user_menu)
        
    row = get_user_queue(m.from_user.id)
    if row:
        p, t = queue_pos(row[1])
        await m.answer(f"🟢 <b>Ты в очереди!</b>\nМесто: <b>#{p} из {t}</b>", parse_mode="HTML")
    else:
        await m.answer("🟢 Ты в сети! Сдавай номера.", reply_markup=user_menu)

@dp.message(F.text == "📊 Мои номера")
async def cmd_my_nums(m: types.Message):
    row = get_user_queue(m.from_user.id)
    if not row:
        return await m.answer("📭 <b>Очередь пуста</b>\nЖми «📱 Сдать номера»", parse_mode="HTML")
    
    p, t = queue_pos(row[1])
    await m.answer(f"📄 <b>Твои номера:</b>\n<code>{row[0]}</code>\n\n📍 Очередь: <b>#{p} из {t}</b>", parse_mode="HTML")

# --- СДАЧА НОМЕРОВ ---
@dp.message(F.text == "📱 Сдать номера")
async def cmd_submit(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ Сначала заверши текущий чат!", reply_markup=chat_user_menu)
    
    await state.set_state(Form.waiting_numbers)
    await m.answer("✍️ <b>Введи номера (по 1 в строку):</b>\n\n+79991234567\n89991234567", parse_mode="HTML")

@dp.message(Form.waiting_numbers)
async def process_numbers(m: types.Message, state: FSMContext):
    # Фильтруем номера
    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    
    if not nums:
        return await m.answer("❌ <b>Нет валидных номеров!</b>\nПопробуй ещё раз.", parse_mode="HTML")

    add_to_queue(m.from_user.id, nums)
    await state.clear()

    # Уведомление админам
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ВЗЯТЬ ЗАЯВКУ", callback_data=f"take_{m.from_user.id}")]])
    text = f"🚨 <b>НОВАЯ ЗАЯВКА</b>\n👤: {html.escape(m.from_user.full_name)}\n🆔: <code>{m.from_user.id}</code>\n\n📞:\n<code>{html.escape('\n'.join(nums))}</code>"

    for adm in ADMIN_IDS:
        try: await bot.send_message(adm, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    await m.answer("✅ <b>Заявка в очереди!</b>\nЖди ответа админа.", reply_markup=user_menu, parse_mode="HTML")

# --- ЛОГИКА ЧАТА ---

@dp.callback_query(F.data.startswith("take_"))
async def admin_take(cb: types.CallbackQuery):
    user_id = int(cb.data.split("_")[1])
    admin_id = cb.from_user.id

    if user_id in active_chats:
        return await cb.answer("❌ Уже занят другим админом!", show_alert=True)

    # Создаем связь
    active_chats[user_id] = admin_id
    active_chats[admin_id] = user_id

    # Обновляем сообщение админа (убираем кнопку)
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"✅ Вы взяли заявку юзера <code>{user_id}</code>", reply_markup=admin_menu, parse_mode="HTML")
    
    # Пишем юзеру
    try:
        await bot.send_message(user_id, "👨‍💻 <b>Админ на связи!</b>\nЧат открыт, ожидай проверки.", reply_markup=chat_user_menu, parse_mode="HTML")
    except:
        await cb.message.answer("❌ Не удалось написать юзеру (мб бот заблокирован).")
        del active_chats[admin_id]
        if user_id in active_chats: del active_chats[user_id]

    await cb.answer()

# === ФУНКЦИЯ ЗАКРЫТИЯ ЧАТА ===
async def close_session(admin_id, user_id, finish_text_user, finish_text_admin):
    # Удаляем связи
    if admin_id in active_chats: del active_chats[admin_id]
    if user_id in active_chats: del active_chats[user_id]

    # Отправляем сообщения и ВОЗВРАЩАЕМ КЛАВИАТУРЫ
    try:
        await bot.send_message(user_id, finish_text_user, parse_mode="HTML", reply_markup=user_menu)
    except: pass

    try:
        await bot.send_message(admin_id, finish_text_admin, parse_mode="HTML", reply_markup=admin_menu) # Админу всегда возвращаем его меню
    except: pass

@dp.message(F.text == "💰 Номер взят")
async def admin_done(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return

    admin_id = m.from_user.id
    user_id = active_chats.get(admin_id)

    if not user_id:
        # Если чата нет, просто возвращаем меню админу, чтобы кнопки не висели
        return await m.answer("⚠️ Нет активного чата.", reply_markup=admin_menu)

    # Удаляем из очереди
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))

    # Текст для пользователя про СТОП-ВОРК
    user_msg = (
        f"✅ <b>НОМЕР ПРИНЯТ!</b>\n\n"
        f"🛑 <b>Выплата будет после СТОП-ВОРКА тут:</b>\n"
        f"👉 <a href='{PAYOUT_CHANNEL}'><b>ССЫЛКА НА ЧАТ ВЫПЛАТ</b></a> 👈\n\n"
        f"<i>Можешь сдавать следующие номера!</i>"
    )
    
    await close_session(admin_id, user_id, user_msg, "💸 <b>Принято!</b> Юзер уведомлен о стоп-ворке.")

@dp.message(F.text == "🔒 Закончить чат")
async def stop_chat(m: types.Message):
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)

    if not partner_id:
        # Восстанавливаем клавиатуру, если чат заглючил
        kb = admin_menu if sender_id in ADMIN_IDS else user_menu
        return await m.answer("🔒 Чат уже завершен.", reply_markup=kb)

    # Определяем, кто админ, кто юзер
    if sender_id in ADMIN_IDS:
        admin_id, user_id = sender_id, partner_id
        closer = "Администратором"
    else:
        admin_id, user_id = partner_id, sender_id
        closer = "Пользователем"

    await close_session(
        admin_id, 
        user_id, 
        f"🔒 Чат завершен {closer}.", 
        f"🔒 Чат завершен {closer}."
    )

# --- ПЕРЕСЫЛКА СООБЩЕНИЙ (BRIDGE) ---
@dp.message()
async def bridge_msg(m: types.Message):
    # Игнорируем команды и кнопки меню, если они не обработались выше
    if m.text and (m.text.startswith("/") or m.text in ["📱 Сдать номера", "✅ Я тут", "📊 Мои номера", "💰 Номер взят", "🔒 Закончить чат"]):
        return

    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)

    if partner_id:
        try:
            # Просто копируем сообщение собеседнику
            await m.copy_to(partner_id)
        except:
            await m.answer("❌ Сообщение не доставлено (собеседник заблокировал бота).")
            # Автоматически закрываем сломанный чат
            if sender_id in ADMIN_IDS:
                await close_session(sender_id, partner_id, "", "❌ Чат закрыт из-за ошибки.")
    else:
        # Если чата нет, но пишут текст - показываем меню
        kb = admin_menu if sender_id in ADMIN_IDS else user_menu
        await m.answer("Не понимаю команду. Используй меню 👇", reply_markup=kb)

async def main():
    asyncio.create_task(cleaner_task())
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
