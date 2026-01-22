import streamlit as st
import asyncio
import threading
import io
import os
import time
import cv2
import numpy as np
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance, ImageFilter
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader, PdfWriter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from datetime import datetime
import pandas as pd

# --- 1. GLOBAL XOTIRA (Xatolikni oldini oladi) ---
# Bu xotira barcha oqimlar (Thread) uchun ochiq
if "GLOBAL_USER_DATA" not in globals():
    GLOBAL_USER_DATA = {} # {uid: {'files': [], 'state': None, 'pdf_file': None}}

# --- 2. PREMIUM UI DIZAYN ---
st.set_page_config(page_title="AI Studio Premium 2026", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background: #0e1117; }
    .stMetric { background-color: #161b22; border-radius: 12px; padding: 20px; border: 1px solid #30363d; }
    .main-title { color: #58a6ff; font-size: 45px; font-weight: bold; text-align: center; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    </style>
    """, unsafe_allow_html=True)

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ Secrets sozlanmagan!")
    st.stop()

# --- 3. AI & MEDIA LOGIC ---
def ai_enhance_pro(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    dst = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
    pil_img = Image.fromarray(cv2.cvtColor(dst, cv2.COLOR_BGR2RGB))
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(2.0)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def scanner_effect(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    scan = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    _, buf = cv2.imencode(".jpg", scan)
    return buf.tobytes()

# --- 4. BOT ENGINE ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

INFO_TEXT = """
<b>🤖 AI Studio 2026 Qo'llanmasi:</b>

✨ <b>Rasm yuborsangiz:</b>
- Sifatni AI orqali oshirish (Enhance)
- Oq-qora skaner (PDF)
- Rasmlardan Word hujjati yaratish

📄 <b>PDF yuborsangiz:</b>
- PDF-ni kerakli sahifalarga kesish
- PDF-ni Wordga (Docx) o'tkazish
- PDF-ni Matnga (Txt) o'tkazish

<i>Boshlash uchun fayl yoki rasm yuboring!</i>
"""

# --- 5. BOT HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    GLOBAL_USER_DATA[m.from_user.id] = {'files': [], 'state': None}
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ℹ️ Info", callback_data="btn_info"),
         InlineKeyboardButton(text="👨‍💻 Admin", callback_data="btn_admin")]
    ])
    await m.answer(f"👋 Salom {m.from_user.first_name}!\nUniversal AI yordamchiga xush kelibsiz!", reply_markup=kb)

@dp.callback_query(F.data == "btn_info")
async def info_call(call: types.CallbackQuery):
    await call.message.answer(INFO_TEXT)
    await call.answer()

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    uid = m.from_user.id
    if uid not in GLOBAL_USER_DATA: GLOBAL_USER_DATA[uid] = {'files': []}
    
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    GLOBAL_USER_DATA[uid]['files'].append(content.read())
    
    count = len(GLOBAL_USER_DATA[uid]['files'])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF yaratish", callback_data="menu_pdf")],
        [InlineKeyboardButton(text="📝 Word qilish", callback_data="menu_word")],
        [InlineKeyboardButton(text="✨ AI Enhance", callback_data="menu_enhance")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ {count}-chi rasm olindi. Nima qilamiz?", reply_markup=kb)

@dp.callback_query(F.data == "menu_pdf")
async def pdf_style_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Original", callback_data="f_orig"),
         InlineKeyboardButton(text="📄 Oq-qora Skaner", callback_data="f_scan")],
        [InlineKeyboardButton(text="✨ AI Yaxshilangan", callback_data="f_ai")]
    ])
    await call.message.edit_text("<b>PDF uchun rasm uslubini tanlang:</b>", reply_markup=kb)

@dp.message(F.document)
async def handle_pdf(m: types.Message):
    if m.document.mime_type == "application/pdf":
        uid = m.from_user.id
        file = await bot.get_file(m.document.file_id)
        content = await bot.download_file(file.file_path)
        GLOBAL_USER_DATA[uid] = {'pdf_file': content.read(), 'state': None}
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✂️ PDF-ni kesish", callback_data="pdf_split")],
            [InlineKeyboardButton(text="📝 Wordga (Docx)", callback_data="pdf_to_docx")]
        ])
        await m.reply(f"📄 <b>{m.document.file_name}</b> qabul qilindi. Tanlang:", reply_markup=kb)

@dp.callback_query(F.data == "pdf_split")
async def split_start(call: types.CallbackQuery):
    GLOBAL_USER_DATA[call.from_user.id]['state'] = "waiting_split"
    await call.message.answer("✂️ Kesish uchun sahifalar oralig'ini yozing.\nMisol: <code>1-3</code>")

@dp.message(F.text)
async def text_handler(m: types.Message):
    uid = m.from_user.id
    if uid in GLOBAL_USER_DATA and GLOBAL_USER_DATA[uid].get('state') == "waiting_split":
        try:
            start_p, end_p = map(int, m.text.split("-"))
            reader = PdfReader(io.BytesIO(GLOBAL_USER_DATA[uid]['pdf_file']))
            writer = PdfWriter()
            for i in range(start_p - 1, min(end_p, len(reader.pages))):
                writer.add_page(reader.pages[i])
            
            out = io.BytesIO()
            writer.write(out)
            await m.answer_document(BufferedInputFile(out.getvalue(), filename="split.pdf"), caption="✅ Kesilgan PDF")
        except:
            await m.answer("❌ Xato! Misol: 1-5")
        GLOBAL_USER_DATA[uid]['state'] = None

# --- 6. SINGLETON THREAD (Conflict Killer) ---
def start_bot_thread():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    new_loop.run_until_complete(starter())

if not any(t.name == "AIProThread" for t in threading.enumerate()):
    threading.Thread(target=start_bot_thread, name="AIProThread", daemon=True).start()

# --- 7. PREMIUM WEB UI ---
st.markdown('<p class="main-title">🛡️ AI Studio Premium Dashboard</p>', unsafe_allow_html=True)

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    auth = st.text_input("Admin Key", type="password")
    st.divider()
    st.info(f"🕒 {datetime.now().strftime('%H:%M:%S')}")

if auth == ADMIN_PASS:
    st.success("Admin Panel Online")
    t1, t2 = st.tabs(["📊 Statistika", "ℹ️ Bot Ma'lumotlari"])
    with t1:
        c1, c2 = st.columns(2)
        c1.metric("Threadlar", threading.active_count())
        c2.metric("Userlar (RAM)", len(GLOBAL_USER_DATA))
        st.area_chart(pd.DataFrame(np.random.randn(10, 2), columns=['PDF', 'AI']))
    with t2:
        st.info("Hozirda botda ko'rsatiladigan Info matni:")
        st.code(INFO_TEXT)
else:
    st.markdown("### Admin panel uchun parolni kiriting.")
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg")
    st.warning("⚠️ Diqqat: Ma'lumotlar faqat admin uchun ochiq.")
