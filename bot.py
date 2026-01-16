import asyncio
import os
import json
import re
import threading
import pytz
from datetime import datetime

import streamlit as st
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

import whisper
from groq import Groq
from deep_translator import GoogleTranslator

# --- 0. KONFIGURATSIYA VA BAZA ---
ADMIN_ID = 1416457518 
USERS_FILE = "bot_users_list.txt"
SETTINGS_FILE = "bot_settings.json"
uz_tz = pytz.timezone('Asia/Tashkent')

# FSM (Holatlar) - Broadcast uchun
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

def get_uz_time():
    return datetime.now(uz_tz).strftime('%Y-%m-%d %H:%M:%S')

# Ma'lumotlarni yuklash/saqlash
def load_json(filename, default):
    if os.path.exists(filename):
        with open(filename, "r") as f: return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, "w") as f: json.dump(data, f)

def log_user_and_get_count(user: types.User):
    uid = user.id
    user_list = []
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f: user_list = f.readlines()
    
    exists = any(str(uid) in line for line in user_list)
    if not exists:
        count = len(user_list) + 1
        row = f"{count}. ID: {uid} | Name: {user.first_name} | @{user.username} | {get_uz_time()}\n"
        with open(USERS_FILE, "a", encoding="utf-8") as f: f.write(row)
        return count, True
    return len(user_list), False

# --- 1. GLOBAL SOZLAMALAR ---
try:
    BOT_TOKEN = st.secrets["BOT_TOKEN"]
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except:
    st.error("Secrets sozlanmagan!")
    st.stop()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
client_groq = Groq(api_key=GROQ_API_KEY)
async_lock = asyncio.Lock() # Asinxron navbat uchun
waiting_users = 0

@st.cache_resource
def load_local_whisper():
    return whisper.load_model("base")

model_local = load_local_whisper()
bot_config = load_json(SETTINGS_FILE, {"maintenance": False})
user_settings = {}
user_data = {}

# --- 2. KLAVIATURALAR ---
def get_main_menu(uid):
    kb = ReplyKeyboardBuilder()
    kb.button(text="⚡ Groq Rejimi")
    kb.button(text="🎧 Whisper Rejimi")
    kb.button(text="🌐 Saytga kirish (Login)")
    kb.button(text="ℹ️ Yordam")
    if uid == ADMIN_ID:
        kb.button(text="🔑 Admin Panel")
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

# --- 3. FORMATLASH (FAQAT GROQ UCHUN) ---
def format_smart_context(text, lang_code=None):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    res = "📝 **AQLLI TAHLIL (GROQ)**\n\n"
    para = ""
    for i, s in enumerate(sentences):
        if lang_code:
            try:
                tr = GoogleTranslator(source='auto', target=lang_code).translate(s)
                s = f"{s} _({tr})_"
            except: pass
        para += s + " "
        if (i + 1) % 4 == 0:
            res += "    " + para.strip() + "\n\n"
            para = ""
    if para: res += "    " + para.strip()
    return res

# --- 4. HANDLERLAR (BOT MANTIQI) ---

@dp.message(Command("start"))
async def cmd_start(m: types.Message):
    count, is_new = log_user_and_get_count(m.from_user)
    if is_new:
        try: await bot.send_message(ADMIN_ID, f"🆕 YANGI FOYDALANUVCHI: {m.from_user.first_name} (№{count})")
        except: pass
    
    user_settings[m.chat.id] = user_settings.get(m.chat.id, "groq")
    await m.answer(f"👋 **Assalomu alaykum!**\n\nSiz botimizning **{count}-foydalanuvchisiz!**\nRejim: {user_settings[m.chat.id].upper()}",
                   reply_markup=get_main_menu(m.from_user.id), parse_mode="Markdown")

@dp.message(F.text == "ℹ️ Yordam")
async def help_h(m: types.Message):
    await m.answer("📖 **Qo'llanma:** Audio yuboring -> Tilni tanlang -> Formatni tanlang.\n⚠️ Maks: 25MB.")

