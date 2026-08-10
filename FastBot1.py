import asyncio
import logging
import os
import sqlite3
from html import escape
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    LabeledPrice,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder
BOT_TOKEN = os.getenv("8638068274:AAFIk6QdGkszQsybzdyqSkVmqA7-W9ZTouU")

ADMIN_IDS = {7543852010, 418350122}
PRIMARY_ADMIN_USERNAME = "@Fast_gamer_uz"

PREVIEW_COST = 1000
REF_REWARD = 5

GAME_URL = "https://t.me/FastPrevyuBotShashkaGame.Replit.app"
GROUP_URL = "https://t.me/Fast_prevyu_bot?startgroup=true"
BOT_USERNAME = "Fast_Prevyu_Bot"

PROMO_CODES = {
    "FAST",
    "FAST_GAMER_UZ",
    "FAST_GAMER",
    "PREVYU",
    "FAST_PREVYU_BOT",
    "FAST_PREVYU",
    "FASTZO'R",
    "FASTGAOBUNABOL",
}

DB_PATH = "fastbot.sqlite3"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
router = Router()
dp.include_router(router)


# ============================================================
# FSM states
# ============================================================

class UserStates(StatesGroup):
    waiting_preview = State()
    waiting_promo = State()


# ============================================================
# Database
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            stars INTEGER NOT NULL DEFAULT 0,
            referred_by INTEGER,
            referred_rewarded INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS promo_used (
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            used_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(user_id, code)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS preview_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER PRIMARY KEY,
            rating INTEGER NOT NULL DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS custom_buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            row INTEGER NOT NULL DEFAULT 0,
            position INTEGER NOT NULL DEFAULT 0,
            function TEXT,
            color TEXT
        )
    """)

    # Doimiy asosiy adminlar
    for admin_id in ADMIN_IDS:
        username = PRIMARY_ADMIN_USERNAME if admin_id == 7543852010 else ""
        cur.execute(
            "INSERT OR IGNORE INTO admins(user_id, username) VALUES (?, ?)",
            (admin_id, username),
        )

    conn.commit()
    conn.close()


def ensure_user(tg_user):
    conn = db()
    cur = conn.cursor()

    row = cur.execute(
        "SELECT user_id FROM users WHERE user_id=?",
        (tg_user.id,),
    ).fetchone()

    if not row:
        cur.execute(
            """
            INSERT INTO users(user_id, username, first_name)
            VALUES (?, ?, ?)
            """,
            (
                tg_user.id,
                tg_user.username or "",
                tg_user.first_name or "",
            ),
        )
    else:
        cur.execute(
            """
            UPDATE users
            SET username=?, first_name=?
            WHERE user_id=?
            """,
            (
                tg_user.username or "",
                tg_user.first_name or "",
                tg_user.id,
            ),
        )

    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = db()
    row = conn.execute(
        "SELECT * FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row


def get_all_user_ids():
    conn = db()
    rows = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    return [row["user_id"] for row in rows]


def is_admin(user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True

    conn = db()
    row = conn.execute(
        "SELECT 1 FROM admins WHERE user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()

    return bool(row)


def add_balance(user_id: int, amount: int):
    conn = db()
    conn.execute(
        "UPDATE users SET balance=MAX(0, balance+?) WHERE user_id=?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


def set_balance(user_id: int, amount: int):
    conn = db()
    conn.execute(
        "UPDATE users SET balance=? WHERE user_id=?",
        (max(0, amount), user_id),
    )
    conn.commit()
    conn.close()


def deduct_balance(user_id: int, amount: int) -> bool:
    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE users
        SET balance=balance-?
        WHERE user_id=? AND balance>=?
        """,
        (amount, user_id, amount),
    )

    ok = cur.rowcount == 1
    conn.commit()
    conn.close()

    return ok


def set_referrer_if_empty(user_id: int, referrer_id: int):
    conn = db()

    row = conn.execute(
        "SELECT referred_by FROM users WHERE user_id=?",
        (user_id,),
    ).fetchone()

    if row and row["referred_by"] is None and user_id != referrer_id:
        conn.execute(
            "UPDATE users SET referred_by=? WHERE user_id=?",
            (referrer_id, user_id),
        )
        conn.commit()
        conn.close()
        return True

    conn.close()
    return False


