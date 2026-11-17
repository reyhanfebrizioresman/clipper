"""Periksa instalasi clipper di mesin ini dan tunjukkan cara memperbaiki yang kurang.

    .venv/bin/python scripts/cek_instalasi.py                # periksa saja
    .venv/bin/python scripts/cek_instalasi.py --unduh-model  # + unduh model deteksi wajah

Kode keluar 0 bila semua yang WAJIB beres (peringatan tidak menggagalkan), 1 bila tidak.
Tidak mengubah apa pun selain mengunduh model wajah bila diminta.
"""
import argparse
import hashlib
import importlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MODEL = ROOT / "models" / "blaze_face_short_range.tflite"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_detector/"
             "blaze_face_short_range/float16/latest/blaze_face_short_range.tflite")
MODEL_SHA256 = "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f"

WARNA = sys.stdout.isatty() and os.name != "nt"
TANDA = {"ok": ("\033[32m✓\033[0m" if WARNA else "[ OK ]"),
         "warn": ("\033[33m!\033[0m" if WARNA else "[PERINGATAN]"),
         "gagal": ("\033[31m✗\033[0m" if WARNA else "[GAGAL]")}
hasil: list[str] = []


def lapor(status: str, judul: str, ket: str = "", saran: str = "") -> None:
    hasil.append(status)
    print(f"{TANDA[status]} {judul}" + (f" — {ket}" if ket else ""))
    if saran and status != "ok":
        for baris in saran.splitlines():
            print(f"    → {baris}")


