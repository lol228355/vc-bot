import asyncio, logging, sqlite3, re, html
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- КОНСТАНТЫ ---
# ВАЖНО: ЗАМЕНИТЕ ЭТО НА СВОЙ ТОКЕН И ID
TOKEN = "8449633779:AAGzj1Es07rBCxH_xcm_sG0F_tRjqAUWvVY" 
ADMIN_IDS = [8448843727, 8227071592] # Ваши ID администраторов
PAYOUT_CHANNEL = "https://t.me/+nTCkyUL-ycUxNGFi" # Ссылка на канал с выплатами

# Инициализация
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# active_chats: {user_id: admin_id, admin_id: user_id} - связывает партнера и админа в двустороннем чате
active_chats = {} 

# --- БАЗА ДАННЫХ ---
DB_NAME = "bot.db"
QUEUE_TIMEOUT_MINUTES = 16

def init_db():
    """Инициализация базы данных и создание таблицы очереди."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE, -- Уникальность, чтобы один юзер = одна заявка
                numbers TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
            conn.commit()
        logging.info("База данных инициализирована.")
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")

init_db()

def add_to_queue(uid, numbers):
    """Добавляет или обновляет заявку пользователя в очереди."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            # Используем REPLACE INTO для обновления, если user_id уже существует (лучше, чем DELETE+INSERT)
            cur.execute("""REPLACE INTO queue (user_id, numbers) VALUES (?, ?)""", 
                        (uid, "\n".join(numbers)))
            conn.commit()
    except Exception as e:
        logging.error(f"Ошибка добавления в очередь: {e}")

def get_user_numbers_and_id(uid):
    """Получает номера и ID записи пользователя в очереди за последние 16 минут."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(f"""SELECT numbers, id FROM queue 
                            WHERE user_id = ? AND ts > datetime('now', '-{QUEUE_TIMEOUT_MINUTES} minutes') 
                            ORDER BY id DESC LIMIT 1""", (uid,))
            return cur.fetchone()
    except Exception as e:
        logging.error(f"Ошибка получения номеров пользователя: {e}")
        return None

def queue_position(my_id):
    """Определяет позицию заявки в очереди."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            # Считаем количество записей, которые старше или равны нашей, и не протухли
            cur.execute(f"""SELECT COUNT(*) FROM queue WHERE id <= ? AND ts > datetime('now', '-{QUEUE_TIMEOUT_MINUTES} minutes')""", (my_id,))
            pos = cur.fetchone()[0]
            # Считаем общее количество активных записей
            cur.execute(f"""SELECT COUNT(*) FROM queue WHERE ts > datetime('now', '-{QUEUE_TIMEOUT_MINUTES} minutes')""")
            total = cur.fetchone()[0]
            return pos, total
    except Exception as e:
        logging.error(f"Ошибка определения позиции в очереди: {e}")
        return 0, 0

def clean_old():
    """Удаляет просроченные заявки из очереди."""
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM queue WHERE ts < datetime('now', '-{QUEUE_TIMEOUT_MINUTES} minutes')")
            if cur.rowcount > 0:
                logging.info(f"Удалено {cur.rowcount} просроченных заявок.")
            conn.commit()
    except Exception as e:
        logging.error(f"Ошибка очистки старых записей: {e}")

async def cleaner_task():
    """Фоновая задача для периодической очистки очереди."""
    while True:
        await asyncio.sleep(180) # Каждые 3 минуты
        clean_old()

# --- КЛАВИАТУРЫ ---
user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📱 Сдать номера"), KeyboardButton(text="📊 Мои номера")],
    [KeyboardButton(text="✅ Я тут"), KeyboardButton(text="❓ Инфо")]
], resize_keyboard=True, one_time_keyboard=False)

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="💰 Номер взят"), KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True, one_time_keyboard=False)

payout_btn = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="💸 Отчёты и выплаты в канале", url=PAYOUT_CHANNEL)
]])

# Клавиатура для пользователя при начале чата с админом (чтобы мог закрыть чат)
chat_user_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔒 Закончить чат")]
], resize_keyboard=True, one_time_keyboard=False)


# --- ХЭНДЛЕРЫ ---

class NumbersState(StatesGroup):
    waiting = State()

