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
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader, PdfWriter
from pdf2docx import Converter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from datetime import datetime

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Universal AI Studio 2026", layout="wide")

# Global Cache
if 'U_CACHE' not in st.session_state:
    st.session_state.U_CACHE = {} # {uid: {'files': [], 'state': None}}

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except Exception as e:
    st.error(f"Secrets xatosi: {e}")
    st.stop()

# --- 2. ADVANCED IMAGE & FILE LOGIC ---

def enhance_image_pro(img_bytes):
    """AI darajasida sifatni oshirish"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # 1. Shovqinni kamaytirish (Denoising)
    dst = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
    # 2. Pillow-ga o'tkazish
    pil_img = Image.fromarray(cv2.cvtColor(dst, cv2.COLOR_BGR2RGB))
    # 3. Kontrast va aniqlik (Sharpness)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.3)
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(2.0)
    
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def apply_modern_filter(img_bytes, f_type):
    """Zamonaviy badiiy effektlar"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if f_type == "sketch": # Qalamda chizilgan
        gray, color = cv2.pencilSketch(img, sigma_s=60, sigma_r=0.07, shade_factor=0.05)
        res = gray
    elif f_type == "stylize": # Moybo'yoq effekti
        res = cv2.stylization(img, sigma_s=60, sigma_r=0.45)
    elif f_type == "hdr": # HDR effekt
        res = cv2.detailEnhance(img, sigma_s=12, sigma_r=0.15)
    else: res = img
        
    _, buffer = cv2.imencode(".jpg", res)
    return buffer.tobytes()

# --- 3. BOT INITIALIZATION ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 4. BOT HANDLERS & EXPLANATIONS ---

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    st.session_state.U_CACHE[m.from_user.id] = {'files': [], 'state': None}
    welcome = (
        f"👋 <b>Salom, {m.from_user.full_name}!</b>\n\n"
        "Men universal media yordamchiman. Quyidagilarni qila olaman:\n"
        "• 📸 <b>Rasm yuborsangiz:</b> PDF, Word qilish yoki sifatini oshirish.\n"
        "• 📄 <b>PDF yuborsangiz:</b> Kesish (split), Word yoki Matnga o'tkazish.\n"
        "• 📝 <b>Hujjat yuborsangiz:</b> Uni boshqa formatga o'tkazish.\n\n"
        "<i>Boshlash uchun istalgan fayl yoki rasmni yuboring!</i>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Adminga murojaat", callback_data="contact_admin")]
    ])
    await m.answer(welcome, reply_markup=kb)

# 📸 RASM QABUL QILISH
@dp.message(F.photo)
async def handle_photo(m: types.Message):
    uid = m.from_user.id
    if uid not in st.session_state.U_CACHE: st.session_state.U_CACHE[uid] = {'files': [], 'state': None}
    
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    st.session_state.U_CACHE[uid]['files'].append(content.read())
    
    count = len(st.session_state.U_CACHE[uid]['files'])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF (Tahrirlanadigan)", callback_data="m_pdf_edit")],
        [InlineKeyboardButton(text="🖼 Rasmlar (Original/Filtr)", callback_data="m_img_process")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear_cache")]
    ])
    
    text = (
        f"✅ <b>{count}-chi rasm qabul qilindi.</b>\n\n"
        "<b>Nima qilamiz?</b>\n"
        "1. <b>PDF:</b> Rasmlarni bitta PDF qiladi (matnlarini nusxalasa bo'ladi).\n"
        "2. <b>Rasmlar:</b> Sifatini oshirish yoki filtr berish."
    )
    await m.reply(text, reply_markup=kb)

