import streamlit as st
import os, json, base64, pytz, time
from datetime import datetime
from deep_translator import GoogleTranslator
from groq import Groq

# --- 1. SOZLAMALAR ---
uz_tz = pytz.timezone('Asia/Tashkent')

try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
    client = Groq(api_key=GROQ_API_KEY)
except Exception:
    st.error("❌ Secrets bo'limida 'GROQ_API_KEY' topilmadi!")
    st.stop()

st.set_page_config(page_title="Neon Karaoke Web", layout="centered")

# --- 2. KUCHAYTIRILGAN NEON DIZAYN ---
st.markdown("""
<style>
    #MainMenu {visibility: hidden;} header {visibility: hidden;} footer {visibility: hidden;}
    .stDeployButton {display:none;}
    .stApp { background-color: #000000 !important; color: white !important; }
    h1, h2, h3 { text-align: center; color: #fff; text-shadow: 0 0 10px #00e5ff, 0 0 20px #00e5ff; font-weight: bold; }

    /* Neon Progress Slider */
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #00e5ff, #00ff88) !important;
        box-shadow: 0 0 20px #00e5ff;
        border-radius: 10px;
    }

    /* Fayl yuklash (Belgilar olib tashlangan) */
    [data-testid="stFileUploader"] section { 
        background-color: #000 !important; 
        border: 3px dashed #00e5ff !important; 
        border-radius: 20px;
        padding: 50px 20px !important;
    }
    [data-testid="stFileUploader"] section svg { display: none !important; }
    [data-testid="stFileUploader"] section div div { font-size: 0px !important; }

    [data-testid="stFileUploader"] button {
         background-color: #000 !important;
         color: #00e5ff !important;
         border: 2px solid #00e5ff !important;
         box-shadow: 0 0 20px #00e5ff;
         border-radius: 10px;
         font-weight: bold;
         font-size: 18px !important;
         padding: 12px 25px !important;
         display: block !important; margin: 0 auto !important;
    }
    [data-testid="stFileUploader"] button span::before { content: "FAYL TANLASH UCHUN BOSING"; visibility: visible; }
    [data-testid="stFileUploader"] button span { visibility: hidden; }

    .limit-text { color: #ff0055; text-shadow: 0 0 10px #ff0055; font-weight: bold; text-align: center; margin-bottom: 15px; }

    /* Neon Player Box */
    .neon-box { background: #050505; border: 2px solid #00e5ff; box-shadow: 0 0 25px rgba(0,229,255,0.4); border-radius: 20px; padding: 25px; margin-top: 25px; }
    
    div.stButton > button, div.stDownloadButton > button {
        background-color: #000 !important; color: #00e5ff !important; border: 2px solid #00e5ff !important;
        box-shadow: 0 0 15px #00e5ff; border-radius: 12px; font-weight: bold; width: 100%; text-transform: uppercase;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. PLAYER KOMPONENTI ---
def render_neon_player(audio_bytes, transcript_data):
    b64 = base64.b64encode(audio_bytes).decode()
    transcript_json = json.dumps(transcript_data)
    html = f"""
    <div class="neon-box">
        <h3 style="text-align:center; color:#00e5ff;">🎵 NEON KARAOKE PLAYER 🎵</h3>
        <audio id="player" controls style="width:100%; filter:invert(1) drop-shadow(0 0 8px #00e5ff); margin-bottom:15px;">
            <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
        </audio>
        <div id="lyrics" style="height:450px; overflow-y:auto; scroll-behavior:smooth; padding:15px; border-top:1px solid #333;"></div>
    </div>
    <script>
        const audio = document.getElementById('player');
        const box = document.getElementById('lyrics');
        const data = {transcript_json};
        data.forEach((line, i) => {{
            const div = document.createElement('div');
            div.id = 'L-'+i; div.style.padding='15px'; div.style.borderBottom='1px solid #222'; div.style.cursor='pointer';
            div.innerHTML = `<div style="font-size:22px; font-weight:bold; color:#444;">${{line.text}}</div>` + 
                            (line.tr ? `<div style="font-size:17px; color:#333; margin-top:5px;">${{line.tr}}</div>` : '');
            div.onclick = () => {{ audio.currentTime = line.start; audio.play(); }};
            box.appendChild(div);
        }});
        audio.ontimeupdate = () => {{
            let idx = data.findIndex(x => audio.currentTime >= x.start && audio.currentTime < x.end);
            data.forEach((_, i) => {{ 
                let el = document.getElementById('L-'+i);
                if(el) {{ el.children[0].style.color='#444'; el.style.borderLeft='none'; }}
            }});
            if(idx !== -1){{
                let el = document.getElementById('L-'+idx);
                if(el) {{ 
                    el.children[0].style.color='#00e5ff'; el.style.borderLeft='5px solid #00e5ff';
                    el.scrollIntoView({{behavior:'smooth', block:'center'}});
                }}
            }}
        }};
    </script>
    """
    st.components.v1.html(html, height=620)

# --- 4. ASOSIY WEB LOGIKA ---
st.title("🎧 NEON TRANSCRIPT WEB")
st.markdown('<p class="limit-text">⚠️ MAKSIMAL 25MB | MP3, WAV</p>', unsafe_allow_html=True)

up = st.file_uploader("", type=['mp3', 'wav'], label_visibility="collapsed")
lang = st.selectbox("Tarjima tili:", ["🇺🇿 O'zbek", "🇷🇺 Rus", "🇬🇧 Ingliz", "📄 Original"], index=3)

if st.button("🚀 TAHLILNI BOSHLASH") and up:
    path = f"t_{time.time()}.mp3"
    progress_placeholder = st.empty()
    
    try:
        with progress_placeholder.container():
            st.markdown("<p style='color:#00e5ff; text-align:center; font-weight:bold;'>⚡ Jarayon ketmoqda...</p>", unsafe_allow_html=True)
            bar = st.progress(0)
            with open(path, "wb") as f: f.write(up.getbuffer())
            
            # Slayer Progress Simulation
            for i in range(1, 41): time.sleep(0.01); bar.progress(i)
            
            # Groq API Call
            with open(path, "rb") as f:
                res = client.audio.transcriptions.create(file=(path, f.read()), model="whisper-large-v3-turbo", response_format="verbose_json")
            
            for i in range(41, 91): time.sleep(0.01); bar.progress(i)
            
            p_data = []; txt_out = ""; t_code = {"🇺🇿 O'zbek":"uz","🇷🇺 Rus":"ru","🇬🇧 Ingliz":"en"}.get(lang)
            for s in res.segments:
                tr = GoogleTranslator(source='auto', target=t_code).translate(s['text']) if t_code else None
                p_data.append({"start": s['start'], "end": s['end'], "text": s['text'].strip(), "tr": tr})
                txt_out += f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}] {s['text'].strip()}\n"
            
            bar.progress(100); time.sleep(0.5); progress_placeholder.empty()
            
            render_neon_player(up.getvalue(), p_data)
            st.download_button("📄 TXT YUKLAB OLISH", txt_out, file_name=f"{up.name}.txt")

    except Exception as e: st.error(f"Xato: {e}")
    finally:
        if os.path.exists(path): os.remove(path)

st.caption("© Shodlik (Otavaliyev_M)")
