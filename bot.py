import streamlit as st
import telebot
from telebot import types
import whisper
from groq import Groq
import os, json, threading, pytz, torch, time, re, gc
from datetime import datetime
from deep_translator import GoogleTranslator

# --- 0. ADMIN VA BAZA SOZLAMALARI ---
ADMIN_ID = 1416457518 
USERS_FILE = "bot_users_list.txt"
uz_tz = pytz.timezone('Asia/Tashkent')
FILE_SIZE_LIMIT_MB = 20 # 20 MB limit

def get_uz_time():
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def log_user_and_get_count(m):
    uid = m.from_user.id
    first_name = m.from_user.first_name
    username = f"@{m.from_user.username}" if m.from_user.username else "yo'q"
    
    user_list = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            user_list = f.readlines()
            
    exists = any(str(uid) in line for line in user_list)
    
    if not exists:
        count = len(user_list) + 1
        user_row = f"{count}. ID: {uid} | Ism: {first_name} | User: {username} | Sana: {get_uz_time()}\n"
        with open(USERS_FILE, "a", encoding="utf-8") as f:
            f.write(user_row)
        
        report = (
            f"🆕 *YANGI FOYDALANUVCHI! (№{count})*\n\n"
            f"👤 Ism: {first_name}\n"
            f"🆔 ID: `{uid}`\n"
            f"⏰ Vaqt: {get_uz_time()}"
        )
        try: bot.send_message(ADMIN_ID, report, parse_mode="Markdown")
        except: pass
        return count
    else:
        for i, line in enumerate(user_list):
            if str(uid) in line:
                return i + 1
    return len(user_list)

# --- 1. GLOBAL KONFIGURATSIYA ---
processing_lock = threading.Lock()
waiting_users = 0
WEB_APP_URL = "https://script1232.streamlit.app" 

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    st.error("❌ Secrets-da kerakli kalitlar topilmadi!")
    st.stop()

client_groq = Groq(api_key=GROQ_API_KEY)

@st.cache_resource
def load_local_whisper():
    return whisper.load_model("base")

model_local = load_local_whisper()
bot = telebot.TeleBot(BOT_TOKEN)

# Streamlit interfeysi
st.set_page_config(page_title="Neon Hybrid Server", layout="centered")
st.title("🤖 Neon Hybrid Bot Server")
st.success("Server va Bot faol holatda!")

if 'user_settings' not in st.session_state: st.session_state.user_settings = {}
if 'user_data' not in st.session_state: st.session_state.user_data = {}

# --- 2. MENU VA KLAVIATURA ---
def main_menu_markup(uid):
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(types.KeyboardButton("⚡ Groq Rejimi"), types.KeyboardButton("🎧 Whisper Rejimi"))
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    if uid == ADMIN_ID:
        menu.add(types.KeyboardButton("🔑 Admin Panel"))
    return menu

# --- 3. BOT FUNKSIYALARI ---

@bot.message_handler(commands=['start'])
def welcome(m):
    count = log_user_and_get_count(m)
    st.session_state.user_settings[m.chat.id] = st.session_state.user_settings.get(m.chat.id, "groq")
    mode_text = "⚡ Groq (Tezkor)" if st.session_state.user_settings[m.chat.id] == "groq" else "🎧 Whisper (Basic)"
    
    msg = (
        f"👋 **Assalomu alaykum!**\n\n"
        f"Siz botimizning **{count}-foydalanuvchisiz!**\n\n"
        "Men audio va ovozli xabarlarni matnga aylantirib beruvchi aqlli botman.\n\n"
        f"💡 Hozirgi rejim: **{mode_text}**\n\n"
        "Boshlash uchun audio yuboring!"
    )
    bot.send_message(m.chat.id, msg, parse_mode="Markdown", reply_markup=main_menu_markup(m.chat.id))

