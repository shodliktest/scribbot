import streamlit as st
import asyncio
import threading
import os
import io
import time
import sqlite3
import pytz
import pandas as pd
import numpy as np
import cv2
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# --- 1. SOZLAMALAR ---
st.set_page_config(page_title="AI Studio Admin", layout="wide", page_icon="🛡")

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ Secrets sozlanmagan! Streamlit Cloud -> Settings -> Secrets qismini tekshiring.")
    st.stop()

DB_FILE = "bot_data.db"
uz_tz = pytz.timezone('Asia/Tashkent')

# --- 2. BAZA (SQLite) ---
@st.cache_resource
def get_db_conn():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_db_conn()
    conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, join_date TEXT)")
    conn.commit()

def add_user(uid, uname):
    conn = get_db_conn()
    now = datetime.now(uz_tz).strftime("%Y-%m-%d %H:%M")
    conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (uid, uname, now))
    conn.commit()

# --- 3. CORE LOGIC (Rasmga ishlov berish) ---
def process_media(img_bytes, action):
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if action == "enhance":
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        enhancer = ImageEnhance.Contrast(pil_img)
        return "image", enhancer.enhance(1.5)

    elif action == "ocr":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray, lang='uzb+rus+eng')
        return "text", text if text.strip() else "❌ Matn topilmadi."

    elif action == "pdf":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        scanned = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        pil_scanned = Image.fromarray(scanned)
        img_io = io.BytesIO()
        pil_scanned.save(img_io, format="JPEG")
        pdf_data = img2pdf.convert(img_io.getvalue())
        return "pdf", io.BytesIO(pdf_data)

    elif action == "sketch":
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inv = 255 - gray
        blur = cv2.GaussianBlur(inv, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blur, scale=256)
        return "image", Image.fromarray(sketch)

# --- 4. TELEGRAM BOT (Asosiy Protsess) ---
@st.cache_resource
def get_bot():
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot()
dp = Dispatcher()
init_db()

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    add_user(m.from_user.id, m.from_user.username)
    await m.answer(f"👋 Salom <b>{m.from_user.full_name}</b>!\nRasm yuboring, men uni professional tahrirlayman.")

@dp.message(F.photo)
async def handle_photo(m: types.Message):
    if m.photo[-1].file_size > 25 * 1024 * 1024:
        await m.answer("❌ Fayl 25MB dan katta!")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Enhance", callback_data="do_enhance"), InlineKeyboardButton(text="📝 OCR", callback_data="do_ocr")],
        [InlineKeyboardButton(text="📄 PDF Scan", callback_data="do_pdf"), InlineKeyboardButton(text="🎨 Sketch", callback_data="do_sketch")]
    ])
    await m.reply("Tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("do_"))
async def callback_handler(call: types.CallbackQuery):
    action = call.data.split("_")[1]
    msg = call.message
    status = await msg.answer("⏳ Bajarilmoqda... `[░░░░░░░░░░] 0%`", parse_mode="Markdown")
    
    try:
        file = await bot.get_file(msg.reply_to_message.photo[-1].file_id)
        down = await bot.download_file(file.file_path)
        img_bytes = down.read()
        
        await status.edit_text("⚙️ AI ishlamoqda... `[██████░░░░] 60%`", parse_mode="Markdown")
        
        loop = asyncio.get_event_loop()
        res_type, res = await loop.run_in_executor(None, process_media, img_bytes, action)
        
        await status.edit_text("📤 Yuborilmoqda... `[██████████] 100%`", parse_mode="Markdown")

        if res_type == "image":
            buf = io.BytesIO()
            res.save(buf, format="JPEG")
            await msg.answer_photo(BufferedInputFile(buf.getvalue(), filename="res.jpg"))
        elif res_type == "text":
            await msg.answer(f"📝 <b>Natija:</b>\n\n<code>{res}</code>")
        elif res_type == "pdf":
            await msg.answer_document(BufferedInputFile(res.read(), filename="scan.pdf"))
        
        await status.delete()
    except Exception as e:
        await status.edit_text(f"❌ Xato: {str(e)}")

# --- 5. SINGLETON RUNNER (Qotib qolmaslik himoyasi) ---
def run_bot():
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    async def start():
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, handle_signals=False)
    new_loop.run_until_complete(start())

if "bot_online" not in st.session_state:
    if not any(t.name == "BotThread" for t in threading.enumerate()):
        threading.Thread(target=run_bot, name="BotThread", daemon=True).start()
    st.session_state.bot_online = True

# --- 6. ADMIN PANEL (WEB) ---
st.title("🔐 AI Studio Admin Panel")
conn = get_db_conn()
df = pd.read_sql_query("SELECT * FROM users", conn)

st.metric("Jami foydalanuvchilar", len(df))
tab1, tab2 = st.tabs(["📢 Broadcast", "📋 Foydalanuvchilar"])

with tab1:
    auth = st.text_input("Parol:", type="password")
    if auth == ADMIN_PASS:
        txt = st.text_area("Xabar:")
        if st.button("🚀 Hammaga yuborish"):
            stats = {"s": 0, "f": 0}
            async def do_bc():
                temp_bot = Bot(token=BOT_TOKEN)
                for uid in df['user_id']:
                    try: 
                        await temp_bot.send_message(uid, txt)
                        stats["s"] += 1
                    except: stats["f"] += 1
                await temp_bot.session.close()
            asyncio.run(do_bc())
            st.success(f"Yuborildi: {stats['s']}, Xato: {stats['f']}")
    else: st.warning("Parol kiritilmadi.")

with tab2:
    st.dataframe(df, use_container_width=True)
