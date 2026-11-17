"""Job latar + pembatalan untuk kerja panjang (unduh, Whisper, deteksi wajah, render).

Klien MCP membatasi lama satu panggilan tool (Codex: pendek secara bawaan; Claude Code:
batal bila diam 30 menit). Karena itu kerja panjang berjalan di thread sendiri, tool
hanya menunggu sebentar lalu mengembalikan job_id yang bisa dipantau/dibatalkan.

Konteks job (token batal + pelapor progres) disimpan thread-local, sehingga kode di
lapisan dalam (ffmpeg, Whisper, deteksi wajah) bisa memeriksa pembatalan dan melapor
progres tanpa parameter tambahan di setiap fungsi.
"""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable

_lokal = threading.local()


class Dibatalkan(Exception):
    """Job dihentikan atas permintaan pengguna."""


class Token:
    """Token pembatalan: menandai batal dan membunuh subprocess yang sedang jalan."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._kunci = threading.Lock()
        self._proc: subprocess.Popen | None = None

    @property
    def dibatalkan(self) -> bool:
        return self._event.is_set()

    def batal(self) -> None:
        self._event.set()
        with self._kunci:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def cek(self) -> None:
        if self._event.is_set():
            raise Dibatalkan("job dibatalkan")

    def _pasang(self, proc: subprocess.Popen | None) -> None:
        with self._kunci:
            self._proc = proc
        # batal() bisa terjadi tepat sebelum proc terpasang: jangan biarkan lolos
        if proc is not None and self._event.is_set():
            proc.terminate()


def cek() -> None:
    """Lempar Dibatalkan bila job thread ini sudah dibatalkan (no-op di luar job)."""
    token = getattr(_lokal, "token", None)
    if token is not None:
        token.cek()


def lapor(tahap: str, info: dict) -> None:
    """Kirim progres ke job thread ini (no-op di luar job)."""
    fn = getattr(_lokal, "lapor", None)
    if fn is not None:
        fn(tahap, info)


def run_bisa_batal(cmd: list[str], cwd=None) -> None:
    """Pengganti pipeline.run_subprocess yang bisa dihentikan lewat Token.

    stdin=DEVNULL: proses anak tidak boleh mewarisi stdin server MCP stdio
    (itu jalur protokol), walau ffmpeg di uji nyata tidak terbukti memakannya.
    """
    token = getattr(_lokal, "token", None)
    if token is not None:
        token.cek()
    proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if token is not None:
        token._pasang(proc)
    try:
        _, err = proc.communicate()
    finally:
        if token is not None:
            token._pasang(None)
    if token is not None:
        token.cek()
    if proc.returncode != 0:
        raise RuntimeError(f"gagal: {' '.join(map(str, cmd[:3]))}...\n"
                           f"{err.decode(errors='replace')[-700:]}")


def transkrip_bisa_batal(video, vtt, *, whisper_model: str = "small",
                         language: str | None = None, perangkat: str = "cpu"):
    """Seperti pipeline.transcribe, tapi Whisper diperiksa pembatalannya per segmen
    dan melapor posisi tiap ~60 dtk audio (Whisper CPU bisa belasan menit)."""
    from . import pipeline
    from .transcript import Segment

    if vtt:
        return pipeline.transcribe(video, vtt)
    cek()
    model = pipeline.muat_whisper(whisper_model, perangkat, lapor)
    cek()
    lapor("transkrip", {"perangkat": "GPU" if getattr(model, "clipper_perangkat", "cpu") == "cuda" else "CPU"})
    # deteksi bahasa + prompt tanda baca (lihat pipeline.whisper_segments)
    segmen, info = pipeline.whisper_segments(model, video, language)
    hasil, terakhir = [], 0.0
    for s in segmen:
        cek()
        hasil.append(Segment(s.start, s.end, s.text.strip()))
        if s.end - terakhir >= 60:
            terakhir = s.end
            lapor("transkrip", {"posisi_s": round(s.end), "total_s": round(info.duration)})
    return hasil


@dataclass
class Job:
    id: str
    jenis: str
    status: str = "berjalan"          # berjalan | selesai | gagal | dibatalkan
    dibuat: float = field(default_factory=time.time)
    selesai_pada: float | None = None
    progres: list[str] = field(default_factory=list)
    hasil: Any = None
    galat: str | None = None
    token: Token = field(default_factory=Token, repr=False)
    beres: threading.Event = field(default_factory=threading.Event, repr=False)

    def ringkas(self, n_progres: int = 5) -> dict:
        d: dict[str, Any] = {
            "job_id": self.id, "jenis": self.jenis, "status": self.status,
            "durasi_s": round((self.selesai_pada or time.time()) - self.dibuat, 1),
            "progres_terakhir": self.progres[-n_progres:],
        }
        if self.hasil is not None:
            d["hasil"] = self.hasil
        if self.galat:
            d["galat"] = self.galat
        return d


class JobManager:
    MAKS_PROGRES = 200

    def __init__(self, maks_simpan: int = 100) -> None:
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._kunci = threading.Lock()
        self.maks_simpan = maks_simpan

    def mulai(self, jenis: str, fn: Callable[..., Any], **argumen) -> Job:
        """Jalankan fn(on_progress=..., **argumen) di thread latar."""
        job = Job(id=uuid.uuid4().hex[:10], jenis=jenis)

        def catat(tahap: str, info: dict) -> None:
            job.progres.append(f"[{tahap}] " + ", ".join(f"{k}={v}" for k, v in info.items()))
            if len(job.progres) > self.MAKS_PROGRES:
                del job.progres[: -self.MAKS_PROGRES]

        def jalan() -> None:
            _lokal.token, _lokal.lapor = job.token, catat
            try:
                job.hasil = fn(on_progress=catat, **argumen)
                job.status = "selesai"
            except Dibatalkan:
                job.status, job.galat = "dibatalkan", "dibatalkan atas permintaan"
            except Exception as e:  # noqa: BLE001 - pesan galat diteruskan ke klien
                if job.token.dibatalkan:
                    job.status, job.galat = "dibatalkan", "dibatalkan atas permintaan"
                else:
                    job.status, job.galat = "gagal", f"{type(e).__name__}: {e}"[-1500:]
            finally:
                job.selesai_pada = time.time()
                _lokal.token = _lokal.lapor = None
                job.beres.set()

        with self._kunci:
            self._jobs[job.id] = job
            # buang riwayat job lama yang sudah selesai
            while len(self._jobs) > self.maks_simpan:
                lama = next((k for k, j in self._jobs.items() if j.beres.is_set()), None)
                if lama is None:
                    break
                del self._jobs[lama]
        threading.Thread(target=jalan, name=f"job-{job.id}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        with self._kunci:
            return self._jobs.get(job_id)

    def daftar(self) -> list[Job]:
        with self._kunci:
            return list(reversed(self._jobs.values()))

    def batal(self, job_id: str) -> Job | None:
        job = self.get(job_id)
        if job is not None and not job.beres.is_set():
            job.token.batal()
        return job

    def batal_semua(self) -> None:
        for job in self.daftar():
            if not job.beres.is_set():
                job.token.batal()
