import streamlit as st
import os
import re
import ssl
import subprocess
import glob
import shutil
import math
import requests
import urllib3
from pydub import AudioSegment
import yt_dlp
from google import genai

# Setup SSL & Warnings
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Khmer Dubbing Studio Pro", layout="wide")

# Custom UI Styling (កំណត់ពណ៌បៃតងលើប៊ូតុង Gemini ដោយប្រើ data-testid ច្បាស់លាស់)
st.markdown("""
    <style>
    div[data-baseweb="textarea"] textarea {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        font-size: 15px !important;
        border: 1px solid #444444 !important;
    }
    div.stButton > button.gemini-btn {
        background-color: #28a745 !important;
        color: #FFFFFF !important;
        font-weight: bold !important;
        font-size: 16px !important;
        border: 1px solid #1e7e34 !important;
        border-radius: 8px !important;
        padding: 12px 24px !important;
        width: 100% !important;
    }
    div.stButton > button.gemini-btn:hover {
        background-color: #218838 !important;
        color: #FFFFFF !important;
    }
    </style>
""", unsafe_allow_html=True)

# File Paths
CACHE_SCRIPT_FILE = "cached_script.txt"
video_input_path = "original_video.mp4"
extracted_mp3_path = "extracted_audio.mp3"
raw_khmer_audio = "raw_khmer_audio.mp3"
final_video_no_sub = "final_dubbed_audio_only.mp4"

def get_dir_size_mb():
    total_size = 0
    for dirpath, dirnames, filenames in os.walk('.'):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)

