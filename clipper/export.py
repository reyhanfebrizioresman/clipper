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

def aturan_efektif(aturan: dict | None = None) -> dict[str, dict]:
    """Aturan per platform setelah digabung dengan pengaturan (untuk ditampilkan di UI)."""
    hasil = {k: {"maks_durasi": m, "catatan": c} for k, (m, c) in _ATURAN.items()}
    for k, v in (aturan or {}).items():
        hasil[k] = {**hasil.get(k, {"maks_durasi": _DEFAULT[0], "catatan": _DEFAULT[1]}), **v}
    return hasil

def platform_variants(c: Campaign, hook: str, platforms: list[str] | None = None,
                      aturan: dict | None = None) -> list[ExportSpec]:
    """aturan: {platform: {maks_durasi, catatan}} dari pengaturan; menimpa _ATURAN per field."""
    out = []
    for p in (platforms if platforms is not None else c.platform):
        key = p.strip().lower()
        cap = campaign.caption(c, hook)
        if key == "tiktok":
            # Draft.js TikTok: newline merusak paste → satu baris
            cap = " ".join(cap.split())
        maks, catatan = _ATURAN.get(key, _DEFAULT)
        ubah = (aturan or {}).get(key, {})
        maks, catatan = ubah.get("maks_durasi", maks), ubah.get("catatan", catatan)
        out.append(ExportSpec(key, cap, maks, catatan))
    return out
