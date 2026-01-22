import streamlit as st
import asyncio
import threading
import io
import os
import time
import random
import pandas as pd
import numpy as np
import cv2
import img2pdf
import pytesseract
from docx import Document
from docx.shared import Inches
from pdf2docx import Converter
from PIL import Image, ImageEnhance, ImageFilter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.client.default import DefaultBotProperties
from datetime import datetime

# --- 1. SAHIFA SOZLAMALARI ---
st.set_page_config(page_title="AI Studio Dashboard", layout="wide", page_icon="🛡️")

# CSS orqali dizaynni chiroyli qilish
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border-radius: 10px; padding: 15px; border: 1px solid #30363d; }
    .stInfo { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# Global Xotira (Thread-safe lug'at)
if 'USER_DATA' not in st.session_state:
    st.session_state.USER_DATA = {}

# --- 2. SECRETS TEKSHIRUV ---
try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except Exception as e:
    st.error(f"❌ Secrets sozlanmagan: {e}")
    st.stop()

# --- 3. CORE LOGIC (RASM VA PDF) ---
def process_media_action(image_list, action):
    if action == "enhance":
        processed = []
        for img_b in image_list:
            pil_img = Image.open(io.BytesIO(img_b)).convert("RGB")
            pil_img = ImageEnhance.Contrast(pil_img).enhance(1.4)
            pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.6)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=95)
            processed.append(buf.getvalue())
        return "images", processed

    elif action == "ocr":
        full_text = ""
        for i, img_b in enumerate(image_list):
            pil_img = Image.open(io.BytesIO(img_b))
            text = pytesseract.image_to_string(pil_img, lang='uzb+rus+eng')
            full_text += f"\n--- {i+1}-sahifa ---\n{text}\n"
        return "text", full_text

    elif action == "pdf":
        scanned_bytes = []
        for img_b in image_list:
            nparr = np.frombuffer(img_b, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            _, buffer = cv2.imencode(".jpg", thresh)
            scanned_bytes.append(buffer.tobytes())
        pdf_data = img2pdf.convert(scanned_bytes)
        return "file", (pdf_data, "document.pdf")

# --- 4. BOT HANDLERS VA DISPATCHER ---
# Singleton Bot ob'ekti
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# HANDLERLARNI RO'YXATDAN O'TKAZISH
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    st.session_state.USER_DATA[m.from_user.id] = []
    await m.answer(f"👋 Salom <b>{m.from_user.full_name}</b>!\n\nMen sun'iy intellekt yordamida rasmlaringizni PDF, Word qilaman yoki matnlarini o'qiyman. Boshlash uchun rasm yuboring.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    uid = m.from_user.id
    if uid not in st.session_state.USER_DATA:
        st.session_state.USER_DATA[uid] = []
    
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    st.session_state.USER_DATA[uid].append(content.read())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Bajarish ({len(st.session_state.USER_DATA[uid])})", callback_data="menu_main")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm qabul qilindi. Yana yuborishingiz yoki amalni tanlashingiz mumkin.", reply_markup=kb)

@dp.callback_query(F.data == "menu_main")
async def main_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="act_pdf"), InlineKeyboardButton(text="✨ Enhance", callback_data="act_enhance")],
        [InlineKeyboardButton(text="🔍 OCR (Matn)", callback_data="act_ocr"), InlineKeyboardButton(text="🎨 Random Filter", callback_data="act_filter")]
    ])
    await call.message.edit_text("Kerakli amalni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("act_"))
async def final_action(call: types.CallbackQuery):
    action = call.data.split("_")[1]
    uid = call.from_user.id
    if uid not in st.session_state.USER_DATA or not st.session_state.USER_DATA[uid]:
        await call.answer("Rasmlar topilmadi!", show_alert=True)
        return

    status = await call.message.edit_text("⏳ AI ishlov bermoqda, iltimos kuting...")
    try:
        loop = asyncio.get_event_loop()
        res_type, result = await loop.run_in_executor(None, process_media_action, st.session_state.USER_DATA[uid], action)
        
        if res_type == "images":
            for img in result: await call.message.answer_photo(BufferedInputFile(img, filename="res.jpg"))
        elif res_type == "text":
            await call.message.answer(f"📝 <b>Natija:</b>\n\n<code>{result[:4000]}</code>")
        elif res_type == "file":
            data, name = result
            await call.message.answer_document(BufferedInputFile(data, filename=name))
        
        st.session_state.USER_DATA[uid] = [] # Keshni tozalash
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Xatolik: {e}")

# --- 5. SINGLETON RUNNER (KILLER WEBHOOK) ---
def run_bot():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def starter():
        # Conflictni oldini olish uchun webhookni tozalash
        await bot.delete_webhook(drop_pending_updates=True)
        # Polling boshlash
        await dp.start_polling(bot, handle_signals=False)
    
    new_loop.run_until_complete(starter())

# Threadni ishga tushirish
if "bot_active" not in st.session_state:
    if not any(t.name == "MainBotThread" for t in threading.enumerate()):
        t = threading.Thread(target=run_bot, name="MainBotThread", daemon=True)
        t.start()
    st.session_state.bot_active = True

# --- 6. ADMIN PANEL (WEB UI) ---
st.title("🛡️ AI Studio Control Center")

# Sidebar - Admin login
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    st.header("Admin Kirish")
    user_pass = st.text_input("Parol", type="password")
    st.divider()
    st.write("🤖 Bot: @AI_Studio_Bot")
    st.write("📅 Sana:", datetime.now().strftime("%d-%m-%Y"))

if user_pass == ADMIN_PASS:
    st.success("✅ Tizimga kirildi. Xush kelibsiz!")
    
    # Statistika tablari
    tab1, tab2, tab3 = st.tabs(["📊 Statistika", "🤖 Bot Monitoring", "🛠 Sozlamalar"])
    
    with tab1:
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Aktiv Threadlar", threading.active_count())
        with c2: st.metric("Xotiradagi Userlar", len(st.session_state.USER_DATA))
        with c3: st.metric("Server Status", "Online 🟢")
        
        # Grafik (Simulyatsiya)
        st.subheader("Foydalanish darajasi")
        chart_data = pd.DataFrame(np.random.randn(20, 3), columns=['OCR', 'PDF', 'Enhance'])
        st.line_chart(chart_data)

    with tab2:
        st.subheader("Live Logs")
        if any(t.name == "MainBotThread" for t in threading.enumerate()):
            st.info("🟢 Bot oqimi (MainBotThread) barqaror ishlamoqda.")
        else:
            st.error("🔴 Bot to'xtab qolgan!")
            if st.button("Botni qayta yoqish"):
                st.rerun()
        
        st.code(f"Bot ID: {bot.id}\nAdmin ID: {ADMIN_ID}\nStatus: Listening for updates...")

    with tab3:
        st.subheader("Tizimni tozalash")
        if st.button("Keshni tozalash (RAM)"):
            st.session_state.USER_DATA = {}
            st.success("Barcha vaqtinchalik ma'lumotlar o'chirildi.")

else:
    # Saytga kirishdan oldin chiroyli Banner
    st.info("Iltimos, boshqaruv paneliga kirish uchun parolni kiriting.")
    st.image("https://img.freepik.com/free-vector/cyber-security-concept_23-2148532223.jpg", use_column_width=True)
    
    with st.expander("Tizim haqida ma'lumot"):
        st.write("""
        Ushbu tizim sun'iy intellekt yordamida media fayllarni qayta ishlaydi:
        - Rasmlarni PDF Skaner qilish.
        - Xira rasmlarni tiniqlashtirish (Enhance).
        - Rasmlardan matnlarni ajratib olish (OCR).
        - Fayllarni Word (DOCX) formatiga o'tkazish.
        """)
