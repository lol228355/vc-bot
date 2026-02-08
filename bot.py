import logging
import asyncio
import random
import aiosqlite
import time
import requests
import json
from datetime import datetime
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiocryptopay import AioCryptoPay

# ⚙️ КОНФИГУРАЦИЯ
BOT_TOKEN = "8295201485:AAGFxmaC584b75hJrTFAMukvXs7da3L7hAE"
CRYPTO_PAY_TOKEN = "514479:AAb64Swo8pexGV3iVkgI4MqdlYYsg22BhOZ"
ADMIN_IDS = [8119723042, 8448843727]  # Обновленные ID админов
MIN_BET = 0.1
MIN_DEPOSIT = 0.1
MIN_WITHDRAW = 0.1
BONUS_AMOUNT = 0.05
REFERRAL_REWARD = 0.1
REQUIRED_BIO_TEXT = "@Andcasino_bot_bot лучший бот для игр на $ с шансом 80% победы"

# Убрана система скрытых шансов для новичков

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN)
dp = Dispatcher()
DB_NAME = "andron_casino.db"

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С CRYPTOBOT API ---
CRYPTO_API_URL = "https://pay.crypt.bot/api/"
CRYPTO_HEADERS = {
    "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
    "Content-Type": "application/json"
}

async def create_crypto_check(amount: float):
    """Создать чек (выходящий платеж/выплата) через CryptoBot API"""
    url = f"{CRYPTO_API_URL}createCheck"
    payload = {
        "asset": "USDT",
        "amount": str(amount)
        # Убрано поле "pin_to_user_id": None - оно не требуется для обычных чеков
    }
    
    try:
        response = requests.post(url, headers=CRYPTO_HEADERS, json=payload)
        response.raise_for_status()
        res = response.json()
        
        logging.info(f"CryptoBot API response: {res}")
        
        if res.get("ok"):
            return {
                "success": True,
                "check_url": res["result"]["bot_check_url"],
                "check_id": res["result"].get("check_id")
            }
        else:
            error_msg = res.get("error", {})
            if isinstance(error_msg, dict):
                error_msg = error_msg.get("name", str(error_msg))
            return {
                "success": False,
                "error": error_msg
            }
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при создании чека (сетевые проблемы): {e}")
        return {
            "success": False,
            "error": f"Сетевые проблемы: {str(e)}"
        }
    except Exception as e:
        logging.error(f"Ошибка при создании чека: {e}")
        return {
            "success": False,
            "error": str(e)
        }

# --- СОСТОЯНИЯ ---
class States(StatesGroup):
    waiting_for_captcha = State()
    waiting_for_bet = State()
    waiting_for_turn = State()
    waiting_for_withdraw = State()
    waiting_for_deposit = State()
    admin_giving_balance = State()
    admin_manage_ban = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                username TEXT, 
                balance REAL DEFAULT 0.0,
                last_bonus INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                referrer_id INTEGER DEFAULT 0,
                referral_paid INTEGER DEFAULT 0,
                total_deposited REAL DEFAULT 0.0,
                total_withdrawn REAL DEFAULT 0.0,
                total_bets REAL DEFAULT 0.0,
                created_at INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0
            )
        """)
        
        # Таблица транзакций (пополнения и выводы)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT, -- 'deposit' или 'withdraw'
                amount REAL,
                status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'failed'
                invoice_id TEXT,
                check_id TEXT,
                created_at INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)
        
        await db.commit()

async def update_db_schema():
    """Обновляет схему базы данных, добавляя недостающие колонки"""
    async with aiosqlite.connect(DB_NAME) as db:
        # Проверяем, существует ли колонка check_id в таблице transactions
        cursor = await db.execute("PRAGMA table_info(transactions)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        # Добавляем колонку check_id, если её нет
        if 'check_id' not in column_names:
            await db.execute("ALTER TABLE transactions ADD COLUMN check_id TEXT")
            logging.info("Добавлена колонка check_id в таблицу transactions")
        
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            columns = [column[0] for column in cursor.description]
            row = await cursor.fetchone()
            if row:
                # Создаем словарь с именованными полями
                user_dict = {}
                for i, column in enumerate(columns):
                    user_dict[column] = row[i]
                return user_dict
            return None

async def update_total_bets(user_id, bet_amount):
    """Обновляет сумму всех ставок пользователя"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET total_bets = total_bets + ? WHERE user_id = ?", 
                        (bet_amount, user_id))
        await db.commit()

async def is_user_banned(user_id):
    u = await get_user(user_id)
    return u and u.get('is_banned', 0) == 1

async def increment_games_played(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET games_played = games_played + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def check_referral_reward(user_id):
    """Проверяет, нужно ли начислить реферальное вознаграждение"""
    user = await get_user(user_id)
    if not user or user.get('referrer_id', 0) == 0 or user.get('referral_paid', 0) == 1:
        return False
    
    # Проверяем, сыграл ли реферал хотя бы в одну игру
    if user.get('games_played', 0) > 0:
        referrer_id = user.get('referrer_id', 0)
        
        # Начисляем реферальное вознаграждение
        async with aiosqlite.connect(DB_NAME) as db:
            # Начисляем рефереру
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                           (REFERRAL_REWARD, referrer_id))
            # Отмечаем, что реферал получил награду
            await db.execute("UPDATE users SET referral_paid = 1 WHERE user_id = ?", (user_id,))
            await db.commit()
        
        # Уведомляем реферера
        try:
            referrer = await get_user(referrer_id)
            if referrer:
                await bot.send_message(
                    referrer_id,
                    f"🎉 **Реферальная награда!**\n\n"
                    f"Ваш реферал {user.get('username', 'Неизвестно')} сыграл в игры!\n"
                    f"Вы получили: `{REFERRAL_REWARD}$`\n\n"
                    f"💰 Ваш баланс: `{float(referrer.get('balance', 0)) + REFERRAL_REWARD:.2f}$`"
                )
        except Exception as e:
            logging.error(f"Ошибка уведомления реферера: {e}")
        
        return True
    return False

