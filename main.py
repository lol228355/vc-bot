import asyncio
import logging
import sqlite3
import re
import html
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ==================== КОНФИГУРАЦИЯ ====================
TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY"
ADMIN_IDS = [8227071592, 8340396727]
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"

DB_NAME = "bot_vc.db"
QUEUE_TIMEOUT_MIN = 15      # Полное время жизни
WARNING_TIME_MIN = 5        # Предупреждение за 5 минут

IS_WORK_ACTIVE = True
WARNED_USERS = set()

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
active_chats = {} 

# ==================== БАЗА ДАННЫХ ====================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                numbers TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                is_banned BOOLEAN DEFAULT 0,
                mute_until TIMESTAMP
            )
        """)
        try: conn.execute("ALTER TABLE users ADD COLUMN mute_until TIMESTAMP")
        except: pass

init_db()

def get_conn():
    return sqlite3.connect(DB_NAME)

def get_ban_status(uid):
    with get_conn() as conn:
        res = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,)).fetchone()
        return res[0] if res else 0

def set_ban_status(uid, status):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, ?)", (uid, status))
        conn.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, uid))
        if status == 1:
            conn.execute("DELETE FROM queue WHERE user_id=?", (uid,))

def set_mute(uid, hours=24):
    expiry = datetime.now() + timedelta(hours=hours)
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 0)", (uid,))
        conn.execute("UPDATE users SET mute_until = ? WHERE user_id = ?", (expiry, uid))
        conn.execute("DELETE FROM queue WHERE user_id=?", (uid,))

def check_mute(uid):
    with get_conn() as conn:
        res = conn.execute("SELECT mute_until FROM users WHERE user_id = ?", (uid,)).fetchone()
        if res and res[0]:
            try: mute_time = datetime.fromisoformat(str(res[0]))
            except: 
                try: mute_time = datetime.strptime(str(res[0]), "%Y-%m-%d %H:%M:%S.%f")
                except: return False, ""
            
            if mute_time > datetime.now():
                rem = mute_time - datetime.now()
                h, r = divmod(rem.seconds, 3600)
                m, _ = divmod(r, 60)
                return True, f"{h}ч {m}мин"
    return False, ""

def add_to_queue(uid, numbers):
    with get_conn() as conn:
        conn.execute("REPLACE INTO queue (user_id, numbers, ts) VALUES (?, ?, CURRENT_TIMESTAMP)", (uid, "\n".join(numbers)))

def update_timestamp(uid):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE queue SET ts = CURRENT_TIMESTAMP WHERE user_id = ?", (uid,))
        return cur.rowcount > 0

def get_queue_info(uid):
    with get_conn() as conn:
        return conn.execute("SELECT numbers, id FROM queue WHERE user_id = ?", (uid,)).fetchone()

def get_all_queue():
    with get_conn() as conn:
        return conn.execute("SELECT user_id, numbers FROM queue ORDER BY id ASC").fetchall()

def get_position(row_id):
    with get_conn() as conn:
        pos = conn.execute("SELECT COUNT(*) FROM queue WHERE id <= ?", (row_id,)).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        return pos, total

# ==================== CLEANER TASK ====================
async def cleaner_task():
    while True:
        await asyncio.sleep(60)
        try:
            now = datetime.now()
            with get_conn() as conn:
                rows = conn.execute("SELECT user_id, ts FROM queue").fetchall()
                
            for uid, ts_str in rows:
                try:
                    try: ts = datetime.fromisoformat(ts_str)
                    except: ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except: continue

                diff_minutes = (now - ts).total_seconds() / 60

                if diff_minutes >= QUEUE_TIMEOUT_MIN:
                    with get_conn() as conn:
                        conn.execute("DELETE FROM queue WHERE user_id = ?", (uid,))
                    if uid in WARNED_USERS: WARNED_USERS.remove(uid)
                    try:
                        await bot.send_message(uid, "❌ <b>Тайм-аут.</b> Заявка удалена.", parse_mode="HTML", reply_markup=user_menu)
                    except: pass
                
                elif diff_minutes >= (QUEUE_TIMEOUT_MIN - WARNING_TIME_MIN):
                    if uid not in WARNED_USERS:
                        WARNED_USERS.add(uid)
                        try:
                            await bot.send_message(uid, f"⚠️ <b>Предупреждение!</b>\nЧерез {WARNING_TIME_MIN} мин удалим заявку.\nЖмите <b>«✅ Я онлайн»</b>.", parse_mode="HTML")
                        except: pass
        except Exception as e:
            logging.error(f"Cleaner Error: {e}")

# ==================== КЛАВИАТУРЫ ====================
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="✨ Новая заявка")],
    [KeyboardButton(text="📍 Моя позиция")],
    [KeyboardButton(text="✅ Я онлайн (Обновить таймер)")],
    [KeyboardButton(text="💰 Условия и выплаты")]
], resize_keyboard=True)

admin_panel_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🟢 START WORK"), KeyboardButton(text="🔴 STOP WORK")],
    [KeyboardButton(text="📋 Очередь"), KeyboardButton(text="🔨 Бан"), KeyboardButton(text="🤐 Мут (24ч)")],
    [KeyboardButton(text="⬅️ Выход")]
], resize_keyboard=True)

chat_admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💰 Номер взят"), KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

chat_user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

info_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📂 Перейти к выплатам", url=PAYOUT_CHANNEL)]])

# ==================== HANDLERS ====================
class AdminStates(StatesGroup): waiting_ban = State(); waiting_mute = State()
class UserStates(StatesGroup): waiting_nums = State()

class BannedFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return get_ban_status(m.from_user.id) == 1
class AdminFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return m.from_user.id in ADMIN_IDS

@dp.message(BannedFilter())
async def banned_handler(m: types.Message):
    await m.answer("⛔ <b>Вы заблокированы.</b>", parse_mode="HTML")

# --- АДМИНКА ---
@dp.message(Command("admin"), AdminFilter())
async def admin_start(m: types.Message):
    status = "🟢 ON" if IS_WORK_ACTIVE else "🔴 OFF"
    await m.answer(f"🔧 <b>Админ-панель (ВЦ)</b>\nСтатус: {status}", reply_markup=admin_panel_kb, parse_mode="HTML")

@dp.message(F.text == "⬅️ Выход", AdminFilter())
async def admin_exit(m: types.Message):
    await m.answer("Выход.", reply_markup=user_menu)

@dp.message(F.text == "🟢 START WORK", AdminFilter())
async def start_work(m: types.Message):
    global IS_WORK_ACTIVE; IS_WORK_ACTIVE = True
    await m.answer("✅ Work STARTED", reply_markup=admin_panel_kb)

@dp.message(F.text == "🔴 STOP WORK", AdminFilter())
async def stop_work(m: types.Message):
    global IS_WORK_ACTIVE; IS_WORK_ACTIVE = False
    await m.answer("🛑 Work STOPPED", reply_markup=admin_panel_kb)

@dp.message(F.text == "📋 Очередь", AdminFilter())
async def show_queue(m: types.Message):
    rows = get_all_queue()
    if not rows: return await m.answer("📭 Пусто.")
    await m.answer(f"📋 Заявок: {len(rows)}")
    for uid, nums in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ПРИНЯТЬ", callback_data=f"take_{uid}")]])
        first_num = nums.splitlines()[0]
        await m.answer(f"👤 ID: <code>{uid}</code>\n📞: {html.escape(first_num)}...", reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🔨 Бан", AdminFilter())
async def ban_ask(m: types.Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_ban); await m.answer("ID для бана:")

@dp.message(AdminStates.waiting_ban)
async def ban_exec(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text); new_status = 0 if get_ban_status(uid) else 1
        set_ban_status(uid, new_status)
        await m.answer(f"ID {uid}: {'🔒 Бан' if new_status else '🔓 Разбан'}", reply_markup=admin_panel_kb)
    except: await m.answer("❌ Ошибка")
    await state.clear()

@dp.message(F.text == "🤐 Мут (24ч)", AdminFilter())
async def mute_ask(m: types.Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_mute); await m.answer("ID для мута:")

@dp.message(AdminStates.waiting_mute)
async def mute_exec(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text); set_mute(uid)
        await m.answer(f"ID {uid} мут 24ч.", reply_markup=admin_panel_kb)
    except: await m.answer("❌ Ошибка")
    await state.clear()

# --- ПОЛЬЗОВАТЕЛЬ ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    if m.from_user.id in active_chats: return await m.answer("⚠️ Вы в чате!", reply_markup=chat_user_menu)
    
    st_text = "" if IS_WORK_ACTIVE else "\n🔴 <b>СТОП ВОРК</b>"
    
    msg = f"""<b>💎 AndronWork | ВЦ</b>{st_text}