def reward_referrer_if_needed(user_id: int):
    conn = db()

    row = conn.execute(
        """
        SELECT referred_by, referred_rewarded
        FROM users
        WHERE user_id=?
        """,
        (user_id,),
    ).fetchone()

    if (
        not row
        or not row["referred_by"]
        or row["referred_rewarded"]
    ):
        conn.close()
        return None

    referrer_id = row["referred_by"]

    conn.execute(
        """
        UPDATE users
        SET balance=balance+?, referred_rewarded=1
        WHERE user_id=?
        """,
        (REF_REWARD, user_id),
    )

    conn.execute(
        "UPDATE users SET balance=balance+? WHERE user_id=?",
        (REF_REWARD, referrer_id),
    )

    conn.commit()
    conn.close()

    return referrer_id


# ============================================================
# Keyboards
# ============================================================

def main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.add(
        KeyboardButton(text="⭐ Prevyu yasash ⭐")
    )

    kb.row(
        KeyboardButton(text="🎁 Promo kod 🎁"),
        KeyboardButton(text="💳 Balans to‘ldirish 💳"),
    )

    kb.row(
        KeyboardButton(text="🎮 O‘yinlar"),
        KeyboardButton(text="➕ Guruhga qo‘shish ➕"),
    )

    # Bu tugma faqat adminlarga ko'rinadi.
    if is_admin(user_id):
        kb.row(
            KeyboardButton(text="⛓️‍💥 Admin Sozlamalar ⚙️")
        )

    return kb.as_markup(resize_keyboard=True)


def games_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="♟️ Shashka"),
        KeyboardButton(text="🎲 Minecraft"),
        KeyboardButton(text="🔘 Omad doirasi"),
    )

    kb.row(KeyboardButton(text="⬅️ Menyu"))

    return kb.as_markup(resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()

    kb.row(
        KeyboardButton(text="/users"),
        KeyboardButton(text="/Admin user"),
    )
    kb.row(
        KeyboardButton(text="/NewAdmins"),
        KeyboardButton(text="/DeleteAdmin"),
    )
    kb.row(
        KeyboardButton(text="/Rating"),
        KeyboardButton(text="/broadcast"),
    )
    kb.row(
        KeyboardButton(text="/Onemessage"),
        KeyboardButton(text="/Userprofile"),
    )
    kb.row(
        KeyboardButton(text="/UserUsername"),
        KeyboardButton(text="/Buttoneditor"),
    )
    kb.row(
        KeyboardButton(text="/ButtonsName"),
        KeyboardButton(text="/NewButton"),
    )
    kb.row(
        KeyboardButton(text="/ButtonColor"),
        KeyboardButton(text="/DaletButton"),
    )
    kb.row(
        KeyboardButton(text="/ButtonFunction"),
        KeyboardButton(text="/ButtonFunctionDalet"),
    )
    kb.row(
        KeyboardButton(text="/BalanceDeleteAll"),
        KeyboardButton(text="/BalanceDalete1"),
    )
    kb.row(
        KeyboardButton(text="/Balancing"),
        KeyboardButton(text="/AllHumansBalans1"),
    )
    kb.row(
        KeyboardButton(text="/NewWindowButton"),
        KeyboardButton(text="/IdendUser"),
    )
    kb.row(KeyboardButton(text="/RandomHuman"))
    kb.row(KeyboardButton(text="⬅️ Menyu"))

    return kb.as_markup(resize_keyboard=True)


# ============================================================
# Helpers
# ============================================================

def display_username(row) -> str:
    if row["username"]:
        return "@" + row["username"].lstrip("@")
    return row["first_name"] or str(row["user_id"])


def start_text(user_id: int) -> str:
    row = get_user(user_id)
    username = display_username(row)

    return (
        f"👋 💎 <b>Salom {escape(username)} 💎</b>\n\n"
        f"🔥 <b>@Fast_prevyu_bot ga xush kelibsiz</b> 🔥\n\n"
        f"⭐ <b>Iltimos menyudan foydalaning va "
        f"o‘z prevyuyingizni tayyorlang</b> ⭐"
    )


async def resolve_user(arg: str) ->
Optional[int]:
    arg = arg.strip()

    if not arg:
        return None

    if arg.startswith("@"):
        username = arg[1:].lower()

        conn = db()
        row = conn.execute(
            "SELECT user_id FROM users WHERE lower(username)=?",
            (username,),
        ).fetchone()
        conn.close()

        return row["user_id"] if row else None

    try:
        return int(arg)
    except ValueError:
        return None


# ============================================================
# START
# ============================================================

@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject):
    ensure_user(message.from_user)

    # /start REFERRER_ID
    if command.args:
        try:
            referrer_id = int(command.args.strip())

            if (
                referrer_id != message.from_user.id
                and get_user(referrer_id)
            ):
                set_referrer_if_empty(
                    message.from_user.id,
                    referrer_id,
                )

        except ValueError:
            pass

    # Referral mukofoti bir marta beriladi.
    rewarded = reward_referrer_if_needed(message.from_user.id)

    if rewarded:
        try:
            await bot.send_message(
                rewarded,
                "🎉 Sizning taklif havolangiz orqali yangi "
                "foydalanuvchi kirdi!\n"
                "💎 <b>+5 Balans</b> berildi.",
            )
        except Exception:
            pass

    await message.answer(
        start_text(message.from_user.id),
        reply_markup=main_keyboard(message.from_user.id),
    )


