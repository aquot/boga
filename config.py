import os

# Path direktori
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
METADATA_DIR = os.path.join(BASE_DIR, "metadata")
UPLOAD_PROGRESS_FILE = os.path.join(BASE_DIR, "upload_progress.json")
FFMPEG_PIDS_FILE = os.path.join(BASE_DIR, "ffmpeg_pids.json")

# Pastikan folder ada
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(METADATA_DIR, exist_ok=True)

# Format ekstensi video yang diizinkan
ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov'}

# Fungsi utilitas
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
