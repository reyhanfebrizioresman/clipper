import json
import pytest
from clipper import campaign, source

BRIEF = {
    "slug": "ftm-potrade",
    "nama": "Podcast FTM Potrade",
    "cpm_rp": 3000,
    "durasi_min_s": 15,
    "durasi_maks_s": 180,
    "platform": ["TikTok", "Instagram"],
    "hashtag": ["#FTMPodtrade", "#Fxpayout", "#TMGM", "#TradingForex", "#tradingclpo"],
    "keywords": ["rebate", "broker", "IB", "komisi"],
    "larangan": ["hook menyerang orang", "bot"],
}

def test_load_reads_brief(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps(BRIEF), encoding="utf-8")
    c = campaign.load(f)
    assert c.durasi_min_s == 15 and c.durasi_maks_s == 180
    assert "#TMGM" in c.hashtag

def test_caption_contains_every_required_hashtag(tmp_path):
    f = tmp_path / "c.json"; f.write_text(json.dumps(BRIEF), encoding="utf-8")
    c = campaign.load(f)
    cap = campaign.caption(c, hook="Mobil sport IB ternyata cuma pinjaman broker.")
    for tag in BRIEF["hashtag"]:
        assert tag in cap, f"hashtag wajib {tag} hilang — klip tidak dibayar"
    assert cap.startswith("Mobil sport")          # hook di depan biar kebaca duluan
    assert len(cap) <= 2200                       # batas caption TikTok/Instagram

def test_caption_rejects_empty_hook(tmp_path):
    f = tmp_path / "c.json"; f.write_text(json.dumps(BRIEF), encoding="utf-8")
    c = campaign.load(f)
    with pytest.raises(ValueError):
        campaign.caption(c, hook="   ")

def test_download_cmd_asks_for_subtitle_and_mp4(tmp_path):
    import sys
    cmd = source.download_cmd("https://youtu.be/abc123", tmp_path)
    joined = " ".join(cmd)
    # dipanggil sebagai modul python venv, bukan binary global:
    # di server yt-dlp hanya ada di dalam .venv, tidak di PATH
    assert cmd[:3] == [sys.executable, "-m", "yt_dlp"]
    assert "--write-auto-subs" in cmd            # hemat: pakai subtitle otomatis kalau ada
    assert "id" in joined                        # prioritaskan subtitle Indonesia
    assert "mp4" in joined
    assert str(tmp_path) in joined
