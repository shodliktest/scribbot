import streamlit as st
import telebot
from telebot import types
import whisper
import os, pytz, threading, json
from datetime import datetime

# --- 1. SOZLAMALAR ---
# ⚠️ BU YERGA BIRINCHI (WEB) SAYTINGIZ LINKINI QO'YING!
WEB_APP_URL = "https://shodlik1transcript.streamlit.app"
uz_tz = pytz.timezone('Asia/Tashkent')

@st.cache_resource
def load_model():
    # RAMni tejash uchun 'tiny' model
    return whisper.load_model("tiny")

model = load_model()

try:
    bot = telebot.TeleBot(st.secrets["BOT_TOKEN"])
except:
    st.error("Secrets-da BOT_TOKEN topilmadi!")
    st.stop()

# Server yuzasi (oddiy status sahifasi)
st.set_page_config(page_title="Bot Server", page_icon="🤖")
st.title("🤖 Neon Karaoke Bot Server")
st.markdown(f"**Holat:** 🟢 Online")
st.markdown(f"**Ulanish:** [Asosiy Sayt]({WEB_APP_URL})")

# --- 2. BOT MANTIQI ---
def run_bot():
    @bot.message_handler(commands=['start'])
    def start_msg(m):
        # Saytga ID bilan link beramiz
        link = f"{WEB_APP_URL}/?uid={m.chat.id}"
        
        menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        menu.add(types.KeyboardButton("🌐 Saytga kirish (Login)"), types.KeyboardButton("ℹ️ Yordam"))
        
        inline_markup = types.InlineKeyboardMarkup()
        inline_markup.add(types.InlineKeyboardButton("🚀 Neon Saytni Ochish", url=link))
        
        bot.send_message(m.chat.id, 
                         f"👋 **Assalomu alaykum!**\n\n"
                         f"Menga audio yuboring yoki Neon Playerdan foydalanish uchun saytga o'ting:", 
                         reply_markup=menu)
        bot.send_message(m.chat.id, "👇 Saytga kirish tugmasi:", reply_markup=inline_markup)

    @bot.message_handler(func=lambda message: message.text == "🌐 Saytga kirish (Login)")
    def open_site(m):
        link = f"{WEB_APP_URL}/?uid={m.chat.id}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🚀 Saytni Ochish", url=link))
        bot.reply_to(m, "Sizning shaxsiy havolangiz:", reply_markup=markup)

    @bot.message_handler(content_types=['audio', 'voice'])
    def handle_audio(m):
        path = f"bot_tmp_{m.chat.id}_{int(datetime.now().timestamp())}.mp3"
        try:
            bot.reply_to(m, "⏳ Tahlil qilinmoqda... (Server 2)")
            
            fid = m.audio.file_id if m.content_type=='audio' else m.voice.file_id
            f_info = bot.get_file(fid)
            down = bot.download_file(f_info.file_path)
            
            with open(path, "wb") as f: f.write(down)
            
            # Whisper tahlil
            result = model.transcribe(path)
            
            txt = f"TRANSKRIPSIYA (BOT)\nSana: {datetime.now(uz_tz).strftime('%Y-%m-%d %H:%M')}\n\n"
            for s in result['segments']:
                tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                txt += f"{tm} {s['text'].strip()}\n"
            
            txt += "\n---\n© Shodlik (Otavaliyev_M)"
            
            # Saytga o'tish tugmasi
            link = f"{WEB_APP_URL}/?uid={m.chat.id}"
            mark = types.InlineKeyboardMarkup()
            mark.add(types.InlineKeyboardButton("🎵 Saytda Pleyerda ochish", url=link))
            
            with open("bot_res.txt", "w", encoding="utf-8") as f: f.write(txt)
            with open("bot_res.txt", "rb") as f:
                bot.send_document(m.chat.id, f, caption="✅ Tahlil tayyor!", reply_markup=mark)
            
            os.remove("bot_res.txt")
        except Exception as e:
            bot.send_message(m.chat.id, f"Xato yuz berdi: {e}")
        finally:
            if os.path.exists(path): os.remove(path)

    bot.infinity_polling()

# Botni orqa fonda ishga tushirish
if 'bot_thread' not in st.session_state:
    st.session_state['bot_thread'] = True
    t = threading.Thread(target=run_bot, daemon=True)
    t.start()
