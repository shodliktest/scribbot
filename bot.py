import streamlit as st
import telebot
from telebot import types
import whisper
from groq import Groq
import os, json, threading, pytz, torch, time, re
from datetime import datetime
from deep_translator import GoogleTranslator

# --- 0. ADMIN VA BAZA SOZLAMALARI ---
ADMIN_ID = 1416457518 # Sizning Telegram ID
USERS_FILE = "bot_users_list.txt"
uz_tz = pytz.timezone('Asia/Tashkent')

def get_uz_time():
    """O'zbekiston vaqtini qaytaradi"""
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def log_user_and_get_count(m):
    """Foydalanuvchini ro'yxatga oladi va uning tartib raqamini qaytaradi"""
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

user_settings = {} # Rejimni saqlash
user_data = {}     # Tahlil ma'lumotlarini saqlash

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
    user_settings[m.chat.id] = user_settings.get(m.chat.id, "groq")
    
    mode_text = "⚡ Groq (Tezkor)" if user_settings[m.chat.id] == "groq" else "🎧 Whisper (Basic)"
    
    msg = (
        f"👋 **Assalomu alaykum!**\n\n"
        f"Siz botimizning **{count}-foydalanuvchisiz!**\n\n"
        "Men audio va ovozli xabarlarni matnga aylantirib beruvchi aqlli botman.\n\n"
        "🚀 **Imkoniyatlar:**\n"
        "• **Groq Rejimi:** Dunyodagi eng tezkor tahlil.\n"
        "• **Whisper Rejimi:** Sekinroq lekin aniq tahlil.\n\n"
        f"💡 Hozirgi rejim: **{mode_text}**\n\n"
        "Boshlash uchun audio yuboring!"
    )
    bot.send_message(m.chat.id, msg, parse_mode="Markdown", reply_markup=main_menu_markup(m.chat.id))