def jalankan(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout + p.stderr
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def os_saran(debian: str, mac: str, windows: str) -> str:
    if sys.platform == "darwin":
        return mac
    if os.name == "nt":
        return windows
    return debian


def cek_python() -> None:
    v = sys.version_info
    teks = f"{v.major}.{v.minor}.{v.micro} ({sys.executable})"
    if v < (3, 11):
        lapor("gagal", "Python", teks, "butuh Python 3.11 atau lebih baru (3.11/3.12 disarankan)")
    elif v >= (3, 13):
        lapor("warn", "Python", teks, "3.13+ belum diuji; mediapipe kadang belum punya wheel. "
                                       "Pakai 3.11/3.12 bila pip install gagal")
    else:
        lapor("ok", "Python", teks)
    if sys.prefix == sys.base_prefix:
        lapor("warn", "Virtualenv", "tidak sedang di dalam .venv",
              "jalankan skrip ini dengan python dari .venv proyek (lihat docs/instalasi.md)")


def cek_paket() -> None:
    wajib = {"yt_dlp": "yt-dlp", "faster_whisper": "faster-whisper", "av": "av",
             "mediapipe": "mediapipe", "cv2": "opencv-python", "fastapi": "fastapi",
             "uvicorn": "uvicorn", "mcp": "mcp", "httpx": "httpx"}
    kurang = []
    for modul, paket in wajib.items():
        try:
            importlib.import_module(modul)
        except Exception as e:     # mediapipe bisa gagal karena library sistem, bukan pip
            kurang.append(f"{paket} ({type(e).__name__}: {str(e)[:80]})")
    if kurang:
        lapor("gagal", "Paket Python", "; ".join(kurang),
              "pip install -r requirements.txt (dari dalam .venv)\n"
              "mediapipe gagal karena libEGL/libGLES di Linux tanpa layar: "
              "sudo apt install libegl1 libgles2")
    else:
        lapor("ok", "Paket Python", "semua dependensi wajib terpasang")
    try:
        importlib.import_module("google.genai")
        lapor("ok", "google-genai", "opsional, untuk pemilih momen Gemini")
    except Exception:
        lapor("warn", "google-genai", "tidak terpasang (opsional, hanya untuk Gemini)",
              "pip install -r requirements.txt")


def cek_ffmpeg() -> None:
    from clipper import render
    ff, fp = shutil.which(render.FFMPEG) or render.FFMPEG, shutil.which("ffprobe")
    kode, out = jalankan([ff, "-hide_banner", "-version"])
    if kode != 0:
        lapor("gagal", "ffmpeg", "tidak ditemukan di PATH",
              os_saran("sudo apt install ffmpeg", "brew install ffmpeg",
                       "winget install Gyan.FFmpeg  (lalu buka terminal baru)"))
        return
    versi = out.splitlines()[0].replace("ffmpeg version ", "").split(" Copyright")[0]
    lapor("ok" if fp else "gagal", "ffmpeg / ffprobe", versi if fp else "ffprobe tidak ditemukan",
          "ffprobe biasanya satu paket dengan ffmpeg; pasang ulang ffmpeg")
    _, filt = jalankan([ff, "-hide_banner", "-filters"])
    if " subtitles " not in filt:
        lapor("gagal", "ffmpeg + libass", "filter 'subtitles' tidak ada di build ffmpeg ini",
              "pakai build ffmpeg dengan libass (paket distro / Homebrew / gyan.dev full sudah)")
    else:
        lapor("ok", "ffmpeg + libass", "filter subtitles tersedia")


def cek_deno() -> None:
    from clipper import source
    d = source._deno()
    if d:
        kode, out = jalankan([d, "--version"])
        lapor("ok", "Deno", out.splitlines()[0] if kode == 0 and out else d)
    else:
        lapor("warn", "Deno", "tidak ditemukan — unduhan YouTube bisa gagal atau resolusinya terbatas",
              os_saran("curl -fsSL https://deno.land/install.sh | sh",
                       "brew install deno",
                       "winget install DenoLand.Deno")
              + "\natau set CLIPPER_DENO=/path/ke/deno")


def cek_font() -> None:
    if not shutil.which("fc-list"):
        lapor("warn", "Font Lato", "fc-list tidak ada, tidak bisa diperiksa",
              "pastikan font Lato terpasang (gaya subtitle bawaan 'lato')")
        return
    _, out = jalankan(["fc-list", ":", "family"])
    if "lato" in out.lower():
        lapor("ok", "Font Lato", "terpasang")
    else:
        lapor("warn", "Font Lato", "tidak terpasang — subtitle akan memakai font cadangan",
              os_saran("sudo apt install fonts-lato", "brew install --cask font-lato",
                       "unduh Lato dari fonts.google.com/specimen/Lato lalu Install for all users"))


def unduh_model() -> None:
    MODEL.parent.mkdir(parents=True, exist_ok=True)
    print(f"  mengunduh {MODEL_URL}")
    fd, tmp = tempfile.mkstemp(dir=MODEL.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f, urllib.request.urlopen(MODEL_URL, timeout=60) as r:
            f.write(r.read())
        sha = hashlib.sha256(Path(tmp).read_bytes()).hexdigest()
        if sha != MODEL_SHA256:
            raise ValueError(f"checksum tidak cocok ({sha[:12]}…), file dibuang")
        os.chmod(tmp, 0o644)
        os.replace(tmp, MODEL)
    finally:
        Path(tmp).unlink(missing_ok=True)


def cek_model(boleh_unduh: bool) -> None:
    p = Path(os.environ.get("CLIPPER_FACE_MODEL") or MODEL)
    if not p.is_file() and boleh_unduh and not os.environ.get("CLIPPER_FACE_MODEL"):
        try:
            unduh_model()
        except Exception as e:
            lapor("gagal", "Model deteksi wajah", f"unduhan gagal: {e}")
            return
    if p.is_file():
        lapor("ok", "Model deteksi wajah", str(p))
    else:
        lapor("warn", "Model deteksi wajah", "tidak ada — reframe ikut wajah mati (blur-pad saja)",
              "jalankan ulang dengan --unduh-model")


def cek_mediapipe() -> None:
    p = Path(os.environ.get("CLIPPER_FACE_MODEL") or MODEL)
    if not p.is_file():
        return
    stderr = None
    try:
        from mediapipe.tasks.python import BaseOptions, vision
        sys.stderr.flush()
        stderr = os.dup(2)                       # redam log INFO C++ LiteRT saat memuat model
        with open(os.devnull, "w") as nol:
            os.dup2(nol.fileno(), 2)
        det = vision.FaceDetector.create_from_options(
            vision.FaceDetectorOptions(base_options=BaseOptions(model_asset_path=str(p))))
        det.close()
        os.dup2(stderr, 2)
        lapor("ok", "MediaPipe", "detektor wajah bisa dimuat")
    except Exception as e:
        if stderr is not None:
            os.dup2(stderr, 2)
        lapor("warn", "MediaPipe", f"detektor wajah gagal dimuat ({str(e)[:100]})",
              "Linux tanpa layar: sudo apt install libegl1 libgles2")


def cek_folder() -> None:
    for nama, env, bawaan in (("Folder kerja", "CLIPPER_WORK", ROOT / "work"),
                              ("Folder campaign", "CLIPPER_CAMPAIGNS", ROOT / "campaigns")):
        p = Path(os.environ.get(env) or bawaan)
        target = p if p.exists() else p.parent
        if os.access(target, os.W_OK):
            lapor("ok", nama, str(p))
        else:
            lapor("gagal", nama, f"{p} tidak bisa ditulis", f"perbaiki izin folder, atau set {env}")
    try:
        bebas = shutil.disk_usage(ROOT).free / 1e9
        lapor("ok" if bebas >= 10 else "warn", "Ruang disk", f"{bebas:.0f} GB kosong",
              "video sumber 1080p ±1 GB per jam; sisakan minimal 10 GB")
    except OSError:
        pass


def cek_perangkat() -> None:
    from clipper import hardware
    from clipper.config import Settings
    print("\nPerangkat (sama dengan kartu 'Perangkat server' di web UI):")
    hw = hardware.deteksi()
    r = hardware.ringkas(hw, Settings())
    print(f"  CPU {hw.cpu} core · RAM {hw.ram_gb or '?'} GB · GPU {hw.gpu or 'tidak terdeteksi'}"
          + (f" ({hw.vram_gb} GB)" if hw.vram_gb else ""))
    print(f"  Whisper: {r['whisper']} · encoder video: {r['encoder']}"
          f" · encoder GPU lolos uji: {', '.join(hw.encoders) or 'tidak ada'}")
    print("  Setelan awal: " + ", ".join(f"{k}={v}" for k, v in r["rekomendasi"].items()))
    vendor = hw.gpu_vendor
    if vendor and not hw.encoders:
        lapor("warn", "Encoder GPU", f"GPU {vendor} terlihat tapi tidak ada encoder GPU yang lolos uji",
              {"nvidia": "pasang driver NVIDIA terbaru; ffmpeg harus build dengan h264_nvenc",
               "amd": "Linux: sudo apt install mesa-va-drivers, tambahkan user ke grup 'render'\n"
                      "Windows: perbarui driver AMD Adrenalin; ffmpeg gyan.dev full punya h264_amf",
               "intel": "sudo apt install intel-media-va-driver (atau i965-va-driver untuk Intel lama)",
               "apple": "pakai ffmpeg dari Homebrew (brew install ffmpeg)"}.get(vendor, ""))
    if vendor == "nvidia" and not hw.cuda:
        lapor("warn", "Whisper GPU", "GPU NVIDIA ada, tapi CTranslate2 tidak melihat CUDA",
              "pip install nvidia-cublas-cu12 'nvidia-cudnn-cu12==9.*' lalu jalankan ulang\n"
              "(lihat bagian GPU NVIDIA di docs/instalasi.md)")
    if vendor == "apple" and not hw.mlx and platform.machine() == "arm64":
        lapor("warn", "Whisper GPU", "mlx-whisper belum terpasang", "pip install -r requirements.txt")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--unduh-model", action="store_true",
                    help="unduh model deteksi wajah MediaPipe bila belum ada (±230 KB)")
    args = ap.parse_args()
    print(f"Clipper — cek instalasi di {platform.system()} {platform.machine()} ({ROOT})\n")
    cek_python()
    cek_paket()
    cek_ffmpeg()
    cek_deno()
    cek_font()
    cek_model(args.unduh_model)
    cek_mediapipe()
    cek_folder()
    try:
        cek_perangkat()
    except Exception as e:
        lapor("warn", "Deteksi perangkat", f"gagal ({e}); clipper tetap jalan di CPU")
    gagal, warn = hasil.count("gagal"), hasil.count("warn")
    print()
    if gagal:
        print(f"{gagal} masalah wajib dan {warn} peringatan. Perbaiki yang bertanda gagal dulu.")
        return 1
    print("Siap dipakai." + (f" ({warn} peringatan opsional di atas.)" if warn else ""))
    print("Jalankan web UI:  python scripts/web.py   → http://127.0.0.1:8780")
    return 0


if __name__ == "__main__":
    sys.exit(main())
