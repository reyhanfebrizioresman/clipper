"""Server MCP clipper (pintu 2 di spek): klien AI pengguna (Claude Code / Claude
Desktop / Codex) yang memilih momen & menulis hook; engine ini yang memotong,
memberi subtitle, dan menulis caption. Tidak ada panggilan LLM dari sisi server.

Kerja panjang (fetch_source, render_clips, auto_clips) berjalan sebagai job latar:
tool menunggu paling lama `tunggu_s` detik; bila belum selesai, ia mengembalikan
job_id untuk dipantau dengan job_status / dihentikan dengan cancel_job. Dengan begitu
klien yang batas waktunya pendek (mis. Codex) tetap bisa memakai server ini.

Jalankan (stdio):   .venv/bin/python scripts/mcp_server.py
Lewat SSH:          ssh -T reyhan /home/reyhan/clipper-v2/.venv/bin/python \
                        /home/reyhan/clipper-v2/scripts/mcp_server.py
HTTP (lokal):       .venv/bin/python scripts/mcp_server.py --http --port 8765
Mode HTTP tidak punya autentikasi: hanya untuk 127.0.0.1 (akses dari luar lewat SSH
tunnel). Host lain ditolak kecuali --izinkan-tanpa-auth.
"""

import argparse
import atexit
import functools
import logging
import time
from typing import Annotated, Any, Literal

import anyio
from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from .jobs import Job, JobManager
from .service import ClipperError, ClipperService, Selection

INSTRUKSI = """\
Clipper: mesin pemotong video panjang jadi klip vertikal 9:16 (subtitle terbakar +
caption berhashtag wajib) untuk campaign clipping (Clippo/TernakKlip).

Alur yang disarankan:
1. list_campaigns -> get_campaign_brief(slug): baca angle, keywords, larangan, durasi.
2. fetch_source(url_atau_path): unduh + transkrip (subtitle bawaan, atau Whisper di CPU,
   bisa beberapa menit). Hasilnya di-cache; panggil ulang itu instan.
3. Baca isi: get_transcript (per halaman) dan/atau list_candidate_windows (potongan yang
   sudah mulai/selesai di batas kalimat, plus skor kata kunci).
4. Kamu yang memilih momen terbaik sesuai angle & larangan brief, tulis hook_title yang
   jujur (bukan clickbait menyesatkan, tidak menyerang orang/brand), lalu render_clips.
   Waktu pilihan otomatis ditempel ke kalimat utuh dalam batas durasi campaign.
   Alternatif tanpa menalar sendiri: auto_clips (pemilih kata kunci / Gemini engine).
5. get_clip untuk caption per platform. Unggah tetap MANUAL (aturan TikTok/IG).

Job: fetch_source, render_clips, dan auto_clips mengembalikan {job_id, status, ...}.
status 'selesai' -> hasilnya di 'hasil'. status 'berjalan' -> panggil
job_status(job_id, tunggu_s) sampai selesai (jangan memulai job yang sama lagi);
cancel_job untuk menghentikan. Bila klienmu sanggup menunggu lama, beri tunggu_s
besar (mis. 600) supaya jarang perlu memantau ulang.
Semua path yang dikembalikan adalah path di server clipper, bukan di mesin klien.
"""

mcp = FastMCP("clipper", instructions=INSTRUKSI, log_level="WARNING")
JOBS = JobManager()
# server berhenti (klien menutup sesi) -> hentikan ffmpeg/yt-dlp yang masih jalan
atexit.register(JOBS.batal_semua)

TUNGGU_BAWAAN = 45.0   # di bawah batas waktu tool bawaan klien yang paling ketat
TUNGGU_MAKS = 3000.0   # di bawah idle timeout 30 menit Claude Code (progres tetap dikirim)
DETAK_S = 30.0


@functools.cache
def svc() -> ClipperService:
    return ClipperService.from_env()


async def _tunggu(ctx: Context | None, job: Job, tunggu_s: float, dari: int = 0) -> dict[str, Any]:
    """Tunggu job sampai selesai atau tunggu_s habis, sambil meneruskan progres ke klien
    (notifikasi progres juga menjaga klien tidak menganggap panggilan ini macet)."""
    tunggu_s = max(0.0, min(float(tunggu_s), TUNGGU_MAKS))
    batas = time.monotonic() + tunggu_s
    hitung, idx, detak = 0, dari, time.monotonic()

    async def kirim(pesan: str) -> None:
        nonlocal hitung, detak
        hitung += 1
        detak = time.monotonic()
        if ctx is None:
            return
        try:
            await ctx.report_progress(hitung, None, pesan)
            await ctx.info(pesan)
        except Exception:
            pass

    while True:
        baru = job.progres[idx:]
        idx += len(baru)
        for pesan in baru:
            await kirim(pesan)
        if job.beres.is_set() or time.monotonic() >= batas:
            break
        if time.monotonic() - detak >= DETAK_S:
            await kirim(f"[{job.jenis}] masih bekerja")
        await anyio.sleep(min(0.5, max(0.0, batas - time.monotonic())))

    hasil = job.ringkas()
    if not job.beres.is_set():
        hasil["petunjuk"] = (f"masih berjalan; panggil job_status(job_id='{job.id}', tunggu_s=...) "
                             "untuk menunggu lagi, atau cancel_job untuk menghentikan")
    return hasil