# ============================================================
# MAIN MENU
# ============================================================

@router.message(F.text == "⭐ Prevyu yasash ⭐")
async def preview_start(message: Message, state: FSMContext):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    if row["balance"] < PREVIEW_COST:
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    await state.set_state(UserStates.waiting_preview)

    await message.answer(
        "⭐ <b>Minecraft skiningizni PNG tarzda yuboring.</b>\n\n"
        "💵 Narxi: <b>1000 balans</b>"
    )


@router.message(F.text == "🎁 Promo kod 🎁")
async def promo_start(message: Message, state: FSMContext):
    await state.set_state(UserStates.waiting_promo)
    await message.answer("🎁 <b>Promo kodni yozing:</b>")


@router.message(F.text == "💳 Balans to‘ldirish 💳")
async def balance_topup(message: Message):
    await message.answer(
        "💳 <b>Balans to‘ldirish</b> 💳\n\n"
        f"Admin: <b>{PRIMARY_ADMIN_USERNAME}</b> ga yozing — "
        "pulga balans beradi yoki star ga beradi.\n\n"
        "⭐ Quyida Telegram Stars orqali to‘g‘ridan-to‘g‘ri "
        "star yuborishingiz mumkin:"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ 1 Star yuborish",
                    callback_data="star_1",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐⭐ 2 Star yuborish",
                    callback_data="star_2",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⭐⭐⭐ 3 Star yuborish",
                    callback_data="star_3",
                )
            ],
        ]
    )

    await message.answer(
        "⭐ <b>Star yuborish</b>:",
        reply_markup=kb,
    )


@router.message(F.text == "🎮 O‘yinlar")
async def games(message: Message):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    # O'yinlar hali bot ichiga ulanmagan.
    playing = 0

    await message.answer(
        f"🎮 <b>O'yinlar</b>\n\n"
        f"{escape(display_username(row))}!✅ "
        f"Balansingiz: <b>{row['balance']}</b>\n\n"
        f"✅ <b>O'yinlar nomi:</b>\n"
        f"1. Minecraft\n"
        f"2. Shashka\n"
        f"3. Omad doirasi\n\n"
        f"🟢 Hozir o'ynalmoqda: "
        f"( O'yin o'ynayotgan odamlar soni: "
        f"<b>{playing}</b> kishi )\n\n"
        f"<b>O'yin tanlang: 👇</b>",
        reply_markup=games_keyboard(),
    )


@router.message(F.text == "➕ Guruhga qo‘shish ➕")
async def add_group(message: Message):
    await message.answer(
        "➕ <b>Botni guruhga qo'shish:</b>\n"
        f"{GROUP_URL}"
    )


