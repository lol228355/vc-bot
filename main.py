import asyncio, logging, sqlite3, re, html
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== НАСТРОЙКИ ====================
TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY"
ADMIN_IDS = [8448843727, 8227071592]
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"
QUEUE_TIMEOUT_MIN = 15

# Глобальный переключатель работы
IS_WORK_ACTIVE = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

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
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_banned BOOLEAN DEFAULT 0,
            mute_until TIMESTAMP
        )""")
        try:
            cur.execute("ALTER TABLE users ADD COLUMN mute_until TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        conn.commit()

init_db()

# --- ФУНКЦИИ БАНА И МУТА ---
def get_ban_status(uid):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,))
        res = cur.fetchone()
        return res[0] if res else 0

def set_ban_status(uid, status):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, ?)", (uid, status))
        cur.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, uid))
        conn.commit()

def set_mute(uid, hours=24):
    expiry = datetime.now() + timedelta(hours=hours)
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 0)", (uid,))
        cur.execute("UPDATE users SET mute_until = ? WHERE user_id = ?", (expiry, uid))
        conn.commit()

def check_mute(uid):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT mute_until FROM users WHERE user_id = ?", (uid,))
        row = cur.fetchone()
        if row and row[0]:
            try:
                mute_until = datetime.fromisoformat(row[0])
            except ValueError:
                mute_until = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S.%f")
            if mute_until > datetime.now():
                remaining = mute_until - datetime.now()
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                return True, f"{hours}ч {minutes}мин"
    return False, ""

# --- ФУНКЦИИ ОЧЕРЕДИ ---
def add_to_queue(uid, numbers):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("REPLACE INTO queue (user_id, numbers, ts) VALUES (?, ?, CURRENT_TIMESTAMP)", (uid, "\n".join(numbers)))
        conn.commit()

def update_timestamp(uid):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE queue SET ts = CURRENT_TIMESTAMP WHERE user_id = ?", (uid,))
        return cur.rowcount > 0

def get_user_queue(uid):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT numbers, id FROM queue WHERE user_id = ?", (uid,))
        return cur.fetchone()

def get_all_queue():
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id, numbers FROM queue")
        return cur.fetchall()

def queue_pos(row_id):
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM queue WHERE id <= ?", (row_id,))
        pos = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM queue")
        total = cur.fetchone()[0]
        return pos, total

async def cleaner_task():
    while True:
        await asyncio.sleep(60)
        try:
            with sqlite3.connect(DB_NAME) as conn:
                cur = conn.cursor()
                cur.execute(f"SELECT user_id FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes')")
                expired = cur.fetchall()
                if expired:
                    cur.execute(f"DELETE FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes')")
                    conn.commit()
                    for (uid,) in expired:
                        try:
                            await bot.send_message(uid, f"⚠️ <b>Тайм-аут!</b>\nЗаявка удалена. Жми «✅ Я тут» чаще.", parse_mode="HTML", reply_markup=user_menu)
                        except: pass
        except Exception as e:
            logging.error(f"Cleaner error: {e}")

# ==================== ФИЛЬТРЫ ====================
class BannedFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return get_ban_status(message.from_user.id) == 1

class AdminFilter(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.from_user.id in ADMIN_IDS

# ==================== КЛАВИАТУРЫ ====================
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📱 Сдать номера"), KeyboardButton(text="📊 Мои номера")],
    [KeyboardButton(text="✅ Я тут"), KeyboardButton(text="❓ Инфо")]
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

info_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Канал с выплатами", url=PAYOUT_CHANNEL)]])

# ==================== STATES ====================
class AdminStates(StatesGroup):
    waiting_ban_id = State()
    waiting_mute_id = State()

class UserStates(StatesGroup):
    waiting_numbers = State()

# ==================== ХЭНДЛЕРЫ (БАН) ====================
@dp.message(BannedFilter())
async def banned_msg(m: types.Message):
    await m.answer("🚫 <b>Вы заблокированы администрацией навсегда.</b>", parse_mode="HTML")

# ==================== ХЭНДЛЕРЫ (АДМИНКА) ====================
@dp.message(Command("admin"), AdminFilter())
async def open_admin(m: types.Message):
    status = "🟢 ON" if IS_WORK_ACTIVE else "🔴 OFF"
    await m.answer(f"⚙️ <b>ADMIN PANEL</b>\nStatus: <b>{status}</b>", reply_markup=admin_panel_kb, parse_mode="HTML")

@dp.message(F.text == "⬅️ Выход", AdminFilter())
async def exit_admin(m: types.Message):
    await m.answer("Вышли в обычный режим.", reply_markup=user_menu)

@dp.message(F.text == "🟢 START WORK", AdminFilter())
async def start_work(m: types.Message):
    global IS_WORK_ACTIVE
    IS_WORK_ACTIVE = True
    await m.answer("✅ <b>ВОРК ЗАПУЩЕН!</b>", reply_markup=admin_panel_kb, parse_mode="HTML")

@dp.message(F.text == "🔴 STOP WORK", AdminFilter())
async def stop_work(m: types.Message):
    global IS_WORK_ACTIVE
    IS_WORK_ACTIVE = False
    await m.answer("🛑 <b>ВОРК ОСТАНОВЛЕН!</b>", reply_markup=admin_panel_kb, parse_mode="HTML")

@dp.message(F.text == "📋 Очередь", AdminFilter())
async def show_queue_list(m: types.Message):
    rows = get_all_queue()
    if not rows: return await m.answer("📭 Очередь пуста.")
    await m.answer(f"📋 <b>Заявок: {len(rows)}</b>", parse_mode="HTML")
    for uid, nums in rows:
        # ИСПРАВЛЕНО: Теперь показывает полный номер без точек
        full_num = html.escape(nums.splitlines()[0])
        txt = f"👤 ID: <code>{uid}</code>\n📞: <code>{full_num}</code>"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ВЗЯТЬ", callback_data=f"take_{uid}")]])
        await m.answer(txt, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🔨 Бан", AdminFilter())
async def ban_user_start(m: types.Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_ban_id)
    await m.answer("✍️ <b>Введите ID для бана/разбана:</b>", parse_mode="HTML")

@dp.message(AdminStates.waiting_ban_id)
async def ban_user_finish(m: types.Message, state: FSMContext):
    try:
        target_id = int(m.text.strip())
        new_status = 0 if get_ban_status(target_id) else 1
        set_ban_status(target_id, new_status)
        action = "забанен 🚫" if new_status else "разбанен ✅"
        await m.answer(f"Пользователь <code>{target_id}</code> {action}", parse_mode="HTML", reply_markup=admin_panel_kb)
        if new_status:
            with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM queue WHERE user_id = ?", (target_id,))
    except: await m.answer("❌ Ошибка ID.")
    await state.clear()

@dp.message(F.text == "🤐 Мут (24ч)", AdminFilter())
async def mute_user_start(m: types.Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_mute_id)
    await m.answer("✍️ <b>Введите ID для МУТА на 24ч:</b>", parse_mode="HTML")

@dp.message(AdminStates.waiting_mute_id)
async def mute_user_finish(m: types.Message, state: FSMContext):
    try:
        target_id = int(m.text.strip())
        set_mute(target_id, 24)
        with sqlite3.connect(DB_NAME) as conn:
             conn.execute("DELETE FROM queue WHERE user_id = ?", (target_id,))
        await m.answer(f"🤐 Юзер <code>{target_id}</code> в муте на 24ч.", parse_mode="HTML", reply_markup=admin_panel_kb)
    except: await m.answer("❌ Ошибка ID.")
    await state.clear()

# ==================== ХЭНДЛЕРЫ (ПОЛЬЗОВАТЕЛЬ) ====================
@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ У вас активный чат с админом!", reply_markup=chat_user_menu)

    status_text = ""
    if not IS_WORK_ACTIVE:
        status_text = "\n\n🔴 <b>ВОРК СЕЙЧАС ОСТАНОВЛЕН</b>"

    row = get_user_queue(m.from_user.id)
    info = ""
    if row:
        p, t = queue_pos(row[1])
        info = f"\n\n📋 <b>Твоя очередь: #{p} из {t}</b>"

    await m.answer(f"""<b>💎 AndronWork — ВЦ 2025</b>

