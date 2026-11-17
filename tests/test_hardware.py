import sys
import types

import pytest

from clipper import hardware, pipeline, render
from clipper.config import Settings, load_settings
from clipper.hardware import Hardware
from tests.test_service import SEGMEN
from tests.test_settings import svc  # noqa: F401  (fixture)

H = Hardware


@pytest.mark.parametrize("hw, harap", [
    (H(cpu=6, ram_gb=29.3), ("small", "veryfast", 1080, 5.0)),      # devodo
    (H(cpu=4, ram_gb=8), ("base", "superfast", 1080, 3.0)),
    (H(cpu=2, ram_gb=3.5), ("tiny", "ultrafast", 720, 2.0)),
    (H(cpu=8, ram_gb=None), ("small", "veryfast", 1080, 5.0)),     # RAM tak diketahui = 8 GB
    (H(cpu=4, ram_gb=16, gpu="RTX 3060", vram_gb=12, cuda=True, nvenc=True),
     ("large-v3", "veryfast", 1080, 3.0)),
    (H(cpu=4, ram_gb=16, gpu="GTX 1660", vram_gb=6, cuda=True), ("medium", "superfast", 1080, 3.0)),
])
def test_recommendation_per_machine(hw, harap):
    r = hardware.rekomendasi(hw)
    assert (r["whisper_model"], r["preset"], r["tinggi_unduh"], r["reframe_fps"]) == harap


def test_standard_machine_keeps_old_defaults():
    s = Settings()
    r = hardware.rekomendasi(H(cpu=6, ram_gb=16))
    assert all(getattr(s, k) == v for k, v in r.items())


def test_effective_device():
    gpu, cpu = H(cpu=4, ram_gb=8, gpu="x", cuda=True, nvenc=True), H(cpu=4, ram_gb=8)
    assert hardware.whisper_efektif("otomatis", gpu) == "cuda"
    assert hardware.whisper_efektif("otomatis", cpu) == "cpu"
    assert hardware.whisper_efektif("cpu", gpu) == "cpu"
    assert hardware.encoder_efektif("otomatis", gpu) == "nvenc"
    assert hardware.encoder_efektif("otomatis", cpu) == "cpu"


def test_nvenc_needs_encoder_and_working_test_encode():
    def palsu(hasil_uji):
        def jalankan(cmd, timeout=20):
            return (0, "V....D h264_nvenc  NVIDIA") if "-encoders" in cmd else (hasil_uji, "")
        return jalankan
    assert hardware._nvenc(palsu(0)) is True
    assert hardware._nvenc(palsu(1)) is False             # driver tidak cocok
    assert hardware._nvenc(lambda cmd, timeout=20: (0, "libx264")) is False


def test_nvidia_smi_parse(monkeypatch):
    monkeypatch.setattr(hardware.shutil, "which", lambda n: "/usr/bin/nvidia-smi")
    assert hardware._gpu_nvidia(lambda c, t=10: (0, "NVIDIA GeForce RTX 3060, 12288\n")) == \
        ("NVIDIA GeForce RTX 3060", 12.0)
    assert hardware._gpu_nvidia(lambda c, t=10: (9, "")) == (None, None)
    monkeypatch.setattr(hardware.shutil, "which", lambda n: None)
    assert hardware._gpu_nvidia(lambda c, t=10: (0, "x, 1")) == (None, None)


def test_real_detection_is_safe():
    hw = hardware.deteksi()           # mesin penguji apa adanya: tidak boleh melempar
    assert hw.cpu >= 1 and (hw.ram_gb is None or hw.ram_gb > 0)


def test_nvenc_args():
    cmd = " ".join(render.cut_cmd("s.mp4", 0, 5, "o.mp4", crf=21, preset="veryfast", encoder="nvenc"))
    assert "-c:v h264_nvenc -preset p3" in cmd and "-cq 21" in cmd and "libx264" not in cmd
    cmd = " ".join(render.burn_cmd("a.mp4", "a.srt", "b.mp4", crf=21, preset="slow", encoder="nvenc"))
    assert "h264_nvenc -preset p7" in cmd
    assert "libx264" in " ".join(render.burn_cmd("a.mp4", "a.srt", "b.mp4"))


