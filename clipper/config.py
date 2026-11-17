"""Pengaturan engine. Urutan: env var > settings.json (diatur dari web UI) >
~/.clipper.toml > bawaan. Murni, tanpa impor berat.

SKEMA adalah satu sumber kebenaran: validasi di sini, dan form Pengaturan di web UI
digambar dari skema yang sama (lewat /api/settings).
"""
import json
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from .styles import STYLES

GAYA_TETAP = frozenset(STYLES)

@dataclass
class Settings:
    # otak AI
    ai_provider: str = "keyword"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"
    ollama_host: str | None = None
    # unduhan & transkrip
    tinggi_unduh: int = 1080
    bahasa_subtitle: str = "id"
    whisper_model: str = "small"
    bahasa: str | None = None              # None = deteksi otomatis
    # pemilihan potongan
    maks_durasi: float = 60.0
    maks_pangkas: float = 0.4
    # render
    subtitle_style: str = "lato"
    karakter_per_baris: int = 46
    crf: int = 23
    preset: str = "veryfast"
    audio_kbps: int = 160
    # reframe
    reframe: bool = True
    reframe_fps: float = 5.0
    reframe_ambang: float = 0.3
    reframe_kecepatan: float = 0.15
    # koleksi
    gaya_kustom: dict = field(default_factory=dict)   # nama -> field gaya (lihat SKEMA_GAYA)
    platform: dict = field(default_factory=dict)      # tiktok -> {maks_durasi, catatan}


PRESET = ["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow"]
WHISPER = ["tiny", "base", "small", "medium", "large-v3"]

# Tiap entri: kelompok, label, tipe, batas/pilihan, keterangan. Urutan = urutan di form.
SKEMA: dict[str, dict[str, Any]] = {
    "ai_provider": {"kelompok": "Otak AI", "label": "Pemilih momen otomatis", "tipe": "pilihan",
                    "pilihan": ["keyword", "gemini"],
                    "ket": "Dipakai 'Klip otomatis'. Gemini butuh API key."},
    "gemini_api_key": {"kelompok": "Otak AI", "label": "API key Gemini", "tipe": "rahasia",
                       "ket": "Disimpan di server (izin 0600); tidak pernah dikirim utuh ke browser."},
    "gemini_model": {"kelompok": "Otak AI", "label": "Model Gemini", "tipe": "teks",
                     "pola": r"^[a-z0-9][a-z0-9.\-]{1,60}$"},
    "tinggi_unduh": {"kelompok": "Unduhan & transkrip", "label": "Resolusi unduhan maks",
                     "tipe": "pilihan", "pilihan": [720, 1080, 1440, 2160],
                     "ket": "Tinggi piksel video sumber dari yt-dlp."},
    "bahasa_subtitle": {"kelompok": "Unduhan & transkrip", "label": "Bahasa subtitle YouTube",
                        "tipe": "teks", "pola": r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$",
                        "ket": "Kode bahasa subtitle yang diambil, mis. id atau en."},
    "whisper_model": {"kelompok": "Unduhan & transkrip", "label": "Model Whisper",
                      "tipe": "pilihan", "pilihan": WHISPER,
                      "ket": "Bila tak ada subtitle. Lebih besar = lebih akurat tapi jauh lebih lambat di CPU."},
    "bahasa": {"kelompok": "Unduhan & transkrip", "label": "Bahasa Whisper", "tipe": "pilihan",
               "pilihan": [None, "id", "en"], "label_pilihan": {"": "otomatis"},
               "ket": "Kosong = deteksi otomatis."},
    "maks_durasi": {"kelompok": "Pemilihan potongan", "label": "Durasi maks bawaan (dtk)",
                    "tipe": "angka", "min": 10, "maks": 600,
                    "ket": "Tetap dibatasi durasi maks campaign."},
    "maks_pangkas": {"kelompok": "Pemilihan potongan", "label": "Batas pangkas ke akhir kalimat",
                     "tipe": "angka", "min": 0, "maks": 0.9, "langkah": 0.05,
                     "ket": "Porsi durasi pilihan yang boleh dibuang demi berakhir di akhir kalimat."},
    "subtitle_style": {"kelompok": "Render", "label": "Gaya subtitle bawaan", "tipe": "gaya"},
    "karakter_per_baris": {"kelompok": "Render", "label": "Karakter per baris subtitle",
                           "tipe": "bulat", "min": 16, "maks": 80},
    "crf": {"kelompok": "Render", "label": "Kualitas video (CRF)", "tipe": "bulat",
            "min": 14, "maks": 35, "ket": "Lebih kecil = lebih tajam & file lebih besar. 23 = standar."},
    "preset": {"kelompok": "Render", "label": "Kecepatan encode", "tipe": "pilihan", "pilihan": PRESET,
               "ket": "Lebih lambat = file lebih kecil di kualitas sama, tapi CPU lebih lama."},
    "audio_kbps": {"kelompok": "Render", "label": "Bitrate audio (kbps)", "tipe": "pilihan",
                   "pilihan": [96, 128, 160, 192, 256]},
    "reframe": {"kelompok": "Reframe", "label": "Reframe ikut wajah (bawaan)", "tipe": "boolean"},
    "reframe_fps": {"kelompok": "Reframe", "label": "Sampel deteksi wajah per detik",
                    "tipe": "angka", "min": 1, "maks": 15, "langkah": 1,
                    "ket": "Lebih tinggi = jalur kamera lebih halus, deteksi lebih lama."},
    "reframe_ambang": {"kelompok": "Reframe", "label": "Ambang blur-pad", "tipe": "angka",
                       "min": 0.05, "maks": 0.9, "langkah": 0.05,
                       "ket": "Bila porsi frame tanpa wajah / banyak wajah melebihi ini, pakai blur-pad."},
    "reframe_kecepatan": {"kelompok": "Reframe", "label": "Kecepatan geser kamera",
                          "tipe": "angka", "min": 0.02, "maks": 1, "langkah": 0.01,
                          "ket": "Lebar sumber per detik; kecil = lebih tenang, besar = lebih cepat mengikuti."},
}

