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

TOKEN = "8389575987:AAFu7A8NSmK3D6AynohVIw5QDPiYqRSNhbY"
ADMIN_IDS = [8227071592, 8394356460]
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

active_chats = {}
config = {"work": True, "price": "ВЦ 5$ — 15 минут — без холда"}

def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, orders INTEGER DEFAULT 0)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS queue (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, numbers TEXT, ts TEXT DEFAULT (datetime('now')))""")
    conn.commit()
    conn.close()

init_db()

def add_to_queue(uid, numbers):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO queue (user_id, numbers) VALUES (?, ?)", (uid, "\n".join(numbers)))
    conn.commit()
    conn.close()

def in_queue(uid):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM queue WHERE user_id = ? AND ts > datetime('now', '-16 minutes')", (uid,))
    res = cur.fetchone()
    conn.close()
    return bool(res)

def queue_pos(uid):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT id FROM queue WHERE user_id = ? ORDER BY id DESC LIMIT 1", (uid,))
    row = cur.fetchone()
    if not row: return None, None
    my_id = row[0]
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

async def cleaner():
    while True:
        await asyncio.sleep(180)
        clean_old()

main_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton("Сдать номер"), KeyboardButton("Где мои номера?")],
    [KeyboardButton("Прайс"), KeyboardButton("Я в сети")]
], resize_keyboard=True)

admin_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton("Номер взят")], [KeyboardButton("Закончить чат")]], resize_keyboard=True)
user_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton("Закончить чат")]], resize_keyboard=True)
payout_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("Забрать 5$", url=PAYOUT_CHANNEL)]])

@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (m.from_user.id,))
    cur.execute("SELECT orders FROM users WHERE user_id = ?", (m.from_user.id,))
    orders = cur.fetchone()[0] or 0
    conn.commit()
    conn.close()
    await m.answer(f"""Привет, <b>{html.escape(m.from_user.first_name)}</b>!

ID: <code>{m.from_user.id}</code>
Сдано номеров: <b>{orders}</b>

<b>Прайс:</b>
{config['price']}

Жми «Я в сети» каждые 15 минут!""", reply_markup=main_kb, parse_mode="HTML")

@dp.message(F.text == "Прайс")
async def price(m: types.Message): await m.answer(config["price"])

@dp.message(F.text == "Я в сети")
async def online(m: types.Message):
    if in_queue(m.from_user.id):
        pos, total = queue_pos(m.from_user.id)
        await m.answer(f"Ты в сети\nМесто: <b>{pos}</b> из <b>{total}</b>", parse_mode="HTML")
    else:
        await m.answer("Ты в сети. Можешь сдать номера.")

@dp.message(F.text == "Где мои номера?")
async def where(m: types.Message):
    if not in_queue(m.from_user.id):
        return await m.answer("Твоих номеров нет в очереди")
    pos, total = queue_pos(m.from_user.id)
    await m.answer(f"Номера в очереди!\nМесто: <b>{pos}</b> из <b>{total}</b>", parse_mode="HTML")

class Form(StatesGroup): numbers = State()

@dp.message(F.text == "Сдать номер")
async def ask(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats: return await m.answer("Ты уже в чате!")
    if not config["work"]: return await m.answer("Приём закрыт")
    await state.set_state(Form.numbers)
    await m.answer("Кидай номера (по одному на строку):")

@dp.message(Form.numbers)
async def get_nums(m: types.Message, state: FSMContext):
    if m.from_user.id in active_chats:
        try: await m.copy_to(active_chats[m.from_user.id])
        except: pass
        return

    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    if not nums: return await m.answer("Нет валидных номеров!")

    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET orders = orders + 1 WHERE user_id = ?", (m.from_user.id,))
    conn.commit()
    conn.close()

    add_to_queue(m.from_user.id, nums)

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("Взять", callback_data=f"take_{m.from_user.id}")]])
    text = f"<b>НОВАЯ ЗАЯВКА</b>\nОт: <a href='tg://user?id={m.from_user.id}'>{html.escape(m.from_user.first_name)}</a>\nID: <code>{m.from_user.id}</code>\n\n<code>{html.escape('\n'.join(nums))}</code>"

    for admin in ADMIN_IDS:
        try: await bot.send_message(admin, text, reply_markup=kb, parse_mode="HTML")
        except: pass

    await m.answer("Заявка в очереди!\nЖми «Я в сети» каждые 15 мин", reply_markup=main_kb)
    await state.clear()

@dp.callback_query(F.data.startswith("take_"))
async def take(cb: types.CallbackQuery):
    uid = int(cb.data.split("_")[1])
    if uid in active_chats: return await cb.answer("Уже взято!", show_alert=True)
    active_chats[uid] = cb.from_user.id
    active_chats[cb.from_user.id] = uid
    await cb.message.edit_reply_markup()
    await bot.send_message(cb.from_user.id, "Чат открыт", reply_markup=admin_kb)
    await bot.send_message(uid, "Админ на связи!", reply_markup=user_kb)
    await cb.answer()

@dp.message(F.text == "Номер взят")
async def taken(m: types.Message):
    if m.from_user.id not in active_chats: return
    uid = active_chats.pop(m.from_user.id)
    active_chats.pop(uid, None)
    await bot.send_message(uid, "Номер принят!\nВыплата 5$ уже в канале:", reply_markup=payout_btn)
    await m.answer("Выплата отправлена", reply_markup=main_kb)

@dp.message(F.text == "Закончить чат")
async def end(m: types.Message):
    if m.from_user.id not in active_chats:
        partner = active_chats.pop(m.from_user.id)
        active_chats.pop(partner, None)
        await m.answer("Чат закрыт", reply_markup=main_kb)
        try: await bot.send_message(partner, "Чат закрыт")
        except: pass

@dp.message()
async def bridge(m: types.Message):
    if m.text and m.text.startswith("/"): return
    if m.from_user.id in active_chats:
        try: await m.copy_to(active_chats[m.from_user.id])
        except: pass

@dp.message(Command("admin"))
async def admin_panel(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    await m.answer("Админка", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("ВКЛ/ВЫКЛ приём", callback_data="toggle")
    ]]))

@dp.callback_query(F.data == "toggle")
async def toggle(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    config["work"] = not config["work"]
    await cb.answer(f"Приём: {'ВКЛ' if config['work'] else 'ВЫКЛ'}")

async def main():
    asyncio.create_task(cleaner())
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен 24/7")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
