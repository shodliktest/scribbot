import streamlit as st
import asyncio
import threading
import os
import io
import time
import sqlite3
import numpy as np
import cv2
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties

# --- 1. SOZLAMALAR VA XAVFSIZLIK ---
st.set_page_config(page_title="Admin Panel", layout="wide", page_icon="🛡")

try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = int(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ `.streamlit/secrets.toml` fayli noto'g'ri yoki mavjud emas!")
    st.stop()

DB_FILE = "bot_database.db"

# --- 2. BAZA BILAN ISHLASH (Admin Broadcast uchun) ---
def init_db():
    with sqlite3.connect(DB_FILE, check_same_thread=False) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)")

def add_user(user_id, username):
    with sqlite3.connect(DB_FILE, check_same_thread=False) as conn:
        conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (user_id, username))

def get_all_users():
    with sqlite3.connect(DB_FILE, check_same_thread=False) as conn:
        return [row[0] for row in conn.execute("SELECT user_id FROM users")]

# --- 3. TASVIRNI QAYTA ISHLASH (CORE) ---
def process_image_logic(img_bytes, action):
    # Baytlarni OpenCV formatiga o'tkazish
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if action == "enhance":
        # Sifatni oshirish
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        enhancer = ImageEnhance.Contrast(pil_img)
        pil_img = enhancer.enhance(1.5)
        sharp = ImageEnhance.Sharpness(pil_img)
        return "image", sharp.enhance(1.3)

    elif action == "ocr":
        # Matn o'qish (OCR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Shovqinni tozalash
        gray = cv2.medianBlur(gray, 3)
        text = pytesseract.image_to_string(gray, lang='uzb+eng+rus')
        return "text", text if text.strip() else "❌ Matnni aniqlab bo'lmadi."

    elif action == "pdf":
        # Hujjat Skaneri (Adaptive Threshold)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Hujjat effekti berish (oq-qora toza skan)
        scanned = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        pil_scanned = Image.fromarray(scanned)
        
        # PDF ga aylantirish uchun JPEG ga o'tkazish
        img_io = io.BytesIO()
        pil_scanned.save(img_io, format="JPEG", quality=90)
        pdf_bytes = img2pdf.convert(img_io.getvalue())
        
        pdf_io = io.BytesIO(pdf_bytes)
        return "pdf", pdf_io

    elif action == "sketch":
        # Style Transfer (Qalamda chizilgan effekt)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inv = 255 - gray
        blur = cv2.GaussianBlur(inv, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blur, scale=256)
        return "image", Image.fromarray(sketch)

    elif action == "cartoon":
        # Style Transfer (Multfilm effekti)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 9)
        color = cv2.bilateralFilter(img, 9, 250, 250)
        cartoon = cv2.bitwise_and(color, color, mask=edges)
        return "image", Image.fromarray(cv2.cvtColor(cartoon, cv2.COLOR_BGR2RGB))

# --- 4. TELEGRAM BOT (HANDLERS) ---
@st.cache_resource
def get_bot_instance():
    """Singleton Bot Instance"""
    return Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))

bot = get_bot_instance()
dp = Dispatcher()
init_db()

@dp.message(Command("start"))
async def start_cmd(m: types.Message):
    add_user(m.from_user.id, m.from_user.username)
    await m.answer(f"👋 Salom <b>{m.from_user.full_name}</b>!\n\n📸 Rasm yuboring, men uni professional darajada tahrirlab beraman.")