async def _mulai(ctx: Context | None, jenis: str, tunggu_s: float, fn, **argumen) -> dict[str, Any]:
    return await _tunggu(ctx, JOBS.mulai(jenis, fn, **argumen), tunggu_s)


class Pilihan(BaseModel):
    start: float = Field(description="detik mulai di video sumber")
    end: float = Field(description="detik selesai di video sumber")
    hook_title: str = Field("", description="kalimat pembuka caption; kosong = diambil dari transkrip")
    alasan: str = Field("", description="kenapa momen ini dipilih (disimpan di manifest)")


Gaya = Literal["lato", "bold", "karaoke"]
Tunggu = Annotated[float, Field(description="detik menunggu job sebelum kembali dengan status "
                                            "'berjalan' (maks 3000)")]


# ------------------------------------------------------------------ tool cepat
@mcp.tool()
def list_campaigns() -> list[dict[str, Any]]:
    """Daftar brief campaign yang tersedia (slug, nama, platform, rentang durasi, CPM)."""
    return svc().list_campaigns()


@mcp.tool()
def get_campaign_brief(slug: str) -> dict[str, Any]:
    """Brief lengkap satu campaign: hashtag wajib, keywords, angle, larangan, koreksi istilah."""
    return svc().get_campaign_brief(slug)


@mcp.tool()
def save_campaign_brief(brief: dict, timpa: bool = False) -> dict[str, Any]:
    """Simpan brief campaign baru (JSON). Wajib: slug, nama, cpm_rp, durasi_min_s,
    durasi_maks_s, platform, hashtag. Opsional: keywords, angle, larangan, koreksi.
    timpa=true untuk mengganti brief yang sudah ada."""
    return svc().save_campaign_brief(brief, timpa=timpa)


@mcp.tool()
def list_sources() -> list[dict[str, Any]]:
    """Sumber yang sudah di-fetch (terbaru dulu)."""
    return svc().list_sources()


@mcp.tool()
def get_transcript(source_id: str, mulai_s: float = 0.0, sampai_s: float | None = None,
                   offset: int = 0, limit: int = 400) -> dict[str, Any]:
    """Transkrip berwaktu, per halaman. Tiap baris: 'indeks | mulai-selesai | teks'.
    Pakai mulai_s/sampai_s untuk membaca bagian tertentu; 'berikutnya' = offset halaman lanjut."""
    return svc().get_transcript(source_id, mulai_s=mulai_s, sampai_s=sampai_s,
                                offset=offset, limit=limit)


@mcp.tool()
def list_candidate_windows(source_id: str, campaign: str, min_s: float | None = None,
                           max_s: float | None = None, maks_durasi: float = 60.0,
                           urut: Literal["waktu", "skor"] = "waktu",
                           offset: int = 0, limit: int = 30) -> dict[str, Any]:
    """Potongan kandidat yang mulai & selesai di batas kalimat, dalam batas durasi campaign
    (default dibatasi maks_durasi 60 dtk, disukai TikTok/Reels). skor_kata_kunci = jumlah
    kemunculan keywords brief. Ini bahan menalar, bukan keputusan akhir."""
    return svc().list_candidate_windows(source_id, campaign, min_s=min_s, max_s=max_s,
                                        maks_durasi=maks_durasi, urut=urut,
                                        offset=offset, limit=limit)


@mcp.tool()
def list_clips(campaign: str | None = None, source_id: str | None = None) -> list[dict[str, Any]]:
    """Klip yang sudah dirender (path di server, waktu, hook, ukuran)."""
    return svc().list_clips(campaign, source_id)


@mcp.tool()
def get_clip(campaign: str, source_id: str, file: str) -> dict[str, Any]:
    """Detail satu klip: caption, subtitle SRT, dan varian caption per platform
    (TikTok satu baris, dst.) beserta catatan safe-zone."""
    return svc().get_clip(campaign, source_id, file)


# ------------------------------------------------------------- tool job (panjang)
@mcp.tool()
async def fetch_source(
    sumber: Annotated[str, Field(description="URL video (YouTube dll.) atau path file di server")],
    whisper_model: Annotated[str, Field(description="model faster-whisper bila tak ada subtitle")] = "small",
    bahasa: Annotated[str | None, Field(description="kode bahasa Whisper, mis. 'id'; kosong = auto")] = None,
    paksa_whisper: Annotated[bool, Field(description="abaikan subtitle bawaan, transkrip ulang pakai Whisper")] = False,
    ulang: Annotated[bool, Field(description="abaikan cache, unduh & transkrip ulang")] = False,
    tunggu_s: Tunggu = TUNGGU_BAWAAN,
    ctx: Context = None,
) -> dict[str, Any]:
    """[job] Unduh (kalau URL) dan transkrip video sumber. hasil.source_id dipakai tool lain.
    Bisa lama (unduhan + Whisper CPU); hasil di-cache per sumber."""
    return await _mulai(ctx, "fetch_source", tunggu_s, svc().fetch_source, target=sumber,
                        whisper_model=whisper_model, language=bahasa,
                        paksa_whisper=paksa_whisper, ulang=ulang)


