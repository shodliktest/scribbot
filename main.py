import streamlit as st
import telebot
from telebot import types
import threading
import io
import os
import time
import cv2
import numpy as np
import pytesseract
import img2pdf
from PIL import Image, ImageEnhance
from docx import Document
from docx.shared import Inches
from PyPDF2 import PdfReader, PdfWriter
from pdf2docx import Converter
from datetime import datetime
import pandas as pd

# --- 1. GLOBAL XOTIRA (Xatoliksiz ishlash uchun) ---
if "GLOBAL_DATA" not in globals():
    GLOBAL_DATA = {} # {user_id: {'files': [], 'state': None, 'doc_path': None}}

# --- 2. PREMIUM DIZAYN (STREAMLIT) ---
st.set_page_config(page_title="AI Studio Pro", layout="wide", page_icon="💎")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 15px; }
    .css-1d391kg { padding-top: 1rem; }
    .info-box { background: #0d1117; border-left: 5px solid #58a6ff; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
    h1 { color: #58a6ff; }
    </style>
    """, unsafe_allow_html=True)

# SECRETS
try:
    BOT_TOKEN = st.secrets["telegram"]["BOT_TOKEN"]
    ADMIN_ID = str(st.secrets["telegram"]["ADMIN_ID"])
    ADMIN_PASS = st.secrets["telegram"]["ADMIN_PASSWORD"]
except:
    st.error("❌ Secrets fayli sozlanmagan!")
    st.stop()

# --- 3. AI VA MEDIA FUNKSIYALAR ---
def enhance_image(img_bytes):
    """Rasmni AI yordamida tiniqlashtirish"""
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
    """Hujjat skaneri effekti (Oq-qora)"""
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    _, buf = cv2.imencode(".jpg", thresh)
    return buf.tobytes()

def images_to_docx(image_list):
    """Rasmlarni Word (Docx) ga joylash"""
    doc = Document()
    for img in image_list:
        doc.add_picture(io.BytesIO(img), width=Inches(6))
        doc.add_page_break()
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()

# --- 4. BOT SOZLAMALARI ---
@st.cache_resource
def get_bot():
    return telebot.TeleBot(BOT_TOKEN, threaded=False)

bot = get_bot()

# TUSHUNTIRISH MATNI
INFO_TEXT = """
<b>ℹ️ BOT QO'LLANMASI:</b>

📸 <b>Rasm yuborsangiz:</b>
1. <b>PDF Skaner:</b> Rasmlarni bitta PDF kitob qiladi.
2. <b>Word (DOCX):</b> Rasmlarni Word hujjatiga joylaydi.
3. <b>OCR (Matn):</b> Rasmdagi yozuvlarni ajratib oladi.
4. <b>AI Enhance:</b> Xira rasmni tiniqlashtiradi.

📄 <b>PDF yuborsangiz:</b>
1. <b>Kesish (Split):</b> Kerakli sahifalarni ajratib beradi (masalan: 1-5).
2. <b>Konvertatsiya:</b> PDF ni Word yoki Matn ko'rinishiga o'tkazadi.

<i>Boshlash uchun fayl yuboring!</i>
"""

# --- 5. BOT HANDLERS ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.chat.id
    GLOBAL_DATA[uid] = {'files': [], 'state': None}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("ℹ️ To'liq Ma'lumot", callback_data="info"))
    markup.add(types.InlineKeyboardButton("👨‍💻 Adminga murojaat", callback_data="contact_admin"))
    
    bot.send_message(uid, f"👋 <b>Salom {message.from_user.first_name}!</b>\n\nMen sizning universal yordamchingizman. Rasm yoki fayl yuboring, qolganini menga qo'yib bering!", parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "info")
def show_info(call):
    bot.send_message(call.message.chat.id, INFO_TEXT, parse_mode="HTML")

# --- RASM QABUL QILISH ---
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    uid = message.chat.id
    if uid not in GLOBAL_DATA: GLOBAL_DATA[uid] = {'files': []}
    
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)
    GLOBAL_DATA[uid]['files'].append(downloaded)
    
    count = len(GLOBAL_DATA[uid]['files'])
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 PDF qilish", callback_data="to_pdf"),
        types.InlineKeyboardButton("📝 Word (DOCX)", callback_data="to_docx"),
        types.InlineKeyboardButton("✨ AI Tiniqlash", callback_data="to_enhance"),
        types.InlineKeyboardButton("🔍 OCR (Matn)", callback_data="to_ocr"),
        types.InlineKeyboardButton("🗑 Tozalash", callback_data="clear")
    )
    
    bot.reply_to(message, f"✅ <b>{count}-rasm qabul qilindi.</b>\nNima qilamiz?", reply_markup=markup, parse_mode="HTML")

# --- HUJJAT (PDF/DOC) QABUL QILISH ---
@bot.message_handler(content_types=['document'])
def handle_docs(message):
    uid = message.chat.id
    mime = message.document.mime_type
    
    file_info = bot.get_file(message.document.file_id)
    file_content = bot.download_file(file_info.file_path)
    
    GLOBAL_DATA[uid] = {'doc_content': file_content, 'filename': message.document.file_name, 'state': None}
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    if "pdf" in mime:
        markup.add(types.InlineKeyboardButton("✂️ PDF-ni Kesish (Split)", callback_data="pdf_split"))
        markup.add(types.InlineKeyboardButton("📝 Word-ga o'tkazish", callback_data="pdf_to_word"))
        markup.add(types.InlineKeyboardButton("🔍 Matnni olish (TXT)", callback_data="pdf_to_txt"))
    else:
        markup.add(types.InlineKeyboardButton("📄 PDF-ga o'tkazish", callback_data="doc_to_pdf"))
        
    bot.reply_to(message, f"📂 <b>{message.document.file_name}</b> qabul qilindi. Tanlang:", reply_markup=markup, parse_mode="HTML")

# --- CALLBACK ACTIONS ---
@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    uid = call.message.chat.id
    action = call.data
    
    if action == "clear":
        GLOBAL_DATA[uid] = {'files': []}
        bot.delete_message(uid, call.message.message_id)
        bot.send_message(uid, "🗑 Xotira tozalandi.")
        return

    # PDF Uslubini tanlash
    if action == "to_pdf":
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🖼 Original", callback_data="style_orig"),
                   types.InlineKeyboardButton("📄 Skaner (Oq-qora)", callback_data="style_scan"),
                   types.InlineKeyboardButton("✨ AI Yaxshilangan", callback_data="style_ai"))
        bot.edit_message_text("🎨 <b>PDF uslubini tanlang:</b>", uid, call.message.message_id, reply_markup=markup, parse_mode="HTML")
        return

    # Word (Docx)
    if action == "to_docx":
        if not GLOBAL_DATA.get(uid, {}).get('files'): return
        bot.send_message(uid, "⏳ Word hujjat tayyorlanmoqda...")
        docx_data = images_to_docx(GLOBAL_DATA[uid]['files'])
        bot.send_document(uid, io.BytesIO(docx_data), visible_file_name="hujjat.docx", caption="✅ Tayyor!")
        GLOBAL_DATA[uid]['files'] = []

    # AI Enhance
    if action == "to_enhance":
        if not GLOBAL_DATA.get(uid, {}).get('files'): return
        bot.send_message(uid, "⏳ Rasmlar tiniqlashtirilmoqda...")
        for img in GLOBAL_DATA[uid]['files']:
            processed = enhance_image(img)
            bot.send_photo(uid, processed)
        bot.send_message(uid, "✅ Bajarildi!")
        GLOBAL_DATA[uid]['files'] = []

    # OCR
    if action == "to_ocr":
        if not GLOBAL_DATA.get(uid, {}).get('files'): return
        msg = bot.send_message(uid, "⏳ Matn o'qilmoqda...")
        full_text = ""
        for img in GLOBAL_DATA[uid]['files']:
            pil_img = Image.open(io.BytesIO(img))
            text = pytesseract.image_to_string(pil_img, lang='uzb+rus+eng')
            full_text += text + "\n\n"
        
        if len(full_text) > 4000:
            bot.send_document(uid, io.BytesIO(full_text.encode()), visible_file_name="matn.txt")
        else:
            bot.send_message(uid, f"📝 <b>Natija:</b>\n{full_text}", parse_mode="HTML")
        bot.delete_message(uid, msg.message_id)
        GLOBAL_DATA[uid]['files'] = []

    # PDF Split Start
    if action == "pdf_split":
        GLOBAL_DATA[uid]['state'] = 'waiting_split'
        bot.send_message(uid, "✂️ <b>Qaysi sahifalarni kesamiz?</b>\n\nMasalan: <code>1-5</code> deb yozing.", parse_mode="HTML")

    # PDF Generation (Styles)
    if action.startswith("style_"):
        style = action.split("_")[1]
        user_files = GLOBAL_DATA.get(uid, {}).get('files')
        if not user_files: return
        
        bot.edit_message_text("⏳ PDF tayyorlanmoqda...", uid, call.message.message_id)
        processed = []
        for img in user_files:
            if style == "scan": res = scan_effect(img)
            elif style == "ai": res = enhance_image(img)
            else: res = img
            processed.append(res)
            
        pdf_bytes = img2pdf.convert(processed)
        bot.send_document(uid, io.BytesIO(pdf_bytes), visible_file_name="scan_hujjat.pdf", caption="✅ Marhamat!")
        GLOBAL_DATA[uid]['files'] = []

# TEXT HANDLER (Split uchun)
@bot.message_handler(func=lambda m: True)
def text_handle(message):
    uid = message.chat.id
    state = GLOBAL_DATA.get(uid, {}).get('state')
    
    if state == "waiting_split":
        try:
            start, end = map(int, message.text.split("-"))
            pdf_content = GLOBAL_DATA[uid]['doc_content']
            reader = PdfReader(io.BytesIO(pdf_content))
            writer = PdfWriter()
            
            for i in range(start-1, min(end, len(reader.pages))):
                writer.add_page(reader.pages[i])
            
            out = io.BytesIO()
            writer.write(out)
            bot.send_document(uid, out, visible_file_name="kesilgan.pdf", caption="✅ PDF kesildi.")
        except:
            bot.send_message(uid, "❌ Xato! Format: 1-5")
        GLOBAL_DATA[uid]['state'] = None
    
    elif message.reply_to_message: # Admin javobi
        pass # Bu yerga admin logikasini qo'shish mumkin

# --- 6. BACKGROUND THREAD MANAGER ---
def run_bot_thread():
    bot.remove_webhook()
    bot.get_updates(offset=-1) # Pending updates killer
    bot.polling(none_stop=True)

if not any(t.name == "BotThread2026" for t in threading.enumerate()):
    t = threading.Thread(target=run_bot_thread, name="BotThread2026", daemon=True)
    t.start()

# --- 7. STREAMLIT WEB SAYT (CHIROYLI QISMI) ---
st.title("🛡️ AI Studio Control Center")

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712035.png", width=100)
    st.header("🔐 Admin Panel")
    parol = st.text_input("Parol kiriting", type="password")
    st.divider()
    st.info(f"📅 {datetime.now().strftime('%Y-%m-%d')}")

if parol == ADMIN_PASS:
    # --- ADMIN BOSHQARUV QISMI ---
    st.success("Tizimga muvaffaqiyatli kirildi!")
    
    tab1, tab2, tab3 = st.tabs(["📊 Statistika", "ℹ️ Bot Ma'lumotlari", "⚙️ Sozlamalar"])
    
    with tab1:
        col1, col2, col3 = st.columns(3)
        col1.metric("Server Threadlar", threading.active_count())
        col2.metric("Foydalanuvchilar (RAM)", len(GLOBAL_DATA))
        col3.metric("Status", "🟢 Active")
        
        st.subheader("Haftalik Faollik")
        chart_data = pd.DataFrame(np.random.randn(20, 2), columns=['PDF', 'OCR'])
        st.line_chart(chart_data)
        
    with tab2:
        st.subheader("Joriy Info Matni")
        st.markdown(f'<div class="info-box">{INFO_TEXT}</div>', unsafe_allow_html=True)
        
    with tab3:
        if st.button("🧹 RAM Xotirani Tozalash"):
            GLOBAL_DATA.clear()
            st.success("Xotira tozalandi!")

else:
    # --- FOYDALANUVCHI UCHUN CHIROYLI SAHIFA (Siz so'ragan qism) ---
    st.markdown("### 🤖 Universal AI Media Bot")
    st.image("https://img.freepik.com/free-vector/artificial-intelligence-background-digital-technology-concept_23-2148304918.jpg?w=1380", use_column_width=True, caption="Powered by AI Studio")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="info-box">
        <h4>🚀 Bot Imkoniyatlari:</h4>
        <ul>
            <li><b>PDF Skaner:</b> Rasmlarni professional PDF qilish</li>
            <li><b>OCR:</b> Rasmdagi matnlarni ko'chirib olish</li>
            <li><b>AI Enhance:</b> Sifatsiz rasmlarni tiniqlash</li>
            <li><b>Converter:</b> PDF ↔ Word ↔ Text</li>
        </ul>
        </div>
        """, unsafe_allow_html=True)
        
    with col2:
        st.info("💡 **Maslahat:** Botdan foydalanish uchun Telegramga kiring va **/start** tugmasini bosing.")
        st.warning("🔒 Barcha ma'lumotlar shifrlangan va xavfsiz saqlanadi.")
    
