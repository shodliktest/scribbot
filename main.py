import streamlit as st
import asyncio
import threading
import os
import io
import time
import sqlite3
import numpy as np
import cv2
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# --- 1. CONFIG ---
st.set_page_config(page_title="AI Scanner Admin", layout="wide")

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("Secrets xatosi!")
    st.stop()

DB_FILE = "bot_core.db"

# Foydalanuvchi keshini xotirada saqlash (Singleton uslubida)
if "user_data" not in st.session_state:
    st.session_state.user_data = {} # {user_id: [img_bytes, ...]}

# --- 2. IMAGE FILTERS CORE ---
def apply_filter(img_bytes, filter_type):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if filter_type == "document":
        # Skaner effekti: Oq-qora, yuqori kontrast
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        return processed
    
    elif filter_type == "magic":
        # Yorqinlashtirish
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        enhancer = ImageEnhance.Brightness(pil_img)
        pil_img = enhancer.enhance(1.2)
        enhancer = ImageEnhance.Contrast(pil_img)
        return cv2.cvtColor(np.array(pil_img.enhance(1.3)), cv2.COLOR_RGB2BGR)
    
    return img # Original

def generate_pdf(image_list, filter_type):
    processed_images = []
    for img_b in image_list:
        filtered = apply_filter(img_b, filter_type)
        _, buffer = cv2.imencode(".jpg", filtered, [cv2.IMWRITE_JPEG_QUALITY, 90])
        processed_images.append(buffer.tobytes())
    
    # img2pdf orqali barcha rasmlarni bitta PDF sahifalariga yig'ish
    pdf_bytes = img2pdf.convert(processed_images)
    return io.BytesIO(pdf_bytes)

# --- 3. BOT INITIALIZATION ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 4. BOT HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    st.session_state.user_data[m.from_user.id] = [] # Keshni tozalash
    await m.answer(f"👋 Salom {m.from_user.full_name}!\n\nBir yoki bir nechta rasm yuboring, so'ngra ularni PDF qilib beraman.")

@dp.message(F.photo)
async def handle_photos(m: types.Message):
    uid = m.from_user.id
    if uid not in st.session_state.user_data:
        st.session_state.user_data[uid] = []
    
    # Defender: Max 20 sahifa
    if len(st.session_state.user_data[uid]) >= 20:
        await m.answer("⚠️ Limitga yetdingiz (Maksimal 20 rasm).")
        return

    # Yuklab olish
    file = await bot.get_file(m.photo[-1].file_id)
    down = await bot.download_file(file.file_path)
    st.session_state.user_data[uid].append(down.read())
    
    count = len(st.session_state.user_data[uid])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ PDF-ni yakunlash ({count} ta)", callback_data="choose_filter")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.answer(f"📸 {count}-rasm qo'shildi.", reply_markup=kb)

@dp.callback_query(F.data == "choose_filter")
async def filter_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Asl holatda (Original)", callback_data="pdf_original")],
        [InlineKeyboardButton(text="📄 Hujjat (Oq-qora Scan)", callback_data="pdf_document")],
        [InlineKeyboardButton(text="✨ Yorqin (Magic Color)", callback_data="pdf_magic")],
        [InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back")]
    ])
    await call.message.edit_text("PDF uslubini tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("pdf_"))
async def finalize_pdf(call: types.CallbackQuery):
    uid = call.from_user.id
    filter_type = call.data.split("_")[1]
    
    if uid not in st.session_state.user_data or not st.session_state.user_data[uid]:
        await call.answer("Rasmlar topilmadi!", show_alert=True)
        return

    status = await call.message.edit_text(f"⏳ {len(st.session_state.user_data[uid])} sahifali PDF yaratilmoqda...")
    
    try:
        loop = asyncio.get_event_loop()
        pdf_io = await loop.run_in_executor(None, generate_pdf, st.session_state.user_data[uid], filter_type)
        
        await call.message.answer_document(
            BufferedInputFile(pdf_io.read(), filename=f"scan_{filter_type}.pdf"),
            caption="✅ Tayyor! Marhamat, hujjatingiz."
        )
        st.session_state.user_data[uid] = [] # Keshni bo'shatish
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Xatolik: {e}")

@dp.callback_query(F.data == "clear")
async def clear_data(call: types.CallbackQuery):
    st.session_state.user_data[call.from_user.id] = []
    await call.message.edit_text("🗑 Barcha rasmlar tozalandi. Yangi rasm yuborishingiz mumkin.")

# --- 5. SINGLETON RUNNER (KILLER WEBHOOK) ---
def run_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    loop.run_until_complete(starter())

if "active" not in st.session_state:
    if not any(t.name == "MainBotThread" for t in threading.enumerate()):
        threading.Thread(target=run_bot, name="MainBotThread", daemon=True).start()
    st.session_state.active = True

# --- 6. ADMIN PANEL ---
st.title("🛡 AI Scanner Admin")
st.sidebar.text_input("Parol", type="password", key="admin_p")

if st.session_state.admin_p == ADMIN_PASS:
    st.success("Admin Panel Online")
    st.metric("Aktiv Threadlar", threading.active_count())
    st.info("Bot Telegramda foydalanuvchilarni qabul qilmoqda.")
