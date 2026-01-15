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
st.success("Server faol. Navbat tizimi va Hybrid rejim yoqilgan!")

# Foydalanuvchi sozlamalari (Vaqtinchalik xotira)
user_settings = {} # Har bir user uchun tanlangan modelni saqlaydi
user_data = {}     # Tahlil jarayoni uchun ma'lumotlar

# --- 2. YORDAMCHI FUNKSIYALAR ---
def get_uz_time():
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def main_menu_markup():
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Yangi model tanlash tugmalari menyuga qo'shildi
    menu.add(
        types.KeyboardButton("⚡ Groq Rejimi"), 
        types.KeyboardButton("🎧 Whisper Rejimi")
    )
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    return menu

# --- 3. BOT MANTIQI ---

@bot.message_handler(commands=['start'])
def welcome(m):
    # Modelni defalt holatda Groq qilib belgilaymiz
    if m.chat.id not in user_settings:
        user_settings[m.chat.id] = "groq"
        
    msg_text = (
        "👋 **Assalomu alaykum!**\n\n"
        "Men audio fayllarni matnga aylantirib beruvchi aqlli botman.\n\n"
        "**Imkoniyatlarim:**\n"
        "✅ Audioni matnga aylantirish (Transcription)\n"
        "✅ Matnni boshqa tillarga tarjima qilish\n"
        "✅ Saytda Neon Player orqali ko'rish\n"
        "✅ Har xil formatda natija olish\n\n"
        "🚀 Boshlash uchun menga **audio yoki ovozli xabar** yuboring!\n\n"
        "💡 *Hozirgi tanlangan rejim:* **" + user_settings[m.chat.id].upper() + "**"
    )
    bot.send_message(m.chat.id, msg_text, parse_mode="Markdown", reply_markup=main_menu_markup())

@bot.message_handler(func=lambda message: message.text == "⚡ Groq Rejimi")
def set_groq(m):
    user_settings[m.chat.id] = "groq"
    bot.send_message(m.chat.id, "✅ **Groq Rejimi yoqildi!**\nEndi tahlillar o'ta tezkor (3-5 soniya) amalga oshiriladi.", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🎧 Whisper Rejimi")
def set_whisper(m):
    user_settings[m.chat.id] = "local"
    bot.send_message(m.chat.id, "✅ **Whisper Rejimi (Basic) yoqildi!**\nEndi tahlillar ritm va pauzalarga asoslanadi (Navbat bo'lishi mumkin).", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "ℹ️ Yordam")
def help_command(m):
    help_text = (
        "📖 **Botdan foydalanish qo'llanmasi:**\n\n"
        "1️⃣ **Audio yuboring:** MP3 yoki Ovozli xabar tashlang.\n"
        "2️⃣ **Tilni tanlang:** Matn qaysi tilda chiqishini belgilang.\n"
        "3️⃣ **Formatni tanlang:** Natijani fayl (TXT) yoki to'g'ridan-to'g'ri chatda xabar ko'rinishida oling.\n\n"
        "✨ **Neon Sayt:** Har bir natija ostida 'Jonli Subtitel' tugmasi bo'ladi. Uni bossangiz, saytga o'tasiz va audioni so'zma-so'z neon effektida ko'rasiz."
    )
    bot.reply_to(m, help_text, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "🌐 Saytga kirish (Login)")
def site_login(m):
    link = f"{WEB_APP_URL}/?uid={m.chat.id}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚀 Neon Saytni Ochish", url=link))
    bot.send_message(m.chat.id, "Sizning shaxsiy havolangiz orqali sayt sizni taniydi va natijalarni avtomatik yuboradi:", reply_markup=markup)

