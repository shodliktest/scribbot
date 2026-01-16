import streamlit as st
import telebot
from telebot import types
import whisper
from groq import Groq
import os, json, threading, pytz, torch, time, re, sys
from datetime import datetime
from deep_translator import GoogleTranslator

# --- 0. ADMIN VA BAZA SOZLAMALARI ---
ADMIN_ID = 1416457518 
USERS_FILE = "bot_users_list.txt"
BAN_FILE = "banned_users.json"
SETTINGS_FILE = "bot_settings.json"
uz_tz = pytz.timezone('Asia/Tashkent')

def get_uz_time():
    """O'zbekiston vaqtini olish"""
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f: return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, "w") as f: json.dump(data, f)

def log_user_and_get_count(m):
    """Foydalanuvchini ro'yxatga olish va tartib raqamini aniqlash"""
    uid = m.from_user.id
    user_list = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            user_list = f.readlines()
    
    exists = any(str(uid) in line for line in user_list)
    if not exists:
        count = len(user_list) + 1
        user_row = f"{count}. ID: {uid} | Ism: {m.from_user.first_name} | User: @{m.from_user.username} | {get_uz_time()}\n"
        with open(USERS_FILE, "a", encoding="utf-8") as f: f.write(user_row)
        try:
            bot.send_message(ADMIN_ID, f"🆕 *YANGI FOYDALANUVCHI! (№{count})*\n👤 {m.from_user.first_name}\n🆔 `{uid}`", parse_mode="Markdown")
        except: pass
        return count
    else:
        for i, line in enumerate(user_list):
            if str(uid) in line: return i + 1
    return len(user_list)

# --- 1. GLOBAL KONFIGURATSIYA ---
processing_lock = threading.Lock()
waiting_users = 0
WEB_APP_URL = "https://script1232.streamlit.app" 

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    st.error("❌ Secrets sozlanmagan!")
    st.stop()

client_groq = Groq(api_key=GROQ_API_KEY)
@st.cache_resource
def load_local_whisper():
    return whisper.load_model("base")

model_local = load_local_whisper()
bot = telebot.TeleBot(BOT_TOKEN)

# Bot holati
bot_config = load_json(SETTINGS_FILE, {"maintenance": False})
banned_users = load_json(BAN_FILE, [])

st.title("🤖 Neon Hybrid Ultimate Server")

user_settings = {} 
user_data = {}

# --- 2. KLAVIATURA VA MENU ---
def main_menu(uid):
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(types.KeyboardButton("⚡ Groq Rejimi"), types.KeyboardButton("🎧 Whisper Rejimi"))
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    if uid == ADMIN_ID:
        menu.add(types.KeyboardButton("🔑 Admin Panel"))
    return menu

# --- 3. AQLLI TAHLIL (FAQAT GROQ UCHUN) ---
def format_smart_context(text, lang_code=None):
    """Matnni professional formatlash va tarjima qo'shish"""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    formatted_text = "📝 **AQLLI TAHLIL NATIJASI (GROQ MODE)**\n\n"
    
    current_paragraph = ""
    for i, sent in enumerate(sentences):
        if lang_code:
            try:
                tr = GoogleTranslator(source='auto', target=lang_code).translate(sent)
                sent = f"{sent} _({tr})_" # Italiyan (Italic) uslubda
            except: pass
        
        current_paragraph += sent + " "
        if (i + 1) % 4 == 0:
            formatted_text += "    " + current_paragraph.strip() + "\n\n"
            current_paragraph = ""
    
    if current_paragraph:
        formatted_text += "    " + current_paragraph.strip()
    return formatted_text

# --- 4. BOT MANTIQI ---

@bot.message_handler(commands=['start'])
def welcome(m):
    if m.from_user.id in banned_users:
        bot.send_message(m.chat.id, "🚫 Botdan foydalanish taqiqlangan.")
        return
    if bot_config['maintenance'] and m.from_user.id != ADMIN_ID:
        bot.send_message(m.chat.id, "🔧 Texnik ishlar ketmoqda...")
        return

    count = log_user_and_get_count(m)
    user_settings[m.chat.id] = user_settings.get(m.chat.id, "groq")
    msg = (f"👋 **Assalomu alaykum!**\n\nSiz botimizning **{count}-foydalanuvchisiz!**\n\n"
           f"Tanlangan rejim: **{user_settings[m.chat.id].upper()}**")
    bot.send_message(m.chat.id, msg, parse_mode="Markdown", reply_markup=main_menu(m.chat.id))