@dp.message(F.text == "🌐 Saytga kirish (Login)")
async def login_h(m: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🚀 Saytga o'tish", url="https://script1232.streamlit.app")
    await m.answer("Neon Player uchun saytga kiring:", reply_markup=kb.as_markup())

# REJIMNI ALMASHTIRISH
@dp.message(F.text.in_(["⚡ Groq Rejimi", "🎧 Whisper Rejimi"]))
async def switch_h(m: types.Message):
    user_settings[m.chat.id] = "groq" if "Groq" in m.text else "local"
    await m.answer(f"✅ Rejim: **{user_settings[m.chat.id].upper()}**", parse_mode="Markdown")

# ADMIN PANEL
@dp.message(F.text == "🔑 Admin Panel", F.chat.id == ADMIN_ID)
async def admin_h(m: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Ro'yxat", callback_data="adm_list")
    kb.button(text="🔄 Reboot", callback_data="adm_reboot")
    kb.button(text="📢 Broadcast", callback_data="adm_bc")
    kb.button(text="🔧 Maintenance", callback_data="adm_maint")
    kb.adjust(2)
    await m.answer("🚀 **Admin boshqaruv paneli**", reply_markup=kb.as_markup())

# AUDIO QABUL QILISH
@dp.message(F.audio | F.voice)
async def audio_h(m: types.Message):
    f_size = m.audio.file_size if m.audio else m.voice.file_size
    if f_size > 25 * 1024 * 1024:
        await m.answer("❌ Fayl juda katta (Maks 25MB).")
        return
    
    user_data[m.chat.id] = {
        'fid': m.audio.file_id if m.audio else m.voice.file_id,
        'fname': m.audio.file_name if m.audio else "Ovozli.ogg"
    }
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🇺🇿 O'zbek", callback_data="l_uz")
    kb.button(text="🇷🇺 Rus", callback_data="l_ru")
    kb.button(text="📄 Original", callback_data="l_orig")
    kb.adjust(2)
    
    mode = user_settings.get(m.chat.id, "groq").upper()
    await m.answer(f"⚙️ Rejim: {mode}\n🌍 **Tilni tanlang:**", reply_markup=kb.as_markup())

# CALLBACKLAR
@dp.callback_query()
async def callbacks(call: types.CallbackQuery, state: FSMContext):
    chat_id = call.message.chat.id
    global waiting_users

    if call.data == "adm_reboot":
        await call.message.answer("🔄 Rebooting..."); os._exit(0)
    
    elif call.data == "adm_bc":
        await call.message.answer("📢 Xabarni yuboring:")
        await state.set_state(AdminStates.waiting_for_broadcast)

    elif call.data == "adm_list":
        if os.path.exists(USERS_FILE):
            await call.message.answer_document(types.FSInputFile(USERS_FILE))

    elif call.data.startswith("l_"):
        user_data[chat_id]['lang'] = call.data.replace("l_", "")
        kb = InlineKeyboardBuilder()
        kb.button(text="⏱ Split (Vaqt bilan)", callback_data="v_split")
        kb.button(text="📖 Full Context (Groqda aqlli)", callback_data="v_full")
        await call.message.edit_text("📄 **Ko'rinish:**", reply_markup=kb.as_markup())

    elif call.data.startswith("v_"):
        user_data[chat_id]['view'] = call.data.replace("v_", "")
        kb = InlineKeyboardBuilder()
        kb.button(text="📁 TXT Fayl", callback_data="f_txt")
        kb.button(text="💬 Chat", callback_data="f_chat")
        await call.message.edit_text("💾 **Format:**", reply_markup=kb.as_markup())

    elif call.data.startswith("f_"):
        fmt = call.data.replace("f_", "")
        data = user_data[chat_id]
        mode = user_settings.get(chat_id, "groq")
        
        await call.message.delete()
        waiting_users += 1
        wait_msg = await call.message.answer(f"⏳ Navbat: {waiting_users-1}\nRejim: {mode.upper()}")
        
        async with async_lock: # NAVBAT TIZIMI
            try:
                # Progress funksiyasi
                async def update_p(p, txt):
                    bar = "▓" * (p // 10) + "░" * (10 - (p // 10))
                    try: await wait_msg.edit_text(f"🛰 **REJIM: {mode.upper()}**\n\n{txt}\n\n📊 {p}%\n{bar}")
                    except: pass

                await update_p(10, "📥 Yuklanmoqda...")
                f_path = f"t_{chat_id}.mp3"
                file = await bot.get_file(data['fid'])
                await bot.download_file(file.file_path, f_path)
                
                await update_p(50, "🧠 AI tahlil qilmoqda...")
                if mode == "groq":
                    with open(f_path, "rb") as f:
                        res = client_groq.audio.transcriptions.create(file=(f_path, f.read()), model="whisper-large-v3-turbo", response_format="verbose_json")
                    segments = res.segments
                else:
                    res = model_local.transcribe(f_path)
                    segments = res['segments']

                await update_p(90, "✍️ Formatlanmoqda...")
                l_code = {"uz":"uz", "ru":"ru"}.get(data['lang'])
                final_text = ""

                if mode == "groq":
                    if data['view'] == "full":
                        raw = " ".join([s.text.strip() for s in segments])
                        final_text = format_smart_context(raw, l_code)
                    else:
                        for s in segments:
                            tm = f"[{int(s.start//60):02d}:{int(s.start%60):02d}]"
                            tr = GoogleTranslator(source='auto', target=l_code).translate(s.text.strip()) if l_code else ""
                            final_text += f"{tm} {s.text.strip()}\n" + (f" _({tr})_\n\n" if tr else "\n")
                else:
                    for s in segments:
                        tm = f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}]"
                        final_text += f"{tm} {s['text'].strip()}\n\n"

                imzo = f"\n---\n👤 **Dasturchi:** @Otavaliyev_M\n⏰ **Vaqt:** {get_uz_time()}"
                
                if fmt == "txt":
                    with open(f"r_{chat_id}.txt", "w", encoding="utf-8") as f: f.write(final_text + imzo)
                    await call.message.answer_document(types.FSInputFile(f"r_{chat_id}.txt"), caption="✅ Tayyor!")
                    os.remove(f"r_{chat_id}.txt")
                else:
                    await call.message.answer((final_text + imzo)[:4096], parse_mode="Markdown")

                await wait_msg.delete()
                if os.path.exists(f_path): os.remove(f_path)
            except Exception as e:
                await call.message.answer(f"❌ Xato: {e}")
            finally:
                waiting_users -= 1

# BROADCAST HANDLER
@dp.message(AdminStates.waiting_for_broadcast)
async def broadcast_finish(m: types.Message, state: FSMContext):
    await state.clear()
    await m.answer("🚀 Tarqatilmoqda...")
    # (Bu yerda barcha userlarga copy_message qilish kodi bo'ladi)
    await m.answer("✅ Yakunlandi.")

# --- 5. STREAMLIT RUNNER ---
async def main():
    st.success("Aiogram Bot Server ishlamoqda!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(main())
    except:
        pass
    
