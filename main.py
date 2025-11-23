# AndronWork — ВЦ 5$ бот 2025 | Красиво, надёжно, 24/7 на Railway
import asyncio
import logging
import sqlite3
import re
import html
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# ==================== ТВОИ ДАННЫЕ ====================
TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY"
ADMIN_IDS = [8448843727, 8227071592]                         # ← твои админы
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"           # ← канал выплат

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

active_chats = {}      # кто с кем в чате
taken_by = {}          # заявка → админ (чтобы не дублировалось)

# ==================== БАЗА И ОЧЕРЕДЬ ====================
def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        numbers TEXT,
        ts TEXT DEFAULT (datetime('now'))
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
    cur.execute("SELECT numbers, id FROM queue WHERE user_id = ? AND ts > datetime('now', '-16 minutes') ORDER BY id DESC LIMIT 1", (uid,))
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

# ==================== КЛАВИАТУРЫ ====================
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Сдать номера"), KeyboardButton(text="Мои номера")],
    [KeyboardButton(text="Я тут")]
], resize_keyboard=True)

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Номер взят")],
    [KeyboardButton(text="Закончить чат")]
], resize_keyboard=True)

payout_btn = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Тут будут отчёты и выплаты", url=PAYOUT_CHANNEL)
]])

# ==================== ХЕНДЛЕРЫ ====================
@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    row = get_user_numbers(m.from_user.id)
    pos_text = ""
    if row:
        pos, total = queue_position(row[1])
        pos_text = f"\nТвои номера в очереди: <b>{pos}</b> из <b>{total}</b>"

    await m.answer(f"""AndronWork

Привет, <b>{html.escape(m.from_user.first_name)}</b>!

<b>ВЦ 5$ — 15 минут — без холда</b>

Жми «Я тут» каждые 15 минут!{pos_text}""",
                   reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "Я тут")
async def im_here(m: types.Message):
    row = get_user_numbers(m.from_user.id)
    if row:
        pos, total = queue_position(row[1])
        await m.answer(f"Ты в сети!\nМесто: <b>{pos}</b> из <b>{total}</b>", parse_mode="HTML")
    else:
        await m.answer("Ты в сети! Можешь сдать номера.")

@dp.message(F.text == "Мои номера")
async def my_numbers(m: types.Message):
    row = get_user_numbers(m.from_user.id)
    if not row:
        return await m.answer("Нет номеров в очереди.\nНажми «Сдать номера»")
    numbers = row[0].replace("\n", ", ")
    pos, total = queue_position(row[1])
    await m.answer(f"Твои номера:\n<code>{html.escape(numbers)}</code>\n\nМесто: <b>{pos}</b> из <b>{total}</b>", parse_mode="HTML")

class NumbersState(StatesGroup):
    waiting = State()

@dp.message(F.text == "Сдать номера")
async def ask_numbers(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats:
        return await m.answer("Ты уже в чате с админом!")
    await state.set_state(NumbersState.waiting)
    await m.answer("Кидай номера (по одному на строку):")

@dp.message(NumbersState.waiting)
async def receive_numbers(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats:
        try: await m.copy_to(active_chats[m.from_user.id])
        except: pass
        return

    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    if not nums:
        return await m.answer("Нет валидных номеров!")

    add_to_queue(m.from_user.id, nums)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Взять", callback_data=f"take_{m.from_user.id}")]])
    text = (f"AndronWork | НОВАЯ ЗАЯВКА\n\n"
            f"От: <a href='tg://user?id={m.from_user.id}'>{html.escape(m.from_user.first_name)}</a> | <code>{m.from_user.id}</code>\n\n"
            f"<code>{html.escape('\n'.join(nums))}</code>")

    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    await m.answer("Заявка в очереди!\nЖми «Я тут» каждые 15 мин", reply_markup=user_menu)

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cb: types.CallbackQuery):
    uid = int(cb.data.split("_")[1])
    if uid in taken_by:
        return await cb.answer("Уже взято другим админом!", show_alert=True)
    
    taken_by[uid] = cb.from_user.id
    active_chats[uid] = cb.from_user.id
    active_chats[cb.from_user.id] = uid

    await cb.message.edit_reply_markup(reply_markup=None)
    await bot.send_message(cb.from_user.id, "Чат открыт", reply_markup=admin_menu)
    await bot.send_message(uid, "Админ на связи!", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Закончить чат")]], resize_keyboard=True))
    await cb.answer()

@dp.message(F.text == "Номер взят")
async def number_taken(m: types.Message):
    if m.from_user.id not in active_chats: return
    uid = active_chats.pop(m.from_user.id)
    active_chats.pop(uid, None)
    taken_by.pop(uid, None)

    await bot.send_message(uid, "Номер принят!\n\nТут будут отчёты и выплаты:", reply_markup=payout_btn)
    await m.answer("Выплата отправлена", reply_markup=user_menu)

@dp.message(F.text == "Закончить чат")
async def end_chat(m: types.Message):
    partner = active_chats.pop(m.from_user.id, None)
    if partner:
        active_chats.pop(partner, None)
        taken_by.pop(m.from_user.id, None)
        try: await bot.send_message(partner, "Чат закрыт")
        except: pass
    await m.answer("Чат закрыт", reply_markup=user_menu)

@dp.message()
async def bridge(m: types.Message):
    if m.text and m.text.startswith("/"): return
    if m.from_user.id in active_chats:
        try: await m.copy_to(active_chats[m.from_user.id])
        except: pass

# ==================== ЗАПУСК ====================
async def main():
    asyncio.create_task(cleaner_task())
    await bot.delete_webhook(drop_pending_updates=True)
    print("AndronWork бот запущен 24/7 — всё огонь!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