@dp.message(Command("start"))
async def start(m: types.Message, state: FSMContext):
    """Обработка команды /start."""
    await state.clear()
    
    # Если пользователь в чате с админом, не сбрасываем, просто уведомляем
    if m.from_user.id in active_chats:
        await m.answer("⚠️ Вы уже в активном чате с администратором. Чтобы выйти, нажмите «🔒 Закончить чат».", 
                       reply_markup=chat_user_menu)
        return
        
    row = get_user_numbers_and_id(m.from_user.id)
    queue_info = ""
    if row:
        pos, total = queue_position(row[1])
        queue_info = f"\n\n👉 Твоя заявка активна: <b>#{pos}</b> из <b>{total}</b>"

    await m.answer(f"""
    
    💎 <b>AndronWork | Привет, {html.escape(m.from_user.first_name)}!</b> 👋

    ✨ **ВЦ по 5$ — 16 минут — без холда**
    
    🚀 **Быстрые и честные выплаты гарантированы.**
    
    ⏰ Чтобы твоя заявка была активна, жми **«✅ Я тут»** каждые **{QUEUE_TIMEOUT_MINUTES} минут**!
    {queue_info}
    """,
        reply_markup=user_menu, 
        parse_mode="HTML")

@dp.message(F.text == "❓ Инфо")
async def info_handler(m: types.Message):
    """Вывод информационного сообщения."""
    await m.answer(f"""
    
    💡 **Информация о работе:**
    
    💰 **Ставка:** 5$ за ВЦ.
    ⏳ **Время холда:** 16 минут (никакого долгого ожидания!).
    
    **Как работать?**
    1. Жми **«📱 Сдать номера»**.
    2. Вводи номера (по одному на строку) и отправляй.
    3. Твоя заявка попадает в очередь.
    4. **Важно:** Жми **«✅ Я тут»** каждые **{QUEUE_TIMEOUT_MINUTES} минут**, чтобы твоя заявка оставалась активной.
    5. Как только админ возьмет заявку, ты получишь уведомление.
    
    *Мы ценим твоё время и предлагаем лучшие условия!*
    
    """, parse_mode="HTML", reply_markup=payout_btn)


@dp.message(F.text == "✅ Я тут")
async def im_here(m: types.Message):
    """Обновление статуса в очереди."""
    row = get_user_numbers_and_id(m.from_user.id)
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ Вы в чате с админом. Не нужно нажимать «Я тут»!")

    if row:
        pos, total = queue_position(row[1])
        await m.answer(f"🟢 **Ты в сети!** Твоя заявка активна.\n🎯 Место в очереди: **#{pos} из {total}**.", parse_mode="HTML")
    else:
        await m.answer("🟢 **Ты в сети!** Нажми **«📱 Сдать номера»** для начала работы.", reply_markup=user_menu)

@dp.message(F.text == "📊 Мои номера")
async def my_numbers(m: types.Message):
    """Просмотр активных номеров в очереди."""
    row = get_user_numbers_and_id(m.from_user.id)
    
    if not row:
        return await m.answer("❌ **Номеров в активной очереди нет**.\n\nНажми **«📱 Сдать номера»**, чтобы начать.", parse_mode="HTML")
    
    numbers_list = row[0].replace("\n", "\n")
    pos, total = queue_position(row[1])
    await m.answer(f"""
    
    📊 **Твои номера в очереди**
    
    📞 Номера:
    <code>{html.escape(numbers_list)}</code>
    
    🎯 **Позиция в очереди:** **#{pos}** из **{total}**
    
    *Помни про {QUEUE_TIMEOUT_MINUTES} минут!*
    
    """, parse_mode="HTML")

@dp.message(F.text == "📱 Сдать номера")
async def ask_numbers(m: types.Message, state: FSMContext):
    """Запрос на ввод номеров."""
    if m.from_user.id in active_chats:
        return await m.answer("⚠️ Ты уже в чате с админом. Дождитесь завершения текущего чата или нажмите **«🔒 Закончить чат»**.", reply_markup=chat_user_menu)
        
    await state.set_state(NumbersState.waiting)
    await m.answer("""
    
    📲 **Введи номера!**
    
    Кидай номера по одному на строку. Мы поддерживаем российские форматы:
    
    Пример:
    <code>+79991234567
    89991234567
    79991234567</code>
    
    """, parse_mode="HTML")

