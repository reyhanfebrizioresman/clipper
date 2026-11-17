import json

import pytest
from fastapi.testclient import TestClient

from clipper.config import Settings
from clipper.service import ClipperService
from clipper.web import _host_lokal, create_app
from tests.test_service import BRIEF, SEGMEN, _fake_run

H = {"X-Clipper": "1"}


@pytest.fixture
def web(tmp_path):
    camps = tmp_path / "campaigns"
    camps.mkdir()
    (camps / "uji.json").write_text(json.dumps(BRIEF))
    svc = ClipperService(camps, tmp_path / "work", Settings(reframe=False), run=_fake_run,
                         transcriber=lambda v, vtt, **k: list(SEGMEN))
    app = create_app(svc)
    c = TestClient(app, base_url="http://127.0.0.1:8780")
    c.svc, c.jobs = svc, app.state.jobs
    return c


def _tunggu(c, job: dict) -> dict:
    assert c.jobs.get(job["job_id"]).beres.wait(10)
    return c.get(f"/api/jobs/{job['job_id']}").json()


def _unggah(c, isi=b"video") -> str:
    r = c.post("/api/sources/upload", headers=H, files={"file": ("rekaman saya.mp4", isi)})
    assert r.status_code == 200, r.text
    j = _tunggu(c, r.json())
    assert j["status"] == "selesai", j
    return j["hasil"]["source_id"]


def test_index_and_static_served(web):
    r = web.get("/")
    assert r.status_code == 200 and "Clipper Studio" in r.text
    assert web.get("/static/app.js").status_code == 200


def test_mutations_require_custom_header(web):
    r = web.post("/api/sources", json={"sumber": "https://example.com/v"})
    assert r.status_code == 403                       # tanpa X-Clipper: ditolak (anti-CSRF)


def test_foreign_host_header_rejected(web):
    r = web.get("/api/campaigns", headers={"Host": "evil.example:8780"})
    assert r.status_code == 403                       # anti DNS rebinding


def test_host_check_parsing():
    assert _host_lokal("127.0.0.1:8780") and _host_lokal("localhost") and _host_lokal("[::1]:8780")
    assert not _host_lokal("10.10.10.151:8780") and not _host_lokal(None)


def test_source_must_be_url_not_server_path(web):
    r = web.post("/api/sources", headers=H, json={"sumber": "/etc/passwd"})
    assert r.status_code == 400 and "URL" in r.json()["detail"]


def test_upload_rejects_non_video(web):
    r = web.post("/api/sources/upload", headers=H, files={"file": ("x.sh", b"#!/bin/sh")})
    assert r.status_code == 400


def test_upload_fetch_transcript_and_candidates(web):
    sid = _unggah(web)
    assert web.get("/api/sources").json()[0]["source_id"] == sid
    meta = web.get(f"/api/sources/{sid}").json()
    assert meta["jumlah_segmen"] == len(SEGMEN) and "video" not in meta
    seg = web.get(f"/api/sources/{sid}/transcript").json()["segmen"]
    assert seg[0] == [0, 3, "Halo semua."]
    k = web.get(f"/api/sources/{sid}/candidates", params={"campaign": "uji"}).json()
    assert k["total"] >= 1 and k["kandidat"][0]["teks"]


def test_source_video_supports_range(web):
    sid = _unggah(web, b"0123456789")
    r = web.get(f"/media/source/{sid}", headers={"Range": "bytes=2-5"})
    assert r.status_code == 206 and r.content == b"2345"


def test_render_then_library_and_clip_detail(web):
    sid = _unggah(web)
    r = web.post("/api/render", headers=H, json={
        "source_id": sid, "campaign": "uji", "reframe": False,
        "pilihan": [{"start": 3, "end": 15, "hook_title": "Rebate itu sumber utama IB"}]})
    assert r.status_code == 200, r.text
    j = _tunggu(web, r.json())
    assert j["status"] == "selesai", j
    klip = web.get("/api/clips", params={"campaign": "uji"}).json()
    assert len(klip) == 1
    d = web.get(f"/api/clips/uji/{sid}/{klip[0]['file']}").json()
    assert d["hook"] == "Rebate itu sumber utama IB"
    assert {v["platform"] for v in d["varian_platform"]} == {"tiktok", "instagram"}
    v = web.get(f"/media/clip/uji/{sid}/{klip[0]['file']}", params={"unduh": True})
    assert v.status_code == 200 and "attachment" in v.headers["content-disposition"]


def test_render_unknown_campaign_fails_fast(web):
    sid = _unggah(web)
    r = web.post("/api/render", headers=H, json={
        "source_id": sid, "campaign": "tidak-ada", "pilihan": [{"start": 0, "end": 10}]})
    assert r.status_code == 400 and "tidak ada" in r.json()["detail"]


def test_clip_path_traversal_rejected(web):
    sid = _unggah(web)
    assert web.get(f"/media/clip/uji/{sid}/..%2F..%2Fcampaigns%2Fuji.json").status_code in (400, 404)
    assert web.get("/media/source/..%2F..%2Fetc").status_code in (400, 404)


def test_campaign_create_update_validation(web):
    baru = {**BRIEF, "slug": "kedua", "nama": "Kedua"}
    assert web.post("/api/campaigns", headers=H, json=baru).status_code == 200
    assert web.post("/api/campaigns", headers=H, json=baru).status_code == 400   # sudah ada
    rusak = {**baru, "hashtag": []}
    assert web.put("/api/campaigns/kedua", headers=H, json=rusak).status_code == 400
    ubah = {**baru, "nama": "Kedua Diubah"}
    assert web.put("/api/campaigns/kedua", headers=H, json=ubah).status_code == 200
    assert web.get("/api/campaigns/kedua").json()["nama"] == "Kedua Diubah"
    assert web.put("/api/campaigns/lain", headers=H, json=ubah).status_code == 400  # slug beda


def test_cancel_unknown_job_404(web):
    assert web.post("/api/jobs/tidakada/cancel", headers=H).status_code == 404
