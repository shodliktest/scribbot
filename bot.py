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

# Streamlit ma'lumotlarni unutmasligi uchun session_state dan foydalanamiz
if "user_data" not in st.session_state: st.session_state.user_data = {}
if "user_settings" not in st.session_state: st.session_state.user_settings = {}

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

# --- 2. KLAVIATURA VA MENU ---
def main_menu(uid):
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(types.KeyboardButton("⚡ Groq Rejimi"), types.KeyboardButton("🎧 Whisper Rejimi"))
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    if uid == ADMIN_ID:
        menu.add(types.KeyboardButton("🔑 Admin Panel"))
    return menu

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
    st.session_state.user_settings[m.chat.id] = st.session_state.user_settings.get(m.chat.id, "groq")
    current_mode = st.session_state.user_settings[m.chat.id]
    mode_text = "⚡ Groq" if current_mode == "groq" else "🎧 Whisper"
    
    msg = (
        f"👋 **Assalomu alaykum!**\n\n"
        f"Siz botimizning **{count}-foydalanuvchisiz!**\n\n"
        "Men audio va ovozli xabarlarni matnga aylantirib beruvchi aqlli botman.\n\n"
        "🚀 **Imkoniyatlar:**\n"
        "• **Groq Rejimi:** Dunyodagi eng tezkor tahlil.\n"
        "• **Whisper Rejimi:** Pauzalarga asoslangan ritmik tahlil.\n\n"
        f"💡 Hozirgi rejim: **{mode_text}**\n\n"
        "Boshlash uchun audio yuboring!"
    )
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
    st.session_state.user_settings[m.chat.id] = "groq" if "Groq" in m.text else "local"
    bot.send_message(m.chat.id, f"✅ Rejim o'zgardi: **{st.session_state.user_settings[m.chat.id].upper()}**")

