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
TOKEN = "8513008058:AAFMzDqlvqlhvqptKERIwoqZ2a85E4Msn1o"
ADMIN_IDS = [8448843727, 8340396727, 8227071592]
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"

DB_NAME = "bot_vc.db"
QUEUE_TIMEOUT_MIN = 15      
WARNING_TIME_MIN = 5        
HOLD_TIME_MIN = 15          # Таймер БезХолд (15 мин)
CODE_WAIT_MIN = 3

# ТЕКСТ ТАРИФА
TARIFF_TEXT = "БХ РФ (RU) - 15 мин/$5.0"

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
                username TEXT,
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
                username TEXT,
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
        
        # Обновление старой БД (добавление колонок если их нет)
        try: conn.execute("ALTER TABLE users ADD COLUMN mute_until TIMESTAMP")
        except: pass
        try: conn.execute("ALTER TABLE active_work ADD COLUMN status TEXT DEFAULT 'process'")
        except: pass
        try: conn.execute("ALTER TABLE active_work ADD COLUMN hold_until TIMESTAMP")
        except: pass
        
        # ДОБАВЛЯЕМ КОЛОНКУ USERNAME
        try: conn.execute("ALTER TABLE queue ADD COLUMN username TEXT")
        except: pass
        try: conn.execute("ALTER TABLE active_work ADD COLUMN username TEXT")
        except: pass

init_db()

def get_conn(): return sqlite3.connect(DB_NAME)

def get_current_chat_user(admin_id):
    """Пытается найти юзера в памяти, если нет — ищет в БД и восстанавливает связь."""
    if admin_id in active_chats:
        return active_chats[admin_id]
    
    with get_conn() as conn:
        row = conn.execute("SELECT user_id FROM active_work WHERE admin_id = ?", (admin_id,)).fetchone()
        if row:
            uid = row[0]
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

def add_to_queue(uid, username, numbers):
    # numbers - это уже список
    formatted_numbers = "\n".join(numbers)
    with get_conn() as conn:
        conn.execute("REPLACE INTO queue (user_id, username, numbers, ts) VALUES (?, ?, ?, CURRENT_TIMESTAMP)", (uid, username, formatted_numbers))

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
    # Теперь берем и username
    with get_conn() as conn: return conn.execute("SELECT user_id, numbers, username FROM queue ORDER BY id ASC").fetchall()

def get_active_work_list():
    # Теперь берем и username
    with get_conn() as conn: return conn.execute("SELECT user_id, admin_id, numbers, status, hold_until, username FROM active_work").fetchall()

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
    [KeyboardButton(text="📱 Сдать номера")], 
    [KeyboardButton(text="📍 Моя позиция")],
    [KeyboardButton(text="✅ Я онлайн (Обновить таймер)")],
    [KeyboardButton(text="💰 Условия и выплаты")]
], resize_keyboard=True)

# МЕНЮ ВЫБОРА ТАРИФА (ОБНОВЛЕНО)
tariffs_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text=TARIFF_TEXT, callback_data="tariff_ru")]
])

admin_panel_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🟢 START WORK"), KeyboardButton(text="🔴 STOP WORK")],
    [KeyboardButton(text="📋 Очередь"), KeyboardButton(text="📱 Номера (БезХолд)")],
    [KeyboardButton(text="🔨 Бан"), KeyboardButton(text="🤐 Мут (24ч)")],
    [KeyboardButton(text="⬅️ Выход")]
], resize_keyboard=True)

chat_admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Номер встал")]
], resize_keyboard=True)

chat_user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True)

# ==================== HANDLERS / STATES ====================
class AdminStates(StatesGroup): waiting_ban = State(); waiting_mute = State()
class UserStates(StatesGroup): waiting_nums = State()

class BannedFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return get_ban_status(m.from_user.id) == 1

class AdminFilter(BaseFilter):
    async def __call__(self, m: types.Message) -> bool: return m.from_user.id in ADMIN_IDS

@dp.message(BannedFilter())
async def banned_handler(m: types.Message): await m.answer("⛔ <b>Вы заблокированы.</b>", parse_mode="HTML")

# --- ЛОГИКА СДАЧИ НОМЕРОВ ---

