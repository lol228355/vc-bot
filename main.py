import asyncio, logging, sqlite3, re, html
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== НАСТРОЙКИ (ВЦ) ====================
TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY"
ADMIN_IDS = [8227071592, 8340396727] # <--- Обновлено
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"
QUEUE_TIMEOUT_MIN = 15  
DB_NAME = "bot_vc.db"   

IS_WORK_ACTIVE = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
active_chats = {}

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            numbers TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_banned BOOLEAN DEFAULT 0,
            mute_until TIMESTAMP
        )""")
        try: cur.execute("ALTER TABLE users ADD COLUMN mute_until TIMESTAMP")
        except: pass
        conn.commit()

init_db()

# --- ФУНКЦИИ БАНА/МУТА/ОЧЕРЕДИ ---
def get_ban_status(uid):
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,)).fetchone()[0] if conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,)).fetchone() else 0

def set_ban_status(uid, status):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, ?)", (uid, status))
        conn.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, uid))

def set_mute(uid, hours=24):
    expiry = datetime.now() + timedelta(hours=hours)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 0)", (uid,))
        conn.execute("UPDATE users SET mute_until = ? WHERE user_id = ?", (expiry, uid))

def check_mute(uid):
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT mute_until FROM users WHERE user_id = ?", (uid,)).fetchone()
        if res and res[0]:
            try: mute_until = datetime.fromisoformat(res[0])
            except: mute_until = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S.%f")
            if mute_until > datetime.now():
                rem = mute_until - datetime.now()
                h, r = divmod(rem.seconds, 3600)
                m, _ = divmod(r, 60)
                return True, f"{h}ч {m}мин"
    return False, ""

def add_to_queue(uid, numbers):
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("REPLACE INTO queue (user_id, numbers, ts) VALUES (?, ?, CURRENT_TIMESTAMP)", (uid, "\n".join(numbers)))

def update_timestamp(uid):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE queue SET ts = CURRENT_TIMESTAMP WHERE user_id = ?", (uid,))
        return cur.rowcount > 0

def get_user_queue(uid):
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT numbers, id FROM queue WHERE user_id = ?", (uid,)).fetchone()

def get_all_queue():
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT user_id, numbers FROM queue").fetchall()

def queue_pos(row_id):
    with sqlite3.connect(DB_NAME) as conn:
        pos = conn.execute("SELECT COUNT(*) FROM queue WHERE id <= ?", (row_id,)).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        return pos, total

async def cleaner_task():
    while True:
        await asyncio.sleep(60)
        try:
            with sqlite3.connect(DB_NAME) as conn:
                expired = conn.execute(f"SELECT user_id FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes')").fetchall()
                if expired:
                    conn.execute(f"DELETE FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes')")
                    conn.commit()
                    for (uid,) in expired:
                        try: await bot.send_message(uid, f"⚠️ <b>Тайм-аут.</b> Заявка удалена.", parse_mode="HTML", reply_markup=user_menu)
                        except: pass
        except: pass

# --- ФИЛЬТРЫ ---
class BannedFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return get_ban_status(m.from_user.id) == 1
class AdminFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return m.from_user.id in ADMIN_IDS

# --- КЛАВИАТУРЫ ---
user_menu = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Сдать номера"), KeyboardButton(text="📊 Статус заявки")],[KeyboardButton(text="✅ Я на месте"), KeyboardButton(text="ℹ️ Условия")]], resize_keyboard=True)
admin_panel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🟢 START WORK"), KeyboardButton(text="🔴 STOP WORK")],[KeyboardButton(text="📋 Очередь"), KeyboardButton(text="🔨 Бан"), KeyboardButton(text="🤐 Мут (24ч)")],[KeyboardButton(text="⬅️ Выход")]], resize_keyboard=True)
chat_admin_menu = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="💰 Номер взят"), KeyboardButton(text="🔒 Закончить чат")]], resize_keyboard=True)
chat_user_menu = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔒 Закончить чат")]], resize_keyboard=True)
info_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📂 Выплаты", url=PAYOUT_CHANNEL)]])

class AdminStates(StatesGroup): waiting_ban_id = State(); waiting_mute_id = State()
class UserStates(StatesGroup): waiting_numbers = State()

# --- ЛОГИКА ---
@dp.message(BannedFilter())
async def banned(m: types.Message): await m.answer("⛔ <b>Вы заблокированы.</b>", parse_mode="HTML")

@dp.message(Command("admin"), AdminFilter())
async def adm(m: types.Message): await m.answer(f"🔧 <b>Админка (ВЦ)</b>\nСтатус: {'🟢 ON' if IS_WORK_ACTIVE else '🔴 OFF'}", reply_markup=admin_panel_kb, parse_mode="HTML")
@dp.message(F.text == "⬅️ Выход", AdminFilter())
async def ex(m: types.Message): await m.answer("Выход.", reply_markup=user_menu)
@dp.message(F.text == "🟢 START WORK", AdminFilter())
async def sw(m: types.Message): global IS_WORK_ACTIVE; IS_WORK_ACTIVE=True; await m.answer("✅ Ворк ON", reply_markup=admin_panel_kb)
@dp.message(F.text == "🔴 STOP WORK", AdminFilter())
async def stw(m: types.Message): global IS_WORK_ACTIVE; IS_WORK_ACTIVE=False; await m.answer("🛑 Ворк OFF", reply_markup=admin_panel_kb)

@dp.message(F.text == "📋 Очередь", AdminFilter())
async def qlist(m: types.Message):
    rows = get_all_queue()
    if not rows: return await m.answer("📭 Пусто")
    await m.answer(f"📋 Заявок: {len(rows)}")
    for uid, nums in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ПРИНЯТЬ", callback_data=f"take_{uid}")]])
        await m.answer(f"👤 <code>{uid}</code>\n📞 {html.escape(nums.splitlines()[0])}", reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🔨 Бан", AdminFilter())
async def ban_s(m: types.Message, state: FSMContext): await state.set_state(AdminStates.waiting_ban_id); await m.answer("ID для бана:")
@dp.message(AdminStates.waiting_ban_id)
async def ban_f(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text); s = 0 if get_ban_status(uid) else 1; set_ban_status(uid, s)
        if s: sqlite3.connect(DB_NAME).execute("DELETE FROM queue WHERE user_id=?",(uid,)).commit()
        await m.answer(f"ID {uid}: {'Бан' if s else 'Разбан'}", reply_markup=admin_panel_kb)
    except: await m.answer("Ошибка ID")
    await state.clear()

@dp.message(F.text == "🤐 Мут (24ч)", AdminFilter())
async def mut_s(m: types.Message, state: FSMContext): await state.set_state(AdminStates.waiting_mute_id); await m.answer("ID для мута:")
@dp.message(AdminStates.waiting_mute_id)
async def mut_f(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text); set_mute(uid); sqlite3.connect(DB_NAME).execute("DELETE FROM queue WHERE user_id=?",(uid,)).commit()
        await m.answer(f"ID {uid} в муте на 24ч.", reply_markup=admin_panel_kb)
    except: await m.answer("Ошибка ID")
    await state.clear()

@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    await state.clear()
    if m.from_user.id in active_chats: return await m.answer("⚠️ Вы в чате.", reply_markup=chat_user_menu)
    st = "" if IS_WORK_ACTIVE else "\n🔴 <b>СТОП ВОРК</b>\n"
    r = get_user_queue(m.from_user.id); inf = f"\n\n📊 Очередь: {queue_pos(r[1])[0]}/{queue_pos(r[1])[1]}" if r else ""
    await m.answer(f"<b>💎 AndronWork (ВЦ)</b>\nПривет, {m.from_user.first_name}.{st}\n💵 <b>5$ / акк</b> | Холд {QUEUE_TIMEOUT_MIN} мин{inf}", reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "✅ Я на месте")
async def here(m: types.Message):
    if update_timestamp(m.from_user.id):
        p, t = queue_pos(get_user_queue(m.from_user.id)[1])
        await m.answer(f"🔄 Таймер обновлен. {p}/{t}", parse_mode="HTML")
    else: await m.answer("⚠️ Нет заявки.", reply_markup=user_menu)

@dp.message(F.text == "ℹ️ Условия")
async def info(m: types.Message): await m.answer(f"<b>Инфо ВЦ</b>\nСтавка: 5$\nХолд: {QUEUE_TIMEOUT_MIN} мин", parse_mode="HTML", reply_markup=info_btn)
@dp.message(F.text == "📊 Статус заявки")
async def my(m: types.Message):
    r = get_user_queue(m.from_user.id)
    if r: p,t = queue_pos(r[1]); await m.answer(f"📞 <code>{r[0]}</code>\n📍 {p}/{t}", parse_mode="HTML")
    else: await m.answer("📭 Пусто")

@dp.message(F.text == "📱 Сдать номера")
async def sub(m: types.Message, state: FSMContext):
    mt, tm = check_mute(m.from_user.id)
    if mt: return await m.answer(f"🤐 Мут еще {tm}")
    if not IS_WORK_ACTIVE: return await m.answer("🔴 Ворк стоп.")
    if m.from_user.id in active_chats: return await m.answer("⚠️ Заверши чат.")
    await state.set_state(UserStates.waiting_numbers); await m.answer("📝 Кидай номера:")

@dp.message(UserStates.waiting_numbers)
async def proc(m: types.Message, state: FSMContext):
    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    if not nums: return await m.answer("❌ Нет номеров.")
    add_to_queue(m.from_user.id, nums); await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ПРИНЯТЬ", callback_data=f"take_{m.from_user.id}")]])
    txt = f"🚨 <b>ВЦ ЗАЯВКА</b>\n👤 {html.escape(m.from_user.full_name)} (<code>{m.from_user.id}</code>)\n📞:\n{html.escape(m.text)}"
    for a in ADMIN_IDS: 
        try: await bot.send_message(a, txt, reply_markup=kb, parse_mode="HTML")
        except: pass
    await m.answer(f"✅ Принято. Жми «Я на месте» раз в {QUEUE_TIMEOUT_MIN} мин.", reply_markup=user_menu)

@dp.callback_query(F.data.startswith("take_"))
async def take(c: types.CallbackQuery):
    uid = int(c.data.split("_")[1])
    if uid in active_chats: return await c.answer("❌ Занято")
    active_chats[uid] = c.from_user.id; active_chats[c.from_user.id] = uid
    await c.message.edit_reply_markup(None); await c.message.answer(f"✅ Чат с {uid}", reply_markup=chat_admin_menu)
    try: await bot.send_message(uid, "👨‍💻 Админ тут.", reply_markup=chat_user_menu)
    except: pass

async def close(aid, uid, ut, at):
    if aid in active_chats: del active_chats[aid]
    if uid in active_chats: del active_chats[uid]
    try: await bot.send_message(uid, ut, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    try: await bot.send_message(aid, at, parse_mode="HTML", reply_markup=admin_panel_kb)
    except: pass

@dp.message(F.text == "💰 Номер взят")
async def done(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    uid = active_chats.get(m.from_user.id)
    if not uid: return await m.answer("Нет чата", reply_markup=admin_panel_kb)
    sqlite3.connect(DB_NAME).execute("DELETE FROM queue WHERE user_id=?",(uid,)).commit()
    msg = f"✅ <b>ПРИНЯТО (ВЦ)</b>\n💰 Выплата после стоп-ворка: <a href='{PAYOUT_CHANNEL}'>КАНАЛ</a>"
    await close(m.from_user.id, uid, msg, "💸 Готово.")

@dp.message(F.text == "🔒 Закончить чат")
async def stopc(m: types.Message):
    snd = m.from_user.id; ptr = active_chats.get(snd)
    if not ptr: return await m.answer("Чат закрыт", reply_markup=admin_panel_kb if snd in ADMIN_IDS else user_menu)
    adm, usr = (snd, ptr) if snd in ADMIN_IDS else (ptr, snd)
    await close(adm, usr, "🔒 Админ закрыл чат.", "🔒 Чат закрыт.")

@dp.message()
async def brg(m: types.Message):
    if m.text and m.text.startswith("/"): return
    ptr = active_chats.get(m.from_user.id)
    if ptr: 
        try: await m.copy_to(ptr)
        except: await m.answer("❌ Ошибка")
    elif m.from_user.id not in ADMIN_IDS: await m.answer("🤖 Используй меню.", reply_markup=user_menu)

# --- ИСПРАВЛЕННЫЙ ЗАПУСК ---
async def main():
    asyncio.create_task(cleaner_task())
    await bot.delete_webhook(drop_pending_updates=True) 
    print("🚀 Bot VC Started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
