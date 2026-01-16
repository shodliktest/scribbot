import streamlit as st
import telebot
from telebot import types
import whisper
from groq import Groq
import os, json, threading, pytz, torch, time
from datetime import datetime
from deep_translator import GoogleTranslator

# --- 0. ADMIN SOZLAMALARI VA HOLATI ---
ADMIN_ID = 1416457518 
USERS_FILE = "bot_users_list.txt"

# Bot va rejimlar holatini saqlash (Session State)
if 'bot_status' not in st.session_state:
    st.session_state.bot_status = True  # Bot xizmati yoqilgan/o'chirilgan
if 'modes_status' not in st.session_state:
    st.session_state.modes_status = True # Rejimlar (Groq/Whisper) ishlayapti/yopiq

def log_user_to_admin(m):
    """Yangi foydalanuvchini ro'yxatga oladi va adminga bildiradi"""
    uid = m.from_user.id
    first_name = m.from_user.first_name
    last_name = m.from_user.last_name or ""
    username = f"@{m.from_user.username}" if m.from_user.username else "yo'q"
    
    exists = False
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            if str(uid) in f.read():
                exists = True
                
    if not exists:
        user_row = f"ID: {uid} | Name: {first_name} {last_name} | Username: {username} | Date: {get_uz_time()}\n"
        with open(USERS_FILE, "a", encoding="utf-8") as f:
            f.write(user_row)
            
        report = (
            f"🆕 *YANGI FOYDALANUVCHI START BOSDI!*\n\n"
            f"🆔 *UID:* `{uid}`\n"
            f"👤 *Ism:* {first_name} {last_name}\n"
            f"🌐 *Username:* {username}\n"
            f"⏰ *Vaqt:* {get_uz_time()}"
        )
        try:
            bot.send_message(ADMIN_ID, report, parse_mode="Markdown")
        except:
            pass

# --- 1. GLOBAL SOZLAMALAR (Asil kod) ---
params = st.query_params

if params.get("cron") == "1":
    st.markdown("OK")
    st.stop()

processing_lock = threading.Lock()
waiting_users = 0

uz_tz = pytz.timezone('Asia/Tashkent')
WEB_APP_URL = "https://script1232.streamlit.app" 

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    st.error("❌ Secrets-da BOT_TOKEN yoki GROQ_API_KEY topilmadi!")
    st.stop()

client_groq = Groq(api_key=GROQ_API_KEY)

@st.cache_resource
def load_local_whisper():
    return whisper.load_model("base")

model_local = load_local_whisper()
bot = telebot.TeleBot(BOT_TOKEN)

st.set_page_config(page_title="Neon Hybrid Server", layout="centered")
st.title("🤖 Neon Hybrid Bot Server")
st.success("Server va Bot ishlamoqda!")
st.info("Ushbu sahifa botning 'miyasi' hisoblanadi. Uni yopmang.")

user_settings = {} 
user_data = {}

# --- 2. YORDAMCHI FUNKSIYALAR ---
def get_uz_time():
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def main_menu_markup(uid):
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if int(uid) == ADMIN_ID:
        menu.add(types.KeyboardButton("👑 Admin Panel"))
    menu.add(types.KeyboardButton("⚡ Groq Rejimi"), types.KeyboardButton("🎧 Whisper Rejimi"))
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    return menu

def admin_panel_markup():
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(types.KeyboardButton("📊 Statistika"), types.KeyboardButton("📂 Ro'yxatni yuklash"))
    menu.add(types.KeyboardButton("📢 Hammaga xabar"), types.KeyboardButton("👤 UID-ga xabar"))
    menu.add(types.KeyboardButton("🛑 Botni to'xtatish"), types.KeyboardButton("✅ Botni ishlatish"))
    menu.add(types.KeyboardButton("📵 Rejimlarni yopish"), types.KeyboardButton("📶 Rejimlarni yoqish"))
    menu.add(types.KeyboardButton("♻️ Reboot"), types.KeyboardButton("⬅️ Orqaga"))
    return menu

# --- 3. BOT MANTIQI ---