Привет, {html.escape(m.from_user.first_name)}!
Принимаем ВЦ.

💰 Цена: <b>5$ / акк</b>
⏳ Холд: <b>Нет</b>
⏱ Таймер: {QUEUE_TIMEOUT_MIN} мин"""
    await m.answer(msg, reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "💰 Условия и выплаты")
async def cmd_info(m: types.Message):
    await m.answer("📃 <b>Инфо ВЦ</b>\n\n💵 5$\n🚀 Выплаты после стопа", parse_mode="HTML", reply_markup=info_btn)

@dp.message(F.text == "✅ Я онлайн (Обновить таймер)")
async def cmd_online(m: types.Message):
    if update_timestamp(m.from_user.id):
        if m.from_user.id in WARNED_USERS: WARNED_USERS.remove(m.from_user.id)
        q = get_queue_info(m.from_user.id)
        pos, total = get_position(q[1])
        await m.answer(f"🔄 <b>Обновлено!</b>\n📍 Очередь: {pos} / {total}", parse_mode="HTML")
    else:
        await m.answer("⚠️ Нет заявки.", reply_markup=user_menu)

@dp.message(F.text == "📍 Моя позиция")
async def cmd_pos(m: types.Message):
    q = get_queue_info(m.from_user.id)
    if q:
        pos, total = get_position(q[1])
        await m.answer(f"📍 Место: <b>{pos} / {total}</b>", parse_mode="HTML")
    else:
        await m.answer("📭 Пусто.")

@dp.message(F.text == "✨ Новая заявка")
async def cmd_new(m: types.Message, state: FSMContext):
    is_muted, text = check_mute(m.from_user.id)
    if is_muted: return await m.answer(f"🤐 Мут: {text}")
    if not IS_WORK_ACTIVE: return await m.answer("🔴 Стоп ворк.")
    if m.from_user.id in active_chats: return await m.answer("⚠️ Закройте чат.")

    await state.set_state(UserStates.waiting_nums)
    await m.answer("📝 <b>Кидайте номера:</b>", parse_mode="HTML")

@dp.message(UserStates.waiting_nums)
async def process_nums(m: types.Message, state: FSMContext):
    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+?7|8)?\d{10}$", x.strip())]
    if not nums: return await m.answer("❌ Нет номеров.")
    
    add_to_queue(m.from_user.id, nums)
    if m.from_user.id in WARNED_USERS: WARNED_USERS.remove(m.from_user.id)
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ЗАБРАТЬ", callback_data=f"take_{m.from_user.id}")]])
    notify = f"🔔 <b>ВЦ ЗАЯВКА</b>\n👤 {html.escape(m.from_user.full_name)}\n📄 Кол-во: {len(nums)}"
    for adm in ADMIN_IDS:
        try: await bot.send_message(adm, notify, reply_markup=kb, parse_mode="HTML")
        except: pass

    await m.answer(f"✅ <b>Принято!</b>\n⏱ Жмите «Я онлайн» каждые {QUEUE_TIMEOUT_MIN} мин.", reply_markup=user_menu, parse_mode="HTML")

# ==================== ЧАТ ====================
@dp.callback_query(F.data.startswith("take_"))
async def take_chat(c: types.CallbackQuery):
    uid = int(c.data.split("_")[1])
    if uid in active_chats: return await c.answer("❌ Занято.")
    
    active_chats[uid] = c.from_user.id
    active_chats[c.from_user.id] = uid
    
    with get_conn() as conn: conn.execute("DELETE FROM queue WHERE user_id=?", (uid,))
    if uid in WARNED_USERS: WARNED_USERS.remove(uid)

    await c.message.edit_reply_markup(reply_markup=None)
    await c.message.answer(f"✅ Чат с {uid}", reply_markup=chat_admin_menu)
    try: await bot.send_message(uid, "👨‍💻 <b>Админ тут.</b>", parse_mode="HTML", reply_markup=chat_user_menu)
    except: pass

async def close_chat(admin_id, user_id, user_text, admin_text):
    if admin_id in active_chats: del active_chats[admin_id]
    if user_id in active_chats: del active_chats[user_id]
    
    try: await bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    try: await bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=admin_panel_kb)
    except: pass

@dp.message(F.text == "💰 Номер взят")
async def admin_done(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    user_id = active_chats.get(m.from_user.id)
    if not user_id: return await m.answer("Нет чата.")
    
    await close_chat(m.from_user.id, user_id, 
                     f"✅ <b>Принято!</b>\n💰 Ждите выплату: {PAYOUT_CHANNEL}", 
                     "💸 Готово.")

@dp.message(F.text == "🔒 Закончить чат")
async def stop_chat_any(m: types.Message):
    sender = m.from_user.id
    partner = active_chats.get(sender)
    if not partner: return await m.answer("Нет чата.", reply_markup=user_menu)

    if sender in ADMIN_IDS:
        await close_chat(sender, partner, "🔒 Админ закрыл чат.", "🔒 Чат закрыт.")
    else:
        await close_chat(partner, sender, "🔒 Вы закрыли чат.", "🔒 Юзер закрыл чат.")

@dp.message()
async def chat_bridge(m: types.Message):
    if m.text and m.text.startswith("/"): return
    partner = active_chats.get(m.from_user.id)
    if partner:
        try: await m.copy_to(partner)
        except: await m.answer("❌ Ошибка")
    elif m.from_user.id not in ADMIN_IDS:
        await m.answer("🤖 Меню.", reply_markup=user_menu)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(cleaner_task())
    print("🚀 Bot VC STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Stop")