@dp.message(F.photo)
async def photo_processing(m: types.Message):
    # DEFENDER: 25MB Limit
    file_size = m.photo[-1].file_size
    if file_size > 25 * 1024 * 1024:
        await m.answer("❌ <b>Xatolik:</b> Fayl hajmi 25MB dan katta!")
        return

    # Menyular
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✨ Sifatni oshirish", callback_data="do_enhance"),
         InlineKeyboardButton(text="📝 OCR (Matn)", callback_data="do_ocr")],
        [InlineKeyboardButton(text="📄 PDF Skaner", callback_data="do_pdf"),
         InlineKeyboardButton(text="✏️ Sketch", callback_data="do_sketch")],
        [InlineKeyboardButton(text="🎨 Cartoon", callback_data="do_cartoon")]
    ])
    await m.reply("👇 Kerakli xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("do_"))
async def callback_worker(call: types.CallbackQuery):
    action = call.data.split("_")[1]
    msg = call.message
    photo = msg.reply_to_message.photo[-1]

    # Progress Bar Funksiyasi
    async def update_progress(text, percent):
        bar_len = 10
        filled = int(bar_len * percent / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        try:
            await status_msg.edit_text(f"{text}\n`[{bar}] {percent}%`", parse_mode="Markdown")
        except: pass

    status_msg = await msg.answer("⏳ <b>Ulanmoqda...</b>")
    
    try:
        # 1. Yuklab olish
        await update_progress("📥 Rasm yuklanmoqda...", 20)
        file_info = await bot.get_file(photo.file_id)
        downloaded = await bot.download_file(file_info.file_path)
        img_bytes = downloaded.read()

        # 2. Qayta ishlash
        await update_progress("⚙️ AI ishlamoqda...", 60)
        # CPU ishlashini bloklamaslik uchun Executor ishlatamiz
        loop = asyncio.get_event_loop()
        res_type, result = await loop.run_in_executor(None, process_image_logic, img_bytes, action)

        # 3. Yuborish
        await update_progress("📤 Natija yuklanmoqda...", 90)
        
        if res_type == "image":
            buf = io.BytesIO()
            result.save(buf, format="JPEG", quality=95)
            buf.seek(0)
            await msg.answer_photo(BufferedInputFile(buf.read(), filename="edit.jpg"), caption="✅ <b>Tayyor!</b>")
        
        elif res_type == "text":
            if len(result) > 4000:
                # Agar matn uzun bo'lsa fayl qilamiz
                buf = io.BytesIO(result.encode())
                await msg.answer_document(BufferedInputFile(buf.read(), filename="ocr_text.txt"), caption="✅ <b>Matn faylda!</b>")
            else:
                await msg.answer(f"📝 <b>Natija:</b>\n\n{result}")
        
        elif res_type == "pdf":
            result.seek(0)
            await msg.answer_document(BufferedInputFile(result.read(), filename="hujjat.pdf"), caption="✅ <b>Professional Scan (PDF)</b>")

        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Xatolik:</b> {str(e)}")

# --- 5. BACKGROUND THREAD MANAGER (Killer Webhook) ---
def run_bot_in_background():
    """Botni alohida oqimda, xavfsiz ishga tushirish"""
    async def runner():
        # Webhookni o'ldirish (Pending update'larni tozalash)
        await bot.delete_webhook(drop_pending_updates=True)
        try:
            await dp.start_polling(bot)
        except Exception as e:
            print(f"Bot Polling Error: {e}")

    # Yangi Loop yaratish (Streamlit Loop bilan konflikt bo'lmasligi uchun)
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)
    new_loop.run_until_complete(runner())

# Singleton Thread Check
if "bot_active" not in st.session_state:
    thread_exists = False
    for t in threading.enumerate():
        if t.name == "SecureBotThread":
            thread_exists = True
            break
    
    if not thread_exists:
        t = threading.Thread(target=run_bot_in_background, name="SecureBotThread", daemon=True)
        t.start()
    st.session_state.bot_active = True

# --- 6. ADMIN PANEL (STREAMLIT UI) ---
st.sidebar.title("🔐 Admin Login")
password = st.sidebar.text_input("Parol", type="password")

if password == ADMIN_PASS:
    st.title("🎛 Admin Boshqaruv Paneli")
    
    # Statistika
    users = get_all_users()
    col1, col2, col3 = st.columns(3)
    col1.metric("Jami Foydalanuvchilar", len(users))
    col2.metric("Bot Holati", "🟢 Aktiv")
    col3.metric("Server Threadlar", threading.active_count())
    
    st.divider()
    
    # Saytga kirish tugmasi (Simulyatsiya)
    st.markdown("### 🌐 Sayt boshqaruvi")
    if st.button("🔗 Admin Panelni Yangilash (Refresh Site)"):
        st.rerun()

    # Broadcast (Xabar tarqatish)
    st.markdown("### 📢 Xabar Tarqatish")
    msg_text = st.text_area("Xabar matnini kiriting:", height=100)
    
    if st.button("🚀 Hammaga Yuborish"):
        if not msg_text:
            st.warning("Matn yozilmadi!")
        else:
            progress = st.progress(0)
            status_txt = st.empty()
            
            # Asinxron yuborish funksiyasi
            async def send_broadcast():
                count = 0
                for i, uid in enumerate(users):
                    try:
                        await bot.send_message(uid, msg_text)
                        count += 1
                    except: pass
                    # Progress barni yangilash
                    percent = int((i + 1) / len(users) * 100)
                    progress.progress(percent)
                    status_txt.text(f"Yuborilmoqda: {i+1}/{len(users)}")
                return count

            # Streamlit ichida async ishlatish
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            sent_count = loop.run_until_complete(send_broadcast())
            
            st.success(f"✅ Xabar {sent_count} kishiga yuborildi!")

else:
    st.title("🤖 AI Bot Server")
    st.info("Bot orqa fonda ishlamoqda. Admin panelga kirish uchun parolni kiriting.")
    
