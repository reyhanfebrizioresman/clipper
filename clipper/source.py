"""Ambil video sumber campaign beserta subtitlenya kalau tersedia.

Video dan subtitle sengaja diunduh dengan dua perintah terpisah: YouTube
membalas 429 (Too Many Requests) kalau subtitle diminta beruntun, dan kalau
digabung, kegagalan subtitle ikut menggagalkan unduhan videonya.
"""
import os
import shutil
import sys
from pathlib import Path

def _deno() -> str | None:
    """Lokasi Deno: CLIPPER_DENO > PATH > ~/.deno/bin/deno (lokasi installer resmi,
    yang tidak ada di PATH sesi SSH non-interaktif seperti server MCP)."""
    for kandidat in (os.environ.get("CLIPPER_DENO"), shutil.which("deno"),
                     str(Path.home() / ".deno" / "bin" / "deno")):
        if kandidat and Path(kandidat).is_file():
            return kandidat
    return None

def _yt_dlp() -> list[str]:
    # dipanggil sebagai modul interpreter yang sedang jalan: di server yt-dlp
    # hanya terpasang di dalam .venv dan tidak ada di PATH global
    cmd = [sys.executable, "-m", "yt_dlp"]
    # YouTube kini mewajibkan pemecah tantangan JS (yt-dlp-ejs + Deno); tanpa itu
    # subtitle gagal dan format video dibatasi
    deno = _deno()
    if deno:
        cmd += ["--js-runtimes", f"deno:{deno}"]
    return cmd

def download_cmd(url: str, out_dir) -> list[str]:
    return _yt_dlp() + [
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--retries", "3",
        "--no-playlist",  # URL watch?v=..&list=.. jangan unduh satu playlist
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
        "--no-playlist",
        "-o", str(Path(out_dir) / "%(id)s.%(ext)s"),
        url]
