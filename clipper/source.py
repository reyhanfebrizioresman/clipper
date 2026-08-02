"""Ambil video sumber campaign beserta subtitlenya kalau tersedia."""
import sys
from pathlib import Path

def download_cmd(url: str, out_dir) -> list[str]:
    # Dipanggil sebagai modul python interpreter yang sedang jalan: di server
    # yt-dlp hanya terpasang di dalam .venv dan tidak ada di PATH global.
    # Subtitle otomatis dipakai duluan — kalau ada, Whisper tidak perlu jalan
    # (transkripsi CPU makan belasan menit per jam video).
    return [sys.executable, "-m", "yt_dlp",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "id,id-ID,en",
            "--convert-subs", "vtt",
            "-o", str(Path(out_dir) / "%(id)s.%(ext)s"),
            url]
