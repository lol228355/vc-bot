# AndronWork — САМОЕ КРАСИВОЕ ОФОРМЛЕНИЕ 2025
import asyncio, logging, sqlite3, re, html
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY"
ADMIN_IDS = [8448843727, 8227071592]
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

active_chats = {}
taken_by = {}

# ==================== БАЗА ====================
def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        numbers TEXT,
        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

init_db()

def add_to_queue(uid, numbers):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO queue (user_id, numbers) VALUES (?, ?)", (uid, "\n".join(numbers)))
    conn.commit()
    conn.close()

def get_user_numbers(uid):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""SELECT numbers, id FROM queue 
                   WHERE user_id = ? AND ts > datetime('now', '-16 minutes') 
                   ORDER BY id DESC LIMIT 1""", (uid,))
    row = cur.fetchone()
    conn.close()
    return row

def queue_position(my_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM queue WHERE id <= ? AND ts > datetime('now', '-16 minutes')", (my_id,))
    pos = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM queue WHERE ts > datetime('now', '-16 minutes')")
    total = cur.fetchone()[0]
    conn.close()
    return pos, total

def clean_old():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM queue WHERE ts < datetime('now', '-16 minutes')")
    conn.commit()
    conn.close()

async def cleaner_task():
    while True:
        await asyncio.sleep(180)
        clean_old()

# ==================== КРАСИВЫЕ КЛАВИАТУРЫ ====================
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📱 Сдать номера"), KeyboardButton(text="📊 Мои номера")],
    [KeyboardButton(text="✅ Я тут")]
], resize_keyboard=True)

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💰 Номер взят")],
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

payout_btn = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="💸 Тут будут отчёты и выплаты", url=PAYOUT_CHANNEL)
]])

# ==================== СТАРТ ====================
@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    row = get_user_numbers(m.from_user.id)
    queue_info = ""
    if row:
        pos, total = queue_position(row[1])
        queue_info = f"\n\n🎯 Твои номера в очереди: <b>#{pos}</b> из <b>{total}</b>"

    await m.answer(f"""<b>🚀 AndronWork</b>

👋 Привет, <b>{html.escape(m.from_user.first_name)}</b>!

💎 <b>ВЦ по 5$ — 15 минут — без холда</b>

⚡️ <b>Самые быстрые и честные выплаты</b>
🛡 <b>Никаких скамов и задержек</b>

⏰ Жми «✅ Я тут» каждые 15 минут — и ты в деле!{queue_info}""",
                   reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "✅ Я тут")
async def im_here(m: types.Message):
    row = get_user_numbers(m.from_user.id)
    if row:
        pos, total = queue_position(row[1])
        await m.answer(f"🟢 Ты в сети!\n🎯 Место в очереди: <b>#{pos}/{total}</b>", parse_mode="HTML")
    else:
        await m.answer("🟢 Ты в сети — можно сдавать номера! 📱")

@dp.message(F.text == "📊 Мои номера")
async def my_numbers(m: types.Message):
    row = get_user_numbers(m.from_user.id)
    if not row:
        return await m.answer("❌ <b>Номеров в очереди нет</b>\n\nНажми «📱 Сдать номера»", parse_mode="HTML")
    
    numbers = row[0].replace("\n", "\n")
    pos, total = queue_position(row[1])
    await m.answer(f"""<b>📊 Твои номера в очереди</b>

📞 {numbers}

🎯 <b>Позиция в очереди: #{pos} из {total}</b>""", parse_mode="HTML")

class NumbersState(StatesGroup):
    waiting = State()

