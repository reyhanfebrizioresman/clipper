from clipper.reframe import (
    BlurPad, FaceBox, SingleFace, build_filter, detect_faces, plan_reframe, smooth_path,
)


def test_plan_reframe_blurpad_when_two_faces_dominate():
    frames = [[FaceBox(t, 100, 500, 80, 80), FaceBox(t, 900, 500, 80, 80)] for t in range(10)]
    assert isinstance(plan_reframe(frames, 1920, 1080), BlurPad)


def test_plan_reframe_singleface_when_one_face():
    frames = [[FaceBox(t, 950 + t * 5, 500, 80, 80)] for t in range(10)]
    assert isinstance(plan_reframe(frames, 1920, 1080), SingleFace)


def test_plan_reframe_blurpad_when_no_faces():
    assert isinstance(plan_reframe([[] for _ in range(10)], 1920, 1080), BlurPad)
    assert isinstance(plan_reframe([], 1920, 1080), BlurPad)


def test_smooth_path_has_no_jitter():
    noisy = [(0, 100), (0.1, 900), (0.2, 100), (0.3, 900)]
    sm = smooth_path(noisy, max_dx_per_s=200)
    assert all(abs(sm[i + 1][1] - sm[i][1]) <= 200 * 0.1 + 1e-6 for i in range(len(sm) - 1))


def test_build_filter_blurpad_contains_boxblur():
    assert "boxblur" in build_filter(BlurPad(), 1920, 1080)


def test_build_filter_singleface_crops_and_scales():
    f = build_filter(SingleFace([(0, 500), (1, 700), (2, 900)]), 1920, 1080)
    assert "crop=" in f and "scale=1080:1920" in f and "boxblur" not in f


def test_detect_faces_uses_injected_detector():
    calls = []

    def fake(video, w, h, fps):
        calls.append((w, h, fps))
        return [[FaceBox(0, 1, 2, 3, 4)]]

    assert detect_faces("v.mp4", 1920, 1080, fps_sample=3, detector=fake)[0][0].cx == 1
    assert calls == [(1920, 1080, 3)]
