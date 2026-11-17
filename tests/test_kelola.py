import json

import pytest
from fastapi.testclient import TestClient

from clipper.service import ClipperError
from clipper.web import create_app
from tests.test_settings import GAYA, svc  # noqa: F401  (fixture)

H = {"X-Clipper": "1"}


def _satu_klip(svc, hook="Rebate itu sumber utama IB"):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    k = svc.render_clips(sid, "uji", [{"start": 3, "end": 15, "hook_title": hook}])["klip"][0]
    return sid, k["file"]


def test_edit_hook_rewrites_caption_without_render(svc):
    sid, f = _satu_klip(svc)
    n_cmd = len(svc._cmds)
    d = svc.update_clip("uji", sid, f, hook="Hook baru yang jujur")
    assert len(svc._cmds) == n_cmd                       # tidak ada ffmpeg
    assert d["caption"].startswith("Hook baru yang jujur\n\n#Wajib")
    assert all("Hook baru" in v["caption"] for v in d["varian_platform"])


def test_status_and_link_kept_after_rerender(svc):
    sid, f = _satu_klip(svc)
    svc.update_clip("uji", sid, f, status="diunggah", tautan="https://www.tiktok.com/@a/video/1")
    svc.save_settings({"crf": 20, "gaya_kustom": {"kuning": GAYA}})
    r = svc.rerender_clip("uji", sid, f, gaya="kuning")["klip"][0]
    assert r["file"] == f                                 # nomor sama, tidak menambah klip
    assert len(svc.list_clips("uji")) == 1
    k = svc.list_clips("uji")[0]
    assert (k["status"], k["tautan"], k["gaya"]) == ("diunggah", "https://www.tiktok.com/@a/video/1", "kuning")
    assert k["hook"] == "Rebate itu sumber utama IB"     # hook lama dipertahankan
    terakhir = " ".join(" ".join(c) for c in svc._cmds[-2:])
    assert "-crf 20" in terakhir and "PrimaryColour=&H00CCFF&" in terakhir


def test_rerender_keeps_same_window(svc):
    sid, f = _satu_klip(svc)
    awal = svc.list_clips("uji")[0]
    svc.rerender_clip("uji", sid, f)
    akhir = svc.list_clips("uji")[0]
    assert (awal["mulai"], awal["durasi"]) == (akhir["mulai"], akhir["durasi"])


@pytest.mark.parametrize("ubah", [{"status": "viral"}, {"tautan": "javascript:alert(1)"},
                                  {"hook": "   "}])
def test_update_validation(svc, ubah):
    sid, f = _satu_klip(svc)
    with pytest.raises(ClipperError):
        svc.update_clip("uji", sid, f, **ubah)


def test_delete_clip_removes_files_and_manifest(svc):
    sid, f = _satu_klip(svc)
    d = svc.work_dir / "uji" / sid / "clips"
    svc.delete_clip("uji", sid, f)
    assert not list(d.glob(f.replace(".mp4", ".*")))
    assert svc.list_clips("uji") == []
    assert json.loads((d.parent / "clips.json").read_text()) == []


def test_entry_rejects_foreign_or_bad_names(svc):
    sid, f = _satu_klip(svc)
    for nama in ("../clips.json", "lain-01.mp4", "uji-01.txt"):
        with pytest.raises(ClipperError):
            svc.delete_clip("uji", sid, nama)


def test_summary_counts(svc):
    sid, f = _satu_klip(svc)
    svc.update_clip("uji", sid, f, status="disubmit")
    r = svc.ringkasan()
    assert r["sumber"] == 1 and r["klip"] == 1
    assert r["per_status"] == {"baru": 0, "diunggah": 0, "disubmit": 1}
    assert r["per_campaign"] == {"uji": 1}


def test_web_manage_endpoints(svc):
    c = TestClient(create_app(svc), base_url="http://127.0.0.1:8780")
    sid, f = _satu_klip(svc)
    url = f"/api/clips/uji/{sid}/{f}"
    assert c.patch(url, json={"status": "diunggah"}).status_code == 403          # tanpa X-Clipper
    r = c.patch(url, headers=H, json={"hook": "Hook dari web", "status": "diunggah"})
    assert r.status_code == 200 and r.json()["status"] == "diunggah"
    assert c.patch(url, headers=H, json={"status": "x"}).status_code == 400
    j = c.post(url + "/render-ulang", headers=H, json={}).json()
    assert c.app.state.jobs.get(j["job_id"]).beres.wait(10)
    assert c.get(f"/api/jobs/{j['job_id']}").json()["status"] == "selesai"
    assert c.get("/api/ringkasan").json()["klip"] == 1
    assert c.get("/api/info").json()["versi"]
    assert c.delete(url, headers=H).status_code == 200
    assert c.get("/api/clips").json() == []


def test_mcp_manage_tools(svc, monkeypatch):
    import anyio
    from clipper import mcp_server as ms
    monkeypatch.setattr(ms, "svc", lambda: svc)
    sid, f = _satu_klip(svc)

    d = ms.update_clip("uji", sid, f, hook="Hook dari MCP", status="disubmit")
    assert d["hook"] == "Hook dari MCP" and d["status"] == "disubmit"
    assert ms.get_summary()["per_status"]["disubmit"] == 1

    async def ulang():
        r = await ms.rerender_clip("uji", sid, f, tunggu_s=10)
        assert r["status"] == "selesai" and r["hasil"]["klip"][0]["file"] == f
    anyio.run(ulang)
    assert ms.get_clip("uji", sid, f)["status"] == "disubmit"      # status bertahan

    assert ms.update_settings({"crf": 21})["nilai"]["crf"] == 21
    assert ms.get_settings()["nilai"]["crf"] == 21
    with pytest.raises(ClipperError):
        ms.update_settings({"gemini_api_key": "AIzaRahasia"})      # rahasia hanya lewat web UI
    assert "Rahasia" not in json.dumps(ms.get_settings())

    with pytest.raises(ClipperError):
        ms.delete_clip("uji", sid, f)                               # tanpa konfirmasi
    ms.delete_clip("uji", sid, f, konfirmasi=True)
    assert ms.list_clips("uji") == []