@dp.message(NumbersState.waiting)
async def receive_numbers(m: types.Message, state: FSMContext):
    """Прием и обработка номеров от пользователя."""
    
    # Регулярное выражение для российских номеров: +7, 7, или 8, далее 10 цифр
    num_pattern = re.compile(r"^(\+7|7|8)?\d{10}$")
    nums = [x.strip() for x in m.text.splitlines() if num_pattern.match(x.strip())]
    
    if not nums:
        return await m.answer("❌ **Не найдено валидных номеров**.\n\nПожалуйста, используй формат: `+79991234567` или `89991234567`", parse_mode="HTML")

    # Добавляем (или обновляем) заявку в очередь
    add_to_queue(m.from_user.id, nums)
    await state.clear()

    # Уведомление для админов
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎯 Взять в работу", callback_data=f"take_{m.from_user.id}")
    ]])
    
    text = f"""
    
    🔔 **🚀 AndronWork | НОВАЯ ЗАЯВКА**
    
    👤 От: <a href='tg://user?id={m.from_user.id}'>{html.escape(m.from_user.first_name)}</a>
    🆔 ID: <code>{m.from_user.id}</code>
    
    📞 Номера:
    <code>{html.escape('\n'.join(nums))}</code>
    
    """

    for admin in ADMIN_IDS:
        try: 
            await bot.send_message(admin, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e: 
            logging.error(f"Не удалось отправить уведомление админу {admin}: {e}")

    await m.answer("✅ **Заявка успешно добавлена в очередь!**\n\n*Админ скоро её возьмет. Не забывай нажимать **«✅ Я тут»**!*", 
                   reply_markup=user_menu, parse_mode="HTML")

@dp.callback_query(F.data.startswith("take_"))
async def take_order(cb: types.CallbackQuery):
    """Обработка кнопки 'Взять в работу' от админа."""
    
    # Проверка, что только админы могут нажимать
    if cb.from_user.id not in ADMIN_IDS:
        return await cb.answer("❌ Вы не администратор.", show_alert=True)
        
    uid = int(cb.data.split("_")[1])
    
    if uid in active_chats:
        return await cb.answer("❌ Эта заявка уже в работе!", show_alert=True)
    
    # Устанавливаем чат
    active_chats[uid] = cb.from_user.id
    active_chats[cb.from_user.id] = uid

    try:
        # Убираем кнопку "Взять"
        await cb.message.edit_reply_markup(reply_markup=None)
        await cb.message.edit_text(cb.message.html_text + f"\n\n👨‍💼 **Взял в работу:** <a href='tg://user?id={cb.from_user.id}'>{html.escape(cb.from_user.first_name)}</a>", 
                                   parse_mode="HTML")
                                   
        # Уведомляем админа
        await bot.send_message(cb.from_user.id, f"💬 **Чат с пользователем {uid} открыт.**", reply_markup=admin_menu)
        
        # Уведомляем пользователя
        await bot.send_message(uid, "👨‍💼 **Админ на связи!** Мы уже работаем с твоей заявкой. Для общения просто пиши сюда.", 
                               reply_markup=chat_user_menu)
                               
        await cb.answer("✅ Вы взяли заявку! Чат открыт.")
        logging.info(f"Админ {cb.from_user.id} взял заявку {uid}.")
        
    except Exception as e:
        logging.error(f"Ошибка при открытии чата: {e}")
        # Откатываем чат при ошибке
        active_chats.pop(uid, None)
        active_chats.pop(cb.from_user.id, None)
        await cb.answer("❌ Произошла ошибка при открытии чата.", show_alert=True)

async def _close_chat_procedure(user_id, admin_id, final_message_user, final_message_admin, user_menu_final):
    """Универсальная процедура закрытия чата."""
    
    # Сначала удаляем из active_chats
    active_chats.pop(user_id, None)
    active_chats.pop(admin_id, None)
    
    # Уведомляем пользователя
    try:
        await bot.send_message(user_id, final_message_user, 
                               reply_markup=user_menu_final, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
        
    # Уведомляем админа
    try:
        await bot.send_message(admin_id, final_message_admin, 
                               reply_markup=admin_menu, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Не удалось отправить сообщение админу {admin_id}: {e}")

@dp.message(F.text == "💰 Номер взят")
async def number_taken(m: types.Message):
    """Завершение чата и уведомление о выплате (только для админа)."""
    if m.from_user.id not in ADMIN_IDS:
        return # Не админ, игнорируем
        
    admin_id = m.from_user.id
    user_id = active_chats.get(admin_id)
    
    if not user_id:
        return await m.answer("❌ Нет активного чата для завершения.")
    
    # 1. Удаляем заявку из очереди (подразумеваем успешную выплату)
    try:
        with sqlite3.connect(DB_NAME) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM queue WHERE user_id = ?", (user_id,))
            conn.commit()
    except Exception as e:
        logging.error(f"Ошибка удаления из очереди {user_id}: {e}")
        
    # 2. Закрываем чат и уведомляем
    await _close_chat_procedure(
        user_id,
        admin_id,
        "✅ **Номер принят! Выплата произведена!**\n\n*Можешь сдавать новые номера.*",
        "💸 **Выплата отправлена пользователю.** Чат закрыт.",
        user_menu
    )
    logging.info(f"Чат {admin_id}-{user_id} закрыт. Выплата подтверждена.")


@dp.message(F.text == "🔒 Закончить чат")
async def end_chat(m: types.Message):
    """Завершение чата (может быть инициировано как админом, так и пользователем)."""
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)
    
    if not partner_id:
        # Если нет партнера, просто возвращаем обычное меню, если не админ
        if sender_id not in ADMIN_IDS:
            return await m.answer("🔒 Чат закрыт.", reply_markup=user_menu)
        return await m.answer("❌ Нет активного чата для завершения.", reply_markup=admin_menu)
        
    is_sender_admin = sender_id in ADMIN_IDS
    
    # Определяем, кто есть кто
    admin_id = sender_id if is_sender_admin else partner_id
    user_id = partner_id if is_sender_admin else sender_id
    
    # Закрываем чат и уведомляем
    await _close_chat_procedure(
        user_id,
        admin_id,
        "🔒 **Чат закрыт администратором.**\n\nМожешь сдавать новые номера.",
        "🔒 **Чат закрыт.**",
        user_menu
    )
    logging.info(f"Чат {admin_id}-{user_id} закрыт инициатором {sender_id}.")

@dp.message()
async def bridge(m: types.Message):
    """Хэндлер-мост для пересылки сообщений в активном чате."""
    
    # Игнорируем команды
    if m.text and m.text.startswith("/"): 
        return
        
    sender_id = m.from_user.id
    partner_id = active_chats.get(sender_id)
    
    if partner_id:
        # Проверяем, чтобы админ не мог отправить /start или другое
        if m.text in ["📱 Сдать номера", "📊 Мои номера", "✅ Я тут", "❓ Инфо", "💰 Номер взят", "🔒 Закончить чат"]:
            return # Игнорируем нажатия кнопок во время чата, кроме команды закрытия
            
        try: 
            await m.copy_to(partner_id)
            logging.debug(f"Сообщение от {sender_id} переслано к {partner_id}.")
        except Exception as e: 
            logging.error(f"Ошибка пересылки сообщения от {sender_id} к {partner_id}: {e}")
            await m.answer("❌ Не удалось отправить сообщение. Чат может быть неактивен.")
            
    # Если нет активного чата, просто возвращаем главное меню, если это не админ
    elif sender_id not in ADMIN_IDS:
         await m.answer("❌ Неизвестная команда или нет активной работы. Используй кнопки меню.", reply_markup=user_menu)

async def main():
    """Главная функция запуска бота."""
    try:
        # Запускаем фоновую задачу очистки
        asyncio.create_task(cleaner_task())
        
        # Удаляем вебхук и запускаем long polling
        await bot.delete_webhook(drop_pending_updates=True)
        print("🚀 AndronWork — САМОЕ КРАСИВОЕ ОФОРМЛЕНИЕ 2025 — запущено! 💎")
        logging.info("Бот запущен.")
        await dp.start_polling(bot)
    except Exception as e:
        logging.critical(f"Критическая ошибка в main: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот остановлен вручную.")
