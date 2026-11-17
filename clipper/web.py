"""Web app clipper (pintu 1 di spek): Clipper Studio di browser.

Memakai ClipperService yang sama dengan server MCP. Kerja berat (fetch, render, auto)
berjalan sebagai job latar; UI memantau lewat /api/jobs.

Jalankan:   .venv/bin/python scripts/web.py            (http://127.0.0.1:8780)
Tidak ada autentikasi: server hanya mendengarkan loopback, akses dari mesin lain lewat
SSH tunnel. Host lain ditolak kecuali --izinkan-tanpa-auth.

Perlindungan untuk server lokal tanpa login:
- header Host harus loopback (menangkal DNS rebinding dari situs lain);
- request yang mengubah data wajib membawa header X-Clipper (browser tidak mengirim
  header khusus lintas situs tanpa preflight CORS, yang tidak kita izinkan).
"""
from __future__ import annotations

import argparse
import atexit
import functools
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .jobs import Job, JobManager
from .service import ClipperError, ClipperService, Selection

STATIC = Path(__file__).resolve().parent / "web_static"
HOST_LOOPBACK = {"127.0.0.1", "localhost", "::1", "[::1]"}
AMAN = {"GET", "HEAD", "OPTIONS"}
_NAMA_AMAN = re.compile(r"[^A-Za-z0-9._-]+")


class SumberBaru(BaseModel):
    sumber: str = Field(min_length=1, max_length=2000)
    bahasa: str | None = None
    paksa_whisper: bool = False
    ulang: bool = False


class Pilihan(BaseModel):
    start: float
    end: float
    hook_title: str = ""
    alasan: str = ""


class RenderReq(BaseModel):
    source_id: str
    campaign: str
    pilihan: list[Pilihan] = Field(min_length=1, max_length=30)
    gaya: str | None = None
    reframe: bool | None = None
    maks_durasi: float | None = Field(None, gt=0, le=600)


class AutoReq(BaseModel):
    source_id: str
    campaign: str
    jumlah: int = Field(3, ge=1, le=20)
    lewati: int = Field(0, ge=0)
    ai: str | None = None
    gaya: str | None = None
    reframe: bool | None = None
    maks_durasi: float | None = Field(None, gt=0, le=600)


def _host_lokal(host_header: str | None) -> bool:
    if not host_header:
        return False
    h = host_header.strip().lower()
    if h.startswith("["):                       # [::1]:8780
        h = h[: h.find("]") + 1]
    elif h.count(":") == 1:                     # 127.0.0.1:8780
        h = h.split(":", 1)[0]
    return h in HOST_LOOPBACK


