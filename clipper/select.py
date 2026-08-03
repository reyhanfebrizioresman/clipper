"""Pilih potongan (window) layak-klip dari transkrip.

Potongan selalu dimulai dan diakhiri di batas segmen supaya tidak memutus
kalimat di tengah — aturan campaign melarang potongan yang mengubah makna.
"""
import re
from dataclasses import dataclass

from clipper.transcript import Segment

AKHIR_KALIMAT = (".", "!", "?", "…")
# kata pengisi khas transkrip otomatis — dibuang dari caption saja, tidak dari subtitle
FILLER = re.compile(r"\b(ee+|eh+|emm+|hmm+|anu)\b[,]?\s*", re.IGNORECASE)

@dataclass
class Window:
    start: float
    end: float
    text: str
    segments: list

def _mulai_kalimat(segments: list[Segment], i: int) -> bool:
    # subtitle otomatis dipecah per beberapa kata, jadi "batas segmen" saja tidak
    # cukup — klip bisa dibuka dengan penggalan seperti "gini" atau "Iya."
    return i == 0 or segments[i - 1].text.rstrip().endswith(AKHIR_KALIMAT)

def build_windows(segments: list[Segment], min_s: float, max_s: float) -> list[Window]:
    jendela: list[Window] = []
    i = 0
    while i < len(segments):
        if not _mulai_kalimat(segments, i):
            i += 1
            continue
        j = i
        while j < len(segments) and segments[j].end - segments[i].start <= max_s:
            j += 1
        # j sekarang segmen pertama yang membuat durasi lewat batas
        if j > i and segments[j - 1].end - segments[i].start >= min_s:
            dipakai = segments[i:j]
            jendela.append(Window(start=dipakai[0].start, end=dipakai[-1].end,
                                  text=" ".join(s.text for s in dipakai),
                                  segments=dipakai))
            i = j
        else:
            i += 1
    return jendela

def rank(windows: list[Window], keywords: list[str]) -> list[Window]:
    kunci = [k.lower() for k in keywords]

    def skor(w: Window) -> tuple:
        teks = w.text.lower()
        return (-sum(teks.count(k) for k in kunci), w.start)

    return sorted(windows, key=skor)

def hook(window: Window, min_kata: int = 5) -> str:
    """Kalimat pembuka untuk caption — cari kalimat utuh pertama yang cukup
    berisi, bukan penggalan seperti "gini" atau "Iya."."""
    def rapikan(s: str) -> str:
        s = FILLER.sub("", s)
        s = re.sub(r"\s+", " ", s).strip(" ,")
        return s[:1].upper() + s[1:] if s else s

    kalimat = [k.strip() for k in re.split(r"(?<=[.!?…])\s+", window.text) if k.strip()]
    for k in kalimat:
        bersih = rapikan(k)
        if len(bersih.split()) >= min_kata:
            return bersih
    return rapikan(window.text)[:120] or "(tanpa teks)"