@dp.message(F.text == "📱 Сдать номера")
async def ask_tariff(m: types.Message):
    is_muted, info = check_mute(m.from_user.id)
    if is_muted:
        return await m.answer(f"🤐 Вы в муте ещё {info}.")
    await m.answer("Выберите тариф:", reply_markup=tariffs_kb)

@dp.callback_query(F.data == "tariff_ru")
async def tariff_chosen(c: types.CallbackQuery, state: FSMContext):
    await c.answer()
    is_muted, info = check_mute(c.from_user.id)
    if is_muted:
        return await c.message.answer(f"🤐 Вы в муте ещё {info}.")

    await state.set_state(UserStates.waiting_nums)
    await c.message.edit_text(
        "📝 <b>Введите ваши номера:</b>\n\n"
        "Можно списком, можно в строчку.\n"
        "Пример:\n<code>+79001234567\n+79007654321</code>",
        parse_mode="HTML"
    )

@dp.message(UserStates.waiting_nums)
async def receive_numbers(m: types.Message, state: FSMContext):
    text = m.text
    if not text: return
    
    # ИСПРАВЛЕНИЕ: Используем Regex для поиска номеров
    # Ищет последовательности цифр от 10 до 15 знаков, возможно с плюсом
    found_numbers = re.findall(r'\+?\d{10,15}', text)
    valid_numbers = list(set(found_numbers)) # Удаляем дубликаты
    
    if not valid_numbers:
        return await m.answer("❌ Не найдено корректных номеров. Попробуйте еще раз.", reply_markup=user_menu)

    # Сохраняем username пользователя (или "Без ника")
    username = f"@{m.from_user.username}" if m.from_user.username else "Без ника"

    add_to_queue(m.from_user.id, username, valid_numbers)
    await state.clear()
    
    await m.answer(
        f"✅ <b>Заявка принята!</b>\n"
        f"Тариф: {TARIFF_TEXT}\n"
        f"Количество: {len(valid_numbers)}\n"
        f"Ожидайте, администратор скоро возьмет их в работу.",
        parse_mode="HTML",
        reply_markup=user_menu
    )
    
    for admin_id in ADMIN_IDS:
        try: 
            await bot.send_message(
                admin_id, 
                f"🆕 <b>Новая заявка!</b>\n"
                f"Юзер: {username} (ID: <code>{m.from_user.id}</code>)\n"
                f"Кол-во: {len(valid_numbers)}", 
                parse_mode="HTML"
            )
        except: pass

# --- ОСТАЛЬНЫЕ ХЭНДЛЕРЫ ЮЗЕРА ---

@dp.message(F.text == "📍 Моя позиция")
async def my_pos(m: types.Message):
    row = get_queue_info(m.from_user.id)
    if not row:
        return await m.answer("📂 У вас нет активных заявок в очереди.")
    pos, total = get_position(row[1])
    await m.answer(f"📊 <b>Ваша позиция:</b> {pos} из {total}\n⏳ Ожидайте...", parse_mode="HTML")

@dp.message(F.text.contains("Я онлайн"))
async def im_online(m: types.Message):
    if update_timestamp(m.from_user.id):
        if m.from_user.id in WARNED_USERS: WARNED_USERS.remove(m.from_user.id)
        await m.answer("✅ Таймер обновлен! Вы в очереди.")
    else:
        await m.answer("⚠️ Вы не в очереди.")

@dp.message(F.text == "💰 Условия и выплаты")
async def show_rules(m: types.Message):
    await m.answer(f"ℹ️ <b>Инфо:</b>\nВыплаты тут: {PAYOUT_CHANNEL}", parse_mode="HTML")

@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    await m.answer("👋 Привет! Сдавай номера через кнопку ниже.", reply_markup=user_menu)

# --- АДМИНКА ---

@dp.message(Command("admin"), AdminFilter())
async def admin_start(m: types.Message):
    await m.answer("🔧 Админ-панель", reply_markup=admin_panel_kb)

@dp.message(F.text == "⬅️ Выход", AdminFilter())
async def admin_exit(m: types.Message):
    await m.answer("Вышли.", reply_markup=user_menu)

