"""Inti layanan clipper yang dipakai bersama oleh server MCP (dan nanti web app).

Tata letak penyimpanan di bawah work dir:

    _sources/<source_id>/          video sumber (kalau diunduh), subtitle, meta.json,
                                   transcript.json  -> cache: fetch kedua kali instan
    <slug>/<source_id>/clips/      <slug>-NN.mp4 + .srt + .txt (caption)
    <slug>/<source_id>/clips.json  manifest klip (hook, waktu, asal pilihan)

Tidak ada impor berat di level modul; Whisper/mediapipe dimuat malas oleh pipeline.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Any, Callable, Iterable

from . import campaign as camp
from . import export, jobs, pipeline, select, source
from .brain.base import Proposal
from .config import (GAYA_BAWAAN_BARU, SKEMA, SKEMA_GAYA, SKEMA_PLATFORM, Settings,
                     SettingsError, baca_json, load_settings, simpan_json, terkunci_env)
from .styles import STYLES, semua_gaya
from .transcript import Segment

ROOT = Path(__file__).resolve().parent.parent
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_SOURCE_ID = re.compile(r"^[uf]-[0-9a-f]{12}$")
_KLIP = re.compile(r"^(?P<slug>[a-z0-9-]+)-(?P<n>\d{2,})\.mp4$")

Run = Callable[..., None]
Progress = Callable[[str, dict], None]


class ClipperError(Exception):
    """Kesalahan yang pesannya layak ditampilkan apa adanya ke klien."""


@dataclass
class Selection:
    """Momen pilihan klien AI. Waktu dalam detik video sumber."""
    start: float
    end: float
    hook_title: str = ""
    alasan: str = ""


def _cek_slug(slug: str) -> str:
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise ClipperError(f"slug campaign tidak sah: {slug!r} (huruf kecil, angka, '-')")
    return slug


def _cek_source_id(source_id: str) -> str:
    if not isinstance(source_id, str) or not _SOURCE_ID.match(source_id):
        raise ClipperError(f"source_id tidak sah: {source_id!r} — ambil dari fetch_source/list_sources")
    return source_id


def _durasi_video(video: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(video)],
            capture_output=True, check=True, timeout=60).stdout.decode().strip()
        return round(float(out), 1)
    except Exception:
        return None


def _mmss(detik: float) -> str:
    m, d = divmod(max(detik, 0.0), 60)
    return f"{int(m):02d}:{d:04.1f}"


class ClipperService:
    def __init__(self, campaigns_dir: Path, work_dir: Path,
                 settings: Settings | None = None, *, run: Run = jobs.run_bisa_batal,
                 transcriber: Callable[..., list[Segment]] = jobs.transkrip_bisa_batal,
                 face_detector: Callable | None = None,
                 settings_path: Path | None = None, toml_path: Path | str = "~/.clipper.toml"):
        self.campaigns_dir = Path(campaigns_dir).expanduser()
        self.work_dir = Path(work_dir).expanduser()
        # settings tetap (tes) atau dinamis: settings.json di work dir, diatur dari web UI,
        # dibaca ulang tiap kali berubah -> berlaku di job berikutnya tanpa restart
        self._settings_tetap = settings
        self.settings_path = Path(settings_path) if settings_path else self.work_dir / "settings.json"
        self.toml_path = Path(str(toml_path)).expanduser()
        self._settings_cache: Settings | None = None
        self._settings_kunci: tuple | None = None
        self.run = run
        self.transcriber = transcriber
        self.face_detector = face_detector  # None = mediapipe (reframe._mediapipe_detector)
        # fetch & render makan CPU penuh dan menomori file: satu per satu
        self._kunci = threading.Lock()

    @property
    def settings(self) -> Settings:
        if self._settings_tetap is not None:
            return self._settings_tetap

        def mtime(p: Path):
            try:
                return p.stat().st_mtime_ns
            except OSError:
                return None
        kunci = (mtime(self.settings_path), mtime(self.toml_path))
        if self._settings_cache is None or kunci != self._settings_kunci:
            self._settings_cache = load_settings(path=self.toml_path, json_path=self.settings_path)
            self._settings_kunci = kunci
        return self._settings_cache

    @settings.setter
    def settings(self, nilai: Settings) -> None:
        self._settings_tetap = nilai

    def gaya_subtitle(self, s: Settings | None = None) -> dict:
        return semua_gaya((s or self.settings).gaya_kustom)

    def get_settings(self) -> dict:
        """Setelan efektif untuk UI. API key tidak pernah dikirim utuh."""
        s = self.settings
        nilai = {f.name: getattr(s, f.name) for f in fields(Settings)}
        key = nilai.pop("gemini_api_key")
        nilai["gemini_api_key"] = {"ada": bool(key), "akhir": key[-4:] if key and len(key) >= 8 else ""}
        tersimpan = baca_json(self.settings_path)
        tersimpan.pop("gemini_api_key", None)
        return {"nilai": nilai, "tersimpan": sorted(tersimpan), "terkunci_env": terkunci_env(),
                "skema": SKEMA, "skema_gaya": SKEMA_GAYA, "gaya_baru": GAYA_BAWAAN_BARU,
                "skema_platform": SKEMA_PLATFORM, "gaya_bawaan": sorted(STYLES),
                "platform_efektif": export.aturan_efektif(s.platform),
                "file": str(self.settings_path)}

    def save_settings(self, perubahan: dict) -> dict:
        """Simpan perubahan (sebagian). null = kembalikan ke bawaan."""
        if not isinstance(perubahan, dict):
            raise ClipperError("setelan harus objek JSON")
        try:
            simpan_json(self.settings_path, perubahan, gaya_dikenal=set(STYLES))
        except SettingsError as e:
            raise ClipperError(str(e)) from None
        self._settings_kunci = None          # paksa baca ulang
        return self.get_settings()

    def _run(self, cmd: list[str], cwd=None) -> None:
        # periksa batal sebelum & sesudah: run palsu di tes tidak tahu soal token
        jobs.cek()
        self.run(cmd, cwd=cwd)
        jobs.cek()

    @contextmanager
    def _giliran(self, lapor: Progress):
        """Kunci kerja berat; selama mengantre tetap bisa dibatalkan."""
        if not self._kunci.acquire(blocking=False):
            lapor("antre", {"pesan": "menunggu job lain selesai"})
            while not self._kunci.acquire(timeout=1):
                jobs.cek()
        try:
            yield
        finally:
            self._kunci.release()

    def _detektor_wajah(self, source_id: str) -> Callable:
        """Detektor wajah ber-cache disk: deteksi seluruh video cukup sekali per sumber,
        bukan sekali per proses server (tiap sesi AI baru = proses baru)."""
        sdir = self._source_dir(source_id)

        def deteksi(video, sw: int, sh: int, fps: float):
            from . import reframe
            st = Path(video).stat()
            # versi detektor ikut jadi kunci: ganti petak/model/resolusi -> deteksi ulang,
            # bukan diam-diam memakai hasil detektor lama
            versi = ("custom" if self.face_detector is not None else
                     repr((getattr(reframe, "PETAK", None), getattr(reframe, "LEBAR_DEKODE", None))))
            sidik = [st.st_size, int(st.st_mtime), sw, sh, versi]
            p = sdir / f"wajah-{fps:g}fps.json"
            if p.is_file():
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                    if d.get("sidik") == sidik:
                        return [[reframe.FaceBox(*b) for b in f] for f in d["frame"]]
                except (ValueError, KeyError, TypeError):
                    pass  # cache rusak: deteksi ulang
            jobs.lapor("reframe", {"pesan": "deteksi wajah seluruh video (sekali per sumber)"})
            terakhir = [0.0]

            def tiap_sampel(t: float) -> None:
                jobs.cek()
                if t - terakhir[0] >= 120:
                    terakhir[0] = t
                    jobs.lapor("reframe", {"posisi_s": round(t)})

            try:
                if self.face_detector is not None:
                    frames = self.face_detector(video, sw, sh, fps)
                else:
                    frames = reframe._mediapipe_detector(video, sw, sh, fps, on_sample=tiap_sampel)
            except jobs.Dibatalkan:
                raise
            except Exception as e:
                # planner pipeline menelan error lalu memakai blur-pad: laporkan ke klien
                jobs.lapor("peringatan", {"pesan": f"reframe gagal ({type(e).__name__}: {e}); "
                                                   "klip memakai blur-pad"})
                raise
            p.write_text(json.dumps({"sidik": sidik, "frame": [
                [[round(b.t, 3), round(b.cx, 1), round(b.cy, 1), round(b.w, 1), round(b.h, 1)]
                 for b in f] for f in frames]}), encoding="utf-8")
            return frames
        return deteksi

    @classmethod
    def from_env(cls) -> "ClipperService":
        return cls(Path(os.environ.get("CLIPPER_CAMPAIGNS", ROOT / "campaigns")),
                   Path(os.environ.get("CLIPPER_WORK", ROOT / "work")))

    # ------------------------------------------------------------------ campaign
    def _campaign_path(self, slug: str) -> Path:
        return self.campaigns_dir / f"{_cek_slug(slug)}.json"

    def list_campaigns(self) -> list[dict]:
        hasil = []
        for p in sorted(self.campaigns_dir.glob("*.json")):
            try:
                c = camp.load(p)
            except Exception as e:  # brief rusak jangan menjatuhkan seluruh daftar
                hasil.append({"file": p.name, "error": str(e)[:200]})
                continue
            hasil.append({"slug": c.slug, "nama": c.nama, "platform": c.platform,
                          "durasi_s": [c.durasi_min_s, c.durasi_maks_s], "cpm_rp": c.cpm_rp})
        return hasil

    def get_campaign_brief(self, slug: str) -> dict:
        p = self._campaign_path(slug)
        if not p.is_file():
            ada = [x["slug"] for x in self.list_campaigns() if "slug" in x]
            raise ClipperError(f"campaign {slug!r} tidak ada. Yang tersedia: {ada}")
        return json.loads(p.read_text(encoding="utf-8"))

    def load_campaign(self, slug: str) -> camp.Campaign:
        self.get_campaign_brief(slug)  # pesan error yang ramah
        return camp.load(self._campaign_path(slug))

    def save_campaign_brief(self, brief: dict, *, timpa: bool = False) -> dict:
        if not isinstance(brief, dict):
            raise ClipperError("brief harus objek JSON")
        slug = _cek_slug(brief.get("slug", ""))
        wajib = ["nama", "cpm_rp", "durasi_min_s", "durasi_maks_s", "platform", "hashtag"]
        kurang = [k for k in wajib if k not in brief]
        if kurang:
            raise ClipperError(f"brief kurang field wajib: {kurang}")
        if not (0 < float(brief["durasi_min_s"]) < float(brief["durasi_maks_s"])):
            raise ClipperError("harus 0 < durasi_min_s < durasi_maks_s")
        if not brief["hashtag"]:
            raise ClipperError("hashtag wajib tidak boleh kosong")
        p = self._campaign_path(slug)
        if p.exists() and not timpa:
            raise ClipperError(f"campaign {slug!r} sudah ada; kirim timpa=true untuk mengganti")
        dikenal = camp.Campaign.__dataclass_fields__.keys()
        camp.Campaign(**{k: v for k, v in brief.items() if k in dikenal})  # validasi tipe dasar
        self.campaigns_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(brief, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {"slug": slug, "file": str(p)}

    # -------------------------------------------------------------------- sumber
    def _source_dir(self, source_id: str) -> Path:
        return self.work_dir / "_sources" / _cek_source_id(source_id)

    @staticmethod
    def _id_untuk(target: str) -> tuple[str, Path | None]:
        lokal = Path(target).expanduser()
        if lokal.is_file():
            lokal = lokal.resolve()
            return "f-" + hashlib.sha1(str(lokal).encode()).hexdigest()[:12], lokal
        if re.match(r"^https?://", target.strip(), re.I):
            return "u-" + hashlib.sha1(target.strip().encode()).hexdigest()[:12], None
        raise ClipperError(f"sumber bukan URL http(s) maupun file yang ada di server: {target!r}")

    def _meta(self, source_id: str) -> dict:
        p = self._source_dir(source_id) / "meta.json"
        if not p.is_file():
            raise ClipperError(f"sumber {source_id} belum di-fetch — panggil fetch_source dulu")
        return json.loads(p.read_text(encoding="utf-8"))

    def segments(self, source_id: str) -> list[Segment]:
        self._meta(source_id)
        data = json.loads((self._source_dir(source_id) / "transcript.json").read_text(encoding="utf-8"))
        return [Segment(a, b, t) for a, b, t in data]

    def fetch_source(self, target: str, *, whisper_model: str | None = None,
                     language: str | None = None, paksa_whisper: bool = False,
                     ulang: bool = False, on_progress: Progress | None = None) -> dict:
        """whisper_model/language None = ambil dari pengaturan."""
        lapor = on_progress or (lambda t, i: None)
        st_ = self.settings
        whisper_model = whisper_model or st_.whisper_model
        language = language or st_.bahasa
        source_id, lokal = self._id_untuk(target)
        sdir = self._source_dir(source_id)
        meta_p = sdir / "meta.json"

        def dari_cache() -> dict | None:
            if ulang or not meta_p.is_file():
                return None
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            video = Path(meta["video"])
            st = video.stat() if video.is_file() else None
            if st and (lokal is None or [st.st_size, int(st.st_mtime)] == meta.get("sidik")):
                return {**meta, "cache": True}
            return None

        if (m := dari_cache()) is not None:
            return m
        with self._giliran(lapor):
            # cek ulang: fetch lain untuk sumber yang sama mungkin baru selesai
            if (m := dari_cache()) is not None:
                return m
            sdir.mkdir(parents=True, exist_ok=True)
            vtt: Path | None = None
            if lokal is not None:
                video = lokal
                teks = sorted(lokal.parent.glob(lokal.stem + "*.vtt")) + \
                    sorted(lokal.parent.glob(lokal.stem + "*.srt"))
                vtt = teks[0] if teks else None
            else:
                lapor("unduh", {"url": target})
                self._run(source.download_cmd(target, sdir, tinggi=st_.tinggi_unduh))
                try:
                    self._run(source.subtitle_cmd(target, sdir, bahasa=st_.bahasa_subtitle))
                except RuntimeError as e:  # YouTube sering 429; Whisper cadangannya
                    lapor("peringatan", {"pesan": f"subtitle tidak terambil: {str(e)[:120]}"})
                mp4 = sorted(sdir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
                if not mp4:
                    raise ClipperError("unduhan selesai tapi tidak ada file .mp4")
                video = mp4[-1]
                teks = sorted(sdir.glob(video.stem + "*.vtt")) + sorted(sdir.glob(video.stem + "*.srt"))
                vtt = teks[0] if teks else None

            if paksa_whisper:
                vtt = None
            asal = "subtitle" if vtt else "whisper"
            lapor("transkrip", {"asal": asal, "subtitle": vtt.name if vtt else None})
            segmen = self.transcriber(video, vtt, whisper_model=whisper_model, language=language) \
                if not vtt else self.transcriber(video, vtt)
            if not segmen and vtt:
                lapor("peringatan", {"pesan": "subtitle kosong; pakai Whisper"})
                asal = "whisper"
                segmen = self.transcriber(video, None, whisper_model=whisper_model, language=language)
            if not segmen:
                raise ClipperError("transkrip kosong — tidak ada ucapan yang bisa dipotong")

            (sdir / "transcript.json").write_text(
                json.dumps([[round(s.start, 3), round(s.end, 3), s.text] for s in segmen],
                           ensure_ascii=False), encoding="utf-8")
            st = video.stat()
            meta = {
                "source_id": source_id,
                "asal": target,
                "video": str(video),
                "subtitle": str(vtt) if vtt else None,
                "transkrip_dari": asal,
                "durasi_s": _durasi_video(video) or round(segmen[-1].end, 1),
                "jumlah_segmen": len(segmen),
                "sidik": [st.st_size, int(st.st_mtime)],
            }
            meta_p.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            return {**meta, "cache": False}

    def list_sources(self) -> list[dict]:
        hasil = []
        for p in sorted((self.work_dir / "_sources").glob("*/meta.json"),
                        key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            hasil.append({k: m.get(k) for k in
                          ("source_id", "asal", "durasi_s", "jumlah_segmen", "transkrip_dari")})
        return hasil

    def get_source(self, source_id: str) -> dict:
        """Meta satu sumber, termasuk path video di server."""
        m = self._meta(source_id)
        return {k: m.get(k) for k in ("source_id", "asal", "video", "durasi_s",
                                      "jumlah_segmen", "transkrip_dari")}

    def get_transcript(self, source_id: str, *, mulai_s: float = 0.0,
                       sampai_s: float | None = None, offset: int = 0,
                       limit: int = 400) -> dict:
        segmen = self.segments(source_id)
        dalam = [(i, s) for i, s in enumerate(segmen)
                 if s.end > mulai_s and (sampai_s is None or s.start < sampai_s)]
        limit = max(1, min(int(limit), 2000))
        offset = max(0, int(offset))
        halaman = dalam[offset: offset + limit]
        return {
            "source_id": source_id,
            "total_segmen_dalam_rentang": len(dalam),
            "offset": offset,
            "berikutnya": offset + len(halaman) if offset + len(halaman) < len(dalam) else None,
            "format": "indeks | mulai_s-selesai_s | teks",
            "baris": [f"{i} | {s.start:.1f}-{s.end:.1f} | {s.text}" for i, s in halaman],
        }

    # ------------------------------------------------------------------ kandidat
    def _batas(self, c: camp.Campaign, min_s: float | None, max_s: float | None,
               maks_durasi: float | None) -> tuple[float, float]:
        if maks_durasi is None:
            maks_durasi = self.settings.maks_durasi
        lo = c.durasi_min_s if min_s is None else max(float(min_s), 1.0)
        hi = min(c.durasi_maks_s, maks_durasi) if max_s is None else float(max_s)
        if lo >= hi:
            raise ClipperError(f"rentang durasi tidak sah: {lo}-{hi} dtk")
        return lo, hi

    def list_candidate_windows(self, source_id: str, slug: str, *, min_s: float | None = None,
                               max_s: float | None = None, maks_durasi: float | None = None,
                               urut: str = "waktu", offset: int = 0, limit: int = 30) -> dict:
        c = self.load_campaign(slug)
        lo, hi = self._batas(c, min_s, max_s, maks_durasi)
        segmen = self.segments(source_id)
        jendela = select.build_windows(segmen, lo, hi)
        akhir = dict(zip(map(id, segmen), select.penanda_akhir(segmen)))
        kunci = [k.lower() for k in c.keywords]
        isi = []
        for w in jendela:
            teks = w.text.lower()
            isi.append({"start": round(w.start, 2), "end": round(w.end, 2),
                        "durasi": round(w.end - w.start, 1), "rentang": f"{_mmss(w.start)}-{_mmss(w.end)}",
                        "skor_kata_kunci": sum(teks.count(k) for k in kunci),
                        # False: kalimat terakhir lebih panjang dari batas durasi, jadi
                        # potongan ini berhenti di tengah kalimat
                        "akhir_kalimat": akhir.get(id(w.segments[-1]), True),
                        "teks": w.text})
        if urut == "skor":
            isi.sort(key=lambda x: (-x["skor_kata_kunci"], x["start"]))
        elif urut != "waktu":
            raise ClipperError("urut harus 'waktu' atau 'skor'")
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        halaman = isi[offset: offset + limit]
        return {"campaign": slug, "durasi_s": [lo, hi], "total": len(isi), "offset": offset,
                "berikutnya": offset + len(halaman) if offset + len(halaman) < len(isi) else None,
                "kandidat": halaman}

    # -------------------------------------------------------------------- render
    def _clip_dir(self, slug: str, source_id: str) -> Path:
        return self.work_dir / _cek_slug(slug) / _cek_source_id(source_id) / "clips"

    def _manifest(self, slug: str, source_id: str) -> list[dict]:
        p = self._clip_dir(slug, source_id).parent / "clips.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else []

    def _nomor_berikut(self, klip_dir: Path) -> int:
        nomor = [int(m["n"]) for p in klip_dir.glob("*.mp4") if (m := _KLIP.match(p.name))]
        return max(nomor, default=0)

    def _render(self, source_id: str, slug: str, chooser, jumlah: int, *, gaya: str | None,
                reframe: bool | None, maks_durasi: float | None, catatan: list[dict],
                on_progress: Progress | None) -> list[dict]:
        """catatan[i] = info tambahan untuk window ke-i yang dikembalikan chooser."""
        c = self.load_campaign(slug)
        meta = self._meta(source_id)
        video = Path(meta["video"])
        if not video.is_file():
            raise ClipperError(f"video sumber hilang: {video} — fetch_source ulang dengan ulang=true")
        segmen = self.segments(source_id)
        dasar = self.settings                    # satu snapshot untuk seluruh job
        if maks_durasi is None:
            maks_durasi = dasar.maks_durasi
        semua = self.gaya_subtitle(dasar)
        gaya = gaya or dasar.subtitle_style
        if gaya not in semua:
            raise ClipperError(f"gaya subtitle tidak dikenal: {gaya!r}. Pilihan: {sorted(semua)}")
        s = dasar if reframe is None else replace(dasar, reframe=reframe)

        with self._giliran(on_progress or (lambda t, i: None)):
            klip_dir = self._clip_dir(slug, source_id)
            klip_dir.mkdir(parents=True, exist_ok=True)
            lewati = self._nomor_berikut(klip_dir)
            hasil = pipeline.process(
                c, video, segmen, klip_dir, jumlah=jumlah, lewati=lewati,
                maks_durasi=maks_durasi, chooser=chooser, run=self._run,
                on_progress=on_progress, style=semua[gaya], settings=s,
                reframe_planner=pipeline.make_reframe_planner(
                    s, detector=self._detektor_wajah(source_id)))
            manifest = self._manifest(slug, source_id)
            baru = []
            for r in hasil:
                urutan = r.rank - lewati - 1  # nomor dihitung di dalam kunci: aman dari balapan
                ekstra = catatan[urutan] if 0 <= urutan < len(catatan) else {}
                caption_p = klip_dir / r.file.replace(".mp4", ".txt")
                caption = caption_p.read_text(encoding="utf-8") if caption_p.is_file() else None
                item = {**asdict(r), "source_id": source_id, "campaign": slug, "gaya": gaya,
                        **ekstra}
                if caption:
                    # ClipResult.hook dipotong 80 karakter; simpan hook utuh dari caption
                    # supaya varian per platform sama persis dengan file .txt
                    item["hook"] = caption.rsplit("\n\n", 1)[0]
                manifest = [m for m in manifest if m.get("file") != r.file] + [item]
                baru.append({**item, "path": str(klip_dir / r.file), "caption": caption})
            (klip_dir.parent / "clips.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            return baru

    def render_clips(self, source_id: str, slug: str, pilihan: Iterable[Selection | dict], *,
                     gaya: str | None = None, reframe: bool | None = None,
                     maks_durasi: float | None = None, on_progress: Progress | None = None) -> dict:
        """Render momen pilihan klien. Tiap pilihan ditempel ke batas kalimat
        (aturan campaign: jangan memotong sampai mengubah makna)."""
        c = self.load_campaign(slug)
        segmen = self.segments(source_id)
        lo, hi = self._batas(c, None, None, maks_durasi)
        jendela: list[select.Window] = []
        dilewati, catatan, terlihat = [], [], set()
        for i, p in enumerate(pilihan):
            sel = p if isinstance(p, Selection) else Selection(**p)
            if sel.end <= sel.start:
                dilewati.append({"pilihan": i, "alasan": "end harus > start"})
                continue
            snap = select.snap_to_windows(
                [Proposal(sel.start, sel.end, sel.hook_title.strip(), sel.alasan, score=None)],
                segmen, lo, hi, maks_pangkas=self.settings.maks_pangkas)
            if not snap:
                dilewati.append({"pilihan": i, "alasan": f"tidak bisa ditempel ke kalimat utuh "
                                 f"dengan durasi {lo:g}-{hi:g} dtk"})
                continue
            w = snap[0]
            if (w.start, w.end) in terlihat:
                dilewati.append({"pilihan": i, "alasan": "sama dengan pilihan sebelumnya setelah ditempel"})
                continue
            terlihat.add((w.start, w.end))
            jendela.append(w)
            catatan.append({"diminta": [sel.start, sel.end], "alasan": sel.alasan})
        if not jendela:
            return {"klip": [], "dilewati": dilewati}

        klip = self._render(source_id, slug, lambda *a: jendela, len(jendela), gaya=gaya,
                            reframe=reframe, maks_durasi=maks_durasi, catatan=catatan,
                            on_progress=on_progress)
        return {"klip": klip, "dilewati": dilewati}

    def auto_clips(self, source_id: str, slug: str, *, jumlah: int = 5, lewati: int = 0,
                   ai: str | None = None, gaya: str | None = None, reframe: bool | None = None,
                   maks_durasi: float | None = None, on_progress: Progress | None = None) -> dict:
        """Pilih momen dengan otak engine sendiri (kata kunci / Gemini), lalu render."""
        s = self.settings if ai is None else replace(self.settings, ai_provider=ai)
        if s.ai_provider not in ("keyword", "gemini"):
            raise ClipperError("ai harus 'keyword' atau 'gemini'")
        lewati = max(0, int(lewati))
        dasar = pipeline.make_chooser(s)
        dipakai = {"pemilih": "keyword" if dasar is pipeline.keyword_chooser else s.ai_provider,
                   "catatan": None}
        if s.ai_provider != "keyword" and dasar is pipeline.keyword_chooser:
            dipakai["catatan"] = f"otak {s.ai_provider} tidak bisa dimuat; pakai kata kunci"

        def lapor(tahap: str, info: dict) -> None:
            if tahap == "pilih" and "dari" in info:
                # pipeline.process melabeli dari/sampai dengan nomor file; di sini yang
                # bermakna adalah peringkat kandidat yang benar-benar dipilih
                info = {**info, "dari": lewati + 1, "sampai": lewati + info.get("dipilih", 0)}
            if on_progress:
                on_progress(tahap, info)

        # Fallback ditangani di sini, bukan di pipeline.process: fallback bawaan memakai
        # 'lewati' = nomor file (salah kandidat) dan tidak melaporkan pemilih sebenarnya.
        def pilih(seg, c, lo, hi, n, _nomor_file):
            try:
                return dasar(seg, c, lo, hi, n, lewati)
            except Exception as e:
                if dasar is pipeline.keyword_chooser:
                    raise
                dipakai.update(pemilih="keyword", catatan=f"otak {s.ai_provider} gagal ({e}); "
                                                            "pakai kata kunci")
                lapor("peringatan", {"pesan": dipakai["catatan"]})
                return pipeline.keyword_chooser(seg, c, lo, hi, n, lewati)

        klip = self._render(source_id, slug, pilih, jumlah, gaya=gaya, reframe=reframe,
                            maks_durasi=maks_durasi, catatan=[], on_progress=lapor)
        return {"klip": klip, **{k: v for k, v in dipakai.items() if v is not None}}

    # --------------------------------------------------------------------- klip
    def list_clips(self, slug: str | None = None, source_id: str | None = None) -> list[dict]:
        hasil = []
        pola_slug = _cek_slug(slug) if slug else "*"
        pola_src = _cek_source_id(source_id) if source_id else "[uf]-*"
        for mp in sorted(self.work_dir.glob(f"{pola_slug}/{pola_src}/clips.json")):
            for m in json.loads(mp.read_text(encoding="utf-8")):
                f = mp.parent / "clips" / m["file"]
                if f.is_file():
                    hasil.append({"campaign": m.get("campaign"), "source_id": m.get("source_id"),
                                  "file": m["file"], "path": str(f), "mulai": m.get("mulai"),
                                  "durasi": m.get("durasi"), "hook": m.get("hook"),
                                  "ukuran_mb": round(f.stat().st_size / 1e6, 1)})
        return hasil

    def get_clip(self, slug: str, source_id: str, file: str) -> dict:
        if not _KLIP.match(file or ""):
            raise ClipperError(f"nama file klip tidak sah: {file!r}")
        klip_dir = self._clip_dir(slug, source_id)
        f = klip_dir / file
        if not f.is_file():
            raise ClipperError(f"klip tidak ada: {f}")
        m = next((x for x in self._manifest(slug, source_id) if x.get("file") == file), {})
        cap_p, srt_p = f.with_suffix(".txt"), f.with_suffix(".srt")
        c = self.load_campaign(slug)
        caption = cap_p.read_text(encoding="utf-8") if cap_p.is_file() else None
        # sumber kebenaran hook = caption .txt (manifest lama menyimpan hook terpotong)
        hook = caption.rsplit("\n\n", 1)[0] if caption else m.get("hook")
        varian = ([asdict(v) for v in export.platform_variants(c, hook, aturan=self.settings.platform)]
                  if hook else [])
        return {**m, "hook": hook, "path": str(f), "ukuran_mb": round(f.stat().st_size / 1e6, 1),
                "caption": caption,
                "srt": srt_p.read_text(encoding="utf-8") if srt_p.is_file() else None,
                "varian_platform": varian}
