import streamlit as st
import asyncio
import threading
import io
import os
import re
import tempfile
import cv2
import numpy as np
import pytesseract
import img2pdf
import html  # <--- Xatolikni tuzatish uchun muhim kutubxona
from PIL import Image, ImageEnhance
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader, PdfWriter
from pdf2docx import Converter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from datetime import datetime
import pandas as pd

# --- 1. GLOBAL XOTIRA ---
if "GLOBAL_DATA" not in globals():
    GLOBAL_DATA = {} 

# --- 2. PREMIUM DIZAYN ---
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
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ Secrets fayli sozlanmagan!")
    st.stop()

# --- 3. KUCHAYTIRILGAN FUNKSIYALAR ---

def convert_pdf_to_docx_safe(pdf_bytes):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf_in:
        tf_in.write(pdf_bytes)
        temp_pdf = tf_in.name
    temp_docx = temp_pdf.replace(".pdf", ".docx")
    try:
        cv = Converter(temp_pdf)
        cv.convert(temp_docx, start=0, end=None)
        cv.close()
        with open(temp_docx, "rb") as f: docx_bytes = f.read()
        return docx_bytes
    except: return None
    finally:
        if os.path.exists(temp_pdf): os.remove(temp_pdf)
        if os.path.exists(temp_docx): os.remove(temp_docx)