@bot.message_handler(content_types=['audio', 'voice'])
def audio_handler(m):
    # Foydalanuvchi tanlagan modelni tekshirish
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
    
    # Model ma'lumotini xabarga qo'shamiz
    mode_info = "⚡ Groq" if user_settings[m.chat.id] == "groq" else "🎧 Whisper"
    msg = bot.send_message(m.chat.id, f"🎯 **Rejim:** {mode_info}\n🛑 **DIQQAT:** Tilni tanlash orqali matn avtomatik tarjima qilinadi. Kerakli tilni tanlang:", 
                           parse_mode="Markdown", reply_markup=markup)
    user_data[m.chat.id]['m_ids'].append(msg.message_id)
    
    user_data[m.chat.id]['fid'] = m.audio.file_id if m.content_type == 'audio' else m.voice.file_id
    user_data[m.chat.id]['fname'] = m.audio.file_name if m.content_type == 'audio' else "Ovozli_xabar.ogg"

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    global waiting_users
    
    if call.data.startswith("lang_"):
        user_data[chat_id]['lang'] = call.data.replace("lang_", "")
        
        # Modelni tahlil paytida ham o'zgartirish imkoniyati (Original talabingiz bo'yicha)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("⚡ Groq Cloud (Tezkor)", callback_data="mod_groq"),
            types.InlineKeyboardButton("🎧 Whisper Local (Ritmik)", callback_data="mod_local")
        )
        bot.edit_message_text("🤖 **Qaysi AI modelidan foydalanamiz?**", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("mod_"):
        user_settings[chat_id] = call.data.replace("mod_", "")
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📁 TXT Fayl", callback_data="fmt_txt"),
            types.InlineKeyboardButton("💬 Chatda olish", callback_data="fmt_chat")
        )
        bot.edit_message_text("Qanday formatda olishni xohlaysiz?", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("fmt_"):
        fmt = call.data.replace("fmt_", "")
        data = user_data[chat_id]
        current_model = user_settings[chat_id]
        
        # Xabarlarni o'chirish
        for mid in data['m_ids']:
            try: bot.delete_message(chat_id, mid)
            except: pass
        try: bot.delete_message(chat_id, call.message.message_id)
        except: pass
        
        waiting_users += 1
        wait_msg = bot.send_message(chat_id, f"⏳ **Navbatdasiz: {waiting_users-1} kishi bor.**\nTahlil boshlanishi bilan sizga xabar beraman...")

        def process_task():
            global waiting_users
            with processing_lock:
                bot.edit_message_text(f"🚀 **Tahlil boshlandi!**\nModel: {current_model.upper()}\nKutib turing...", chat_id, wait_msg.message_id)
                
                try:
                    f_info = bot.get_file(data['fid'])
                    down = bot.download_file(f_info.file_path)
                    path = f"t_{chat_id}.mp3"
                    with open(path, "wb") as f: f.write(down)
                    
                    if current_model == "groq":
                        with open(path, "rb") as f:
                            res = client_groq.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3-turbo")
                        segments = [{"start": 0, "text": res.text}]
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
                    
                    footer = f"\n---\n👤 Shodlik | 🤖 AI: {current_model.upper()} | ⏰ {get_uz_time()}"
                    
                    markup = types.InlineKeyboardMarkup()
                    markup.add(types.InlineKeyboardButton("✨ JONLI SUBTITEL (SAYT)", url=f"{WEB_APP_URL}/?uid={chat_id}"))

                    if fmt == "txt":
                        with open(f"r_{chat_id}.txt", "w", encoding="utf-8") as f: f.write(final_text + footer)
                        with open(f"r_{chat_id}.txt", "rb") as f:
                            bot.send_document(chat_id, f, caption=f"✅ Natija tayyor!\nFayl: {data['fname']}", reply_markup=markup)
                        os.remove(f"r_{chat_id}.txt")
                    else:
                        if len(final_text + footer) > 4000:
                            bot.send_message(chat_id, final_text[:4000] + "...")
                            bot.send_message(chat_id, footer, reply_markup=markup)
                        else:
                            bot.send_message(chat_id, final_text + footer, reply_markup=markup)

                    bot.delete_message(chat_id, wait_msg.message_id)
                    if os.path.exists(path): os.remove(path)

                except Exception as e:
                    bot.send_message(chat_id, f"❌ Xatolik: {e}")
                finally:
                    waiting_users -= 1

        threading.Thread(target=process_task).start()

# Polling
if 'bot_started' not in st.session_state:
    st.session_state.bot_started = True
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
