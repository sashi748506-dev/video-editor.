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
    "Paste YouTube URL or Upload MP4 → Gemini finds viral moment → Auto-crops"
    " 1:1"
)

# API Key Handling
try:
  api_key = st.secrets.get("GEMINI_API_KEY", None)
except Exception:
  api_key = None

if not api_key:
  api_key = st.sidebar.text_input(
      "Gemini API Key",
      type="password",
      help="Get free key from aistudio.google.com",
  )

# Input method: Link or Direct File
tab1, tab2 = st.tabs(["🔗 YouTube Link", "📁 Upload Video File"])
url = None
uploaded_file = None

with tab1:
  url = st.text_input(
      "YouTube Video Link:",
      placeholder="https://www.youtube.com/watch?v=...",
  )

with tab2:
  uploaded_file = st.file_uploader("Apni raw MP4 video yahan drop karo", type=["mp4", "mov"])


def download_video(yt_url):
  out_tmpl = "downloads/%(id)s.%(ext)s"
  # Bypass 403 Forbidden using mobile player client
  ydl_opts = {
      "format": "best[ext=mp4]/best",
      "outtmpl": out_tmpl,
      "quiet": True,
      "no_warnings": True,
      "extractor_args": {"youtube": {"player_client": ["android", "ios", "tv"]}},
      "http_headers": {
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
              " (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
          )
      },
  }
  try:
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      info = ydl.extract_info(yt_url, download=True)
      filename = ydl.prepare_filename(info)
      return filename
  except Exception as e:
    raise RuntimeError(f"YouTube download failed: {str(e)}")


def analyze_with_gemini(video_path):
  genai.configure(api_key=api_key)

  with st.spinner("Gemini API video analyze kar raha hai..."):
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
      time.sleep(3)
      video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
      raise ValueError("Video processing failed on Gemini.")

    model = genai.GenerativeModel(model_name="gemini-1.5-flash")
    prompt = """
        Analyze this video and identify the single most viral, high-retention 30 to 45-second segment.
        The segment MUST be suitable for a 1:1 square crop where the speaker/action is centered.
        
        Return ONLY a raw JSON object with no markdown backticks or explanations:
        {
          "start_time": "00:01:15",
          "end_time": "00:01:50",
          "hook_text": "CATCHY BOLD HOOK"
        }

        Constraint: hook_text MUST be a concise 3 to 5 word catchy hook in ALL CAPS.
        """
    response = model.generate_content([video_file, prompt])

    # Safely clean response text
    raw_text = response.text.strip()
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
    raw_text = re.sub(r"\s*```$", "", raw_text).strip()

    # Extract JSON string block using regex if present
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
      raw_text = match.group(0)

    parsed_json = json.loads(raw_text)

    # Cleanup file from Gemini API storage
    try:
      genai.delete_file(video_file.name)
    except Exception:
      pass

    return parsed_json


def clean_directory(dir_path):
  """Removes files in directory to prevent disk bloat."""
  if os.path.exists(dir_path):
    for f in os.listdir(dir_path):
      file_p = os.path.join(dir_path, f)
      try:
        if os.path.isfile(file_p):
          os.remove(file_p)
      except Exception:
        pass


def process_square_video(input_path, start, end, hook, output_path):
  clean_hook = (
      hook.replace("\\", "\\\\")
      .replace("'", "\\'")
      .replace(":", "\\:")
      .replace("%", "\\%")
  )
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
  elif not url and not uploaded_file:
    st.error("YouTube URL daalo ya file upload karo!")
  else:
    os.makedirs("downloads", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    raw_file = None
    out_file = None
    try:
      with st.status("Ship mode activated...", expanded=True) as status:
        if uploaded_file is not None:
          st.write("1. Uploaded video load ho rahi hai...")
          raw_file = os.path.join("downloads", uploaded_file.name)
          with open(raw_file, "wb") as f:
            f.write(uploaded_file.getbuffer())
        else:
          st.write("1. Video download ho rahi hai (Bypassing 403)...")
          try:
            raw_file = download_video(url)
          except Exception as dl_err:
            st.error(f"YouTube Download Error: {dl_err}")
            st.warning(
                "YouTube block active. Please download the video manually and"
                " use the 'Upload Video File' tab!"
            )
            st.stop()

        st.write("2. AI se viral hook aur timestamps dhoondh rahe hain...")
        meta = analyze_with_gemini(raw_file)

        start = meta.get("start_time", "00:00:00")
        end = meta.get("end_time", "00:00:30")
        hook = meta.get("hook_text", "VIRAL MOMENT")
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
    finally:
      # Clean up intermediate downloaded/uploaded raw input file and temporary directory contents
      if raw_file and os.path.exists(raw_file):
        try:
          os.remove(raw_file)
        except Exception:
          pass
      clean_directory("downloads")
        
