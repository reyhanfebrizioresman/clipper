"""Orkestrasi video -> klip 9:16, sebagai pustaka yang bisa diimpor (CLI & web)."""
import subprocess
import sys
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
        return windows[lewati: lewati + jumlah]
    return pilih


def make_chooser(settings: Settings) -> Chooser:
    if settings.ai_provider == "gemini":
        try:
            from .brain.gemini import GeminiScorer
            return brain_chooser(GeminiScorer(settings.gemini_api_key or "",
                                              model=settings.gemini_model))
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


def rebase_frames(frames, start: float, end: float, fps_sample: float):
    """Ambil sampel dalam [start, end] dan geser waktunya ke relatif-klip (0..durasi):
    -ss sebelum -i membuat `t` di filtergraph dimulai dari 0."""
    from .reframe import FaceBox
    potong = frames[int(start * fps_sample): int(end * fps_sample)]
    return [[FaceBox(fb.t - start, fb.cx, fb.cy, fb.w, fb.h) for fb in f] for f in potong]


def make_reframe_planner(settings: Settings, *, fps_sample: float | None = None, detector=None):
    """Planner (video, window) -> filtergraph | None. Semua impor/probe malas;
    gagal apa pun -> None (cut_cmd memakai blur-pad)."""
    if not settings.reframe:
        return None
    fps_sample = fps_sample or settings.reframe_fps
    cache: dict = {}

    def planner(video: Path, w: select.Window) -> str | None:
        try:
            from . import reframe
            key = str(video)
            if key not in cache:
                sw, sh = _probe_dims(video)
                cache[key] = (sw, sh, reframe.detect_faces(video, sw, sh, fps_sample=fps_sample,
                                                              detector=detector))
            sw, sh, frames = cache[key]
            potong = rebase_frames(frames, w.start, w.end, fps_sample)
            rencana = reframe.plan_reframe(potong, sw, sh, multi_face_ratio=settings.reframe_ambang,
                                           kecepatan=settings.reframe_kecepatan)
            return reframe.build_filter(rencana, sw, sh)
        except Exception as e:
            # tetap jalan dengan blur-pad, tapi jangan diam: dulu mediapipe yang rusak
            # membuat reframe tak pernah aktif tanpa ada yang tahu
            if not cache.get("_sudah_lapor"):
                cache["_sudah_lapor"] = True
                print(f"[peringatan] reframe gagal ({e}); pakai blur-pad", file=sys.stderr)
            return None
    return planner


# Whisper (small) untuk bahasa Indonesia sering menulis tanpa tanda baca sama sekali;
# padahal pemilihan potongan mencari awal kalimat dari tanda baca (select.py). Contoh
# kalimat bertanda baca di initial_prompt membuat Whisper ikut menulis tanda baca
# (uji podcast FTM: 0% -> 65% segmen berakhir tanda baca).
PROMPT_TANDA_BACA = {
    "id": "Halo, selamat datang. Hari ini kita ngobrol santai, ya? Betul. "
          "Jadi, menurut kamu gimana? Menarik, kan.",
}


def whisper_segments(model, video: Path, language: str | None = None):
    """Jalankan Whisper dengan prompt tanda baca sesuai bahasa. Bahasa dideteksi dulu
    bila tidak diberikan: prompt Indonesia ke audio bahasa lain bisa membelokkan hasil.
    Audio didekode sekali dan dipakai untuk deteksi maupun transkripsi."""
    import faster_whisper
    dekode = getattr(faster_whisper, "decode_audio", None)
    sr = getattr(getattr(model, "feature_extractor", None), "sampling_rate", 16000)
    audio = dekode(str(video), sampling_rate=sr) if dekode else str(video)
    if language is None and dekode is not None and hasattr(model, "detect_language"):
        try:
            language = model.detect_language(audio, vad_filter=True)[0]
        except Exception:
            language = None  # biarkan transcribe mendeteksi sendiri, tanpa prompt
    return model.transcribe(audio, language=language, vad_filter=True,
                            initial_prompt=PROMPT_TANDA_BACA.get(language or ""))


