"""Potong video sumber jadi klip vertikal 9:16 lalu bakar subtitle."""
import os
from pathlib import Path

from clipper.reframe import blur_pad_graph
from clipper.styles import STYLES, SubtitleStyle
from clipper.transcript import (akhir_kalimat, buang_filler,
                                koreksi_istilah, rapikan_kapital)

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
W, H = 1080, 1920

def cut_cmd(src, start: float, end: float, out_mp4, *,
            filtergraph: str | None = None) -> list[str]:
    # -ss ditaruh sebelum -i: ffmpeg loncat langsung ke posisi, tidak mendekode dari awal.
    # Default: video sumber ditaruh di sepertiga atas, sisa layar diisi versi blur
    # (satu sumber kebenaran: reframe.blur_pad_graph).
    durasi = end - start
    fc = filtergraph if filtergraph is not None else blur_pad_graph(W, H)
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

def _kata_berwaktu(window, koreksi):
    """Ratakan seluruh segmen jadi daftar (kata, waktu). Potongan mentah VTT
    otomatis sering terbelah aneh; menyusun ulang dari kata membuat tiap baris
    subtitle utuh."""
    hasil = []
    for seg in window.segments:
        teks = koreksi_istilah(buang_filler(seg.text), koreksi)
        teks = teks.lstrip(" .,")
        kata = teks.split()
        if not kata:
            continue
        durasi = max(seg.end - seg.start, 0.001)
        for i, k in enumerate(kata):
            mulai = seg.start + durasi * i / len(kata)
            selesai = seg.start + durasi * (i + 1) / len(kata)
            hasil.append((k, mulai, selesai))
    return hasil

def _kelompokkan(kata_berwaktu, maks_karakter):
    """Kumpulkan kata jadi cue: berhenti saat kalimat selesai atau baris penuh."""
    cue, kini = [], []
    for k, mulai, selesai in kata_berwaktu:
        panjang = len(" ".join([w for w, _, _ in kini] + [k]))
        if kini and panjang > maks_karakter:
            cue.append(kini)
            kini = []
        kini.append((k, mulai, selesai))
        if akhir_kalimat(k):
            cue.append(kini)
            kini = []
    if kini:
        cue.append(kini)
    return cue

def write_srt(window, out_path, maks_karakter: int = 46, koreksi: dict | None = None) -> None:
    kata = _kata_berwaktu(window, koreksi)
    baris, n = [], 0
    mulai_kalimat = True
    for kelompok in _kelompokkan(kata, maks_karakter):
        if not kelompok:
            continue
        teks = " ".join(w for w, _, _ in kelompok)
        teks = rapikan_kapital(teks, awal_kalimat=mulai_kalimat)
        mulai_kalimat = akhir_kalimat(teks)
        n += 1
        mulai = kelompok[0][1] - window.start
        selesai = kelompok[-1][2] - window.start
        baris += [str(n), f"{_ts(mulai)} --> {_ts(selesai)}", teks, ""]
    Path(out_path).write_text("\n".join(baris), encoding="utf-8")

def burn_cmd(in_mp4, srt_name: str, out_mp4, *,
             style: SubtitleStyle = STYLES["lato"]) -> list[str]:
    return [FFMPEG, "-y", "-i", str(in_mp4),
            "-vf", f"subtitles={srt_name}:force_style='{style.force_style}'",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "copy", str(out_mp4)]
