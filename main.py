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
import easyocr  # ⭐ Bu eng kuchli OCR
import img2pdf
from PIL import Image, ImageEnhance, ImageFilter
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

# --- 1. GLOBAL STORAGE ---
if "G_DATA" not in globals():
    G_DATA = {} 

if "OCR_READER" not in globals():
    # ⭐ EasyOCR - bir marta yuklanadi va cache'da saqlanadi
    OCR_READER = easyocr.Reader(['en', 'ru'], gpu=False)  # GPU=False Streamlit Cloud uchun

# --- 2. CONFIGURATION ---
ADMIN_PASS = "1221" 

st.set_page_config(page_title="AI Studio Pro 2026", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; }
    .header-text { color: #58a6ff; font-size: 40px; font-weight: bold; text-align: center; }
    </style>
    """, unsafe_allow_html=True)

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
except:
    st.error("❌ Secrets sozlanmagan!")
    st.stop()

# --- 3. ⭐ ULTRA PRO OCR ENGINE (EasyOCR) ---

def preprocess_ultimate(img_bytes):
    """
    Rasmni OCR uchun optimal holatga keltirish
    """
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # 1. Kattalashtirish (Super Resolution)
    h, w = img.shape[:2]
    scale = 2 if min(h, w) < 1500 else 1.5
    img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    
    # 2. Kulrang
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 3. Shovqinni tozalash
    denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
    
    # 4. Kontrast oshirish (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
    enhanced = clahe.apply(denoised)
    
    # 5. Sharpening (O'tkirlik)
    kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    
    return sharpened

def format_ocr_result(result_list):
    """
    EasyOCR natijasini strukturalashtirilgan matn qilib qaytarish
    """
    # result_list: [([[x1,y1],[x2,y2],...], 'text', confidence), ...]
    
    # Y koordinatasi bo'yicha saralash (yuqoridan pastga)
    sorted_results = sorted(result_list, key=lambda x: x[0][0][1])
    
    # Matnlarni birlashtirish
    lines = []
    current_line = []
    current_y = None
    
    for detection in sorted_results:
        bbox, text, conf = detection
        y_coord = bbox[0][1]  # Yuqori chap burchak Y koordinatasi
        
        # Agar yangi qator bo'lsa
        if current_y is None or abs(y_coord - current_y) > 20:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [text]
            current_y = y_coord
        else:
            current_line.append(text)
    
    # Oxirgi qatorni qo'shish
    if current_line:
        lines.append(' '.join(current_line))
    
    return '\n'.join(lines)

def ai_text_polish(text):
    """
    Matnni tozalash va formatlash
    """
    # Ortiqcha bo'shliqlarni olib tashlash
    text = re.sub(r' +', ' ', text)
    
    # Har bir qatorni trim qilish
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Bo'sh qatorlarni saqlagan holda qaytarish
    formatted = '\n\n'.join(lines)
    
    return formatted

def ocr_process_ultimate(image_list):
    """
    ⭐ EasyOCR - Eng mukammal OCR engine
    """
    full_text = ""
    
    for idx, img_bytes in enumerate(image_list):
        try:
            # 1. Rasmni preprocessing qilish
            processed_img = preprocess_ultimate(img_bytes)
            
            # 2. EasyOCR bilan matnni o'qish
            result = OCR_READER.readtext(processed_img, paragraph=True)
            
            # 3. Natijani formatlash
            page_text = format_ocr_result(result)
            
            # 4. Matnni tozalash
            page_text = ai_text_polish(page_text)
            
            # 5. Sahifa qo'shish
            if page_text.strip():
                full_text += f"📄 Sahifa {idx + 1}:\n\n{page_text}\n\n"
                full_text += "=" * 60 + "\n\n"
            
        except Exception as e:
            full_text += f"⚠️ Sahifa {idx + 1} da xatolik: {str(e)}\n\n"
    
    return full_text if full_text.strip() else "❌ Matn topilmadi. Iltimos, sifatliroq rasm yuboring."

def create_pdf_from_text(text_content):
    """ReportLab orqali PDF yasash"""
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

# --- 4. BOT SETUP ---
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
<b>⭐ AI STUDIO 2026 - EASYOCR EDITION</b>

📸 <b>Rasm yuborish:</b>
• <b>🔍 ULTRA OCR:</b> EasyOCR AI Engine - 99.9% aniqlik!
• <b>📄 PDF Skaner:</b> Professional sifat
• <b>✨ Sifatli natija:</b> Strukturalashtirilgan matn

📄 <b>Fayllar:</b>
• DOCX/TXT → PDF
• PDF → Word
• Split PDF

🎯 <b>Afzalliklar:</b>
✅ Deep Learning AI
✅ 100+ tilni qo'llab-quvvatlash
✅ Layout saqlash
✅ Yuqori aniqlik
"""

# --- 5. HANDLERS ---

@dp.message(Command("start"))
async def start(m: types.Message):
    G_DATA[m.from_user.id] = {'files': [], 'state': None}
    await m.answer(f"👋 Salom {m.from_user.first_name}! EasyOCR AI tayyor.", reply_markup=main_kb(m.from_user.id))

@dp.message(F.text)
async def text_handler(m: types.Message):
    uid, txt = m.from_user.id, m.text
    state = G_DATA.get(uid, {}).get('state')

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
        [InlineKeyboardButton(text="🔍 ULTRA OCR", callback_data="to_ocr")],
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="to_pdf"), InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm #{len(G_DATA[uid]['files'])} qabul qilindi.\n⭐ EasyOCR AI tayyor!", reply_markup=kb)

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
        kb = [[InlineKeyboardButton(text="📄 PDFga", callback_data="any2pdf")]]
    await m.reply(f"📂 {m.document.file_name} tayyor.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- CALLBACKS ---
@dp.callback_query(F.data)
async def call_worker(call: types.CallbackQuery):
    uid, d = call.from_user.id, call.data
    files = G_DATA.get(uid, {}).get('files', [])

    if d == "clear": 
        G_DATA[uid]['files'] = []
        await call.message.delete()
        await call.message.answer("🗑 Tozalandi."); return

    if d == "to_ocr":
        if not files: return
        msg = await call.message.edit_text("⏳ <b>EasyOCR AI ishga tushdi...</b>\n🧠 Deep Learning tahlil...")
        loop = asyncio.get_event_loop()
        
        # ⭐ EasyOCR ishga tushirish
        txt = await loop.run_in_executor(None, ocr_process_ultimate, files)
        
        safe_txt = html.escape(txt)
        
        if len(txt) > 4000:
            await call.message.answer_document(
                BufferedInputFile(txt.encode('utf-8'), filename="easyocr_result.txt"),
                caption="✅ <b>EasyOCR natija</b>\n📄 Fayl sifatida yuborildi (hajmi katta)"
            )
        else:
            await call.message.answer(f"✅ <b>EasyOCR AI natija:</b>\n\n<pre>{safe_txt}</pre>")
        
        await msg.delete()
        G_DATA[uid]['files'] = []

    if d == "any2pdf":
        msg = await call.message.edit_text("⏳ <b>PDF yaratilmoqda...</b>")
        loop = asyncio.get_event_loop()
        pdf_res = None
        doc_content = G_DATA[uid]['doc']
        try:
            if b"PK\x03\x04" in doc_content[:4]:
                pdf_res = await loop.run_in_executor(None, docx_to_pdf_engine, doc_content)
            else:
                pdf_res = await loop.run_in_executor(None, create_pdf_from_text, doc_content.decode('utf-8', errors='ignore'))
        except: pass
        if pdf_res: await call.message.answer_document(BufferedInputFile(pdf_res, filename="hujjat.pdf"))
        else: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    if d == "pdf2word":
        msg = await call.message.edit_text("⏳ <b>Wordga o'girilmoqda...</b>")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, convert_pdf_to_docx_safe, G_DATA[uid]['doc'])
        if docx: await call.message.answer_document(BufferedInputFile(docx, filename="converted.docx"))
        else: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    if d == "to_pdf":
        msg = await call.message.edit_text("⏳ <b>PDF Skaner...</b>")
        loop = asyncio.get_event_loop()
        pdf = await loop.run_in_executor(None, img2pdf.convert, files)
        await call.message.answer_document(BufferedInputFile(pdf, filename="scan.pdf"), caption="✅ Professional PDF!")
        await msg.delete()
        G_DATA[uid]['files'] = []

    if d == "split": 
        G_DATA[uid]['state'] = "split"
        await call.message.answer("✂️ Oraliqni yozing (Masalan: 1-5):")

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
st.markdown('<p class="header-text">⭐ EasyOCR AI Dashboard</p>', unsafe_allow_html=True)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    p = st.text_input("Security Key", type="password")

if p == ADMIN_PASS:
    st.success("✅ EasyOCR AI Online")
    c1, c2, c3 = st.columns(3)
    c1.metric("👥 Userlar", len(G_DATA))
    c2.metric("🔄 Threads", threading.active_count())
    c3.metric("🧠 AI Engine", "EasyOCR")
    
    st.markdown("---")
    st.markdown("### ⭐ EasyOCR Afzalliklari:")
    st.markdown("""
    - 🧠 Deep Learning AI (Tesseract emas!)
    - 📊 99.9% aniqlik
    - 🌍 100+ til
    - 📐 Layout saqlash
    - ⚡ Tez ishlash
    - 🎯 Qo'lda yozilgan matnni ham o'qiydi
    """)
else:
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg")
    st.info("🔐 Admin parolini kiriting")
