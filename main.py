import asyncio, logging, sqlite3, re, html
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

# Глобальный переключатель работы (по умолчанию включен)
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
        # Таблица очереди
        cur.execute("""CREATE TABLE IF NOT EXISTS queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            numbers TEXT,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Таблица пользователей (для банов)
        cur.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            is_banned BOOLEAN DEFAULT 0
        )""")
        conn.commit()

init_db()

# --- ФУНКЦИИ БД ---
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
    """Получить всех юзеров в очереди"""
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

# ГЛАВНАЯ АДМИН ПАНЕЛЬ
admin_panel_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🟢 START WORK"), KeyboardButton(text="🔴 STOP WORK")],
    [KeyboardButton(text="📋 Очередь (Список)"), KeyboardButton(text="🔨 Бан Пользователя")],
    [KeyboardButton(text="⬅️ Выйти из админки")]
], resize_keyboard=True)

chat_admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💰 Номер взят"), KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

chat_user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

info_btn = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 Канал с выплатами", url=PAYOUT_CHANNEL)]])

# ==================== FSM для Админки ====================
class AdminStates(StatesGroup):
    waiting_ban_id = State()

class UserStates(StatesGroup):
    waiting_numbers = State()

# ==================== ХЭНДЛЕРЫ (БАН) ====================
@dp.message(BannedFilter())
async def banned_msg(m: types.Message):
    await m.answer("🚫 <b>Вы заблокированы администрацией.</b>", parse_mode="HTML")

# ==================== ХЭНДЛЕРЫ (АДМИНКА) ====================
@dp.message(Command("admin"), AdminFilter())
async def open_admin(m: types.Message):
    status = "🟢 ВКЛЮЧЕН" if IS_WORK_ACTIVE else "🔴 ВЫКЛЮЧЕН"
    await m.answer(f"⚙️ <b>Админ-панель</b>\n\nСтатус ворка: <b>{status}</b>", reply_markup=admin_panel_kb, parse_mode="HTML")

@dp.message(F.text == "⬅️ Выйти из админки", AdminFilter())
async def exit_admin(m: types.Message):
    await m.answer("Вышли в обычный режим.", reply_markup=user_menu)

@dp.message(F.text == "🟢 START WORK", AdminFilter())
async def start_work(m: types.Message):
    global IS_WORK_ACTIVE
    IS_WORK_ACTIVE = True
    await m.answer("✅ <b>ВОРК ЗАПУЩЕН!</b>\nПользователи могут кидать заявки.", reply_markup=admin_panel_kb, parse_mode="HTML")
    # Можно сделать рассылку всем, что ворк начался (по желанию)

@dp.message(F.text == "🔴 STOP WORK", AdminFilter())
async def stop_work(m: types.Message):
    global IS_WORK_ACTIVE
    IS_WORK_ACTIVE = False
    await m.answer("🛑 <b>ВОРК ОСТАНОВЛЕН!</b>\nПрием заявок закрыт.", reply_markup=admin_panel_kb, parse_mode="HTML")