@bot.message_handler(content_types=['audio', 'voice'])
def handle_audio(m):
    f_size = m.audio.file_size if m.content_type == 'audio' else m.voice.file_size
    if f_size > 25 * 1024 * 1024:
        bot.send_message(m.chat.id, "❌ **Xato:** Fayl 25MB dan katta. Serverni himoya qilish uchun bunday fayllarni qabul qila olmayman.")
        return
    
    st.session_state.user_data[m.chat.id] = {
        'fid': m.audio.file_id if m.content_type == 'audio' else m.voice.file_id, 
        'fname': m.audio.file_name if m.content_type == 'audio' else "Ovozli.ogg"
    }
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 Original", callback_data="lang_orig"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        types.InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru")
    )
    current_mode = st.session_state.user_settings.get(m.chat.id, "groq")
    mode = "⚡ Groq" if current_mode == "groq" else "🎧 Whisper"
    bot.send_message(m.chat.id, f"🎯 **Tanlangan rejim:** {mode}\n\n🌍 **Tarjima tilini tanlang:**\n(Til tanlansa, har bir gapdan so'ng qavs ichida tarjimasi qo'shiladi)", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def calls(call):
    chat_id = call.message.chat.id
    global waiting_users, bot_config

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

    if call.data.startswith("lang_"):
        if chat_id not in st.session_state.user_data:
            bot.answer_callback_query(call.id, "❌ Audio ma'lumotlari muddati o'tgan. Qayta yuboring.", show_alert=True)
            return
        st.session_state.user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("⏱ Split (Vaqt bilan)", callback_data="v_split"),
                    types.InlineKeyboardButton("📖 Full Context (Groqda aqlli)", callback_data="v_full"))
        bot.edit_message_text("📄 **Ko'rinish:**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("v_"):
        st.session_state.user_data[chat_id]['view'] = call.data.replace("v_", "")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("📁 TXT Fayl", callback_data="f_txt"),
                    types.InlineKeyboardButton("💬 Chat", callback_data="f_chat"))
        bot.edit_message_text("💾 **Format: Malumotni qaysi kornishda olmoqchisiz?**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("f_"):
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        fmt = call.data.replace("f_", "")
        data = st.session_state.user_data.get(chat_id)
        mode = st.session_state.user_settings.get(chat_id, "groq")
        
        if not data:
            bot.send_message(chat_id, "❌ Xatolik: Ma'lumot topilmadi. Audioni qayta yuboring.")
            return

        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Siz navbatdasiz.**\nSizdan oldin: {waiting_users-1} kishi bor.\nRejim: {mode.upper()}")

        def process_task():
            global waiting_users
            with processing_lock:
                def update_progress(percent, status_text):
                    bar_len = 10
                    filled = int(percent / 10)
                    bar = "▓" * filled + "░" * (bar_len - filled)
                    progress_msg = f"🛰 **TAHLIL REJIMIDAGI HOLAT: {mode.upper()}**\n\n{status_text}\n\n📊 Progress: {percent}%\n{bar}"
                    try: bot.edit_message_text(progress_msg, chat_id, wait_msg.message_id)
                    except: pass

                path = f"tmp_{chat_id}.mp3"
                try:
                    update_progress(10, "📥 Fayl serverga yuklanmoqda...")
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    with open(path, "wb") as f: f.write(down)
                    
                    update_progress(30, "🧠 AI model ishga tushmoqda...")
                    segments = []
                    if mode == "groq":
                        with open(path, "rb") as f:
                            res = client_groq.audio.transcriptions.create(
                                file=(path, f), model="whisper-large-v3-turbo", response_format="verbose_json"
                            )
                        segments = res.segments
                    else:
                        res = model_local.transcribe(path)
                        segments = res['segments']

                    update_progress(70, "✍️ Matn shakllantirilmoqda...")
                    lang_code = data['lang'] if data['lang'] != "orig" else None
                    final_text = ""
                    
                    if data['view'] == "split":
                        for s in segments:
                            start_time = s['start']
                            sub_sentences = re.split(r'(?<=[.!?])\s+', s['text'].strip())
                            for sub in sub_sentences:
                                if not sub: continue
                                tm = f"[{int(start_time//60):02d}:{int(start_time%60):02d}]"
                                if lang_code:
                                    try:
                                        tr = GoogleTranslator(source='auto', target=lang_code).translate(sub)
                                        final_text += f"{tm} {sub}\n_({tr})_\n\n"
                                    except: final_text += f"{tm} {sub}\n\n"
                                else:
                                    final_text += f"{tm} {sub}\n\n"
                    else:
                        raw_full = " ".join([s['text'].strip() for s in segments])
                        sentences = re.split(r'(?<=[.!?])\s+', raw_full)
                        for sent in sentences:
                            if not sent: continue
                            if lang_code:
                                try:
                                    tr = GoogleTranslator(source='auto', target=lang_code).translate(sent)
                                    final_text += f"{sent} ({tr}) "
                                except: final_text += f"{sent} "
                            else: final_text += f"{sent} "

                    update_progress(100, "✅ Tahlil yakunlandi!")
                    footer = f"\n\n---\n👤 Dasturchi: @Otavaliyev_M\n🤖 Bot: @{bot.get_me().username}\n⚙️ Rejim: {mode.upper()}\n⏰ Vaqt: {get_uz_time()}"
                    
                    if fmt == "txt":
                        txt_file = f"res_{chat_id}.txt"
                        with open(txt_file, "w", encoding="utf-8") as f: f.write(final_text + footer)
                        with open(txt_file, "rb") as f: bot.send_document(chat_id, f, caption="Natija tayyor!")
                        os.remove(txt_file)
                    else:
                        full_msg = final_text + footer
                        if len(full_msg) > 4000:
                            for x in range(0, len(full_msg), 4000): bot.send_message(chat_id, full_msg[x:x+4000])
                        else: bot.send_message(chat_id, full_msg)

                    bot.delete_message(chat_id, wait_msg.message_id)
                except Exception as e:
                    bot.send_message(chat_id, f"❌ Xatolik: {e}")
                finally:
                    if os.path.exists(path): os.remove(path)
                    waiting_users -= 1

        threading.Thread(target=process_task).start()

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

# --- 5. STREAMLIT LIFECYCLE (Conflict 409 oldini olish) ---
if "bot_started" not in st.session_state:
    # Eski pollinglarni tozalash
    bot.stop_polling()
    time.sleep(1)
    # Yangi botni faqat bir marta ishga tushirish
    threading.Thread(target=bot.infinity_polling, kwargs={"timeout":20, "long_polling_timeout":10}, daemon=True).start()
    st.session_state["bot_started"] = True
    st.write("✅ Bot Polling ishga tushirildi.")

st.info("Bot holati: Faol. Audio yuborishni kuting.")
