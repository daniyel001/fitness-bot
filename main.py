import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
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


class OnboardingStates(StatesGroup):
    waiting_for_goal = State()
    waiting_for_level = State()
    waiting_for_days = State()


class ProgressStates(StatesGroup):
    waiting_for_weight = State()
    waiting_for_note = State()


# --- Константы ---
FITNESS_LEVELS = ["Новичок", "Средний", "Продвинутый"]
GOALS = ["Похудение", "Набор массы", "Выносливость"]

WORKOUT_LIBRARY: Dict[str, Dict[str, List[str]]] = {
    "Новичок": {
        "Похудение": [
            "Разминка 10 минут ходьбы или легкого бега",
            "Круговая тренировка (3 круга): приседания x15, отжимания от колен x12, планка 30 сек",
            "Заминка: растяжка бедер и спины"
        ],
        "Набор массы": [
            "Разминка: суставная гимнастика 5 минут",
            "Силовая тренировка (3 подхода): приседания с весом тела x12, отжимания x10, тяга эспандера к поясу x15",
            "Финиш: упражнение на пресс (велосипед) 3x20"
        ],
        "Выносливость": [
            "Разминка: прыжки со скакалкой 3 минуты",
            "Интервальная кардио (4 раунда): 40 секунд бег на месте + 20 секунд отдыха",
            "Заминка: дыхательные упражнения"
        ]
    },
    "Средний": {
        "Похудение": [
            "Разминка: эллипс 8 минут",
            "Круг: берпи x12, выпады x14, отжимания x15, планка 40 сек (4 круга)",
            "Финиш: растяжка ног и корпуса"
        ],
        "Набор массы": [
            "Разминка: бег 5 минут",
            "Силовая: приседания со штангой 4x8, жим лежа 4x8, тяга в наклоне 4x10",
            "Дополнительно: гиперэкстензия 3x15"
        ],
        "Выносливость": [
            "Разминка: велотренажер 8 минут",
            "Интервалы: 6 раундов 1 мин спринт + 1 мин легкий бег",
            "Финиш: упражнения на пресс 3x25"
        ]
    },
    "Продвинутый": {
        "Похудение": [
            "Разминка: функциональная 10 минут",
            "HIIT: 5 раундов (30 сек берпи + 30 сек альпинист + 30 сек прыжки на тумбу + 30 сек отдыха)",
            "Финиш: растяжка + дыхательная практика"
        ],
        "Набор массы": [
            "Разминка: лёгкий комплекс на мобилизацию",
            "Силовая: становая тяга 5x5, жим стоя 4x6, подтягивания с весом 4x8",
            "Добивка: упражнение на бицепс и трицепс 3x12"
        ],
        "Выносливость": [
            "Разминка: гребной тренажер 7 минут",
            "Кроссфит-комплекс: 5 раундов (400 м бег + 20 приседаний + 15 отжиманий + 10 подтягиваний)",
            "Финиш: планка 3x1 мин"
        ]
    }
}

NUTRITION_TIPS: Dict[str, List[str]] = {
    "Похудение": [
        "Держите дефицит калорий 10-15% от поддерживающей нормы",
        "Сосредоточьтесь на белке: 1.6-2 г на кг веса",
        "Включите много овощей и цельнозерновых продуктов",
        "Пейте не менее 30 мл воды на кг массы тела"
    ],
    "Набор массы": [
        "Профицит калорий 10% и больше",
        "Белок 2 г/кг, углеводы из круп, овощей и фруктов",
        "Обязательно добавьте перекусы после тренировок",
        "Контролируйте восстановление и сон 7-8 часов"
    ],
    "Выносливость": [
        "Сбалансируйте углеводы 50-60% рациона",
        "Включайте электролиты при длительных тренировках",
        "Белок 1.4-1.6 г/кг для восстановления",
        "Следите за приёмом омега-3 и витаминов группы B"
    ]
}

