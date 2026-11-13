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