@mcp.tool()
async def render_clips(source_id: str, campaign: str, pilihan: list[Pilihan],
                       gaya: Gaya | None = None, reframe: bool | None = None,
                       maks_durasi: float = 60.0, tunggu_s: Tunggu = TUNGGU_BAWAAN,
                       ctx: Context = None) -> dict[str, Any]:
    """[job] Render momen pilihanmu jadi klip 9:16 + subtitle + caption (.txt berhashtag
    wajib). Waktu ditempel ke kalimat utuh dan durasi dijaga dalam batas campaign; pilihan
    yang tak muat dilaporkan di hasil.dilewati. reframe=true: crop ikut wajah (deteksi wajah
    seluruh video sekali per sumber, lalu di-cache); false: blur-pad. Nomor file melanjutkan
    klip yang sudah ada."""
    return await _mulai(ctx, "render_clips", tunggu_s, svc().render_clips,
                        source_id=source_id, slug=campaign,
                        pilihan=[Selection(**p.model_dump()) for p in pilihan],
                        gaya=gaya, reframe=reframe, maks_durasi=maks_durasi)


@mcp.tool()
async def auto_clips(source_id: str, campaign: str, jumlah: int = 5, lewati: int = 0,
                     ai: Literal["keyword", "gemini"] | None = None, gaya: Gaya | None = None,
                     reframe: bool | None = None, maks_durasi: float = 60.0,
                     tunggu_s: Tunggu = TUNGGU_BAWAAN, ctx: Context = None) -> dict[str, Any]:
    """[job] Pilih & render otomatis dengan pemilih engine sendiri (kata kunci, atau Gemini
    bila GEMINI_API_KEY ada di server). lewati = lompati N kandidat teratas (batch lanjutan).
    hasil.pemilih = pemilih yang benar-benar dipakai."""
    return await _mulai(ctx, "auto_clips", tunggu_s, svc().auto_clips,
                        source_id=source_id, slug=campaign, jumlah=jumlah, lewati=lewati,
                        ai=ai, gaya=gaya, reframe=reframe, maks_durasi=maks_durasi)


@mcp.tool()
async def job_status(job_id: str, tunggu_s: Tunggu = TUNGGU_BAWAAN,
                     ctx: Context = None) -> dict[str, Any]:
    """Pantau job: tunggu sampai selesai atau tunggu_s habis. tunggu_s=0 = cek sekali."""
    job = JOBS.get(job_id)
    if job is None:
        raise ClipperError(f"job {job_id!r} tidak dikenal (job hanya hidup selama sesi server; "
                           "hasil yang sudah jadi tetap ada di list_sources / list_clips)")
    return await _tunggu(ctx, job, tunggu_s, dari=len(job.progres))


@mcp.tool()
async def cancel_job(job_id: str) -> dict[str, Any]:
    """Hentikan job yang sedang berjalan (ffmpeg/yt-dlp dibunuh, Whisper & deteksi wajah
    berhenti di sampel berikutnya). Klip yang sudah selesai sebelum dibatalkan tetap ada."""
    job = JOBS.batal(job_id)
    if job is None:
        raise ClipperError(f"job {job_id!r} tidak dikenal")
    with anyio.move_on_after(15):
        while not job.beres.is_set():
            await anyio.sleep(0.2)
    return job.ringkas()


@mcp.tool()
def list_jobs() -> list[dict[str, Any]]:
    """Job di sesi server ini (terbaru dulu), tanpa isi hasil."""
    return [{k: v for k, v in j.ringkas(1).items() if k != "hasil"} for j in JOBS.daftar()]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Server MCP clipper")
    ap.add_argument("--http", action="store_true", help="streamable HTTP, bukan stdio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--izinkan-tanpa-auth", action="store_true",
                    help="izinkan --host selain loopback (server ini TANPA autentikasi)")
    args = ap.parse_args(argv)
    if args.http and args.host not in ("127.0.0.1", "localhost", "::1") and not args.izinkan_tanpa_auth:
        # tool-nya mengunduh URL & menulis file di server: jangan dibuka ke jaringan
        ap.error(f"--host {args.host} membuka server tanpa autentikasi ke jaringan; "
                 "pakai SSH tunnel, atau tambahkan --izinkan-tanpa-auth bila paham risikonya")
    # stdout milik protokol MCP (stdio): semua log ke stderr
    logging.basicConfig(level=logging.WARNING)
    if args.http:
        mcp.settings.host, mcp.settings.port = args.host, args.port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
