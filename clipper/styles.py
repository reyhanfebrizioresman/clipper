"""Template gaya subtitle (ASS force_style untuk libass)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SubtitleStyle:
    name: str
    force_style: str


# libass menskalakan angka style ke tinggi referensi 288 (faktor 1920/288 ~ 6,7):
# FontSize=13 ~ 87 px. MarginV=95 (~500 px dari bawah): di atas caption & tombol
# TikTok yang memakan ~15% layar bawah, tapi tetap dekat dengan video di atasnya.
STYLES: dict[str, SubtitleStyle] = {
    "lato": SubtitleStyle(
        "lato",
        "FontName=Lato Black,Bold=1,FontSize=13,PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,Outline=2,Shadow=1,MarginV=95,Alignment=2"),
    "bold": SubtitleStyle(
        "bold",
        "FontName=Lato Black,Bold=1,FontSize=15,PrimaryColour=&HFFFFFF&,"
        "OutlineColour=&H000000&,Outline=3,Shadow=0,MarginV=95,Alignment=2"),
    "karaoke": SubtitleStyle(
        "karaoke",
        "FontName=Lato Black,Bold=1,FontSize=14,PrimaryColour=&H00FFFF&,"
        "OutlineColour=&H000000&,BorderStyle=3,Outline=2,Shadow=0,MarginV=95,Alignment=2"),
}


def _ass_warna(hex_rgb: str) -> str:
    """#RRGGBB -> &HBBGGRR& (urutan warna ASS terbalik)."""
    h = hex_rgb.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def dari_field(nama: str, f: dict) -> SubtitleStyle:
    """Gaya kustom dari field form (sudah divalidasi config.SKEMA_GAYA).
    Nilai sudah dibatasi ke karakter aman, jadi tidak bisa menyusup ke argumen ffmpeg."""
    bagian = [
        f"FontName={f['font']}", f"Bold={1 if f['tebal'] else 0}", f"FontSize={f['ukuran']}",
        f"PrimaryColour={_ass_warna(f['warna'])}", f"OutlineColour={_ass_warna(f['warna_outline'])}",
    ]
    if f["kotak"]:
        bagian.append("BorderStyle=3")
    bagian += [f"Outline={f['outline']}", f"Shadow={f['bayangan']}",
               f"MarginV={f['posisi']}", "Alignment=2"]
    return SubtitleStyle(nama, ",".join(bagian))


def semua_gaya(gaya_kustom: dict | None = None) -> dict[str, SubtitleStyle]:
    """Gaya bawaan + gaya kustom dari pengaturan (nama kustom tidak boleh menimpa bawaan)."""
    hasil = dict(STYLES)
    for nama, f in (gaya_kustom or {}).items():
        if nama not in STYLES:
            hasil[nama] = dari_field(nama, f)
    return hasil