SKEMA_GAYA: dict[str, dict[str, Any]] = {
    "font": {"label": "Font", "tipe": "teks", "pola": r"^[A-Za-z0-9 ._-]{1,60}$"},
    "ukuran": {"label": "Ukuran", "tipe": "bulat", "min": 6, "maks": 40},
    "warna": {"label": "Warna teks", "tipe": "warna"},
    "warna_outline": {"label": "Warna outline/kotak", "tipe": "warna"},
    "outline": {"label": "Tebal outline", "tipe": "bulat", "min": 0, "maks": 8},
    "bayangan": {"label": "Bayangan", "tipe": "bulat", "min": 0, "maks": 6},
    "posisi": {"label": "Jarak dari bawah", "tipe": "bulat", "min": 0, "maks": 260,
               "ket": "95 ≈ di atas area caption TikTok."},
    "tebal": {"label": "Huruf tebal", "tipe": "boolean"},
    "kotak": {"label": "Latar kotak", "tipe": "boolean"},
}
GAYA_BAWAAN_BARU = {"font": "Lato Black", "ukuran": 13, "warna": "#FFFFFF",
                    "warna_outline": "#000000", "outline": 2, "bayangan": 1, "posisi": 95,
                    "tebal": True, "kotak": False}
SKEMA_PLATFORM = {
    "maks_durasi": {"label": "Durasi maks (dtk)", "tipe": "angka", "min": 5, "maks": 600},
    "catatan": {"label": "Catatan safe-zone", "tipe": "teks", "maks_panjang": 300},
}

# env var yang mengunci setelan (UI menampilkannya sebagai terkunci)
ENV = {
    "ai_provider": ["CLIPPER_AI"],
    "gemini_api_key": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "ollama_host": ["OLLAMA_HOST"],
    "subtitle_style": ["CLIPPER_SUBTITLE_STYLE"],
    "reframe": ["CLIPPER_REFRAME"],
}
_NAMA = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
_WARNA = re.compile(r"^#[0-9A-Fa-f]{6}$")