# --- ФУНКЦИИ ДЛЯ ТРАНЗАКЦИЙ ---
async def add_transaction(user_id, trans_type, amount, invoice_id=None, check_id=None, status='pending'):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO transactions (user_id, type, amount, status, invoice_id, check_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, trans_type, amount, status, invoice_id, check_id, int(time.time())))
        await db.commit()

async def update_transaction_status(invoice_id=None, check_id=None, status='completed'):
    async with aiosqlite.connect(DB_NAME) as db:
        if invoice_id:
            await db.execute("UPDATE transactions SET status = ? WHERE invoice_id = ?", (status, str(invoice_id)))
        elif check_id:
            await db.execute("UPDATE transactions SET status = ? WHERE check_id = ?", (status, str(check_id)))
        await db.commit()

async def get_transactions(limit=50, trans_type=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?"
        params = [limit]
        
        if trans_type:
            query = "SELECT * FROM transactions WHERE type = ? ORDER BY created_at DESC LIMIT ?"
            params = [trans_type, limit]
        
        cursor = await db.execute(query, params)
        return await cursor.fetchall()

# --- КЛАВИАТУРЫ ---
def main_menu_kb(user_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 ИГРАТЬ", callback_data="menu_games")
    kb.button(text="👤 ПРОФИЛЬ", callback_data="menu_profile")
    kb.button(text="💳 КОШЕЛЕК", callback_data="menu_wallet")
    kb.button(text="🤝 РЕФЕРАЛЫ", callback_data="menu_refs")
    kb.button(text="🎁 БОНУС", callback_data="menu_bonus")
    kb.button(text="ℹ️ ПОМОЩЬ", callback_data="menu_help")
    kb.button(text="📜 ПРАВИЛА", callback_data="menu_rules")
    if user_id in ADMIN_IDS:
        kb.button(text="🔐 АДМИНКА", callback_data="admin_home")
    kb.adjust(1, 2, 2, 2, 1)
    return kb.as_markup()

def admin_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 ВЫДАТЬ БАЛАНС", callback_data="adm_give")
    kb.button(text="🔨 БАН / РАЗБАН", callback_data="adm_ban_menu")
    kb.button(text="📊 ПОПОЛНЕНИЯ", callback_data="adm_deposits")
    kb.button(text="📤 ВЫВОДЫ", callback_data="adm_withdraws")
    kb.button(text="📈 СТАТИСТИКА", callback_data="adm_stats")
    kb.button(text="🔙 НАЗАД", callback_data="start_over")
    kb.adjust(1, 2, 2, 1)
    return kb.as_markup()

# --- СТАРТ И КАПЧА ---
@dp.message(CommandStart())
@dp.callback_query(F.data == "start_over")
async def cmd_start(event: types.Message | types.CallbackQuery, state: FSMContext = None, command: CommandObject = None):
    if state: 
        await state.clear()
    
    if isinstance(event, types.CallbackQuery):
        uid = event.from_user.id
        message = event.message
    else:
        uid = event.from_user.id
        message = event
    
    if await is_user_banned(uid):
        msg = "⛔ **Доступ ограничен. Вы заблокированы администрацией.**"
        if isinstance(event, types.CallbackQuery):
            await event.message.edit_text(msg, parse_mode="Markdown")
        else:
            await event.answer(msg, parse_mode="Markdown")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_verified FROM users WHERE user_id = ?", (uid,))
        row = await cursor.fetchone()
        if not row:
            ref = 0
            if isinstance(event, types.Message) and command and command.args and command.args.isdigit():
                ref = int(command.args)
            await db.execute("""
                INSERT INTO users (user_id, username, referrer_id, created_at) 
                VALUES (?, ?, ?, ?)
            """, (uid, event.from_user.first_name, ref, int(time.time())))
            await db.commit()
            is_verified = 0
        else: 
            is_verified = row[0]

    if not is_verified:
        options = ["🍎", "🍌", "🍒", "🍉", "🍇", "🍓"]
        target = random.choice(options)
        random.shuffle(options)
        await state.update_data(captcha_target=target)
        kb = InlineKeyboardBuilder()
        for emoji in options: 
            kb.button(text=emoji, callback_data=f"captcha_{emoji}")
        text = f"🤖 **ВЕРИФИКАЦИЯ**\n\nНажмите на: {target}"
        kb.adjust(3)
        if isinstance(event, types.Message): 
            await event.answer(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
        else: 
            await event.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")
        await state.set_state(States.waiting_for_captcha)
    else:
        text = f"👋 **Привет, {event.from_user.first_name}!**\n\n💎 **ANDRON CASINO** — лучшие игры на CryptoBot.\nВыбирай режим и начни выигрывать!"
        if isinstance(event, types.Message): 
            await event.answer(text, reply_markup=main_menu_kb(uid), parse_mode="Markdown")
        else: 
            await event.message.edit_text(text, reply_markup=main_menu_kb(uid), parse_mode="Markdown")

@dp.callback_query(States.waiting_for_captcha, F.data.startswith("captcha_"))
async def process_captcha(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if c.data.split("_")[1] == data.get('captcha_target'):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (c.from_user.id,))
            await db.commit()
        await state.clear()
        await c.answer("✅ Доступ открыт!")
        await cmd_start(c)
    else:
        await c.answer("❌ Неверно!", show_alert=True)
        await cmd_start(c, state)

# --- ПРОФИЛЬ ---
@dp.callback_query(F.data == "menu_profile")
async def profile_cb(c: types.CallbackQuery):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    u = await get_user(c.from_user.id)
    if not u:
        await c.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    # Получаем количество рефералов
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (c.from_user.id,))
        ref_count_result = await cursor.fetchone()
        ref_count = ref_count_result[0] if ref_count_result else 0
    
    # Получаем информацию о реферере, если есть
    referrer_info = ""
    if u.get('referrer_id') and u['referrer_id'] > 0:
        referrer = await get_user(u['referrer_id'])
        if referrer:
            referrer_info = f"👤 Реферер: {referrer.get('username', 'Неизвестно')} (ID: {referrer['user_id']})\n"
    
    text = (
        f"👤 **ПРОФИЛЬ**\n\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"👤 Имя: {u.get('username', 'Неизвестно')}\n"
        f"💰 Баланс: `{float(u.get('balance', 0)):.2f}$`\n"
        f"🎮 Всего ставок: `{float(u.get('total_bets', 0)):.2f}$`\n"
        f"📥 Пополнено: `{float(u.get('total_deposited', 0)):.2f}$`\n"
        f"📤 Выведено: `{float(u.get('total_withdrawn', 0)):.2f}$`\n"
        f"🎮 Сыграно игр: {u.get('games_played', 0)}\n"
        f"{referrer_info}"
        f"🤝 Рефералов: {ref_count}\n"
        f"🔐 Статус: {'✅ Верифицирован' if u.get('is_verified', 0) == 1 else '❌ Не верифицирован'}\n"
        f"🎁 Реферальный бонус: {'✅ Получен' if u.get('referral_paid', 0) == 1 else '❌ Не получен'}"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="start_over")
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

# --- РЕФЕРАЛЫ ---
@dp.callback_query(F.data == "menu_refs")
async def refs_cb(c: types.CallbackQuery):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    u = await get_user(c.from_user.id)
    if not u:
        await c.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    # Получаем список рефералов с дополнительной информацией
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT user_id, username, games_played, referral_paid, balance FROM users WHERE referrer_id = ?", (c.from_user.id,))
        refs_raw = await cursor.fetchall()
        refs = []
        for row in refs_raw:
            refs.append({
                'user_id': row[0],
                'username': row[1],
                'games_played': row[2],
                'referral_paid': row[3],
                'balance': row[4]
            })
    
    ref_list = ""
    active_refs = 0
    for ref in refs:
        status = "✅" if ref['referral_paid'] == 1 else "⏳" if ref.get('games_played', 0) > 0 else "❌"
        ref_list += f"{status} {ref.get('username', 'Неизвестно')} (ID: {ref['user_id']}) - баланс: {float(ref.get('balance', 0)):.2f}$\n"
        if ref.get('games_played', 0) > 0:
            active_refs += 1
    
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={c.from_user.id}"
    
    # Считаем заработанную сумму
    earned = active_refs * REFERRAL_REWARD
    
    text = (
        f"🤝 **РЕФЕРАЛЬНАЯ СИСТЕМА**\n\n"
        f"🔗 Ваша реф. ссылка:\n`{ref_link}`\n\n"
        f"💰 **Награда:** `{REFERRAL_REWARD}$` за каждого реферала, который сыграет хотя бы в одну игру\n"
        f"💸 **Заработано:** `{earned:.2f}$`\n"
        f"👥 **Всего рефералов:** {len(refs)}\n"
        f"🎮 **Активных (сыграли):** {active_refs}\n\n"
        f"📊 **Ваши рефералы:**\n{ref_list if refs else 'Пока нет рефералов'}\n\n"
        f"ℹ️ Статусы:\n"
        f"✅ - бонус получен\n"
        f"⏳ - сыграл, бонус ожидает\n"
        f"❌ - еще не играл"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить", callback_data="menu_refs")
    kb.button(text="🔙 Назад", callback_data="start_over")
    kb.adjust(1)
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

# --- ПРАВИЛА И ПОМОЩЬ ---
@dp.callback_query(F.data == "menu_help")
async def help_cb(c: types.CallbackQuery):
    text = (
        "ℹ️ **СПРАВКА И FAQ**\n\n"
        "💳 **КАК ПОПОЛНИТЬ?**\n"
        "1. Зайдите в «Кошелек» -> «Пополнить».\n"
        "2. Введите сумму USDT (от 0.1$).\n"
        "3. Оплатите счет в CryptoBot.\n\n"
        "📤 **КАК ВЫВЕСТИ?**\n"
        "1. В разделе «Кошелек» выберите вывод.\n"
        "2. Введите сумму от 1.0$.\n"
        "3. Получите чек от CryptoBot.\n\n"
        "🤝 **РЕФЕРАЛЬНАЯ СИСТЕМА:**\n"
        f"• Приглашайте друзей по своей ссылке\n"
        f"• Получайте `{REFERRAL_REWARD}$` за каждого друга, который сыграет в игры\n\n"
        "🆘 **САППОРТ:**\n"
        "По любым вопросам обращайтесь к администраторам:\n"
        f"👨‍💻 Админ 1: `8119723042`\n"
        f"👨‍💻 Админ 2: `8448843727`\n\n"
        f"Также вы можете написать в наш канал поддержки: https://t.me/Gemini_0"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍💻 Спросить у админа", callback_data="ask_admin")
    kb.button(text="📢 Канал поддержки", url="https://t.me/Gemini_0")
    kb.button(text="🔙 Назад", callback_data="start_over")
    kb.adjust(1)
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "ask_admin")
async def ask_admin_cb(c: types.CallbackQuery):
    await c.answer("Свяжитесь с администраторами:\nID: 8119723042 или 8448843727\nЛибо напишите в канал поддержки: https://t.me/Gemini_0", show_alert=True)

@dp.callback_query(F.data == "menu_rules")
async def rules_cb(c: types.CallbackQuery):
    text = (
        "📜 **ПРАВИЛА ANDRON CASINO**\n\n"
        "💰 **ЛИМИТЫ:**\n"
        "• Ставка: от `0.1$`\n"
        "• Пополнение: от `0.1$`\n"
        "• Вывод: от `1.0$`\n\n"
        "🎮 **ИГРЫ:**\n"
        "• Дартс/Кубик: Победа x1.9, Ничья x0.9.\n"
        "• Мины: 8 мин, +25% к ставке за каждый кристалл.\n\n"
        "🎁 **БОНУС:**\n"
        "• Раз в 24 часа. Нужно иметь рекламу бота в БИО.\n\n"
        "🤝 **РЕФЕРАЛЫ:**\n"
        f"• `{REFERRAL_REWARD}$` за реферала, который сыграет в игры\n\n"
        "⚖️ **ОБЩИЕ ПРАВИЛА:**\n"
        "• Запрещено мультиаккаунтинг\n"
        "• Запрещено использование ботов\n"
        "• Администрация оставляет за собой право изменять правила"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="start_over")
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

# --- БОНУС ---
@dp.callback_query(F.data == "menu_bonus")
async def bonus_cb(c: types.CallbackQuery):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    u = await get_user(c.from_user.id)
    if not u:
        await c.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    now = int(time.time())
    if now - u.get('last_bonus', 0) < 86400:
        return await c.answer("⏳ Можно брать только раз в сутки!", show_alert=True)
    
    try:
        chat = await bot.get_chat(c.from_user.id)
        if REQUIRED_BIO_TEXT.lower() not in (chat.bio or "").lower():
            return await c.message.answer(f"❌ **Условие не выполнено!**\nУстановите в БИО профиля:\n`{REQUIRED_BIO_TEXT}`", parse_mode="Markdown")
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ?, last_bonus = ? WHERE user_id = ?", (BONUS_AMOUNT, now, c.from_user.id))
            await db.commit()
        
        await c.message.answer(f"✅ **Бонус получен!** +`{BONUS_AMOUNT}$`", parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка при получении бонуса: {e}")
        await c.answer("❌ Ошибка доступа к профилю", show_alert=True)

# --- ИГРОВОЙ БЛОК ---
@dp.callback_query(F.data == "menu_games")
async def games_list(c: types.CallbackQuery):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    kb = InlineKeyboardBuilder()
    gs = [("🎯 Дартс", "darts"), ("🎲 Кубик", "dice"), ("⚽ Футбол", "football"), 
          ("🏀 Баскет", "basket"), ("🎳 Боулинг", "bowling"), ("💣 Мины", "mines")]
    for n, code in gs: 
        kb.button(text=n, callback_data=f"play_{code}")
    kb.button(text="🔙 Назад", callback_data="start_over")
    kb.adjust(2)
    
    text = "🎰 **ВЫБЕРИТЕ ИГРУ**"
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("play_"))
async def game_start(c: types.CallbackQuery, state: FSMContext):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    game = c.data.split("_")[1]
    await state.update_data(g=game)
    await c.message.answer(f"🕹 Выбрано: **{game.upper()}**\nВведите сумму ставки:")
    await state.set_state(States.waiting_for_bet)

@dp.message(States.waiting_for_bet)
async def handle_bet(m: types.Message, state: FSMContext):
    if await is_user_banned(m.from_user.id): 
        return
    
    try:
        bet = float(m.text.replace(',', '.'))
        u = await get_user(m.from_user.id)
        if bet < MIN_BET: 
            return await m.answer(f"❌ Минимальная ставка: {MIN_BET}$")
        if bet > float(u.get('balance', 0)): 
            return await m.answer("❌ Недостаточно средств на балансе.")
        
        data = await state.get_data()
        
        if data['g'] == "mines":
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (bet, m.from_user.id))
                await db.commit()
            
            # Обновляем сумму ставок
            await update_total_bets(m.from_user.id, bet)
            
            # 8 МИН (было 6)
            f = ["0"]*17 + ["M"]*8  # 17 безопасных клеток, 8 мин
            random.shuffle(f)
            await state.update_data(field=f, bet=bet, opened=0, mult=1.0)
            
            # Увеличиваем счетчик сыгранных игр и проверяем реферальное вознаграждение
            await increment_games_played(m.from_user.id)
            await check_referral_reward(m.from_user.id)
            
            return await m.answer(
                f"💣 **MINES** (8 мин) | Ставка: `{bet}$`",
                reply_markup=get_mines_kb(f, bet), 
                parse_mode="Markdown"
            )
            
        emo = {"darts":"🎯", "dice":"🎲", "football":"⚽", "basket":"🏀", "bowling":"🎳"}[data['g']]
        await state.update_data(bet=bet, emo=emo)
        await m.answer(f"Отправьте эмодзи {emo} для броска!")
        await state.set_state(States.waiting_for_turn)
    except ValueError: 
        await m.answer("❌ Введите корректное число!")

@dp.message(States.waiting_for_turn, F.dice)
async def dice_logic(m: types.Message, state: FSMContext):
    if await is_user_banned(m.from_user.id): 
        return
    
    data = await state.get_data()
    if m.dice.emoji != data['emo']: 
        return
    
    bet = data['bet']
    
    # Обновляем сумму ставок
    await update_total_bets(m.from_user.id, bet)
    
    # Увеличиваем счетчик сыгранных игр и проверяем реферальное вознаграждение
    await increment_games_played(m.from_user.id)
    await check_referral_reward(m.from_user.id)
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (bet, m.from_user.id))
        await db.commit()
    
    b_dice = await m.answer_dice(emoji=data['emo'])
    await asyncio.sleep(4)
    
    # Убрана система скрытых шансов - используем простую логику
    if m.dice.value > b_dice.dice.value:
        # Игрок победил
        win = bet * 1.9
        result_text = "win"
        res = "🏆 ПОБЕДА"
        emoji = "💰"
    elif m.dice.value == b_dice.dice.value:
        # Ничья
        win = bet * 0.9
        result_text = "draw"
        res = "🤝 НИЧЬЯ"
        emoji = "⚖️"
    else:
        # Проигрыш
        win = 0
        result_text = "lose"
        res = "💀 ПРОИГРЫШ"
        emoji = "😢"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win, m.from_user.id))
        await db.commit()
    
    await m.answer(
        f"{emoji} **{res}!**\n"
        f"Вы: {m.dice.value} | Бот: {b_dice.dice.value}\n"
        f"Баланс: {'+' if win > 0 else ''}`{win:.2f}$`", 
        reply_markup=main_menu_kb(m.from_user.id), 
        parse_mode="Markdown"
    )
    await state.clear()