def enhance_image(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    dst = cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
    pil_img = Image.fromarray(cv2.cvtColor(dst, cv2.COLOR_BGR2RGB))
    pil_img = ImageEnhance.Sharpness(pil_img).enhance(2.0)
    pil_img = ImageEnhance.Contrast(pil_img).enhance(1.2)
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

def scan_effect(img_bytes):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    _, buf = cv2.imencode(".jpg", thresh)
    return buf.tobytes()

def images_to_docx(image_list):
    doc = Document()
    for img in image_list:
        doc.add_picture(io.BytesIO(img), width=Inches(6))
        doc.add_page_break()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

# --- 🔴 ENG KUCHLI OCR REJIMI 🔴 ---

def ocr_process_pro(image_list):
    full_text = ""
    # Tesseract konfiguratsiyasi (Neural Network + Auto Page Segmentation)
    custom_config = r'--oem 3 --psm 6' 
    
    for img_bytes in image_list:
        # 1. Rasmni o'qish
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # 2. Kattalashtirish (Upscaling) - mayda harflar uchun
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        
        # 3. Oq-qora qilish (Grayscale)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 4. Shovqinni tozalash va Binarizatsiya (Thresholding)
        # Bu rasmni faqat qora va oq rangda qoldiradi, OCR uchun ideal
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        
        # 5. PIL formatga o'tkazish
        pil_img = Image.fromarray(thresh)
        
        # 6. Matnni o'qish
        text = pytesseract.image_to_string(pil_img, lang='uzb+rus+eng', config=custom_config)
        full_text += text + "\n\n----------------\n\n"
        
    return full_text

# --- 4. BOT SETUP ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 5. MENYU ---
def get_main_kb(user_id):
    kb = [[KeyboardButton(text="ℹ️ Info"), KeyboardButton(text="👨‍💻 Adminga murojaat")]]
    if str(user_id) == ADMIN_ID:
        kb.append([KeyboardButton(text="💎 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

INFO_TEXT = """
<b>ℹ️ AI STUDIO QO'LLANMASI:</b>

📸 <b>Rasm yuborsangiz:</b>
• <b>📄 PDF Skaner:</b> Rasmlarni bitta PDF kitob qiladi.
• <b>📝 Word (DOCX):</b> Rasmlarni Word hujjatiga joylaydi.
• <b>🔍 OCR (Matn):</b> Rasmdan yozuvni (PRO rejimda) ajratib oladi.
• <b>✨ AI Tiniqlash:</b> Xira rasmlarni tozalaydi.

📄 <b>PDF yuborsangiz:</b>
• <b>✂️ Kesish:</b> Kerakli sahifalarni ajratib beradi.
• <b>📝 Wordga:</b> PDF ni tahrirlanadigan Wordga o'giradi.

<i>Boshlash uchun shunchaki fayl yuboring!</i>
"""

# --- 6. HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    uid = m.from_user.id
    GLOBAL_DATA[uid] = {'files': [], 'state': None}
    await m.answer(f"👋 <b>Salom {m.from_user.first_name}!</b>\n\nMen tayyorman. Rasm yoki fayl yuboring.", reply_markup=get_main_kb(uid))

@dp.message(F.text)
async def text_router(m: types.Message):
    uid = m.from_user.id
    text = m.text
    state = GLOBAL_DATA.get(uid, {}).get('state')

    # ADMIN REPLY
    if str(uid) == ADMIN_ID and m.reply_to_message:
        replied_text = m.reply_to_message.text or m.reply_to_message.caption or ""
        match = re.search(r"#ID(\d+)", replied_text)
        if match:
            target_id = match.group(1)
            try:
                # Xatolikni oldini olish uchun html.escape ishlatamiz
                safe_text = html.escape(text)
                await bot.send_message(target_id, f"👨‍💻 <b>Admin javobi:</b>\n\n{safe_text}")
                await m.answer(f"✅ Javob yuborildi.")
            except: await m.answer("❌ Foydalanuvchi bloklagan.")
        else: await m.answer("❌ #ID topilmadi.")
        return

    # PDF SPLIT
    if state == "waiting_split":
        try:
            start, end = map(int, text.split("-"))
            pdf_content = GLOBAL_DATA[uid]['doc_content']
            loop = asyncio.get_event_loop()
            status = await m.answer("⏳ <b>PDF kesilmoqda...</b>")
            def split_sync():
                reader = PdfReader(io.BytesIO(pdf_content))
                writer = PdfWriter()
                for i in range(start-1, min(end, len(reader.pages))):
                    writer.add_page(reader.pages[i])
                out = io.BytesIO(); writer.write(out); return out.getvalue()
            pdf_out = await loop.run_in_executor(None, split_sync)
            await status.delete()
            await m.answer_document(BufferedInputFile(pdf_out, filename="kesilgan.pdf"), caption="✅ Tayyor!")
        except: await m.answer("❌ Xato! Misol: 1-5")
        GLOBAL_DATA[uid]['state'] = None
        return

    # MUROJAAT
    if state == "waiting_contact":
        safe_msg = html.escape(text) # Xavfsiz matn
        msg = f"📩 <b>YANGI XABAR!</b>\n👤: {m.from_user.full_name}\n🆔: #ID{uid}\n\n📝: {safe_msg}"
        await bot.send_message(ADMIN_ID, msg)
        await m.answer("✅ Adminga yuborildi.", reply_markup=get_main_kb(uid))
        GLOBAL_DATA[uid]['state'] = None
        return

    if text == "ℹ️ Info": await m.answer(INFO_TEXT)
    elif text == "👨‍💻 Adminga murojaat":
        GLOBAL_DATA[uid] = GLOBAL_DATA.get(uid, {})
        GLOBAL_DATA[uid]['state'] = "waiting_contact"
        await m.answer("📝 Xabarni yozing:", reply_markup=types.ReplyKeyboardRemove())

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    uid = m.from_user.id
    if GLOBAL_DATA.get(uid, {}).get('state') == "waiting_contact":
        await bot.send_message(ADMIN_ID, f"📩 <b>Rasm</b> (#ID{uid}):")
        await m.send_copy(ADMIN_ID); await m.answer("✅ Yuborildi.", reply_markup=get_main_kb(uid))
        GLOBAL_DATA[uid]['state'] = None; return

    if uid not in GLOBAL_DATA: GLOBAL_DATA[uid] = {'files': []}
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    GLOBAL_DATA[uid]['files'].append(content.read())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="to_pdf"), InlineKeyboardButton(text="📝 Word (DOCX)", callback_data="to_word")],
        [InlineKeyboardButton(text="🔍 OCR (Matn)", callback_data="to_ocr"), InlineKeyboardButton(text="✨ AI Tiniqlash", callback_data="to_enhance")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.reply(f"✅ Rasm qabul qilindi ({len(GLOBAL_DATA[uid]['files'])} ta).", reply_markup=kb)

@dp.message(F.document)
async def handle_docs(m: types.Message):
    uid = m.from_user.id
    if GLOBAL_DATA.get(uid, {}).get('state') == "waiting_contact":
        await bot.send_message(ADMIN_ID, f"📩 <b>Fayl</b> (#ID{uid}):")
        await m.send_copy(ADMIN_ID); await m.answer("✅ Yuborildi.", reply_markup=get_main_kb(uid))
        GLOBAL_DATA[uid]['state'] = None; return

    file = await bot.get_file(m.document.file_id)
    content = await bot.download_file(file.file_path)
    GLOBAL_DATA[uid] = {'doc_content': content.read(), 'filename': m.document.file_name, 'state': None}
    
    kb = []
    if "pdf" in m.document.mime_type:
        kb = [[InlineKeyboardButton(text="✂️ PDF Kesish", callback_data="pdf_split"), InlineKeyboardButton(text="📝 Wordga o'tkazish", callback_data="pdf_to_docx")]]
    else:
        kb = [[InlineKeyboardButton(text="📄 PDFga o'tkazish", callback_data="doc_to_pdf")]]
    await m.reply("📂 Fayl menyusi:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- CALLBACKS ---
@dp.callback_query(F.data)
async def callback_worker(call: types.CallbackQuery):
    uid = call.from_user.id
    action = call.data
    files = GLOBAL_DATA.get(uid, {}).get('files', [])

    if action == "clear":
        GLOBAL_DATA[uid] = {'files': []}
        await call.message.delete(); await call.message.answer("🗑 Tozalandi.", reply_markup=get_main_kb(uid)); return

    if action == "to_pdf":
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Original", callback_data="style_orig"), InlineKeyboardButton(text="Skaner", callback_data="style_scan")]])
        await call.message.edit_text("Uslubni tanlang:", reply_markup=kb); return

    if action == "to_docx":
        if not files: return
        msg = await call.message.edit_text("⏳ <b>Tayyorlanmoqda...</b>")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, images_to_docx, files)
        await call.message.answer_document(BufferedInputFile(docx, filename="hujjat.docx"))
        await msg.delete(); GLOBAL_DATA[uid]['files'] = []

    if action == "to_enhance":
        msg = await call.message.edit_text("⏳ <b>AI ishlamoqda...</b>")
        loop = asyncio.get_event_loop()
        for i, img in enumerate(files):
            if i % 2 == 0: await msg.edit_text(f"⏳ <b>Rasm {i+1}/{len(files)} tiniqlashtirilmoqda...</b>")
            res = await loop.run_in_executor(None, enhance_image, img)
            await call.message.answer_photo(BufferedInputFile(res, filename=f"hd_{i+1}.jpg"))
        await msg.delete(); GLOBAL_DATA[uid]['files'] = []

    # 🔴 OCR PRO (XATOLIK TUZATILGAN) 🔴
    if action == "to_ocr":
        if not files: return
        msg = await call.message.edit_text("⏳ <b>Matn o'qilmoqda (PRO OCR)...</b>")
        loop = asyncio.get_event_loop()
        
        # Pro OCR funksiyasini chaqiramiz
        text_result = await loop.run_in_executor(None, ocr_process_pro, files)
        
        # ⚠️ XAVFSIZLIK: < > & belgilarni html.escape() qilamiz
        safe_text = html.escape(text_result)
        
        if len(safe_text) > 4000:
            await call.message.answer_document(BufferedInputFile(text_result.encode(), filename="matn.txt"))
        else:
            # Safe textni jo'natamiz
            await call.message.answer(f"📝 <b>Natija:</b>\n\n<pre>{safe_text}</pre>")
            
        await msg.delete(); GLOBAL_DATA[uid]['files'] = []

    if action == "pdf_to_docx":
        msg = await call.message.edit_text("⏳ <b>Konvertatsiya ketmoqda...</b>")
        loop = asyncio.get_event_loop()
        docx_bytes = await loop.run_in_executor(None, convert_pdf_to_docx_safe, GLOBAL_DATA[uid]['doc_content'])
        if docx_bytes: await call.message.answer_document(BufferedInputFile(docx_bytes, filename="converted.docx"))
        else: await call.message.answer("❌ Xatolik.")
        await msg.delete()

    if action == "pdf_split":
        GLOBAL_DATA[uid]['state'] = "waiting_split"
        await call.message.answer("✂️ Qaysi betlarni kesamiz? (Masalan: 1-5)")

    if action.startswith("style_"):
        style = action.split("_")[1]
        if not files: return
        msg = await call.message.edit_text("⏳ <b>PDF yig'ilmoqda...</b>")
        loop = asyncio.get_event_loop()
        def make_pdf():
            proc = []
            for img in files:
                if style == "scan": proc.append(scan_effect(img))
                else: proc.append(img)
            return img2pdf.convert(proc)
        pdf = await loop.run_in_executor(None, make_pdf)
        await call.message.answer_document(BufferedInputFile(pdf, filename="scan.pdf"))
        await msg.delete(); GLOBAL_DATA[uid]['files'] = []

# --- 7. RUNNER ---
def run_bot_thread():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    new_loop.run_until_complete(starter())

if not any(t.name == "AiogramThread" for t in threading.enumerate()):
    threading.Thread(target=run_bot_thread, name="AiogramThread", daemon=True).start()

# --- 8. ADMIN PANEL (WEB) ---
st.markdown('<p class="header-text">🛡️ AI Studio Control Center</p>', unsafe_allow_html=True)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    st.header("🔐 Admin Kirish")
    parol = st.text_input("Parol", type="password")

if parol == ADMIN_PASS:
    st.success("Tizimga kirildi!")
    t1, t2, t3 = st.tabs(["📊 Statistika", "ℹ️ Info", "⚙️ Tizim"])
    with t1:
        c1, c2, c3 = st.columns(3)
        c1.metric("Threadlari", threading.active_count())
        c2.metric("Userlar", len(GLOBAL_DATA))
        c3.metric("Baza", "Online 🟢")
        st.line_chart(pd.DataFrame(np.random.randn(20, 2), columns=['PDF', 'OCR']))
    with t2:
        st.markdown(f'<div class="info-box">{INFO_TEXT}</div>', unsafe_allow_html=True)
    with t3:
        if st.button("🧹 Tozalash"): GLOBAL_DATA.clear(); st.success("Tozalandi!")
else:
    st.markdown("### 🤖 Universal AI Media Bot")
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg", use_column_width=True)
    col1, col2 = st.columns(2)
    with col1: st.info("💡 **Botni ishlatish:** Telegramga kiring, **/start** bosing.")
    with col2: st.warning("🔒 **Xavfsizlik:** Ma'lumotlar serverda saqlanmaydi.")
    