@bot.message_handler(func=lambda m: m.text == "ℹ️ Yordam")
def help_btn(m):
    bot.send_message(m.chat.id, "📖 **Qo'llanma:**\n\n1. Audio yuboring.\n2. Tilni tanlang.\n3. Formatni (Split/Full) tanlang.\n\n⚠️ Maks: 25MB.")

@bot.message_handler(func=lambda m: m.text == "🌐 Saytga kirish (Login)")
def login_btn(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Saytga o'tish", url=WEB_APP_URL))
    bot.send_message(m.chat.id, "Neon Player uchun saytga kiring:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🔑 Admin Panel" and m.chat.id == ADMIN_ID)
def admin_p(m):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("📋 Ro'yxat", callback_data="adm_list"),
               types.InlineKeyboardButton("🔄 Reboot", callback_data="adm_reboot"),
               types.InlineKeyboardButton("📢 Xabar tarqatish", callback_data="adm_bc"),
               types.InlineKeyboardButton("🔧 Texnik ishlar", callback_data="adm_maint"),
               types.InlineKeyboardButton("📊 Stats", callback_data="adm_stats"))
    bot.send_message(ADMIN_ID, "🚀 **Admin boshqaruv paneli**", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"])
def switch_m(m):
    user_settings[m.chat.id] = "groq" if "Groq" in m.text else "local"
    bot.send_message(m.chat.id, f"✅ Rejim o'zgardi: **{user_settings[m.chat.id].upper()}**")

@bot.message_handler(content_types=['audio', 'voice'])
def handle_audio(m):
    f_size = m.audio.file_size if m.content_type == 'audio' else m.voice.file_size
    if f_size > 25 * 1024 * 1024:
        bot.send_message(m.chat.id, "❌ **Xato:** Fayl 25MB dan katta. Serverni himoya qilish uchun bunday fayllarni qabul qila olmayman.")
        return
    if f_size > 20 * 1024 * 1024:
        bot.send_message(m.chat.id, "⚠️ **Ogohlantirish:** Fayl 20MB dan katta, tahlil biroz ko'proq vaqt olishi mumkin.")

    user_data[m.chat.id] = {'fid': m.audio.file_id if m.content_type == 'audio' else m.voice.file_id, 'fname': m.audio.file_name if m.content_type == 'audio' else "Ovozli.ogg"}
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz"),
               types.InlineKeyboardButton("🇷🇺 Rus", callback_data="lang_ru"),
               types.InlineKeyboardButton("📄 Original", callback_data="lang_orig"))
    bot.send_message(m.chat.id, f"⚙️ Rejim: {user_settings.get(m.chat.id, 'groq').upper()}\n🌍 **Til:**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def calls(call):
    chat_id = call.message.chat.id
    global waiting_users, bot_config

    # Admin Callbacklari
    if chat_id == ADMIN_ID:
        if call.data == "adm_reboot":
            bot.send_message(ADMIN_ID, "🔄 Tizim qayta yuklanmoqda..."); os._exit(0)
        elif call.data == "adm_maint":
            bot_config['maintenance'] = not bot_config['maintenance']; save_json(SETTINGS_FILE, bot_config)
            bot.send_message(ADMIN_ID, f"🛠 Rejim: {'🔧 Texnik ishlar' if bot_config['maintenance'] else '✅ Faol'}")
        elif call.data == "adm_stats":
            count = 0
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, "r") as f: count = len(f.readlines())
            bot.send_message(ADMIN_ID, f"📊 Jami foydalanuvchilar: {count}")
        elif call.data == "adm_bc":
            msg = bot.send_message(ADMIN_ID, "📢 Xabarni yuboring:")
            bot.register_next_step_handler(msg, process_broadcast)
        elif call.data == "adm_list":
            if os.path.exists(USERS_FILE):
                with open(USERS_FILE, "rb") as f: bot.send_document(ADMIN_ID, f)

    # Foydalanuvchi Callbacklari
    if call.data.startswith("lang_"):
        user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("⏱ Split (Vaqt bilan)", callback_data="v_split"),
                   types.InlineKeyboardButton("📖 Full Context (Groqda aqlli)", callback_data="v_full"))
        bot.edit_message_text("📄 **Ko'rinish:**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("v_"):
        user_data[chat_id]['view'] = call.data.replace("v_", "")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📁 TXT Fayl", callback_data="f_txt"),
                   types.InlineKeyboardButton("💬 Chat", callback_data="f_chat"))
        bot.edit_message_text("💾 **Format:**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("f_"):
        fmt = call.data.replace("f_", "")
        data = user_data[chat_id]
        mode = user_settings.get(chat_id, "groq")
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ Navbatda: {waiting_users-1} kishi.\nRejim: **{mode.upper()}**")

        def process():
            global waiting_users
            with processing_lock:
                try:
                    def prog(p, txt):
                        bar = "▓" * (p // 10) + "░" * (10 - (p // 10))
                        try: bot.edit_message_text(f"🛰 **REJIM: {mode.upper()}**\n\n{txt}\n\n📊 {p}%\n{bar}", chat_id, wait_msg.message_id)
                        except: pass

                    prog(10, "📥 Yuklanmoqda...")
                    path = f"t_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(bot.download_file(bot.get_file(data['fid']).file_path))
                    
                    prog(50, "🧠 AI tahlil qilmoqda...")
                    if mode == "groq":
                        try:
                            with open(path, "rb") as f:
                                res = client_groq.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3-turbo", response_format="verbose_json")
                            segments = res.segments
                        except:
                            bot.edit_message_text("⚠️ **Groq Limitda!**\n\nIltimos, **Whisper Rejimi**ni tanlang yoki keyinroq urinib ko'ring.", chat_id, wait_msg.message_id)
                            return
                    else:
                        res = model_local.transcribe(path)
                        segments = res['segments']

                    prog(90, "✍️ Formatlanmoqda...")
                    l_code = {"uz":"uz", "ru":"ru"}.get(data['lang'])
                    final_text = ""

                    if mode == "groq":
                        if data['view'] == "full":
                            raw_txt = " ".join([s['text'].strip() for s in segments])
                            final_text = format_smart_context(raw_txt, l_code)
                        else:
                            for s in segments:
                                tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                                txt = s['text'].strip()
                                tr = GoogleTranslator(source='auto', target=l_code).translate(txt) if l_code else ""
                                final_text += f"{tm} {txt}\n" + (f" _({tr})_\n\n" if tr else "\n")
                    else:
                        for s in segments:
                            tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                            txt = s['text'].strip()
                            final_text += f"{tm} {txt}\n\n"

                    imzo = f"\n---\n👤 **Dasturchi:** @Otavaliyev_M\n🤖 **Bot:** @{bot.get_me().username}\n⏰ **Vaqt:** {get_uz_time()}"
                    
                    if fmt == "txt":
                        with open(f"r_{chat_id}.txt", "w", encoding="utf-8") as f: f.write(final_text + imzo)
                        with open(f"r_{chat_id}.txt", "rb") as f: bot.send_document(chat_id, f, caption=f"Tayyor! \nBot: @{bot.get_me().username}")
                        os.remove(f"r_{chat_id}.txt")
                    else:
                        bot.send_message(chat_id, (final_text + imzo)[:4096], parse_mode="Markdown")

                    bot.delete_message(chat_id, wait_msg.message_id)
                    if os.path.exists(path): os.remove(path)
                except Exception as e: bot.send_message(chat_id, f"❌ Xato: {e}")
                finally: waiting_users -= 1

        threading.Thread(target=process).start()

def process_broadcast(message):
    user_ids = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            for line in f:
                try: user_ids.append(line.split("|")[0].split(":")[1].strip())
                except: pass
    s, f = 0, 0
    for uid in user_ids:
        try: bot.copy_message(uid, ADMIN_ID, message.message_id); s += 1
        except: f += 1
    bot.send_message(ADMIN_ID, f"✅ Yakunlandi! Yetkazildi: {s}, Xato: {f}")

threading.Thread(target=bot.infinity_polling, daemon=True).start()
                