@router.message(F.text == "⛓️‍💥 Admin Sozlamalar ⚙️")
async def admin_settings(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Siz admin emassiz.")
        return

    await message.answer(
        "⛓️‍💥 <b>Admin Sozlamalari</b>\n\n"
        "/users — Foydalanuvchilar soni\n"
        "/Admin user — Adminlar soni\n"
        "/NewAdmins — Yangi adminlar\n"
        "/DeleteAdmin — Adminlarni o'chirish\n"
        "/Rating — Reyting\n"
        "/broadcast — Hammaga xabar yuborish\n"
        "/Onemessage — Bitta odamga xabar\n"
        "/Userprofile — Foydalanuvchi profili\n"
        "/UserUsername — Foydalanuvchi usernamesi\n"
        "/Buttoneditor — Tugmalar joyi\n"
        "/ButtonsName — Tugmalar nomi\n"
        "/NewButton — Yangi tugma\n"
        "/ButtonColor — Tugmalar rangi\n"
        "/DaletButton — Tugmalar o'chirish\n"
        "/ButtonFunction — Tugmalar funksiyalari\n"
        "/ButtonFunctionDalet — Tugma funksiyasini o'chirish\n"
        "/BalanceDeleteAll — Hammani balansini o'chirish\n"
        "/BalanceDalete1 — Bitta odam balansini o'chirish\n"
        "/Balancing — 1 ta odamga balans berish\n"
        "/AllHumansBalans1 — Hammaga balans berish\n"
        "/NewWindowButton — Yangi oyna\n"
        "/IdendUser — ID orqali foydalanuvchini topish\n"
        "/RandomHuman — Random odam tanlash",
        reply_markup=admin_keyboard(),
    )


@router.message(F.text == "⬅️ Menyu")
async def back_menu(message: Message):
    await message.answer(
        "🏠 <b>Asosiy menyu</b>",
        reply_markup=main_keyboard(message.from_user.id),
    )


# ============================================================
# PROMO / TEXT STATES
# ============================================================

@router.message(UserStates.waiting_promo, F.text)
async def promo_text_router(
    message: Message,
    state: FSMContext,
):
    ensure_user(message.from_user)

    text = message.text.strip()

    if text.startswith("/"):
        await state.clear()
        return

    code = text.upper().strip()
    code = (
        code.replace("’", "'")
        .replace("‘", "'")
        .replace("ʻ", "'")
    )

    if code in PROMO_CODES:
        conn = db()

        already = conn.execute(
            """
            SELECT 1 FROM promo_used
            WHERE user_id=? AND code=?
            """,
            (message.from_user.id, code),
        ).fetchone()

        if already:
            conn.close()
            await state.clear()

            await message.answer(
                "❌ Bu promokoddan siz avval foydalanib bo'lgansiz."
            )
            return

        conn.execute(
            "INSERT INTO promo_used(user_id, code) VALUES (?, ?)",
            (message.from_user.id, code),
        )

        conn.execute(
            "UPDATE users SET balance=balance+5 WHERE user_id=?",
            (message.from_user.id,),
        )

        conn.commit()
        conn.close()

        await state.clear()

        await message.answer(
            "🎉 Promokod qabul qilindi!\n"
            "💎 <b>+5 Balans</b> berildi."
        )
        return

    row = get_user(message.from_user.id)
    username = escape(display_username(row))

    await state.clear()

    await message.answer(
        f"Kechiring {username} brodar siz yozgan "
        f"<b>{escape(text)}</b> bu promokod afsuski 😔 yo'q ❌\n"
        "Boshidan harakat qling."
    )


@router.message(UserStates.waiting_preview, F.text)
async def preview_text_router(
    message: Message,
    state: FSMContext,
):
    await state.clear()
    await message.answer("Bu PNG emas ❌")


@router.message(F.text)
async def text_router(message: Message):
    ensure_user(message.from_user)

    text = message.text.strip()

    if text.startswith("/"):
        return

    if text == "♟️ Shashka":
        await message.answer(
            "♟️ <b>Shashka o'ynash uchun:</b>\n"
            f"{GAME_URL}"
        )
        return

    if text == "🎲 Minecraft":
        await message.answer(
            "🎲 <b>Minecraft</b> o'yini tez orada qo'shiladi."
        )
        return

    if text == "🔘 Omad doirasi":
        await message.answer(
            "🔘 <b>Omad doirasi</b> tez orada qo'shiladi."
        )
        return

    await message.answer(
        "❓ Tushunmadim. Iltimos, menyudagi tugmalardan foydalaning."
    )


# ============================================================
# PREVIEW / SKIN
# ============================================================

@router.message(F.photo)
async def receive_photo(
    message: Message,
    state: FSMContext,
):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    if row["balance"] < PREVIEW_COST:
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    await state.clear()

    await message.answer(
        "⏳ <b>Prevyu tayyorlanmoqda...</b>"
    )

    if not deduct_balance(
        message.from_user.id,
        PREVIEW_COST,
    ):
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    photo = message.photo[-1]

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO preview_orders(user_id, file_id)
        VALUES (?, ?)
        """,
        (message.from_user.id, photo.file_id),
    )

    order_id = cur.lastrowid

    conn.commit()
    conn.close()

    user = get_user(message.from_user.id)
    username = display_username(user)

    caption = (
        "🎮 <b>Yangi Skin</b>\n\n"
        f"<b>Foydalanuvchi Nomi:</b> "
        f"{escape(user['first_name'] or 'Nomaʼlum')}\n"
        f"👤 <b>User:</b> {escape(username)}\n"
        f"🆔 <b>Foydalanuvchi ID:</b> "
        f"<code>{user['user_id']}</code>\n"
        f"💵 <b>Balans:</b> {user['balance']}\n"
        f"🔢 <b>Buyurtma:</b> #{order_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id,
                photo.file_id,
                caption=caption,
            )
        except Exception as e:
            logger.warning(
                "Could not send preview to admin %s: %s",
                admin_id,
                e,
            )


@router.message(F.document)
async def receive_document(
    message: Message,
    state: FSMContext,
):
    ensure_user(message.from_user)

    doc = message.document
    mime = (doc.mime_type or "").lower()
    name = (doc.file_name or "").lower()

    # PNG document bo'lsa qabul qilamiz.
    if mime != "image/png" and not name.endswith(".png"):
        await message.answer("Bu PNG emas ❌")
        return

    row = get_user(message.from_user.id)

    if row["balance"] < PREVIEW_COST:
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    await state.clear()

    await message.answer(
        "⏳ <b>Prevyu tayyorlanmoqda...</b>"
    )

    if not deduct_balance(
        message.from_user.id,
        PREVIEW_COST,
    ):
        await message.answer(
            "Kechiring, lekin sizda yetarlicha balans yo'q ❌"
        )
        return

    conn = db()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO preview_orders(user_id, file_id)
        VALUES (?, ?)
        """,
        (message.from_user.id, doc.file_id),
    )

    order_id = cur.lastrowid

    conn.commit()
    conn.close()

    user = get_user(message.from_user.id)
    username = display_username(user)

    caption = (
        "🎮 <b>Yangi Skin</b>\n\n"
        f"<b>Foydalanuvchi Nomi:</b> "
        f"{escape(user['first_name'] or 'Nomaʼlum')}\n"
        f"👤 <b>User:</b> {escape(username)}\n"
        f"🆔 <b>Foydalanuvchi ID:</b> "
        f"<code>{user['user_id']}</code>\n"
        f"💵 <b>Balans:</b> {user['balance']}\n"
        f"🔢 <b>Buyurtma:</b> #{order_id}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_document(
                admin_id,
                doc.file_id,
                caption=caption,
            )
        except Exception as e:
            logger.warning(
                "Could not send document to admin %s: %s",
                admin_id,
                e,
            )


