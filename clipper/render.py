"""Potong video sumber jadi klip vertikal 9:16 lalu bakar subtitle."""
import os
from dataclasses import dataclass
from pathlib import Path

from clipper.reframe import blur_pad_graph
from clipper.styles import STYLES, SubtitleStyle
from clipper.transcript import (akhir_kalimat, buang_filler,
                                koreksi_istilah, rapikan_kapital)

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")
W, H = 1080, 1920
# preset libx264 -> preset NVENC yang kira-kira setara (p1 tercepat ... p7 terbaik)
NVENC_PRESET = {"ultrafast": "p1", "superfast": "p2", "veryfast": "p3", "faster": "p4",
                "fast": "p5", "medium": "p6", "slow": "p7"}
# preset libx264 -> mode kualitas AMF (AMD)
AMF_KUALITAS = {"ultrafast": "speed", "superfast": "speed", "veryfast": "balanced",
                "faster": "balanced", "fast": "quality", "medium": "quality", "slow": "quality"}
VAAPI_DEVICE = "/dev/dri/renderD128"
# encoder video yang didukung, urutan = prioritas saat 'otomatis'
ENCODER_GPU = ("nvenc", "videotoolbox", "amf", "vaapi")


@dataclass(frozen=True)
class Encode:
    """Cara encode satu encoder: argumen sebelum -i, akhiran filter video, argumen codec."""
    sebelum_input: tuple[str, ...]
    akhiran_filter: str          # "" atau mis. "format=nv12,hwupload" (VAAPI butuh frame di GPU)
    codec: tuple[str, ...]


def encode_spec(encoder: str, preset: str, crf: int) -> Encode:
    """encoder: 'cpu' (libx264), 'nvenc' (NVIDIA), 'videotoolbox' (Apple), 'amf' (AMD,
    terutama Windows), atau 'vaapi[:/dev/dri/renderDxxx]' (AMD/Intel di Linux).
    CRF diterjemahkan ke parameter kualitas tetap masing-masing encoder."""
    q = int(crf)
    nama, _, alat = encoder.partition(":")
    if nama == "nvenc":
        return Encode((), "", ("-c:v", "h264_nvenc", "-preset", NVENC_PRESET.get(preset, "p4"),
                               "-rc", "vbr", "-cq", str(q), "-b:v", "0", "-pix_fmt", "yuv420p"))
    if nama == "videotoolbox":
        # -q:v 1..100 (besar = bagus); CRF 23 ~ 60. Konstan-kualitas butuh Apple Silicon.
        return Encode((), "", ("-c:v", "h264_videotoolbox", "-q:v",
                               str(max(1, min(100, round(100 - q * 1.75)))),
                               "-pix_fmt", "yuv420p"))
    if nama == "amf":
        return Encode((), "", ("-c:v", "h264_amf", "-quality", AMF_KUALITAS.get(preset, "balanced"),
                               "-rc", "cqp", "-qp_i", str(q), "-qp_p", str(q),
                               "-pix_fmt", "yuv420p"))
    if nama == "vaapi":
        return Encode(("-vaapi_device", alat or VAAPI_DEVICE), "format=nv12,hwupload",
                      ("-c:v", "h264_vaapi", "-rc_mode", "CQP", "-qp", str(q)))
    return Encode((), "", ("-c:v", "libx264", "-preset", preset, "-crf", str(q),
                           "-pix_fmt", "yuv420p"))


def video_args(encoder: str, preset: str, crf: int) -> list[str]:
    return list(encode_spec(encoder, preset, crf).codec)


def uji_encode_cmd(encoder: str) -> list[str]:
    """Encode 0,2 dtk warna hitam dengan argumen yang sama persis dengan render sungguhan:
    bila ini berhasil, encoder (driver, perangkat, opsi) benar-benar bisa dipakai."""
    e = encode_spec(encoder, "veryfast", 23)
    vf = ["-vf", e.akhiran_filter] if e.akhiran_filter else []
    return [FFMPEG, "-hide_banner", "-loglevel", "error", *e.sebelum_input, "-f", "lavfi",
            "-i", "color=c=black:s=320x240:d=0.2", *vf, *e.codec, "-f", "null", "-"]

def cut_cmd(src, start: float, end: float, out_mp4, *,
            filtergraph: str | None = None, crf: int = 23, preset: str = "veryfast",
            audio_kbps: int = 160, encoder: str = "cpu") -> list[str]:
    # -ss ditaruh sebelum -i: ffmpeg loncat langsung ke posisi, tidak mendekode dari awal.
    # Default: video sumber ditaruh di sepertiga atas, sisa layar diisi versi blur
    # (satu sumber kebenaran: reframe.blur_pad_graph).
    durasi = end - start
    fc = filtergraph if filtergraph is not None else blur_pad_graph(W, H)
    e = encode_spec(encoder, preset, crf)
    keluaran = "[v]"
    if e.akhiran_filter:
        fc, keluaran = f"{fc};[v]{e.akhiran_filter}[vgpu]", "[vgpu]"
    return [FFMPEG, "-y", *e.sebelum_input, "-ss", f"{start:.3f}", "-i", str(src),
            "-t", f"{durasi:.3f}", "-filter_complex", fc, "-map", keluaran, "-map", "0:a?",
            *e.codec,
            "-c:a", "aac", "-b:a", f"{int(audio_kbps)}k", "-ar", "44100", "-ac", "2", str(out_mp4)]

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
             style: SubtitleStyle = STYLES["lato"], crf: int = 23,
             preset: str = "veryfast", encoder: str = "cpu") -> list[str]:
    e = encode_spec(encoder, preset, crf)
    vf = f"subtitles={srt_name}:force_style='{style.force_style}'"
    if e.akhiran_filter:
        vf += "," + e.akhiran_filter
    return [FFMPEG, "-y", *e.sebelum_input, "-i", str(in_mp4), "-vf", vf, *e.codec,
            "-c:a", "copy", str(out_mp4)]