@bot.message_handler(commands=['start'])
def welcome(m):
    # Log tizimi
    log_user_to_admin(m)
    
    if m.chat.id not in user_settings:
        user_settings[m.chat.id] = "groq"
    
    current_mode = "⚡ Groq (Tezkor)" if user_settings[m.chat.id] == "groq" else "🎧 Whisper (Basic)"
    
    # ORIGINAL JAVOB MATNI (Hech nima qisqartirilmadi)
    msg_text = (
        "👋 **Assalomu alaykum!**\n\n"
        "Men audio va ovozli xabarlarni matnga aylantirib beruvchi aqlli botman. "
        "Siz uchun ikkita maxsus tahlil rejimi tayyorlab qo'yilgan:\n\n"
        "⚡ **Groq Rejimi (Cloud):**\n"
        "Dunyodagi eng tezkor serverlar (Groq LPU) yordamida ishlaydi. "
        "Audiongizni o'ta tezkor (3-5 soniyada) va yuqori aniqlikda tahlil qiladi.\n\n"
        "🎧 **Whisper Rejimi (Local/Basic):**\n"
        "Ushbu rejim audiodagi ritm, nafas va pauzalarga asoslanadi. "
        "Matnni xuddi siz eshitganingizdek ritmik bo'laklarga bo'lib beradi.\n\n"
        "🚀 **Boshlash uchun menga audio yoki ovozli xabar yuboring!**\n\n"
        f"💡 *Hozirgi tanlangan rejim:* **{current_mode}**\n"
        "*(Rejimni pastdagi menyu tugmalari orqali xohlagan vaqtda o'zgartirishingiz mumkin)*"
    )
    
    if m.chat.id == ADMIN_ID:
        msg_text += "\n\n😎 **Salom Admin! Boshqaruv paneli yuklandi.**"
        
    bot.send_message(m.chat.id, msg_text, parse_mode="Markdown", reply_markup=main_menu_markup(m.chat.id))

# --- 4. ADMIN PANEL HANDLERS ---
@bot.message_handler(func=lambda message: message.text == "👑 Admin Panel" and message.chat.id == ADMIN_ID)
def admin_panel_open(m):
    bot.send_message(m.chat.id, "🛠 **Admin boshqaruv paneli ochildi:**", reply_markup=admin_panel_markup())

@bot.message_handler(func=lambda message: message.chat.id == ADMIN_ID)
def handle_admin_requests(m):
    if m.text == "📊 Statistika":
        count = 0
        last_u = "Hali yo'q"
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
                count = len(lines)
                if count > 0: last_u = lines[-1].strip()
        
        stat_msg = (
            f"📊 **Statistika:**\n\n"
            f"👥 Jami foydalanuvchilar: {count}\n"
            f"🕒 Oxirgi qo'shilgan: \n`{last_u}`\n\n"
            f"🤖 Bot holati: {'✅ Aktiv' if st.session_state.bot_status else '🛑 To\'xtatilgan'}\n"
            f"⚙️ Rejimlar: {'✅ Ochiq' if st.session_state.modes_status else '📵 Yopiq'}"
        )
        bot.send_message(m.chat.id, stat_msg, parse_mode="Markdown")

    elif m.text == "📂 Ro'yxatni yuklash":
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "rb") as f:
                bot.send_document(m.chat.id, f, caption="📂 Barcha foydalanuvchilar ro'yxati")
        else:
            bot.send_message(m.chat.id, "Ro'yxat bo'sh.")

    elif m.text == "🛑 Botni to'xtatish":
        st.session_state.bot_status = False
        bot.send_message(m.chat.id, "🛑 Bot yangi audiolarni qabul qilmaydi (Admin uchun ochiq).")

    elif m.text == "✅ Botni ishlatish":
        st.session_state.bot_status = True
        bot.send_message(m.chat.id, "✅ Bot barcha uchun ishga tushirildi.")

    elif m.text == "📵 Rejimlarni yopish":
        st.session_state.modes_status = False
        bot.send_message(m.chat.id, "📵 Tahlil rejimlar yopildi.")

    elif m.text == "📶 Rejimlarni yoqish":
        st.session_state.modes_status = True
        bot.send_message(m.chat.id, "📶 Rejimlar qayta yoqildi.")

    elif m.text == "♻️ Reboot":
        bot.send_message(m.chat.id, "♻️ Server qayta yuklanmoqda (Rerun)...")
        st.rerun()

    elif m.text == "📢 Hammaga xabar":
        bot.send_message(m.chat.id, "Xabaringizni yozing (yoki bekor qilish uchun 'bekor' deb yozing):")
        bot.register_next_step_handler(m, broadcast_to_all)

    elif m.text == "👤 UID-ga xabar":
        bot.send_message(m.chat.id, "Foydalanuvchi UID raqamini kiriting:")
        bot.register_next_step_handler(m, get_uid_step)

    elif m.text == "⬅️ Orqaga":
        bot.send_message(m.chat.id, "Asosiy menyu:", reply_markup=main_menu_markup(m.chat.id))
    
    else:
        # Agar admin rejim tugmalarini bossa
        process_standard_messages(m)

