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
from docx.shared import Inches, Pt
from PyPDF2 import PdfReader, PdfWriter
from pdf2docx import Converter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import simpleSplit
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
import pandas as pd

# --- 1. GLOBAL XOTIRA ---
if "G_DATA" not in globals(): G_DATA = {}

# --- 2. ADMIN PAROL & SOZLAMALAR ---
# 🔐 ADMIN PAROL SHU YERDA:
ADMIN_PASS = "1221"

st.set_page_config(page_title="AI Studio Pro", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 15px; }
    .info-box { background: #0d1117; border-left: 5px solid #1f6feb; padding: 20px; border-radius: 8px; }
    </style>
    """, unsafe_allow_html=True)

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
except:
    st.error("❌ Secrets (BOT_TOKEN, ADMIN_ID) sozlanmagan!")
    st.stop()

# --- 3. KUCHAYTIRILGAN MEDIA FUNKSIYALAR ---

def ocr_pro_high_quality(image_list):
    """Eng yuqori sifatli OCR (Pre-processing bilan)"""
    full_text = ""
    # Tesseract sozlamalari: --oem 3 (Neural Net), --psm 6 (Block text)
    custom_config = r'--oem 3 --psm 6'
    
    for img_bytes in image_list:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 1. Upscaling (2 barobar kattalashtirish)
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # 2. Grayscale & Denoising
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
        
        # 3. Binarization (Otsu Thresholding) - Matnni qora, fonni oq qiladi
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        # 4. OCR
        pil_img = Image.fromarray(thresh)
        text = pytesseract.image_to_string(pil_img, lang='uzb+rus+eng', config=custom_config)
        full_text += text + "\n\n----------------\n\n"
        
    return full_text

def create_pdf_from_text(text_content, filename="hujjat.pdf"):
    """Matndan yoki DOCX dan PDF yasash (ReportLab)"""
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    text_object = p.beginText(40, height - 40)
    
    # Standart shrift (Kirillitsani qo'llamasligi mumkin, shuning uchun oddiy)
    # Agar serverda shrift bo'lsa, TTFont bilan yuklash kerak. Hozircha standart:
    text_object.setFont("Helvetica", 12)
    
    # Matnni sahifaga sig'dirish
    lines = text_content.split('\n')
    for line in lines:
        # Uzun qatorlarni bo'lish
        wrapped_lines = simpleSplit(line, "Helvetica", 12, width - 80)
        for wrapped in wrapped_lines:
            # Sahifa tugasa yangisini ochish
            if text_object.getY() < 40:
                p.drawText(text_object)
                p.showPage()
                text_object = p.beginText(40, height - 40)
                text_object.setFont("Helvetica", 12)
            text_object.textLine(wrapped)
            
    p.drawText(text_object)
    p.save()
    buffer.seek(0)
    return buffer.getvalue()

def docx_to_pdf_engine(docx_bytes):
    """DOCX -> Matn -> PDF (Eng ishonchli usul)"""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
        tf.write(docx_bytes)
        temp_path = tf.name
    
    try:
        doc = Document(temp_path)
        full_text = []
        for para in doc.paragraphs:
            full_text.append(para.text)
        text_content = "\n".join(full_text)
        return create_pdf_from_text(text_content)
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)

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

def enhance_image(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    dst = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
    pil = Image.fromarray(cv2.cvtColor(dst, cv2.COLOR_BGR2RGB))
    pil = ImageEnhance.Sharpness(pil).enhance(2.0)
    pil = ImageEnhance.Contrast(pil).enhance(1.2)
    b = io.BytesIO(); pil.save(b, "JPEG", quality=95); return b.getvalue()

def scan_effect(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    _, b = cv2.imencode(".jpg", thresh); return b.tobytes()

def images_to_docx(image_list):
    doc = Document()
    for img in image_list:
        doc.add_picture(io.BytesIO(img), width=Inches(6))
        doc.add_page_break()
    b = io.BytesIO(); doc.save(b); return b.getvalue()

# --- 4. BOT SETUP ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

def main_kb(uid):
    kb = [[KeyboardButton(text="ℹ️ Info"), KeyboardButton(text="👨‍💻 Adminga murojaat")]]
    if str(uid) == ADMIN_ID: kb.append([KeyboardButton(text="💎 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

INFO_TEXT = """
<b>ℹ️ AI STUDIO QO'LLANMASI:</b>

📸 <b>Rasm yuborsangiz:</b>
• <b>🔍 OCR PRO:</b> Rasmdan matnni eng yuqori sifatda o'qish.
• <b>📄 PDF Skaner:</b> Rasmlarni birlashtirib PDF qilish.
• <b>✨ Enhance:</b> Sifatni oshirish.

📄 <b>Fayllar (DOCX, TXT, PDF):</b>
• <b>DOCX/TXT -> PDF:</b> Hujjatlarni PDF formatga o'tkazish.
• <b>PDF -> Word:</b> PDF ni tahrirlanadigan formatga o'tkazish.
• <b>Split:</b> PDF ni kesish.
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

    if str(uid) == ADMIN_ID and m.reply_to_message:
        try:
            tid = re.search(r"#ID(\d+)", m.reply_to_message.text or m.reply_to_message.caption).group(1)
            await bot.send_message(tid, f"👨‍💻 <b>Admin javobi:</b>\n\n{html.escape(txt)}")
            await m.answer("✅ Yuborildi.")
        except: await m.answer("❌ Xatolik.")
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

    if state == "contact":
        await bot.send_message(ADMIN_ID, f"📩 #ID{uid} dan:\n{html.escape(txt)}")
        await m.answer("✅ Yuborildi.", reply_markup=main_kb(uid)); G_DATA[uid]['state'] = None
        return

    if txt == "ℹ️ Info": await m.answer(INFO_TEXT)
    elif txt == "👨‍💻 Adminga murojaat":
        G_DATA[uid]['state'] = "contact"
        await m.answer("Xabarni yozing:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.photo)
async def photo_h(m: types.Message):
    uid = m.from_user.id
    if G_DATA.get(uid, {}).get('state') == "contact":
        await bot.send_message(ADMIN_ID, f"📩 Rasm #ID{uid}:")
        await m.send_copy(ADMIN_ID); await m.answer("✅ Yuborildi.", reply_markup=main_kb(uid))
        G_DATA[uid]['state'] = None; return

    if uid not in G_DATA: G_DATA[uid] = {'files': []}
    f = await bot.download(m.photo[-1])
    G_DATA[uid]['files'].append(f.read())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="to_pdf"), InlineKeyboardButton(text="📝 Word", callback_data="to_word")],
        [InlineKeyboardButton(text="🔍 OCR PRO (Matn)", callback_data="to_ocr"), InlineKeyboardButton(text="✨ Enhance", callback_data="to_enhance")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm {len(G_DATA[uid]['files'])} ta.", reply_markup=kb)

@dp.message(F.document)
async def doc_h(m: types.Message):
    uid = m.from_user.id
    fname = m.document.file_name
    
    if G_DATA.get(uid, {}).get('state') == "contact":
        await bot.send_message(ADMIN_ID, f"📩 Fayl #ID{uid}:")
        await m.send_copy(ADMIN_ID); await m.answer("✅ Yuborildi.", reply_markup=main_kb(uid))
        G_DATA[uid]['state'] = None; return

    f = await bot.download(m.document)
    content = f.read()
    G_DATA[uid] = {'doc': content, 'state': None}
    
    kb = []
    if "pdf" in m.document.mime_type:
        kb = [[InlineKeyboardButton(text="✂️ Kesish", callback_data="split"), InlineKeyboardButton(text="📝 Wordga", callback_data="pdf2word")]]
    elif "word" in m.document.mime_type or "docx" in m.document.mime_type or "txt" in m.document.mime_type or "plain" in m.document.mime_type:
        kb = [[InlineKeyboardButton(text="📄 PDF ga o'tkazish", callback_data="any2pdf")]]
    
    await m.reply(f"📂 {fname} qabul qilindi.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data)
async def call_h(c: types.CallbackQuery):
    uid, d = c.from_user.id, c.data
    files = G_DATA.get(uid, {}).get('files', [])

    if d == "clear": G_DATA[uid] = {'files': []}; await c.message.delete(); await c.message.answer("🗑 Tozalandi."); return

    if d == "to_ocr":
        if not files: return
        msg = await c.message.edit_text("⏳ <b>OCR PRO ishlamoqda...</b>")
        loop = asyncio.get_event_loop()
        txt = await loop.run_in_executor(None, ocr_pro_high_quality, files)
        if len(txt) > 4000: await c.message.answer_document(BufferedInputFile(txt.encode(), filename="ocr.txt"))
        else: await c.message.answer(f"📝 <b>Natija:</b>\n<pre>{html.escape(txt)}</pre>")
        await msg.delete(); G_DATA[uid]['files'] = []

    if d == "any2pdf": # DOCX/TXT -> PDF
        msg = await c.message.edit_text("⏳ <b>PDF yasalmoqda...</b>")
        loop = asyncio.get_event_loop()
        
        pdf_res = None
        # Agar TXT bo'lsa
        if b"%PDF" not in G_DATA[uid]['doc']: # Oddiy tekshiruv
            try:
                # Agar DOCX bo'lsa (binary signature orqali yoki shunchaki try/except)
                pdf_res = await loop.run_in_executor(None, docx_to_pdf_engine, G_DATA[uid]['doc'])
            except:
                # Agar TXT bo'lsa
                txt_content = G_DATA[uid]['doc'].decode('utf-8', errors='ignore')
                pdf_res = await loop.run_in_executor(None, create_pdf_from_text, txt_content)
        
        if pdf_res: await c.message.answer_document(BufferedInputFile(pdf_res, filename="hujjat.pdf"))
        else: await c.message.answer("❌ Fayl formati qo'llab quvvatlanmadi.")
        await msg.delete()

    if d == "pdf2word":
        msg = await c.message.edit_text("⏳ <b>Konvertatsiya...</b>")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, convert_pdf_to_docx_safe, G_DATA[uid]['doc'])
        if docx: await c.message.answer_document(BufferedInputFile(docx, filename="converted.docx"))
        else: await c.message.answer("❌ Xatolik.")
        await msg.delete()

    if d == "to_pdf":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Original", callback_data="s_orig"), InlineKeyboardButton(text="Skaner", callback_data="s_scan")]])
        await c.message.edit_text("Tanlang:", reply_markup=kb); return
    
    if d == "split": G_DATA[uid]['state'] = "split"; await c.message.answer("✂️ 1-5:"); return
    
    if d == "to_word":
        loop = asyncio.get_event_loop(); docx = await loop.run_in_executor(None, images_to_docx, files)
        await c.message.answer_document(BufferedInputFile(docx, filename="images.docx")); G_DATA[uid]['files'] = []

    if d == "to_enhance":
        msg = await c.message.edit_text("⏳ AI...")
        loop = asyncio.get_event_loop()
        for i, img in enumerate(files):
            if i % 2 == 0: await msg.edit_text(f"⏳ Rasm {i+1}...")
            res = await loop.run_in_executor(None, enhance_image, img)
            await c.message.answer_photo(BufferedInputFile(res, filename="hd.jpg"))
        await msg.delete(); G_DATA[uid]['files'] = []

    if d.startswith("s_"):
        msg = await c.message.edit_text("⏳ PDF...")
        st = d.split("_")[1]
        loop = asyncio.get_event_loop()
        def m_pdf():
            p = []
            for i in files: p.append(scan_effect(i) if st == "scan" else i)
            return img2pdf.convert(p)
        pdf = await loop.run_in_executor(None, m_pdf)
        await c.message.answer_document(BufferedInputFile(pdf, filename="scan.pdf"))
        await msg.delete(); G_DATA[uid]['files'] = []

# --- RUNNER ---
def run():
    asyncio.run(bot.delete_webhook(drop_pending_updates=True))
    asyncio.run(dp.start_polling(bot))
if not any(t.name == "BT" for t in threading.enumerate()): threading.Thread(target=run, name="BT", daemon=True).start()

# --- WEB UI ---
st.markdown('<p class="header-text">🛡️ AI Studio Pro</p>', unsafe_allow_html=True)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    p = st.text_input("Parol", type="password")

if p == ADMIN_PASS:
    st.success("Admin Panel")
    t1, t2 = st.tabs(["Statistika", "Info"])
    with t1: st.metric("Users", len(G_DATA)); st.metric("Threads", threading.active_count())
    with t2: st.markdown(f'<div class="info-box">{INFO_TEXT}</div>', unsafe_allow_html=True)
else:
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg")
    st.info("Bot ishlashi uchun Telegramga kiring.")
    