# --- Клавиатуры ---
def get_client_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Мой абонемент"), KeyboardButton(text="📅 План тренировок")],
            [KeyboardButton(text="🥗 Питание"), KeyboardButton(text="📈 Прогресс")],
            [KeyboardButton(text="🆔 Мой ID"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )


def get_admin_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список клиентов"), KeyboardButton(text="👤 Добавить клиента")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="✅ Отметить посещение")]
        ],
        resize_keyboard=True
    )


def get_cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


# --- Инициализация базы ---
async def init_db() -> None:
    try:
        async with aiosqlite.connect("visits.db") as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS clients (
                    user_id INTEGER PRIMARY KEY,
                    name TEXT,
                    visits_left INTEGER DEFAULT 12,
                    last_visit TEXT,
                    end_date TEXT,
                    registration_date TEXT,
                    fitness_goal TEXT DEFAULT '',
                    fitness_level TEXT DEFAULT '',
                    preferred_days TEXT DEFAULT '',
                    reminder_time TEXT DEFAULT ''
                )
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS progress_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    logged_at TEXT,
                    weight REAL,
                    note TEXT,
                    FOREIGN KEY(user_id) REFERENCES clients(user_id)
                )
                """
            )

            columns: List[str] = []
            async with db.execute("PRAGMA table_info(clients)") as cursor:
                async for row in cursor:
                    columns.append(row[1])

            migrations = {
                "fitness_goal": "ALTER TABLE clients ADD COLUMN fitness_goal TEXT DEFAULT ''",
                "fitness_level": "ALTER TABLE clients ADD COLUMN fitness_level TEXT DEFAULT ''",
                "preferred_days": "ALTER TABLE clients ADD COLUMN preferred_days TEXT DEFAULT ''",
                "reminder_time": "ALTER TABLE clients ADD COLUMN reminder_time TEXT DEFAULT ''"
            }

            for column, query in migrations.items():
                if column not in columns:
                    await db.execute(query)

            await db.commit()
            logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")


# --- Вспомогательные функции ---
async def get_client_info(user_id: int) -> Tuple:
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute(
            "SELECT name, visits_left, end_date, last_visit, fitness_goal, fitness_level, preferred_days FROM clients WHERE user_id=?",
            (user_id,)
        ) as cursor:
            return await cursor.fetchone()


def build_workout_plan(level: str, goal: str, days: str) -> str:
    workouts = WORKOUT_LIBRARY.get(level, {}).get(goal, [])
    if not workouts:
        return "План пока не готов. Обратитесь к администратору."

    header = (
        f"📅 План тренировок для цели: {goal}\n"
        f"💪 Уровень: {level}\n"
        f"📆 Рекомендуемые дни: {days or 'укажите в профиле'}\n\n"
    )
    body = "\n\n".join(f"{idx + 1}. {item}" for idx, item in enumerate(workouts))
    return header + body


def build_nutrition_advice(goal: str) -> str:
    tips = NUTRITION_TIPS.get(goal)
    if not tips:
        return "Пока нет рекомендаций по питанию, обратитесь к тренеру."
    return "🥗 Рекомендации по питанию:\n\n" + "\n".join(f"• {tip}" for tip in tips)


async def mark_visit(user_id: int, msg: types.Message) -> None:
    try:
        async with aiosqlite.connect("visits.db") as db:
            async with db.execute(
                "SELECT name, visits_left, end_date FROM clients WHERE user_id=?",
                (user_id,)
            ) as cursor:
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
            await bot.send_message(
                user_id,
                f"✅ Ваше посещение засчитано. Осталось {visits_left} посещений."
            )
        except Exception as e:
            logger.warning(f"Не удалось уведомить клиента {user_id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при отметке посещения: {e}")
        await msg.answer("❌ Произошла ошибка при обработке посещения.")


async def fetch_profile(user_id: int) -> Tuple[str, str, str]:
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute(
            "SELECT fitness_goal, fitness_level, preferred_days FROM clients WHERE user_id=?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return "", "", ""
            return row


async def fetch_progress_logs(user_id: int, limit: int = 3) -> List[Tuple[str, float, str]]:
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute(
            "SELECT logged_at, weight, note FROM progress_logs WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            return await cursor.fetchall()


# --- Команды клиента ---
@dp.message(Command("start"))
async def start_cmd(msg: types.Message, state: FSMContext) -> None:
    try:
        user_id = msg.from_user.id
        name = msg.from_user.full_name

        async with aiosqlite.connect("visits.db") as db:
            await db.execute(
                "INSERT OR IGNORE INTO clients (user_id, name, end_date, registration_date) VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    name,
                    (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                    datetime.now().strftime("%Y-%m-%d")
                )
            )
            await db.commit()

        if user_id == ADMIN_ID:
            await msg.answer("🔐 Админ-панель активирована", reply_markup=get_admin_kb())
            return

        goal, level, days = await fetch_profile(user_id)

        if not goal or not level:
            await msg.answer(
                "👋 Добро пожаловать! Давайте подберем план под ваши цели.\n\n"
                "Напишите главную цель тренировок (Похудение, Набор массы или Выносливость)."
            )
            await state.set_state(OnboardingStates.waiting_for_goal)
            return

        welcome_msg = (
            f"🎉 Добро пожаловать, {name}!\n\n"
            "📋 Ваш абонемент активен. Используйте кнопки ниже для управления."
        )

        await msg.answer(welcome_msg, reply_markup=get_client_kb())

    except Exception as e:
        logger.error(f"Ошибка в start команде: {e}")
        await msg.answer("❌ Произошла ошибка при запуске бота.")


@dp.message(OnboardingStates.waiting_for_goal)
async def onboarding_goal(msg: types.Message, state: FSMContext) -> None:
    goal = msg.text.strip().capitalize()
    if goal not in GOALS:
        await msg.answer("Выберите одну из целей: Похудение, Набор массы или Выносливость.")
        return

    await state.update_data(goal=goal)
    await msg.answer("Отлично! Какой у вас уровень подготовки? (Новичок, Средний, Продвинутый)")
    await state.set_state(OnboardingStates.waiting_for_level)


@dp.message(OnboardingStates.waiting_for_level)
async def onboarding_level(msg: types.Message, state: FSMContext) -> None:
    level = msg.text.strip().capitalize()
    if level not in FITNESS_LEVELS:
        await msg.answer("Введите уровень: Новичок, Средний или Продвинутый.")
        return

    await state.update_data(level=level)
    await msg.answer("Супер! Укажите удобные дни тренировок (например: Пн, Ср, Пт).")
    await state.set_state(OnboardingStates.waiting_for_days)


@dp.message(OnboardingStates.waiting_for_days)
async def onboarding_days(msg: types.Message, state: FSMContext) -> None:
    days = msg.text.strip()
    data = await state.get_data()
    goal = data.get("goal")
    level = data.get("level")
    user_id = msg.from_user.id

    async with aiosqlite.connect("visits.db") as db:
        await db.execute(
            "UPDATE clients SET fitness_goal=?, fitness_level=?, preferred_days=? WHERE user_id=?",
            (goal, level, days, user_id)
        )
        await db.commit()

    await state.clear()

    await msg.answer(
        "Отлично! Я подготовил для вас персональные рекомендации. "
        "Используйте меню ниже, чтобы просмотреть план тренировок и советы по питанию.",
        reply_markup=get_client_kb()
    )


@dp.message(F.text == "📊 Мой абонемент")
async def my_status(msg: types.Message) -> None:
    try:
        user_id = msg.from_user.id
        client_info = await get_client_info(user_id)

        if not client_info:
            await msg.answer("❌ Вас нет в базе, отправьте /start")
            return

        name, visits_left, end_date, last_visit, goal, level, days = client_info
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        days_left = (end_date_obj - datetime.now()).days

        status = "🟢 Активен" if days_left > 0 and visits_left > 0 else "🔴 Неактивен"

        message = (
            "📊 Ваш абонемент\n\n"
            f"👤 {name}\n"
            f"📊 Статус: {status}\n"
            f"🎟 Осталось посещений: {visits_left}\n"
            f"📅 Абонемент до: {end_date}\n"
            f"⏳ Осталось дней: {max(0, days_left)}"
        )

        if last_visit:
            message += f"\n🕐 Последнее посещение: {last_visit}"
        if goal:
            message += f"\n🎯 Цель: {goal}"
        if level:
            message += f"\n💪 Уровень: {level}"
        if days:
            message += f"\n📆 Дни тренировок: {days}"

        await msg.answer(message)

    except Exception as e:
        logger.error(f"Ошибка статуса: {e}")
        await msg.answer("❌ Ошибка при получении информации.")


@dp.message(F.text == "📅 План тренировок")
async def show_workout_plan(msg: types.Message) -> None:
    goal, level, days = await fetch_profile(msg.from_user.id)

    if not goal or not level:
        await msg.answer("⚠️ Заполните профиль, чтобы получить персональные рекомендации. Отправьте /start.")
        return

    await msg.answer(build_workout_plan(level, goal, days))


@dp.message(F.text == "🥗 Питание")
async def show_nutrition(msg: types.Message) -> None:
    goal, _, _ = await fetch_profile(msg.from_user.id)

    if not goal:
        await msg.answer("⚠️ Сначала выберите цель тренировок. Отправьте /start.")
        return

    await msg.answer(build_nutrition_advice(goal))


@dp.message(F.text == "📈 Прогресс")
async def progress_menu(msg: types.Message, state: FSMContext) -> None:
    logs = await fetch_progress_logs(msg.from_user.id)

    message = "📈 Отслеживание прогресса\n\nОтправьте ваш текущий вес (в кг), чтобы я записал его."

    if logs:
        message += "\n\nПоследние записи:"
        for logged_at, weight, note in logs:
            note_display = f" — {note}" if note else ""
            weight_display = f"{weight:.1f}" if weight is not None else "—"
            message += f"\n• {logged_at}: {weight_display} кг{note_display}"

    await msg.answer(message)
    await state.set_state(ProgressStates.waiting_for_weight)


@dp.message(ProgressStates.waiting_for_weight)
async def progress_weight(msg: types.Message, state: FSMContext) -> None:
    text = msg.text.replace(",", ".").strip()
    try:
        weight = float(text)
        await state.update_data(weight=weight)
        await msg.answer("Записал вес. Добавьте комментарий или напишите '-' если без комментария.")
        await state.set_state(ProgressStates.waiting_for_note)
    except ValueError:
        await msg.answer("Введите вес числом, например 72.4")


@dp.message(ProgressStates.waiting_for_note)
async def progress_note(msg: types.Message, state: FSMContext) -> None:
    note = msg.text.strip()
    if note == "-":
        note = ""

    data = await state.get_data()
    weight = data.get("weight")

    async with aiosqlite.connect("visits.db") as db:
        await db.execute(
            "INSERT INTO progress_logs (user_id, logged_at, weight, note) VALUES (?, ?, ?, ?)",
            (
                msg.from_user.id,
                datetime.now().strftime("%d.%m.%Y %H:%M"),
                weight,
                note
            )
        )
        await db.commit()

    await state.clear()
    await msg.answer("✅ Прогресс обновлён! Продолжайте в том же духе.")


@dp.message(F.text == "🆔 Мой ID")
async def get_my_id(msg: types.Message) -> None:
    user_id = msg.from_user.id
    await msg.answer(
        f"🆔 Ваш User ID: `{user_id}`\n\nСообщите этот ID администратору для отметки посещений.",
        parse_mode="Markdown"
    )


@dp.message(F.text == "ℹ️ Помощь")
async def help_cmd(msg: types.Message) -> None:
    help_text = (
        "ℹ️ Помощь по боту:\n\n"
        "📊 Мой абонемент — статус абонемента и данные профиля\n"
        "📅 План тренировок — персональный план под ваши цели\n"
        "🥗 Питание — рекомендации по рациону\n"
        "📈 Прогресс — обновление веса и заметок\n"
        "🆔 Мой ID — ваш идентификатор для администратора\n"
        "ℹ️ Помощь — это сообщение\n\n"
        "Для отметки посещения сообщите свой ID администратору."
    )
    await msg.answer(help_text)


# --- Админ команды ---
@dp.message(F.text == "📋 Список клиентов")
async def list_clients(msg: types.Message) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    try:
        async with aiosqlite.connect("visits.db") as db:
            async with db.execute(
                "SELECT user_id, name, visits_left, end_date, fitness_goal FROM clients ORDER BY name"
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await msg.answer("📭 Клиентов пока нет")
            return

        text = "📋 Список клиентов:\n\n"
        for user_id, name, visits_left, end_date, goal in rows:
            status = "✅" if visits_left > 0 else "❌"
            goal_info = f"🎯 {goal}\n" if goal else ""
            text += (
                f"{status} {name} (ID: {user_id})\n"
                f"   🎟 {visits_left} посещ., до {end_date}\n"
                f"   {goal_info}\n"
            )

        await msg.answer(text)

    except Exception as e:
        logger.error(f"Ошибка списка клиентов: {e}")
        await msg.answer("❌ Ошибка при получении списка клиентов.")


@dp.message(F.text == "📊 Статистика")
async def show_stats(msg: types.Message) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    try:
        async with aiosqlite.connect("visits.db") as db:
            async with db.execute("SELECT COUNT(*) FROM clients") as cursor:
                total = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM clients WHERE visits_left > 0 AND end_date >= date('now')"
            ) as cursor:
                active = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM progress_logs") as cursor:
                progress_total = (await cursor.fetchone())[0]

        stats_text = (
            "📊 Статистика зала\n\n"
            f"👥 Всего клиентов: {total}\n"
            f"✅ Активных: {active}\n"
            f"🗒 Записей прогресса: {progress_total}\n"
            f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        await msg.answer(stats_text)

    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await msg.answer("❌ Ошибка при получении статистики.")


@dp.message(F.text == "👤 Добавить клиента")
async def add_client_start(msg: types.Message, state: FSMContext) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    await msg.answer("👤 Отправьте User ID клиента:", reply_markup=get_cancel_kb())
    await state.set_state(AddClientStates.waiting_for_user_id)


@dp.message(F.text == "✅ Отметить посещение")
async def manual_visit_start(msg: types.Message, state: FSMContext) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    await msg.answer("Введите User ID клиента для отметки посещения:", reply_markup=get_cancel_kb())
    await state.update_data(action="mark_visit")
    await state.set_state(AddClientStates.waiting_for_user_id)


@dp.message(F.text == "❌ Отмена")
async def cancel_handler(msg: types.Message, state: FSMContext) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    current_state = await state.get_state()
    if current_state is None:
        return

    await state.clear()
    await msg.answer("❌ Действие отменено", reply_markup=get_admin_kb())


@dp.message(AddClientStates.waiting_for_user_id)
async def process_user_id(msg: types.Message, state: FSMContext) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    if msg.text == "❌ Отмена":
        await state.clear()
        await msg.answer("❌ Действие отменено", reply_markup=get_admin_kb())
        return

    user_id_text = msg.text.strip()

    if not re.match(r"^\d+$", user_id_text):
        await msg.answer("❌ User ID должен содержать только цифры. Попробуйте еще раз:", reply_markup=get_cancel_kb())
        return

    user_id = int(user_id_text)

    data = await state.get_data()
    action = data.get("action")

    if action == "mark_visit":
        await mark_visit(user_id, msg)
        await state.clear()
        await msg.answer("Выберите следующее действие", reply_markup=get_admin_kb())
        return

    async with aiosqlite.connect("visits.db") as db:
        async with db.execute("SELECT name FROM clients WHERE user_id=?", (user_id,)) as cursor:
            existing_client = await cursor.fetchone()

    if existing_client:
        await msg.answer(
            f"❌ Клиент с ID {user_id} уже существует: {existing_client[0]}",
            reply_markup=get_admin_kb()
        )
        await state.clear()
        return

    await state.update_data(user_id=user_id)
    await msg.answer("✅ User ID принят. Теперь отправьте имя клиента:", reply_markup=get_cancel_kb())
    await state.set_state(AddClientStates.waiting_for_name)


@dp.message(AddClientStates.waiting_for_name)
async def process_client_name(msg: types.Message, state: FSMContext) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    if msg.text == "❌ Отмена":
        await state.clear()
        await msg.answer("❌ Добавление клиента отменено", reply_markup=get_admin_kb())
        return

    name = msg.text.strip()

    if len(name) < 2:
        await msg.answer("❌ Имя слишком короткое. Введите корректное имя:", reply_markup=get_cancel_kb())
        return

    data = await state.get_data()
    user_id = data["user_id"]

    try:
        async with aiosqlite.connect("visits.db") as db:
            await db.execute(
                "INSERT INTO clients (user_id, name, visits_left, end_date, registration_date) VALUES (?, ?, ?, ?, ?)",
                (
                    user_id,
                    name,
                    12,
                    (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                    datetime.now().strftime("%Y-%m-%d")
                )
            )
            await db.commit()

        success_msg = (
            "✅ Клиент успешно добавлен!\n\n"
            f"👤 Имя: {name}\n"
            f"🆔 User ID: {user_id}\n"
            "🎟 Посещений: 12\n"
            f"📅 Абонемент до: {(datetime.now() + timedelta(days=30)).strftime('%d.%m.%Y')}"
        )
        await msg.answer(success_msg, reply_markup=get_admin_kb())

        try:
            await bot.send_message(
                user_id,
                "🎉 Добро пожаловать! Вы были добавлены в систему.\n"
                "👤 Используйте команду /start, чтобы завершить настройку профиля.",
                reply_markup=get_client_kb()
            )
        except Exception:
            await msg.answer("⚠️ Клиент добавлен, но не удалось отправить сообщение.")

    except Exception as e:
        logger.error(f"Ошибка добавления клиента: {e}")
        await msg.answer("❌ Ошибка при добавлении клиента.")

    await state.clear()


@dp.message(Command("get_id"))
async def get_id_cmd(msg: types.Message) -> None:
    user_id = msg.from_user.id
    await msg.answer(f"🆔 Ваш User ID: `{user_id}`", parse_mode="Markdown")


@dp.message(Command("broadcast"))
async def broadcast(msg: types.Message) -> None:
    if msg.from_user.id != ADMIN_ID:
        return

    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Использование: /broadcast текст сообщения")
        return

    text = parts[1]
    sent = 0
    async with aiosqlite.connect("visits.db") as db:
        async with db.execute("SELECT user_id FROM clients") as cursor:
            recipients = await cursor.fetchall()

    for (user_id,) in recipients:
        try:
            await bot.send_message(user_id, f"📢 Сообщение от тренера:\n\n{text}")
            sent += 1
        except Exception as exc:
            logger.warning(f"Не удалось отправить рассылку пользователю {user_id}: {exc}")

    await msg.answer(f"✅ Сообщение отправлено {sent} пользователям.")


# --- Запуск бота ---
async def main() -> None:
    logger.info("🚀 Запуск бота...")

    await bot.delete_webhook(drop_pending_updates=True)

    await init_db()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
