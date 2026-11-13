"""Reframe 16:9 -> 9:16: ikuti satu wajah (crop), atau blur-pad kalau ragu."""
from __future__ import annotations

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


def _mediapipe_detector(video, src_w: int, src_h: int, fps_sample: float) -> list[list[FaceBox]]:
    # Import malas: mediapipe/cv2 hanya dibutuhkan di sini.
    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / fps_sample))
    out: list[list[FaceBox]] = []
    idx = 0
    with mp.solutions.face_detection.FaceDetection(model_selection=1) as det:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                res = det.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                t = idx / fps
                faces = []
                for d in res.detections or []:
                    b = d.location_data.relative_bounding_box
                    faces.append(FaceBox(t, (b.xmin + b.width / 2) * src_w,
                                         (b.ymin + b.height / 2) * src_h,
                                         b.width * src_w, b.height * src_h))
                out.append(faces)
            idx += 1
    cap.release()
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
                 multi_face_ratio=0.3) -> SingleFace | BlurPad:
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
    return SingleFace(smooth_path(raw, max_dx_per_s=src_w * 0.15))


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