# ============================================================
# USER COMMANDS
# ============================================================

@router.message(Command("profil"))
async def profile(message: Message):
    ensure_user(message.from_user)

    row = get_user(message.from_user.id)

    await message.answer(
        f"😎 <b>Username:</b> "
        f"{escape(display_username(row))}\n"
        f"💎 <b>ID:</b> <code>{row['user_id']}</code>\n"
        f"💵 <b>Balans:</b> {row['balance']}\n"
        f"⭐ <b>Star:</b> {row['stars']}"
    )


@router.message(Command("yordam"))
async def help_cmd(message: Message):
    await message.answer(
        "🔥 <b>Bot yordam menyusi</b> 🔥\n\n"
        "⭐ <b>Prevyu yasash</b> ⭐\n"
        "💵 Admin orqali maxsus Prevyu buyurtma qilish\n"
        "💎 Promo kod orqali balans olish mumkin\n"
        "✅ Balans to'ldirish uchun admin bilan bog'laning\n"
        "🔗 /Ref — Do'stlaringizni taklif qiling "
        "va har biri uchun 5 Balans oling\n\n"
        "🔘 <b>Botdagi tugmalar:</b>\n"
        "▫️ ⭐ Prevyu yasash ⭐\n"
        "▫️ 🎁 Promo kod 🎁\n"
        "▫️ 💳 Balans to‘ldirish 💳\n"
        "▫️ ➕ Guruhga qo‘shish ➕\n\n"
        f"❤️ <b>Admin:</b> {PRIMARY_ADMIN_USERNAME}"
    )


@router.message(Command("ref", "Ref"))
async def ref_cmd(message: Message):
    ensure_user(message.from_user)

    me = await bot.get_me()
    bot_username = me.username or BOT_USERNAME

    link = (
        f"https://t.me/{bot_username}"
        f"?start={message.from_user.id}"
    )

    await message.answer(
        "⭐️ <b>Bepul Minecraft Prevyu?!</b> "
        "Ha, to'g'ri eshitdingiz!\n"
        "Do'stlaringizni taklif qiling, Balans yig'ing "
        "va Prevyu oling! ☺️\n\n"
        "Har bir taklif qilgan do'stingiz evaziga "
        "<b>5 Balans</b> olasiz.\n\n"
        "🔗 <b>Pastdagi havola orqali "
        "do'stlaringizga ulashing:</b>\n"
        f"{link}"
    )


# ============================================================
# ADMIN COMMANDS
# ============================================================

