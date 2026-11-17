"""Deteksi perangkat mesin clipper (CPU, RAM, GPU NVIDIA/AMD/Intel/Apple) dan setelan
awal yang cocok.

Rekomendasi hanya mengisi lapisan PALING BAWAH pengaturan: apa pun yang diatur
pengguna (web UI / ~/.clipper.toml / env) tetap menang. Deteksi dijalankan sekali
per proses (terdeteksi() di-cache); semua pemeriksaan gagal dengan aman ke CPU.

GPU dipakai lewat dua jalur yang berdiri sendiri:
- encoder video: diuji dengan encode sungguhan berargumen sama persis dengan render
  (render.uji_encode_cmd), jadi driver/opsi yang tidak cocok tidak pernah terpilih;
- Whisper: CTranslate2 di GPU (NVIDIA CUDA, atau AMD bila CTranslate2 build ROCm
  terpasang), atau MLX di Apple Silicon (paket mlx-whisper).
"""
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from . import render

VENDOR = {"0x10de": "nvidia", "0x1002": "amd", "0x8086": "intel"}
NAMA_VENDOR = {"nvidia": "NVIDIA", "amd": "AMD", "intel": "Intel", "apple": "Apple"}


@dataclass(frozen=True)
class Hardware:
    cpu: int                         # core yang boleh dipakai proses ini
    ram_gb: float | None             # None = tidak diketahui (dianggap 8 GB)
    gpu: str | None = None           # nama GPU utama (informasi)
    gpu_vendor: str | None = None    # nvidia | amd | intel | apple
    vram_gb: float | None = None     # memori GPU; Apple = memori bersama (lihat ram_gb)
    cuda: bool = False               # Whisper CTranslate2 di GPU (CUDA / ROCm)
    mlx: bool = False                # Whisper MLX di Apple Silicon
    encoders: tuple[str, ...] = ()   # encoder GPU yang lolos uji, urutan prioritas
    vaapi_device: str | None = None  # render node untuk VAAPI (Linux AMD/Intel)

    def json(self) -> dict:
        d = asdict(self)
        d["encoders"] = list(self.encoders)
        return d


def _jalankan(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _cpu() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))   # hormati batas taskset/container
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _ram_gb(jalankan=_jalankan) -> float | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for baris in f:
                if baris.startswith("MemTotal:"):
                    return round(int(baris.split()[1]) / 1024**2, 1)
    except OSError:
        pass
    if sys.platform == "darwin":
        kode, out = jalankan(["sysctl", "-n", "hw.memsize"], 5)
        if kode == 0 and out.strip().isdigit():
            return round(int(out) / 1024**3, 1)
    try:   # Unix lain
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (AttributeError, ValueError, OSError):
        return None


def _apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _gpu_nvidia(jalankan=_jalankan) -> tuple[str | None, float | None]:
    if not shutil.which("nvidia-smi"):
        return None, None
    kode, out = jalankan(["nvidia-smi", "--query-gpu=name,memory.total",
                          "--format=csv,noheader,nounits"], 10)
    baris = out.strip().splitlines()
    if kode != 0 or not baris:
        return None, None
    nama, _, mib = baris[0].rpartition(",")
    try:
        return nama.strip() or None, round(float(mib) / 1024, 1)
    except ValueError:
        return nama.strip() or None, None


