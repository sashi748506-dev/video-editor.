import json
import os
import re
import subprocess
import time
import google.generativeai as genai
import streamlit as st
import yt_dlp

# Page Config
st.set_page_config(
    page_title="AI Square Video Clipper", page_icon="✂️", layout="centered"
)
st.title("✂️ AI Square Video Clipper (1:1)")
st.caption(
    "Paste YouTube URL → Gemini finds viral moment → Auto-crops 1:1 for feed"
)

# API Key Handling (Streamlit Secrets ya Direct Input)
api_key = st.secrets.get("GEMINI_API_KEY", None)
if not api_key:
  api_key = st.sidebar.text_input(
      "Gemini API Key",
      type="password",
      help="Get free key from aistudio.google.com",
  )

url = st.text_input(
    "YouTube Video Link:",
    placeholder="https://www.youtube.com/watch?v=...",
)


def sanitize_filename(name):
  return re.sub(r"[^\w\-_\. ]", "_", name)


def download_video(yt_url):
  out_tmpl = "downloads/%(id)s.%(ext)s"
  ydl_opts = {
      "format": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
      "outtmpl": out_tmpl,
      "quiet": True,
      "no_warnings": True,
  }
  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(yt_url, download=True)
    filename = ydl.prepare_filename(info)
    return filename, info.get("title", "video")


def analyze_with_gemini(video_path):
  genai.configure(api_key=api_key)

  with st.spinner("Gemini API video analyze kar raha hai..."):
    video_file = genai.upload_file(path=video_path)

    # Wait for processing
    while video_file.state.name == "PROCESSING":
      time.sleep(3)
      video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
      raise ValueError("Video processing failed on Gemini.")

    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    prompt = """
        Analyze this video and identify the single most viral, high-retention 30 to 45-second segment.
        The segment MUST be suitable for a 1:1 square crop where the speaker/action is centered.
        
        Return ONLY a raw JSON object with no markdown backticks:
        {
          "start_time": "00:01:15",
          "end_time": "00:01:50",
          "hook_text": "CATCHY BOLD HOOK (MAX 5 WORDS)"
        }
        """
    response = model.generate_content([video_file, prompt])
    raw_text = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(raw_text)


def process_square_video(input_path, start, end, hook, output_path):
  clean_hook = hook.replace("'", "").replace(":", "-")
  # Filter: 1:1 Center crop + Upper-center hook text overlay
  vf_filter = (
      f"crop=ih:ih:(iw-ih)/2:0,"
      f"drawtext=text='{clean_hook}':fontcolor=white:fontsize=32:box=1:boxcolor=black@0.7:boxborderw=12:x=(w-text_w)/2:y=60"
  )

  cmd = [
      "ffmpeg",
      "-y",
      "-ss",
      start,
      "-to",
      end,
      "-i",
      input_path,
      "-vf",
      vf_filter,
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      "-preset",
      "ultrafast",
      output_path,
  ]
  subprocess.run(cmd, check=True)


if st.button("Generate 1:1 Clip", type="primary"):
  if not api_key:
    st.error("Pehle Gemini API key daalo!")
  elif not url:
    st.error("YouTube URL paste karo!")
  else:
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    try:
      with st.status("Ship mode activated...", expanded=True) as status:
        st.write("1. Video download ho rahi hai...")
        raw_file, title = download_video(url)

        st.write("2. AI se viral hook aur timestamps dhoondh rahe hain...")
        meta = analyze_with_gemini(raw_file)

        start = meta["start_time"]
        end = meta["end_time"]
        hook = meta["hook_text"]
        st.write(f"Timestamp mil gaya: `{start}` se `{end}`")
        st.write(f"Hook: **{hook}**")

        st.write("3. 1:1 Square cropping aur text overlay render ho raha hai...")
        out_file = f"output/clip_{int(time.time())}.mp4"
        process_square_video(raw_file, start, end, hook, out_file)

        status.update(
            label="Square Clip Ready!", state="complete", expanded=False
        )

      st.success("Tada! Clip ready hai.")
      st.video(out_file)

      with open(out_file, "rb") as f:
        st.download_button(
            label="Download Square MP4",
            data=f,
            file_name="viral_square_clip.mp4",
            mime="video/mp4",
        )

    except Exception as e:
      st.error(f"Error aaya: {str(e)}")
      