@router.message(Command("users"))
async def admin_users(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer(
            "❌ Bu buyruq faqat adminlar uchun."
        )
        return

    conn = db()
    count = conn.execute(
        "SELECT COUNT(*) c FROM users"
    ).fetchone()["c"]
    conn.close()

    await message.answer(
        f"👥 <b>Foydalanuvchilar soni:</b> {count}"
    )


@router.message(Command("Admin"))
async def admin_list(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat adminlar.")
        return

    conn = db()
    rows = conn.execute(
        "SELECT * FROM admins ORDER BY user_id"
    ).fetchall()
    conn.close()

    text = f"👑 <b>Adminlar soni ({len(rows)})</b>\n\n"

    for i, row in enumerate(rows, 1):
        name = (
            "@"
            + row["username"].lstrip("@")
            if row["username"]
            else str(row["user_id"])
        )

        text += (
            f"{i}. {escape(name)} — "
            f"<code>{row['user_id']}</code>\n"
        )

    await message.answer(text)


@router.message(Command("NewAdmins"))
async def new_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/NewAdmins ID yoki @username</code>"
        )
        return

    uid = await resolve_user(parts[1])

    if not uid:
        await message.answer(
            "❌ Foydalanuvchi topilmadi. "
            "Avval u botga /start bosgan bo'lishi kerak."
        )
        return

    row = get_user(uid)
    username = row["username"] if row else ""

    conn = db()
    conn.execute(
        """
        INSERT OR REPLACE INTO admins(user_id, username)
        VALUES (?, ?)
        """,
        (uid, username),
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ <code>{uid}</code> admin qilindi."
    )


@router.message(Command("DeleteAdmin"))
async def delete_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/DeleteAdmin ID yoki @username</code>"
        )
        return

    uid = await resolve_user(parts[1])

    if not uid:
        await message.answer("❌ Topilmadi.")
        return

    if uid in ADMIN_IDS:
        await message.answer(
            "❌ Asosiy adminni o'chirib bo'lmaydi."
        )
        return

    conn = db()
    conn.execute(
        "DELETE FROM admins WHERE user_id=?",
        (uid,),
    )
    conn.commit()
    conn.close()

    await message.answer("✅ Admin o'chirildi.")


@router.message(Command("Rating"))
async def rating_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    conn = db()
    rows = conn.execute(
        """
        SELECT u.username, u.first_name,
               r.user_id, r.rating
        FROM ratings r
        LEFT JOIN users u ON u.user_id=r.user_id
        ORDER BY r.rating DESC
        LIMIT 10
        """
    ).fetchall()
    conn.close()

    if not rows:
        await message.answer(
            "⭐ Reyting hali mavjud emas."
        )
        return

    text = "⭐ <b>Top reyting</b>\n\n"

    for i, row in enumerate(rows, 1):
        username = (
            "@"
            + row["username"]
            if row["username"]
            else (
                row["first_name"]
                or str(row["user_id"])
            )
        )

        text += (
            f"{i}. {escape(username)} — "
            f"{row['rating']}\n"
        )

    await message.answer(text)


@router.message(Command("broadcast"))
async def broadcast_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    if not message.reply_to_message:
        await message.answer(
            "📢 Xabarni botga reply qilib "
            "<code>/broadcast</code> yuboring.\n"
            "Rasm, text, GIF, sticker, emoji va "
            "boshqa Telegram media turlari ishlaydi."
        )
        return

    users = get_all_user_ids()
    sent = 0
    failed = 0

    for user_id in users:
        try:
            await message.reply_to_message.copy_to(
                user_id
            )
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 Yuborildi: <b>{sent}</b>\n"
        f"❌ Xato: <b>{failed}</b>"
    )


@router.message(Command("Onemessage"))
async def one_message(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2 or not message.reply_to_message:
        await message.answer(
            "Foydalanish: "
            "<code>/Onemessage ID</code> "
            "va xabarni reply qiling."
        )
        return

    uid = await resolve_user(parts[1])

    if not uid:
        await message.answer(
            "❌ Foydalanuvchi topilmadi."
        )
        return

    try:
        await message.reply_to_message.copy_to(uid)
        await message.answer("✅ Xabar yuborildi.")
    except Exception as e:
        await message.answer(
            f"❌ Yuborilmadi: {escape(str(e))}"
        )


@router.message(Command("Userprofile"))
async def user_profile_admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/Userprofile ID yoki @username</code>"
        )
        return

    uid = await resolve_user(parts[1])
    row = get_user(uid) if uid else None

    if not row:
        await message.answer(
            "❌ Foydalanuvchi topilmadi."
        )
        return

    await message.answer(
        f"😎 <b>Username:</b> "
        f"{escape(display_username(row))}\n"
        f"💎 <b>ID:</b> <code>{row['user_id']}</code>\n"
        f"💵 <b>Balans:</b> {row['balance']}\n"
        f"⭐ <b>Star:</b> {row['stars']}"
    )


