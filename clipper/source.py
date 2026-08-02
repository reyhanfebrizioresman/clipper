"""Ambil video sumber campaign beserta subtitlenya kalau tersedia."""
from pathlib import Path

def download_cmd(url: str, out_dir) -> list[str]:
    # Subtitle otomatis dipakai duluan: kalau ada, tidak perlu jalankan Whisper
    # (transkripsi di CPU server makan waktu belasan menit per jam video).
    return ["yt-dlp",
            "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "--write-auto-subs", "--write-subs",
            "--sub-langs", "id,id-ID,en",
            "--convert-subs", "vtt",
            "-o", str(Path(out_dir) / "%(id)s.%(ext)s"),
            url]
