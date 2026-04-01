#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Auto Upload - GitHub Actions
Drive থেকে video+audio নামায়, merge করে, YouTube-এ upload করে।
"""

import os
import json
import random
import subprocess
import requests
import tempfile
import sys
from pathlib import Path

# ========== CONFIG ==========
YT_CLIENT_ID     = os.environ["YT_CLIENT_ID"]
YT_CLIENT_SECRET = os.environ["YT_CLIENT_SECRET"]
YT_REFRESH_TOKEN = os.environ["YT_REFRESH_TOKEN"]

DRIVE_CLIENT_ID     = os.environ["DRIVE_CLIENT_ID"]
DRIVE_CLIENT_SECRET = os.environ["DRIVE_CLIENT_SECRET"]
DRIVE_REFRESH_TOKEN = os.environ["DRIVE_REFRESH_TOKEN"]

VIDEO_FOLDER_ID = os.environ["VIDEO_FOLDER_ID"]
AUDIO_FOLDER_ID = os.environ.get("AUDIO_FOLDER_ID", "")
YT_PRIVACY      = os.environ.get("YT_PRIVACY", "public")

TEMP_DIR = Path(tempfile.mkdtemp())

def log(msg):
    print(f"[AUTO] {msg}", flush=True)

# ========== TOKEN REFRESH ==========
def refresh_token(client_id, client_secret, refresh_token):
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    })
    r.raise_for_status()
    return r.json()["access_token"]

def get_yt_token():
    log("YouTube token refresh হচ্ছে...")
    token = refresh_token(YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN)
    log("YouTube token ✅")
    return token

def get_drive_token():
    log("Drive token refresh হচ্ছে...")
    token = refresh_token(DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, DRIVE_REFRESH_TOKEN)
    log("Drive token ✅")
    return token

# ========== DRIVE ==========
def list_drive_folder(folder_id, drive_token, file_exts):
    url = f"https://www.googleapis.com/drive/v3/files"
    params = {
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,mimeType,size)",
        "pageSize": 100
    }
    r = requests.get(url, params=params, headers={"Authorization": f"Bearer {drive_token}"})
    r.raise_for_status()
    files = r.json().get("files", [])
    return [f for f in files if any(f["name"].lower().endswith(ext) for ext in file_exts)]

def download_from_drive(file_id, file_name, drive_token):
    log(f"নামানো হচ্ছে: {file_name}")
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    r = requests.get(url, headers={"Authorization": f"Bearer {drive_token}"}, stream=True)
    r.raise_for_status()
    out_path = TEMP_DIR / file_name
    with open(out_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024*1024):
            f.write(chunk)
    size_mb = out_path.stat().st_size / 1024 / 1024
    log(f"নামানো হয়েছে: {file_name} ({size_mb:.1f}MB)")
    return out_path

# ========== FFMPEG ==========
def get_duration(file_path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(file_path)],
            capture_output=True, text=True, timeout=30
        )
        return float(result.stdout.strip())
    except:
        return 0

def merge_video_audio(video_paths, audio_path, output_path):
    """Multiple video clips + one audio → merged output"""
    
    if len(video_paths) == 1:
        concat_path = video_paths[0]
    else:
        # Concat list file বানাও
        concat_list = TEMP_DIR / "concat.txt"
        with open(concat_list, "w") as f:
            for vp in video_paths:
                f.write(f"file '{vp}'\n")
        concat_path = TEMP_DIR / "concat_out.mp4"
        subprocess.run([
            "ffmpeg", "-f", "concat", "-safe", "0",
            "-i", str(concat_list), "-c:v", "copy", "-y", str(concat_path)
        ], check=True, timeout=120, capture_output=True)
        log(f"Video concat done ✅ ({len(video_paths)} clips)")

    # Merge audio
    subprocess.run([
        "ffmpeg",
        "-i", str(concat_path),
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac",
        "-shortest", "-y", str(output_path)
    ], check=True, timeout=180, capture_output=True)
    log("Audio merge done ✅")

def mute_video(input_path, output_path):
    subprocess.run([
        "ffmpeg", "-i", str(input_path),
        "-an", "-c:v", "copy", "-y", str(output_path)
    ], check=True, timeout=60, capture_output=True)

# ========== YOUTUBE UPLOAD ==========
def upload_to_youtube(video_path, title, yt_token):
    log(f"YouTube-এ upload হচ্ছে: {title}")
    
    file_size = video_path.stat().st_size
    metadata = {
        "snippet": {
            "title": title[:100],
            "description": "ইসলামিক ওয়াজ | Islamic Waz\n\n#shorts #islamicshorts #waz #bangla #bangladesh #viral #islam #quran",
            "tags": ["shorts", "islamic shorts", "bangla waz", "waz", "islam", "bangladesh", "viral", "quran"],
            "categoryId": "22"
        },
        "status": {
            "privacyStatus": YT_PRIVACY,
            "selfDeclaredMadeForKids": False
        }
    }

    # Resumable upload init
    init_r = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization": f"Bearer {yt_token}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size)
        },
        json=metadata
    )
    init_r.raise_for_status()
    upload_url = init_r.headers["Location"]

    # Upload video
    with open(video_path, "rb") as f:
        up_r = requests.put(
            upload_url,
            headers={"Content-Type": "video/mp4", "Content-Length": str(file_size)},
            data=f
        )
    up_r.raise_for_status()
    video_id = up_r.json()["id"]
    log(f"Upload সফল ✅ https://youtu.be/{video_id}")
    return video_id

# ========== MAIN ==========
def main():
    log("=" * 50)
    log("YouTube Auto Upload শুরু হচ্ছে...")
    log("=" * 50)

    # Tokens
    yt_token    = get_yt_token()
    drive_token = get_drive_token()

    # List videos
    log(f"Video folder থেকে list করা হচ্ছে...")
    videos = list_drive_folder(VIDEO_FOLDER_ID, drive_token, [".mp4", ".mov", ".avi", ".mkv", ".webm"])
    if not videos:
        log("❌ Drive-এ কোনো video নেই!")
        sys.exit(1)
    log(f"পাওয়া গেছে: {len(videos)} টি video")

    # List audios
    audios = []
    if AUDIO_FOLDER_ID:
        log(f"Audio folder থেকে list করা হচ্ছে...")
        audios = list_drive_folder(AUDIO_FOLDER_ID, drive_token, [".mp3", ".m4a", ".wav", ".aac", ".ogg"])
        log(f"পাওয়া গেছে: {len(audios)} টি audio")

    if not audios:
        log("❌ Audio নেই — audio folder check করো!")
        sys.exit(1)

    # Pick random audio
    audio_file = random.choice(audios)
    audio_path = download_from_drive(audio_file["id"], audio_file["name"], drive_token)
    audio_duration = get_duration(audio_path)
    log(f"Audio duration: {audio_duration:.1f} সেকেন্ড")

    if audio_duration <= 0:
        log("❌ Audio duration মাপা গেলো না!")
        sys.exit(1)

    # Collect videos to fill audio duration
    shuffled_videos = random.sample(videos, len(videos))
    selected_video_paths = []
    total_duration = 0.0

    for video in shuffled_videos:
        if total_duration >= audio_duration:
            break

        vpath = download_from_drive(video["id"], video["name"], drive_token)
        
        # Mute video
        muted_path = TEMP_DIR / f"muted_{video['id']}.mp4"
        try:
            mute_video(vpath, muted_path)
            work_path = muted_path
        except:
            work_path = vpath

        vdur = get_duration(work_path)
        if vdur <= 0:
            log(f"Skip: {video['name']} (duration মাপা গেলো না)")
            continue

        # শেষ clip trim করো যদি exceed করে
        if total_duration + vdur > audio_duration:
            trim_dur = audio_duration - total_duration
            if trim_dur > 0.5:
                trimmed = TEMP_DIR / f"trimmed_{video['id']}.mp4"
                subprocess.run([
                    "ffmpeg", "-i", str(work_path),
                    "-t", str(trim_dur), "-c:v", "copy", "-y", str(trimmed)
                ], check=True, timeout=60, capture_output=True)
                selected_video_paths.append(trimmed)
                log(f"Trimmed: {video['name']} → {trim_dur:.1f}s")
            break

        selected_video_paths.append(work_path)
        total_duration += vdur
        log(f"Added: {video['name']} ({vdur:.1f}s) | Total: {total_duration:.1f}s")

    if not selected_video_paths:
        log("❌ কোনো video process করা গেলো না!")
        sys.exit(1)

    log(f"মোট {len(selected_video_paths)} টি clip নেওয়া হয়েছে")

    # Merge
    final_path = TEMP_DIR / "final_output.mp4"
    merge_video_audio(selected_video_paths, audio_path, final_path)

    # Title from audio filename
    raw_title = audio_file["name"]
    raw_title = raw_title.rsplit(".", 1)[0]  # extension বাদ
    raw_title = raw_title.replace("_", " ").replace("-", " ").strip()
    if not raw_title:
        raw_title = "ইসলামিক ওয়াজ"

    title_variants = [
        raw_title,
        f"{raw_title} | কলিজা কাপানো কথা",
        f"{raw_title} | জীবন বদলে যাবে",
        f"{raw_title} | একবার শুনুন",
    ]
    title = random.choice(title_variants)[:100]

    # Upload
    video_id = upload_to_youtube(final_path, title, yt_token)

    log("=" * 50)
    log(f"✅ সব শেষ! Video ID: {video_id}")
    log(f"🔗 https://youtu.be/{video_id}")
    log("=" * 50)

if __name__ == "__main__":
    main()
