import streamlit as st
import asyncio, threading, io, os, re, tempfile, cv2, html
import numpy as np
import pytesseract, img2pdf
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

# --- 1. GLOBAL XOTIRA VA PAROL ---
if "G_DATA" not in globals(): G_DATA = {}
ADMIN_PASS = "1221"

# --- 2. PREMIUM DIZAYN ---
st.set_page_config(page_title="AI Studio Pro 2026", layout="wide", page_icon="💎")
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; }
    .info-box { background: #0d1117; border-left: 5px solid #1f6feb; padding: 20px; border-radius: 8px; }
    .header-text { color: #58a6ff; font-size: 40px; font-weight: bold; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
except:
    st.error("Secrets sozlanmagan!")
    st.stop()

# --- 3. SUPER PRO MEDIA ENGINE ---

def ocr_process_super_pro(image_list):
    """Soya va shovqinlarni tozalovchi eng kuchli OCR rejimi"""
    full_text = ""
    for img_bytes in image_list:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        # 1. Kattalashtirish
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        # 2. Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # 3. CLAHE - Soyalarni muvozanatlash
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)
        # 4. Adaptive Thresholding - Soyaning ichidagi matnni ko'radi
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        # 5. OCR (O'zbek, Rus, Ingliz)
        text = pytesseract.image_to_string(thresh, lang='eng+uzb+rus', config='--oem 3 --psm 3')
        full_text += text + "\n\n----------------\n\n"
    return html.escape(full_text)

def create_pdf_from_text(text_content):
    """Faqat ReportLab orqali 100% ishlaydigan PDF yaratish"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    text_obj = p.beginText(40, height - 40)
    text_obj.setFont("Helvetica", 12)
    for line in text_content.split('\n'):
        for wrapped in simpleSplit(line, "Helvetica", 12, width - 80):
            if text_obj.getY() < 40:
                p.drawText(text_obj); p.showPage()
                text_obj = p.beginText(40, height - 40); text_obj.setFont("Helvetica", 12)
            text_obj.textLine(wrapped)
    p.drawText(text_obj); p.save(); buffer.seek(0)
    return buffer.getvalue()

def docx_to_pdf_engine(docx_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
        tf.write(docx_bytes); path = tf.name
    try:
        doc = Document(path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return create_pdf_from_text(text)
    finally:
        if os.path.exists(path): os.remove(path)

# --- 4. BOT SETUP (AIOGRAM 3) ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

def main_kb(uid):
    kb = [[KeyboardButton(text="ℹ️ Info"), KeyboardButton(text="👨‍💻 Adminga murojaat")]]
    if str(uid) == ADMIN_ID: kb.append([KeyboardButton(text="💎 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- 5. HANDLERS ---
@dp.message(Command("start"))
async def start(m: types.Message):
    G_DATA[m.from_user.id] = {'files': [], 'state': None}
    await m.answer(f"👋 Salom {m.from_user.first_name}!", reply_markup=main_kb(m.from_user.id))

@dp.message(F.text)
async def text_handler(m: types.Message):
    uid, txt = m.from_user.id, m.text
    state = G_DATA.get(uid, {}).get('state')

    if str(uid) == ADMIN_ID and m.reply_to_message:
        try:
            tid = re.search(r"#ID(\d+)", m.reply_to_message.text or m.reply_to_message.caption).group(1)
            await bot.send_message(tid, f"👨‍💻 <b>Admin:</b>\n\n{html.escape(txt)}")
            await m.answer("✅ Yuborildi.")
        except: await m.answer("❌ Xato.")
        return

    if txt == "ℹ️ Info":
        await m.answer("📸 Rasm -> PDF/Word/OCR\n📄 PDF -> Word/Kesish\n📝 DOCX/TXT -> PDF")
    elif txt == "👨‍💻 Adminga murojaat":
        G_DATA[uid]['state'] = "contact"
        await m.answer("Xabarni yozing:", reply_markup=types.ReplyKeyboardRemove())
    elif state == "contact":
        await bot.send_message(ADMIN_ID, f"📩 #ID{uid} dan:\n{html.escape(txt)}")
        await m.answer("✅ Adminga ketdi.", reply_markup=main_kb(uid)); G_DATA[uid]['state'] = None

@dp.message(F.photo)
async def photo_h(m: types.Message):
    uid = m.from_user.id
    if uid not in G_DATA: G_DATA[uid] = {'files': []}
    f = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(f.file_path)
    G_DATA[uid]['files'].append(content.read())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="to_pdf"), InlineKeyboardButton(text="🔍 OCR PRO", callback_data="to_ocr")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm {len(G_DATA[uid]['files'])} ta.", reply_markup=kb)

@dp.message(F.document)
async def doc_h(m: types.Message):
    uid = m.from_user.id
    f = await bot.get_file(m.document.file_id)
    content = await bot.download_file(f.file_path)
    G_DATA[uid] = {'doc': content.read(), 'state': None}
    kb = []
    if "pdf" in m.document.mime_type:
        kb = [[InlineKeyboardButton(text="📝 Wordga", callback_data="pdf2word")]]
    else:
        kb = [[InlineKeyboardButton(text="📄 PDFga o'tkazish", callback_data="any2pdf")]]
    await m.reply("📂 Fayl qabul qilindi:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data)
async def call_worker(call: types.CallbackQuery):
    uid, d = call.from_user.id, call.data
    files = G_DATA.get(uid, {}).get('files', [])

    if d == "to_ocr":
        if not files: return
        msg = await call.message.edit_text("⏳ <b>Super PRO OCR tahlil qilmoqda...</b>")
        loop = asyncio.get_event_loop()
        txt = await loop.run_in_executor(None, ocr_process_super_pro, files)
        if len(txt) > 4000:
            await call.message.answer_document(BufferedInputFile(txt.encode(), filename="ocr.txt"))
        else:
            await call.message.answer(f"📝 <b>Natija:</b>\n\n<pre>{txt}</pre>")
        await msg.delete(); G_DATA[uid]['files'] = []

    elif d == "any2pdf":
        msg = await call.message.edit_text("⏳ <b>Hujjat PDF ga o'girilmoqda...</b>")
        loop = asyncio.get_event_loop()
        doc_content = G_DATA[uid]['doc']
        try:
            if b"PK\x03\x04" in doc_content[:4]: # DOCX
                pdf_res = await loop.run_in_executor(None, docx_to_pdf_engine, doc_content)
            else: # TXT
                pdf_res = await loop.run_in_executor(None, create_pdf_from_text, doc_content.decode('utf-8', errors='ignore'))
            await call.message.answer_document(BufferedInputFile(pdf_res, filename="hujjat.pdf"))
        except: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    elif d == "clear": G_DATA[uid]['files'] = []; await call.message.answer("Tozalandi.")

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
    p = st.text_input("Parol", type="password")

if p == ADMIN_PASS:
    st.success("Tizim Online")
    st.metric("Users", len(G_DATA))
else:
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg")
    