def muat_whisper(nama: str, perangkat: str = "cpu", on_progress: Progress | None = None):
    """Muat model Whisper. perangkat 'cuda' dicoba dulu (float16) dan diuji dengan satu
    deteksi bahasa pada audio hening: cuBLAS/cuDNN yang hilang baru ketahuan saat model
    benar-benar jalan. Gagal apa pun -> CPU int8, dengan peringatan."""
    import faster_whisper  # lazy: berat, hanya dipakai saat tidak ada subtitle
    if perangkat == "cuda":
        try:
            model = faster_whisper.WhisperModel(nama, device="cuda", compute_type="float16")
            if hasattr(model, "detect_language"):
                import numpy as np
                model.detect_language(np.zeros(16000, dtype=np.float32))
            model.clipper_perangkat = "cuda"
            return model
        except Exception as e:
            if on_progress:
                on_progress("peringatan", {"pesan": f"Whisper GPU gagal ({str(e)[:120]}); pakai CPU"})
    model = faster_whisper.WhisperModel(nama, device="cpu", compute_type="int8")
    model.clipper_perangkat = "cpu"
    return model


def transcribe(video: Path, vtt: Path | None, *, whisper_model: str = "small",
               language: str | None = None, perangkat: str = "cpu") -> list[Segment]:
    if vtt:
        return transcript.parse(vtt.read_text(encoding="utf-8"))
    model = muat_whisper(whisper_model, perangkat)
    # language=None → auto-deteksi bahasa (jangan paksa 'id' ke audio non-Indonesia)
    segmen, _ = whisper_segments(model, video, language)
    return [Segment(s.start, s.end, s.text.strip()) for s in segmen]


def process(c: Campaign, video: Path, segmen: list[Segment], klip_dir: Path, *,
            jumlah: int = 5, lewati: int = 0, maks_durasi: float = 60.0,
            chooser: Chooser = keyword_chooser, run=run_subprocess,
            on_progress: Progress | None = None,
            style: SubtitleStyle = STYLES["lato"],
            reframe_planner: Callable[[Path, select.Window], str | None] | None = None,
            settings: Settings | None = None,
            ) -> list[ClipResult]:
    s = settings or Settings()   # kualitas encode & panjang baris subtitle
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

    # encoder: 'nvenc' (GPU) bila diminta; gagal sekali -> CPU untuk sisa job ini
    enc = ["nvenc" if s.encoder == "nvenc" else "cpu"]

    def encode(buat: Callable[[str], list[str]], cwd=None) -> None:
        if enc[0] == "nvenc":
            try:
                run(buat("nvenc"), cwd=cwd)
                return
            except RuntimeError as e:
                lapor("peringatan", pesan=f"encoder GPU gagal ({str(e)[:120]}); pakai CPU")
                enc[0] = "cpu"
        run(buat("cpu"), cwd=cwd)

    hasil: list[ClipResult] = []
    for n, w in enumerate(terbaik, lewati + 1):
        nama = f"{c.slug}-{n:02d}"
        mentah = klip_dir / f"{nama}-raw.mp4"
        srt = klip_dir / f"{nama}.srt"
        final = klip_dir / f"{nama}.mp4"
        lapor("render", nama=nama, rank=n, durasi=round(w.end - w.start, 1))
        fg = reframe_planner(video, w) if reframe_planner else None
        encode(lambda enc: render.cut_cmd(video, w.start, w.end, mentah, filtergraph=fg,
                                          crf=s.crf, preset=s.preset,
                                          audio_kbps=s.audio_kbps, encoder=enc))
        render.write_srt(w, srt, maks_karakter=s.karakter_per_baris, koreksi=c.koreksi)
        # dijalankan dari folder klip: filter subtitles ffmpeg memakai nama file
        # relatif (path absolut butuh escaping yang rapuh)
        encode(lambda enc: render.burn_cmd(mentah.resolve(), srt.name, final.resolve(),
                                           style=style, crf=s.crf, preset=s.preset,
                                           encoder=enc), cwd=klip_dir)
        mentah.unlink(missing_ok=True)

        hook = (w.hook_title or "").strip() or select.hook(w, koreksi=c.koreksi)
        (klip_dir / f"{nama}.txt").write_text(camp.caption(c, hook), encoding="utf-8")
        hasil.append(ClipResult(file=final.name, mulai=round(w.start, 1),
                                durasi=round(w.end - w.start, 1), hook=hook[:80],
                                rank=n, skor=w.skor))
    lapor("selesai", jumlah=len(hasil))
    return hasil
