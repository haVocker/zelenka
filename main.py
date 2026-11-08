import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID_STR = os.getenv("ADMIN_ID", "0")

try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    ADMIN_ID = 0

logging.basicConfig(level=logging.INFO)

if not BOT_TOKEN:
    raise ValueError("В файле .env не указан BOT_TOKEN!")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class VPNStates(StatesGroup):
    waiting_for_promocode = State()

# --- НАСТРОЙКИ КАНАЛА ---
CHANNEL_ID = "@zelenkavpn"
CHANNEL_URL = "https://t.me/zelenkavpn"

# ==========================================
# БАЗА ДАННЫХ (SQLite)
# ==========================================
DB_PATH = "bot_database.db"

def init_db():
    """Создает базу данных и таблицу при первом запуске."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            terms_accepted INTEGER DEFAULT 0,
            subscribed INTEGER DEFAULT 0,
            trial_used INTEGER DEFAULT 0,
            balance REAL DEFAULT 0.0,
            sub_end TEXT,
            history TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id):
    """Получает данные пользователя из базы."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            "user_id": row[0],
            "terms_accepted": bool(row[1]),
            "subscribed": bool(row[2]),
            "trial_used": bool(row[3]),
            "balance": row[4],
            "sub_end": row[5],
            "history": row[6].split("|") if row[6] else []
        }
    else:
        # Создаем нового пользователя
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
        return {
            "user_id": user_id, "terms_accepted": False, "subscribed": False,
            "trial_used": False, "balance": 0.0, "sub_end": None, "history": []
        }