👋 Привет, {html.escape(m.from_user.first_name)}!
{status_text}
💵 <b>ВЦ по 5$ | {QUEUE_TIMEOUT_MIN} мин | Без холда</b>
👇 Жми кнопки ниже:{info}""", reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "✅ Я тут")
async def cmd_here(m: types.Message):
    if m.from_user.id in active_chats:
        return await m.answer("✅ Ты на связи с админом!", reply_markup=chat_user_menu)
    
    if update_timestamp(m.from_user.id):
        row = get_user_queue(m.from_user.id)
        p, t = queue_pos(row[1])
        await m.answer(f"🟢 <b>Таймер обновлен!</b> #{p}/{t}", parse_mode="HTML")
    else:
        await m.answer("⚠️ Ты не в очереди.", reply_markup=user_menu)

@dp.message(F.text == "❓ Инфо")
async def cmd_info(m: types.Message):
    await m.answer(f"ℹ️ <b>FAQ</b>\n\nКанал выплат: {PAYOUT_CHANNEL}", parse_mode="HTML", reply_markup=info_btn)

@dp.message(F.text == "📊 Мои номера")
async def cmd_my_nums(m: types.Message):
    row = get_user_queue(m.from_user.id)
    if row:
        p, t = queue_pos(row[1])
        await m.answer(f"📄 Номера:\n<code>{row[0]}</code>\n\n#{p} из {t}", parse_mode="HTML")
    else:
        await m.answer("📭 Пусто")

@dp.message(F.text == "📱 Сдать номера")
async def cmd_submit(m: types.Message, state: FSMContext):
    is_muted, time_left = check_mute(m.from_user.id)
    if is_muted:
        return await m.answer(f"🤐 <b>Вам запрещено сдавать номера!</b>\n\n⏳ Мут истечет через: <b>{time_left}</b>", parse_mode="HTML")

    if not IS_WORK_ACTIVE:
        return await m.answer("🔴 <b>ВОРК ОСТАНОВЛЕН!</b>\nПрием заявок временно закрыт.", parse_mode="HTML")

    if m.from_user.id in active_chats:
        return await m.answer("⚠️ Заверши чат.", reply_markup=chat_user_menu)
    
    await state.set_state(UserStates.waiting_numbers)
    await m.answer("✍️ <b>Кидай номера (по 1 в строку):</b>", parse_mode="HTML")

@dp.message(UserStates.waiting_numbers)
async def process_numbers(m: types.Message, state: FSMContext):
    if not m.text: return await m.answer("❌ Нужен текст.")
    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    
    if not nums: return await m.answer("❌ Нет валидных номеров.")
    
    add_to_queue(m.from_user.id, nums)
    await state.clear()
    
    # ИСПРАВЛЕНО: Полный текст номера без точек
    full_nums_text = html.escape('\n'.join(nums))
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ВЗЯТЬ", callback_data=f"take_{m.from_user.id}")]])
    
    text = f"🚨 <b>NEW ЗАЯВКА</b>\n👤: {html.escape(m.from_user.full_name)}\n🆔: <code>{m.from_user.id}</code>\n📞:\n<code>{full_nums_text}</code>"
    
    for adm in ADMIN_IDS:
        try: await bot.send_message(adm, text, reply_markup=kb, parse_mode="HTML")
        except: pass
    
    # ИСПРАВЛЕНО: Красивое сообщение пользователю
    await m.answer(f"✅ <b>Заявка принята!</b>\n\n🕒 Не забывай жать <b>«✅ Я тут»</b> каждые {QUEUE_TIMEOUT_MIN} мин, чтобы не вылететь из очереди.", reply_markup=user_menu, parse_mode="HTML")

# ==================== ЛОГИКА ЧАТА ====================
@dp.callback_query(F.data.startswith("take_"))
async def admin_take(cb: types.CallbackQuery):
    if cb.from_user.id not in ADMIN_IDS: return
    user_id = int(cb.data.split("_")[1])
    
    if user_id in active_chats: return await cb.answer("❌ Занято!", show_alert=True)
    
    active_chats[user_id] = cb.from_user.id
    active_chats[cb.from_user.id] = user_id
    
    await cb.message.edit_reply_markup(reply_markup=None)
    await cb.message.answer(f"✅ Взят юзер <code>{user_id}</code>", reply_markup=chat_admin_menu, parse_mode="HTML")
    try: await bot.send_message(user_id, "👨‍💻 <b>Админ принял заявку!</b>\nКидай коды/фото сюда.", reply_markup=chat_user_menu, parse_mode="HTML")
    except: pass
    await cb.answer()

async def close_session(admin_id, user_id, u_text, a_text):
    if admin_id in active_chats: del active_chats[admin_id]
    if user_id in active_chats: del active_chats[user_id]
    try: await bot.send_message(user_id, u_text, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    try: await bot.send_message(admin_id, a_text, parse_mode="HTML", reply_markup=admin_panel_kb)
    except: pass

@dp.message(F.text == "💰 Номер взят")
async def admin_done(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    user_id = active_chats.get(m.from_user.id)
    if not user_id: return await m.answer("⚠️ Нет чата.", reply_markup=admin_panel_kb)
    
    with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
    
    # ИСПРАВЛЕНО: Сообщение о выплате после стоп ворка
    msg = (
        f"✅ <b>ПРИНЯТО!</b>\n\n"
        f"💰 <b>Выплата будет после СТОП-ВОРКА тут:</b>\n"
        f"👉 <a href='{PAYOUT_CHANNEL}'><b>КАНАЛ С ВЫПЛАТАМИ</b></a>"
    )
    await close_session(m.from_user.id, user_id, msg, "💸 <b>Готово!</b> Юзер уведомлен о стоп-ворке.")

@dp.message(F.text == "🔒 Закончить чат")
async def stop_chat(m: types.Message):
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)
    
    if not partner_id:
        kb = admin_panel_kb if sender_id in ADMIN_IDS else user_menu
        return await m.answer("🔒 Чат закрыт.", reply_markup=kb)
        
    if sender_id in ADMIN_IDS:
        adm, usr = sender_id, partner_id
        await close_session(adm, usr, "🔒 Админ закрыл чат.", "🔒 Чат закрыт.")
    else:
        adm, usr = partner_id, sender_id
        await close_session(adm, usr, "🔒 Чат закрыт.", "🔒 Юзер закрыл чат.")

@dp.message()
async def bridge_msg(m: types.Message):
    buttons = ["📱 Сдать номера", "✅ Я тут", "📊 Мои номера", "💰 Номер взят", "🔒 Закончить чат", "❓ Инфо", "🟢 START WORK", "🔴 STOP WORK", "📋 Очередь", "🔨 Бан", "⬅️ Выход", "🤐 Мут (24ч)"]
    if m.text and (m.text.startswith("/") or m.text in buttons): return
    
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)
    
    if partner_id:
        try: await m.copy_to(partner_id)
        except: await m.answer("❌ Ошибка отправки.")
    else:
        if sender_id not in ADMIN_IDS:
            await m.answer("🤖 Используй меню.", reply_markup=user_menu)

async def main():
    asyncio.create_task(cleaner_task())
    await bot.delete_webhook(drop_pending_updates=True)
    print("🚀 BOT STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
