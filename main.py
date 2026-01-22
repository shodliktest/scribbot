import streamlit as st
import asyncio
import threading
import io
import numpy as np
import cv2
import img2pdf
from PIL import Image, ImageEnhance
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# --- 1. SOZLAMALAR ---
st.set_page_config(page_title="AI Scanner Admin", layout="wide", page_icon="🛡")

# Global o'zgaruvchi (Bot xotirasi uchun)
# DIQQAT: st.session_state o'rniga shu global lug'atni ishlatamiz
USER_DATA = {}

try:
    # Agar mahalliy kompyuterda bo'lsa .streamlit/secrets.toml dan oladi
    # Agar Cloud bo'lsa Settings -> Secrets dan oladi
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except Exception as e:
    st.error(f"Secrets xatosi: {e}")
    st.stop()

# --- 2. TASVIRNI QAYTA ISHLASH FUNKSIYALARI ---
def apply_filter(img_bytes, filter_type):
    """Rasmni tanlangan filtr asosida o'zgartirish"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if filter_type == "document":
        # Skaner effekti (Oq-qora va tiniq)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Adaptive Threshold - soyalarni olib tashlaydi
        processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        return processed
    
    elif filter_type == "magic":
        # Ranglarni kuchaytirish (Magic Color)
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        enhancer = ImageEnhance.Brightness(pil_img)
        pil_img = enhancer.enhance(1.1)
        enhancer = ImageEnhance.Contrast(pil_img)
        pil_img = enhancer.enhance(1.3)
        enhancer = ImageEnhance.Sharpness(pil_img)
        pil_img = enhancer.enhance(1.5)
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    
    return img # Original holat

def generate_pdf(image_list, filter_type):
    """Rasmlar ro'yxatidan PDF yaratish"""
    processed_images = []
    for img_b in image_list:
        filtered = apply_filter(img_b, filter_type)
        # Rasmni JPG formatida siqish (sifatni saqlagan holda)
        _, buffer = cv2.imencode(".jpg", filtered, [cv2.IMWRITE_JPEG_QUALITY, 90])
        processed_images.append(buffer.tobytes())
    
    # img2pdf yordamida A4 formatga moslash
    if not processed_images:
        raise Exception("Rasmlar ro'yxati bo'sh!")
        
    pdf_bytes = img2pdf.convert(processed_images)
    return io.BytesIO(pdf_bytes)

# --- 3. TELEGRAM BOT SOZLAMALARI ---
# Bot obyektini keshlaymiz
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 4. BOT HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    uid = m.from_user.id
    USER_DATA[uid] = [] # Foydalanuvchi xotirasini tozalash
    
    await m.answer(
        f"👋 Salom <b>{m.from_user.full_name}</b>!\n\n"
        "📸 Menga rasmlarni ketma-ket yuboring. Men ularni jamlab, "
        "siz tanlagan uslubda (Skaner, Rangli yoki Asl holatda) PDF qilib beraman."
    )

@dp.message(F.photo)
async def handle_photos(m: types.Message):
    uid = m.from_user.id
    
    # Foydalanuvchi uchun joy ochamiz
    if uid not in USER_DATA:
        USER_DATA[uid] = []
    
    # DEFENDER: Maksimal 20 ta rasm
    if len(USER_DATA[uid]) >= 20:
        await m.answer("⚠️ Bitta PDF uchun maksimal 20 ta rasm limiti qo'yilgan.")
        return

    # Rasmni yuklab olish
    status_msg = await m.reply("📥 Yuklanmoqda...")
    try:
        file = await bot.get_file(m.photo[-1].file_id)
        down = await bot.download_file(file.file_path)
        USER_DATA[uid].append(down.read())
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {e}")
        return
    
    count = len(USER_DATA[uid])
    
    # Tugmalar
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ PDF-ni yakunlash ({count} rasm)", callback_data="finish_menu")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_all")]
    ])
    
    await m.answer(f"✅ {count}-rasm qo'shildi.", reply_markup=kb)

