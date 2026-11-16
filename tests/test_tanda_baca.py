import sys
import types

from clipper import pipeline, select
from clipper.brain.base import Proposal
from clipper.transcript import Segment

# transkrip Whisper bahasa Indonesia tanpa tanda baca (pola nyata podcast FTM)
POLOS = [Segment(i * 5.0, i * 5.0 + 5.0, f"frasa nomor {i} tentang broker dan rebate")
         for i in range(40)]
BERTANDA = [Segment(0, 5, "Halo semua."), Segment(5, 10, "Ini bagian satu"),
            Segment(10, 15, "yang masih lanjut."), Segment(15, 20, "Kalimat baru dimulai.")]


def test_unpunctuated_transcript_yields_many_windows_not_one():
    jendela = select.build_windows(POLOS, 15, 60)
    assert len(jendela) > 3                         # dulu: 1 jendela untuk seluruh video
    assert jendela[1].start > 0


def test_snap_on_unpunctuated_keeps_requested_position():
    w = select.snap_to_windows([Proposal(52.0, 98.0, "hook", "", 1.0)], POLOS, 15, 60)
    assert w and 45 <= w[0].start <= 52             # dulu: tertarik ke detik 0
    assert w[0].end >= 98 - 5


def test_punctuated_transcript_behaviour_unchanged():
    assert select.penanda_akhir(BERTANDA) == [True, False, True, True]
    starts = [w.start for w in select.build_windows(BERTANDA, 4, 11)]
    assert 10 not in starts                         # tidak mulai di tengah kalimat


def test_hook_without_punctuation_stays_short():
    w = select.build_windows(POLOS, 15, 60)[0]
    h = select.hook(w)
    assert len(h.split()) < 15 and h.startswith("Frasa nomor 0")


def _fake_whisper(monkeypatch, bahasa_terdeteksi):
    panggilan = {}

    class Model:
        feature_extractor = types.SimpleNamespace(sampling_rate=16000)

        def __init__(self, *a, **k):
            pass

        def detect_language(self, audio, **k):
            return bahasa_terdeteksi, 0.99, []

        def transcribe(self, audio, **k):
            panggilan.update(k)
            return [], types.SimpleNamespace(language=k.get("language"), duration=0)

    stub = types.ModuleType("faster_whisper")
    stub.WhisperModel = Model
    stub.decode_audio = lambda path, sampling_rate=16000: "audio-terdekode"
    monkeypatch.setitem(sys.modules, "faster_whisper", stub)
    return panggilan


def test_indonesian_audio_gets_punctuation_prompt(monkeypatch, tmp_path):
    p = _fake_whisper(monkeypatch, "id")
    pipeline.transcribe(tmp_path / "v.mp4", None)
    assert p["language"] == "id" and "?" in p["initial_prompt"]


def test_other_language_gets_no_indonesian_prompt(monkeypatch, tmp_path):
    p = _fake_whisper(monkeypatch, "en")
    pipeline.transcribe(tmp_path / "v.mp4", None)
    assert p["language"] == "en" and p["initial_prompt"] is None