def _baca(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _gpu_linux(drm: Path = Path("/sys/class/drm")) -> list[dict]:
    """GPU dari sysfs: [{vendor, node, nama, vram_gb}] per render node (renderD128, ...)."""
    hasil = []
    for node in sorted(drm.glob("renderD*")):
        dev = node / "device"
        vendor = VENDOR.get((_baca(dev / "vendor") or "").lower())
        if not vendor:
            continue
        vram = _baca(dev / "mem_info_vram_total")          # amdgpu, byte
        hasil.append({"vendor": vendor, "node": f"/dev/dri/{node.name}",
                      "nama": _baca(dev / "product_name") or f"GPU {NAMA_VENDOR[vendor]}",
                      "vram_gb": round(int(vram) / 1024**3, 1) if vram and vram.isdigit() else None})
    return hasil


def _gpu_windows(jalankan=_jalankan) -> str | None:
    kode, out = jalankan(["powershell", "-NoProfile", "-Command",
                          "(Get-CimInstance Win32_VideoController).Name"], 15)
    nama = [b.strip() for b in out.splitlines() if b.strip()] if kode == 0 else []
    # utamakan GPU diskrit bila ada beberapa (mis. Intel iGPU + AMD/NVIDIA)
    for kata in ("NVIDIA", "AMD", "Radeon"):
        for n in nama:
            if kata.lower() in n.lower():
                return n
    return nama[0] if nama else None


def _vendor_dari_nama(nama: str | None) -> str | None:
    n = (nama or "").lower()
    for kata, v in (("nvidia", "nvidia"), ("geforce", "nvidia"), ("amd", "amd"),
                    ("radeon", "amd"), ("intel", "intel"), ("apple", "apple")):
        if kata in n:
            return v
    return None


def _cuda_whisper() -> bool:
    """CTranslate2 (mesin faster-whisper) melihat GPU: CUDA (NVIDIA) atau ROCm (AMD, hanya
    dengan build CTranslate2 ROCm). Library yang kurang baru ketahuan saat model dimuat;
    pipeline.muat_whisper lalu jatuh ke CPU."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _mlx_whisper() -> bool:
    if not _apple_silicon():
        return False
    try:
        import importlib.util
        return importlib.util.find_spec("mlx_whisper") is not None
    except (ImportError, ValueError):
        return False


def _encoder_gpu(jalankan=_jalankan, vaapi_device: str | None = None) -> tuple[str, ...]:
    """Encoder GPU yang ada di build ffmpeg ini DAN lolos uji encode sungguhan."""
    kode, daftar = jalankan([render.FFMPEG, "-hide_banner", "-encoders"], 10)
    if kode != 0:
        return ()
    lolos = []
    for enc in render.ENCODER_GPU:
        if f"h264_{enc}" not in daftar:
            continue
        nama = enc
        if enc == "vaapi":
            if not vaapi_device:
                continue
            nama = f"vaapi:{vaapi_device}"
        if jalankan(render.uji_encode_cmd(nama), 20)[0] == 0:
            lolos.append(enc)
    return tuple(lolos)


def deteksi(jalankan=_jalankan, drm: Path = Path("/sys/class/drm")) -> Hardware:
    gpu = vendor = vram = vaapi = None
    nv_nama, nv_vram = _gpu_nvidia(jalankan)
    linux = _gpu_linux(drm) if sys.platform.startswith("linux") else []
    lain = next((g for g in linux if g["vendor"] != "nvidia"), None)   # AMD/Intel -> VAAPI
    if nv_nama:
        gpu, vendor, vram = nv_nama, "nvidia", nv_vram
    elif lain:
        gpu, vendor, vram = lain["nama"], lain["vendor"], lain["vram_gb"]
    elif _apple_silicon():
        gpu, vendor = "Apple Silicon", "apple"
    elif sys.platform == "win32":
        gpu = _gpu_windows(jalankan)
        vendor = _vendor_dari_nama(gpu)
    if lain:
        vaapi = lain["node"]
    return Hardware(cpu=_cpu(), ram_gb=_ram_gb(jalankan), gpu=gpu, gpu_vendor=vendor,
                    vram_gb=vram, cuda=_cuda_whisper(), mlx=_mlx_whisper(),
                    encoders=_encoder_gpu(jalankan, vaapi), vaapi_device=vaapi)


@lru_cache(maxsize=1)
def terdeteksi() -> Hardware:
    """Deteksi sekali per proses (nvidia-smi & uji encode ffmpeg butuh ~1 dtk)."""
    return deteksi()


def rekomendasi(hw: Hardware) -> dict:
    """Setelan awal yang wajar untuk perangkat ini. Mesin 6 core / 8 GB+ tanpa GPU
    mendapat bawaan lama (small, veryfast, 1080p, 5 fps)."""
    c, ram = hw.cpu, hw.ram_gb if hw.ram_gb is not None else 8.0
    if hw.cuda:
        vram = hw.vram_gb or 0
        whisper = "large-v3" if vram >= 10 else "medium" if vram >= 5 else "small"
    elif hw.mlx:                       # memori bersama Apple: RAM = memori GPU
        whisper = "large-v3" if ram >= 32 else "medium" if ram >= 16 else "small"
    elif c >= 6 and ram >= 8:
        whisper = "small"
    elif c >= 4 and ram >= 4:
        whisper = "base"
    else:
        whisper = "tiny"
    if hw.encoders or c >= 6:
        preset = "veryfast"
    elif c >= 4:
        preset = "superfast"
    else:
        preset = "ultrafast"
    return {
        "whisper_model": whisper,
        "preset": preset,
        "tinggi_unduh": 720 if c <= 2 or ram < 4 else 1080,
        "reframe_fps": 5.0 if c >= 6 else 3.0 if c >= 4 else 2.0,
    }


def whisper_efektif(pilihan: str, hw: Hardware) -> str:
    """'otomatis' -> cuda / mlx bila tersedia, selain itu cpu. Pilihan eksplisit dihormati
    (jatuh ke CPU saat dimuat bila ternyata gagal)."""
    if pilihan == "otomatis":
        return "cuda" if hw.cuda else "mlx" if hw.mlx else "cpu"
    return pilihan


def encoder_efektif(pilihan: str, hw: Hardware) -> str:
    """Nama encoder untuk render. VAAPI membawa render node-nya: 'vaapi:/dev/dri/renderD128'."""
    enc = (hw.encoders[0] if hw.encoders else "cpu") if pilihan == "otomatis" else pilihan
    if enc == "vaapi" and hw.vaapi_device:
        return f"vaapi:{hw.vaapi_device}"
    return enc


def ringkas(hw: Hardware, s) -> dict:
    """Untuk UI/MCP: perangkat, rekomendasi, dan perangkat yang benar-benar dipakai."""
    return {"hardware": hw.json(), "rekomendasi": rekomendasi(hw),
            "whisper": whisper_efektif(s.perangkat_whisper, hw),
            "encoder": encoder_efektif(s.encoder, hw).partition(":")[0]}
