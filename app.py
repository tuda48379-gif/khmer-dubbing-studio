import streamlit as st
import os
import re
import ssl
import subprocess
import glob
import shutil
import requests
import urllib3
from pydub import AudioSegment
import yt_dlp
from google import genai

# Bypass SSL
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Khmer Dubbing Studio Pro", layout="wide")

# Custom Styling
st.markdown("""
    <style>
    div[data-baseweb="textarea"] textarea {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        font-size: 15px !important;
        border: 1px solid #444444 !important;
    }
    </style>
""", unsafe_allow_html=True)

# File Paths
CACHE_SCRIPT_FILE = "cached_script.txt"
video_input_path = "original_video.mp4"
extracted_mp3_path = "extracted_audio.mp3"
raw_khmer_audio = "raw_khmer_audio.mp3"
final_video_no_sub = "final_dubbed_audio_only.mp4"
final_video_with_sub = "final_dubbed_with_sub.mp4"
ass_sub_path = "subtitles.ass"

def hard_reset_all():
    files_to_delete = [
        CACHE_SCRIPT_FILE, video_input_path, extracted_mp3_path, 
        raw_khmer_audio, final_video_no_sub, final_video_with_sub, ass_sub_path,
        "temp_dl_video.mp4", "temp_dl_audio.mp3", "t_raw_vid.mp4", "t_raw_aud.mp3"
    ]
    for f in files_to_delete:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
            
    for pattern in ["*.mp3", "*.wav", "*.mp4", "*.srt", "*.ass"]:
        for f in glob.glob(pattern):
            try: os.remove(f)
            except Exception: pass

    for p in glob.glob("temp_*") + glob.glob("raw_*") + ["temp_processing", "__pycache__"]:
        if os.path.exists(p):
            try:
                if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
                else: os.remove(p)
            except Exception: pass
            
    st.session_state.clear()

st.title("🎬 Khmer Dubbing Studio Pro")

col_info, col_reset = st.columns([3, 1])
with col_info:
    st.info("💡 ដំណើរការ៖ ១. បញ្ចូលវីដេអូ ➔ ២. បកប្រែ Script ➔ ៣. បង្កើតសំឡេង Auto-Sync ➔ ៤. ជ្រើសរើស Render វីដេអូ")
with col_reset:
    st.write("🧹 **Storage**")
    if st.button("🗑️ Reset All (លុប Data ទាំងអស់)", type="secondary", use_container_width=True):
        hard_reset_all()
        st.success("✅ បាន Reset រួចរាល់!")
        st.rerun()

st.divider()

# 1. API Key
st.subheader("🔑 ១. បញ្ចូល Gemini API Key")
gemini_key = st.text_input("🔑 Gemini API Key:", type="password", value="")

st.divider()

def has_audio_stream(file_path):
    try:
        chk = subprocess.run(["ffprobe", "-i", file_path, "-show_streams", "-select_streams", "a", "-loglevel", "error"], capture_output=True, text=True)
        return bool(chk.stdout.strip())
    except: return False

