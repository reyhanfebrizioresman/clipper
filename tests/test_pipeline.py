import sys
import types

from clipper.campaign import Campaign
from clipper.pipeline import process, transcribe
from clipper.transcript import Segment


def test_process_renders_each_chosen_window_and_writes_caption(tmp_path):
    seg = [Segment(0, 2, "IB forex itu babu broker."), Segment(2, 4, "Jangan bohong.")]
    c = Campaign(slug="x", nama="X", cpm_rp=3000, durasi_min_s=1, durasi_maks_s=60,
                 platform=["tiktok"], hashtag=["#Wajib"], keywords=["ib"])
    calls = []
    def fake_run(cmd, cwd=None): calls.append((cmd[0], cwd))
    stages = []
    res = process(c, tmp_path / "v.mp4", seg, tmp_path, jumlah=1,
                  run=fake_run, on_progress=lambda s, i: stages.append(s))
    assert len(res) == 1 and res[0].file.endswith(".mp4")
    assert any(cwd == tmp_path for _, cwd in calls)          # burn ran in clips dir
    cap = (tmp_path / res[0].file.replace(".mp4", ".txt")).read_text()
    assert "#Wajib" in cap                                   # mandatory hashtag present
    assert "render" in stages                                # progress fired


def test_transcribe_uses_whisper_when_no_vtt(monkeypatch, tmp_path):
    called = {}
    class FakeModel:
        def __init__(self, *a, **k): pass
        def transcribe(self, path, **k): called["ran"] = True; return ([], None)
    # faster_whisper tidak wajib terpasang di lingkungan uji: sediakan stub modul
    stub = types.ModuleType("faster_whisper")
    stub.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", stub)
    transcribe(tmp_path / "v.mp4", None)
    assert called["ran"]            # no subtitle -> Whisper fallback, no crash
