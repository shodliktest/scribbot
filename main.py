import streamlit as st
import asyncio
import threading
import io
import os
import re
import cv2
import numpy as np
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader, PdfWriter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from datetime import datetime
import pandas as pd

# --- 1. GLOBAL XOTIRA ---
if "GLOBAL_DATA" not in globals():
    GLOBAL_DATA = {} 
    # {user_id: {'files': [], 'state': None, 'doc_content': None}}

# --- 2. DIZAYN VA SOZLAMALAR ---
st.set_page_config(page_title="AI Studio Pro", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; }
    .info-box { background: #0d1117; border-left: 5px solid #58a6ff; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ Secrets fayli sozlanmagan!")
    st.stop()

# --- 3. AI FUKSIYALAR ---
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

# --- 4. BOT SETUP (AIOGRAM) ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 5. MENYU (KEYBOARDS) ---
def get_main_kb(user_id):
    """Doimiy pastki menyu"""
    kb = [
        [KeyboardButton(text="ℹ️ Info"), KeyboardButton(text="👨‍💻 Adminga murojaat")]
    ]
    if str(user_id) == ADMIN_ID:
        kb.append([KeyboardButton(text="💎 Admin Panel")])
    
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

INFO_TEXT = """
<b>ℹ️ BOT QO'LLANMASI:</b>

📸 <b>Rasm yuborsangiz:</b>
• PDF Skaner (Oq-qora)
• Word (DOCX) ga joylash
• AI Tiniqlashtirish

📄 <b>PDF yuborsangiz:</b>
• Sahifalarni kesish (Split)
• Word yoki Matnga o'tkazish

<i>Boshlash uchun fayl yuboring!</i>
"""

# --- 6. HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    uid = m.from_user.id
    GLOBAL_DATA[uid] = {'files': [], 'state': None}
    
    await m.answer(
        f"👋 <b>Salom {m.from_user.first_name}!</b>\n\nMen tayyorman. Fayl yuboring yoki quyidagi menyudan foydalaning.",
        reply_markup=get_main_kb(uid)
    )

# --- TEXT ROUTER (Admin Reply & Menu) ---
@dp.message(F.text)
async def text_router(m: types.Message):
    uid = m.from_user.id
    text = m.text
    state = GLOBAL_DATA.get(uid, {}).get('state')

    # 1. ADMIN REPLY LOGIC
    if str(uid) == ADMIN_ID and m.reply_to_message:
        # Admin reply qilgan xabarni tekshiramiz
        replied_text = m.reply_to_message.text or m.reply_to_message.caption or ""
        
        # ID ni topish (#ID12345)
        match = re.search(r"#ID(\d+)", replied_text)
        if match:
            target_id = match.group(1)
            try:
                await bot.send_message(target_id, f"👨‍💻 <b>Admin javobi:</b>\n\n{text}")
                await m.answer(f"✅ Javob {target_id} ga yuborildi.")
            except:
                await m.answer("❌ Xatolik: Foydalanuvchi botni bloklagan.")
        else:
            await m.answer("❌ ID topilmadi. #ID bor xabarga reply qiling.")
        return

    # 2. PDF SPLIT INPUT
    if state == "waiting_split":
        try:
            start, end = map(int, text.split("-"))
            pdf_content = GLOBAL_DATA[uid]['doc_content']
            
            # Asinxron ishlash uchun Executor
            loop = asyncio.get_event_loop()
            def split_pdf_sync():
                reader = PdfReader(io.BytesIO(pdf_content))
                writer = PdfWriter()
                for i in range(start-1, min(end, len(reader.pages))):
                    writer.add_page(reader.pages[i])
                out = io.BytesIO()
                writer.write(out)
                return out.getvalue()

            pdf_out = await loop.run_in_executor(None, split_pdf_sync)
            await m.answer_document(BufferedInputFile(pdf_out, filename="kesilgan.pdf"), caption="✅ PDF kesildi.")
        except:
            await m.answer("❌ Xato format! Misol: 1-5")
        GLOBAL_DATA[uid]['state'] = None
        return

    # 3. USER CONTACT MESSAGE
    if state == "waiting_contact":
        msg_to_admin = (
            f"📩 <b>YANGI MUROJAAT!</b>\n"
            f"👤: {m.from_user.full_name}\n"
            f"🆔: #ID{uid}\n"
            f"username: @{m.from_user.username}\n\n"
            f"📝: {text}"
        )
        await bot.send_message(ADMIN_ID, msg_to_admin)
        await m.answer("✅ Xabaringiz adminga yuborildi.", reply_markup=get_main_kb(uid))
        GLOBAL_DATA[uid]['state'] = None
        return

    # 4. MENU BUTTONS
    if text == "ℹ️ Info":
        await m.answer(INFO_TEXT)
    
    elif text == "👨‍💻 Adminga murojaat":
        GLOBAL_DATA[uid] = GLOBAL_DATA.get(uid, {})
        GLOBAL_DATA[uid]['state'] = "waiting_contact"
        await m.answer("📝 <b>Murojaatingizni yozing:</b>\n(Matn yozing)", reply_markup=types.ReplyKeyboardRemove())
    
    elif text == "💎 Admin Panel" and str(uid) == ADMIN_ID:
        await m.answer("🖥 Admin panel Web versiyada ochiq.")

# --- FILE HANDLERS ---

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    uid = m.from_user.id
    
    # Murojaat payti rasm yuborsa adminga o'tkazish
    if GLOBAL_DATA.get(uid, {}).get('state') == "waiting_contact":
        await bot.send_message(ADMIN_ID, f"📩 <b>Rasm keldi</b> (#ID{uid}):")
        await m.send_copy(ADMIN_ID)
        await m.answer("✅ Rasm adminga ketdi.", reply_markup=get_main_kb(uid))
        GLOBAL_DATA[uid]['state'] = None
        return

    if uid not in GLOBAL_DATA: GLOBAL_DATA[uid] = {'files': []}
    
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    GLOBAL_DATA[uid]['files'].append(content.read())
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF qilish", callback_data="to_pdf"),
         InlineKeyboardButton(text="📝 Word (DOCX)", callback_data="to_docx")],
        [InlineKeyboardButton(text="✨ AI Tiniqlash", callback_data="to_enhance"),
         InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    
    await m.reply(f"✅ Rasm qabul qilindi ({len(GLOBAL_DATA[uid]['files'])} ta).", reply_markup=kb)

@dp.message(F.document)
async def handle_docs(m: types.Message):
    uid = m.from_user.id
    
    # Murojaat payti fayl yuborsa
    if GLOBAL_DATA.get(uid, {}).get('state') == "waiting_contact":
        await bot.send_message(ADMIN_ID, f"📩 <b>Fayl keldi</b> (#ID{uid}):")
        await m.send_copy(ADMIN_ID)
        await m.answer("✅ Fayl adminga ketdi.", reply_markup=get_main_kb(uid))
        GLOBAL_DATA[uid]['state'] = None
        return

    file = await bot.get_file(m.document.file_id)
    content = await bot.download_file(file.file_path)
    GLOBAL_DATA[uid] = {'doc_content': content.read(), 'filename': m.document.file_name, 'state': None}
    
    kb = []
    if "pdf" in m.document.mime_type:
        kb = [
            [InlineKeyboardButton(text="✂️ PDF Kesish", callback_data="pdf_split")],
            [InlineKeyboardButton(text="📝 Wordga o'tkazish", callback_data="pdf_to_docx")]
        ]
    else:
        kb = [[InlineKeyboardButton(text="📄 PDFga o'tkazish", callback_data="doc_to_pdf")]]
        
    await m.reply("📂 Fayl qabul qilindi:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# --- CALLBACKS ---
@dp.callback_query(F.data)
async def callback_worker(call: types.CallbackQuery):
    uid = call.from_user.id
    action = call.data
    
    if action == "clear":
        GLOBAL_DATA[uid] = {'files': []}
        await call.message.delete()
        await call.message.answer("🗑 Tozalandi.", reply_markup=get_main_kb(uid))
        return

    if action == "to_pdf":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Original", callback_data="style_orig"),
             InlineKeyboardButton(text="Skaner", callback_data="style_scan")]
        ])
        await call.message.edit_text("Uslubni tanlang:", reply_markup=kb)
        return

    if action == "to_docx":
        if not GLOBAL_DATA.get(uid, {}).get('files'): return
        await call.message.edit_text("⏳ Word tayyorlanmoqda...")
        loop = asyncio.get_event_loop()
        docx = await loop.run_in_executor(None, images_to_docx, GLOBAL_DATA[uid]['files'])
        await call.message.answer_document(BufferedInputFile(docx, filename="hujjat.docx"))
        GLOBAL_DATA[uid]['files'] = []

    if action == "to_enhance":
        await call.message.edit_text("⏳ Tiniqlashtirilmoqda...")
        loop = asyncio.get_event_loop()
        for img in GLOBAL_DATA[uid]['files']:
            res = await loop.run_in_executor(None, enhance_image, img)
            await call.message.answer_photo(BufferedInputFile(res, filename="hd.jpg"))
        GLOBAL_DATA[uid]['files'] = []

    if action == "pdf_split":
        GLOBAL_DATA[uid]['state'] = "waiting_split"
        await call.message.answer("✂️ Qaysi betlarni kesamiz? (Masalan: 1-5)")

    if action.startswith("style_"):
        style = action.split("_")[1]
        files = GLOBAL_DATA.get(uid, {}).get('files')
        if not files: return
        
        await call.message.edit_text("⏳ PDF yasalmoqda...")
        loop = asyncio.get_event_loop()
        
        def make_pdf_sync():
            proc = []
            for img in files:
                if style == "scan": proc.append(scan_effect(img))
                else: proc.append(img)
            return img2pdf.convert(proc)

        pdf_bytes = await loop.run_in_executor(None, make_pdf_sync)
        await call.message.answer_document(BufferedInputFile(pdf_bytes, filename="scan.pdf"))
        GLOBAL_DATA[uid]['files'] = []

# --- 7. BACKGROUND RUNNER ---
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
st.title("🛡️ AI Admin Control")
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    st.header("Kirish")
    parol = st.text_input("Parol", type="password")

if parol == ADMIN_PASS:
    st.success("Admin Panel")
    t1, t2 = st.tabs(["Statistika", "Info Matni"])
    with t1:
        st.metric("Userlar (RAM)", len(GLOBAL_DATA))
        st.metric("Threadlar", threading.active_count())
    with t2:
        st.code(INFO_TEXT)
else:
    # --- FOYDALANUVCHI INTERFEYSI (LOGINSIZ) ---
    st.markdown("### 🤖 Universal AI Media Bot")
    st.image("https://img.freepik.com/free-vector/abstract-technology-particle-background_23-2148426649.jpg", use_column_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("💡 **Bot ishlashi:** Telegramga kiring, **/start** bosing va rasm yuboring.")
    with col2:
        st.warning("🔒 **Xavfsizlik:** Tizim himoyalangan va shaxsiy ma'lumotlar saqlanmaydi.")
    
