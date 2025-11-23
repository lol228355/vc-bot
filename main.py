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
ADMIN_IDS = [8227071592, 8340396727] 
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi"
QUEUE_TIMEOUT_MIN = 15  # Время жизни заявки в минутах
WARNING_TIME_MIN = 5    # Время предупреждения до таймаута в минутах
DB_NAME = "bot_vc.db"    

IS_WORK_ACTIVE = True
LAST_WARNINGS = {} # Словарь для отслеживания отправленных предупреждений

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
active_chats = {} # Словарь для активных диалогов (user_id: admin_id)

def init_db():
    """Инициализация базы данных и создание таблиц."""
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
        # Попытка добавить столбец, если его нет (для обратной совместимости)
        try: cur.execute("ALTER TABLE users ADD COLUMN mute_until TIMESTAMP")
        except: pass
        conn.commit()

init_db()

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_ban_status(uid):
    """Получить статус бана пользователя."""
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (uid,)).fetchone()
        return res[0] if res else 0

def set_ban_status(uid, status):
    """Установить статус бана пользователя (1 - бан, 0 - разбан)."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, ?)", (uid, status))
        conn.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (status, uid))
        conn.commit()

def set_mute(uid, hours=24):
    """Установить мут пользователю на указанное количество часов."""
    expiry = datetime.now() + timedelta(hours=hours)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id, is_banned) VALUES (?, 0)", (uid,))
        conn.execute("UPDATE users SET mute_until = ? WHERE user_id = ?", (expiry, uid))
        conn.commit()

def check_mute(uid):
    """Проверить, находится ли пользователь в муте. Возвращает (True/False, оставшееся время)."""
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT mute_until FROM users WHERE user_id = ?", (uid,)).fetchone()
        if res and res[0]:
            try:
                # Попытка преобразования из ISO-формата
                mute_until = datetime.fromisoformat(res[0])
            except:
                # Fallback для старых форматов
                try: mute_until = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S.%f")
                except: mute_until = datetime.strptime(res[0], "%Y-%m-%d %H:%M:%S")

            if mute_until > datetime.now():
                rem = mute_until - datetime.now()
                h, r = divmod(rem.seconds, 3600)
                m, _ = divmod(r, 60)
                return True, f"{h}ч {m}мин"
    return False, ""

def add_to_queue(uid, numbers):
    """Добавить или обновить заявку в очереди."""
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("REPLACE INTO queue (user_id, numbers, ts) VALUES (?, ?, CURRENT_TIMESTAMP)", (uid, "\n".join(numbers)))
        conn.commit()

def update_timestamp(uid):
    """Обновить метку времени активности заявки."""
    with sqlite3.connect(DB_NAME) as conn:
        cur = conn.cursor()
        cur.execute("UPDATE queue SET ts = CURRENT_TIMESTAMP WHERE user_id = ?", (uid,))
        conn.commit()
        return cur.rowcount > 0

def get_user_queue(uid):
    """Получить заявку пользователя и ID записи."""
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT numbers, id FROM queue WHERE user_id = ?", (uid,)).fetchone()

def get_all_queue():
    """Получить все активные заявки."""
    with sqlite3.connect(DB_NAME) as conn:
        return conn.execute("SELECT user_id, numbers FROM queue ORDER BY id ASC").fetchall()

def queue_pos(row_id):
    """Получить позицию заявки в очереди и общее количество."""
    with sqlite3.connect(DB_NAME) as conn:
        pos = conn.execute("SELECT COUNT(*) FROM queue WHERE id <= ?", (row_id,)).fetchone()[0]
        total = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
        return pos, total

async def send_warning(uid, remaining_time):
    """Отправка предупреждения о скором таймауте."""
    try:
        await bot.send_message(
            uid,
            f"⚠️ <b>Внимание!</b> Ваша заявка будет удалена через **{remaining_time} мин** из-за неактивности. Нажмите **✅ Я онлайн**.",
            parse_mode="HTML",
            reply_markup=user_menu
        )
    except Exception as e:
        logging.error(f"Не удалось отправить предупреждение пользователю {uid}: {e}")

async def cleaner_task():
    """Фоновая задача для очистки очереди по таймауту и отправки предупреждений."""
    while True:
        await asyncio.sleep(60) # Проверка каждую минуту
        try:
            with sqlite3.connect(DB_NAME) as conn:
                # 1. Проверка на таймаут и удаление
                expired = conn.execute(f"SELECT user_id FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes')").fetchall()
                if expired:
                    conn.execute(f"DELETE FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes')")
                    conn.commit()
                    for (uid,) in expired:
                        LAST_WARNINGS.pop(uid, None) # Удаляем из списка предупреждений
                        try: 
                            # Уведомление об удалении
                            await bot.send_message(uid, f"⚠️ <b>Тайм-аут.</b> Заявка удалена.", parse_mode="HTML", reply_markup=user_menu)
                        except Exception as e:
                            logging.error(f"Не удалось уведомить пользователя {uid} об удалении: {e}")

                # 2. Проверка на необходимость предупреждения
                warning_time = QUEUE_TIMEOUT_MIN - WARNING_TIME_MIN
                if warning_time > 0:
                    # Выбираем записи, которым осталось (0, WARNING_TIME_MIN] минут
                    rows_to_warn = conn.execute(
                        f"SELECT user_id FROM queue WHERE ts > datetime('now', '-{QUEUE_TIMEOUT_MIN} minutes') AND ts < datetime('now', '-{warning_time} minutes')"
                    ).fetchall()
                    
                    for (uid,) in rows_to_warn:
                        if uid not in LAST_WARNINGS:
                            await send_warning(uid, WARNING_TIME_MIN)
                            LAST_WARNINGS[uid] = datetime.now() # Помечаем, что предупреждение отправлено
        except Exception as e:
            logging.error(f"Ошибка в cleaner_task: {e}")

# --- ФИЛЬТРЫ ---
class BannedFilter(BaseFilter):
    """Фильтр для заблокированных пользователей."""
    async def __call__(self, m: types.Message) -> bool: return get_ban_status(m.from_user.id) == 1
class AdminFilter(BaseFilter):
    """Фильтр для администраторов."""
    async def __call__(self, m: types.Message) -> bool: return m.from_user.id in ADMIN_IDS

# --- КЛАВИАТУРЫ ---
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

info_btn = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📂 Выплаты", url=PAYOUT_CHANNEL)]
])

# --- СОСТОЯНИЯ FSM ---
class AdminStates(StatesGroup): waiting_ban_id = State(); waiting_mute_id = State()
class UserStates(StatesGroup): waiting_numbers = State()

# --- ЛОГИКА ОБРАБОТЧИКОВ ---

@dp.message(BannedFilter())
async def banned(m: types.Message):
    """Обработчик для заблокированных пользователей."""
    await m.answer("⛔ <b>Вы заблокированы.</b>", parse_mode="HTML")

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin"), AdminFilter())
async def adm(m: types.Message):
    """Команда /admin."""
    await m.answer(f"🔧 <b>Админка (ВЦ)</b>\nСтатус: {'🟢 ON' if IS_WORK_ACTIVE else '🔴 OFF'}", reply_markup=admin_panel_kb, parse_mode="HTML")
    
@dp.message(F.text == "⬅️ Выход", AdminFilter())
async def ex(m: types.Message):
    """Выход из админки."""
    await m.answer("Выход.", reply_markup=user_menu)

@dp.message(F.text == "🟢 START WORK", AdminFilter())
async def sw(m: types.Message):
    """Включение работы."""
    global IS_WORK_ACTIVE
    IS_WORK_ACTIVE=True
    await m.answer("✅ Ворк ON", reply_markup=admin_panel_kb)

@dp.message(F.text == "🔴 STOP WORK", AdminFilter())
async def stw(m: types.Message):
    """Остановка работы."""
    global IS_WORK_ACTIVE
    IS_WORK_ACTIVE=False
    await m.answer("🛑 Ворк OFF", reply_markup=admin_panel_kb)

@dp.message(F.text == "📋 Очередь", AdminFilter())
async def qlist(m: types.Message):
    """Просмотр очереди."""
    rows = get_all_queue()
    if not rows: return await m.answer("📭 Пусто")
    
    await m.answer(f"📋 Заявок: {len(rows)}")
    for uid, nums in rows:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ПРИНЯТЬ", callback_data=f"take_{uid}")]])
        # Показываем только первый номер для краткости
        await m.answer(f"👤 <code>{uid}</code>\n📞 {html.escape(nums.splitlines()[0])}", reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "🔨 Бан", AdminFilter())
async def ban_s(m: types.Message, state: FSMContext):
    """Начало процесса бана/разбана."""
    await state.set_state(AdminStates.waiting_ban_id)
    await m.answer("ID для бана:")

@dp.message(AdminStates.waiting_ban_id)
async def ban_f(m: types.Message, state: FSMContext):
    """Завершение процесса бана/разбана."""
    try:
        uid = int(m.text)
        current_status = get_ban_status(uid)
        new_status = 1 if current_status == 0 else 0
        set_ban_status(uid, new_status)
        
        if new_status: 
            # Удаляем из очереди, если забанен
            with sqlite3.connect(DB_NAME) as conn:
                conn.execute("DELETE FROM queue WHERE user_id=?",(uid,))
                conn.commit()
            LAST_WARNINGS.pop(uid, None)
            
        await m.answer(f"ID {uid}: {'Бан' if new_status else 'Разбан'}", reply_markup=admin_panel_kb)
    except Exception as e:
        logging.error(f"Ошибка бана: {e}")
        await m.answer("❌ Ошибка ID")
    finally:
        await state.clear()

@dp.message(F.text == "🤐 Мут (24ч)", AdminFilter())
async def mut_s(m: types.Message, state: FSMContext):
    """Начало процесса мута."""
    await state.set_state(AdminStates.waiting_mute_id)
    await m.answer("ID для мута:")
    
@dp.message(AdminStates.waiting_mute_id)
async def mut_f(m: types.Message, state: FSMContext):
    """Завершение процесса мута."""
    try:
        uid = int(m.text)
        set_mute(uid)
        # Удаляем из очереди, если наложен мут
        with sqlite3.connect(DB_NAME) as conn:
            conn.execute("DELETE FROM queue WHERE user_id=?",(uid,))
            conn.commit()
        LAST_WARNINGS.pop(uid, None)
        await m.answer(f"ID {uid} в муте на 24ч.", reply_markup=admin_panel_kb)
    except Exception as e:
        logging.error(f"Ошибка мута: {e}")
        await m.answer("❌ Ошибка ID")
    finally:
        await state.clear()

# --- ПОЛЬЗОВАТЕЛЬСКАЯ ЛОГИКА ---

@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    """Команда /start."""
    await state.clear()
    
    # Проверка активного диалога
    if m.from_user.id in active_chats: 
        return await m.answer("⚠️ Вы в чате.", reply_markup=chat_user_menu)
    
    st = "" if IS_WORK_ACTIVE else "🛑 <b>СТОП ВОРК: Прием приостановлен.</b>\n"
    r = get_user_queue(m.from_user.id)
    inf = f"\n\n📊 Ваша позиция: {queue_pos(r[1])[0]}/{queue_pos(r[1])[1]}" if r else ""
    
    msg = f"""<b>💎 AndronWork | ВЦ</b>
{st}
Привет, **{m.from_user.first_name}**!
Добро пожаловать в рабочую систему по приему аккаунтов.

