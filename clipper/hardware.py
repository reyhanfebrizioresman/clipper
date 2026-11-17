"""Deteksi perangkat mesin clipper (CPU, RAM, GPU NVIDIA) dan setelan awal yang cocok.

Rekomendasi hanya mengisi lapisan PALING BAWAH pengaturan: apa pun yang diatur
pengguna (web UI / ~/.clipper.toml / env) tetap menang. Deteksi dijalankan sekali
per proses (terdeteksi() di-cache); semua pemeriksaan gagal dengan aman ke CPU.
"""
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from functools import lru_cache

FFMPEG = os.getenv("FFMPEG_BIN", "ffmpeg")


@dataclass(frozen=True)
class Hardware:
    cpu: int                        # core yang boleh dipakai proses ini
    ram_gb: float | None            # None = tidak diketahui (dianggap 8 GB)
    gpu: str | None = None          # nama GPU NVIDIA pertama
    vram_gb: float | None = None
    cuda: bool = False              # Whisper (CTranslate2) bisa jalan di GPU
    nvenc: bool = False             # ffmpeg bisa encode h264_nvenc

    def json(self) -> dict:
        return asdict(self)


def _jalankan(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def _cpu() -> int:
    try:
        return max(1, len(os.sched_getaffinity(0)))   # hormati batas taskset/container
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _ram_gb() -> float | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for baris in f:
                if baris.startswith("MemTotal:"):
                    return round(int(baris.split()[1]) / 1024**2, 1)
    except OSError:
        pass
    try:   # macOS / Unix lain
        return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (AttributeError, ValueError, OSError):
        return None


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


def _cuda_whisper() -> bool:
    """CTranslate2 (mesin faster-whisper) melihat GPU CUDA. Library cuBLAS/cuDNN yang
    kurang baru ketahuan saat model dimuat; pipeline.muat_whisper lalu jatuh ke CPU."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def _nvenc(jalankan=_jalankan) -> bool:
    """h264_nvenc ada di build ffmpeg ini DAN benar-benar bisa encode (driver cocok)."""
    kode, out = jalankan([FFMPEG, "-hide_banner", "-encoders"], 10)
    if kode != 0 or "h264_nvenc" not in out:
        return False
    kode, _ = jalankan([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                        "-i", "color=c=black:s=320x240:d=0.2", "-c:v", "h264_nvenc",
                        "-f", "null", "-"], 20)
    return kode == 0


def deteksi(jalankan=_jalankan) -> Hardware:
    gpu, vram = _gpu_nvidia(jalankan)
    return Hardware(cpu=_cpu(), ram_gb=_ram_gb(), gpu=gpu, vram_gb=vram,
                    cuda=bool(gpu) and _cuda_whisper(), nvenc=_nvenc(jalankan))


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
    elif c >= 6 and ram >= 8:
        whisper = "small"
    elif c >= 4 and ram >= 4:
        whisper = "base"
    else:
        whisper = "tiny"
    if hw.nvenc or c >= 6:
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
    """'otomatis' -> cuda bila tersedia. Pilihan 'cuda' dihormati (jatuh ke CPU saat dimuat
    bila ternyata gagal)."""
    if pilihan == "otomatis":
        return "cuda" if hw.cuda else "cpu"
    return pilihan


def encoder_efektif(pilihan: str, hw: Hardware) -> str:
    if pilihan == "otomatis":
        return "nvenc" if hw.nvenc else "cpu"
    return pilihan


def ringkas(hw: Hardware, s) -> dict:
    """Untuk UI/MCP: perangkat, rekomendasi, dan perangkat yang benar-benar dipakai."""
    return {"hardware": hw.json(), "rekomendasi": rekomendasi(hw),
            "whisper": whisper_efektif(s.perangkat_whisper, hw),
            "encoder": encoder_efektif(s.encoder, hw)}
