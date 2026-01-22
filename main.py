import streamlit as st
import asyncio
import threading
import io
import time
import random
import numpy as np
import cv2
import img2pdf
import pytesseract
from docx import Document
from docx.shared import Inches
from pdf2docx import Converter
from PIL import Image, ImageEnhance, ImageFilter
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# --- 1. SOZLAMALAR ---
st.set_page_config(page_title="Universal AI Studio Admin", layout="wide")

# Global Xotira
USER_DATA = {} # {uid: {'files': [], 'mode': 'waiting'}}

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except Exception as e:
    st.error(f"Secrets sozlanmagan: {e}")
    st.stop()

# --- 2. CORE PROCESSING LOGIC ---

def process_media_action(image_list, action):
    """Barcha amallarni bajaruvchi asosiy funksiya"""
    
    # 1. Sifatni oshirish (Enhance)
    if action == "enhance":
        processed = []
        for img_b in image_list:
            pil_img = Image.open(io.BytesIO(img_b)).convert("RGB")
            pil_img = ImageEnhance.Contrast(pil_img).enhance(1.4)
            pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.6)
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG", quality=95)
            processed.append(buf.getvalue())
        return "images", processed

    # 2. Matnni o'qish (OCR)
    elif action == "ocr":
        full_text = ""
        for i, img_b in enumerate(image_list):
            pil_img = Image.open(io.BytesIO(img_b))
            text = pytesseract.image_to_string(pil_img, lang='uzb+rus+eng')
            full_text += f"\n--- {i+1}-sahifa ---\n{text}\n"
        return "text", full_text

    # 3. PDF Skaner (Oqartirish)
    elif action == "pdf":
        scanned_bytes = []
        for img_b in image_list:
            nparr = np.frombuffer(img_b, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # Skaner effekti
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            _, buffer = cv2.imencode(".jpg", thresh)
            scanned_bytes.append(buffer.tobytes())
        pdf_data = img2pdf.convert(scanned_bytes)
        return "file", (pdf_data, "document.pdf")

    # 4. Word (DOCX) yaratish
    elif action == "docx":
        doc = Document()
        for img_b in image_list:
            img_stream = io.BytesIO(img_b)
            doc.add_picture(img_stream, width=Inches(6))
            doc.add_page_break()
        doc_buf = io.BytesIO()
        doc.save(doc_buf)
        return "file", (doc_buf.getvalue(), "converted_doc.docx")

    # 5. Tasodifiy filtrlar (Random Filters)
    elif action == "filter":
        processed = []
        filters = [ImageFilter.BLUR, ImageFilter.CONTOUR, ImageFilter.DETAIL, ImageFilter.EDGE_ENHANCE, ImageFilter.EMBOSS]
        for img_b in image_list:
            pil_img = Image.open(io.BytesIO(img_b)).convert("RGB")
            pil_img = pil_img.filter(random.choice(filters))
            buf = io.BytesIO()
            pil_img.save(buf, format="JPEG")
            processed.append(buf.getvalue())
        return "images", processed

# --- 3. BOT INITIALIZATION ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()

# --- 4. BOT HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    USER_DATA[m.from_user.id] = []
    await m.answer(f"👋 Salom <b>{m.from_user.full_name}</b>!\nRasm yuboring, men ularni tahrirlayman yoki PDF/DOCX qilaman.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    uid = m.from_user.id
    if uid not in USER_DATA: USER_DATA[uid] = []
    
    if len(USER_DATA[uid]) >= 25:
        await m.answer("⚠️ Limit: Maksimal 25 ta rasm.")
        return

    # Faylni yuklab olish
    file = await bot.get_file(m.photo[-1].file_id)
    content = await bot.download_file(file.file_path)
    USER_DATA[uid].append(content.read())
    
    count = len(USER_DATA[uid])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🚀 Bajarish ({count})", callback_data="menu_main")],
        [InlineKeyboardButton(text="🗑 Tozalash", callback_data="clear")]
    ])
    await m.answer(f"✅ {count}-rasm qabul qilindi.", reply_markup=kb)

# PDF faylni qabul qilish (DOCX ga o'girish uchun)
@dp.message(F.document)
async def handle_doc(m: types.Message):
    if m.document.mime_type == "application/pdf":
        status = await m.answer("⏳ PDF qabul qilindi. DOCX ga o'girilmoqda...")
        file = await bot.get_file(m.document.file_id)
        content = await bot.download_file(file.file_path)
        
        # Faylni diskka vaqtincha saqlash (pdf2docx diskdan ishlashni talab qiladi)
        with open("temp.pdf", "wb") as f: f.write(content.read())
        
        try:
            cv = Converter("temp.pdf")
            cv.convert("temp.docx", start=0, end=None)
            cv.close()
            
            await m.answer_document(FSInputFile("temp.docx"), caption="✅ PDF muvaffaqiyatli Wordga o'girildi!")
            os.remove("temp.pdf")
            os.remove("temp.docx")
        except Exception as e:
            await m.answer(f"❌ Xatolik: {e}")
        await status.delete()

@dp.callback_query(F.data == "menu_main")
async def main_menu(call: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 PDF (Skaner)", callback_data="act_pdf"),
         InlineKeyboardButton(text="📝 Word (DOCX)", callback_data="act_docx")],
        [InlineKeyboardButton(text="✨ Enhance (Tiniq)", callback_data="act_enhance"),
         InlineKeyboardButton(text="🔍 OCR (Matn)", callback_data="act_ocr")],
        [InlineKeyboardButton(text="🎨 Random Filter", callback_data="act_filter")]
    ])
    await call.message.edit_text("Tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("act_"))
async def final_action(call: types.CallbackQuery):
    action = call.data.split("_")[1]
    uid = call.from_user.id
    
    if uid not in USER_DATA or not USER_DATA[uid]:
        await call.answer("Rasmlar topilmadi!", show_alert=True)
        return

    msg = await call.message.edit_text(f"⏳ {len(USER_DATA[uid])} ta fayl ishlanmoqda...")
    
    try:
        loop = asyncio.get_event_loop()
        res_type, result = await loop.run_in_executor(None, process_media_action, USER_DATA[uid], action)
        
        if res_type == "images":
            for img in result:
                await call.message.answer_photo(BufferedInputFile(img, filename="res.jpg"))
        elif res_type == "text":
            if len(result) > 4000:
                await call.message.answer_document(BufferedInputFile(result.encode(), filename="text.txt"))
            else:
                await call.message.answer(f"📝 <b>Natija:</b>\n\n<code>{result}</code>")
        elif res_type == "file":
            data, name = result
            await call.message.answer_document(BufferedInputFile(data, filename=name))
        
        USER_DATA[uid] = [] # Keshni tozalash
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {e}")

@dp.callback_query(F.data == "clear")
async def clear_cache(call: types.CallbackQuery):
    USER_DATA[call.from_user.id] = []
    await call.message.edit_text("🗑 Tozalandi.")

# --- 5. SINGLETON THREAD MANAGER ---
def run_bot():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def starter():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    new_loop.run_until_complete(starter())

if not any(t.name == "MainBotThread" for t in threading.enumerate()):
    threading.Thread(target=run_bot, name="MainBotThread", daemon=True).start()

# --- 6. ADMIN PANEL (WEB) ---
st.title("🛡 AI Studio Admin Panel")
st.metric("Aktiv Threadlar", threading.active_count())
st.info("Bot Telegramda online. Foydalanuvchilar soni (RAM): " + str(len(USER_DATA)))
    