# --- ЛОГИКА МИН ---
def get_mines_kb(f, win, over=False):
    kb = InlineKeyboardBuilder()
    for i, cell in enumerate(f):
        t = ("💣" if cell=="M" else "💎") if over else ("🟦" if cell!="O" else "💎")
        if over or cell=="O":
            kb.button(text=t, callback_data="ignore")
        else:
            kb.button(text=t, callback_data=f"m_cl_{i}")
    kb.adjust(5)
    if not over: 
        kb.row(types.InlineKeyboardButton(text=f"💰 ЗАБРАТЬ {win:.2f}$", callback_data="m_cash"))
    else: 
        kb.row(types.InlineKeyboardButton(text="🔙 МЕНЮ", callback_data="start_over"))
    return kb.as_markup()

@dp.callback_query(F.data.startswith("m_cl_"))
async def mine_click(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = int(c.data.split("_")[2])
    f = data["field"].copy()
    b = data["bet"]
    o = data["opened"]
    
    if f[idx] == "M":
        await c.message.edit_text("💥 **ВЗРЫВ!** Ставка сгорела.", reply_markup=get_mines_kb(f, 0, True), parse_mode="Markdown")
        await state.clear()
    else:
        f[idx] = "O"
        o += 1
        m = round(1.0 + (o * 0.25), 2)
        await state.update_data(field=f, opened=o, mult=m)
        await c.message.edit_text(f"💎 **MINES** | x{m}\nТекущий выигрыш: `{b*m:.2f}$`", reply_markup=get_mines_kb(f, b*m), parse_mode="Markdown")
    await c.answer()

@dp.callback_query(F.data == "m_cash")
async def mine_cash(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    win = round(data["bet"] * data.get("mult", 1.0), 2)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win, c.from_user.id))
        await db.commit()
    
    await c.message.edit_text(
        f"🤑 **ВЫИГРЫШ ЗАБРАН!**\n"
        f"Сумма: `{win:.2f}$`", 
        reply_markup=main_menu_kb(c.from_user.id), 
        parse_mode="Markdown"
    )
    await state.clear()

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_home")
async def adm_panel(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: 
        await c.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    await c.message.edit_text("🔐 **АДМИН-ПАНЕЛЬ**", reply_markup=admin_menu_kb(), parse_mode="Markdown")

# Просмотр пополнений
@dp.callback_query(F.data == "adm_deposits")
async def adm_deposits_cb(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: 
        return
    
    deposits = await get_transactions(trans_type='deposit', limit=20)
    
    if not deposits:
        await c.message.edit_text("📥 **ПОПОЛНЕНИЯ**\n\nНет данных о пополнениях.", reply_markup=admin_menu_kb(), parse_mode="Markdown")
        return
    
    text = "📥 **ПОСЛЕДНИЕ ПОПОЛНЕНИЯ**\n\n"
    
    for dep in deposits:
        dt = datetime.fromtimestamp(dep['created_at']).strftime('%d.%m.%Y %H:%M')
        user = await get_user(dep['user_id'])
        username = user.get('username', f"ID: {dep['user_id']}") if user else f"ID: {dep['user_id']}"
        
        status_emoji = {
            'pending': '⏳',
            'completed': '✅',
            'failed': '❌'
        }.get(dep['status'], '❓')
        
        text += (
            f"{status_emoji} **{username}**\n"
            f"💰 `{dep['amount']:.2f}$` | 📅 {dt}\n"
            f"🆔 ID: `{dep['user_id']}` | Статус: {dep['status']}\n"
            f"📋 Invoice: `{dep['invoice_id'] or 'N/A'}`\n"
            f"{'-'*30}\n"
        )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 ОБНОВИТЬ", callback_data="adm_deposits")
    kb.button(text="📊 СТАТИСТИКА", callback_data="adm_stats")
    kb.button(text="🔙 НАЗАД", callback_data="admin_home")
    kb.adjust(2, 1)
    
    await c.message.edit_text(text[:4000], reply_markup=kb.as_markup(), parse_mode="Markdown")

# Просмотр выводов
@dp.callback_query(F.data == "adm_withdraws")
async def adm_withdraws_cb(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: 
        return
    
    withdraws = await get_transactions(trans_type='withdraw', limit=20)
    
    if not withdraws:
        await c.message.edit_text("📤 **ВЫВОДЫ**\n\nНет данных о выводах.", reply_markup=admin_menu_kb(), parse_mode="Markdown")
        return
    
    text = "📤 **ПОСЛЕДНИЕ ВЫВОДЫ**\n\n"
    
    for wd in withdraws:
        dt = datetime.fromtimestamp(wd['created_at']).strftime('%d.%m.%Y %H:%M')
        user = await get_user(wd['user_id'])
        username = user.get('username', f"ID: {wd['user_id']}") if user else f"ID: {wd['user_id']}"
        
        status_emoji = {
            'pending': '⏳',
            'completed': '✅',
            'failed': '❌'
        }.get(wd['status'], '❓')
        
        text += (
            f"{status_emoji} **{username}**\n"
            f"💰 `{wd['amount']:.2f}$` | 📅 {dt}\n"
            f"🆔 ID: `{wd['user_id']}` | Статус: {wd['status']}\n"
            f"📋 Check ID: `{wd['check_id'] or 'N/A'}`\n"
            f"{'-'*30}\n"
        )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 ОБНОВИТЬ", callback_data="adm_withdraws")
    kb.button(text="📊 СТАТИСТИКА", callback_data="adm_stats")
    kb.button(text="🔙 НАЗАД", callback_data="admin_home")
    kb.adjust(2, 1)
    
    await c.message.edit_text(text[:4000], reply_markup=kb.as_markup(), parse_mode="Markdown")

# Статистика (админ видит всё)
@dp.callback_query(F.data == "adm_stats")
async def adm_stats_cb(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: 
        return
    
    async with aiosqlite.connect(DB_NAME) as db:
        # Общая статистика
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        total_users_result = await cursor.fetchone()
        total_users = total_users_result[0] if total_users_result else 0
        
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE balance > 0")
        active_users_result = await cursor.fetchone()
        active_users = active_users_result[0] if active_users_result else 0
        
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        banned_users_result = await cursor.fetchone()
        banned_users = banned_users_result[0] if banned_users_result else 0
        
        # Финансовая статистика
        cursor = await db.execute("SELECT SUM(amount) FROM transactions WHERE type = 'deposit' AND status = 'completed'")
        total_deposited_result = await cursor.fetchone()
        total_deposited = float(total_deposited_result[0]) if total_deposited_result and total_deposited_result[0] else 0
        
        cursor = await db.execute("SELECT SUM(amount) FROM transactions WHERE type = 'withdraw' AND status = 'completed'")
        total_withdrawn_result = await cursor.fetchone()
        total_withdrawn = float(total_withdrawn_result[0]) if total_withdrawn_result and total_withdrawn_result[0] else 0
        
        cursor = await db.execute("SELECT SUM(balance) FROM users")
        total_balance_result = await cursor.fetchone()
        total_balance = float(total_balance_result[0]) if total_balance_result and total_balance_result[0] else 0
        
        # Статистика ставок
        cursor = await db.execute("SELECT SUM(total_bets) FROM users")
        total_bets_result = await cursor.fetchone()
        total_bets = float(total_bets_result[0]) if total_bets_result and total_bets_result[0] else 0
        
        # Считаем средние ставки
        cursor = await db.execute("SELECT AVG(total_bets) FROM users WHERE total_bets > 0")
        avg_bets_result = await cursor.fetchone()
        avg_bets = float(avg_bets_result[0]) if avg_bets_result and avg_bets_result[0] else 0
        
        # Статистика игр
        cursor = await db.execute("SELECT SUM(games_played) FROM users")
        total_games_result = await cursor.fetchone()
        total_games = total_games_result[0] if total_games_result else 0
        
        # Сегодняшние транзакции
        today_start = int(time.time()) - 86400
        cursor = await db.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE type = 'deposit' AND status = 'completed' AND created_at > ?", (today_start,))
        today_deposits_result = await cursor.fetchone()
        today_deposits_count = today_deposits_result[0] if today_deposits_result else 0
        today_deposits_sum = float(today_deposits_result[1]) if today_deposits_result and today_deposits_result[1] else 0
        
        cursor = await db.execute("SELECT COUNT(*), SUM(amount) FROM transactions WHERE type = 'withdraw' AND status = 'completed' AND created_at > ?", (today_start,))
        today_withdraws_result = await cursor.fetchone()
        today_withdraws_count = today_withdraws_result[0] if today_withdraws_result else 0
        today_withdraws_sum = float(today_withdraws_result[1]) if today_withdraws_result and today_withdraws_result[1] else 0
    
    text = (
        "📊 **СТАТИСТИКА ANDRON CASINO**\n\n"
        f"👥 **Пользователи:**\n"
        f"• Всего: {total_users}\n"
        f"• Активных: {active_users}\n"
        f"• Забаненных: {banned_users}\n"
        f"• Средняя сумма ставок: `{avg_bets:.2f}$`\n\n"
        
        f"💰 **Финансы:**\n"
        f"• Общий баланс: `{total_balance:.2f}$`\n"
        f"• Всего пополнено: `{total_deposited:.2f}$`\n"
        f"• Всего выведено: `{total_withdrawn:.2f}$`\n"
        f"• Прибыль: `{total_deposited - total_withdrawn:.2f}$`\n\n"
        
        f"🎮 **Ставки и игры:**\n"
        f"• Всего ставок: `{total_bets:.2f}$`\n"
        f"• Сыграно игр: {total_games}\n\n"
        
        f"📅 **За сегодня:**\n"
        f"• Пополнений: {today_deposits_count} на `{today_deposits_sum:.2f}$`\n"
        f"• Выводов: {today_withdraws_count} на `{today_withdraws_sum:.2f}$`\n\n"
        
        f"⚙️ **Игры:**\n"
        f"• Мины: 8 мин на поле 5x5\n"
        f"• Коэффициент за кристалл: +25%\n"
        f"• Мультипликатор в играх: x1.9 при победе, x0.9 при ничьей"
    )
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📥 ПОПОЛНЕНИЯ", callback_data="adm_deposits")
    kb.button(text="📤 ВЫВОДЫ", callback_data="adm_withdraws")
    kb.button(text="🔄 ОБНОВИТЬ", callback_data="adm_stats")
    kb.button(text="🔙 НАЗАД", callback_data="admin_home")
    kb.adjust(2, 2)
    
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_ban_menu")
async def adm_ban_st(c: types.CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS: 
        return
    await c.message.answer("Введите ID пользователя для бана/разбана:")
    await state.set_state(States.admin_manage_ban)

@dp.message(States.admin_manage_ban)
async def adm_ban_fin(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS: 
        return
    try:
        uid = int(m.text)
        u = await get_user(uid)
        if not u: 
            return await m.answer("❌ Юзер не найден.")
        new = 1 if u.get('is_banned', 0) == 0 else 0
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (new, uid))
            await db.commit()
        await m.answer(f"✅ Готово. Теперь статус: {'ЗАБАНЕН' if new else 'РАЗБАНЕН'}")
    except: 
        await m.answer("❌ ID должен быть числом.")
    await state.clear()

@dp.callback_query(F.data == "adm_give")
async def adm_give_st(c: types.CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS: 
        return
    await c.message.answer("Введите ID и сумму через пробел (например: 123456 10.5):")
    await state.set_state(States.admin_giving_balance)

@dp.message(States.admin_giving_balance)
async def adm_give_fin(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS: 
        return
    
    try:
        parts = m.text.split()
        if len(parts) != 2:
            return await m.answer("❌ Неверный формат. Введите: ID сумма")
        
        uid = int(parts[0])
        amt = float(parts[1])
        
        # Проверяем, существует ли пользователь
        user = await get_user(uid)
        if not user:
            return await m.answer(f"❌ Пользователь с ID {uid} не найден.")
        
        # Начисляем баланс
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, uid))
            await db.commit()
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                uid,
                f"🎁 **АДМИНИСТРАТОР ANDRON CASINO НАЧИСЛИЛ ВАМ БАЛАНС**\n\n"
                f"💰 Сумма: `{amt:.2f}$`\n"
                f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"💳 Ваш текущий баланс: `{float(user.get('balance', 0)) + amt:.2f}$`"
            )
        except Exception as e:
            logging.error(f"Ошибка уведомления пользователя: {e}")
        
        await m.answer(f"✅ Баланс пользователю {uid} пополнен на {amt:.2f}$")
        
    except ValueError:
        await m.answer("❌ Ошибка ввода. Формат: `ID сумма` (например: 1234567 10.5)")
    except Exception as e:
        logging.error(f"Ошибка при выдаче баланса: {e}")
        await m.answer("❌ Произошла ошибка при выдаче баланса.")
    
    await state.clear()

# --- КОШЕЛЕК ---
@dp.callback_query(F.data == "menu_wallet")
async def wallet_view(c: types.CallbackQuery):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    u = await get_user(c.from_user.id)
    if not u:
        await c.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    text = (
        f"💳 **КОШЕЛЕК**\n\n"
        f"💰 Баланс: `{float(u.get('balance', 0)):.2f}$`"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ ПОПОЛНИТЬ", callback_data="deposit_auto")
    kb.button(text="📤 ВЫВЕСТИ", callback_data="withdraw_ask")
    kb.button(text="🔙 НАЗАД", callback_data="start_over")
    kb.adjust(2, 1)
    await c.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="Markdown")

# --- ВЫВОД (через CryptoBot API) ---
@dp.callback_query(F.data == "withdraw_ask")
async def withdraw_ask_cb(c: types.CallbackQuery, state: FSMContext):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    u = await get_user(c.from_user.id)
    if not u:
        await c.answer("❌ Пользователь не найден!", show_alert=True)
        return
    
    if float(u.get('balance', 0)) < MIN_WITHDRAW:
        return await c.answer(f"❌ Минимальная сумма вывода: {MIN_WITHDRAW}$", show_alert=True)
    
    await c.message.answer(f"💰 Ваш баланс: `{float(u.get('balance', 0)):.2f}$`\n\nВведите сумму для вывода (мин. {MIN_WITHDRAW}$):")
    await state.set_state(States.waiting_for_withdraw)

@dp.message(States.waiting_for_withdraw)
async def withdraw_handle(m: types.Message, state: FSMContext):
    if await is_user_banned(m.from_user.id): 
        return
    
    try:
        amount = float(m.text.replace(',', '.'))
        u = await get_user(m.from_user.id)
        
        if amount < MIN_WITHDRAW:
            return await m.answer(f"❌ Минимальная сумма вывода: {MIN_WITHDRAW}$")
        
        if amount > float(u.get('balance', 0)):
            return await m.answer("❌ Недостаточно средств на балансе")
        
        # Создаем чек через CryptoBot API
        check_result = await create_crypto_check(amount)
        
        if not check_result["success"]:
            return await m.answer(f"❌ Ошибка при создании чека: {check_result['error']}\nПопробуйте позже или обратитесь в поддержку.")
        
        # Добавляем запись о выводе
        await add_transaction(m.from_user.id, 'withdraw', amount, 
                            check_id=check_result.get("check_id"), status='pending')
        
        # Обновляем статистику пользователя
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance - ?, total_withdrawn = total_withdrawn + ? WHERE user_id = ?", 
                           (amount, amount, m.from_user.id))
            await db.commit()
        
        await m.answer(
            f"✅ **Вывод оформлен!**\n\n"
            f"💰 Сумма: `{amount}$`\n"
            f"🔗 Ссылка на чек: {check_result['check_url']}\n\n"
            f"💡 **Как получить выплату:**\n"
            f"1. Нажмите на ссылку выше\n"
            f"2. Чек будет открыт в CryptoBot\n"
            f"3. Нажмите 'Активировать чек'\n"
            f"4. Средства будут зачислены на ваш баланс в CryptoBot\n\n"
            f"📊 Ваш баланс в боте: `{float(u.get('balance', 0)) - amount:.2f}$`"
        )
        await state.clear()
        
    except ValueError:
        await m.answer("❌ Введите корректную сумму (например: 1.0)")

# --- ПОПОЛНЕНИЕ (через CryptoBot) ---
@dp.callback_query(F.data == "deposit_auto")
async def dep_ask(c: types.CallbackQuery, state: FSMContext):
    if await is_user_banned(c.from_user.id): 
        await c.answer("⛔ Вы забанены!", show_alert=True)
        return
    
    await c.message.answer(f"Введите сумму пополнения в USDT (от {MIN_DEPOSIT}$):")
    await state.set_state(States.waiting_for_deposit)

@dp.message(States.waiting_for_deposit)
async def dep_create(m: types.Message, state: FSMContext):
    if await is_user_banned(m.from_user.id): 
        return
    
    try:
        val = float(m.text.replace(',', '.'))
        
        if val < MIN_DEPOSIT:
            return await m.answer(f"❌ Минимальная сумма пополнения: {MIN_DEPOSIT}$")
        
        # Создаем инвойс через CryptoBot
        inv = await crypto.create_invoice(asset='USDT', amount=val)
        
        # Добавляем запись о пополнении
        await add_transaction(m.from_user.id, 'deposit', val, inv.invoice_id, status='pending')
        
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 ОПЛАТИТЬ СЧЕТ", url=inv.bot_invoice_url)
        kb.button(text="🔄 ПРОВЕРИТЬ ОПЛАТУ", callback_data=f"check_{inv.invoice_id}")
        kb.button(text="❌ ОТМЕНА", callback_data="start_over")
        kb.adjust(1)
        
        await m.answer(
            f"💎 **СЧЕТ НА ОПЛАТУ**\n\n"
            f"💰 Сумма: `{val}$ USDT`\n"
            f"⏳ Счет действителен 15 минут\n\n"
            f"📋 **Инструкция:**\n"
            f"1. Нажмите кнопку 'ОПЛАТИТЬ СЧЕТ'\n"
            f"2. Оплатите в CryptoBot\n"
            f"3. Нажмите 'ПРОВЕРИТЬ ОПЛАТУ'",
            reply_markup=kb.as_markup(),
            parse_mode="Markdown"
        )
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка создания инвойса: {e}")
        await m.answer("❌ Ошибка при создании счета. Попробуйте позже.")

@dp.callback_query(F.data.startswith("check_"))
async def dep_check(c: types.CallbackQuery):
    iid = int(c.data.split("_")[1])
    invs = await crypto.get_invoices(invoice_ids=[iid])
    
    if invs and invs[0].status == 'paid':
        amt = float(invs[0].amount)
        
        # Обновляем статус транзакции
        await update_transaction_status(invoice_id=str(iid), status='completed')
        
        async with aiosqlite.connect(DB_NAME) as db:
            # Пополняем баланс
            await db.execute("UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?", 
                           (amt, amt, c.from_user.id))
            await db.commit()
        
        await c.message.answer(f"✅ **Счет оплачен!**\n\nЗачислено: `{amt}$`\nБаланс обновлен.", parse_mode="Markdown")
        await cmd_start(c)
    else: 
        await c.answer("⏳ Счет еще не оплачен!", show_alert=True)

@dp.callback_query(F.data == "ignore")
async def ignore_cb(c: types.CallbackQuery): 
    await c.answer()

async def main():
    # Инициализируем базу данных
    await init_db()
    
    # Обновляем схему БД (добавляем недостающие колонки)
    await update_db_schema()
    
    # Запускаем бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
