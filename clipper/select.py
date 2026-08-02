"""Pilih potongan (window) layak-klip dari transkrip.

Potongan selalu dimulai dan diakhiri di batas segmen supaya tidak memutus
kalimat di tengah — aturan campaign melarang potongan yang mengubah makna.
"""
from dataclasses import dataclass

from clipper.transcript import Segment

@dataclass
class Window:
    start: float
    end: float
    text: str
    segments: list

def build_windows(segments: list[Segment], min_s: float, max_s: float) -> list[Window]:
    jendela: list[Window] = []
    i = 0
    while i < len(segments):
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