# YORDAM VA LOGIN JAVOBLARI
@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def help_answer(m):
    help_text = (
        "❓ **Botdan qanday foydalanish kerak?**\n\n"
        "1️⃣ **Rejimni tanlang:** 'Groq' (juda tez) yoki 'Whisper' (navbat bilan).\n"
        "2️⃣ **Audio yuboring:** Ovozli xabar yoki musiqa fayli.\n"
        "3️⃣ **Tilni tanlang:** Original matn yoki tarjima (O'zbek/Rus).\n"
        "4️⃣ **Natijani oling:** Bot sizga vaqtlar bo'yicha (Timelips) tahlilni yuboradi.\n\n"
        "⚠️ **Eslatma:** Bir vaqtda faqat bitta fayl tahlil qilinadi. Agar navbat bo'lsa, bot sizni xabardor qiladi."
    )
    bot.send_message(m.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🌐 Saytga kirish (Login)")
def login_answer(m):
    login_text = (
        "🌐 **Bizning Web-Platforma**\n\n"
        "Saytimizda siz tahlil qilingan matnlarni **Neon Karaoke** effektida ko'rishingiz mumkin!\n\n"
        f"🔗 **Manzil:** {WEB_APP_URL}\n\n"
        "💡 **Afzalliklari:**\n"
        "• Interaktiv interfeys\n"
        "• Kattaroq fayllar bilan ishlash\n"
        "• Vizual qulaylik"
    )
    bot.send_message(m.chat.id, login_text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔑 Admin Panel" and m.chat.id == ADMIN_ID)
def admin_panel(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 Chatda ro'yxat", callback_data="adm_chat"),
               types.InlineKeyboardButton("📁 TXT faylda", callback_data="adm_txt"))
    bot.send_message(m.chat.id, "Admin panelga xush kelibsiz.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"])
def change_mode(m):
    if "Groq" in m.text:
        user_settings[m.chat.id] = "groq"
        bot.send_message(m.chat.id, "✅ **Groq Rejimi tanlandi!**")
    else:
        user_settings[m.chat.id] = "local"
        bot.send_message(m.chat.id, "✅ **Whisper Rejimi tanlandi!**")

@bot.message_handler(content_types=['audio', 'voice'])
def audio_handler(m):
    if m.chat.id not in user_settings: user_settings[m.chat.id] = "groq"
    user_data[m.chat.id] = {'m_ids': [m.message_id]}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 Original", callback_data="lang_orig"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        types.InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru")
    )
    mode = "⚡ Groq" if user_settings[m.chat.id] == "groq" else "🎧 Whisper"
    bot.send_message(m.chat.id, f"🎯 **Rejim:** {mode}\n\n🌍 **Tahlil tilini tanlang:**", reply_markup=markup)
    
    user_data[m.chat.id]['fid'] = m.audio.file_id if m.content_type == 'audio' else m.voice.file_id
    user_data[m.chat.id]['fname'] = m.audio.file_name if m.content_type == 'audio' else f"audio_{get_uz_time()}.ogg"

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    global waiting_users
    
    if call.data.startswith("lang_"):
        user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        user_data[chat_id]['view'] = "split" # Faqat Timelips rejimi
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📁 TXT Fayl", callback_data="fmt_txt"),
                   types.InlineKeyboardButton("💬 Chatda olish", callback_data="fmt_chat"))
        bot.edit_message_text("📁 **Natijani qanday formatda olishni xohlaysiz?**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("adm_"):
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            if call.data == "adm_chat":
                bot.send_message(ADMIN_ID, f"📑 **Foydalanuvchilar:**\n\n{content[:4000]}")
            else:
                with open("users.txt", "w", encoding="utf-8") as f: f.write(content)
                with open("users.txt", "rb") as f: bot.send_document(ADMIN_ID, f, caption="📂 Ro'yxat")
                os.remove("users.txt")
        else: bot.send_message(ADMIN_ID, "Baza bo'sh.")

    elif call.data.startswith("fmt_"):
        fmt = call.data.replace("fmt_", "")
        data = user_data[chat_id]
        mode = user_settings[chat_id]
        
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Siz navbatdasiz.**\nSizdan oldin: {waiting_users-1} kishi bor.")

        def process_task():
            global waiting_users
            with processing_lock:
                def update_progress(percent, status_text):
                    bar_len = 10
                    filled = int(percent / 10)
                    bar = "▓" * filled + "░" * (bar_len - filled)
                    progress_msg = f"🛰 **TAHLIL: {mode.upper()}**\n\n{status_text}\n\n📊 Progress: {percent}%\n{bar}"
                    try: bot.edit_message_text(progress_msg, chat_id, wait_msg.message_id)
                    except: pass

                try:
                    for p in range(0, 25, 5): 
                        update_progress(p, "📥 Fayl yuklanmoqda...")
                        time.sleep(0.2)
                        
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    path = f"tmp_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(down)
                    
                    update_progress(30, "🧠 AI tahlil qilmoqda...")
                    
                    segments = []
                    if mode == "groq":
                        try:
                            with open(path, "rb") as f:
                                res = client_groq.audio.transcriptions.create(
                                    file=(path, f.read()), model="whisper-large-v3-turbo", response_format="verbose_json"
                                )
                            segments = res.segments
                        except:
                            bot.send_message(chat_id, "⚠️ Groq limiti tugagan. Iltimos birozdan so'ng urinib ko'ring yoki **Whisper Rejimi**ni ishlating.")
                            return
                    else:
                        res = model_local.transcribe(path)
                        segments = res['segments']

                    update_progress(80, "✍️ Matn shakllantirilmoqda...")

                    lang_code = {"uz": "uz", "ru": "ru"}.get(data['lang'])
                    final_text = ""
                    
                    # FAQAT TIMELIPS (SPLIT) REJIMI
                    for s in segments:
                        tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                        txt = s['text'].strip()
                        if lang_code:
                            tr = GoogleTranslator(source='auto', target=lang_code).translate(txt)
                            final_text += f"{tm} {txt} ({tr})\n\n"
                        else:
                            final_text += f"{tm} {txt}\n\n"

                    update_progress(100, "✅ Yakunlandi!")

                    footer = (
                        f"\n\n---\n"
                        f"⚙️ Rejim: {mode.upper()}\n"
                        f"⏰ Vaqt: {get_uz_time()}"
                    )
                    
                    if fmt == "txt":
                        with open(f"res_{chat_id}.txt", "w", encoding="utf-8") as f: 
                            f.write(final_text + footer)
                        with open(f"res_{chat_id}.txt", "rb") as f:
                            bot.send_document(chat_id, f, caption=f"Tayyor!")
                        os.remove(f"res_{chat_id}.txt")
                    else:
                        if len(final_text + footer) > 4000:
                            bot.send_message(chat_id, (final_text + footer)[:4000])
                            bot.send_message(chat_id, (final_text + footer)[4000:])
                        else:
                            bot.send_message(chat_id, final_text + footer)

                    bot.delete_message(chat_id, wait_msg.message_id)
                    if os.path.exists(path): os.remove(path)

                except Exception as e:
                    bot.send_message(chat_id, f"❌ Xatolik yuz berdi.")
                finally:
                    waiting_users -= 1

        threading.Thread(target=process_task).start()

threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