---
💵 Оплата: **5$ за аккаунт.**
⏳ Таймер активности: БезХолд **{QUEUE_TIMEOUT_MIN} мин.** (Необходимо подтверждать присутствие).
🚀 Канал с выплатами: [Указан в кнопке "💰 Условия и выплаты"]
---

### 💡 Как начать работу:
1. Нажми **"✨ Новая заявка"**.
2. Отправь **список номеров** (один номер = один аккаунт).
3. Следи за очередью и регулярно жми **"✅ Я онлайн"**, чтобы не потерять место.
4. Дождись, когда Админ подключится к твоему чату.
{inf}
"""
    await m.answer(msg, reply_markup=user_menu, parse_mode="HTML")

@dp.message(F.text == "✅ Я онлайн (Обновить таймер)")
async def here(m: types.Message):
    """Обновление таймера активности в очереди."""
    if update_timestamp(m.from_user.id):
        # Удаляем из предупреждений, так как активность подтверждена
        LAST_WARNINGS.pop(m.from_user.id, None)
        r = get_user_queue(m.from_user.id)
        p, t = queue_pos(r[1])
        await m.answer(f"🔄 Таймер обновлен. Вы в очереди: **{p}/{t}**", parse_mode="HTML")
    else: 
        await m.answer("⚠️ Нет заявки. Отправьте новую, чтобы встать в очередь.", reply_markup=user_menu)

@dp.message(F.text == "💰 Условия и выплаты")
async def info(m: types.Message): 
    """Информация об условиях и выплатах."""
    await m.answer(f"<b>Инфо ВЦ</b>\nСтавка: 5$ за аккаунт\nТаймер: БезХолд {QUEUE_TIMEOUT_MIN} мин\n\nВыплаты проводятся после Стоп-Ворка.", parse_mode="HTML", reply_markup=info_btn)
    
@dp.message(F.text == "📍 Моя позиция")
async def my(m: types.Message):
    """Позиция пользователя в очереди."""
    r = get_user_queue(m.from_user.id)
    if r: 
        p,t = queue_pos(r[1])
        # Показываем только первый номер из заявки
        first_number = r[0].splitlines()[0]
        await m.answer(f"📞 Номер: <code>{first_number}</code>\n📍 Позиция: **{p}/{t}**", parse_mode="HTML")
    else: 
        await m.answer("📭 Пусто")

@dp.message(F.text == "✨ Новая заявка")
async def sub(m: types.Message, state: FSMContext):
    """Начало подачи новой заявки."""
    mt, tm = check_mute(m.from_user.id)
    if mt: return await m.answer(f"🤐 Мут еще **{tm}**")
    if not IS_WORK_ACTIVE: return await m.answer("🔴 Ворк стоп.")
    if m.from_user.id in active_chats: return await m.answer("⚠️ Заверши чат перед подачей новой заявки.", reply_markup=chat_user_menu)
    
    # Сразу удаляем из очереди, если уже есть, перед началом новой
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM queue WHERE user_id=?",(m.from_user.id,))
        conn.commit()
    LAST_WARNINGS.pop(m.from_user.id, None)
    
    await state.set_state(UserStates.waiting_numbers)
    await m.answer("📝 Кидай номера списком (каждый номер с новой строки):")

@dp.message(UserStates.waiting_numbers)
async def proc(m: types.Message, state: FSMContext):
    """Обработка списка номеров."""
    # Регулярное выражение для номера телефона (с опциональными +7/7/8 и 10 цифрами)
    nums = [x.strip() for x in m.text.splitlines() if re.match(r"^(\+7|7|8)?\d{10}$", x.strip())]
    
    if not nums: 
        return await m.answer("❌ Нет номеров или они не соответствуют формату. Попробуй снова.")
        
    add_to_queue(m.from_user.id, nums)
    await state.clear()
    
    # Уведомление администраторов
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚡️ ПРИНЯТЬ", callback_data=f"take_{m.from_user.id}")]])
    txt = f"🚨 <b>ВЦ ЗАЯВКА</b>\n👤 {html.escape(m.from_user.full_name)} (<code>{m.from_user.id}</code>)\n📞:\n{html.escape(m.text)}"
    
    for a in ADMIN_IDS: 
        try: await bot.send_message(a, txt, reply_markup=kb, parse_mode="HTML")
        except: pass
        
    await m.answer(f"✅ Принято. Вы в очереди. Жми **✅ Я онлайн** каждые {QUEUE_TIMEOUT_MIN} мин (БезХолд).", reply_markup=user_menu)

# --- ЛОГИКА ДИАЛОГОВ И CALLBACKS ---

@dp.callback_query(F.data.startswith("take_"))
async def take(c: types.CallbackQuery):
    """Админ принимает заявку."""
    uid = int(c.data.split("_")[1])
    # Проверка, занят ли пользователь или админ
    if uid in active_chats or c.from_user.id in active_chats: 
        return await c.answer("❌ Занято")
    
    # Начинаем чат
    active_chats[uid] = c.from_user.id
    active_chats[c.from_user.id] = uid
    
    # Удаляем запись из очереди (теперь она в активном чате)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM queue WHERE user_id=?",(uid,))
        conn.commit()
    LAST_WARNINGS.pop(uid, None)

    await c.message.edit_reply_markup(None)
    await c.message.answer(f"✅ Чат с <code>{uid}</code>.", reply_markup=chat_admin_menu, parse_mode="HTML")
    try: 
        await bot.send_message(uid, "👨‍💻 Админ тут.", reply_markup=chat_user_menu)
    except Exception as e:
        logging.error(f"Не удалось уведомить пользователя {uid} о начале чата: {e}")
        await c.message.answer(f"❌ Не удалось уведомить пользователя <code>{uid}</code>.", parse_mode="HTML")

async def close(aid, uid, ut, at):
    """Закрытие активного диалога."""
    if aid in active_chats: del active_chats[aid]
    if uid in active_chats: del active_chats[uid]
    
    # Отправка сообщений пользователю и админу с обновлением клавиатур
    try: await bot.send_message(uid, ut, parse_mode="HTML", reply_markup=user_menu)
    except: pass
    try: await bot.send_message(aid, at, parse_mode="HTML", reply_markup=admin_panel_kb)
    except: pass

@dp.message(F.text == "💰 Номер взят")
async def done(m: types.Message):
    """Админ завершает чат (аккаунт принят)."""
    if m.from_user.id not in ADMIN_IDS: return
    
    uid = active_chats.get(m.from_user.id)
    if not uid: return await m.answer("Нет чата", reply_markup=admin_panel_kb)
    
    # Удаление из очереди (для подстраховки)
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("DELETE FROM queue WHERE user_id=?",(uid,))
        conn.commit()
        
    msg = f"✅ <b>ПРИНЯТО (ВЦ)</b>\n💰 Выплата после стоп-ворка: <a href='{PAYOUT_CHANNEL}'>КАНАЛ</a>"
    await close(m.from_user.id, uid, msg, "💸 Готово.")

@dp.message(F.text == "🔒 Закончить чат")
async def stopc(m: types.Message):
    """Завершение чата (кем угодно)."""
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)
    
    if not partner_id: 
        return await m.answer("Чат закрыт", reply_markup=admin_panel_kb if sender_id in ADMIN_IDS else user_menu)
    
    # Определяем, кто админ, а кто пользователь
    if sender_id in ADMIN_IDS:
        adm, usr = sender_id, partner_id
        user_msg = "🔒 Админ закрыл чат."
        admin_msg = "🔒 Чат закрыт."
    else:
        adm, usr = partner_id, sender_id
        user_msg = "🔒 Вы закрыли чат."
        admin_msg = f"🔒 Пользователь <code>{usr}</code> закрыл чат."
        
    await close(adm, usr, user_msg, admin_msg)

@dp.message()
async def brg(m: types.Message):
    """Функция-мост для пересылки сообщений в активном чате."""
    if m.text and m.text.startswith("/"): return # Игнорируем команды
    
    partner_id = active_chats.get(m.from_user.id)
    
    if partner_id: 
        # Пересылка сообщения
        try: await m.copy_to(partner_id)
        except: await m.answer("❌ Ошибка")
    elif m.from_user.id not in ADMIN_IDS: 
        # Если нет активного чата и это не админ
        await m.answer("🤖 Используй меню.", reply_markup=user_menu)

# --- ЗАПУСК БОТА ---
async def main():
    """Основная функция запуска бота."""
    # Запуск фоновой задачи очистки
    asyncio.create_task(cleaner_task())
    
    # Удаление вебхуков и запуск long polling
    await bot.delete_webhook(drop_pending_updates=True) 
    print("🚀 Bot VC Started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped by KeyboardInterrupt")
    except Exception as e:
        print(f"🛑 Critical error: {e}")