def broadcast_to_all(m):
    if m.text.lower() == 'bekor': return
    if os.path.exists(USERS_FILE):
        count = 0
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if "ID: " in line:
                    try:
                        uid = int(line.split("|")[0].replace("ID: ", "").strip())
                        bot.send_message(uid, f"📢 **ADMIN XABARI:**\n\n{m.text}", parse_mode="Markdown")
                        count += 1
                        time.sleep(0.1)
                    except: pass
        bot.send_message(m.chat.id, f"✅ {count} kishiga yuborildi.")

def get_uid_step(m):
    try:
        uid = int(m.text)
        bot.send_message(m.chat.id, f"UID: {uid}. Endi xabar matnini yuboring:")
        bot.register_next_step_handler(m, lambda msg: send_private(msg, uid))
    except:
        bot.send_message(m.chat.id, "UID raqam bo'lishi kerak.")

def send_private(m, uid):
    try:
        bot.send_message(uid, f"📩 **Admin sizga xabar yubordi:**\n\n{m.text}", parse_mode="Markdown")
        bot.send_message(m.chat.id, "✅ Xabar yuborildi.")
    except Exception as e:
        bot.send_message(m.chat.id, f"❌ Xatolik: {e}")

# --- 5. STANDART FUNKSIYALAR ---

def process_standard_messages(m):
    if m.text == "ℹ️ Yordam":
        help_command(m)
    elif m.text == "🌐 Saytga kirish (Login)":
        site_login(m)
    elif m.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"]:
        change_mode(m)

@bot.message_handler(func=lambda message: message.text == "ℹ️ Yordam")
def help_command(m):
    help_text = (
        "📖 **Botdan foydalanish qo'llanmasi:**\n\n"
        "1️⃣ **Audio yuboring:** MP3, WAV formatdagi fayl yoki Ovozli xabar tashlang.\n"
        "2️⃣ **Tilni tanlang:** Matn qaysi tilda chiqishini belgilang. Bot avtomatik tarjima qila oladi.\n"
        "3️⃣ **Formatni tanlang:** Natijani fayl (TXT) yoki to'g'ridan-to'g'ri chatda xabar ko'rinishida oling.\n\n"
        "✨ **Neon Sayt:** Har bir natija ostida 'Jonli Subtitel' tugmasi bo'ladi. Uni bossangiz, saytga o'tasiz va audioni so'zma-so'z neon effektida ko'rasiz."
    )
    bot.reply_to(m, help_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🌐 Saytga kirish (Login)")
def site_login(m):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Neon Saytni Ochish", url=WEB_APP_URL))
    bot.send_message(m.chat.id, "Bizning rasmiy veb-saytimizga quyidagi havola orqali o'ting:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"])
def change_mode(m):
    # OGOHLANTIRISH: Rejim yopiq bo'lsa
    if not st.session_state.modes_status and m.chat.id != ADMIN_ID:
        bot.send_message(m.chat.id, "⚠️ **Kechirasiz!** Hozirda ushbu rejim vaqtincha texnik ishlar sababli to'xtatilgan. Iltimos, keyinroq urinib ko'ring.")
        return

    if "Groq" in m.text:
        user_settings[m.chat.id] = "groq"
        bot.send_message(m.chat.id, "✅ **Groq Rejimi tanlandi!**\nEndi tahlillar o'ta tezkor (3-5 soniya) amalga oshiriladi.")
    else:
        user_settings[m.chat.id] = "local"
        bot.send_message(m.chat.id, "✅ **Whisper Rejimi (Basic) tanlandi!**\nEndi tahlillar ritm va pauzalarga asoslanadi (Navbat bo'lishi mumkin).")