@dp.message(F.text == "📱 Сдать номера")
async def ask_numbers(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ Ты уже в чате с админом")
    await state.set_state(NumbersState.waiting)
    await m.answer("📱 Кидай номера по одному на строку:\n\n<code>+79991234567\n89991234567\n79991234567</code>", parse_mode="HTML")

@dp.message(NumbersState.waiting)
async def receive_numbers(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats:
        try: 
            await m.copy_to(active_chats[m.from_user.id])
            return
        except: 
            pass

    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    if not nums:
        return await m.answer("❌ Не нашёл валидных номеров\n\n📱 Формат: +79991234567 или 89991234567")

    add_to_queue(m.from_user.id, nums)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎯 Взять", callback_data=f"take_{m.from_user.id}")]])
    text = f"""<b>🚀 AndronWork | НОВАЯ ЗАЯВКА</b>

👤 От: <a href='tg://user?id={m.from_user.id}'>{html.escape(m.from_user.first_name)}</a>
🆔 ID: <code>{m.from_user.id}</code>

📞 Номера:
<code>{html.escape('\n'.join(nums))}</code>"""

    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    await m.answer("✅ <b>Заявка успешно добавлена в очередь!</b>\n\n⏰ Жми «✅ Я тут» каждые 15 минут", reply_markup=user_menu, parse_mode="HTML")

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cb: types.CallbackQuery):
    uid = int(cb.data.split("_")[1])
    if uid in taken_by:
        return await cb.answer("❌ Уже взято другим админом!", show_alert=True)
    
    taken_by[uid] = cb.from_user.id
    active_chats[uid] = cb.from_user.id
    active_chats[cb.from_user.id] = uid

    await cb.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(cb.from_user.id, "💬 Чат с пользователем открыт", reply_markup=admin_menu)
    await bot.send_message(uid, "👨‍💼 Админ на связи! Ожидай выплаты 💸", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔒 Закончить чат")]], resize_keyboard=True))
    await cb.answer("✅ Вы взяли заявку!")

@dp.message(F.text == "💰 Номер взят")
async def number_taken(m: types.Message):
    if m.from_user.id not in active_chats:
        return await m.answer("❌ Нет активного чата")
    
    partner_id = active_chats.get(m.from_user.id)
    if not partner_id:
        return await m.answer("❌ Ошибка: партнер не найден")
    
    # Удаляем из активных чатов
    if m.from_user.id in active_chats:
        active_chats.pop(m.from_user.id)
    if partner_id in active_chats:
        active_chats.pop(partner_id)
    if partner_id in taken_by:
        taken_by.pop(partner_id)
    
    # Отправляем сообщение пользователю
    try:
        await bot.send_message(partner_id, "✅ <b>Номер принят!</b>\n\n💸 Тут будут отчёты и выплаты:", reply_markup=payout_btn, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Ошибка отправки пользователю: {e}")
    
    await m.answer("💸 Выплата отправлена пользователю", reply_markup=admin_menu)

@dp.message(F.text == "🔒 Закончить чат")
async def end_chat(m: types.Message):
    partner_id = None
    
    # Находим партнера по чату
    if m.from_user.id in active_chats:
        partner_id = active_chats[m.from_user.id]
        active_chats.pop(m.from_user.id)
    
    if partner_id and partner_id in active_chats:
        active_chats.pop(partner_id)
    
    # Удаляем из taken_by
    if m.from_user.id in taken_by:
        taken_by.pop(m.from_user.id)
    if partner_id and partner_id in taken_by:
        taken_by.pop(partner_id)
    
    # Отправляем сообщение партнеру
    if partner_id:
        try:
            await bot.send_message(partner_id, "🔒 Чат закрыт админом", reply_markup=user_menu)
        except Exception as e:
            logging.error(f"Ошибка отправки партнеру: {e}")
    
    # Отправляем сообщение отправителю
    if m.from_user.id in ADMIN_IDS:
        await m.answer("🔒 Чат закрыт", reply_markup=admin_menu)
    else:
        await m.answer("🔒 Чат закрыт", reply_markup=user_menu)

@dp.message()
async def bridge(m: types.Message):
    if m.text and m.text.startswith("/"): 
        return
    
    # Проверяем, находится ли пользователь в активном чате
    if m.from_user.id in active_chats:
        partner_id = active_chats[m.from_user.id]
        try: 
            await m.copy_to(partner_id)
        except Exception as e:
            logging.error(f"Ошибка пересылки сообщения: {e}")
            await m.answer("❌ Не удалось отправить сообщение")

async def main():
    asyncio.create_task(cleaner_task())
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 AndronWork — САМОЕ КРАСИВОЕ ОФОРМЛЕНИЕ 2025 — запущено! 💎")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
