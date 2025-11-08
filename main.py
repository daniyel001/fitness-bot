import io
import qrcode
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from pyzbar.pyzbar import decode
from PIL import Image
import asyncio
import os
from datetime import datetime, timedelta
import re

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
        keyboard=[[KeyboardButton(text="🎟 Мой QR")], [KeyboardButton(text="📊 Мои посещения")]],
        resize_keyboard=True
    )

def get_admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список клиентов"), KeyboardButton(text="👤 Добавить клиента")],
            [KeyboardButton(text="📸 Сканировать QR")],
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
    async with aiosqlite.connect("visits.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                visits_left INTEGER DEFAULT 12,
                last_visit TEXT,
                end_date TEXT
            )
        """)
        await db.commit()

# --- Вспомогательные функции ---
async def mark_visit(user_id: int, msg: types.Message):
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
        await db.execute("UPDATE clients SET visits_left=?, last_visit=? WHERE user_id=?", (visits_left, last_visit, user_id))
        await db.commit()
    await msg.answer(f"✅ Посещение засчитано для {name}. Осталось {visits_left} посещений.")
    try:
        await bot.send_message(user_id, f"✅ Ваше посещение засчитано. Осталось {visits_left} посещений.")
    except:
        pass

# --- Команды клиента ---
@dp.message(Command("start"))
async def start_cmd(msg: types.Message):
    user_id = msg.from_user.id
    name = msg.from_user.full_name
    async with aiosqlite.connect("visits.db") as db:
        await db.execute("INSERT OR IGNORE INTO clients (user_id, name, end_date) VALUES (?, ?, ?)",
                         (user_id, name, (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")))
        await db.commit()
    
    if user_id == ADMIN_ID:
        await msg.answer("🔐 Админ-панель активирована", reply_markup=get_admin_kb())
        return
    
    # Создание QR-кода для обычных пользователей
    qr_data = str(user_id)
    qr_img = qrcode.make(qr_data)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    photo = BufferedInputFile(buf.read(), filename="qr.png")
    await msg.answer_photo(photo=photo, caption=f"🎟 Ваш абонемент, {name}\n📅 До {(datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')}",
                           reply_markup=get_client_kb())

@dp.message(F.text == "🎟 Мой QR")
async def my_qr(msg: types.Message):
    user_id = msg.from_user.id
    name = msg.from_user.full_name
    qr_data = str(user_id)
    qr_img = qrcode.make(qr_data)
    buf = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    photo = BufferedInputFile(buf.read(), filename="qr.png")
    await msg.answer_photo(photo=photo, caption=f"🎟 Ваш QR, {name}")

@dp.message(F.text == "📊 Мои посещения")
async def my_status(msg: types.Message):
    user_id = msg.from_user.id
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute("SELECT visits_left, end_date FROM clients WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
    if not row:
        await msg.answer("❌ Вас нет в базе, отправьте /start")
        return
    visits_left, end_date = row
    await msg.answer(f"📊 Осталось посещений: {visits_left}\n📅 Абонемент до: {end_date}")

# --- Админ команды ---
@dp.message(F.text == "📋 Список клиентов")
async def list_clients(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute("SELECT user_id, name, visits_left, end_date FROM clients") as cursor:
            rows = await cursor.fetchall()
    if not rows:
        await msg.answer("📭 Клиентов пока нет")
        return
    
    text = "📋 Список клиентов:\n\n"
    for user_id, name, visits_left, end_date in rows:
        text += f"👤 {name} (ID: {user_id})\n"
        text += f"   🎟 Осталось посещений: {visits_left}\n"
        text += f"   📅 Абонемент до: {end_date}\n\n"
    
    await msg.answer(text)

@dp.message(F.text == "👤 Добавить клиента")
async def add_client_start(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    await msg.answer(
        "👤 Для добавления клиента отправьте его User ID.\n\n"
        "Как получить User ID:\n"
        "1. Попросите пользователя отправить боту @userinfobot\n"
        "2. Или используйте команду /get_id если пользователь уже писал боту\n"
        "3. User ID - это число, например: 123456789",
        reply_markup=get_cancel_kb()
    )
    await state.set_state(AddClientStates.waiting_for_user_id)

@dp.message(F.text == "❌ Отмена")
async def cancel_handler(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await msg.answer("❌ Добавление клиента отменено", reply_markup=get_admin_kb())

@dp.message(AddClientStates.waiting_for_user_id)
async def process_user_id(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    user_id_text = msg.text.strip()
    
    # Проверяем, что введено число
    if not re.match(r'^\d+$', user_id_text):
        await msg.answer("❌ User ID должен содержать только цифры. Попробуйте еще раз:", reply_markup=get_cancel_kb())
        return
    
    user_id = int(user_id_text)
    
    # Проверяем, не существует ли уже клиент с таким ID
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute("SELECT name FROM clients WHERE user_id=?", (user_id,)) as cursor:
            existing_client = await cursor.fetchone()
    
    if existing_client:
        await msg.answer(f"❌ Клиент с ID {user_id} уже существует в базе: {existing_client[0]}", reply_markup=get_admin_kb())
        await state.clear()
        return
    
    await state.update_data(user_id=user_id)
    await msg.answer("✅ User ID принят. Теперь отправьте имя клиента:", reply_markup=get_cancel_kb())
    await state.set_state(AddClientStates.waiting_for_name)

@dp.message(AddClientStates.waiting_for_name)
async def process_client_name(msg: types.Message, state: FSMContext):
    if msg.from_user.id != ADMIN_ID:
        return
    
    name = msg.text.strip()
    
    if len(name) < 2:
        await msg.answer("❌ Имя слишком короткое. Введите корректное имя:", reply_markup=get_cancel_kb())
        return
    
    data = await state.get_data()
    user_id = data['user_id']
    
    # Добавляем клиента в базу
    async with aiosqlite.connect("visits.db") as db:
        await db.execute(
            "INSERT INTO clients (user_id, name, visits_left, end_date) VALUES (?, ?, ?, ?)",
            (user_id, name, 12, (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"))
        )
        await db.commit()
    
    await msg.answer(
        f"✅ Клиент успешно добавлен!\n\n"
        f"👤 Имя: {name}\n"
        f"🆔 User ID: {user_id}\n"
        f"🎟 Посещений: 12\n"
        f"📅 Абонемент до: {(datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')}",
        reply_markup=get_admin_kb()
    )
    
    # Отправляем сообщение клиенту, если бот добавлен у него
    try:
        await bot.send_message(
            user_id,
            f"🎉 Добро пожаловать! Вы были добавлены в систему.\n\n"
            f"👤 Ваше имя: {name}\n"
            f"🎟 Количество посещений: 12\n"
            f"📅 Абонемент действует до: {(datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')}\n\n"
            f"Используйте кнопки ниже для управления вашим абонементом:",
            reply_markup=get_client_kb()
        )
    except Exception as e:
        await msg.answer(f"⚠️ Клиент добавлен, но не получилось отправить ему приветственное сообщение. Возможно, бот не запущен у пользователя.")
    
    await state.clear()

@dp.message(F.text == "📸 Сканировать QR")
async def scan_qr_prompt(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    await msg.answer("📸 Отправьте фото с QR-кодом для сканирования")

# Команда для получения User ID
@dp.message(Command("get_id"))
async def get_id_cmd(msg: types.Message):
    user_id = msg.from_user.id
    await msg.answer(f"🆔 Ваш User ID: `{user_id}`\n\nОтправьте этот номер администратору для добавления в систему.", parse_mode="Markdown")

# --- Обработка кнопок админа ---
@dp.callback_query()
async def cb_handler(cb: types.CallbackQuery):
    if cb.from_user.id != ADMIN_ID:
        await cb.answer("❌ У вас нет прав для этого действия", show_alert=True)
        return
        
    data = cb.data
    if not data:
        return
    
    try:
        if ":" in data:
            parts = data.split(":")
            if len(parts) == 3:
                action, user_id_str, value_str = parts
                user_id = int(user_id_str)
                value = int(value_str)
                
                async with aiosqlite.connect("visits.db") as db:
                    if action == "add_visits":
                        await db.execute("UPDATE clients SET visits_left = visits_left + ? WHERE user_id=?", (value, user_id))
                        await db.commit()
                        await cb.message.edit_text(f"✅ Клиенту {user_id} добавлено {value} посещений")
                    elif action == "extend":
                        async with db.execute("SELECT end_date FROM clients WHERE user_id=?", (user_id,)) as cursor:
                            row = await cursor.fetchone()
                        if row and row[0]:
                            current_end = datetime.strptime(row[0], "%Y-%m-%d")
                            new_end = max(datetime.now(), current_end) + timedelta(days=value)
                        else:
                            new_end = datetime.now() + timedelta(days=value)
                        await db.execute("UPDATE clients SET end_date=? WHERE user_id=?", (new_end.strftime("%Y-%m-%d"), user_id))
                        await db.commit()
                        await cb.message.edit_text(f"✅ Абонемент клиента {user_id} продлён до {new_end.strftime('%d.%m.%Y')}")
    except Exception as e:
        await cb.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
    
    await cb.answer()

# --- Сканирование QR фото ---
@dp.message(F.photo)
async def scan_qr_photo(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return
    
    await msg.answer("⏳ Обрабатываю QR-код...")
    
    try:
        photo = msg.photo[-1]
        file = await bot.get_file(photo.file_id)
        path = f"temp_{msg.message_id}.jpg"
        await bot.download_file(file.file_path, path)
        
        # Открываем и обрабатываем изображение
        image = Image.open(path)
        decoded = decode(image)
        
        os.remove(path)
        
        if not decoded:
            await msg.answer("❌ QR-код не распознан. Убедитесь, что фото четкое и хорошо освещено.")
            return
        
        qr_data = decoded[0].data.decode("utf-8")
        try:
            user_id = int(qr_data)
        except ValueError:
            await msg.answer("⚠️ QR-код не содержит корректный ID пользователя")
            return
        
        await mark_visit(user_id, msg)
        
    except Exception as e:
        await msg.answer(f"❌ Ошибка при обработке QR-кода: {str(e)}")

# --- Точка входа ---
async def main():
    print("🚀 Бот запущен и готов к работе.")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())