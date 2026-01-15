import streamlit as st
import telebot
from telebot import types
import whisper # Groq o'rniga Whisperga qaytdik
import os
import json
import threading
import pytz
from datetime import datetime
from deep_translator import GoogleTranslator
import time

# --- 1. SOZLAMALAR ---
WEB_APP_URL = "https://shodlik1transcript.streamlit.app"
uz_tz = pytz.timezone('Asia/Tashkent')

try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
except:
    st.error("❌ Secrets-da BOT_TOKEN topilmadi!")
    st.stop()

# Mahalliy modelni yuklash (RAM uchun 'base' yoki 'tiny' tavsiya etiladi)
@st.cache_resource
def load_ai_model():
    return whisper.load_model("base")

model = load_ai_model()
bot = telebot.TeleBot(BOT_TOKEN)

# Streamlit interfeysi (Server holati uchun)
st.set_page_config(page_title="Bot Server", page_icon="🤖")
st.title("🤖 Neon Karaoke Bot Server")
st.success("Bot tizimi muvaffaqiyatli ishga tushdi!")
st.info(f"Bot manzili: @{bot.get_me().username}")

user_data = {}

# --- 2. YORDAMCHI FUNKSIYALAR ---
def get_uz_time():
    return datetime.now(uz_tz).strftime('%H:%M:%S')

def delete_user_messages(chat_id, message_ids):
    for m_id in message_ids:
        try: bot.delete_message(chat_id, m_id)
        except: pass

# --- 3. BOT MANTIQI ---

@bot.message_handler(commands=['start'])
def welcome(m):
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
    
    msg_text = (
        "👋 **Assalomu alaykum!**\n\n"
        "Men audio fayllarni matnga aylantirib beruvchi aqlli botman.\n\n"
        "**Imkoniyatlarim:**\n"
        "✅ Audioni matnga aylantirish (Transcription)\n"
        "✅ Matnni boshqa tillarga tarjima qilish\n"
        "✅ Saytda Neon Player orqali ko'rish\n"
        "✅ Har xil formatda natija olish\n\n"
        "🚀 Boshlash uchun menga **audio yoki ovozli xabar** yuboring!"
    )
    bot.send_message(m.chat.id, msg_text, parse_mode="Markdown", reply_markup=menu)

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
    user_data[m.chat.id] = {'m_ids': [m.message_id]}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📄 Original", callback_data="lang_orig"),
        types.InlineKeyboardButton("🇺🇿 O'zbekcha", callback_data="lang_uz"),
        types.InlineKeyboardButton("🇷🇺 Ruscha", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇬🇧 Inglizcha", callback_data="lang_en")
    )
    
    msg = bot.send_message(m.chat.id, "🛑 **DIQQAT:** Tilni tanlash orqali matn avtomatik tarjima qilinadi. Kerakli tilni tanlang:", 
                           parse_mode="Markdown", reply_markup=markup)
    user_data[m.chat.id]['m_ids'].append(msg.message_id)
    
    fid = m.audio.file_id if m.content_type == 'audio' else m.voice.file_id
    user_data[m.chat.id]['fid'] = fid
    user_data[m.chat.id]['fname'] = m.audio.file_name if m.content_type == 'audio' else "Ovozli_xabar.ogg"

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    
    if call.data.startswith("lang_"):
        lang = call.data.replace("lang_", "")
        user_data[chat_id]['lang'] = lang
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📁 TXT Fayl", callback_data="fmt_txt"),
            types.InlineKeyboardButton("💬 Chatda olish", callback_data="fmt_chat")
        )
        msg = bot.edit_message_text("Qanday formatda olishni xohlaysiz?", chat_id, call.message.message_id, reply_markup=markup)

    elif call.data.startswith("fmt_"):
        fmt = call.data.replace("fmt_", "")
        lang = user_data[chat_id]['lang']
        fid = user_data[chat_id]['fid']
        
        delete_user_messages(chat_id, user_data[chat_id]['m_ids'])
        
        wait_msg = bot.send_message(chat_id, "⏳ **Tahlil ketmoqda...**", parse_mode="Markdown")
        
        try:
            f_info = bot.get_file(fid)
            down = bot.download_file(f_info.file_path)
            path = f"tmp_{chat_id}.mp3"
            with open(path, "wb") as f: f.write(down)
            
            # --- MAHALLIY WHISPER TAHLIL JARAYONI ---
            result = model.transcribe(path)
            
            t_code = {"uz": "uz", "ru": "ru", "en": "en"}.get(lang)
            final_text = ""
            for s in result['segments']:
                tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                orig = s['text'].strip()
                if t_code:
                    trans = GoogleTranslator(source='auto', target=t_code).translate(orig)
                    final_text += f"{tm} {orig}\n Tarjima: {trans}\n\n"
                else:
                    final_text += f"{tm} {orig}\n\n"
            
            footer = (
                f"\n---\n"
                f"👤 Dasturchi: @Otavaliyev_M\n"
                f"🤖 Bot: @{bot.get_me().username}\n"
                f"⏰ Vaqt: {get_uz_time()} (UZB)"
            )
            
            site_link = f"{WEB_APP_URL}/?uid={chat_id}"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✨ JONLI SUBTITEL (SAYT)", url=site_link))

            if fmt == "txt":
                with open("res.txt", "w", encoding="utf-8") as f: f.write(final_text + footer)
                with open("res.txt", "rb") as f:
                    bot.send_document(chat_id, f, caption=f"✅ Natija tayyor!\nFayl: {user_data[chat_id]['fname']}", reply_markup=markup)
                os.remove("res.txt")
            else:
                if len(final_text + footer) > 4000:
                    bot.send_message(chat_id, final_text[:4000] + "...")
                    bot.send_message(chat_id, footer, reply_markup=markup)
                else:
                    bot.send_message(chat_id, final_text + footer, reply_markup=markup)

            bot.delete_message(chat_id, wait_msg.message_id)
            if os.path.exists(path): os.remove(path)
            
        except Exception as e:
            bot.send_message(chat_id, f"❌ Xatolik yuz berdi: {e}")

# Botni alohida oqimda ishga tushirish
def run_polling():
    bot.infinity_polling()

if 'bot_thread' not in st.session_state:
    st.session_state['bot_thread'] = True
    threading.Thread(target=run_polling, daemon=True).start()

st.markdown('<div style="position:fixed; bottom:0; right:0; padding:10px; color:lime;">● Bot Status: Active (Whisper Local)</div>', unsafe_allow_html=True)
