import streamlit as st
import streamlit.components.v1 as components
import os, json, base64, time
from deep_translator import GoogleTranslator
from groq import Groq

# --- 1. SOZLAMALAR ---
st.set_page_config(page_title="Neon Karaoke Pro", layout="centered", initial_sidebar_state="collapsed")

# --- 2. STEALTH MODE (Streamlitni yashirish) ---
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stDeployButton {display: none;}
        [data-testid="stStatusWidget"] {visibility: hidden;}
        [data-testid="stHeader"] {display: none;}
        [data-testid="stToolbar"] {display: none;}
        
        .block-container {
            padding-top: 0rem !important;
            padding-bottom: 0rem !important;
            margin-top: 20px !important;
        }
        div[data-testid="stDecoration"] { display: none; }
        .stApp { background-color: #000000; color: white; }
    </style>
""", unsafe_allow_html=True)

# --- 3. NEON DIZAYN ---
st.markdown("""
<style>
    h1, h2, h3, p {
        color: #fff !important;
        text-align: center;
        text-shadow: 0 0 10px #00e5ff, 0 0 20px #00e5ff;
        font-family: sans-serif;
    }
    [data-testid="stFileUploader"] {
        background-color: #050505;
        border: 2px dashed #00e5ff;
        border-radius: 20px;
        padding: 20px;
        margin-top: 20px;
    }
    [data-testid="stFileUploader"] section > div { color: #00e5ff !important; }
    [data-testid="stFileUploader"] button {
        background-color: #000; color: #00e5ff; border: 1px solid #00e5ff;
    }
    .stButton > button {
        background: linear-gradient(45deg, #00e5ff, #00ff88);
        color: black !important;
        font-weight: bold;
        border: none;
        border-radius: 15px;
        height: 50px;
        font-size: 18px;
        box-shadow: 0 0 15px #00e5ff;
        margin-top: 10px;
    }
    .stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 0 25px #00ff88;
    }
    [data-testid="stSelectbox"] label { color: #00e5ff !important; }
    div[data-baseweb="select"] > div {
        background-color: #111; border: 1px solid #00e5ff; color: white;
    }
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #00e5ff, #00ff88);
        box-shadow: 0 0 10px #00e5ff;
    }
</style>
""", unsafe_allow_html=True)

# API Kalit
api_key = st.secrets.get("GROQ_API_KEY") or os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key) if api_key else None

# --- 4. INTERFEYS ---

st.title("  SHodlik AI PRO ")
st.markdown("<p style='margin-bottom: 30px; opacity: 0.7;'>AI Smart Synchronization</p>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Musiqani tanlang (MP3/WAV)", type=['mp3', 'wav'])

col1, col2 = st.columns([2, 1])
with col1:
    lang = st.selectbox("Tarjima tili:", ["„ Original", " O'zbek", " Rus", " Ingliz"])
with col2:
    st.write("") 
    st.write("") 

if uploaded_file:
    if st.button("TAHLILNI BOSHLASH"):
        if not client:
            st.error("API kalit topilmadi!")
        else:
            try:
                progress_text = "Jarayon boshlanmoqda..."
                my_bar = st.progress(0, text=progress_text)

                # 1. Yuklash
                my_bar.progress(10, text="Fayl serverga yuklanmoqda...")
                temp_path = f"temp_{int(time.time())}.mp3"
                with open(temp_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                
                # 2. Transkripsiya
                my_bar.progress(40, text="Sun'iy intellekt eshitmoqda...")
                with open(temp_path, "rb") as file:
                    trans = client.audio.transcriptions.create(
                        file=(temp_path, file.read()),
                        model="whisper-large-v3-turbo",
                        response_format="verbose_json",
                    )
                
                # 3. So'zlarni yig'ish
                my_bar.progress(70, text="Gaplar ajratilmoqda...")
                all_words_with_time = []
                for seg in trans.segments:
                    words = seg['text'].strip().split()
                    if not words: continue
                    dur = (seg['end'] - seg['start']) / len(words)
                    for i, w in enumerate(words):
                        all_words_with_time.append({
                            "text": w,
                            "start": seg['start'] + (i * dur),
                            "end": seg['start'] + ((i + 1) * dur)
                        })
                
                # 4. Katta harf mantiqi
                final_lines = []
                current_line_words = []
                line_start_time = 0.0
                
                if all_words_with_time:
                    line_start_time = all_words_with_time[0]['start']

                for i, item in enumerate(all_words_with_time):
                    word = item['text']
                    clean_word = word.strip().replace('"', '').replace('(', '')
                    
                    if i > 0 and clean_word and clean_word[0].isupper():
                        full_text = " ".join([w['text'] for w in current_line_words])
                        
                        t_code = {"„ Original": None, " O'zbek":"uz"," Rus":"ru"," Ingliz":"en"}.get(lang)
                        tr = None
                        if t_code:
                            try:
                                tr = GoogleTranslator(source='auto', target=t_code).translate(full_text)
                            except: pass

                        final_lines.append({
                            "start": line_start_time,
                            "end": item['start'],
                            "text": full_text,
                            "tr": tr
                        })
                        
                        current_line_words = [item]
                        line_start_time = item['start']
                    else:
                        current_line_words.append(item)
                
                if current_line_words:
                    full_text = " ".join([w['text'] for w in current_line_words])
                    t_code = {"“„ Original": None, " O'zbek":"uz"," Rus":"ru"," Ingliz":"en"}.get(lang)
                    tr = GoogleTranslator(source='auto', target=t_code).translate(full_text) if t_code else None
                    
                    final_lines.append({
                        "start": line_start_time,
                        "end": current_line_words[-1]['end'],
                        "text": full_text,
                        "tr": tr
                    })

                # 5. Tayyor
                my_bar.progress(100, text="  Tayyor! ")
                time.sleep(0.5)
                my_bar.empty()

                # 6. PLAYER HTML (Avto-Skroll qo'shildi)
                audio_b64 = base64.b64encode(uploaded_file.getvalue()).decode()
                json_data = json.dumps(final_lines)
                
                player_html = f"""
                <div id="main-player-box" style="background: #080808; border: 2px solid #00e5ff; border-radius: 20px; padding: 20px; box-shadow: 0 0 20px rgba(0,229,255,0.2); margin-top: 20px;">
                    <audio id="player" controls style="width: 100%; filter: invert(1); margin-bottom: 20px;">
                        <source src="data:audio/mp3;base64,{audio_b64}" type="audio/mp3">
                    </audio>
                    <div id="lyrics" style="height: 450px; overflow-y: auto; padding: 10px; scroll-behavior: smooth;"></div>
                </div>
                
                <script>
                    const data = {json_data};
                    const container = document.getElementById('lyrics');
                    const audio = document.getElementById('player');
                    
                    // --- AVTO SKROLL VA PLAYERGA YURISH ---
                    // Sahifa yuklangandan keyin player markazga keladi
                    setTimeout(() => {{
                        const box = document.getElementById('main-player-box');
                        if(box) {{
                            box.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}
                    }}, 500);

                    // --- MATNLARNI CHIZISH ---
                    data.forEach((line, i) => {{
                        const div = document.createElement('div');
                        div.id = 'line-' + i;
                        div.style.padding = '15px';
                        div.style.marginBottom = '12px';
                        div.style.borderLeft = '4px solid #333';
                        div.style.background = 'rgba(255,255,255,0.02)';
                        div.style.borderRadius = '0 10px 10px 0';
                        div.style.cursor = 'pointer';
                        div.style.transition = 'all 0.3s';
                        
                        div.innerHTML = `<div style="font-size: 20px; color: #fff; font-weight: 500;">${{line.text}}</div>` + 
                                        (line.tr ? `<div style="font-size: 16px; color: #888; margin-top: 5px; font-style: italic;">${{line.tr}}</div>` : '');
                        
                        div.onclick = () => {{ audio.currentTime = line.start; audio.play(); }};
                        container.appendChild(div);
                    }});

                    // --- VAQT BO'YICHA YURISH ---
                    audio.ontimeupdate = () => {{
                        const t = audio.currentTime;
                        let idx = data.findIndex(x => t >= x.start && t < x.end);
                        
                        document.querySelectorAll('div[id^="line-"]').forEach(el => {{
                            el.style.background = 'rgba(255,255,255,0.02)';
                            el.style.borderLeftColor = '#333';
                            el.style.transform = 'scale(1)';
                            el.children[0].style.color = '#fff';
                            if(el.children[1]) el.children[1].style.color = '#888';
                        }});

                        if(idx !== -1) {{
                            const active = document.getElementById('line-' + idx);
                            active.style.background = 'linear-gradient(90deg, rgba(0, 229, 255, 0.15), transparent)';
                            active.style.borderLeftColor = '#00e5ff';
                            active.style.transform = 'scale(1.02)';
                            active.children[0].style.color = '#00e5ff';
                            if(active.children[1]) active.children[1].style.color = '#00ffff';
                            
                            // Matn ichidagi avto-skroll
                            active.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                        }}
                    }};
                </script>
                """
                
                components.html(player_html, height=700)
                os.remove(temp_path)

            except Exception as e:
                st.error(f"Xatolik: {e}")

                    