class SettingsError(ValueError):
    """Nilai setelan tidak sah; pesannya layak ditampilkan ke pengguna."""


def _cek(nama: str, aturan: dict, v: Any) -> Any:
    tipe = aturan["tipe"]
    label = aturan.get("label", nama)
    if tipe == "boolean":
        if not isinstance(v, bool):
            raise SettingsError(f"{label}: harus ya/tidak")
        return v
    if tipe in ("angka", "bulat"):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise SettingsError(f"{label}: harus angka")
        if tipe == "bulat":
            if float(v) != int(v):
                raise SettingsError(f"{label}: harus bilangan bulat")
            v = int(v)
        else:
            v = float(v)
        if "min" in aturan and v < aturan["min"] or "maks" in aturan and v > aturan["maks"]:
            raise SettingsError(f"{label}: harus {aturan.get('min')}–{aturan.get('maks')}")
        return v
    if tipe == "pilihan":
        if v == "" and None in aturan["pilihan"]:
            v = None
        if v not in aturan["pilihan"]:
            raise SettingsError(f"{label}: pilihan tidak dikenal ({v!r})")
        return v
    if tipe == "warna":
        if not isinstance(v, str) or not _WARNA.match(v):
            raise SettingsError(f"{label}: warna harus #RRGGBB")
        return v.upper()
    if tipe in ("teks", "rahasia", "gaya"):
        if v is None and tipe == "rahasia":
            return None
        if not isinstance(v, str):
            raise SettingsError(f"{label}: harus teks")
        v = v.strip()
        if tipe == "rahasia":
            if any(c.isspace() for c in v) or len(v) > 200:
                raise SettingsError(f"{label}: format tidak sah")
            return v or None
        if "pola" in aturan and not re.match(aturan["pola"], v):
            raise SettingsError(f"{label}: format tidak sah")
        if len(v) > aturan.get("maks_panjang", 200):
            raise SettingsError(f"{label}: terlalu panjang")
        return v
    raise SettingsError(f"{label}: tipe tidak dikenal")


def validasi(data: dict, *, gaya_dikenal: set[str] | None = None) -> dict:
    """Validasi perubahan setelan (sebagian). Mengembalikan nilai yang sudah dirapikan."""
    if not isinstance(data, dict):
        raise SettingsError("setelan harus objek JSON")
    hasil: dict[str, Any] = {}
    for k, v in data.items():
        if k == "gaya_kustom":
            hasil[k] = _validasi_gaya(v)
        elif k == "platform":
            hasil[k] = _validasi_platform(v)
        elif k in SKEMA:
            hasil[k] = _cek(k, SKEMA[k], v)
        else:
            raise SettingsError(f"setelan tidak dikenal: {k}")
    if "subtitle_style" in hasil and gaya_dikenal is not None:
        semua = set(gaya_dikenal) | set(hasil.get("gaya_kustom", {}))
        if hasil["subtitle_style"] not in semua:
            raise SettingsError(f"gaya subtitle {hasil['subtitle_style']!r} tidak ada")
    return hasil


def _validasi_gaya(v: Any) -> dict:
    if not isinstance(v, dict) or len(v) > 30:
        raise SettingsError("gaya kustom harus objek (maks 30 gaya)")
    hasil = {}
    for nama, isi in v.items():
        if not isinstance(nama, str) or not _NAMA.match(nama):
            raise SettingsError(f"nama gaya {nama!r} tidak sah (huruf kecil, angka, -)")
        if nama in GAYA_TETAP:
            raise SettingsError(f"gaya {nama!r} adalah gaya bawaan; pakai nama lain")
        if not isinstance(isi, dict):
            raise SettingsError(f"gaya {nama}: harus objek")
        lengkap = {**GAYA_BAWAAN_BARU, **isi}
        tak_dikenal = set(lengkap) - set(SKEMA_GAYA)
        if tak_dikenal:
            raise SettingsError(f"gaya {nama}: field tidak dikenal {sorted(tak_dikenal)}")
        hasil[nama] = {k: _cek(k, SKEMA_GAYA[k], lengkap[k]) for k in SKEMA_GAYA}
    return hasil


