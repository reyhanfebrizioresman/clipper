import json
from pathlib import Path

import pytest

from clipper.config import Settings
from clipper.service import ClipperError, ClipperService, Selection
from clipper.transcript import Segment

BRIEF = {"slug": "uji", "nama": "Uji", "cpm_rp": 1000, "durasi_min_s": 4, "durasi_maks_s": 60,
         "platform": ["TikTok", "Instagram"], "hashtag": ["#Wajib", "#Dua"],
         "keywords": ["rebate"]}

SEGMEN = [Segment(0, 3, "Halo semua."), Segment(3, 6, "Hari ini kita bahas rebate broker."),
          Segment(6, 9, "Ini bagian penting"), Segment(9, 12, "yang jarang dibahas orang."),
          Segment(12, 15, "Rebate itu sumber utama IB."), Segment(15, 18, "Terima kasih.")]


def _fake_run(cmd, cwd=None):
    # ffmpeg palsu: buat file keluaran (argumen terakhir) supaya alur file nyata teruji
    out = Path(cmd[-1])
    if cwd and not out.is_absolute():
        out = Path(cwd) / out
    if out.suffix == ".mp4":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"x")


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


def test_fetch_source_local_file_caches(svc):
    calls = []
    asli = svc.transcriber
    svc.transcriber = lambda *a, **k: calls.append(1) or asli(*a, **k)
    m1 = svc.fetch_source(str(svc._video))
    m2 = svc.fetch_source(str(svc._video))
    assert m1["source_id"].startswith("f-") and m1["jumlah_segmen"] == len(SEGMEN)
    assert m1["transkrip_dari"] == "whisper" and m2["cache"] is True
    assert len(calls) == 1                       # kedua kali tidak transkrip ulang


def test_fetch_source_rejects_garbage(svc):
    with pytest.raises(ClipperError):
        svc.fetch_source("bukan-url-atau-file")


def test_transcript_paging_and_windows(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    t = svc.get_transcript(sid, limit=4)
    assert len(t["baris"]) == 4 and t["berikutnya"] == 4
    assert svc.get_transcript(sid, mulai_s=10)["total_segmen_dalam_rentang"] == 3
    k = svc.list_candidate_windows(sid, "uji", urut="skor")
    assert k["total"] >= 1 and k["kandidat"][0]["skor_kata_kunci"] >= 1


def test_render_clips_snaps_to_sentence_and_writes_caption(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    # mulai di tengah kalimat (7 dtk) -> harus mundur ke awal kalimat (6 dtk)
    r = svc.render_clips(sid, "uji", [Selection(7, 14, "IB kaya dari rebate"),
                                       {"start": 7, "end": 14},          # duplikat setelah snap
                                       {"start": 0, "end": 1}])          # terlalu pendek? snap memanjangkan
    starts = [k["mulai"] for k in r["klip"]]
    assert 6.0 in starts
    k = next(x for x in r["klip"] if x["mulai"] == 6.0)
    assert k["hook"] == "IB kaya dari rebate"
    assert "#Wajib" in k["caption"] and k["caption"].startswith("IB kaya dari rebate")
    assert any("sama dengan" in d["alasan"] for d in r["dilewati"])
    # render kedua melanjutkan penomoran, tidak menimpa
    r2 = svc.render_clips(sid, "uji", [Selection(12, 18, "lanjutan")])
    semua = {c["file"] for c in svc.list_clips("uji")}
    assert r2["klip"][0]["file"] not in {k["file"] for k in r["klip"]}
    assert len(semua) == len(r["klip"]) + 1
    detail = svc.get_clip("uji", sid, r2["klip"][0]["file"])
    tiktok = next(v for v in detail["varian_platform"] if v["platform"] == "tiktok")
    assert "\n" not in tiktok["caption"] and detail["srt"]


def test_auto_clips_keyword(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    r = svc.auto_clips(sid, "uji", jumlah=1, ai="keyword")
    assert len(r["klip"]) == 1 and r["pemilih"] == "keyword"


def test_path_traversal_rejected(svc):
    with pytest.raises(ClipperError):
        svc.get_campaign_brief("../etc/passwd")
    with pytest.raises(ClipperError):
        svc.get_clip("uji", "f-000000000000", "../../x.mp4")


def test_save_campaign_brief_validates(svc):
    with pytest.raises(ClipperError):
        svc.save_campaign_brief({"slug": "baru", "nama": "x"})
    with pytest.raises(ClipperError):
        svc.save_campaign_brief(BRIEF)               # sudah ada, tanpa timpa
    out = svc.save_campaign_brief({**BRIEF, "slug": "baru"})
    assert Path(out["file"]).is_file()
    assert "baru" in [c["slug"] for c in svc.list_campaigns()]


# --- regresi dari evaluasi ulang -------------------------------------------------

def test_get_clip_variants_use_full_hook_not_truncated(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    panjang = "Hook yang sangat panjang " * 6          # > 80 karakter
    r = svc.render_clips(sid, "uji", [Selection(6, 15, panjang.strip())])
    d = svc.get_clip("uji", sid, r["klip"][0]["file"])
    ig = next(v for v in d["varian_platform"] if v["platform"] == "instagram")
    assert ig["caption"] == d["caption"]                # varian == file .txt persis
    assert d["hook"] == panjang.strip()


def test_auto_clips_reports_real_chooser_and_keeps_lewati(svc):
    from clipper import pipeline
    sid = svc.fetch_source(str(svc._video))["source_id"]
    c = svc.load_campaign("uji")
    teratas = pipeline.keyword_chooser(svc.segments(sid), c, c.durasi_min_s, 60, 1, 0)[0]
    svc.render_clips(sid, "uji", [Selection(15, 18)])  # sudah ada klip: nomor file != 0
    r = svc.auto_clips(sid, "uji", jumlah=1, ai="gemini")   # tanpa API key -> gagal
    assert r["pemilih"] == "keyword" and "gagal" in r["catatan"]
    assert r["klip"][0]["mulai"] == round(teratas.start, 1)  # lewati=0 tetap kandidat #1


def test_negative_offset_is_clamped(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    assert svc.get_transcript(sid, offset=-3, limit=2)["baris"][0].startswith("0 |")
    assert svc.list_candidate_windows(sid, "uji", offset=-5)["offset"] == 0


def test_yt_dlp_never_downloads_playlists():
    from clipper import source
    assert "--no-playlist" in source.download_cmd("https://x/watch?v=a&list=b", "/tmp")
    assert "--no-playlist" in source.subtitle_cmd("https://x/watch?v=a&list=b", "/tmp")


def test_http_mode_refuses_non_loopback_host():
    from clipper import mcp_server
    with pytest.raises(SystemExit):
        mcp_server.main(["--http", "--host", "0.0.0.0"])


def test_candidate_windows_flag_sentence_end(svc):
    sid = svc.fetch_source(str(svc._video))["source_id"]
    k = svc.list_candidate_windows(sid, "uji", min_s=4, max_s=8)["kandidat"]
    assert all("akhir_kalimat" in x for x in k)
    # 6-12 dtk: "Ini bagian penting yang jarang dibahas orang." -> akhir kalimat
    assert any(x["akhir_kalimat"] for x in k)