@router.message(Command("UserUsername"))
async def user_username(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: <code>/UserUsername ID</code>"
        )
        return

    uid = await resolve_user(parts[1])
    row = get_user(uid) if uid else None

    if not row:
        await message.answer("❌ Topilmadi.")
        return

    await message.answer(
        f"👤 Username: "
        f"<b>{escape(display_username(row))}</b>"
    )


# ------------------------------------------------------------
# Button management
# ------------------------------------------------------------

@router.message(Command("Buttoneditor"))
async def button_editor(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    await message.answer(
        "🔘 <b>Tugmalar joyi</b>\n"
        "Hozirgi standart menyu:\n"
        "1. ⭐ Prevyu yasash ⭐\n"
        "2. 🎁 Promo kod 🎁 | "
        "💳 Balans to‘ldirish 💳\n"
        "3. 🎮 O‘yinlar | "
        "➕ Guruhga qo‘shish ➕\n"
        "4. ⛓️‍💥 Admin Sozlamalar ⚙️ "
        "(faqat admin)"
    )


@router.message(Command("ButtonsName"))
async def buttons_name(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    await message.answer(
        "🔘 <b>Tugmalar nomlari</b>\n"
        "Tugma nomini o'zgartirish uchun "
        "/NewButton funksiyasidan foydalaning."
    )


@router.message(Command("NewButton"))
async def new_button(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/NewButton Tugma nomi</code>"
        )
        return

    name = parts[1].strip()

    conn = db()
    conn.execute(
        "INSERT INTO custom_buttons(name) VALUES (?)",
        (name,),
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ Yangi tugma yaratildi: "
        f"<b>{escape(name)}</b>"
    )


@router.message(Command("ButtonColor"))
async def button_color(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Foydalanish: "
            "<code>/ButtonColor tugmaNomi RangNomi</code>"
        )
        return

    name = parts[1]
    color = parts[2]

    conn = db()
    conn.execute(
        """
        UPDATE custom_buttons
        SET color=?
        WHERE name=?
        """,
        (color, name),
    )
    conn.commit()
    conn.close()

    await message.answer(
        f"🎨 {escape(name)} → {escape(color)}"
    )


@router.message(Command("DaletButton"))
async def delete_button(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/DaletButton tugmaNomi</code>"
        )
        return

    conn = db()
    conn.execute(
        "DELETE FROM custom_buttons WHERE name=?",
        (parts[1],),
    )
    conn.commit()
    conn.close()

    await message.answer("✅ Tugma o'chirildi.")


@router.message(Command("ButtonFunction"))
async def button_function(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=2)

    if len(parts) < 3:
        await message.answer(
            "Foydalanish: "
            "<code>/ButtonFunction tugmaNomi funksiya</code>\n"
            "Funksiya: rasm, gif, sticker, emoji, tekst"
        )
        return

    conn = db()
    conn.execute(
        """
        UPDATE custom_buttons
        SET function=?
        WHERE name=?
        """,
        (parts[2], parts[1]),
    )
    conn.commit()
    conn.close()

    await message.answer(
        "✅ Tugma funksiyasi saqlandi."
    )


@router.message(Command("ButtonFunctionDalet"))
async def button_function_delete(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/ButtonFunctionDalet tugmaNomi</code>"
        )
        return

    conn = db()
    conn.execute(
        """
        UPDATE custom_buttons
        SET function=NULL
        WHERE name=?
        """,
        (parts[1],),
    )
    conn.commit()
    conn.close()

    await message.answer(
        "✅ Tugma funksiyasi o'chirildi."
    )


# ------------------------------------------------------------
# Balance management
# ------------------------------------------------------------

@router.message(Command("BalanceDeleteAll"))
async def balance_delete_all(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    conn = db()
    conn.execute("UPDATE users SET balance=0")
    conn.commit()
    conn.close()

    await message.answer(
        "✅ Barcha foydalanuvchilar balansi 0 qilindi."
    )


@router.message(Command("BalanceDalete1"))
async def balance_delete_one(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/BalanceDalete1 ID yoki @username</code>"
        )
        return

    uid = await resolve_user(parts[1])

    if not uid or not get_user(uid):
        await message.answer(
            "❌ Foydalanuvchi topilmadi."
        )
        return

    set_balance(uid, 0)

    await message.answer(
        "✅ Foydalanuvchi balansi o'chirildi."
    )


@router.message(Command("Balancing"))
async def balancing(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split()

    if len(parts) < 3:
        await message.answer(
            "Foydalanish: "
            "<code>/Balancing @Foydalanuvchi "
            "yoki ID Kerakli_summa</code>"
        )
        return

    uid = await resolve_user(parts[1])

    try:
        amount = int(parts[2])
    except ValueError:
        await message.answer(
            "❌ Summa raqam bo'lishi kerak."
        )
        return

    if not uid or not get_user(uid):
        await message.answer(
            "❌ Foydalanuvchi topilmadi."
        )
        return

    add_balance(uid, amount)

    await message.answer(
        f"✅ <code>{uid}</code> balansiga "
        f"<b>+{amount}</b> qo'shildi."
    )


@router.message(Command("AllHumansBalans1"))
async def all_balance(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split()

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: "
            "<code>/AllHumansBalans1 summa</code>"
        )
        return

    try:
        amount = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ Summa raqam bo'lishi kerak."
        )
        return

    conn = db()
    conn.execute(
        "UPDATE users SET balance=balance+?",
        (amount,),
    )
    count = conn.execute(
        "SELECT COUNT(*) c FROM users"
    ).fetchone()["c"]
    conn.commit()
    conn.close()

    await message.answer(
        f"✅ {count} ta foydalanuvchiga "
        f"<b>+{amount}</b> balans berildi."
    )


# ------------------------------------------------------------
# Other admin tools
# ------------------------------------------------------------

@router.message(Command("NewWindowButton"))
async def new_window_button(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    await message.answer(
        "🪟 <b>Yangi oyna</b>\n"
        "Bu funksiya uchun: "
        "<code>/NewWindowButton Tugma nomi</code>"
    )


@router.message(Command("IdendUser"))
async def identify_user(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "Foydalanish: <code>/IdendUser ID</code>"
        )
        return

    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer(
            "❌ ID raqam bo'lishi kerak."
        )
        return

    row = get_user(uid)

    if not row:
        await message.answer(
            "❌ Bu ID bilan foydalanuvchi topilmadi."
        )
        return

    await message.answer(
        f"👤 <b>Foydalanuvchi:</b> "
        f"{escape(display_username(row))}\n"
        f"🆔 <code>{row['user_id']}</code>\n"
        f"💵 Balans: <b>{row['balance']}</b>\n"
        f"⭐ Star: <b>{row['stars']}</b>"
    )


@router.message(Command("RandomHuman"))
async def random_human(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("❌ Faqat admin.")
        return

    conn = db()

    rows = conn.execute(
        """
        SELECT * FROM users
        ORDER BY RANDOM()
        LIMIT 3
        """
    ).fetchall()

    conn.close()

    if not rows:
        await message.answer(
            "❌ Foydalanuvchilar yo'q."
        )
        return

    text = "🎲 <b>Random 3 foydalanuvchi:</b>\n\n"

    for i, row in enumerate(rows, 1):
        text += (
            f"{i}. {escape(display_username(row))} — "
            f"<code>{row['user_id']}</code> — "
            f"💵 {row['balance']}\n"
        )

    await message.answer(text)


# ============================================================
# TELEGRAM STARS
# ============================================================

@router.callback_query(F.data.startswith("star_"))
async def stars_callback(callback: CallbackQuery):
    amounts = {
        "star_1": 1,
        "star_2": 2,
        "star_3": 3,
    }

    amount = amounts.get(callback.data, 1)

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"{amount} Telegram Star",
        description=f"{amount} Telegram Star yuborish",
        payload=(
            f"stars:{callback.from_user.id}:{amount}"
        ),
        currency="XTR",
        prices=[
            LabeledPrice(
                label=f"{amount} Star",
                amount=amount,
            )
        ],
        provider_token="",
    )

    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query):
    await bot.answer_pre_checkout_query(
        query.id,
        ok=True,
    )


@router.message(F.successful_payment)
async def successful_payment(message: Message):
    sp = message.successful_payment

    if not sp:
        return

    amount = getattr(
        sp,
        "total_amount",
        0,
    )

    conn = db()

    conn.execute(
        """
        UPDATE users
        SET stars=stars+?
        WHERE user_id=?
        """,
        (amount, message.from_user.id),
    )

    conn.commit()
    conn.close()

    await message.answer(
        "⭐ To'lov qabul qilindi!\n"
        f"💎 Sizning hisobingizga "
        f"<b>{amount} Star</b> yozildi."
    )


# ============================================================
# STARTUP
# ============================================================

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_BOT_TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN ni FastBot1.py ichiga yozing yoki "
            "BOT_TOKEN environment variable o'rnating."
        )

    init_db()

    me = await bot.get_me()
    logger.info(
        "Bot started: @%s",
        me.username,
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")