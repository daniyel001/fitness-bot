import io
import qrcode
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio
import logging
from datetime import datetime, timedelta
import re

# --- Настройки логирования ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Настройки ---
TOKEN = "8391384916:AAEtQdeslStJfhHlD6Sz1aUIM27M48SOu5c"
ADMIN_ID = 5024480192

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Состояния FSM ---
class AddClientStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_name = State()

# --- Клавиатуры ---
def get_client_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎟 Мой QR"), KeyboardButton(text="📊 Мои посещения")],
            [KeyboardButton(text="🆔 Мой ID"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

def get_admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список клиентов"), KeyboardButton(text="👤 Добавить клиента")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="✅ Отметить посещение")]
        ],
        resize_keyboard=True
    )

def get_cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

# --- Инициализация базы ---
async def init_db():
    try:
        async with aiosqlite.connect("visits.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    visits_left INTEGER DEFAULT 12,
                    last_visit TEXT,
                    end_date TEXT,
                    registration_date TEXT
                )
            """)
            await db.commit()
            logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")

# --- Вспомогательные функции ---
async def get_client_info(user_id: int):
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute("SELECT name, visits_left, end_date, last_visit FROM clients WHERE user_id=?", (user_id,)) as cursor:
            return await cursor.fetchone()

async def mark_visit(user_id: int, msg: types.Message):
    try:
        async with aiosqlite.connect("visits.db") as db:
            async with db.execute("SELECT name, visits_left, end_date FROM clients WHERE user_id=?", (user_id,)) as cursor:
                row = await cursor.fetchone()
            if not row:
                await msg.answer("❌ Клиент не найден.")
                return
            
            name, visits_left, end_date = row
            
            if end_date and datetime.now() > datetime.strptime(end_date, "%Y-%m-%d"):
                await msg.answer(f"⚠️ Абонемент {name} истёк!")
                return
            
            if visits_left <= 0:
                await msg.answer(f"⚠️ У {name} закончились посещения.")
                return
            
            visits_left -= 1
            last_visit = datetime.now().strftime("%d.%m.%Y %H:%M")
            await db.execute(
                "UPDATE clients SET visits_left=?, last_visit=? WHERE user_id=?", 
                (visits_left, last_visit, user_id)
            )
            await db.commit()
            
        await msg.answer(f"✅ Посещение засчитано для {name}. Осталось {visits_left} посещений.")
        
        try:
            await bot.send_message(user_id, f"✅ Ваше посещение засчитано. Осталось {visits_left} посещений.")
        except Exception as e:
            logger.warning(f"Не удалось уведомить клиента {user_id}: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при отметке посещения: {e}")
        await msg.answer("❌ Произошла ошибка при обработке посещения.")

# --- Команды клиента ---
@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    try:
        user_id = msg.from_user.id
        name = msg.from_user.full_name
        
        async with aiosqlite.connect("visits.db") as db:
            await db.execute(
                "INSERT OR IGNORE INTO clients (user_id, name, end_date, registration_date) VALUES (?, ?, ?, ?)",
                (user_id, name, (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"), datetime.now().strftime("%Y-%m-%d"))
            )
            await db.commit()
        
        if user_id == ADMIN_ID:
            await msg.answer("🔐 Админ-панель активирована", reply_markup=get_admin_kb())
            return
        
        qr_data = str(user_id)
        qr_img = qrcode.make(qr_data)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        photo = BufferedInputFile(buf.read(), filename="qr.png")
        
        await msg.answer_photo(
            photo=photo, 
            caption=f"🎟 Ваш абонемент, {name}\n📅 До {(datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')}",
            reply_markup=get_client_kb()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в start команде: {e}")
        await msg.answer("❌ Произошла ошибка при запуске бота.")

@dp.message(F.text == "🎟 Мой QR")
async def my_qr(msg: types.Message):
    try:
        user_id = msg.from_user.id
        name = msg.from_user.full_name
        
        qr_data = str(user_id)
        qr_img = qrcode.make(qr_data)
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        photo = BufferedInputFile(buf.read(), filename="qr.png")
        
        await msg.answer_photo(photo=photo, caption=f"🎟 Ваш QR-код\n👤 {name}")
    except Exception as e:
        await msg.answer("❌ Ошибка при создании QR-кода.")

@dp.message(F.text == "📊 Мои посещения")
async def my_status(msg: types.Message):
    try:
        user_id = msg.from_user.id
        client_info = await get_client_info(user_id)
        
        if not client_info:
            await msg.answer("❌ Вас нет в базе, отправьте /start")
            return
            
        name, visits_left, end_date, last_visit = client_info
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        days_left = (end_date_obj - datetime.now()).days
        
        status = "🟢 Активен" if days_left > 0 and visits_left > 0 else "🔴 Неактивен"
        
        message = f"📊 Ваш абонемент\n\n👤 {name}\n📊 Статус: {status}\n🎟 Осталось посещений: {visits_left}\n📅 Абонемент до: {end_date}\n⏳ Осталось дней: {max(0, days_left)}"
        
        if last_visit:
            message += f"\n🕐 Последнее посещение: {last_visit}"
            
        await msg.answer(message)
        
    except Exception as e:
        await msg.answer("❌ Ошибка при получении информации.")

@dp.message(F.text == "🆔 Мой ID")
async def get_my_id(msg: types.Message):
    user_id = msg.from_user.id
    await msg.answer(f"🆔 Ваш User ID: `{user_id}`", parse_mode="Markdown")

@dp.message(F.text == "ℹ️ Помощь")
async def help_cmd(msg: types.Message):
    help_text = "ℹ️ Помощь по боту:\n\n🎟 Мой QR - получить QR-код\n📊 Мои посещения - статус абонемента\n🆔 Мой ID - ваш идентификатор"
    await msg.answer(help_text)

# --- Админ команды ---
@dp.message(F.text == "📋 Список клиентов")
async def list_clients(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
        
    try:
        async with aiosqlite.connect("visits.db") as db:
            async with db.execute("SELECT user_id, name, visits_left, end_date FROM clients ORDER BY name") as cursor:
                rows = await cursor.fetchall()
        
        if not rows:
            await msg.answer("📭 Клиентов пока нет")
            return
        
        text = "📋 Список клиентов:\n\n"
        for user_id, name, visits_left, end_date in rows:
            status = "✅" if visits_left > 0 else "❌"
            text += f"{status} {name} - {visits_left} посещ., до {end_date}\n"
        
        await msg.answer(text)
            
    except Exception as e:
        await msg.answer("❌ Ошибка при получении списка клиентов.")

@dp.message(F.text == "📊 Статистика")
async def show_stats(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
        
    try:
        async with aiosqlite.connect("visits.db") as db:
            async with db.execute("SELECT COUNT(*) FROM clients") as cursor:
                total = (await cursor.fetchone())[0]
                
            async with db.execute("SELECT COUNT(*) FROM clients WHERE visits_left > 0 AND end_date >= date('now')") as cursor:
                active = (await cursor.fetchone())[0]
        
        stats_text = f"📊 Статистика зала\n\n👥 Всего клиентов: {total}\n✅ Активных: {active}\n📅 Дата: {datetime.now().strftime('%d.%m.%Y')}"
        await msg.answer(stats_text)
        
    except Exception as e:
        await msg.answer("❌ Ошибка при получении статистики.")

@dp.message(F.text == "👤 Добавить клиента")
async def add_client_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    await msg.answer("👤 Отправьте User ID клиента:", reply_markup=get_cancel_kb())
    await state.set_state(AddClientStates.waiting_for_user_id)

@dp.message(F.text == "✅ Отметить посещение")
async def manual_visit_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    await msg.answer("Введите User ID клиента для отметки посещения:", reply_markup=get_cancel_kb())
    # Сохраняем состояние для ручного ввода ID
    await state.set_state(AddClientStates.waiting_for_user_id)
    await state.update_data(action="mark_visit")

@dp.message(F.text == "❌ Отмена")
async def cancel_handler(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await msg.answer("❌ Действие отменено", reply_markup=get_admin_kb())

@dp.message(AddClientStates.waiting_for_user_id)
async def process_user_id(msg: types.Message
