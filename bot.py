import streamlit as st
import telebot
from telebot import types
import whisper
from groq import Groq
import os, json, threading, pytz, torch, time
from datetime import datetime
from deep_translator import GoogleTranslator

# --- 1. GLOBAL SOZLAMALAR ---
processing_lock = threading.Lock()
waiting_users = 0

uz_tz = pytz.timezone('Asia/Tashkent')
WEB_APP_URL = "https://shodlik1transcript.streamlit.app"

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    st.error("❌ Secrets-da BOT_TOKEN yoki GROQ_API_KEY topilmadi!")
    st.stop()

# MODELLARNI YUKLASH
client_groq = Groq(api_key=GROQ_API_KEY)
@st.cache_resource
def load_local_whisper():
    return whisper.load_model("base")

model_local = load_local_whisper()
bot = telebot.TeleBot(BOT_TOKEN)

# Streamlit UI
st.set_page_config(page_title="Neon Hybrid Server", layout="centered")
st.title("🤖 Neon Hybrid Bot Server")

# Foydalanuvchi sozlamalari (RAMni tejash uchun lug'atdan foydalanamiz)
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
    if m.chat.id not in user_settings:
        user_settings[m.chat.id] = "groq" # Default rejim
        
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
    "💡 *Hozirgi tanlangan rejim:* **" + user_settings[m.chat.id].upper() + "**\n"
    "*(Rejimni pastdagi menyu tugmalari orqali xohlagan vaqtda o'zgartirishingiz mumkin)*"
)
    bot.send_message(m.chat.id, msg_text, parse_mode="Markdown", reply_markup=main_menu_markup())

# REJIMLARNI O'ZGARTIRISH
@bot.message_handler(func=lambda message: message.text in ["⚡ Groq Rejimi", "🎧 Whisper Rejimi"])
def change_mode(m):
    if "Groq" in m.text:
        user_settings[m.chat.id] = "groq"
        bot.send_message(m.chat.id, "✅ **Groq Rejimi tanlandi!** (Tezkor tahlil)")
    else:
        user_settings[m.chat.id] = "local"
        bot.send_message(m.chat.id, "✅ **Whisper Rejimi tanlandi!** (Ritmik tahlil)")

@bot.message_handler(content_types=['audio', 'voice'])
def audio_handler(m):
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
    
    msg = bot.send_message(m.chat.id, f"🎯 **Rejim:** {user_settings[m.chat.id].upper()}\n🌍 **Tilni tanlang:**", 
                           reply_markup=markup)
    user_data[m.chat.id]['m_ids'].append(msg.message_id)
    user_data[m.chat.id]['fid'] = m.audio.file_id if m.content_type == 'audio' else m.voice.file_id
    user_data[m.chat.id]['fname'] = m.audio.file_name if m.content_type == 'audio' else "Ovozli_xabar.ogg"

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    global waiting_users
    
    if call.data.startswith("lang_"):
        user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        # REJIMNI QAYTA SO'RAMAYMIZ! To'g'ridan-to'g'ri formatga o'tamiz.
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
        
        for mid in data['m_ids']:
            try: bot.delete_message(chat_id, mid)
            except: pass
        
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Navbatdasiz: {waiting_users-1} kishi.**\nTahlil boshlanishini kuting...")

        def process_task():
            global waiting_users
            with processing_lock:
                bot.edit_message_text(f"🚀 **Tahlil boshlandi!**\nModel: {mode.upper()}", chat_id, wait_msg.message_id)
                
                try:
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    path = f"t_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(down)
                    
                    # 1. TAHLIL QILISH
                    if mode == "groq":
                        with open(path, "rb") as f:
                            res = client_groq.audio.transcriptions.create(
                                file=(path, f.read()), 
                                model="whisper-large-v3-turbo",
                                response_format="verbose_json" # Vaqt belgilarini olish uchun
                            )
                        segments = res.segments
                    else:
                        res = model_local.transcribe(path)
                        segments = res['segments']
                    
                    # 2. MATNNI SHAKLLANTIRISH (TIMESTAMPS BILAN)
                    t_code = {"uz": "uz", "ru": "ru", "en": "en"}.get(data['lang'])
                    final_text = ""
                    for s in segments:
                        # [00:00] formatidagi vaqt
                        tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                        orig = s['text'].strip()
                        tr = GoogleTranslator(source='auto', target=t_code).translate(orig) if t_code else None
                        final_text += f"{tm} {orig}\n" + (f" Tarjima: {tr}\n" if tr else "") + "\n"
                    
                    # 3. PECHAT (IMZO)
                    pechat = (
                        f"\n---\n"
                        f"👤 Dasturchi: @Otavaliyev_M\n"
                        f"🤖Telegram bot: @{bot.get_me().username}\n"
                        f"⏰ Vaqt: {get_uz_time()} (UZB)"
                    )
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("✨ JONLI SAYT", url=f"{WEB_APP_URL}/?uid={chat_id}"))

                    # Chatga va Faylga pechat bilan yuborish
                    if fmt == "txt":
                        with open(f"r_{chat_id}.txt", "w", encoding="utf-8") as f: f.write(final_text + pechat)
                        with open(f"r_{chat_id}.txt", "rb") as f:
                            bot.send_document(chat_id, f, caption=f"✅ Natija tayyor!", reply_markup=markup)
                        os.remove(f"r_{chat_id}.txt")
                    else:
                        full_msg = final_text + pechat
                        if len(full_msg) > 4000:
                            bot.send_message(chat_id, full_msg[:4000])
                            bot.send_message(chat_id, full_msg[4000:], reply_markup=markup)
                        else:
                            bot.send_message(chat_id, full_msg, reply_markup=markup)

                    bot.delete_message(chat_id, wait_msg.message_id)
                    if os.path.exists(path): os.remove(path)

                except Exception as e:
                    bot.send_message(chat_id, f"❌ Xatolik: {e}")
                finally:
                    waiting_users -= 1

        threading.Thread(target=process_task).start()

# Start
threading.Thread(target=bot.infinity_polling, daemon=True).start()
