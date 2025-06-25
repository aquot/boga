from flask import Flask, render_template, request, redirect, url_for, jsonify
from werkzeug.utils import secure_filename
from apscheduler.schedulers.background import BackgroundScheduler
import os
import json
import subprocess
import signal
import datetime
from config import *

app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# --- Helper Functions ---
def load_metadata(filename):
    meta_path = os.path.join(METADATA_DIR, f"{filename}.json")
    if not os.path.exists(meta_path):
        return {}
    with open(meta_path) as f:
        return json.load(f)

def save_metadata(filename, data):
    meta_path = os.path.join(METADATA_DIR, f"{filename}.json")
    with open(meta_path, "w") as f:
        json.dump(data, f)

def get_video_status(meta):
    now = datetime.datetime.now()
    try:
        start_time = datetime.datetime.strptime(meta.get("start_time"), "%Y-%m-%d %H:%M")
        end_time = datetime.datetime.strptime(meta.get("end_time"), "%Y-%m-%d %H:%M")
    except:
        return "Invalid"

    if now < start_time:
        return "Scheduled"
    elif start_time <= now <= end_time:
        return "Streaming"
    else:
        return "Selesai"

def detect_and_download(url):
    if "mega.nz" in url:
        return download_with_mega(url)
    elif "dropbox.com" in url:
        return download_with_dropbox(url)
    else:
        raise ValueError("Platform tidak didukung")

def download_with_mega(url):
    filename = url.split("/")[-1].split("#")[0]
    cmd = ["megadl", url, "--path", DOWNLOAD_DIR]
    subprocess.Popen(cmd)
    return filename

def download_with_dropbox(url):
    direct_link = url.replace("www.dropbox.com", "dl.dropboxusercontent.com").replace("?dl=0", "?dl=1")
    filename = direct_link.split("/")[-1].split("?")[0]
    path = os.path.join(DOWNLOAD_DIR, filename)

    import requests
    with requests.get(direct_link, stream=True) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    return filename

def schedule_streaming_tasks():
    scheduler.remove_all_jobs()
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith((".mp4", ".mkv")):
            meta = load_metadata(f)
            if "start_time" in meta:
                start_time = datetime.datetime.strptime(meta["start_time"], "%Y-%m-%d %H:%M")
                def job_func(fn=f):
                    start_streaming_ffmpeg(fn)
                scheduler.add_job(job_func, 'date', run_date=start_time)

def start_streaming_ffmpeg(filename):
    meta = load_metadata(filename)
    video_path = os.path.join(DOWNLOAD_DIR, filename)
    full_rtmp = f"{meta['rtmp_url']}/{meta['stream_key']}"

    cmd = f'ffmpeg -re {"-stream_loop -1 " if meta.get("loop") else ""}'
    cmd += f'-i "{video_path}" '
    cmd += '-c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 128k -vf scale=1280:720 '
    cmd += f'-f flv "{full_rtmp}" > /dev/null 2>&1 & echo $!'

    pid = int(subprocess.check_output(cmd, shell=True))
    save_pid(pid, filename)

def save_pid(pid, filename):
    if os.path.exists(FFMPEG_PIDS_FILE):
        with open(FFMPEG_PIDS_FILE) as f:
            pids = json.load(f)
    else:
        pids = {}

    pids[filename] = pid
    with open(FFMPEG_PIDS_FILE, "w") as f:
        json.dump(pids, f)

def get_pid(filename):
    if not os.path.exists(FFMPEG_PIDS_FILE):
        return None
    with open(FFMPEG_PIDS_FILE) as f:
        pids = json.load(f)
    return pids.get(filename)

def kill_process(filename):
    pid = get_pid(filename)
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            print("Error killing process:", e)

    # Hapus PID dari file
    if os.path.exists(FFMPEG_PIDS_FILE):
        with open(FFMPEG_PIDS_FILE) as f:
            pids = json.load(f)
        if filename in pids:
            del pids[filename]
        with open(FFMPEG_PIDS_FILE, "w") as f:
            json.dump(pids, f)

# --- Routes ---
@app.route("/", methods=["GET"])
def index():
    videos = []
    for f in os.listdir(DOWNLOAD_DIR):
        if f.endswith((".mp4", ".mkv")):
            meta_path = os.path.join(METADATA_DIR, f"{f}.json")
            if not os.path.exists(meta_path):
                meta = {}
            else:
                with open(meta_path) as jf:
                    meta = json.load(jf)

            meta["filename"] = f
            meta["status"] = get_video_status(meta)
            videos.append(meta)

    # Urutkan berdasarkan waktu mulai
    videos.sort(key=lambda x: x.get("start_time", "9999-99-99 99:99"))

    return render_template("index.html", videos=videos)

@app.route("/download", methods=["POST"])
def download():
    url = request.form.get("url")
    try:
        downloaded_file = detect_and_download(url)
        schedule_streaming_tasks()
        return redirect(url_for("index"))
    except Exception as e:
        return str(e), 500

@app.route("/upload", methods=["POST"])
def upload_file():
    if 'file' not in request.files:
        return "Tidak ada file yang dipilih", 400

    file = request.files['file']
    if file.filename == '':
        return "Nama file kosong", 400

    if allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(DOWNLOAD_DIR, filename))
        return redirect(url_for("index"))

    return "Format file tidak didukung", 400

@app.route("/schedule/<filename>", methods=["POST"])
def schedule(filename):
    loop = "loop" in request.form
    title = request.form.get("title", "Untitled")
    rtmp_url = request.form.get("rtmp_url")
    stream_key = request.form.get("stream_key")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    meta = {
        "title": title,
        "rtmp_url": rtmp_url,
        "stream_key": stream_key,
        "start_time": start_time,
        "end_time": end_time,
        "loop": loop
    }

    save_metadata(filename, meta)
    schedule_streaming_tasks()
    return redirect(url_for("index"))

@app.route("/stop/<filename>")
def stop_stream(filename):
    kill_process(filename)
    return redirect(url_for("index"))

@app.route("/delete/<filename>")
def delete_video(filename):
    path = os.path.join(DOWNLOAD_DIR, filename)
    meta_path = os.path.join(METADATA_DIR, f"{filename}.json")
    if os.path.exists(path):
        os.remove(path)
    if os.path.exists(meta_path):
        os.remove(meta_path)
    kill_process(filename)
    return redirect(url_for("index"))

@app.route("/progress")
def check_progress():
    if not os.path.exists(UPLOAD_PROGRESS_FILE):
        return jsonify({})
    with open(UPLOAD_PROGRESS_FILE) as f:
        return jsonify(json.load(f))

if __name__ == "__main__":
    schedule_streaming_tasks()
    app.run(debug=True)
