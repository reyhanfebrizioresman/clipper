"""Potong video sumber jadi klip vertikal 9:16 lalu bakar subtitle."""
import os
from pathlib import Path

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
W, H = 1080, 1920

def cut_cmd(src, start: float, end: float, out_mp4) -> list[str]:
    # -ss ditaruh sebelum -i: ffmpeg loncat langsung ke posisi, tidak mendekode dari awal.
    # Video sumber (biasanya 16:9) ditaruh di tengah, sisa layar diisi versi blur.
    durasi = end - start
    fc = (
        "[0:v]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},boxblur=40:2[bg];"
        f"[fgsrc]scale={W}:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
    )
    return [FFMPEG, "-y", "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{durasi:.3f}",
            "-filter_complex", fc, "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", str(out_mp4)]

def _ts(detik: float) -> str:
    ms = int(round(detik * 1000))
    j, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    d, ms = divmod(ms, 1000)
    return f"{j:02d}:{m:02d}:{d:02d},{ms:03d}"

def write_srt(window, out_path) -> None:
    # waktu digeser relatif ke awal klip
    baris = []
    for n, seg in enumerate(window.segments, 1):
        baris += [str(n),
                  f"{_ts(seg.start - window.start)} --> {_ts(seg.end - window.start)}",
                  seg.text, ""]
    Path(out_path).write_text("\n".join(baris), encoding="utf-8")

def burn_cmd(in_mp4, srt_name: str, out_mp4) -> list[str]:
    # libass menskalakan angka style ke tinggi referensi 288 (faktor 1920/288 ~ 6,7):
    # FontSize=13 ~ 87 px, MarginV=55 ~ 367 px dari bawah — TikTok menaruh UI lebih
    # tinggi dari YouTube Shorts, jadi marginnya sengaja lebih besar.
    style = ("FontSize=13,PrimaryColour=&HFFFFFF&,OutlineColour=&H000000&,"
             "Outline=2,MarginV=55,Alignment=2")
    return [FFMPEG, "-y", "-i", str(in_mp4),
            "-vf", f"subtitles={srt_name}:force_style='{style}'",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "copy", str(out_mp4)]