def update_user_field(user_id, field, value):
    """Обновляет одно поле у пользователя."""
    # Для списка истории объединяем через |
    if field == "history" and isinstance(value, list):
        value = "|".join(value)
    elif field == "terms_accepted" or field == "subscribed" or field == "trial_used":
        value = 1 if value else 0
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(f"UPDATE users SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

# Инициализация базы при старте
init_db()

# --- ТЕКСТ ГЛАВНОГО МЕНЮ ---
def get_main_menu_text():
    return (
        "<b>ZELENKA VPN</b>\n\n"
        "Быстро. Надежно. Анонимно.\n\n"
        "Добро пожаловать в ZELENKA VPN!\n\n"
        "Быстрое подключение.\n"
        "Твои данные в надежных руках.\n"
        "Анонимный интернет.\n\n"
        "Подключайся и будь свободен!\n"
        "Выбирай кнопку ниже!"
    )

# ==========================================
# КЛАВИАТУРЫ
# ==========================================

def subscription_kb():
    kb = [
        [InlineKeyboardButton(text="📢 Подписаться", url=CHANNEL_URL, style="primary")],
        [InlineKeyboardButton(text="✅ Проверить", callback_data="check_subscription", style="success")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def terms_kb():
    kb = [
        [
            InlineKeyboardButton(text="📜 Условия", url="https://telegra.ph/PUBLICHNAYA-OFERTA-08-12-15", style="primary"),
            InlineKeyboardButton(text="🔒 Приватность", url="https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-12-99", style="primary")
        ],
        [InlineKeyboardButton(text="⚖️ Политика сервиса", url="https://telegra.ph/Politika-servisa-11-07", style="primary")],
        [InlineKeyboardButton(text="💸 Условия возврата", url="https://telegra.ph/Uslovie-vozvrata-11-07", style="primary")],
        [InlineKeyboardButton(text="✅ Принять", callback_data="accept_terms", style="success")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def main_menu_kb():
    kb = [
        [InlineKeyboardButton(text="🎁 Попробовать · 3 дн. бесплатно", callback_data="trial", style="success")],
        [InlineKeyboardButton(text="⚡️ Подключиться", callback_data="connect", style="primary")],
        [
            InlineKeyboardButton(text="📅 Тарифы", callback_data="tariffs", style="primary"),
            InlineKeyboardButton(text="💳 Личный кабинет", callback_data="profile", style="primary")
        ],
        [InlineKeyboardButton(text="💡 О сервисе", callback_data="about", style="primary")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def connect_menu_kb():
    kb = [
        [InlineKeyboardButton(text="🔑 Ключи", callback_data="keys", style="primary")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="instructions", style="primary")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def instructions_kb():
    kb = [
        [
            InlineKeyboardButton(text="🤖 Android", callback_data="instr_android", style="primary"),
            InlineKeyboardButton(text="🍏 iOS", callback_data="instr_ios", style="primary")
        ],
        [
            InlineKeyboardButton(text="💻 Windows", callback_data="instr_windows", style="primary"),
            InlineKeyboardButton(text="🖥 macOS", callback_data="instr_macos", style="primary")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="connect", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def tariffs_menu_kb():
    kb = [
        [InlineKeyboardButton(text="⭐️ Неделя — 39 ₽", callback_data="buy_week", style="primary")],
        [InlineKeyboardButton(text="⭐️ Месяц — 139 ₽", callback_data="buy_month", style="primary")],
        [InlineKeyboardButton(text="⭐️ 3 месяца — 369 ₽", callback_data="buy_3months", style="primary")],
        [InlineKeyboardButton(text="⭐️ 6 месяцев — 669 ₽", callback_data="buy_6months", style="primary")],
        [InlineKeyboardButton(text="⭐️ 1 год — 1199 ₽", callback_data="buy_year", style="primary")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def profile_kb():
    kb = [
        [InlineKeyboardButton(text="📦 Мои подписки", callback_data="my_subs", style="primary")],
        [
            InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up", style="primary"),
            InlineKeyboardButton(text="🎟 Промокод", callback_data="promo", style="primary")
        ],
        [InlineKeyboardButton(text="📜 История операций", callback_data="history", style="primary")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def about_menu_kb():
    kb = [
        [
            InlineKeyboardButton(text="📜 Условия", url="https://telegra.ph/PUBLICHNAYA-OFERTA-08-12-15", style="primary"),
            InlineKeyboardButton(text="🔒 Приватность", url="https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-12-99", style="primary")
        ],
        [InlineKeyboardButton(text="⚖️ Политика сервиса", url="https://telegra.ph/Politika-servisa-11-07", style="primary")],
        [InlineKeyboardButton(text="💸 Условия возврата", url="https://telegra.ph/Uslovie-vozvrata-11-07", style="primary")],
        [InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/zelenkahelp", style="primary")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main", style="danger")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_to_tariffs_kb():
    kb = [[InlineKeyboardButton(text="⬅️ Назад", callback_data="tariffs", style="danger")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_to_profile_kb():
    kb = [[InlineKeyboardButton(text="⬅️ Назад", callback_data="profile", style="danger")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_to_connect_kb():
    kb = [[InlineKeyboardButton(text="⬅️ Назад", callback_data="connect", style="danger")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_to_main_kb():
    kb = [[InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="back_to_main", style="danger")]]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# --- ФУНКЦИИ ДЛЯ ОТРИСОВКИ ЭКРАНОВ ---

async def show_main_menu(target, state: FSMContext = None):
    if state:
        await state.clear()
    text = get_main_menu_text()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")

async def show_profile(target, user_id):
    user = get_user(user_id)
    balance = user.get("balance", 0.0)
    subscribed = user.get("subscribed", False)
    sub_end = user.get("sub_end", "Нет активной подписки")
    status_text = "Активна" if subscribed else "Не активна"
    
    text = (
        f"<b>Личный кабинет</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Ваш ID:</b> <code>{user_id}</code>\n"
        f"<b>Баланс:</b> {balance} ₽\n"
        f"<b>Подписка:</b> {status_text}\n"
        f"<b>Действует до:</b> {sub_end}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Выберите действие:"
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=profile_kb(), parse_mode="HTML")
    else:
        await target.answer(text, reply_markup=profile_kb(), parse_mode="HTML")


# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest:
        return False


# --- ХЕНДЛЕРЫ ---

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = get_user(user_id) # Получаем данные из БД
    
    # 1. Проверяем подписку
    if not await is_subscribed(user_id):
        await message.answer(
            "<b>Для использования бота подпишитесь на наш канал!</b>\n\n"
            "Нажмите «Подписаться», а затем «Проверить».",
            reply_markup=subscription_kb(),
            parse_mode="HTML"
        )
        return
    
    # 2. Проверяем, принял ли пользователь правила (берем из БД)
    if not user.get("terms_accepted"):
        await message.answer(
            "<b>Правила и политики</b>\n\n"
            "Пожалуйста, ознакомьтесь с документами ниже, а затем нажмите «Принять».",
            reply_markup=terms_kb(),
            parse_mode="HTML"
        )
        return

    # 3. Если всё ок — показываем меню
    await show_main_menu(message, state)

@dp.callback_query(F.data == "check_subscription")
async def process_check_subscription(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if await is_subscribed(user_id):
        if not user.get("terms_accepted"):
            await callback.message.edit_text(
                "<b>Правила и политики</b>\n\n"
                "Пожалуйста, ознакомьтесь с документами ниже, а затем нажмите «Принять».",
                reply_markup=terms_kb(),
                parse_mode="HTML"
            )
        else:
            await show_main_menu(callback, state)
    else:
        await callback.answer(
            "Вы еще не подписались на канал! Пожалуйста, подпишитесь и попробуйте снова.",
            show_alert=True
        )

@dp.callback_query(F.data == "accept_terms")
async def process_accept_terms(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    # ВАЖНО: Сохраняем принятие правил в базу данных
    update_user_field(user_id, "terms_accepted", True)
    
    await show_main_menu(callback, state)

@dp.callback_query(F.data == "back_to_main")
async def process_back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not await is_subscribed(user_id):
        await callback.message.edit_text(
            "<b>Для использования бота подпишитесь на наш канал!</b>",
            reply_markup=subscription_kb(),
            parse_mode="HTML"
        )
        await callback.answer("Вы отписались от канала!", show_alert=True)
        return
    
    if not user.get("terms_accepted"):
         await callback.message.edit_text(
            "<b>Правила и политики</b>\n\n"
            "Пожалуйста, ознакомьтесь с документами ниже, а затем нажмите «Принять».",
            reply_markup=terms_kb(),
            parse_mode="HTML"
        )
         await callback.answer("Пожалуйста, примите правила.", show_alert=True)
         return

    await show_main_menu(callback, state)
    await callback.answer()


# --- ПОДПУНКТЫ "ПОДКЛЮЧИТЬСЯ" ---

@dp.callback_query(F.data == "connect")
async def process_connect_menu(callback: CallbackQuery):
    text = "<b>Подключение</b>\n\nВыберите нужный раздел:"
    await callback.message.edit_text(text, reply_markup=connect_menu_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "keys")
async def process_keys(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user.get("subscribed"):
        text = (
            "<b>Ваши ключи</b>\n\n"
            "У вас пока нет активных ключей.\n"
            "Активируйте пробный период или приобретите тариф."
        )
    else:
        fake_vpn_key = "vless://active-uuid@your-server:443?type=tcp&security=reality#ZelenkaVPN_Active"
        text = (
            "<b>Ваши ключи</b>\n\n"
            f"<b>Ваш VPN ключ:</b>\n<code>{fake_vpn_key}</code>\n\n"
            "Скопируйте его и вставьте в приложение."
        )
    await callback.message.edit_text(text, reply_markup=back_to_connect_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "instructions")
async def process_instructions(callback: CallbackQuery):
    text = (
        "<b>Инструкция по подключению</b>\n\n"
        "Выберите вашу операционную систему, чтобы узнать, как настроить VPN."
    )
    await callback.message.edit_text(text, reply_markup=instructions_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "instr_android")
async def process_instr_android(callback: CallbackQuery):
    text = (
        "<b>Инструкция для Android</b>\n\n"
        "1. Скачайте приложение <b>v2rayNG</b> из Google Play или с GitHub.\n"
        "2. Откройте приложение и нажмите на значок «+» в правом верхнем углу.\n"
        "3. Выберите «Импорт из буфера обмена» (ваш ключ уже скопирован).\n"
        "4. Нажмите на название добавленного профиля, чтобы подключиться.\n\n"
        "Ссылка на скачивание: https://play.google.com/store/apps/details?id=com.v2ray.ang"
    )
    await callback.message.edit_text(text, reply_markup=instructions_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "instr_ios")
async def process_instr_ios(callback: CallbackQuery):
    text = (
        "<b>Инструкция для iOS</b>\n\n"
        "1. Скачайте приложение <b>Streisand</b> из App Store.\n"
        "2. Откройте приложение и нажмите на значок «+» в правом верхнем углу.\n"
        "3. Выберите «Добавить из буфера обмена».\n"
        "4. Нажмите «Подключить» на главном экране.\n\n"
        "Ссылка на скачивание: https://apps.apple.com/app/streisand/id6450534064"
    )
    await callback.message.edit_text(text, reply_markup=instructions_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "instr_windows")
async def process_instr_windows(callback: CallbackQuery):
    text = (
        "<b>Инструкция для Windows</b>\n\n"
        "1. Скачайте приложение <b>v2rayN</b> с GitHub.\n"
        "2. Распакуйте архив в любую папку и запустите v2rayN.exe.\n"
        "3. Нажмите «Серверы» -> «Импорт из буфера обмена».\n"
        "4. Нажмите правой кнопкой мыши на добавленный сервер и выберите «Установить как системный прокси».\n\n"
        "Ссылка на скачивание: https://github.com/2dust/v2rayN/releases"
    )
    await callback.message.edit_text(text, reply_markup=instructions_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "instr_macos")
async def process_instr_macos(callback: CallbackQuery):
    text = (
        "<b>Инструкция для macOS</b>\n\n"
        "1. Скачайте приложение <b>V2Box</b> из App Store (или с официального сайта).\n"
        "2. Откройте приложение.\n"
        "3. Нажмите на значок «+» и выберите «Импорт из буфера обмена».\n"
        "4. Переключите тумблер в положение «Вкл» для подключения.\n\n"
        "Ссылка на скачивание: https://apps.apple.com/app/v2box-v2ray-client/id6446814690"
    )
    await callback.message.edit_text(text, reply_markup=instructions_kb(), parse_mode="HTML")
    await callback.answer()

# --- ОСТАЛЬНЫЕ ХЕНДЛЕРЫ ---

@dp.callback_query(F.data == "tariffs")
async def process_tariffs(callback: CallbackQuery):
    text = "<b>Наши тарифы</b>\n\nВыберите подходящий период подписки:"
    await callback.message.edit_text(text, reply_markup=tariffs_menu_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def process_profile(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_profile(callback, callback.from_user.id)
    await callback.answer()

@dp.callback_query(F.data == "about")
async def process_about(callback: CallbackQuery):
    text = "<b>О сервисе ZELENKA VPN</b>\n\nВыберите интересующий вас раздел:"
    await callback.message.edit_text(text, reply_markup=about_menu_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "my_subs")
async def process_my_subs(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if not user.get("subscribed"):
        text = (
            "<b>Мои подписки</b>\n\n"
            "У вас пока нет активных подписок.\n"
            "Вы можете активировать пробный период или приобрести тариф в главном меню."
        )
    else:
        fake_vpn_key = "vless://active-uuid@your-server:443?type=tcp&security=reality#ZelenkaVPN"
        text = (
            "<b>Мои подписки</b>\n\n"
            "<b>Статус:</b> Активна\n"
            f"<b>Действует до:</b> {user.get('sub_end')}\n\n"
            f"<b>Ваш VPN ключ:</b>\n<code>{fake_vpn_key}</code>"
        )
    await callback.message.edit_text(text, reply_markup=back_to_profile_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "top_up")
async def process_top_up(callback: CallbackQuery):
    text = (
        "<b>Пополнение баланса</b>\n\n"
        "Выберите удобный способ оплаты (в разработке):\n"
        "• Банковская карта\n"
        "• СБП\n"
        "• Криптовалюта\n\n"
        "Сейчас для пополнения напишите в поддержку."
    )
    await callback.message.edit_text(text, reply_markup=back_to_profile_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "promo")
async def process_promo(callback: CallbackQuery, state: FSMContext):
    await state.set_state(VPNStates.waiting_for_promocode)
    text = (
        "<b>Ввод промокода</b>\n\n"
        "Пожалуйста, отправьте промокод в чат.\n"
        "Для отмены нажмите на кнопку ниже."
    )
    await callback.message.edit_text(text, reply_markup=back_to_profile_kb(), parse_mode="HTML")
    await callback.answer()

@dp.message(VPNStates.waiting_for_promocode)
async def handle_promocode(message: Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    
    if code == "ZELENKA2024":
        user = get_user(user_id)
        new_balance = user.get("balance", 0.0) + 100.0
        update_user_field(user_id, "balance", new_balance)
        
        history = user.get("history", [])
        history.append("Активация промокода ZELENKA2024 (+100 руб.)")
        update_user_field(user_id, "history", history)
        
        await message.answer("<b>Промокод успешно активирован!</b>\n\nВам начислено 100 руб. на баланс.", parse_mode="HTML")
    else:
        await message.answer("<b>Неверный промокод</b> или срок его действия истек.", parse_mode="HTML")
    
    await state.clear()
    await show_profile(message, user_id)

@dp.callback_query(F.data == "history")
async def process_history(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    history = user.get("history", [])
    
    if not history:
        text = "<b>История операций</b>\n\nВаша история пока пуста."
    else:
        history_text = "\n".join([f"• {item}" for item in history])
        text = f"<b>История операций</b>\n\n{history_text}"
        
    await callback.message.edit_text(text, reply_markup=back_to_profile_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_tariff(callback: CallbackQuery):
    tariff_key = callback.data.replace("buy_", "")
    
    tariffs = {
        "week": {"name": "Неделя", "price": "39 руб."},
        "month": {"name": "Месяц", "price": "139 руб."},
        "3months": {"name": "3 месяца", "price": "369 руб."},
        "6months": {"name": "6 месяцев", "price": "669 руб."},
        "year": {"name": "1 год", "price": "1199 руб."},
    }
    
    selected = tariffs.get(tariff_key)
    
    if selected:
        text = (
            f"<b>Вы выбрали тариф:</b> {selected['name']}\n"
            f"<b>Стоимость:</b> {selected['price']}\n\n"
            f"Для оформления подписки, пожалуйста, перейдите в поддержку: @zelenkahelp\n\n"
            f"<i>(В будущем здесь появится кнопка автоматической оплаты)</i>"
        )
        await callback.message.edit_text(text, reply_markup=back_to_tariffs_kb(), parse_mode="HTML")
    else:
        await callback.answer("Тариф не найден", show_alert=True)
    
    await callback.answer()

@dp.callback_query(F.data == "trial")
async def process_trial(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = get_user(user_id)
    
    if user.get("trial_used"):
        await callback.message.edit_text("Вы уже использовали пробный период.", reply_markup=back_to_main_kb())
    else:
        update_user_field(user_id, "trial_used", True)
        update_user_field(user_id, "subscribed", True)
        update_user_field(user_id, "sub_end", "через 3 дня")
        
        fake_vpn_key = "vless://trial-uuid@your-server:443?type=tcp&security=reality#ZelenkaVPN_Trial"
        await callback.message.edit_text(
            f"<b>Пробный период активирован!</b>\n\nВаш ключ на 3 дня:\n<code>{fake_vpn_key}</code>",
            reply_markup=back_to_main_kb(), parse_mode="HTML"
        )
    await callback.answer()

@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет прав для использования этой команды.")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE subscribed = 1")
    active_subs = cursor.fetchone()[0]
    conn.close()
    
    text = (
        f"<b>Админ-панель</b>\n\n"
        f"Всего пользователей: {total_users}\n"
        f"Активных подписок: {active_subs}"
    )
    await message.answer(text, parse_mode="HTML")


async def main():
    print("Бот запущен...")
    # Файл базы данных создастся автоматически
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())