def _validasi_platform(v: Any) -> dict:
    if not isinstance(v, dict) or len(v) > 20:
        raise SettingsError("platform harus objek (maks 20)")
    hasil = {}
    for nama, isi in v.items():
        kunci = str(nama).strip().lower()
        if not _NAMA.match(kunci):
            raise SettingsError(f"nama platform {nama!r} tidak sah")
        if not isinstance(isi, dict) or set(isi) - set(SKEMA_PLATFORM):
            raise SettingsError(f"platform {nama}: field harus {sorted(SKEMA_PLATFORM)}")
        hasil[kunci] = {k: _cek(k, SKEMA_PLATFORM[k], isi[k]) for k in SKEMA_PLATFORM if k in isi}
    return hasil


def baca_json(path: Path | str | None) -> dict:
    if not path:
        return {}
    p = Path(path).expanduser()
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def simpan_json(path: Path | str, perubahan: dict, *, gaya_dikenal: set[str] | None = None) -> dict:
    """Gabungkan perubahan (sudah divalidasi) ke settings.json secara atomik, izin 0600.
    Nilai None menghapus kunci (kembali ke bawaan)."""
    bersih = validasi({k: v for k, v in perubahan.items() if v is not None},
                      gaya_dikenal=gaya_dikenal)
    p = Path(path).expanduser()
    data = baca_json(p)
    data.update(bersih)
    for k, v in list(perubahan.items()) + list(bersih.items()):
        if v is None:            # None / teks kosong -> hapus: kembali ke lapisan di bawahnya
            data.pop(k, None)
    if "subtitle_style" in data and gaya_dikenal is not None:
        if data["subtitle_style"] not in set(gaya_dikenal) | set(data.get("gaya_kustom", {})):
            raise SettingsError(f"gaya {data['subtitle_style']!r} masih dipakai sebagai bawaan")
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".settings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.chmod(tmp, 0o600)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return data


def terkunci_env(env=os.environ) -> dict[str, str]:
    """Setelan yang ditimpa env var -> nama env-nya."""
    return {k: next(e for e in nama if env.get(e)) for k, nama in ENV.items()
            if any(env.get(e) for e in nama)}


def load_settings(env=os.environ, path="~/.clipper.toml", json_path=None) -> Settings:
    s = Settings()
    dikenal = {f.name for f in fields(Settings)}
    lapisan: list[dict] = []
    p = Path(str(path)).expanduser()
    if p.is_file():
        try:
            lapisan.append(tomllib.loads(p.read_text(encoding="utf-8")))
        except (tomllib.TOMLDecodeError, OSError):
            pass
    lapisan.append(baca_json(json_path))
    for data in lapisan:
        for k, v in data.items():
            if k not in dikenal:
                continue
            try:   # nilai rusak di file jangan menjatuhkan engine: abaikan, pakai lapisan bawah
                v = validasi({k: v})[k] if k in SKEMA or k in ("gaya_kustom", "platform") else v
            except SettingsError:
                continue
            setattr(s, k, v)
    key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if key:
        s.gemini_api_key = key
    if env.get("CLIPPER_AI"):
        s.ai_provider = env["CLIPPER_AI"]
    if env.get("OLLAMA_HOST"):
        s.ollama_host = env["OLLAMA_HOST"]
    if env.get("CLIPPER_SUBTITLE_STYLE"):
        s.subtitle_style = env["CLIPPER_SUBTITLE_STYLE"]
    if env.get("CLIPPER_REFRAME"):
        s.reframe = env["CLIPPER_REFRAME"].lower() not in ("0", "false", "no", "off")
    return s