# AUDIO QABUL QILISH
@bot.message_handler(content_types=['audio', 'voice'])
def audio_handler(m):
    # OGOHLANTIRISH: Bot to'xtatilgan bo'lsa
    if not st.session_state.bot_status and m.chat.id != ADMIN_ID:
        bot.send_message(m.chat.id, "🛑 **Bot vaqtincha to'xtatilgan.**\nHozirda yangi audiolarni qabul qila olmaymiz. Admin tomonidan xizmat tez orada qayta yoqiladi.")
        return

    if m.chat.id not in user_settings:
        user_settings[m.chat.id] = "groq"
        
    user_data[m.chat.id] = {'m_ids': [m.message_id]}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 Original", callback_data="lang_orig"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        types.InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇬🇧 Inglizcha", callback_data="lang_en")
    )
    
    mode_name = "⚡ Groq" if user_settings[m.chat.id] == "groq" else "🎧 Whisper"
    bot.send_message(m.chat.id, f"🎯 **Rejim:** {mode_name}\n🌍 **Tarjima tilini tanlang:**", reply_markup=markup)
    
    user_data[m.chat.id]['fid'] = m.audio.file_id if m.content_type == 'audio' else m.voice.file_id
    user_data[m.chat.id]['fname'] = m.audio.file_name if m.content_type == 'audio' else "Ovozli_xabar.ogg"

# TUGMALAR ISHLOVCHISI (Asil tahlil mantiqi)
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    global waiting_users
    
    # OGOHLANTIRISH
    if not st.session_state.modes_status and chat_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⚠️ Rejimlar yopiq.", show_alert=True)
        return

    if call.data.startswith("lang_"):
        user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📁 TXT Fayl", callback_data="fmt_txt"),
            types.InlineKeyboardButton("💬 Chatda olish", callback_data="fmt_chat")
        )
        bot.edit_message_text("📁 **Formatni tanlang:**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("fmt_"):
        fmt = call.data.replace("fmt_", "")
        data = user_data[chat_id]
        mode = user_settings[chat_id]
        
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Siz navbatdasiz.**\nSizdan oldin: {waiting_users-1} kishi bor.\nNavbatingiz kelishini kuting...")

        def process_task():
            global waiting_users
            with processing_lock:
                bot.edit_message_text(f"🚀 **Tahlil boshlandi!**\nModel: {mode.upper()}...", chat_id, wait_msg.message_id)
                
                try:
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    path = f"t_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(down)
                    
                    if mode == "groq":
                        with open(path, "rb") as f:
                            res = client_groq.audio.transcriptions.create(
                                file=(path, f.read()), 
                                model="whisper-large-v3-turbo", 
                                response_format="verbose_json"
                            )
                        segments = res.segments
                    else:
                        res = model_local.transcribe(path)
                        segments = res['segments']
                    
                    t_code = {"uz": "uz", "ru": "ru", "en": "en"}.get(data['lang'])
                    final_text = ""
                    
                    for s in segments:
                        tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                        orig = s['text'].strip()
                        tr = GoogleTranslator(source='auto', target=t_code).translate(orig) if t_code else None
                        final_text += f"{tm} {orig}\n" + (f" Tarjima: {tr}\n" if tr else "") + "\n"
                    
                    footer = (
                        f"\n---\n"
                        f"👤 Dasturchi: @Otavaliyev_M\n"
                        f"🤖 Telegram bot: @{bot.get_me().username}\n"
                        f"⏰ Vaqt: {get_uz_time()} (UZB)"
                    )
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("✨ JONLI SAYT", url=f"{WEB_APP_URL}/?uid={chat_id}"))

                    if fmt == "txt":
                        with open(f"result_{chat_id}.txt", "w", encoding="utf-8") as f: f.write(final_text + footer)
                        with open(f"result_{chat_id}.txt", "rb") as f:
                            bot.send_document(chat_id, f, caption=f"✅ **Natija tayyor!**\nModel: {mode.upper()}", reply_markup=markup)
                        os.remove(f"result_{chat_id}.txt")
                    else:
                        full_msg = final_text + footer
                        if len(full_msg) > 4000:
                            bot.send_message(chat_id, full_msg[:4000])
                            bot.send_message(chat_id, full_msg[4000:], reply_markup=markup)
                        else:
                            bot.send_message(chat_id, full_msg, reply_markup=markup)

                    bot.delete_message(chat_id, wait_msg.message_id)
                    if os.path.exists(path): os.remove(path)

                except Exception as e:
                    bot.send_message(chat_id, f"❌ Xatolik yuz berdi: {e}")
                finally:
                    waiting_users -= 1

        threading.Thread(target=process_task).start()

# Botni ishga tushirish (Session state orqali faqat bitta thread)
if 'bot_started' not in st.session_state:
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    st.session_state.bot_started = True
            
