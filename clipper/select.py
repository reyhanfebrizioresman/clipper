"""Pilih potongan (window) layak-klip dari transkrip.

Potongan selalu dimulai dan diakhiri di batas segmen supaya tidak memutus
kalimat di tengah — aturan campaign melarang potongan yang mengubah makna.
"""
import re
from dataclasses import dataclass

from clipper.transcript import Segment, buang_filler, koreksi_istilah

AKHIR_KALIMAT = (".", "!", "?", "…")

@dataclass
class Window:
    start: float
    end: float
    text: str
    segments: list
    hook_title: str = ""
    skor: float | None = None

# Di bawah porsi ini, transkrip dianggap "tanpa tanda baca".
AMBANG_TANDA_BACA = 0.10

def penanda_akhir(segments: list[Segment]) -> list[bool]:
    """Apakah segmen ke-i mengakhiri kalimat.

    Normalnya dari tanda baca. Tapi transkrip tanpa tanda baca (Whisper bahasa
    Indonesia tanpa prompt, cache lama) membuat satu-satunya awal kalimat adalah
    segmen pertama -> semua kandidat & pilihan tertarik ke detik 0. Dalam kasus itu
    batas segmen dipakai sebagai batas kalimat: segmen Whisper umumnya berakhir di
    jeda bicara, jadi ini cadangan terbaik yang tersedia tanpa tanda baca."""
    akhir = [s.text.rstrip().endswith(AKHIR_KALIMAT) for s in segments]
    if segments and sum(akhir) / len(segments) < AMBANG_TANDA_BACA:
        return [True] * len(segments)
    return akhir

def _mulai_kalimat(akhir: list[bool], i: int) -> bool:
    # subtitle otomatis dipecah per beberapa kata, jadi "batas segmen" saja tidak
    # cukup — klip bisa dibuka dengan penggalan seperti "gini" atau "Iya."
    return i == 0 or akhir[i - 1]

def build_windows(segments: list[Segment], min_s: float, max_s: float) -> list[Window]:
    jendela: list[Window] = []
    akhir = penanda_akhir(segments)
    i = 0
    while i < len(segments):
        if not _mulai_kalimat(akhir, i):
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

def hook(window: Window, min_kata: int = 5, koreksi: dict | None = None) -> str:
    """Kalimat pembuka untuk caption — cari kalimat utuh pertama yang cukup
    berisi, bukan penggalan seperti "gini" atau "Iya."."""
    def rapikan(s: str) -> str:
        s = koreksi_istilah(buang_filler(s), koreksi)
        return s[:1].upper() + s[1:] if s else s

    kalimat = [k.strip() for k in re.split(r"(?<=[.!?…])\s+", window.text) if k.strip()]
    if not re.search(r"[.!?…]", window.text) and getattr(window, "segments", None):
        # tanpa tanda baca seluruh klip jadi satu "kalimat": pakai segmen pembuka
        # (frasa per jeda bicara) supaya hook tetap pendek
        kalimat = [s.text.strip() for s in window.segments if s.text.strip()]
    for k in kalimat:
        bersih = rapikan(k)
        if len(bersih.split()) >= min_kata:
            return bersih
    return rapikan(window.text)[:120] or "(tanpa teks)"

def snap_to_windows(props, segmen: list[Segment], min_s: float, max_s: float) -> list[Window]:
    """Tempel usulan LLM ke batas kalimat: mulai di awal kalimat terdekat
    sebelum/di proposal.start, berakhir di akhir segmen (diutamakan akhir
    kalimat) yang mencakup proposal.end dan menjaga durasi dalam [min_s, max_s]."""
    hasil: list[Window] = []
    terlihat: set[tuple[float, float]] = set()
    akhir = penanda_akhir(segmen)
    for p in props:
        i = max((k for k in range(len(segmen))
                 if _mulai_kalimat(akhir, k) and segmen[k].start <= p.start), default=0)
        if not segmen:
            break
        mulai = segmen[i].start
        kandidat = []  # indeks akhir (inklusif) yang durasinya sah
        j = i
        while j < len(segmen) and segmen[j].end - mulai <= max_s:
            if segmen[j].end - mulai >= min_s:
                kandidat.append(j)
            j += 1
        if not kandidat:
            continue
        akhir_kalimat = [k for k in kandidat if akhir[k]]
        pilih = None
        for k in (akhir_kalimat or kandidat):
            if segmen[k].end >= p.end:
                pilih = k
                break
        if pilih is None:
            pilih = (akhir_kalimat or kandidat)[-1]
        dipakai = segmen[i:pilih + 1]
        kunci = (dipakai[0].start, dipakai[-1].end)
        if kunci in terlihat:
            continue
        terlihat.add(kunci)
        hasil.append(Window(start=kunci[0], end=kunci[1],
                            text=" ".join(s.text for s in dipakai), segments=dipakai,
                            hook_title=getattr(p, "hook_title", ""),
                            skor=getattr(p, "score", None)))
    return hasil
