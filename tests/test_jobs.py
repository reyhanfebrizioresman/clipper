import json
import time

import anyio
import pytest

from clipper import jobs
from clipper.config import Settings
from clipper.service import ClipperService, Selection
from tests.test_service import BRIEF, SEGMEN, _fake_run


def _tunggu(job, s=10):
    assert job.beres.wait(s), "job tidak selesai"
    return job


def test_job_selesai_dan_gagal():
    m = jobs.JobManager()
    ok = _tunggu(m.mulai("x", lambda on_progress, a: (on_progress("tahap", {"a": a}), a * 2)[1], a=21))
    assert ok.status == "selesai" and ok.hasil == 42 and ok.progres == ["[tahap] a=21"]
    bad = _tunggu(m.mulai("x", lambda on_progress: 1 / 0))
    assert bad.status == "gagal" and "ZeroDivisionError" in bad.galat


def test_cancel_kills_running_subprocess_quickly():
    m = jobs.JobManager()
    job = m.mulai("x", lambda on_progress: jobs.run_bisa_batal(["sleep", "30"]))
    time.sleep(0.5)
    t = time.time()
    m.batal(job.id)
    _tunggu(job, 10)
    assert job.status == "dibatalkan" and time.time() - t < 6


def test_cancel_stops_python_loop_via_cek():
    m = jobs.JobManager()

    def kerja(on_progress):
        for _ in range(300):
            jobs.cek()
            time.sleep(0.05)
        return "tidak boleh sampai sini"

    job = m.mulai("x", kerja)
    time.sleep(0.2)
    m.batal(job.id)
    assert _tunggu(job).status == "dibatalkan" and job.hasil is None


def test_run_bisa_batal_reports_failure_like_original():
    with pytest.raises(RuntimeError, match="gagal"):
        jobs.run_bisa_batal(["sh", "-c", "echo rusak >&2; exit 3"])


@pytest.fixture
def svc(tmp_path):
    camps = tmp_path / "campaigns"
    camps.mkdir()
    (camps / "uji.json").write_text(json.dumps(BRIEF))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    s = ClipperService(camps, tmp_path / "work", Settings(reframe=False), run=_fake_run,
                       transcriber=lambda v, vtt, **k: list(SEGMEN))
    s._video = video
    return s


def test_face_detection_cached_on_disk(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    from clipper.reframe import FaceBox
    panggil = []
    svc.face_detector = lambda v, w, h, f: panggil.append(1) or [[FaceBox(0.0, 1, 2, 3, 4)], []]
    a = svc._detektor_wajah(sid)(svc._video, 1920, 1080, 5)
    # detektor baru (= proses server baru) tetap memakai cache disk
    b = svc._detektor_wajah(sid)(svc._video, 1920, 1080, 5)
    assert len(panggil) == 1 and a == b and b[0][0].cx == 1
    svc._detektor_wajah(sid)(svc._video, 1280, 720, 5)      # ukuran beda -> deteksi ulang
    assert len(panggil) == 2


def test_auto_clips_progress_label_uses_candidate_rank(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    svc.render_clips(sid, "uji", [Selection(15, 18)])      # nomor file sudah 1
    log = []
    svc.auto_clips(sid, "uji", jumlah=1, lewati=0, ai="keyword",
                   on_progress=lambda t, i: log.append((t, i)))
    info = next(i for t, i in log if t == "pilih" and "dari" in i)
    assert info["dari"] == 1 and info["sampai"] == 1


def test_waiting_render_queues_and_can_be_cancelled(svc):
    m = jobs.JobManager()
    sid = svc.fetch_source(str(svc._video))["source_id"]
    svc._kunci.acquire()                       # job lain sedang memegang giliran
    try:
        job = m.mulai("render", svc.render_clips, source_id=sid, slug="uji",
                      pilihan=[Selection(6, 15)])
        time.sleep(0.3)
        assert any("antre" in p for p in job.progres)
        m.batal(job.id)
        assert _tunggu(job).status == "dibatalkan"
    finally:
        svc._kunci.release()


def test_mcp_job_flow(svc, monkeypatch):
    from clipper import mcp_server as ms
    monkeypatch.setattr(ms, "svc", lambda: svc)
    asli = svc.transcriber
    svc.transcriber = lambda *a, **k: (time.sleep(1.0), asli(*a, **k))[1]

    async def alur():
        r = await ms.fetch_source(str(svc._video), tunggu_s=0)
        assert r["status"] == "berjalan" and "petunjuk" in r
        r2 = await ms.job_status(r["job_id"], tunggu_s=10)
        assert r2["status"] == "selesai" and r2["hasil"]["source_id"].startswith("f-")
        sid = r2["hasil"]["source_id"]
        r3 = await ms.render_clips(sid, "uji", [ms.Pilihan(start=6, end=15, hook_title="Hook")],
                                   reframe=False, tunggu_s=10)
        assert r3["status"] == "selesai" and r3["hasil"]["klip"][0]["hook"] == "Hook"
        r4 = await ms.render_clips(sid, "salah slug", [ms.Pilihan(start=6, end=15)], tunggu_s=10)
        assert r4["status"] == "gagal" and "slug" in r4["galat"]
        assert {j["job_id"] for j in ms.list_jobs()} >= {r["job_id"], r4["job_id"]}

    anyio.run(alur)


def test_face_detection_failure_is_reported_not_silent(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    svc.face_detector = lambda *a: (_ for _ in ()).throw(AttributeError("no solutions"))
    m = jobs.JobManager()
    job = m.mulai("x", lambda on_progress: svc._detektor_wajah(sid)(svc._video, 1920, 1080, 5))
    _tunggu(job)
    assert job.status == "gagal"
    assert any("reframe gagal" in p and "blur-pad" in p for p in job.progres)


def test_missing_face_model_gives_clear_error(monkeypatch, tmp_path):
    from clipper import reframe
    monkeypatch.setenv("CLIPPER_FACE_MODEL", str(tmp_path / "tidak-ada.tflite"))
    with pytest.raises(FileNotFoundError, match="CLIPPER_FACE_MODEL"):
        reframe._model_wajah()


def test_face_cache_invalidated_when_detector_changes(svc, monkeypatch):
    from clipper import reframe
    sid = svc.fetch_source(str(svc._video))["source_id"]
    panggil = []
    monkeypatch.setattr(reframe, "_mediapipe_detector",
                        lambda v, w, h, f, on_sample=None: panggil.append(1) or [[]])
    svc._detektor_wajah(sid)(svc._video, 1920, 1080, 5)
    svc._detektor_wajah(sid)(svc._video, 1920, 1080, 5)
    assert len(panggil) == 1                                   # cache dipakai
    monkeypatch.setattr(reframe, "PETAK", ((0.0, 1.0),))       # detektor berubah
    svc._detektor_wajah(sid)(svc._video, 1920, 1080, 5)
    assert len(panggil) == 2                                   # deteksi ulang