@dp.message(F.text == "📋 Очередь (Список)", AdminFilter())
async def show_queue_list(m: types.Message):
    rows = get_all_queue()
    if not rows:
        return await m.answer("📭 Очередь пуста.")
    
    await m.answer(f"📋 <b>Активных заявок: {len(rows)}</b>", parse_mode="HTML")
    
    for uid, nums in rows:
        txt = f"👤 ID: <code>{uid}</code>\n📞: {nums.splitlines()[0]}..."
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ВЗЯТЬ", callback_data=f"take_{uid}")]])
        await m.answer(txt, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🔨 Бан Пользователя", AdminFilter())
async def ban_user_start(m: types.Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_ban_id)
    await m.answer("✍️ <b>Введите ID пользователя</b> для бана/разбана:", parse_mode="HTML")

@dp.message(AdminStates.waiting_ban_id)
async def ban_user_finish(m: types.Message, state: FSMContext):
    try:
        target_id = int(m.text.strip())
        current_status = get_ban_status(target_id)
        new_status = 0 if current_status else 1
        
        set_ban_status(target_id, new_status)
        
        action = "забанен 🚫" if new_status else "разбанен ✅"
        await m.answer(f"Пользователь <code>{target_id}</code> {action}", parse_mode="HTML", reply_markup=admin_panel_kb)
        
        # Если забанили - кикаем из очереди
        if new_status:
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM queue WHERE user_id = ?", (target_id,))
    except ValueError:
        await m.answer("❌ Это не ID. Отмена.")
    
    await state.clear()

# ==================== ХЭНДЛЕРЫ (ПОЛЬЗОВАТЕЛЬ) ====================
@dp.message(Command("start"))
async def cmd_start(m: types.Message, state: FSMContext):
    await state.clear()
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ У вас активный чат с админом!", reply_markup=chat_user_menu)

    status_text = ""
    if not IS_WORK_ACTIVE:
        status_text = "\n\n🔴 <b>ВОРК СЕЙЧАС ОСТАНОВЛЕН (СТОП-ВОРК)</b>"

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
    # ПРОВЕРКА НА СТОП ВОРК
    if not IS_WORK_ACTIVE:
        return await m.answer("🔴 <b>ВОРК ОСТАНОВЛЕН!</b>\nПрием заявок временно закрыт. Ожидайте старта.", parse_mode="HTML")

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
    
    # Уведомление
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ВЗЯТЬ", callback_data=f"take_{m.from_user.id}")]])
    text = f"🚨 <b>NEW ЗАЯВКА</b>\n👤: {html.escape(m.from_user.full_name)}\n🆔: <code>{m.from_user.id}</code>\n📞: <code>{nums[0]}...</code>"
    for adm in ADMIN_IDS:
        try: await bot.send_message(adm, text, reply_markup=kb, parse_mode="HTML")
        except: pass
    
    await m.answer("✅ <b>В очереди!</b> Жми «Я тут» каждые 15 мин.", reply_markup=user_menu)

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
    try: await bot.send_message(admin_id, a_text, parse_mode="HTML", reply_markup=chat_admin_menu) # Оставляем меню чата или меняем на админку
    except: pass

@dp.message(F.text == "💰 Номер взят")
async def admin_done(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    user_id = active_chats.get(m.from_user.id)
    if not user_id: return await m.answer("⚠️ Нет чата.", reply_markup=admin_panel_kb) # Возвращаем в админку если нет чата
    
    with sqlite3.connect(DB_NAME) as conn: conn.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
    
    msg = f"✅ <b>ПРИНЯТО!</b>\nВыплата тут: <a href='{PAYOUT_CHANNEL}'>КАНАЛ</a>"
    # После завершения выплаты возвращаем админу админ-панель
    if m.from_user.id in active_chats: del active_chats[m.from_user.id]
    if user_id in active_chats: del active_chats[user_id]
    
    try: await bot.send_message(user_id, msg, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    await m.answer("💸 <b>Готово!</b>", reply_markup=admin_panel_kb) # Возврат в админку

@dp.message(F.text == "🔒 Закончить чат")
async def stop_chat(m: types.Message):
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)
    
    if not partner_id:
        kb = admin_panel_kb if sender_id in ADMIN_IDS else user_menu
        return await m.answer("🔒 Чат закрыт.", reply_markup=kb)
        
    if sender_id in ADMIN_IDS:
        # Админ закрыл - ему админку, юзеру меню
        kb_adm = admin_panel_kb
        kb_user = user_menu
        txt_adm = "🔒 Чат закрыт."
        txt_user = "🔒 Админ закрыл чат."
    else:
        # Юзер закрыл
        kb_adm = admin_panel_kb # Или chat_admin_menu, но лучше вернуть в админку
        kb_user = user_menu
        txt_adm = "🔒 Юзер закрыл чат."
        txt_user = "🔒 Чат закрыт."
    
    # Ручное закрытие
    if sender_id in active_chats: del active_chats[sender_id]
    if partner_id in active_chats: del active_chats[partner_id]
    
    # Отправка
    adm = sender_id if sender_id in ADMIN_IDS else partner_id
    usr = partner_id if sender_id in ADMIN_IDS else sender_id
    
    try: await bot.send_message(usr, txt_user, reply_markup=kb_user)
    except: pass
    try: await bot.send_message(adm, txt_adm, reply_markup=kb_adm)
    except: pass

@dp.message()
async def bridge_msg(m: types.Message):
    buttons = ["📱 Сдать номера", "✅ Я тут", "📊 Мои номера", "💰 Номер взят", "🔒 Закончить чат", "❓ Инфо", "🟢 START WORK", "🔴 STOP WORK", "📋 Очередь (Список)", "🔨 Бан Пользователя", "⬅️ Выйти из админки"]
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
    print("🚀 ADMIN PANEL ADDED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