@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def help_answer(m):
    help_text = (
        "❓ **Qanday ishlatish kerak?**\n\n"
        "1️⃣ Rejimni tanlang (Groq/Whisper).\n"
        "2️⃣ Audio yoki Voice yuboring.\n"
        "3️⃣ Tilni tanlang va natijani qabul qiling.\n\n"
        f"⚠️ **Limit:** Fayl hajmi {FILE_SIZE_LIMIT_MB} MB dan oshmasligi kerak."
    )
    bot.send_message(m.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🌐 Saytga kirish (Login)")
def login_answer(m):
    login_text = (
        "🌐 **Web-Platforma**\n\n"
        f"🔗 Manzil: {WEB_APP_URL}\n\n"
        "Saytda Neon effektli tahlillarni ko'rishingiz mumkin!"
    )
    bot.send_message(m.chat.id, login_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"])
def change_mode(m):
    st.session_state.user_settings[m.chat.id] = "groq" if "Groq" in m.text else "local"
    bot.send_message(m.chat.id, f"✅ Rejim o'zgardi: **{st.session_state.user_settings[m.chat.id].upper()}**")

@bot.message_handler(content_types=['audio', 'voice'])
def audio_handler(m):
    # --- HAJMNI TEKSHIRISH ---
    f_size = m.audio.file_size if m.content_type == 'audio' else m.voice.file_size
    if f_size > FILE_SIZE_LIMIT_MB * 1024 * 1024:
        bot.send_message(m.chat.id, f"❌ **Fayl juda katta!**\nServer barqarorligi uchun limit: **{FILE_SIZE_LIMIT_MB} MB** qilib belgilangan.\nSizning faylingiz: {round(f_size/(1024*1024), 2)} MB")
        return

    if m.chat.id not in st.session_state.user_settings: st.session_state.user_settings[m.chat.id] = "groq"
    st.session_state.user_data[m.chat.id] = {'m_ids': [m.message_id]}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 Original", callback_data="lang_orig"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        types.InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru")
    )
    bot.send_message(m.chat.id, "🌍 **Tarjima tilini tanlang:**", reply_markup=markup)
    st.session_state.user_data[m.chat.id]['fid'] = m.audio.file_id if m.content_type == 'audio' else m.voice.file_id

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    global waiting_users
    
    if call.data.startswith("lang_"):
        st.session_state.user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("⏱ Split", callback_data="view_split"),
                   types.InlineKeyboardButton("📖 Full Context", callback_data="view_full"))
        bot.edit_message_text("📄 **Matn ko'rinishini tanlang:**", chat_id, call.message.message_id, reply_markup=markup)
        
    elif call.data.startswith("view_"):
        st.session_state.user_data[chat_id]['view'] = call.data.replace("view_", "")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📁 TXT Fayl", callback_data="fmt_txt"),
                   types.InlineKeyboardButton("💬 Chatda olish", callback_data="fmt_chat"))
        bot.edit_message_text("📁 **Formatni tanlang:**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("fmt_"):
        fmt = call.data.replace("fmt_", "")
        data = st.session_state.user_data[chat_id]
        mode = st.session_state.user_settings[chat_id]
        
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Navbatdasiz.** Oldinda: {waiting_users-1} kishi.")

        def process_task():
            global waiting_users
            with processing_lock:
                try:
                    bot.edit_message_text("📥 Serverga yuklanmoqda...", chat_id, wait_msg.message_id)
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    path = f"tmp_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(down)
                    
                    bot.edit_message_text(f"🧠 AI Tahlil boshlandi ({mode.upper()})...", chat_id, wait_msg.message_id)
                    segments = []
                    if mode == "groq":
                        with open(path, "rb") as f:
                            res = client_groq.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3-turbo", response_format="verbose_json")
                        segments = res.segments
                    else:
                        res = model_local.transcribe(path); segments = res['segments']

                    lang_code = {"uz": "uz", "ru": "ru"}.get(data['lang'])
                    final_text = ""
                    if data['view'] == "split":
                        for s in segments:
                            tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                            txt = s['text'].strip()
                            tr = GoogleTranslator(source='auto', target=lang_code).translate(txt) if lang_code else ""
                            final_text += f"{tm} {txt} ({tr})\n\n" if tr else f"{tm} {txt}\n\n"
                    else:
                        raw_full = " ".join([s['text'].strip() for s in segments])
                        sentences = re.split(r'(?<=[.!?])\s+', raw_full)
                        for sent in sentences:
                            tr = GoogleTranslator(source='auto', target=lang_code).translate(sent) if lang_code else ""
                            final_text += f"{sent} ({tr}) " if tr else f"{sent} "

                    footer = f"\n\n---\n⚙️ Rejim: {mode.upper()}\n⏰ {get_uz_time()}"
                    if fmt == "txt":
                        with open(f"res_{chat_id}.txt", "w", encoding="utf-8") as f: f.write(final_text + footer)
                        with open(f"res_{chat_id}.txt", "rb") as f: bot.send_document(chat_id, f)
                        os.remove(f"res_{chat_id}.txt")
                    else:
                        if len(final_text + footer) > 4000:
                            bot.send_message(chat_id, (final_text + footer)[:4000])
                        else:
                            bot.send_message(chat_id, final_text + footer)

                    bot.delete_message(chat_id, wait_msg.message_id)
                except Exception as e: bot.send_message(chat_id, f"❌ Xatolik: {e}")
                finally:
                    # --- XOTIRANI TOZALASH ---
                    if os.path.exists(path): os.remove(path)
                    waiting_users -= 1
                    gc.collect() # RAMni bo'shatish

        threading.Thread(target=process_task).start()

# --- SINGLETON POLLING (CONFLICT 409 FIX) ---
@st.cache_resource
def start_bot_singleton():
    try: bot.stop_polling()
    except: pass
    thread = threading.Thread(target=bot.infinity_polling, kwargs={'timeout': 20, 'long_polling_timeout': 10}, daemon=True)
    thread.start()
    return True

start_bot_singleton()
                                                                                                                                                                         