def download_video_all(url, out_path):
    url = url.strip()
    if "tiktok.com" in url.lower():
        try:
            api_url = "https://www.tikwm.com/api/"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            res = requests.post(api_url, headers=headers, data={'url': url, 'web': 1}, verify=False, timeout=15).json()
            if res.get("code") == 0 and "data" in res:
                d = res["data"]
                v_url = d.get("play") or d.get("wmplay")
                m_url = d.get("music")
                
                t_vid = "t_raw_vid.mp4"
                t_aud = "t_raw_aud.mp3"
                rv = requests.get(v_url, headers=headers, verify=False, timeout=30)
                with open(t_vid, "wb") as f: f.write(rv.content)
                
                if m_url:
                    ra = requests.get(m_url, headers=headers, verify=False, timeout=20)
                    with open(t_aud, "wb") as f: f.write(ra.content)
                    subprocess.run(["ffmpeg", "-y", "-i", t_vid, "-i", t_aud, "-c:v", "copy", "-c:a", "aac", "-shortest", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(t_aud): os.remove(t_aud)
                else:
                    if os.path.exists(out_path): os.remove(out_path)
                    os.rename(t_vid, out_path)
                    
                if os.path.exists(t_vid): os.remove(t_vid)
                if os.path.exists(out_path) and has_audio_stream(out_path): return True, "ជោគជ័យតាម TikWM"
        except Exception: pass

    try:
        ydl_opts = {'format': 'bestvideo+bestaudio/best', 'outtmpl': out_path, 'nocheckcertificate': True, 'merge_output_format': 'mp4', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000: return True, "ជោគជ័យតាម yt-dlp"
    except Exception as e: return False, str(e)
        
    return False, "មិនអាចទាញយកវីដេអូបានទេ"

def parse_time_to_ms(t):
    t = t.replace(',', '.').strip()
    p = t.split(':')
    if len(p) == 3: return int((int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])) * 1000)
    elif len(p) == 2: return int((int(p[0]) * 60 + float(p[1])) * 1000)
    return 0

def ms_to_ass_time(ms):
    hrs = int(ms // 3600000)
    mins = int((ms % 3600000) // 60000)
    secs = int((ms % 60000) // 1000)
    cs = int((ms % 1000) // 10)
    return f"{hrs:01d}:{mins:02d}:{secs:02d}.{cs:02d}"

def clean_speech_text(text):
    patterns = [
        r'\[\s*(ស្រី|female|woman|girl|f)\s*\]:?',
        r'\(\s*(ស្រី|female|woman|girl|f)\s*\):?',
        r'\[\s*(ប្រុស|male|man|boy|m)\s*\]:?',
        r'\(\s*(ប្រុស|male|man|boy|m)\s*\):?',
        r'^(ស្រី|female|woman|girl|f)\s*[:：\-]\s*',
        r'^(ប្រុស|male|man|boy|m)\s*[:：\-]\s*'
    ]
    cleaned = text
    for pat in patterns: cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE).strip()
    return re.sub(r'^[\[\(].*?[\]\)]\s*[:：]?', '', cleaned).strip()

def limit_to_single_line(text, max_len=40):
    if len(text) <= max_len:
        return text
    parts = text.split(" ")
    out = ""
    for p in parts:
        if len(out) + len(p) + 1 <= max_len:
            out = f"{out} {p}".strip()
        else:
            break
    return out if out else text[:max_len]

def parse_srt(srt_text, mode):
    lines = srt_text.replace('\r\n', '\n').split('\n')
    items = []
    curr_start, curr_end, curr_text = None, None, []
    for line in lines:
        s = line.strip()
        if not s: continue
        m = re.search(r'(\d{1,2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{3})', s)
        if m:
            if curr_start and curr_text:
                sp = " ".join(curr_text).strip()
                v = "km-KH-PisethNeural"
                if "🤖" in mode or "អូតូ" in mode:
                    if any(k in sp.lower() for k in ["ស្រី", "female", "(f)", "[f]", "woman"]): v = "km-KH-SreymomNeural"
                elif "👩" in mode: v = "km-KH-SreymomNeural"
                cl = clean_speech_text(sp)
                if cl: items.append({"start": parse_time_to_ms(curr_start), "end": parse_time_to_ms(curr_end), "text": cl, "voice": v, "start_str": curr_start, "end_str": curr_end})
            curr_start, curr_end = m.group(1), m.group(2)
            curr_text = []
        elif not s.isdigit() and "-->" not in s: curr_text.append(s)
            
    if curr_start and curr_text:
        sp = " ".join(curr_text).strip()
        v = "km-KH-PisethNeural"
        if "🤖" in mode or "អូតូ" in mode:
            if any(k in sp.lower() for k in ["ស្រី", "female", "(f)", "[f]", "woman"]): v = "km-KH-SreymomNeural"
        elif "👩" in mode: v = "km-KH-SreymomNeural"
        cl = clean_speech_text(sp)
        if cl: items.append({"start": parse_time_to_ms(curr_start), "end": parse_time_to_ms(curr_end), "text": cl, "voice": v, "start_str": curr_start, "end_str": curr_end})
    return items

def generate_and_fit_audio(text, voice, out_path, target_ms):
    temp_raw = f"raw_{out_path}"
    subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", temp_raw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_raw):
        seg = AudioSegment.from_file(temp_raw)
        actual_ms = len(seg)
        if target_ms <= 0: target_ms = actual_ms
        factor = max(0.6, min(1.8, actual_ms / target_ms))
        if abs(factor - 1.0) > 0.05:
            subprocess.run(["ffmpeg", "-y", "-i", temp_raw, "-filter:a", f"atempo={factor:.2f}", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(temp_raw): os.remove(temp_raw)
        else:
            if os.path.exists(out_path): os.remove(out_path)
            os.rename(temp_raw, out_path)

def create_ass_file(items, out_ass):
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KhmerSub,Noto Sans Khmer,30,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,2,0,2,20,20,35,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(header)
        for it in items:
            s_t = ms_to_ass_time(it["start"])
            e_t = ms_to_ass_time(it["end"])
            txt = limit_to_single_line(it["text"])
            f.write(f"Dialogue: 0,{s_t},{e_t},KhmerSub,,0,0,0,,{txt}\n")

# 2. Video Source
st.subheader("📥 ២. ប្រភពវីដេអូដើម")
input_opt = st.radio("វិធីសាស្ត្របញ្ចូលវីដេអូ៖", ["🔗 URL Link (TikTok / YouTube)", "📂 Upload File MP4"], key="v_opt")

if input_opt == "🔗 URL Link (TikTok / YouTube)":
    url_in = st.text_input("🔗 បញ្ចូល Link វីដេអូ TikTok/YouTube៖", placeholder="https://vt.tiktok.com/...")
    if st.button("📥 ទាញយកវីដេអូដើម", type="primary"):
        if not url_in.strip(): st.error("សូមបញ្ចូល URL!")
        else:
            if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
            if os.path.exists(video_input_path): os.remove(video_input_path)
            st_box = st.empty()
            st_box.info("⏳ កំពុងទាញយកវីដេអូ...")
            ok, msg = download_video_all(url_in.strip(), video_input_path)
            if ok:
                st_box.success("🎉 ទាញយកវីដេអូជោគជ័យ!")
                st.rerun()
            else: st_box.error(f"❌ កំហុស៖ {msg}")
else:
    up_v = st.file_uploader("📂 Upload File MP4 វីដេអូដើម", type=["mp4", "mov"])
    if up_v:
        if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
        with open(video_input_path, "wb") as f: f.write(up_v.read())
        st.success("✅ បាន Upload រួចរាល់!")

if os.path.exists(video_input_path):
    st.video(video_input_path)
    if st.button("✨ ប្រើ Gemini 3.6 Flash ស្ដាប់វីដេអូ ➔ បកប្រែជា Khmer SRT + Tag [ប្រុស]/[ស្រី]"):
        if not gemini_key.strip(): st.error("❌ សូមបញ្ចូល Gemini API Key!")
        else:
            st_box = st.empty()
            st_box.info("⏳ កំពុងបន្សុទ្ធសំឡេងមនុស្សនិយាយ...")
            subprocess.run(["ffmpeg", "-y", "-i", video_input_path, "-vn", "-af", "highpass=f=100,lowpass=f=3800,volume=1.8", "-ar", "16000", "-ac", "1", "-b:a", "128k", extracted_mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if not os.path.exists(extracted_mp3_path) or os.path.getsize(extracted_mp3_path) < 1000:
                st_box.error("❌ មិនអាចទាញយកសំឡេងបានទេ!")
            else:
                try:
                    st_box.info("✨ Gemini 3.6 Flash កំពុងស្ដាប់គ្រប់វិនាទី & បកប្រែពេញលេញ...")
                    client = genai.Client(api_key=gemini_key.strip())
                    audio_file = client.files.upload(file=extracted_mp3_path)
                    prompt = (
                        "CRITICAL INSTRUCTIONS FOR FULL AUDIO DUBBING TRANSCRIPTION:\n"
                        "1. Listen to the ENTIRE audio file from the first second to the very last second without stopping.\n"
                        "2. Transcribe EVERY single dialogue and conversation. DO NOT summarize, DO NOT skip any scene or silence.\n"
                        "3. Translate every dialogue accurately into natural spoken Khmer.\n"
                        "4. Maintain precise timestamps for each line.\n"
                        "5. Tag every line with '[ប្រុស]' (Male) or '[ស្រី]' (Female) at the start.\n"
                        "6. Keep each subtitle line concise (1 single line) for smooth dubbing sync.\n"
                        "7. Return the result STRICTLY in valid SubRip (.srt) subtitle format without markdown formatting."
                    )
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=[audio_file, prompt],
                        config={'temperature': 0.0, 'top_p': 0.95, 'max_output_tokens': 8192}
                    )
                    res_text = response.text.replace("```srt", "").replace("```", "").strip()
                    with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f: f.write(res_text)
                    st_box.success("🎉 Gemini 3.6 Flash បានបកប្រែរួចរាល់ពេញលេញ!")
                    st.rerun()
                except Exception as e: st_box.error(f"❌ កំហុស Gemini៖ {e}")

st.divider()

# 3. Script Editor
st.subheader("📝 ៣. អត្ថបទ Script SRT ខ្មែរ")
cur_script = open(CACHE_SCRIPT_FILE, 'r', encoding='utf-8').read() if os.path.exists(CACHE_SCRIPT_FILE) else ""
user_script = st.text_area("Script SRT ខ្មែរ (គាំទ្រ Tag [ប្រុស]/[ស្រី]):", value=cur_script, height=220)
if user_script != cur_script:
    with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f: f.write(user_script)

v_choice = st.selectbox("🎙️ សំឡេងអាន៖", ["🤖 អូតូ (ប្រុស/ស្រី តាម Tag)", "👨 Piseth (ប្រុសសុទ្ធ)", "👩 Sreymom (ស្រីសុទ្ធ)"])

st.divider()

# 4. Step 1: TTS Audio Generation (Cached)
st.subheader("🔊 ៤. ជំហានទី ១៖ បង្កើតសំឡេង Auto-Sync (TTS)")
if st.button("🎙️ ចាប់ផ្ដើមបង្កើតសំឡេង Auto-Sync (MP3)", type="primary"):
    raw_text = user_script.strip()
    if not raw_text: st.error("សូមបញ្ចូល Script SRT!")
    else:
        items = parse_srt(raw_text, v_choice)
        total = len(items)
        st.markdown(f"### 📊 រកឃើញសរុប **{total} ជួរ**")
        
        if total > 0:
            combined = AudioSegment.silent(duration=0)
            current_ms = 0
            prog = st.progress(0)
            status = st.empty()
            
            for idx, it in enumerate(items):
                status.text(f"⚡ កំពុង Sync ជួរទី {idx+1}/{total}: {it['text'][:25]}...")
                if it["start"] > current_ms:
                    combined += AudioSegment.silent(duration=it["start"] - current_ms)
                    current_ms = it["start"]
                
                temp_f = f"temp_{idx}.mp3"
                try:
                    generate_and_fit_audio(it["text"], it["voice"], temp_f, it["end"] - it["start"])
                    if os.path.exists(temp_f):
                        seg = AudioSegment.from_file(temp_f)
                        combined += seg
                        current_ms += len(seg)
                        os.remove(temp_f)
                except Exception: pass
                prog.progress(int((idx + 1) / total * 100))
                
            combined.export(raw_khmer_audio, format="mp3")
            status.success(f"🎉 បង្កើតសំឡេង Auto-Sync គ្រប់ {total} ជួររួចរាល់! អាច Render វីដេអូបានភ្លាមៗ។")
            st.rerun()

if os.path.exists(raw_khmer_audio):
    st.audio(raw_khmer_audio, format="audio/mp3")
    with open(raw_khmer_audio, "rb") as af:
        st.download_button("📥 ទាញយក File MP3 សុទ្ធ", af, file_name="khmer_audio_synced.mp3", use_container_width=False)

st.divider()

# 5. Step 2: Render Options (Using Cached Audio)
st.subheader("🎬 ៥. ជំហានទី ២៖ ជ្រើសរើស Render វីដេអូ (ប្រើសំឡេងស្រាប់)")

col_r1, col_r2 = st.columns(2)

with col_r1:
    st.write("🎬 **ជម្រើស A: វីដេអូ + សំឡេងសុទ្ធ (គ្មាន Subtitle)**")
    if st.button("🚀 Render Video + Audio Only", type="primary", use_container_width=True):
        if not os.path.exists(video_input_path):
            st.error("❌ មិនទាន់មានវីដេអូដើមទេ!")
        elif not os.path.exists(raw_khmer_audio):
            st.error("❌ សូមចុចបង្កើតសំឡេង (ជំហានទី ៤) ជាមុនសិន!")
        else:
            status_box = st.empty()
            status_box.info("⏳ កំពុង Merge សំឡេងចូលវីដេអូ...")
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", video_input_path,
                "-i", raw_khmer_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                final_video_no_sub
            ]
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            status_box.success("🎉 Render វីដេអូ + សំឡេងសុទ្ធ រួចរាល់!")
            st.rerun()

    if os.path.exists(final_video_no_sub):
        st.video(final_video_no_sub)
        with open(final_video_no_sub, "rb") as vf1:
            st.download_button("📥 Download Video (No Sub)", vf1, file_name="dubbed_video_audio_only.mp4", use_container_width=True)

with col_r2:
    st.write("🔤 **ជម្រើស B: វីដេអូ + សំឡេង + Subtitle ខ្មែរ (Unicode 1 ជួរ)**")
    if st.button("🚀 Render Video + Audio + Subtitle", type="primary", use_container_width=True):
        if not os.path.exists(video_input_path):
            st.error("❌ មិនទាន់មានវីដេអូដើមទេ!")
        elif not os.path.exists(raw_khmer_audio):
            st.error("❌ សូមចុចបង្កើតសំឡេង (ជំហានទី ៤) ជាមុនសិន!")
        else:
            status_box = st.empty()
            status_box.info("⏳ កំពុងដុត Subtitle ខ្មែរ (ASS) និង Merge សំឡេង...")
            
            # បង្កើត ASS Subtitle
            items = parse_srt(user_script.strip(), v_choice)
            create_ass_file(items, ass_sub_path)
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", video_input_path,
                "-i", raw_khmer_audio,
                "-vf", f"ass={ass_sub_path}",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-shortest",
                final_video_with_sub
            ]
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            status_box.success("🎉 Render វីដេអូ + Subtitle ខ្មែរ រួចរាល់!")
            st.rerun()

    if os.path.exists(final_video_with_sub):
        st.video(final_video_with_sub)
        with open(final_video_with_sub, "rb") as vf2:
            st.download_button("📥 Download Video (+ Subtitle)", vf2, file_name="dubbed_video_with_sub.mp4", use_container_width=True)

