"""Orkestrasi video -> klip 9:16, sebagai pustaka yang bisa diimpor (CLI & web)."""
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import campaign as camp
from . import render, select, transcript
from .brain.base import Scorer
from .config import Settings
from .styles import STYLES, SubtitleStyle
from .campaign import Campaign
from .transcript import Segment

Chooser = Callable[[list[Segment], Campaign, float, float, int, int], list[select.Window]]
Progress = Callable[[str, dict], None]


@dataclass
class ClipResult:
    file: str
    mulai: float
    durasi: float
    hook: str
    rank: int
    skor: float | None = None


def run_subprocess(cmd: list[str], cwd=None) -> None:
    hasil = subprocess.run(cmd, capture_output=True, cwd=cwd)
    if hasil.returncode != 0:
        raise RuntimeError(f"gagal: {' '.join(cmd[:3])}...\n"
                           f"{hasil.stderr.decode(errors='replace')[-700:]}")


def keyword_chooser(segmen: list[Segment], c: Campaign, min_s: float, max_s: float,
                    jumlah: int, lewati: int) -> list[select.Window]:
    jendela = select.build_windows(segmen, min_s, max_s)
    peringkat = select.rank(jendela, c.keywords)
    return peringkat[lewati: lewati + jumlah]


def brain_chooser(scorer: Scorer) -> Chooser:
    """Chooser berbasis otak AI: usulan -> tempel ke batas kalimat -> urut skor."""
    def pilih(segmen, c, min_s, max_s, jumlah, lewati):
        props = sorted(scorer.propose(segmen, c, min_s=min_s, max_s=max_s),
                       key=lambda p: -p.score)
        windows = select.snap_to_windows(props, segmen, min_s, max_s)
        # snap_to_windows menjaga urutan & membuang duplikat/usulan tak sah, jadi
        # petakan balik jendela -> usulan lewat batas kalimat yang dipilihnya
        for w in windows:
            asal = next((p for p in props if w.start <= p.start < w.end), None) \
                or min(props, key=lambda p: abs(p.start - w.start))
            w.hook_title = asal.hook_title
            w.skor = asal.score
        return windows[lewati: lewati + jumlah]
    return pilih


def make_chooser(settings: Settings) -> Chooser:
    if settings.ai_provider == "gemini":
        try:
            from .brain.gemini import GeminiScorer
            return brain_chooser(GeminiScorer(settings.gemini_api_key or ""))
        except Exception:
            return keyword_chooser
    return keyword_chooser


def _probe_dims(video: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0:s=x", str(video)],
        capture_output=True, check=True).stdout.decode().strip()
    w, h = out.split("x")
    return int(w), int(h)


def make_reframe_planner(settings: Settings, *, fps_sample: float = 5):
    """Planner (video, window) -> filtergraph | None. Semua impor/probe malas;
    gagal apa pun -> None (cut_cmd memakai blur-pad)."""
    if not settings.reframe:
        return None
    cache: dict = {}

    def planner(video: Path, w: select.Window) -> str | None:
        try:
            from . import reframe
            key = str(video)
            if key not in cache:
                sw, sh = _probe_dims(video)
                cache[key] = (sw, sh, reframe.detect_faces(video, sw, sh, fps_sample=fps_sample))
            sw, sh, frames = cache[key]
            potong = frames[int(w.start * fps_sample): int(w.end * fps_sample)]
            return reframe.build_filter(reframe.plan_reframe(potong, sw, sh), sw, sh)
        except Exception:
            return None
    return planner


def transcribe(video: Path, vtt: Path | None, *, whisper_model: str = "small") -> list[Segment]:
    if vtt:
        return transcript.parse(vtt.read_text(encoding="utf-8"))
    import faster_whisper  # lazy: berat, hanya dipakai saat tidak ada subtitle
    model = faster_whisper.WhisperModel(whisper_model, device="cpu", compute_type="int8")
    segmen, _ = model.transcribe(str(video), language="id", vad_filter=True)
    return [Segment(s.start, s.end, s.text.strip()) for s in segmen]


def process(c: Campaign, video: Path, segmen: list[Segment], klip_dir: Path, *,
            jumlah: int = 5, lewati: int = 0, maks_durasi: float = 60.0,
            chooser: Chooser = keyword_chooser, run=run_subprocess,
            on_progress: Progress | None = None,
            style: SubtitleStyle = STYLES["lato"],
            reframe_planner: Callable[[Path, select.Window], str | None] | None = None,
            ) -> list[ClipResult]:
    def lapor(tahap: str, **info) -> None:
        if on_progress:
            on_progress(tahap, info)

    klip_dir = Path(klip_dir)
    klip_dir.mkdir(parents=True, exist_ok=True)
    batas_atas = min(c.durasi_maks_s, maks_durasi)
    lapor("pilih", segmen=len(segmen))
    try:
        terbaik = chooser(segmen, c, c.durasi_min_s, batas_atas, jumlah, lewati)
    except Exception as e:
        lapor("peringatan", pesan=f"otak AI gagal ({e}); pakai pemilih kata kunci")
        terbaik = keyword_chooser(segmen, c, c.durasi_min_s, batas_atas, jumlah, lewati)
    lapor("pilih", dipilih=len(terbaik), dari=lewati + 1, sampai=lewati + len(terbaik))

    hasil: list[ClipResult] = []
    for n, w in enumerate(terbaik, lewati + 1):
        nama = f"{c.slug}-{n:02d}"
        mentah = klip_dir / f"{nama}-raw.mp4"
        srt = klip_dir / f"{nama}.srt"
        final = klip_dir / f"{nama}.mp4"
        lapor("render", nama=nama, rank=n, durasi=w.end - w.start)
        fg = reframe_planner(video, w) if reframe_planner else None
        run(render.cut_cmd(video, w.start, w.end, mentah, filtergraph=fg))
        render.write_srt(w, srt, koreksi=c.koreksi)
        # dijalankan dari folder klip: filter subtitles ffmpeg memakai nama file
        # relatif (path absolut butuh escaping yang rapuh)
        run(render.burn_cmd(mentah.resolve(), srt.name, final.resolve(), style=style), cwd=klip_dir)
        mentah.unlink(missing_ok=True)

        hook = w.hook_title or select.hook(w, koreksi=c.koreksi)
        (klip_dir / f"{nama}.txt").write_text(camp.caption(c, hook), encoding="utf-8")
        hasil.append(ClipResult(file=final.name, mulai=round(w.start, 1),
                                durasi=round(w.end - w.start, 1), hook=hook[:80],
                                rank=n, skor=w.skor))
    lapor("selesai", jumlah=len(hasil))
    return hasil
