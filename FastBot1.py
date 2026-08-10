import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from datetime import datetime

 
TOKEN = "8638068274:AAFIk6QdGkszQsybzdyqSkVmqA7-W9ZTouU"
ADMIN_ID = 7543852010
ADMIN_USERNAME = "@Fast_gamer_uz"

bot = Bot(token=TOKEN)
dp = Dispatcher()

users = {}
promo_codes = {"Fast": True, "NEW2026": True}

# =================== MENYU ===================
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⭐ Prevyu yasash ⭐")],
            [KeyboardButton(text="💸Pulga Prevyu buyurtma qilish💸")],
            [KeyboardButton(text="🎁Promo kod🎁")]
        ],
        resize_keyboard=True
    )

# =================== COMMANDS ===================
@dp.message(Command("start"))
async def start_cmd(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {"balance": 0, "orders": 0, "bought": 0}

    await message.answer(
        f"Salom @{message.from_user.username}\n\n"
        f"@Fast_prevyu_bot ga hush kelibsiz\n"
        f"Iltimos asosiy menyuga kring va o‘z prevyuyingizni tayyorlang",
        reply_markup=main_menu()
    )

@dp.message(Command("profil"))
async def profil(message: Message):
    user = users.get(message.from_user.id)
    if not user:
        return
    await message.answer(
        f"🆔 ID: {message.from_user.id}\n"
        f"👤 Username: @{message.from_user.username}\n"
        f"💰 Balans: {user['balance']}\n"
        f"🛒 Xarid qilgan: {user['bought']}\n"
        f"🎨 Olingan prevyu: {user['orders']}"
    )

# =================== PREVIEW ===================
@dp.message(F.text == "⭐ Prevyu yasash ⭐")
async def ai_preview(message: Message):
    await message.answer(
        "Iltimos Minecraft skiningizni tashlang.\n"
        "⚠️ Hozircha avtomatik AI rasm yaratish funksiyasi o‘chirildi."
    )

@dp.message(F.photo)
async def receive_skin(message: Message):
    user = users.get(message.from_user.id)
    if not user:
        users[message.from_user.id] = {"balance": 0, "orders": 0, "bought": 0}
        user = users[message.from_user.id]

    if user["balance"] < 100:
        await message.answer("❌ 100 balans kerak!")
        return

    user["balance"] -= 100
    user["orders"] += 1
    await message.answer(
        "📸 Rasm qabul qilindi.\n"
        "❌ AI generator o‘chirilgan, shuning uchun avtomatik prevyu yaratilmaydi."
    )

# =================== PAID ORDER ===================
@dp.message(F.text == "💸Pulga Prevyu buyurtma qilish💸")
async def paid_order(message: Message):
    await bot.send_message(
        ADMIN_ID,
        f"💸 Yangi buyurtma!\nFoydalanuvchi: @{message.from_user.username}\nID: {message.from_user.id}"
    )
    await message.answer(f"✅ Buyurtmangiz adminga yuborildi\nAdmin: {ADMIN_USERNAME}")

# =================== PROMO ===================
@dp.message(F.text == "🎁Promo kod🎁")
async def promo(message: Message):
    await message.answer("Promo kodni kiriting:")

@dp.message()
async def check_promo(message: Message):
    user = users.get(message.from_user.id)
    today = datetime.now()

    # Promo faqat 10 martgacha ishlaydi
    if today.month == 3 and today.day > 10:
        await message.answer("❌ Promo muddati tugagan")
        return

    if message.text in promo_codes and promo_codes[message.text]:
        user["balance"] += 5
        promo_codes[message.text] = False
        await message.answer("🎉 5 balans qo‘shildi!")
    else:
        await message.answer("❌ Noto‘g‘ri yoki ishlatilgan promo kod!")

# =================== MAIN ===================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())