def create_app(svc: ClipperService | None = None, jobs: JobManager | None = None, *,
               izinkan_host_lain: bool = False) -> FastAPI:
    app = FastAPI(title="Clipper Studio", docs_url=None, redoc_url=None, openapi_url=None)
    JOBS = jobs or JobManager()

    @functools.cache
    def layanan() -> ClipperService:
        return svc or ClipperService.from_env()

    app.state.jobs = JOBS
    app.state.svc = layanan

    @app.middleware("http")
    async def jaga(request: Request, call_next):
        if not izinkan_host_lain and not _host_lokal(request.headers.get("host")):
            return JSONResponse({"detail": "host tidak diizinkan"}, status_code=403)
        if request.method not in AMAN and request.headers.get("x-clipper") != "1":
            return JSONResponse({"detail": "header X-Clipper wajib"}, status_code=403)
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    @app.exception_handler(ClipperError)
    async def _galat_clipper(_req: Request, e: ClipperError):
        return JSONResponse({"detail": str(e)}, status_code=400)

    def _job_json(job: Job, n: int = 8) -> dict[str, Any]:
        return job.ringkas(n)

    def _mulai(jenis: str, fn, **arg) -> dict[str, Any]:
        return _job_json(JOBS.mulai(jenis, fn, **arg))

    # ------------------------------------------------------------------ info
    @app.get("/api/info")
    def info() -> dict[str, Any]:
        s = layanan().settings
        return {"gaya": sorted(layanan().gaya_subtitle(s)), "gaya_bawaan": s.subtitle_style,
                "reframe_bawaan": s.reframe, "ai_bawaan": s.ai_provider,
                "maks_durasi_bawaan": s.maks_durasi, "gemini_siap": bool(s.gemini_api_key)}

    # ------------------------------------------------------------- pengaturan
    @app.get("/api/settings")
    def pengaturan() -> dict:
        return layanan().get_settings()

    @app.put("/api/settings")
    def simpan_pengaturan(perubahan: dict[str, Any]) -> dict:
        return layanan().save_settings(perubahan)

    @app.get("/api/fonts")
    def font() -> list[str]:
        """Font yang terpasang di server (untuk gaya subtitle; libass memakai fontconfig)."""
        try:
            out = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True,
                                 timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            return []
        return sorted({n.strip() for baris in out.splitlines() for n in baris.split(",") if n.strip()})

    # -------------------------------------------------------------- campaign
    @app.get("/api/campaigns")
    def campaigns() -> list[dict]:
        return layanan().list_campaigns()

    @app.get("/api/campaigns/{slug}")
    def campaign(slug: str) -> dict:
        return layanan().get_campaign_brief(slug)

    @app.put("/api/campaigns/{slug}")
    def simpan_campaign(slug: str, brief: dict[str, Any]) -> dict:
        if brief.get("slug") != slug:
            raise ClipperError("slug di URL dan di brief harus sama")
        return layanan().save_campaign_brief(brief, timpa=True)

    @app.post("/api/campaigns")
    def campaign_baru(brief: dict[str, Any]) -> dict:
        return layanan().save_campaign_brief(brief, timpa=False)

    # ---------------------------------------------------------------- sumber
    @app.get("/api/sources")
    def sources() -> list[dict]:
        return layanan().list_sources()

    @app.post("/api/sources")
    def sumber_baru(req: SumberBaru) -> dict:
        target = req.sumber.strip()
        if not re.match(r"^https?://", target, re.I):
            # path server bebas tidak boleh dari browser: hanya URL, atau unggah file
            raise ClipperError("sumber harus URL http(s); untuk file lokal pakai unggah")
        return _mulai("fetch_source", layanan().fetch_source, target=target,
                      language=req.bahasa or None, paksa_whisper=req.paksa_whisper, ulang=req.ulang)

    @app.post("/api/sources/upload")
    def unggah(file: UploadFile = File(...), bahasa: str = Form(""),
               paksa_whisper: bool = Form(False)) -> dict:
        nama = _NAMA_AMAN.sub("_", Path(file.filename or "video").name).strip("._") or "video"
        if not nama.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4v")):
            raise ClipperError("format tidak didukung: unggah .mp4/.mov/.mkv/.webm/.m4v")
        folder = layanan().work_dir / "_uploads"
        folder.mkdir(parents=True, exist_ok=True)
        tujuan = folder / f"{uuid.uuid4().hex[:8]}-{nama}"
        with tujuan.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=4 * 1024 * 1024)
        return _mulai("fetch_source", layanan().fetch_source, target=str(tujuan),
                      language=bahasa or None, paksa_whisper=paksa_whisper)

    @app.get("/api/sources/{source_id}")
    def sumber(source_id: str) -> dict:
        m = layanan().get_source(source_id)
        m.pop("video", None)                          # path server tidak perlu ke browser
        return m

    @app.get("/api/sources/{source_id}/transcript")
    def transkrip(source_id: str) -> dict:
        seg = layanan().segments(source_id)
        return {"source_id": source_id,
                "segmen": [[round(s.start, 2), round(s.end, 2), s.text] for s in seg]}

    @app.get("/api/sources/{source_id}/candidates")
    def kandidat(source_id: str, campaign: str, urut: str = "skor", limit: int = 200,
                 maks_durasi: float | None = None) -> dict:
        return layanan().list_candidate_windows(source_id, campaign, urut=urut, limit=limit,
                                                maks_durasi=maks_durasi)

    @app.get("/media/source/{source_id}")
    def video_sumber(source_id: str):
        p = Path(layanan().get_source(source_id)["video"])
        if not p.is_file():
            raise HTTPException(404, "video sumber hilang")
        return FileResponse(p)                        # mendukung Range: video bisa di-seek

    # ---------------------------------------------------------------- render
    @app.post("/api/render")
    def render(req: RenderReq) -> dict:
        pilihan = [Selection(**p.model_dump()) for p in req.pilihan]
        layanan().load_campaign(req.campaign)          # galat cepat sebelum masuk antrean
        return _mulai("render_clips", layanan().render_clips, source_id=req.source_id,
                      slug=req.campaign, pilihan=pilihan, gaya=req.gaya, reframe=req.reframe,
                      maks_durasi=req.maks_durasi)

    @app.post("/api/auto")
    def auto(req: AutoReq) -> dict:
        layanan().load_campaign(req.campaign)
        return _mulai("auto_clips", layanan().auto_clips, source_id=req.source_id,
                      slug=req.campaign, jumlah=req.jumlah, lewati=req.lewati, ai=req.ai,
                      gaya=req.gaya, reframe=req.reframe, maks_durasi=req.maks_durasi)

    # ------------------------------------------------------------------ jobs
    @app.get("/api/jobs")
    def daftar_job() -> list[dict]:
        return [_job_json(j, 3) for j in JOBS.daftar()]

    @app.get("/api/jobs/{job_id}")
    def status_job(job_id: str) -> dict:
        job = JOBS.get(job_id)
        if job is None:
            raise HTTPException(404, "job tidak dikenal")
        return _job_json(job, 30)

    @app.post("/api/jobs/{job_id}/cancel")
    def batal_job(job_id: str) -> dict:
        job = JOBS.batal(job_id)
        if job is None:
            raise HTTPException(404, "job tidak dikenal")
        return _job_json(job)

    # ------------------------------------------------------------------ klip
    @app.get("/api/clips")
    def klip(campaign: str | None = None, source_id: str | None = None) -> list[dict]:
        return list(reversed(layanan().list_clips(campaign or None, source_id or None)))

    @app.get("/api/clips/{slug}/{source_id}/{file}")
    def detail_klip(slug: str, source_id: str, file: str) -> dict:
        return layanan().get_clip(slug, source_id, file)

    @app.get("/media/clip/{slug}/{source_id}/{file}")
    def video_klip(slug: str, source_id: str, file: str, unduh: bool = False):
        d = layanan().get_clip(slug, source_id, file)   # memvalidasi slug/id/nama file
        return FileResponse(d["path"], media_type="video/mp4",
                            filename=file if unduh else None)

    # -------------------------------------------------------------------- UI
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def beranda():
        return FileResponse(STATIC / "index.html", media_type="text/html")

    return app


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Clipper Studio (web UI)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--izinkan-tanpa-auth", action="store_true",
                    help="izinkan --host selain loopback (server ini TANPA autentikasi)")
    args = ap.parse_args(argv)
    lokal = args.host in ("127.0.0.1", "localhost", "::1")
    if not lokal and not args.izinkan_tanpa_auth:
        ap.error(f"--host {args.host} membuka server tanpa autentikasi ke jaringan; "
                 "pakai SSH tunnel, atau tambahkan --izinkan-tanpa-auth bila paham risikonya")
    app = create_app(izinkan_host_lain=not lokal)
    atexit.register(app.state.jobs.batal_semua)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
