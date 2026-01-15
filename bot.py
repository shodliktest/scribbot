import streamlit as st
import telebot
from telebot import types
import os, json, base64, pytz, threading, time
from datetime import datetime
from deep_translator import GoogleTranslator
from groq import Groq

# --- 1. SOZLAMALAR ---
uz_tz = pytz.timezone('Asia/Tashkent')
# API kalitni Secrets-dan olamiz
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    client = Groq(api_key=GROQ_API_KEY)
except:
    st.error("❌ Secrets (API kalit yoki Bot Token) topilmadi!")
    st.stop()

st.set_page_config(page_title="Neon Pro", layout="centered")

# --- 2. DIZAYN (NEON) ---
st.markdown("""
<style>
    .stApp { background-color: #000; color: white; }
    .stProgress > div > div > div > div { background-color: #00e5ff !important; box-shadow: 0 0 15px #00e5ff; }
    [data-testid="stFileUploader"] section { border: 2px dashed #00e5ff !important; background: #000; }
    [data-testid="stFileUploader"] svg { display: none; }
    [data-testid="stFileUploader"] button { background: #000 !important; color: #00e5ff !important; border: 2px solid #00e5ff !important; }
    .neon-box { border: 2px solid #00e5ff; background: #050505; border-radius: 20px; padding: 20px; }
</style>
""", unsafe_allow_html=True)

# --- 3. PLAYER ---
def render_neon_player(audio_bytes, transcript_data):
    b64 = base64.b64encode(audio_bytes).decode()
    html = f"""
    <div class="neon-box">
        <h3 style="text-align:center; color:#00e5ff;">🎵 NEON PLAYER</h3>
        <audio id="p" controls style="width:100%; filter:invert(1);"><source src="data:audio/mp3;base64,{b64}"></audio>
        <div id="l" style="height:350px; overflow-y:auto; margin-top:10px;"></div>
    </div>
    <script>
        const d = {json.dumps(transcript_data)};
        const l = document.getElementById('l');
        d.forEach((x, i) => {{
            const div = document.createElement('div');
            div.id = 'L-'+i; div.style.padding='10px'; div.style.borderBottom='1px solid #222';
            div.innerHTML = `<b style="color:#555">${{x.text}}</b>` + (x.tr ? `<p style="color:#333">${{x.tr}}</p>` : '');
            div.onclick = () => {{ document.getElementById('p').currentTime = x.start; }};
            l.appendChild(div);
        }});
    </script>
    """
    st.components.v1.html(html, height=500)

# --- 4. WEB LOGIKA ---
st.title("🎧 NEON WEB & BOT")
up = st.file_uploader("", type=['mp3'], label_visibility="collapsed")
lang = st.selectbox("Til:", ["🇺🇿 O'zbek", "🇷🇺 Rus", "🇬🇧 Ingliz", "📄 Original"], index=3)

if st.button("🚀 TAHLILNI BOSHLASH") and up:
    placeholder = st.empty()
    path = f"w_{time.time()}.mp3"
    try:
        with placeholder.container():
            st.markdown("<p style='text-align:center; color:#00e5ff;'>⚡ AI tahlil qilmoqda...</p>", unsafe_allow_html=True)
            bar = st.progress(0)
            with open(path, "wb") as f: f.write(up.getbuffer())
            bar.progress(30)
            
            # GROQ API
            with open(path, "rb") as f:
                res = client.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3-turbo", response_format="verbose_json")
            bar.progress(80)
            
            p_data = []; txt = ""; t_code = {"🇺🇿 O'zbek":"uz","🇷🇺 Rus":"ru","🇬🇧 Ingliz":"en"}.get(lang)
            for s in res.segments:
                tr = GoogleTranslator(source='auto', target=t_code).translate(s['text']) if t_code else None
                p_data.append({"start": s['start'], "text": s['text'], "tr": tr})
                txt += f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}] {s['text']}\n"
            
            bar.progress(100); time.sleep(0.5); placeholder.empty()
            render_neon_player(up.getvalue(), p_data)
            st.download_button("📄 TXT YUKLAB OLISH", txt, file_name="result.txt")
    finally:
        if os.path.exists(path): os.remove(path)

# --- 5. BACKEND BOT (GROQ API BILAN) ---
def start_bot():
    bot = telebot.TeleBot(BOT_TOKEN)

    @bot.message_handler(content_types=['audio', 'voice'])
    def handle_audio(m):
        path = f"b_{m.chat.id}.mp3"
        try:
            bot.reply_to(m, "⏳ **O'ta tezkor AI tahlil boshlandi...**")
            f_info = bot.get_file(m.audio.file_id if m.content_type=='audio' else m.voice.file_id)
            down = bot.download_file(f_info.file_path)
            with open(path, "wb") as f: f.write(down)
            
            # GROQ API BOT UCHUN
            with open(path, "rb") as f:
                res = client.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3-turbo")
            
            # Natijani yuborish
            res_txt = f"📄 **Tahlil natijasi:**\n\n{res.text}\n\n---\n👤 Shodlik Pro"
            if len(res_txt) > 4000:
                with open("res.txt", "w") as f: f.write(res_txt)
                with open("res.txt", "rb") as f: bot.send_document(m.chat.id, f)
            else:
                bot.send_message(m.chat.id, res_txt)
                
        except Exception as e: bot.send_message(m.chat.id, f"Xato: {e}")
        finally:
            if os.path.exists(path): os.remove(path)

    bot.infinity_polling()

if 'bot_on' not in st.session_state:
    st.session_state.bot_on = True
    threading.Thread(target=start_bot, daemon=True).start()
