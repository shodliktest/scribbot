import streamlit as st
import asyncio
import threading
import io
import os
import re
import tempfile
import cv2
import html
import json
import numpy as np
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
from google.cloud import vision

# --- 1. GLOBAL STORAGE ---
if "G_DATA" not in globals():
    G_DATA = {} 

# --- 2. CONFIGURATION & AUTHENTICATION ---
st.set_page_config(page_title="Google Vision AI Bot", layout="wide", page_icon="👁️")

# Streamlit sirli kalitlarini o'qish va Google JSON faylini yaratish
try:
    # Telegram sozlamalari
    if "telegram" in st.secrets:
        BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
        ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
    else:
        st.error("❌ 'telegram' bo'limi secrets.toml da topilmadi!")
        st.stop()

    # Google Cloud sozlamalari
    if "gcp_service_account" in st.secrets:
        service_info = dict(st.secrets["gcp_service_account"])
        
        # MUHIM: Private Keydagi \n belgilarni to'g'rilash (Streamlit xatosi oldini olish uchun)
        if "private_key" in service_info:
            service_info["private_key"] = service_info["private_key"].replace("\\n", "\n")
        
        # Vaqtinchalik JSON fayl yaratish
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(service_info, f)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name
    else:
        st.warning("⚠️ Google Cloud Credentials ('gcp_service_account') topilmadi! Vision API ishlamaydi.")

except Exception as e:
    st.error(f"❌ Secrets faylida xatolik: {e}")
    st.stop()

# --- 3. GOOGLE VISION ENGINE & EFFECTS ---

def google_vision_scan(image_bytes):
    """Google Cloud Vision API orqali matnni o'qish"""
    try:
        client = vision.ImageAnnotatorClient()
        content = image_bytes
        image = vision.Image(content=content)
        # DOCUMENT_TEXT_DETECTION - eng kuchli rejim
        response = client.document_text_detection(image=image)
        
        if response.error.message:
            return f"❌ Google API Xatosi: {response.error.message}"
            
        return response.full_text_annotation.text if response.full_text_annotation else "Matn topilmadi."
    except Exception as e:
        return f"❌ Tizim xatosi: {e}"

def process_image_effect(img_bytes, effect="original"):
    """Rasmga effekt berish (Oq-qora, HD)"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if effect == "bw": # Oq-Qora (Skaner effekti)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        _, buf = cv2.imencode(".jpg", processed)
        return buf.tobytes()
        
    elif effect == "enhance": # Sifatni oshirish
        cleaned = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
        pil_img = Image.fromarray(cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB))
        enhancer = ImageEnhance.Sharpness(pil_img)
        sharpened = enhancer.enhance(1.5)
        contrast = ImageEnhance.Contrast(sharpened)
        final_pil = contrast.enhance(1.2)
        buf = io.BytesIO()
        final_pil.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
        
    else: # Original
        return img_bytes

# --- 4. CONVERTERS ---

def create_pdf_from_text(text_content):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    text_obj = p.beginText(40, height - 40)
    text_obj.setFont("Helvetica", 12)
    for line in text_content.split('\n'):
        wrapped_lines = simpleSplit(line, "Helvetica", 12, width - 80)
        for wrapped in wrapped_lines:
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
        text = "\n".join([para.text for para in doc.paragraphs])
        return create_pdf_from_text(text)
    finally:
        if os.path.exists(path): os.remove(path)

def convert_pdf_to_docx_safe(pdf_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
        tf.write(pdf_bytes); temp_pdf = tf.name
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

def images_to_docx(image_list):
    doc = Document()
    for img in image_list:
        doc.add_picture(io.BytesIO(img), width=Inches(6))
        doc.add_page_break()
    b = io.BytesIO(); doc.save(b); return b.getvalue()

# --- 5. BOT SETUP ---
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
<b>👁️ GOOGLE VISION AI BOT</b>

📸 <b>Rasm funksiyalari:</b>
• <b>🔍 Google OCR:</b> Rasmdagi matnni o'qish (Eng aniq)
• <b>📄 PDF Skaner:</b> Rasmlarni PDF qilish (HD sifat)
• <b>✨ Tiniqlash:</b> Sifatni oshirish

📂 <b>Fayl funksiyalari:</b>
• <b>PDF ➡️ Word</b> (Konvertatsiya)
• <b>Word ➡️ PDF</b>
• <b>Split PDF</b> (Kesish)
"""

