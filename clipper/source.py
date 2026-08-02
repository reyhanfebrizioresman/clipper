"""Ambil video sumber campaign beserta subtitlenya kalau tersedia.

Video dan subtitle sengaja diunduh dengan dua perintah terpisah: YouTube
membalas 429 (Too Many Requests) kalau subtitle diminta beruntun, dan kalau
digabung, kegagalan subtitle ikut menggagalkan unduhan videonya.
"""
import sys
from pathlib import Path

def _yt_dlp() -> list[str]:
    # dipanggil sebagai modul interpreter yang sedang jalan: di server yt-dlp
    # hanya terpasang di dalam .venv dan tidak ada di PATH global
    return [sys.executable, "-m", "yt_dlp"]

def download_cmd(url: str, out_dir) -> list[str]:
    return _yt_dlp() + [
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--retries", "3",
        "-o", str(Path(out_dir) / "%(id)s.%(ext)s"),
        url]

def subtitle_cmd(url: str, out_dir) -> list[str]:
    return _yt_dlp() + [
        "--skip-download",
        "--write-auto-subs", "--write-subs",
        "--sub-langs", "id",
        "--convert-subs", "vtt",
        "--sleep-requests", "2",
        "--retries", "2",
        "-o", str(Path(out_dir) / "%(id)s.%(ext)s"),
        url]