# 📄 PDF / DOCX / TXT QABUL QILISH
@dp.message(F.document)
async def handle_docs(m: types.Message):
    uid = m.from_user.id
    mime = m.document.mime_type
    file_info = await bot.get_file(m.document.file_id)
    content = await bot.download_file(file_info.file_path)
    file_bytes = content.read()
    
    st.session_state.U_CACHE[uid] = {'current_file': file_bytes, 'filename': m.document.file_name}

    kb_list = []
    if "pdf" in mime:
        kb_list = [
            [InlineKeyboardButton(text="✂️ PDF-ni kesish", callback_data="pdf_split")],
            [InlineKeyboardButton(text="📝 Word (DOCX) ga o'tkazish", callback_data="pdf_to_docx")],
            [InlineKeyboardButton(text="🔍 Matnga (TXT) o'tkazish", callback_data="pdf_to_txt")]
        ]
    elif "word" in mime or "docx" in mime:
        kb_list = [[InlineKeyboardButton(text="📄 PDF ga o'tkazish", callback_data="docx_to_pdf")]]
    elif "text" in mime or "plain" in mime:
        kb_list = [[InlineKeyboardButton(text="📄 PDF / 📝 DOCX", callback_data="txt_to_all")]]

    await m.reply("📂 <b>Fayl turi aniqlandi.</b> Tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

# --- 5. CALLBACKS & STATE LOGIC ---

@dp.callback_query(F.data == "pdf_split")
async def ask_pages(call: types.CallbackQuery):
    await call.message.answer("✂️ <b>Kesish uchun sahifalarni kiriting.</b>\n\nMasalan: <code>1-5</code> (1-betdan 5-betgacha kesib beraman).")
    st.session_state.U_CACHE[call.from_user.id]['state'] = "waiting_split"

@dp.message(F.text)
async def process_text_input(m: types.Message):
    uid = m.from_user.id
    user_data = st.session_state.U_CACHE.get(uid)
    
    if user_data and user_data.get('state') == "waiting_split":
        try:
            start_p, end_p = map(int, m.text.split("-"))
            reader = PdfReader(io.BytesIO(user_data['current_file']))
            writer = PdfWriter()
            
            for i in range(start_p - 1, min(end_p, len(reader.pages))):
                writer.add_page(reader.pages[i])
            
            out_pdf = io.BytesIO()
            writer.write(out_pdf)
            await m.answer_document(BufferedInputFile(out_pdf.getvalue(), filename="cropped.pdf"), caption="✅ Kesilgan PDF tayyor!")
        except:
            await m.answer("❌ Noto'g'ri format. Misol: 1-5")
        st.session_state.U_CACHE[uid]['state'] = None
    
    elif m.text == "Adminga murojaat": # Reply menyu bo'lsa
        await m.answer("Xabaringizni yozing, men uni adminga yetkazaman.")

@dp.callback_query(F.data.startswith("m_pdf_"))
async def image_to_pdf_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Original", callback_data="p_orig"),
         InlineKeyboardButton(text="📄 Skaner (Oq-qora)", callback_data="p_scan")],
        [InlineKeyboardButton(text="✨ Yaxshilangan (AI)", callback_data="p_enhance")]
    ])
    await call.message.edit_text("<b>PDF uchun rasm uslubini tanlang:</b>\n\n• <i>Original:</i> Rasm qanday bo'lsa shunday.\n• <i>Skaner:</i> Soyasiz, oq fondagi matn.\n• <i>Yaxshilangan:</i> Tiniq va yorqin.", reply_markup=kb)

# --- 6. SINGLETON & KILLER WEBHOOK ---
def run_bot():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    new_loop.run_until_complete(starter())

if "active" not in st.session_state:
    if not any(t.name == "MainAIThread" for t in threading.enumerate()):
        threading.Thread(target=run_bot, name="MainAIThread", daemon=True).start()
    st.session_state.active = True

# --- 7. ADMIN PANEL (WEB) ---
st.title("🛡️ Universal AI Control Center")
with st.sidebar:
    auth = st.text_input("Admin Password", type="password")

if auth == ADMIN_PASS:
    t1, t2 = st.tabs(["📊 Statistika", "📢 Broadcast"])
    with t1:
        st.metric("Bot Status", "🟢 Online")
        st.metric("Aktiv Threadlar", threading.active_count())
    with t2:
        msg = st.text_area("Xabar matni:")
        if st.button("🚀 Yuborish"):
            st.info("Broadcast funksiyasi ulandi.")
else:
    st.info("Boshqaruv uchun parolni kiriting.")
