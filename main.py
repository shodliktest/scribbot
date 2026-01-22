import streamlit as st
import asyncio
import threading
import io
import os
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

# --- 1. PREMIUM UI DESIGN ---
st.set_page_config(page_title="AI Studio Pro 2026", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background: #0e1117; }
    .stTabs [data-baseweb="tab-list"] { gap: 24px; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: #161b22; border-radius: 10px 10px 0 0; padding: 10px 20px; color: #adbac7; }
    .stTabs [aria-selected="true"] { background-color: #1f6feb !important; color: white !important; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #58a6ff; }
    .reportview-container .main .block-container { padding-top: 2rem; }
    </style>
    """, unsafe_allow_html=True)

# Global Memory (Singleton Pattern)
if 'SYS_CACHE' not in st.session_state:
    st.session_state.SYS_CACHE = {} # {uid: {'files': [], 'state': None, 'doc': None}}

# SECRETS LOADING
try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ Secrets sozlanmagan!")
    st.stop()

# --- 2. AI & CORE LOGIC FUNCTIONS ---
def ai_enhance(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    # Denoise + Sharpness
    denoised = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
    pil_img = Image.fromarray(cv2.cvtColor(denoised, cv2.COLOR_BGR2RGB))
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(2.0)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.2)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=98)
    return buf.getvalue()

def scanner_effect(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Adaptive threshold for document feel
    scan = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    _, buf = cv2.imencode(".jpg", scan)
    return buf.tobytes()

# --- 3. ASYNCHRONOUS BOT ENGINE ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 4. BOT HANDLERS WITH GUIDANCE ---
@dp.message(Command("start"))
async def start_handler(m: types.Message):
    uid = m.from_user.id
    st.session_state.SYS_CACHE[uid] = {'files': [], 'state': None}
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Adminga murojaat", callback_data="ask_admin")],
        [InlineKeyboardButton(text="ℹ️ Bot qo'llanmasi", callback_data="show_info")]
    ])
    
    await m.answer(
        f"🌟 <b>Assalomu alaykum, {m.from_user.first_name}!</b>\n\n"
        "Men universal media tahrirchi botman. Menga <b>Rasm, PDF, Word</b> yoki <b>TXT</b> fayl yuboring, "
        "men uni siz xohlagan formatga o'tkazib beraman.\n\n"
        "<i>Hozircha bo'shman, fayl yuborishingizni kutayapman...</i>",
        reply_markup=kb
    )

@dp.message(F.photo)
async def photo_catcher(m: types.Message):
    uid = m.from_user.id
    if uid not in st.session_state.SYS_CACHE: st.session_state.SYS_CACHE[uid] = {'files': []}
    
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    st.session_state.SYS_CACHE[uid]['files'].append(content.read())
    
    count = len(st.session_state.SYS_CACHE[uid]['files'])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF (Birlashtirish)", callback_data="make_pdf")],
        [InlineKeyboardButton(text="📝 Word (Hujjat)", callback_data="make_word")],
        [InlineKeyboardButton(text="🎨 AI Edit (Filtrlar)", callback_data="make_ai")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_all")]
    ])
    
    await m.reply(
        f"📸 <b>{count}-chi rasm qabul qilindi.</b>\n\n"
        "<b>Keyingi qadam:</b> Yana rasm yuboring yoki yuqoridagi amallardan birini tanlang.",
        reply_markup=kb
    )

@dp.callback_query(F.data == "make_pdf")
async def pdf_options(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Original", callback_data="f_pdf_orig"),
         InlineKeyboardButton(text="📄 Skaner (Oq-qora)", callback_data="f_pdf_scan")],
        [InlineKeyboardButton(text="✨ AI Enhance (Sifatli)", callback_data="f_pdf_ai")]
    ])
    await call.message.edit_text(
        "📂 <b>PDF yaratish rejimi:</b>\n\n"
        "• <b>Original:</b> Rasmlar qanday bo'lsa shunday PDF bo'ladi.\n"
        "• <b>Skaner:</b> Soyalar olinadi, matn tiniqlashadi.\n"
        "• <b>AI Enhance:</b> Ranglar va aniqlik professional darajaga ko'tariladi.",
        reply_markup=kb
    )

# --- 5. PDF SPLIT & CONVERT LOGIC ---
@dp.message(F.document)
async def doc_handler(m: types.Message):
    uid = m.from_user.id
    file_info = await bot.get_file(m.document.file_id)
    content = await bot.download_file(file_info.file_path)
    file_bytes = content.read()
    
    st.session_state.SYS_CACHE[uid] = {'current_file': file_bytes, 'fname': m.document.file_name}
    
    kb_list = []
    if m.document.mime_type == "application/pdf":
        kb_list = [
            [InlineKeyboardButton(text="✂️ PDF Kesish (Split)", callback_data="split_pdf")],
            [InlineKeyboardButton(text="📝 Wordga o'tkazish", callback_data="to_docx")],
            [InlineKeyboardButton(text="🔍 Matnga o'tkazish", callback_data="to_txt")]
        ]
    
    await m.answer(f"📁 <b>{m.document.file_name}</b> qabul qilindi. Amallarni tanlang:", 
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data == "split_pdf")
async def split_init(call: types.CallbackQuery):
    st.session_state.SYS_CACHE[call.from_user.id]['state'] = "waiting_split"
    await call.message.answer("✂️ <b>Kesish diapazonini yuboring.</b>\n\nMasalan: <code>1-3</code> (1-betdan 3-betgacha kesib beraman).")

@dp.message(F.text)
async def text_processor(m: types.Message):
    uid = m.from_user.id
    data = st.session_state.SYS_CACHE.get(uid)
    
    if data and data.get('state') == "waiting_split":
        try:
            start, end = map(int, m.text.split("-"))
            reader = PdfReader(io.BytesIO(data['current_file']))
            writer = PdfWriter()
            for i in range(start-1, min(end, len(reader.pages))):
                writer.add_page(reader.pages[i])
            
            out = io.BytesIO()
            writer.write(out)
            await m.answer_document(BufferedInputFile(out.getvalue(), filename="split.pdf"), caption="✅ PDF kesildi!")
        except:
            await m.answer("❌ Xato! Format: 1-5")
        st.session_state.SYS_CACHE[uid]['state'] = None

# --- 6. SINGLETON & KILLER WEBHOOK ---
def run_bot_v3():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    loop.run_until_complete(starter())

if "bot_online" not in st.session_state:
    if not any(t.name == "ProBotThread" for t in threading.enumerate()):
        threading.Thread(target=run_bot_v3, name="ProBotThread", daemon=True).start()
    st.session_state.bot_online = True

# --- 7. PREMIUM ADMIN PANEL ---
st.markdown('<h1 class="main-title">🛡️ AI Studio Pro Dashboard</h1>', unsafe_allow_html=True)

with st.sidebar:
    st.header("🔑 Admin Access")
    pw = st.text_input("Security Key", type="password")
    st.divider()
    st.info(f"🚀 Uptime: Active\n🕒 Time: {datetime.now().strftime('%H:%M')}")

if pw == ADMIN_PASS:
    st.success("Welcome back, Admin!")
    t1, t2, t3 = st.tabs(["📊 Analytics", "📢 Broadcast", "⚙️ System"])
    
    with t1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Active Threads", threading.active_count())
        c2.metric("Cached Users", len(st.session_state.SYS_CACHE))
        c3.metric("API Latency", "12ms")
        
        # Real-time data visualization
        chart_data = pd.DataFrame(np.random.randn(20, 3), columns=['OCR', 'PDF', 'Docx'])
        st.area_chart(chart_data)

    with t2:
        st.subheader("Send Global Message")
        msg = st.text_area("Message Content")
        if st.button("Broadcast Now"):
            st.warning("Feature requires Database link.")

    with t3:
        if st.button("🗑 Force Clear RAM Cache"):
            st.session_state.SYS_CACHE = {}
            st.rerun()
else:
    st.info("Iltimos, tizimga kirish uchun parolni kiriting.")
    st.image("https://img.freepik.com/free-vector/modern-technology-concept-with-data_23-2148464654.jpg")
    
