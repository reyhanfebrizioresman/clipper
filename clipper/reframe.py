"""Reframe 16:9 -> 9:16: ikuti satu wajah (crop), atau blur-pad kalau ragu."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_PATH_POINTS = 40  # batasi panjang ekspresi ffmpeg


@dataclass
class FaceBox:
    t: float
    cx: float
    cy: float
    w: float
    h: float


@dataclass
class SingleFace:
    centres: list[tuple[float, float]] = field(default_factory=list)  # (t, cx)


@dataclass
class BlurPad:
    pass


# Petak deteksi, sebagai pecahan lebar frame. BlazeFace short-range memperkecil gambar
# ke 128 px, sehingga wajah di bidikan lebar (podcast berdua, panggung) tidak tertangkap.
# Mendeteksi per petak membuat wajah ~2x lebih besar di mata model; deteksi ganda di
# daerah tumpang tindih digabung dengan NMS (gabung_deteksi).
PETAK: tuple[tuple[float, float], ...] = ((0.0, 0.4), (0.3, 0.7), (0.6, 1.0))
LEBAR_DEKODE = 1280


def _iou(a, b) -> float:
    ax1, ay1, bx1, by1 = a[0] + a[2], a[1] + a[3], b[0] + b[2], b[1] + b[3]
    iw = max(0.0, min(ax1, bx1) - max(a[0], b[0]))
    ih = max(0.0, min(ay1, by1) - max(a[1], b[1]))
    inter = iw * ih
    return inter / (a[2] * a[3] + b[2] * b[3] - inter + 1e-9)


def gabung_deteksi(kotak: list[tuple], ambang: float = 0.3) -> list[tuple]:
    """NMS: kotak (x, y, w, h, skor); yang saling tumpang tindih > ambang disatukan,
    kotak berskor tertinggi dipertahankan."""
    simpan: list[tuple] = []
    for k in sorted(kotak, key=lambda k: -k[4]):
        if all(_iou(k, s) < ambang for s in simpan):
            simpan.append(k)
    return simpan


def deteksi_petak(detect: Callable, frame, petak=PETAK) -> list[tuple]:
    """detect(gambar_rgb) -> [(x, y, w, h, skor)] dalam piksel gambar itu.
    Jalankan per petak, geser x ke koordinat frame, lalu gabungkan."""
    import numpy as np
    lebar = frame.shape[1]
    hasil = []
    for x0f, x1f in petak:
        x0, x1 = int(x0f * lebar), int(x1f * lebar)
        for x, y, w, h, skor in detect(np.ascontiguousarray(frame[:, x0:x1])):
            hasil.append((x + x0, y, w, h, skor))
    return gabung_deteksi(hasil)


def _model_wajah() -> str:
    """Model BlazeFace untuk MediaPipe Tasks (API lama mp.solutions sudah dihapus
    sejak mediapipe 0.10.30, jadi detektor lama gagal diam-diam -> selalu blur-pad)."""
    p = Path(os.environ.get("CLIPPER_FACE_MODEL", "") or
             Path(__file__).resolve().parent.parent / "models" / "blaze_face_short_range.tflite")
    if not p.is_file():
        raise FileNotFoundError(f"model deteksi wajah tidak ada: {p} "
                                "(blaze_face_short_range.tflite dari MediaPipe; atau set CLIPPER_FACE_MODEL)")
    return str(p)


def _mediapipe_detector(video, src_w: int, src_h: int, fps_sample: float, *,
                        on_sample: Callable[[float], None] | None = None,
                        lebar: int = LEBAR_DEKODE) -> list[list[FaceBox]]:
    # on_sample(t) dipanggil tiap frame sampel: progres & pembatalan (boleh raise).
    # Frame didekode oleh ffmpeg sistem, bukan cv2.VideoCapture: OpenCV bawaan pip tidak
    # bisa mendekode AV1 (format umum unduhan YouTube) -> 0 frame -> diam-diam blur-pad.
    # ffmpeg sekalian menurunkan ke fps_sample & LEBAR_DEKODE (cukup tajam untuk petak).
    import subprocess

    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions, vision

    opsi = vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=_model_wajah()),
        running_mode=vision.RunningMode.IMAGE, min_detection_confidence=0.5)
    tinggi = max(2, round(lebar * src_h / max(src_w, 1) / 2) * 2)
    cmd = [os.getenv("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-nostdin", "-i", str(video),
           "-an", "-vf", f"fps={fps_sample},scale={lebar}:{tinggi}",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    ukuran = lebar * tinggi * 3
    out: list[list[FaceBox]] = []
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL)
    try:
        with vision.FaceDetector.create_from_options(opsi) as det:
            def deteksi_satu(rgb):
                gambar = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                return [(d.bounding_box.origin_x, d.bounding_box.origin_y, d.bounding_box.width,
                         d.bounding_box.height, d.categories[0].score if d.categories else 0.0)
                        for d in det.detect(gambar).detections]

            while True:
                buf = proc.stdout.read(ukuran)
                if len(buf) < ukuran:
                    break
                t = len(out) / fps_sample
                if on_sample is not None:
                    on_sample(t)
                frame = np.frombuffer(buf, np.uint8).reshape(tinggi, lebar, 3)
                faces = []
                for x, y, w, h, _ in deteksi_petak(deteksi_satu, frame):
                    # piksel frame dekode -> skala ke ukuran sumber
                    faces.append(FaceBox(t, (x + w / 2) / lebar * src_w, (y + h / 2) / tinggi * src_h,
                                         w / lebar * src_w, h / tinggi * src_h))
                out.append(faces)
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    if not out:
        raise RuntimeError(f"tidak ada frame yang bisa didekode dari {video} (ffmpeg rc={proc.returncode})")
    return out


def detect_faces(video: Path, src_w: int, src_h: int, *, fps_sample=5,
                 detector: Callable | None = None) -> list[list[FaceBox]]:
    """Satu list wajah per instan sampel. detector(video, w, h, fps) -> list[list[FaceBox]]."""
    return (detector or _mediapipe_detector)(video, src_w, src_h, fps_sample)


def smooth_path(centres: list[tuple[float, float]], *, max_dx_per_s: float) -> list[tuple[float, float]]:
    """Batasi |Δcx| per detik agar tidak goyang."""
    if not centres:
        return []
    out = [centres[0]]
    for t, cx in centres[1:]:
        pt, pcx = out[-1]
        lim = max_dx_per_s * max(t - pt, 0.0)
        out.append((t, pcx + max(-lim, min(lim, cx - pcx))))
    return out


def plan_reframe(frames: list[list[FaceBox]], src_w: int, src_h: int, *,
                 multi_face_ratio=0.3, kecepatan=0.15) -> SingleFace | BlurPad:
    """kecepatan = geser kamera maksimum per detik, dalam porsi lebar sumber."""
    if not frames:
        return BlurPad()
    n = len(frames)
    multi = sum(1 for f in frames if len(f) >= 2)
    zero = sum(1 for f in frames if not f)
    if multi / n > multi_face_ratio or zero / n > multi_face_ratio:
        return BlurPad()
    raw = []
    for f in frames:
        if f:
            p = max(f, key=lambda b: b.w * b.h)
            raw.append((p.t, p.cx))
    return SingleFace(smooth_path(raw, max_dx_per_s=src_w * kecepatan))


def blur_pad_graph(out_w: int = 1080, out_h: int = 1920) -> str:
    return (
        "[0:v]split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},boxblur=40:2[bg];"
        f"[fgsrc]scale={out_w}:-2[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)*0.38[v]"
    )


def _x_expr(points: list[tuple[float, float]], crop_w: float, src_w: int) -> str:
    """Ekspresi ffmpeg piecewise-linear untuk x crop (koma di-escape)."""
    half, hi = crop_w / 2, src_w - crop_w
    pts = [(t, min(max(cx - half, 0.0), hi)) for t, cx in points]
    if len(pts) > MAX_PATH_POINTS:
        stride = len(pts) / MAX_PATH_POINTS
        pts = [pts[int(i * stride)] for i in range(MAX_PATH_POINTS)] + [pts[-1]]
    expr = f"{pts[-1][1]:.1f}"
    for (t0, x0), (t1, x1) in reversed(list(zip(pts, pts[1:]))):
        dt = max(t1 - t0, 1e-6)
        seg = f"{x0:.1f}+({x1 - x0:.1f})*(t-{t0:.3f})/{dt:.3f}"
        expr = f"if(lt(t,{t1:.3f}),{seg},{expr})"
    return f"if(lt(t,{pts[0][0]:.3f}),{pts[0][1]:.1f},{expr})"


def build_filter(plan: SingleFace | BlurPad, src_w: int, src_h: int,
                 out_w=1080, out_h=1920) -> str:
    if isinstance(plan, BlurPad) or not plan.centres:
        return blur_pad_graph(out_w, out_h)
    crop_w = min(src_w, src_h * out_w / out_h)
    cw = int(crop_w) // 2 * 2
    x = _x_expr(plan.centres, cw, src_w)
    return f"[0:v]crop={cw}:{src_h}:'{x}':0,scale={out_w}:{out_h}[v]"
