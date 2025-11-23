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
ADMIN_IDS = [8448843727, 8340396727, 8227071592]
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"

DB_NAME = "bot_vc.db"
QUEUE_TIMEOUT_MIN = 15      
WARNING_TIME_MIN = 5        
HOLD_TIME_MIN = 15          # Таймер БезХолд (15 мин)
CODE_WAIT_MIN = 3

IS_WORK_ACTIVE = True
WARNED_USERS = set()

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS active_work (
                user_id INTEGER PRIMARY KEY,
                admin_id INTEGER,
                numbers TEXT,
                status TEXT DEFAULT 'process',
                hold_until TIMESTAMP,
                start_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_messages (
                user_id INTEGER,
                admin_id INTEGER,
                message_id INTEGER
            )
        """)
        try: conn.execute("ALTER TABLE users ADD COLUMN mute_until TIMESTAMP")
        except: pass
        try: conn.execute("ALTER TABLE active_work ADD COLUMN status TEXT DEFAULT 'process'")
        except: pass
        try: conn.execute("ALTER TABLE active_work ADD COLUMN hold_until TIMESTAMP")
        except: pass

init_db()

def get_conn(): return sqlite3.connect(DB_NAME)

def get_current_chat_user(admin_id):
    """Пытается найти юзера в памяти, если нет — ищет в БД и восстанавливает связь."""
    # 1. Проверяем память
    if admin_id in active_chats:
        return active_chats[admin_id]
    
    # 2. Если в памяти пусто, проверяем БД (защита от перезагрузки)
    with get_conn() as conn:
        # Ищем запись, где этот админ работает с кем-то
        row = conn.execute("SELECT user_id FROM active_work WHERE admin_id = ?", (admin_id,)).fetchone()
        if row:
            uid = row[0]
            # Восстанавливаем в память
            active_chats[admin_id] = uid
            active_chats[uid] = admin_id
            return uid
    return None

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
            delete_admin_messages_for_user(uid)

def set_mute(uid, hours=24):
    expiry = datetime.now() + timedelta(hours=hours)
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 0)", (uid,))
        conn.execute("UPDATE users SET mute_until = ? WHERE user_id = ?", (expiry, uid))
        conn.execute("DELETE FROM queue WHERE user_id=?", (uid,))
        delete_admin_messages_for_user(uid)

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

def save_admin_message(user_id, admin_id, message_id):
    with get_conn() as conn:
        conn.execute("INSERT INTO admin_messages (user_id, admin_id, message_id) VALUES (?, ?, ?)", (user_id, admin_id, message_id))

def get_admin_messages(user_id):
    with get_conn() as conn:
        return conn.execute("SELECT admin_id, message_id FROM admin_messages WHERE user_id=?", (user_id,)).fetchall()

def delete_admin_messages_for_user(user_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM admin_messages WHERE user_id=?", (user_id,))

def update_timestamp(uid):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE queue SET ts = CURRENT_TIMESTAMP WHERE user_id = ?", (uid,))
        return cur.rowcount > 0

def get_queue_info(uid):
    with get_conn() as conn: return conn.execute("SELECT numbers, id FROM queue WHERE user_id = ?", (uid,)).fetchone()

def get_all_queue():
    with get_conn() as conn: return conn.execute("SELECT user_id, numbers FROM queue ORDER BY id ASC").fetchall()

def get_active_work_list():
    with get_conn() as conn: return conn.execute("SELECT user_id, admin_id, numbers, status, hold_until FROM active_work").fetchall()

def get_position(row_id):
    with get_conn() as conn:
        pos = conn.execute("SELECT COUNT(*) FROM queue WHERE id <= ?", (row_id,)).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        return pos, total

# ==================== CLEANER ====================
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
                    msgs = get_admin_messages(uid)
                    for aid, mid in msgs:
                        try: await bot.delete_message(chat_id=aid, message_id=mid)
                        except: pass
                    delete_admin_messages_for_user(uid)
                    with get_conn() as conn: conn.execute("DELETE FROM queue WHERE user_id = ?", (uid,))
                    if uid in WARNED_USERS: WARNED_USERS.remove(uid)
                    try: await bot.send_message(uid, "❌ <b>Тайм-аут.</b> Заявка удалена.", parse_mode="HTML", reply_markup=user_menu)
                    except: pass
                elif diff_minutes >= (QUEUE_TIMEOUT_MIN - WARNING_TIME_MIN):
                    if uid not in WARNED_USERS:
                        WARNED_USERS.add(uid)
                        try: await bot.send_message(uid, f"⚠️ <b>Внимание!</b>\nЧерез {WARNING_TIME_MIN} мин удаление.\nЖмите <b>«✅ Я онлайн»</b>!", parse_mode="HTML")
                        except: pass
        except Exception as e: logging.error(f"Cleaner Error: {e}")

# ==================== КЛАВИАТУРЫ ====================
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="✨ Новая заявка")],
    [KeyboardButton(text="📍 Моя позиция")],
    [KeyboardButton(text="✅ Я онлайн (Обновить таймер)")],
    [KeyboardButton(text="💰 Условия и выплаты")]
], resize_keyboard=True)

admin_panel_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🟢 START WORK"), KeyboardButton(text="🔴 STOP WORK")],
    [KeyboardButton(text="📋 Очередь"), KeyboardButton(text="📱 Номера (БезХолд)")],
    [KeyboardButton(text="🔨 Бан"), KeyboardButton(text="🤐 Мут (24ч)")],
    [KeyboardButton(text="⬅️ Выход")]
], resize_keyboard=True)

# УПРОЩЕННОЕ ЧАТ-МЕНЮ: ОСТАВИЛИ ТОЛЬКО "Номер встал"
chat_admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Номер встал")]
], resize_keyboard=True)

chat_user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

# ==================== HANDLERS ====================
class AdminStates(StatesGroup): waiting_ban = State(); waiting_mute = State()
class UserStates(StatesGroup): waiting_nums = State()
class BannedFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return get_ban_status(m.from_user.id) == 1
class AdminFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return m.from_user.id in ADMIN_IDS

@dp.message(BannedFilter())
async def banned_handler(m: types.Message): await m.answer("⛔ <b>Вы заблокированы.</b>", parse_mode="HTML")

# --- АДМИНКА ---
# ... (Остальные хэндлеры админки без изменений) ...

# --- ПОЛЬЗОВАТЕЛЬ ---
# ... (Остальные хэндлеры пользователя без изменений) ...

# ==================== ЧАТ СИСТЕМА ====================
@dp.callback_query(F.data.startswith("take_"))
async def take_chat(c: types.CallbackQuery):
    uid = int(c.data.split("_")[1])
    if uid in active_chats: 
        try: await c.message.delete()
        except: pass
        return await c.answer("❌ Уже занято.")
    
    nums_data = ""
    with get_conn() as conn:
        row = conn.execute("SELECT numbers FROM queue WHERE user_id=?", (uid,)).fetchone()
        if row: 
            nums_data = row[0]
            conn.execute("INSERT OR REPLACE INTO active_work (user_id, admin_id, numbers, status) VALUES (?, ?, ?, 'process')", (uid, c.from_user.id, nums_data))
            conn.execute("DELETE FROM queue WHERE user_id=?", (uid,))

    admin_msgs = get_admin_messages(uid)
    for aid, mid in admin_msgs:
        try: await bot.delete_message(chat_id=aid, message_id=mid)
        except: pass
    delete_admin_messages_for_user(uid)

    active_chats[uid] = c.from_user.id
    active_chats[c.from_user.id] = uid
    if uid in WARNED_USERS: WARNED_USERS.remove(uid)

    await c.message.answer(f"✅ Взял {uid}", reply_markup=chat_admin_menu)
    try: await bot.send_message(uid, f"📸 <b>Код запрошен!</b>\nАдминистратор отправит вам фото кода.\n⚡️ <b>У вас есть {CODE_WAIT_MIN} минуты на ввод!</b>", parse_mode="HTML", reply_markup=chat_user_menu)
    except: pass

async def close_chat_func(admin_id, user_id, user_text, admin_text):
    if admin_id in active_chats: del active_chats[admin_id]
    if user_id in active_chats: del active_chats[user_id]
    
    try: await bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    try: await bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=admin_panel_kb)
    except: pass

# ИЗМЕНЕНИЕ ФИЛЬТРА: Теперь слушает просто "Номер встал"
@dp.message(F.text == "Номер встал")
async def admin_set_hold(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    user_id = get_current_chat_user(m.from_user.id)
    if not user_id: return await m.answer("Нет чата.")
    
    hold_end = datetime.now() + timedelta(minutes=HOLD_TIME_MIN)
    with get_conn() as conn:
        conn.execute("UPDATE active_work SET status='hold', hold_until=? WHERE user_id=?", (hold_end, user_id))

    await close_chat_func(m.from_user.id, user_id, 
                     f"✅ <b>Номер принят!</b>\n⏳ Пошел БезХолд {HOLD_TIME_MIN} мин.\nОжидайте выплату.",
                     f"✅ Номер отправлен в БезХолд на {HOLD_TIME_MIN} мин.\nЧат закрыт.")

# Хэндлеры для СЛЕТЕЛ и ЗАКРЫТЬ ЧАТ удалены из кнопок, 
# но их логика остаётся для предотвращения ошибок, если админ введёт текст
@dp.message(F.text == "❌ СЛЕТЕЛ (Сразу)")
async def admin_fail_chat(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    user_id = get_current_chat_user(m.from_user.id)
    if not user_id: return await m.answer("Нет чата.")
    with get_conn() as conn: conn.execute("DELETE FROM active_work WHERE user_id=?", (user_id,))
    
    await close_chat_func(m.from_user.id, user_id, 
                     "❌ <b>Номер невалид / не отсканирован.</b>", 
                     "❌ Помечен как слетевший. Чат закрыт.")

@dp.message(F.text == "🔒 Закрыть чат")
@dp.message(F.text == "🔒 Просто закрыть")
@dp.message(F.text == "🔒 Закончить чат")
async def stop_chat_any(m: types.Message):
    sender = m.from_user.id
    partner = get_current_chat_user(sender)
    if not partner: return await m.answer("Нет чата.", reply_markup=user_menu)
    
    with get_conn() as conn: conn.execute("DELETE FROM active_work WHERE user_id=?", (partner if sender in ADMIN_IDS else sender,))

    if sender in ADMIN_IDS:
        await close_chat_func(sender, partner, "🔒 Админ закрыл чат.", "🔒 Чат закрыт.")
    else:
        await close_chat_func(partner, sender, "🔒 Вы закрыли чат.", "🔒 Юзер закрыл чат.")

# ФОТО ОТ АДМИНА
@dp.message(F.photo)
async def photo_bridge(m: types.Message):
    partner = get_current_chat_user(m.from_user.id)
    if partner:
        try: 
            await bot.send_photo(partner, m.photo[-1].file_id, caption="📸 <b>Ваш код на фото! Введите его.</b>", parse_mode="HTML")
            await m.answer("✅ Фото отправлено.")
        except: await m.answer("❌ Ошибка отправки")

@dp.message()
async def chat_bridge(m: types.Message):
    if m.text and m.text.startswith("/"): return
    partner = get_current_chat_user(m.from_user.id)
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