def test_recommendation_is_lowest_layer(tmp_path):
    rek = {"whisper_model": "tiny", "preset": "ultrafast"}
    js = tmp_path / "s.json"
    js.write_text('{"preset": "slow"}')
    s = load_settings({}, tmp_path / "none.toml", js, rekomendasi=rek)
    assert (s.whisper_model, s.preset) == ("tiny", "slow")         # pengguna menang


def test_service_uses_machine_recommendation(svc):
    svc._hardware = H(cpu=2, ram_gb=3)
    svc._settings_kunci = None
    assert svc.settings.whisper_model == "tiny"
    d = svc.get_settings()
    assert d["perangkat"]["hardware"]["cpu"] == 2
    assert "whisper_model" in d["perangkat"]["otomatis"]
    d = svc.save_settings({"whisper_model": "small"})
    assert d["nilai"]["whisper_model"] == "small" and "whisper_model" not in d["perangkat"]["otomatis"]
    d = svc.save_settings({"whisper_model": None})                  # kembali ke rekomendasi
    assert d["nilai"]["whisper_model"] == "tiny"


def test_service_gpu_paths(svc):
    svc._hardware = H(cpu=8, ram_gb=32, gpu="RTX", vram_gb=8, cuda=True, nvenc=True)
    svc._settings_kunci = None
    diminta = {}
    svc.transcriber = lambda v, vtt, **k: (diminta.update(k), list(SEGMEN))[1]
    sid = svc.fetch_source(str(svc._video))["source_id"]
    assert diminta["perangkat"] == "cuda" and diminta["whisper_model"] == "medium"
    svc.render_clips(sid, "uji", [{"start": 3, "end": 15}])
    assert all("h264_nvenc" in c for c in svc._cmds[-2:])
    svc.save_settings({"encoder": "cpu"})
    svc.render_clips(sid, "uji", [{"start": 3, "end": 15}])
    assert all("libx264" in c for c in svc._cmds[-2:])


def test_nvenc_failure_falls_back_to_cpu(svc):
    svc._hardware = H(cpu=8, ram_gb=32, nvenc=True)
    svc._settings_kunci = None
    sid = svc.fetch_source(str(svc._video))["source_id"]
    asli = svc.run

    def run(cmd, cwd=None):
        if "h264_nvenc" in cmd:
            raise RuntimeError("gagal: ffmpeg ... No NVENC capable devices found")
        return asli(cmd, cwd=cwd)
    svc.run = run
    pesan = []
    r = svc.render_clips(sid, "uji", [{"start": 3, "end": 15}],
                         on_progress=lambda t, i: pesan.append((t, i)))
    assert len(r["klip"]) == 1
    assert any(t == "peringatan" and "encoder GPU gagal" in i.get("pesan", "") for t, i in pesan)
    assert all("libx264" in c for c in svc._cmds[-2:])


def test_whisper_gpu_failure_falls_back_to_cpu(monkeypatch):
    dibuat = []

    class Model:
        def __init__(self, nama, device, compute_type):
            dibuat.append((device, compute_type))

        def detect_language(self, audio):
            if dibuat[-1][0] == "cuda":
                raise RuntimeError("Library libcublas.so.12 is not found")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Model))
    pesan = []
    m = pipeline.muat_whisper("small", "cuda", lambda t, i: pesan.append(i["pesan"]))
    assert dibuat == [("cuda", "float16"), ("cpu", "int8")]
    assert m.clipper_perangkat == "cpu" and "libcublas" in pesan[0]
    dibuat.clear()
    assert pipeline.muat_whisper("small", "cpu").clipper_perangkat == "cpu"
    assert dibuat == [("cpu", "int8")]
