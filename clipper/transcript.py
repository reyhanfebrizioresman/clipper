"""Baca transkrip VTT/SRT jadi segmen berwaktu."""
import re
from dataclasses import dataclass

TAG = re.compile(r"<[^>]*>")          # <00:00:03.440>, <c>, </c>
TIME_LINE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})"
)

@dataclass
class Segment:
    start: float
    end: float
    text: str

def _detik(jam: str, menit: str, detik: str, milidetik: str) -> float:
    return int(jam) * 3600 + int(menit) * 60 + int(detik) + int(milidetik.ljust(3, "0")) / 1000

def parse(isi: str) -> list[Segment]:
    segmen: list[Segment] = []
    start = end = None
    baris_teks: list[str] = []

    def tutup() -> None:
        # VTT otomatis YouTube memakai rolling caption: tiap cue mengulang baris
        # sebelumnya lalu menambah baris baru. Yang diambil hanya bagian barunya.
        if start is None or not baris_teks:
            return
        teks = " ".join(baris_teks).strip()
        teks = re.sub(r"\s+", " ", teks)
        if not teks:
            return
        if segmen:
            sebelum = segmen[-1].text
            if teks == sebelum:
                return
            if teks.startswith(sebelum):
                teks = teks[len(sebelum):].strip()
            elif sebelum.endswith(teks):
                return
            if not teks:
                return
        segmen.append(Segment(start, end, teks))

    for baris in isi.splitlines():
        cocok = TIME_LINE.search(baris)
        if cocok:
            tutup()
            baris_teks.clear()
            g = cocok.groups()
            start, end = _detik(*g[:4]), _detik(*g[4:])
            continue
        bersih = baris.strip()
        if not bersih or bersih.isdigit() or bersih.upper().startswith("WEBVTT"):
            if not bersih:
                tutup()
                start = end = None
                baris_teks.clear()
            continue
        if start is not None:
            baris_teks.append(TAG.sub("", bersih).strip())
    tutup()
    return segmen