# --- 6. HANDLERS ---
@dp.message(Command("start"))
async def start(m: types.Message):
    G_DATA[m.from_user.id] = {'files': [], 'state': None}
    await m.answer(f"👋 Salom {m.from_user.first_name}!\nGoogle Vision AI ishlamoqda.", reply_markup=main_kb(m.from_user.id))

@dp.message(F.text)
async def text_handler(m: types.Message):
    uid, txt = m.from_user.id, m.text
    state = G_DATA.get(uid, {}).get('state')

    if str(uid) == ADMIN_ID and m.reply_to_message:
        replied_text = m.reply_to_message.text or m.reply_to_message.caption or ""
        match = re.search(r"#ID(\d+)", replied_text)
        if match:
            try:
                await bot.send_message(match.group(1), f"👨‍💻 <b>Admin:</b>\n{html.escape(txt)}")
                await m.answer("✅ Javob yuborildi.")
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
            await m.answer_document(BufferedInputFile(pdf, filename="kesilgan.pdf"))
        except: await m.answer("❌ Xato! Masalan: 1-5")
        G_DATA[uid]['state'] = None
        return

    if txt == "ℹ️ Info": await m.answer(INFO_TEXT)
    elif txt == "👨‍💻 Adminga murojaat":
        G_DATA[uid]['state'] = "contact"
        await m.answer("Xabarni yozing:", reply_markup=types.ReplyKeyboardRemove())
    elif state == "contact":
        await bot.send_message(ADMIN_ID, f"📩 #ID{uid} Userdan:\n{html.escape(txt)}")
        await m.answer("✅ Yuborildi.", reply_markup=main_kb(uid))
        G_DATA[uid]['state'] = None