def hard_reset_all():
    files_to_delete = [
        CACHE_SCRIPT_FILE, video_input_path, extracted_mp3_path, 
        raw_khmer_audio, final_video_no_sub,
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

    for p in glob.glob("temp_*") + glob.glob("raw_*") + glob.glob("t_raw_*") + glob.glob("chunk_*") + ["temp_processing", "__pycache__"]:
        if os.path.exists(p):
            try:
                if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
                else: os.remove(p)
            except Exception: pass
            
    st.session_state.clear()

st.title("🎬 Khmer Dubbing Studio Pro")

# Storage Info Bar
col_info, col_reset = st.columns([2.5, 1.5])
with col_info:
    st.info("💡 ដំណើរការ៖ ១. បញ្ចូលវីដេអូ ➔ ២. Gemini បកប្រែ Script (Chunking គ្រប់នាទី) ➔ ៣. បង្កើតសំឡេង Auto-Sync ➔ ៤. Render វីដេអូ")
with col_reset:
    used_mb = get_dir_size_mb()
    st.metric(label="💾 ទំហំផ្ទុកប្រើប្រាស់ (Disk Usage)", value=f"{used_mb:.1f} MB")
    if st.button("🗑️ Reset All", type="secondary", use_container_width=True):
        hard_reset_all()
        st.success("✅ បានសម្អាតទំហំផ្ទុកជោគជ័យ!")
        st.rerun()

st.divider()

# 1. API Key
st.subheader("🔑 ១. បញ្ចូល Gemini API Key")
gemini_key = st.text_input("🔑 Gemini API Key:", type="password", value="")

st.divider()

def has_audio_stream(file_path):
    try:
        chk = subprocess.run(
            ["ffprobe", "-i", file_path, "-show_streams", "-select_streams", "a", "-loglevel", "error"],
            capture_output=True, text=True
        )
        return bool(chk.stdout.strip())
    except Exception:
        return False

def download_video_all(url, out_path):
    url = url.strip()
    for f in [out_path, "t_raw_vid.mp4", "t_raw_aud.mp3"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    # TikTok (TikWM)
    if "tiktok.com" in url.lower():
        try:
            api_url = "https://www.tikwm.com/api/"
            res = requests.post(api_url, headers={'User-Agent': 'Mozilla/5.0'}, data={'url': url, 'web': 1}, verify=False, timeout=15).json()
            if res.get("code") == 0 and "data" in res:
                v_url = res["data"].get("play") or res["data"].get("wmplay")
                m_url = res["data"].get("music")
                t_vid, t_aud = "t_raw_vid.mp4", "t_raw_aud.mp3"
                rv = requests.get(v_url, headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=30)
                with open(t_vid, "wb") as f: f.write(rv.content)
                if m_url:
                    ra = requests.get(m_url, headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=20)
                    with open(t_aud, "wb") as f: f.write(ra.content)
                    subprocess.run(["ffmpeg", "-y", "-i", t_vid, "-i", t_aud, "-c:v", "copy", "-c:a", "aac", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if os.path.exists(t_aud): os.remove(t_aud)
                else:
                    if os.path.exists(out_path): os.remove(out_path)
                    os.rename(t_vid, out_path)
                if os.path.exists(t_vid): os.remove(t_vid)
                if os.path.exists(out_path) and has_audio_stream(out_path):
                    return True, "ជោគជ័យតាម TikWM"
        except Exception:
            pass

    # Universal Downloader (គាំទ្រ Dailymotion HLS ដោយមិនកំណត់ format តឹងរ៉ឹង)
    try:
        ydl_opts = {
            'outtmpl': out_path,
            'nocheckcertificate': True,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4'
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return True, "ជោគជ័យ"
    except Exception as e:
        err_str = str(e)
        if "youtube" in url.lower() or "youtu.be" in url.lower():
            return False, "YouTube បានដាក់កំហិត Bot Block លើ Server Cloud។ សូម Upload File MP4 ដោយផ្ទាល់។"
        return False, f"កំហុសទាញយក៖ {err_str}"

    return False, "មិនអាចទាញយកបានទេ សូម Upload File MP4 ជំនួសវិញ"

def parse_time_to_ms(t):
    t = t.replace(',', '.').strip()
    p = t.split(':')
    if len(p) == 3: 
        return int((int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])) * 1000)
    elif len(p) == 2: 
        return int((int(p[0]) * 60 + float(p[1])) * 1000)
    elif len(p) == 1:
        return int(float(p[0]) * 1000)
    return 0

def ms_to_srt_time(ms):
    hrs = int(ms // 3600000)
    mins = int((ms % 3600000) // 60000)
    secs = int((ms % 60000) // 1000)
    millis = int(ms % 1000)
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

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
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE).strip()
    return re.sub(r'^[\[\(].*?[\]\)]\s*[:：]?', '', cleaned).strip()

def parse_srt(srt_text, mode):
    lines = srt_text.replace('\r\n', '\n').split('\n')
    items = []
    curr_start, curr_end, curr_text = None, None, []
    time_pat = re.compile(r'((?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})')

    for line in lines:
        s = line.strip()
        if not s: continue
        m = time_pat.search(s)
        if m:
            if curr_start and curr_text:
                sp = " ".join(curr_text).strip()
                v = "km-KH-PisethNeural"
                if "🤖" in mode or "អូតូ" in mode:
                    if any(k in sp.lower() for k in ["ស្រី", "female", "(f)", "[f]", "woman"]): v = "km-KH-SreymomNeural"
                elif "👩" in mode: v = "km-KH-SreymomNeural"
                cl = clean_speech_text(sp)
                if cl: items.append({"start": parse_time_to_ms(curr_start), "end": parse_time_to_ms(curr_end), "text": cl, "voice": v})
            curr_start, curr_end = m.group(1), m.group(2)
            curr_text = []
        elif not s.isdigit() and "-->" not in s:
            curr_text.append(s)
            
    if curr_start and curr_text:
        sp = " ".join(curr_text).strip()
        v = "km-KH-PisethNeural"
        if "🤖" in mode or "អូតូ" in mode:
            if any(k in sp.lower() for k in ["ស្រី", "female", "(f)", "[f]", "woman"]): v = "km-KH-SreymomNeural"
        elif "👩" in mode: v = "km-KH-SreymomNeural"
        cl = clean_speech_text(sp)
        if cl: items.append({"start": parse_time_to_ms(curr_start), "end": parse_time_to_ms(curr_end), "text": cl, "voice": v})
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

# 2. Video Source
st.subheader("📥 ២. ប្រភពវីដេអូដើម")
input_opt = st.radio("វិធីសាស្ត្របញ្ចូលវីដេអូ៖", ["🔗 URL Link (Dailymotion/TikTok/FB/YouTube)", "📂 Upload File MP4"], key="v_opt")

if input_opt == "🔗 URL Link (Dailymotion/TikTok/FB/YouTube)":
    url_in = st.text_input("🔗 បញ្ចូល Link វីដេអូ៖", placeholder="https://www.dailymotion.com/video/...")
    if st.button("📥 ទាញយកវីដេអូដើម", type="primary"):
        if not url_in.strip(): 
            st.error("សូមបញ្ចូល URL!")
        else:
            if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
            st_box = st.empty()
            st_box.info("⏳ កំពុងទាញយកវីដេអូ...")
            ok, msg = download_video_all(url_in.strip(), video_input_path)
            if ok:
                st_box.success("🎉 ទាញយកវីដេអូជោគជ័យ!")
                st.rerun()
            else: 
                st_box.error(f"❌ {msg}")
else:
    up_v = st.file_uploader("📂 Upload File MP4 វីដេអូដើម", type=["mp4", "mov"])
    if up_v:
        if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
        with open(video_input_path, "wb") as f: f.write(up_v.read())
        st.success("✅ បាន Upload រួចរាល់!")

if os.path.exists(video_input_path):
    st.video(video_input_path)
    
    col_vid_del, col_vid_ai = st.columns([1, 3])
    with col_vid_del:
        if st.button("🗑️ លុបវីដេអូនេះ", use_container_width=True):
            if os.path.exists(video_input_path): os.remove(video_input_path)
            st.rerun()
            
    with col_vid_ai:
        # ប៊ូតុងពណ៌បៃតង (Green Action Button)
        if st.button("✨ ប្រើ Gemini 3.6 Flash ស្ដាប់វីដេអូ ➔ បកប្រែជា Khmer SRT (Full Coverage)", type="primary", use_container_width=True):
            if not gemini_key.strip(): 
                st.error("❌ សូមបញ្ចូល Gemini API Key!")
            else:
                st_box = st.empty()
                st_box.info("⏳ កំពុងបំប្លែងសំឡេងដើម...")
                subprocess.run([
                    "ffmpeg", "-y", "-i", video_input_path,
                    "-vn", "-ar", "24000", "-ac", "1", "-b:a", "128k",
                    extracted_mp3_path
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                if not os.path.exists(extracted_mp3_path) or os.path.getsize(extracted_mp3_path) < 1000:
                    st_box.error("❌ មិនអាចទាញយកសំឡេងបានទេ!")
                else:
                    try:
                        audio = AudioSegment.from_file(extracted_mp3_path)
                        total_duration_ms = len(audio)
                        chunk_length_ms = 90 * 1000  # បំបែកជា ៩០ វិនាទីម្ដង ដើម្បីឱ្យ Gemini ស្ដាប់គ្រប់ពាក្យ មិនរំលង
                        num_chunks = math.ceil(total_duration_ms / chunk_length_ms)
                        
                        client = genai.Client(api_key=gemini_key.strip())
                        all_srt_items = []
                        global_idx = 1
                        
                        prog_bar = st.progress(0)
                        
                        for i in range(num_chunks):
                            start_ms = i * chunk_length_ms
                            end_ms = min((i + 1) * chunk_length_ms, total_duration_ms)
                            st_box.info(f"✨ Gemini កំពុងស្ដាប់ភាគទី {i+1}/{num_chunks} ({start_ms//1000}s ➔ {end_ms//1000}s)...")
                            
                            chunk_audio = audio[start_ms:end_ms]
                            chunk_file = f"chunk_{i}.mp3"
                            chunk_audio.export(chunk_file, format="mp3")
                            
                            uploaded_chunk = client.files.upload(file=chunk_file)
                            prompt = (
                                "Task: Transcribe every spoken sentence in this audio chunk and translate directly into natural spoken Khmer.\n"
                                "Rules:\n"
                                "1. Tag [ប្រុស] for male speaker or [ស្រី] for female speaker at start of each line.\n"
                                "2. Output STRICTLY in standard SubRip (.srt) subtitle format.\n"
                                "3. Transcribe ALL dialogues even background or quiet voices. Do NOT skip.\n"
                                "4. Output ONLY valid SRT content, no explanations."
                            )
                            
                            res = client.models.generate_content(
                                model='gemini-3.6-flash',
                                contents=[uploaded_chunk, prompt],
                                config={'temperature': 0.1, 'max_output_tokens': 4096}
                            )
                            
                            raw_chunk_srt = res.text.replace("```srt", "").replace("```", "").strip()
                            chunk_items = parse_srt(raw_chunk_srt, "🤖 អូតូ")
                            
                            # Shift timestamps ឱ្យត្រូវនឹងពេលវេលាវីដេអូដើម
                            for it in chunk_items:
                                real_start = start_ms + it["start"]
                                real_end = start_ms + it["end"]
                                all_srt_items.append(f"{global_idx}\n{ms_to_srt_time(real_start)} --> {ms_to_srt_time(real_end)}\n[{'ប្រុស' if it['voice']=='km-KH-PisethNeural' else 'ស្រី'}] {it['text']}\n")
                                global_idx += 1
                                
                            if os.path.exists(chunk_file): os.remove(chunk_file)
                            prog_bar.progress(int((i + 1) / num_chunks * 100))

                        final_full_srt = "\n".join(all_srt_items)
                        with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f: 
                            f.write(final_full_srt)
                            
                        st_box.success(f"🎉 Gemini 3.6 Flash បានស្ដាប់ & បកប្រែពេញលេញគ្រប់ {num_chunks} ភាគ (គ្មានការរំលង)!")
                        st.rerun()
                    except Exception as e: 
                        st_box.error(f"❌ កំហុស Gemini៖ {e}")

st.divider()

# 3. Script Editor
st.subheader("📝 ៣. អត្ថបទ Script SRT ខ្មែរ")
cur_script = open(CACHE_SCRIPT_FILE, 'r', encoding='utf-8').read() if os.path.exists(CACHE_SCRIPT_FILE) else ""
user_script = st.text_area("Script SRT ខ្មែរ (គាំទ្រ Tag [ប្រុស]/[ស្រី]):", value=cur_script, height=250)
if user_script != cur_script:
    with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f: 
        f.write(user_script)

v_choice = st.selectbox("🎙️ សំឡេងអាន៖", ["🤖 អូតូ (ប្រុស/ស្រី តាម Tag)", "👨 Piseth (ប្រុសសុទ្ធ)", "👩 Sreymom (ស្រីសុទ្ធ)"])

st.divider()

# 4. Step 1: TTS Audio Generation (Cached)
st.subheader("🔊 ៤. ជំហានទី ១៖ បង្កើតសំឡេង Auto-Sync (TTS)")
if st.button("🎙️ ចាប់ផ្ដើមបង្កើតសំឡេង Auto-Sync (MP3)", type="primary"):
    raw_text = user_script.strip()
    if not raw_text: 
        st.error("សូមបញ្ចូល Script SRT!")
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
                except Exception: 
                    pass
                prog.progress(int((idx + 1) / total * 100))
                
            combined.export(raw_khmer_audio, format="mp3")
            status.success(f"🎉 បង្កើតសំឡេង Auto-Sync គ្រប់ {total} ជួររួចរាល់!")
            st.rerun()
        else:
            st.error("❌ មិនអាច Parse SRT បានទេ! សូមពិនិត្យមើលទម្រង់ម៉ោង។")

if os.path.exists(raw_khmer_audio):
    st.audio(raw_khmer_audio, format="audio/mp3")
    with open(raw_khmer_audio, "rb") as af:
        st.download_button("📥 ទាញយក File MP3 សុទ្ធ", af, file_name="khmer_audio_synced.mp3")

st.divider()

# 5. Step 2: Render Option (រក្សាប្រវែងដើម ១០០%)
st.subheader("🎬 ៥. ជំហានទី ២៖ Render វីដេអូ + សំឡេង (រក្សាប្រវែងដើម)")

if st.button("🚀 Render Video + Audio Only", type="primary", use_container_width=True):
    if not os.path.exists(video_input_path):
        st.error("❌ មិនទាន់មានវីដេអូដើមទេ!")
    elif not os.path.exists(raw_khmer_audio):
        st.error("❌ សូមចុចបង្កើតសំឡេង (ជំហានទី ៤) ជាមុនសិន!")
    else:
        status_box = st.empty()
        status_box.info("⏳ កំពុង Merge សំឡេង (រក្សាប្រវែងវីដេអូដើម)...")
        ffmpeg_cmd = [
            "ffmpeg", "-y",
            "-i", video_input_path,
            "-i", raw_khmer_audio,
            "-filter_complex", "[1:a]apad[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "[aout]",
            final_video_no_sub
        ]
        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        status_box.success("🎉 Render វីដេអូ + សំឡេងសុទ្ធ រួចរាល់ពេញប្រវែងដើម!")
        st.rerun()

if os.path.exists(final_video_no_sub):
    st.video(final_video_no_sub)
    with open(final_video_no_sub, "rb") as vf1:
        st.download_button("📥 Download Video Final", vf1, file_name="dubbed_video_audio_only.mp4", use_container_width=True)
        
