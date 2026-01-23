import streamlit as st
import asyncio
import threading
import io
import os
import re
import tempfile
import cv2
import html
import numpy as np
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader, PdfWriter
from pdf2docx import Converter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from datetime import datetime
import pandas as pd

# --- 1. GLOBAL STORAGE (Thread-safe) ---
if "G_DATA" not in globals():
    G_DATA = {} 

# --- 2. CONFIGURATION & ADMIN PASS ---
ADMIN_PASS = "1221" 

st.set_page_config(page_title="AI Studio Pro 2026", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; }
    .info-box { background: #0d1117; border-left: 5px solid #1f6feb; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
    .header-text { color: #58a6ff; font-size: 40px; font-weight: bold; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
except:
    st.error("❌ Secrets sozlanmagan!")
    st.stop()

# --- 3. PRO MEDIA & OCR ENGINE ---

def ocr_process_pro(image_list):
    """
    Eng kuchli OCR rejimi:
    - Kattalashtirish (Upscaling)
    - Shovqinni tozalash (Denoising)
    - Binarizatsiya (Otsu Thresholding)
    """
    full_text = ""
    custom_config = r'--oem 3 --psm 6' 
    
    for img_bytes in image_list:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 1. Kattalashtirish (mayda harflar uchun)
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # 2. Kulrang holatga keltirish
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 3. Shovqinni kamaytirish
        gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # 4. Binarizatsiya (Rasm faqat qora va oq bo'ladi)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        # 5. Tahrir qilingan rasmdan matnni o'qish
        text = pytesseract.image_to_string(Image.fromarray(thresh), lang='uzb+rus+eng', config=custom_config)
        full_text += text + "\n\n----------------\n\n"
        
    return full_text

def create_pdf_from_text(text_content):
    """ReportLab orqali DOCX/TXT dan PDF yasash"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    text_obj = p.beginText(40, height - 40)
    text_obj.setFont("Helvetica", 12)
    
    for line in text_content.split('\n'):
        wrapped_lines = simpleSplit(line, "Helvetica", 12, width - 80)
        for wrapped in wrapped_lines:
            if text_obj.getY() < 40:
                p.drawText(text_obj)
                p.showPage()
                text_obj = p.beginText(40, height - 40)
                text_obj.setFont("Helvetica", 12)
            text_obj.textLine(wrapped)
    p.drawText(text_obj)
    p.save()
    buffer.seek(0)
    return buffer.getvalue()

def docx_to_pdf_engine(docx_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
        tf.write(docx_bytes)
        path = tf.name
    try:
        doc = Document(path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return create_pdf_from_text(text)
    finally:
        if os.path.exists(path): os.remove(path)

def convert_pdf_to_docx_safe(pdf_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
        tf.write(pdf_bytes)
        temp_pdf = tf.name
    temp_docx = temp_pdf.replace(".pdf", ".docx")
    try:
        cv = Converter(temp_pdf)
        cv.convert(temp_docx, start=0, end=None)
        cv.close()
        with open(temp_docx, "rb") as f: return f.read()
    except: return None
    finally:
        if os.path.exists(temp_pdf): os.remove(temp_pdf)
        if os.path.exists(temp_docx): os.remove(temp_docx)

# --- 4. BOT SETUP (AIOGRAM 3) ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

def main_kb(uid):
    kb = [[KeyboardButton(text="ℹ️ Info"), KeyboardButton(text="👨‍💻 Adminga murojaat")]]
    if str(uid) == ADMIN_ID:
        kb.append([KeyboardButton(text="💎 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

INFO_TEXT = """
<b>ℹ️ AI STUDIO 2026 QO'LLANMASI:</b>

📸 <b>Rasm yuborsangiz:</b>
• <b>🔍 OCR PRO:</b> Rasmdan matnni eng yuqori aniqlikda o'qish.
• <b>📄 PDF Skaner:</b> Hujjatlarni professional skaner qilish.
• <b>✨ AI Enhance:</b> Sifatni oshirish.

📄 <b>Fayllar (DOCX, TXT, PDF):</b>
• <b>DOCX/TXT -> PDF:</b> Hujjatni PDF formatga o'tkazish.
• <b>PDF -> Word:</b> PDFni Wordga konvertatsiya qilish.
• <b>Split:</b> PDF sahifalarini kesish.
"""

# --- 5. HANDLERS ---

@dp.message(Command("start"))
async def start(m: types.Message):
    G_DATA[m.from_user.id] = {'files': [], 'state': None}
    await m.answer(f"👋 Salom {m.from_user.first_name}! Fayl yuboring.", reply_markup=main_kb(m.from_user.id))

@dp.message(F.text)
async def text_handler(m: types.Message):
    uid, txt = m.from_user.id, m.text
    state = G_DATA.get(uid, {}).get('state')

    # ADMIN REPLY LOGIC
    if str(uid) == ADMIN_ID and m.reply_to_message:
        replied_text = m.reply_to_message.text or m.reply_to_message.caption or ""
        match = re.search(r"#ID(\d+)", replied_text)
        if match:
            target_id = match.group(1)
            try:
                await bot.send_message(target_id, f"👨‍💻 <b>Admin javobi:</b>\n\n{html.escape(txt)}")
                await m.answer("✅ Javob yuborildi.")
            except: await m.answer("❌ Foydalanuvchi bloklagan.")
        return

    # PDF SPLIT
    if state == "split":
        try:
            s, e = map(int, txt.split("-"))
            loop = asyncio.get_event_loop()
            def do_split():
                r = PdfReader(io.BytesIO(G_DATA[uid]['doc']))
                w = PdfWriter()
                for i in range(s-1, min(e, len(r.pages))): w.add_page(r.pages[i])
                o = io.BytesIO(); w.write(o); return o.getvalue()
            pdf = await loop.run_in_executor(None, do_split)
            await m.answer_document(BufferedInputFile(pdf, filename="kesilgan.pdf"), caption="✅ Tayyor")
        except: await m.answer("❌ Xato! Misol: 1-5")
        G_DATA[uid]['state'] = None
        return

    if txt == "ℹ️ Info": await m.answer(INFO_TEXT)
    elif txt == "👨‍💻 Adminga murojaat":
        G_DATA[uid]['state'] = "contact"
        await m.answer("Xabarni yozing:", reply_markup=types.ReplyKeyboardRemove())
    elif G_DATA.get(uid, {}).get('state') == "contact":
        await bot.send_message(ADMIN_ID, f"📩 #ID{uid} dan murojaat:\n{html.escape(txt)}")
        await m.answer("✅ Adminga yetkazildi.", reply_markup=main_kb(uid))
        G_DATA[uid]['state'] = None

@dp.message(F.photo)
async def photo_h(m: types.Message):
    uid = m.from_user.id
    if uid not in G_DATA: G_DATA[uid] = {'files': []}
    f = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(f.file_path)
    G_DATA[uid]['files'].append(content.read())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="to_pdf"), InlineKeyboardButton(text="📝 Word", callback_data="to_word")],
        [InlineKeyboardButton(text="🔍 OCR PRO", callback_data="to_ocr"), InlineKeyboardButton(text="✨ AI Enhance", callback_data="to_enhance")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm {len(G_DATA[uid]['files'])} ta bo'ldi. Amallarni tanlang:", reply_markup=kb)

@dp.message(F.document)
async def doc_h(m: types.Message):
    uid = m.from_user.id
    f = await bot.get_file(m.document.file_id)
    content = await bot.download_file(f.file_path)
    G_DATA[uid] = {'doc': content.read(), 'state': None}
    
    kb = []
    if "pdf" in m.document.mime_type:
        kb = [[InlineKeyboardButton(text="✂️ Kesish", callback_data="split"), InlineKeyboardButton(text="📝 Wordga", callback_data="pdf2word")]]
    else:
        kb = [[InlineKeyboardButton(text="📄 PDFga o'tkazish", callback_data="any2pdf")]]
    await m.reply(f"📂 {m.document.file_name} qabul qilindi.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- CALLBACKS ---
@dp.callback_query(F.data)
async def call_worker(call: types.CallbackQuery):
    uid, d = call.from_user.id, call.data
    files = G_DATA.get(uid, {}).get('files', [])

    if d == "clear": G_DATA[uid]['files'] = []; await call.message.delete(); await call.message.answer("🗑 Tozalandi."); return

    if d == "to_ocr":
        if not files: return
        msg = await call.message.edit_text("⏳ <b>PRO OCR tahlil qilmoqda...</b>")
        loop = asyncio.get_event_loop()
        txt = await loop.run_in_executor(None, ocr_process_pro, files)
        safe_txt = html.escape(txt)
        if len(safe_txt) > 4000:
            await call.message.answer_document(BufferedInputFile(txt.encode(), filename="ocr.txt"))
        else:
            await call.message.answer(f"📝 <b>Natija:</b>\n\n<pre>{safe_txt}</pre>")
        await msg.delete(); G_DATA[uid]['files'] = []

    if d == "any2pdf":
        msg = await call.message.edit_text("⏳ <b>Hujjat PDF ga o'girilmoqda...</b>")
        loop = asyncio.get_event_loop()
        pdf_res = None
        doc_content = G_DATA[uid]['doc']
        try:
            if b"PK\x03\x04" in doc_content[:4]: # DOCX Signature
                pdf_res = await loop.run_in_executor(None, docx_to_pdf_engine, doc_content)
            else: # TXT as default
                pdf_res = await loop.run_in_executor(None, create_pdf_from_text, doc_content.decode('utf-8', errors='ignore'))
        except: pass
        if pdf_res: await call.message.answer_document(BufferedInputFile(pdf_res, filename="hujjat.pdf"))
        else: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    if d == "pdf2word":
        msg = await call.message.edit_text("⏳ <b>Wordga konvertatsiya...</b>")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, convert_pdf_to_docx_safe, G_DATA[uid]['doc'])
        if docx: await call.message.answer_document(BufferedInputFile(docx, filename="converted.docx"))
        else: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    if d == "to_pdf":
        msg = await call.message.edit_text("⏳ <b>PDF yasalmoqda...</b>")
        loop = asyncio.get_event_loop()
        pdf = await loop.run_in_executor(None, img2pdf.convert, files)
        await call.message.answer_document(BufferedInputFile(pdf, filename="scan.pdf"))
        await msg.delete(); G_DATA[uid]['files'] = []

    if d == "split": G_DATA[uid]['state'] = "split"; await call.message.answer("✂️ Oraliqni yozing (Masalan: 1-5):")

# --- 6. RUNNER ---
def run_bot():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    new_loop.run_until_complete(starter())

if not any(t.name == "AiogramThread" for t in threading.enumerate()):
    threading.Thread(target=run_bot, name="AiogramThread", daemon=True).start()

# --- 7. ADMIN PANEL ---
st.markdown('<p class="header-text">🛡️ AI Studio Pro Dashboard</p>', unsafe_allow_html=True)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    p = st.text_input("Security Key", type="password")

if p == ADMIN_PASS:
    st.success("Tizim Online")
    c1, c2 = st.columns(2)
    c1.metric("Aktiv Userlar", len(G_DATA)); c2.metric("Oqimlar", threading.active_count())
    st.info("Barcha jarayonlar barqaror.")
else:
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg")
    st.info("Boshqaruv uchun parolni kiriting.")