@dp.message(F.photo)
async def photo_h(m: types.Message):
    uid = m.from_user.id
    if uid not in G_DATA: G_DATA[uid] = {'files': []}
    f = await bot.get_file(m.photo[-1].file_id)
    c = await bot.download_file(f.file_path)
    G_DATA[uid]['files'].append(c.read())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Google OCR", callback_data="to_ocr")],
        [InlineKeyboardButton(text="✨ HD Sifat", callback_data="to_enhance"), InlineKeyboardButton(text="📝 Wordga", callback_data="to_word")],
        [InlineKeyboardButton(text="📄 PDF (Orig)", callback_data="pdf_orig"), InlineKeyboardButton(text="📄 PDF (BW)", callback_data="pdf_bw")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm #{len(G_DATA[uid]['files'])}.\nTanlang:", reply_markup=kb)

@dp.message(F.document)
async def doc_h(m: types.Message):
    uid = m.from_user.id
    f = await bot.get_file(m.document.file_id)
    c = await bot.download_file(f.file_path)
    G_DATA[uid] = {'doc': c.read(), 'state': None}
    
    kb = []
    if "pdf" in m.document.mime_type:
        kb = [[InlineKeyboardButton(text="✂️ Kesish", callback_data="split"), InlineKeyboardButton(text="📝 Wordga", callback_data="pdf2word")]]
    else:
        kb = [[InlineKeyboardButton(text="📄 PDFga", callback_data="any2pdf")]]
    await m.reply(f"📂 {m.document.file_name}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data)
async def call_worker(call: types.CallbackQuery):
    uid, d = call.from_user.id, call.data
    files = G_DATA.get(uid, {}).get('files', [])

    if d == "clear": 
        G_DATA[uid]['files'] = []
        await call.message.delete(); await call.message.answer("🗑 Tozalandi."); return

    if d == "to_ocr":
        if not files: return
        msg = await call.message.edit_text("⏳ <b>Google Vision...</b>")
        loop = asyncio.get_event_loop()
        res = ""
        for i, img in enumerate(files):
            txt = await loop.run_in_executor(None, google_vision_scan, img)
            res += f"📄 Sahifa {i+1}:\n{html.escape(txt)}\n{'='*20}\n"
        
        if len(res) > 3000:
            await call.message.answer_document(BufferedInputFile(res.encode(), filename="ocr.txt"))
        else:
            await call.message.answer(f"📝 <b>Natija:</b>\n<pre>{res}</pre>")
        await msg.delete(); G_DATA[uid]['files'] = []

    elif d == "to_enhance":
        msg = await call.message.edit_text("✨ <b>Tiniqlashtirilmoqda...</b>")
        loop = asyncio.get_event_loop()
        for i, img in enumerate(files):
            res = await loop.run_in_executor(None, process_image_effect, img, "enhance")
            await call.message.answer_photo(BufferedInputFile(res, filename=f"hd_{i+1}.jpg"))
        await msg.delete()

    elif d.startswith("pdf_"):
        mode = d.split("_")[1]
        msg = await call.message.edit_text("⏳ <b>PDF yasalmoqda...</b>")
        loop = asyncio.get_event_loop()
        processed = []
        for img in files:
            p = await loop.run_in_executor(None, process_image_effect, img, mode)
            processed.append(p)
        pdf = await loop.run_in_executor(None, img2pdf.convert, processed)
        await call.message.answer_document(BufferedInputFile(pdf, filename=f"scan_{mode}.pdf"))
        await msg.delete(); G_DATA[uid]['files'] = []

    elif d == "to_word":
        msg = await call.message.edit_text("⏳ <b>Wordga...</b>")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, images_to_docx, files)
        await call.message.answer_document(BufferedInputFile(docx, filename="images.docx"))
        await msg.delete(); G_DATA[uid]['files'] = []
    
    elif d == "any2pdf":
        msg = await call.message.edit_text("⏳ <b>PDFga...</b>")
        loop = asyncio.get_event_loop()
        doc_c = G_DATA[uid]['doc']
        try:
            if b"PK\x03\x04" in doc_c[:4]: pdf = await loop.run_in_executor(None, docx_to_pdf_engine, doc_c)
            else: pdf = await loop.run_in_executor(None, create_pdf_from_text, doc_c.decode(errors='ignore'))
            await call.message.answer_document(BufferedInputFile(pdf, filename="hujjat.pdf"))
        except: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    elif d == "pdf2word":
        msg = await call.message.edit_text("⏳ <b>Wordga...</b>")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, convert_pdf_to_docx_safe, G_DATA[uid]['doc'])
        if docx: await call.message.answer_document(BufferedInputFile(docx, filename="converted.docx"))
        else: await call.message.answer("❌ Xatolik.")
        await msg.delete()
        
    elif d == "split":
        G_DATA[uid]['state'] = "split"
        await call.message.answer("✂️ Oraliqni yozing (1-3):")

# --- 7. RUNNER (MUHIM: THREADING FIX) ---
def run_bot():
    """Botni alohida thread ichida xavfsiz ishga tushirish"""
    try:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        
        async def runner():
            # Webhookni tozalash va Pollingni boshlash
            await bot.delete_webhook(drop_pending_updates=True)
            await dp.start_polling(bot, handle_signals=False)
            
        new_loop.run_until_complete(runner())
    except Exception as e:
        print(f"Bot Error: {e}")

# Streamlit har safar yangilanganda thread qayta ochilmasligi uchun tekshiruv
if not any(t.name == "AiogramThread" for t in threading.enumerate()):
    t = threading.Thread(target=run_bot, name="AiogramThread", daemon=True)
    t.start()

# --- 8. DASHBOARD ---
st.title("🛡️ AI Studio Pro - Vision Edition")
st.success("Bot muvaffaqiyatli ishga tushdi! 🟢")
st.write(f"Joriy Project ID: `{st.secrets['gcp_service_account']['project_id']}`")
    
