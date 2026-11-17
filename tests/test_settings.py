import json
import os
import stat

import pytest
from fastapi.testclient import TestClient

from clipper import export, render
from clipper.campaign import Campaign
from clipper.config import Settings, SettingsError, load_settings, simpan_json, validasi
from clipper.service import ClipperError, ClipperService
from clipper.styles import STYLES, dari_field, semua_gaya
from clipper.web import create_app
from tests.test_service import BRIEF, SEGMEN, _fake_run

GAYA = {"font": "DejaVu Sans", "ukuran": 12, "warna": "#ffcc00", "warna_outline": "#102030",
        "outline": 1, "bayangan": 0, "posisi": 80, "tebal": False, "kotak": True}


def test_layers_toml_then_json_then_env(tmp_path):
    toml = tmp_path / "c.toml"
    toml.write_text('crf = 20\nsubtitle_style = "bold"\n')
    js = tmp_path / "s.json"
    js.write_text(json.dumps({"crf": 18, "preset": "slow"}))
    s = load_settings({"CLIPPER_SUBTITLE_STYLE": "karaoke"}, toml, js)
    assert (s.crf, s.preset, s.subtitle_style) == (18, "slow", "karaoke")


def test_invalid_value_in_file_is_ignored_not_fatal(tmp_path):
    js = tmp_path / "s.json"
    js.write_text(json.dumps({"crf": 99, "preset": "turbo", "audio_kbps": 192}))
    s = load_settings({}, tmp_path / "none.toml", js)
    assert (s.crf, s.preset, s.audio_kbps) == (23, "veryfast", 192)


@pytest.mark.parametrize("ubah", [{"crf": 40}, {"preset": "turbo"}, {"tidak_ada": 1},
                                  {"reframe": "ya"}, {"karakter_per_baris": 20.5},
                                  {"gaya_kustom": {"lato": GAYA}},
                                  {"gaya_kustom": {"Gaya Saya": GAYA}},
                                  {"gaya_kustom": {"x": {**GAYA, "warna": "kuning"}}},
                                  {"gaya_kustom": {"x": {**GAYA, "font": "A'; rm -rf"}}},
                                  {"platform": {"tiktok": {"maks_durasi": 1}}}])
def test_validation_rejects(ubah):
    with pytest.raises(SettingsError):
        validasi(ubah)


def test_save_is_private_and_null_resets(tmp_path):
    p = tmp_path / "s.json"
    simpan_json(p, {"crf": 20, "gemini_api_key": "AIzaRahasia1234"})
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600
    simpan_json(p, {"crf": None, "gemini_api_key": ""})
    assert json.loads(p.read_text()) == {}


def test_default_style_must_exist(tmp_path):
    p = tmp_path / "s.json"
    simpan_json(p, {"gaya_kustom": {"kuning": GAYA}, "subtitle_style": "kuning"},
                gaya_dikenal=set(STYLES))
    with pytest.raises(SettingsError):     # gaya dihapus padahal masih jadi bawaan
        simpan_json(p, {"gaya_kustom": {}}, gaya_dikenal=set(STYLES))


def test_custom_style_force_style():
    fs = dari_field("x", validasi({"gaya_kustom": {"x": GAYA}})["gaya_kustom"]["x"]).force_style
    assert "FontName=DejaVu Sans" in fs and "PrimaryColour=&H00CCFF&" in fs
    assert "OutlineColour=&H302010&" in fs and "BorderStyle=3" in fs and "MarginV=80" in fs
    assert set(semua_gaya({"x": GAYA})) == set(STYLES) | {"x"}


def test_encode_params_reach_ffmpeg():
    cmd = " ".join(render.cut_cmd("s.mp4", 0, 5, "o.mp4", crf=19, preset="slow", audio_kbps=128))
    assert "-crf 19" in cmd and "-preset slow" in cmd and "-b:a 128k" in cmd


def test_platform_override():
    c = Campaign("x", "X", 1, 5, 60, ["TikTok"], ["#a"])
    v = export.platform_variants(c, "Hook", aturan={"tiktok": {"maks_durasi": 90, "catatan": "baru"}})
    assert (v[0].maks_durasi, v[0].catatan) == (90, "baru")


@pytest.fixture
def svc(tmp_path):
    camps = tmp_path / "campaigns"
    camps.mkdir()
    (camps / "uji.json").write_text(json.dumps(BRIEF))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"v")
    s = ClipperService(camps, tmp_path / "work", run=_fake_run, toml_path=tmp_path / "none.toml",
                       transcriber=lambda v, vtt, **k: list(SEGMEN))
    s._video, s._cmds = video, []
    asli = s.run
    s.run = lambda cmd, cwd=None: (s._cmds.append(cmd), asli(cmd, cwd=cwd))
    return s


def test_service_settings_apply_without_restart(svc):
    assert svc.settings.crf == 23
    svc.save_settings({"crf": 19, "reframe": False, "gaya_kustom": {"kuning": GAYA},
                       "subtitle_style": "kuning", "maks_durasi": 10})
    assert svc.settings.crf == 19                       # dibaca ulang, tanpa restart
    sid = svc.fetch_source(str(svc._video))["source_id"]
    assert svc.list_candidate_windows(sid, "uji")["durasi_s"][1] == 10
    svc.render_clips(sid, "uji", [{"start": 3, "end": 9, "hook_title": "Hook"}])
    semua = [" ".join(c) for c in svc._cmds]
    assert any("-crf 19" in c for c in semua)
    assert any("PrimaryColour=&H00CCFF&" in c for c in semua)   # gaya kustom terpakai


def test_get_settings_masks_api_key(svc):
    svc.save_settings({"gemini_api_key": "AIzaSyRahasiaSekali9876"})
    d = svc.get_settings()
    assert d["nilai"]["gemini_api_key"] == {"ada": True, "akhir": "9876"}
    assert "Rahasia" not in json.dumps(d)
    assert svc.settings.gemini_api_key == "AIzaSyRahasiaSekali9876"


def test_save_settings_error_is_clipper_error(svc):
    with pytest.raises(ClipperError):
        svc.save_settings({"crf": 99})


def test_web_settings_endpoints(svc):
    c = TestClient(create_app(svc), base_url="http://127.0.0.1:8780")
    assert c.put("/api/settings", json={"crf": 20}).status_code == 403      # tanpa X-Clipper
    r = c.put("/api/settings", headers={"X-Clipper": "1"}, json={"crf": 20, "preset": "fast"})
    assert r.status_code == 200 and r.json()["nilai"]["crf"] == 20
    assert c.put("/api/settings", headers={"X-Clipper": "1"}, json={"crf": 5}).status_code == 400
    d = c.get("/api/settings").json()
    assert d["skema"]["crf"]["maks"] == 35 and "crf" in d["tersimpan"]
    assert c.get("/api/info").json()["maks_durasi_bawaan"] == 60