@dp.message(F.text == "📋 Очередь", AdminFilter())
async def show_queue(m: types.Message):
    rows = get_all_queue()
    if not rows: return await m.answer("📭 Очередь пуста.")
    
    text = "📋 <b>Очередь:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    # Теперь распаковываем 3 значения (uid, nums, username)
    for uid, nums, username in rows:
        count = len(nums.split('\n'))
        # Отображаем Username в списке
        display_name = username if username else "Без ника"
        text += f"👤 {display_name} | ID: <code>{uid}</code> | {count} шт.\n"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"Взять {uid} ({count} шт)", callback_data=f"take_{uid}")])
        
    await m.answer(text, parse_mode="HTML", reply_markup=kb)

# --- ФУНКЦИЯ ПРОСМОТРА ХОЛДОВ С КНОПКОЙ СЛЕТА ---
@dp.message(F.text == "📱 Номера (БезХолд)", AdminFilter())
async def show_hold(m: types.Message):
    rows = get_active_work_list()
    if not rows: return await m.answer("📭 Пусто.")
    
    text = "📱 <b>В работе / Холд:</b>\n\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    for uid, aid, nums, status, hold_until, username in rows:
        display_name = username if username else str(uid)
        
        if status == 'hold' and hold_until:
            try:
                if isinstance(hold_until, str):
                    try: ht = datetime.fromisoformat(hold_until)
                    except: ht = datetime.strptime(hold_until, "%Y-%m-%d %H:%M:%S.%f")
                else: ht = hold_until
                
                rem = ht - datetime.now()
                if rem.total_seconds() > 0:
                    m_left = int(rem.total_seconds() // 60)
                    text += f"⏳ {display_name} | Осталось {m_left} мин\n"
                    # ДОБАВЛЯЕМ КНОПКУ СЛЕТА
                    kb.inline_keyboard.append([
                        InlineKeyboardButton(text=f"❌ СЛЕТ {display_name}", callback_data=f"drophold_{uid}")
                    ])
                else:
                    text += f"✅ {display_name} | <b>ГОТОВ К ВЫПЛАТЕ</b>\n"
            except:
                text += f"⚠️ {display_name} | Ошибка времени\n"
        else:
            text += f"⚙️ {display_name} | В процессе у админа {aid}\n"
            
    if not kb.inline_keyboard:
        await m.answer(text, parse_mode="HTML")
    else:
        await m.answer(text, parse_mode="HTML", reply_markup=kb)

# --- ОБРАБОТЧИК КНОПКИ СЛЕТА ---
@dp.callback_query(F.data.startswith("drophold_"))
async def admin_drop_hold_click(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return
    uid = int(c.data.split("_")[1])
    
    # Удаляем из базы
    with get_conn() as conn:
        conn.execute("DELETE FROM active_work WHERE user_id=?", (uid,))
    
    try: await c.message.delete()
    except: pass
    
    await c.message.answer(f"🗑 ID {uid} помечен как <b>СЛЕТ</b>.")
    
    # УВЕДОМЛЕНИЕ ЮЗЕРУ О СЛЕТЕ (СТРОГОЕ)
    try:
        await bot.send_message(
            uid,
            "❌ <b>НОМЕР СЛЕТЕЛ!</b>\n\n"
            "Номер перестал работать раньше времени (таймер не завершен).\n"
            "⚠️ <b>ОЧЕНЬ ВАЖНО: НЕ ОТВЯЗЫВАЙТЕ УСТРОЙСТВО!</b>\n"
            "⚠️ <b>НЕ ВЫХОДИТЕ ИЗ АККАУНТА!</b>\n\n"
            "Если вы отвяжете номер, оплата будет невозможна даже частично.",
            parse_mode="HTML",
            reply_markup=user_menu
        )
    except: pass

# --- БАН / МУТ ---

@dp.message(F.text == "🔨 Бан", AdminFilter())
async def ban_start(m: types.Message, state: FSMContext):
    await m.answer("Введите ID для БАНА:")
    await state.set_state(AdminStates.waiting_ban)

@dp.message(AdminStates.waiting_ban)
async def ban_finish(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text)
        set_ban_status(uid, 1)
        await m.answer(f"🔨 Юзер {uid} забанен.")
    except: await m.answer("❌ Некорректный ID")
    await state.clear()

@dp.message(F.text == "🤐 Мут (24ч)", AdminFilter())
async def mute_start(m: types.Message, state: FSMContext):
    await m.answer("Введите ID для МУТА:")
    await state.set_state(AdminStates.waiting_mute)

@dp.message(AdminStates.waiting_mute)
async def mute_finish(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text)
        set_mute(uid, 24)
        await m.answer(f"🤐 Юзер {uid} в муте на 24ч.")
    except: await m.answer("❌ Некорректный ID")
    await state.clear()

# ==================== ЧАТ СИСТЕМА ====================
@dp.callback_query(F.data.startswith("take_"))
async def take_chat(c: types.CallbackQuery):
    uid = int(c.data.split("_")[1])
    if uid in active_chats: 
        try: await c.message.delete()
        except: pass
        return await c.answer("❌ Уже занято.")
    
    nums_data = ""
    username_data = ""
    with get_conn() as conn:
        row = conn.execute("SELECT numbers, username FROM queue WHERE user_id=?", (uid,)).fetchone()
        if row: 
            nums_data = row[0]
            username_data = row[1]
            # Вставляем в активную работу с сохранением username
            conn.execute("INSERT OR REPLACE INTO active_work (user_id, admin_id, username, numbers, status) VALUES (?, ?, ?, ?, 'process')", (uid, c.from_user.id, username_data, nums_data))
            conn.execute("DELETE FROM queue WHERE user_id=?", (uid,))

    admin_msgs = get_admin_messages(uid)
    for aid, mid in admin_msgs:
        try: await bot.delete_message(chat_id=aid, message_id=mid)
        except: pass
    delete_admin_messages_for_user(uid)

    active_chats[uid] = c.from_user.id
    active_chats[c.from_user.id] = uid
    if uid in WARNED_USERS: WARNED_USERS.remove(uid)

    display_name = username_data if username_data else f"ID {uid}"

    # Красивый вывод номеров для копирования
    await c.message.answer(
        f"✅ <b>Взял в работу:</b> {display_name}\n\n"
        f"📱 <b>Номера:</b>\n<code>{nums_data}</code>", 
        parse_mode="HTML",
        reply_markup=chat_admin_menu
    )
    try: await bot.send_message(uid, f"📸 <b>Код запрошен!</b>\nАдминистратор отправит вам фото кода.\n⚡️ <b>У вас есть {CODE_WAIT_MIN} минуты на ввод!</b>", parse_mode="HTML", reply_markup=chat_user_menu)
    except: pass

async def close_chat_func(admin_id, user_id, user_text, admin_text):
    if admin_id in active_chats: del active_chats[admin_id]
    if user_id in active_chats: del active_chats[user_id]
    
    try: await bot.send_message(user_id, user_text, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    try: await bot.send_message(admin_id, admin_text, parse_mode="HTML", reply_markup=admin_panel_kb)
    except: pass

@dp.message(F.text == "Номер встал")
async def admin_set_hold(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return
    user_id = get_current_chat_user(m.from_user.id)
    if not user_id: return await m.answer("Нет чата.")
    
    hold_end = datetime.now() + timedelta(minutes=HOLD_TIME_MIN)
    with get_conn() as conn:
        conn.execute("UPDATE active_work SET status='hold', hold_until=? WHERE user_id=?", (hold_end, user_id))

    await close_chat_func(
        m.from_user.id, user_id, 
        f"✅ <b>Номер принят в работу!</b>\n"
        f"⏳ Таймер запущен: {HOLD_TIME_MIN} мин.\n\n"
        f"⚠️ <b>ВНИМАНИЕ: НЕ ОТВЯЗЫВАЙТЕ УСТРОЙСТВО!</b>\n"
        f"Даже если кажется, что ничего не происходит, дождитесь выплаты.",
        
        f"✅ Номер отправлен в БезХолд на {HOLD_TIME_MIN} мин.\nЧат закрыт."
    )

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

@dp.message(F.photo)
async def photo_bridge(m: types.Message):
    if m.from_user.id not in ADMIN_IDS: return 
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
        except: await m.answer("❌ Ошибка доставки")
    elif m.from_user.id not in ADMIN_IDS:
        await m.answer("🤖 Используйте меню.", reply_markup=user_menu)

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    asyncio.create_task(cleaner_task())
    print("🚀 Bot VC STARTED")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("Stop")
