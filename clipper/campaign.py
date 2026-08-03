"""Brief campaign: aturan yang menentukan bentuk klip dan caption."""
import json
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Campaign:
    slug: str
    nama: str
    cpm_rp: int
    durasi_min_s: float
    durasi_maks_s: float
    platform: list
    hashtag: list
    keywords: list = field(default_factory=list)
    larangan: list = field(default_factory=list)
    koreksi: dict = field(default_factory=dict)   # perbaikan salah dengar transkrip

def load(path) -> Campaign:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    dikenal = Campaign.__dataclass_fields__.keys()
    return Campaign(**{k: v for k, v in data.items() if k in dikenal})

def caption(c: Campaign, hook: str, maks: int = 2200) -> str:
    """Hook di depan (yang kebaca sebelum 'selengkapnya'), hashtag wajib di belakang."""
    hook = hook.strip()
    if not hook:
        raise ValueError("hook kosong — caption tanpa hook bikin klip tidak diklik")
    tag = " ".join(c.hashtag)
    teks = f"{hook}\n\n{tag}"
    if len(teks) > maks:
        sisa = maks - len(tag) - 2
        teks = f"{hook[:sisa].rstrip()}\n\n{tag}"
    return teks