@dp.callback_query(F.data == "finish_menu")
async def show_filter_menu(call: types.CallbackQuery):
    uid = call.from_user.id
    if uid not in USER_DATA or not USER_DATA[uid]:
        await call.answer("Rasmlar yo'q!", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Asl holat (Original)", callback_data="pdf_original")],
        [InlineKeyboardButton(text="📄 Hujjat (Oq-qora Skaner)", callback_data="pdf_document")],
        [InlineKeyboardButton(text="✨ Yorqin (Magic Color)", callback_data="pdf_magic")],
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="clear_all")]
    ])
    await call.message.edit_text("🎨 PDF uslubini tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pdf_"))
async def process_pdf(call: types.CallbackQuery):
    uid = call.from_user.id
    filter_type = call.data.split("_")[1] # original, document, magic
    
    if uid not in USER_DATA or not USER_DATA[uid]:
        await call.message.edit_text("❌ Rasmlar topilmadi. Qaytadan /start bosing.")
        return

    msg = call.message
    status = await msg.edit_text(f"⏳ <b>{len(USER_DATA[uid])} ta sahifa tayyorlanmoqda...</b>\nBu biroz vaqt olishi mumkin.")
    
    try:
        # Og'ir jarayonni alohida oqimda bajaramiz
        loop = asyncio.get_event_loop()
        pdf_io = await loop.run_in_executor(None, generate_pdf, USER_DATA[uid], filter_type)
        
        # Fayl nomini chiroyli qilish
        timestamp = int(time.time())
        filename = f"Scan_{filter_type}_{timestamp}.pdf"
        
        await msg.answer_document(
            BufferedInputFile(pdf_io.read(), filename=filename),
            caption=f"✅ <b>Tayyor!</b> ({filter_type} rejimi)\n🤖 Bot: @{(await bot.get_me()).username}"
        )
        
        # Xotirani tozalash
        USER_DATA[uid] = []
        await status.delete()
        
    except Exception as e:
        await status.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")

@dp.callback_query(F.data == "clear_all")
async def clear_data(call: types.CallbackQuery):
    uid = call.from_user.id
    USER_DATA[uid] = []
    await call.message.edit_text("🗑 Barcha rasmlar o'chirildi. Yangi rasm yuborishingiz mumkin.")

# --- 5. ORQA FONDA BOTNI ISHLATISH (KILLER WEBHOOK) ---
def start_bot_background():
    # Yangi event loop ochamiz (Streamlitniki bilan arashmasligi uchun)
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    
    async def runner():
        # Webhookni o'chirib tashlaymiz (eski update'lar tiqilib qolmasligi uchun)
        await bot.delete_webhook(drop_pending_updates=True)
        # Pollingni boshlaymiz
        await dp.start_polling(bot, handle_signals=False)

    try:
        new_loop.run_until_complete(runner())
    except Exception as e:
        print(f"Bot to'xtadi: {e}")

# Thread himoyasi (Singleton)
# Agar bot allaqachon ishlayotgan bo'lsa, qayta ishga tushirmaymiz
if not any(t.name == "MainBotThread" for t in threading.enumerate()):
    t = threading.Thread(target=start_bot_background, name="MainBotThread", daemon=True)
    t.start()

# --- 6. ADMIN PANEL (STREAMLIT) ---
st.title("🛡 AI PDF Scanner Admin")

# Kirish
col1, col2 = st.columns([1, 2])
with col1:
    admin_pass = st.text_input("Admin Parol", type="password")

if admin_pass == ADMIN_PASS:
    st.success("✅ Tizimga kirildi")
    
    st.metric("Aktiv Threadlar", threading.active_count())
    st.metric("Xotiradagi foydalanuvchilar (Vaqtinchalik)", len(USER_DATA))
    
    st.subheader("Foydalanuvchilarni tozalash")
    if st.button("🧹 RAM Xotirani bo'shatish"):
        USER_DATA.clear()
        st.success("Xotira tozalandi!")
else:
    st.info("Bot Telegramda ishlamoqda. Admin panelga kirish uchun parolni kiriting.")
