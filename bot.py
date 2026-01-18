import streamlit as st
import telebot
from telebot import types
import whisper
from groq import Groq
import os, json, threading, pytz, torch, time
from datetime import datetime
from deep_translator import GoogleTranslator
import streamlit as st

params = st.query_params

if params.get("cron") == "1":
    st.markdown("OK")
    st.stop()
# --- 1. GLOBAL SOZLAMALAR ---
# Navbat uchun qulf va hisoblagich
processing_lock = threading.Lock()
waiting_users = 0

uz_tz = pytz.timezone('Asia/Tashkent')
WEB_APP_URL = "https://https://script1232.streamlit.app" # O'zingizning havolangiz

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    st.error("❌ Secrets-da BOT_TOKEN yoki GROQ_API_KEY topilmadi!")
    st.stop()

# MODELLARNI YUKLASH
# Groq mijozi
client_groq = Groq(api_key=GROQ_API_KEY)

# Local Whisper (RAMni tejash uchun keshlanadi)
@st.cache_resource
def load_local_whisper():
    return whisper.load_model("base")

model_local = load_local_whisper()
bot = telebot.TeleBot(BOT_TOKEN)

# Streamlit UI (Server tirikligini ko'rsatish uchun)
st.set_page_config(page_title="Neon Hybrid Server", layout="centered")
st.title("🤖 Neon Hybrid Bot Server")
st.success("Server va Bot ishlamoqda!")
st.info("Ushbu sahifa botning 'miyasi' hisoblanadi. Uni yopmang.")

# Foydalanuvchi sozlamalari (Rejimni eslab qolish uchun)
user_settings = {} 
user_data = {}

# --- 2. YORDAMCHI FUNKSIYALAR ---
def get_uz_time():
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def main_menu_markup():
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(types.KeyboardButton("⚡ Groq Rejimi"), types.KeyboardButton("🎧 Whisper Rejimi"))
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    return menu

# --- 3. BOT MANTIQI ---

@bot.message_handler(commands=['start'])
def welcome(m):
    # Agar foydalanuvchi yangi bo'lsa, default Groq qo'yamiz
    if m.chat.id not in user_settings:
        user_settings[m.chat.id] = "groq"
    
    current_mode = "⚡ Groq (Tezkor)" if user_settings[m.chat.id] == "groq" else "🎧 Whisper (Basic)"
    
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
    bot.send_message(m.chat.id, msg_text, parse_mode="Markdown", reply_markup=main_menu_markup())

# YORDAM BO'LIMI
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

# SAYTGA KIRISH
@bot.message_handler(func=lambda message: message.text == "🌐 Saytga kirish (Login)")
def site_login(m):
    # Toza link beramiz
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Neon Saytni Ochish", url=WEB_APP_URL))
    bot.send_message(m.chat.id, "Bizning rasmiy veb-saytimizga quyidagi havola orqali o'ting:", reply_markup=markup)

# REJIMLARNI O'ZGARTIRISH
@bot.message_handler(func=lambda message: message.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"])
def change_mode(m):
    if "Groq" in m.text:
        user_settings[m.chat.id] = "groq"
        bot.send_message(m.chat.id, "✅ **Groq Rejimi tanlandi!**\nEndi tahlillar o'ta tezkor (3-5 soniya) amalga oshiriladi.")
    else:
        user_settings[m.chat.id] = "local"
        bot.send_message(m.chat.id, "✅ **Whisper Rejimi (Basic) tanlandi!**\nEndi tahlillar ritm va pauzalarga asoslanadi (Navbat bo'lishi mumkin).")

# AUDIO QABUL QILISH
@bot.message_handler(content_types=['audio', 'voice'])
def audio_handler(m):
    # Agar rejim tanlanmagan bo'lsa, default Groq
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

# TUGMALAR ISHLOVCHISI
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    global waiting_users
    
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
        
        # Eski xabarlarni tozalashga harakat qilamiz
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        # NAVBATGA OLISH
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Siz navbatdasiz.**\nSizdan oldin: {waiting_users-1} kishi bor.\nNavbatingiz kelishini kuting...")

        def process_task():
            global waiting_users
            # LOCK orqali faqat bitta jarayonni o'tkazish
            with processing_lock:
                bot.edit_message_text(f"🚀 **Tahlil boshlandi!**\nModel: {mode.upper()}...", chat_id, wait_msg.message_id)
                
                try:
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    path = f"t_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(down)
                    
                    # --- AI TAHLIL ---
                    if mode == "groq":
                        # Groq: Tezkor va Timestamp bilan
                        with open(path, "rb") as f:
                            res = client_groq.audio.transcriptions.create(
                                file=(path, f.read()), 
                                model="whisper-large-v3-turbo", 
                                response_format="verbose_json"
                            )
                        segments = res.segments
                    else:
                        # Local: Basic (Ritmik)
                        res = model_local.transcribe(path)
                        segments = res['segments']
                    
                    # --- MATN FORMATLASH ---
                    t_code = {"uz": "uz", "ru": "ru", "en": "en"}.get(data['lang'])
                    final_text = ""
                    
                    for s in segments:
                        tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                        orig = s['text'].strip()
                        tr = GoogleTranslator(source='auto', target=t_code).translate(orig) if t_code else None
                        final_text += f"{tm} {orig}\n" + (f" Tarjima: {tr}\n" if tr else "") + "\n"
                    
                    # --- PECHAT (IMZO) ---
                    footer = (
                        f"\n---\n"
                        f"👤 Dasturchi: @Otavaliyev_M\n"
                        f"🤖 Telegram bot: @{bot.get_me().username}\n"
                        f"⏰ Vaqt: {get_uz_time()} (UZB)"
                    )
                    
                    # Saytga havola
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("✨ JONLI SAYT", url=f"{WEB_APP_URL}/?uid={chat_id}"))

                    # Natijani yuborish
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

# Botni ishga tushirish
threading.Thread(target=bot.infinity_polling, daemon=True).start()


