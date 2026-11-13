"""Varian ekspor per platform: caption, batas durasi, catatan safe-zone."""
from dataclasses import dataclass
from . import campaign
from .campaign import Campaign

@dataclass
class ExportSpec:
    platform: str
    caption: str
    maks_durasi: float
    catatan: str

_ATURAN = {
    "tiktok": (60.0, "Hindari ~150px bawah & ~120px kanan (UI TikTok); caption satu baris."),
    "instagram": (60.0, "Reels: jaga teks di tengah, hindari ~250px bawah (caption/tombol)."),
    "youtube": (60.0, "Shorts: hindari ~200px bawah (judul/channel) & sisi kanan."),
}
_DEFAULT = (60.0, "Jaga teks penting di area tengah layar 9:16.")

def platform_variants(c: Campaign, hook: str, platforms: list[str] | None = None) -> list[ExportSpec]:
    out = []
    for p in (platforms if platforms is not None else c.platform):
        key = p.strip().lower()
        cap = campaign.caption(c, hook)
        if key == "tiktok":
            # Draft.js TikTok: newline merusak paste → satu baris
            cap = " ".join(cap.split())
        maks, catatan = _ATURAN.get(key, _DEFAULT)
        out.append(ExportSpec(key, cap, maks, catatan))
    return out
