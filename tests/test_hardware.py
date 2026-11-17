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
    (H(cpu=4, ram_gb=16, gpu="RTX 3060", vram_gb=12, cuda=True, encoders=("nvenc",)),
     ("large-v3", "veryfast", 1080, 3.0)),
    (H(cpu=8, ram_gb=16, gpu="Apple Silicon", gpu_vendor="apple", mlx=True,
       encoders=("videotoolbox",)), ("medium", "veryfast", 1080, 5.0)),
    (H(cpu=4, ram_gb=8, gpu="Radeon", gpu_vendor="amd", encoders=("vaapi",)),
     ("base", "veryfast", 1080, 3.0)),
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
    gpu, cpu = H(cpu=4, ram_gb=8, gpu="x", cuda=True, encoders=("nvenc",)), H(cpu=4, ram_gb=8)
    assert hardware.whisper_efektif("otomatis", gpu) == "cuda"
    assert hardware.whisper_efektif("otomatis", cpu) == "cpu"
    assert hardware.whisper_efektif("cpu", gpu) == "cpu"
    assert hardware.encoder_efektif("otomatis", gpu) == "nvenc"
    assert hardware.encoder_efektif("otomatis", cpu) == "cpu"
    mac = H(cpu=8, ram_gb=16, gpu_vendor="apple", mlx=True, encoders=("videotoolbox",))
    assert (hardware.whisper_efektif("otomatis", mac), hardware.encoder_efektif("otomatis", mac)) \
        == ("mlx", "videotoolbox")
    amd = H(cpu=8, ram_gb=16, gpu_vendor="amd", encoders=("vaapi",), vaapi_device="/dev/dri/renderD129")
    assert hardware.encoder_efektif("otomatis", amd) == "vaapi:/dev/dri/renderD129"
    assert hardware.ringkas(amd, Settings())["encoder"] == "vaapi"


def _ffmpeg_palsu(tersedia: str, lolos: set[str]):
    """ffmpeg palsu: daftar encoder = `tersedia`; uji encode berhasil hanya untuk `lolos`."""
    dijalankan = []

    def jalankan(cmd, timeout=20):
        dijalankan.append(cmd)
        if "-encoders" in cmd:
            return 0, tersedia
        codec = cmd[cmd.index("-c:v") + 1]
        return (0 if codec in lolos else 1), ""
    return jalankan, dijalankan


def test_gpu_encoder_needs_listing_and_working_test_encode():
    j, _ = _ffmpeg_palsu("h264_nvenc h264_amf h264_vaapi libx264", {"h264_nvenc", "h264_vaapi"})
    assert hardware._encoder_gpu(j, "/dev/dri/renderD128") == ("nvenc", "vaapi")
    j, _ = _ffmpeg_palsu("h264_nvenc", set())                 # driver tidak cocok
    assert hardware._encoder_gpu(j) == ()
    j, _ = _ffmpeg_palsu("h264_vaapi", {"h264_vaapi"})         # VAAPI tanpa render node
    assert hardware._encoder_gpu(j, None) == ()
    j, cmds = _ffmpeg_palsu("h264_videotoolbox", {"h264_videotoolbox"})
    assert hardware._encoder_gpu(j) == ("videotoolbox",)
    assert "-q:v" in cmds[-1]                                  # uji = argumen render sungguhan


def test_linux_gpu_from_sysfs(tmp_path):
    def node(nama, vendor, **berkas):
        d = tmp_path / nama / "device"
        d.mkdir(parents=True)
        (d / "vendor").write_text(vendor + "\n")
        for k, v in berkas.items():
            (d / k).write_text(v)
    node("renderD128", "0x8086")
    node("renderD129", "0x1002", mem_info_vram_total=str(8 * 1024**3), product_name="Radeon RX 7600")
    node("card0", "0x1002")                                    # bukan render node
    g = hardware._gpu_linux(tmp_path)
    assert [(x["vendor"], x["node"]) for x in g] == [("intel", "/dev/dri/renderD128"),
                                                     ("amd", "/dev/dri/renderD129")]
    assert g[1]["nama"] == "Radeon RX 7600" and g[1]["vram_gb"] == 8.0
    assert g[0]["nama"] == "GPU Intel" and g[0]["vram_gb"] is None


def test_windows_prefers_discrete_gpu():
    out = "Intel(R) UHD Graphics 630\r\nAMD Radeon RX 6700 XT\r\n"
    assert hardware._gpu_windows(lambda c, t=15: (0, out)) == "AMD Radeon RX 6700 XT"
    assert hardware._vendor_dari_nama("AMD Radeon RX 6700 XT") == "amd"


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


def test_apple_and_amd_encoder_args():
    vt = " ".join(render.cut_cmd("s.mp4", 0, 5, "o.mp4", crf=23, encoder="videotoolbox"))
    assert "-c:v h264_videotoolbox -q:v 60" in vt
    amf = " ".join(render.burn_cmd("a.mp4", "a.srt", "b.mp4", crf=22, preset="ultrafast", encoder="amf"))
    assert "-c:v h264_amf -quality speed -rc cqp -qp_i 22 -qp_p 22" in amf


def test_vaapi_uploads_frames_to_gpu():
    cmd = render.cut_cmd("s.mp4", 0, 5, "o.mp4", crf=24, encoder="vaapi:/dev/dri/renderD129")
    assert cmd[2:4] == ["-vaapi_device", "/dev/dri/renderD129"]       # sebelum -i
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.endswith(";[v]format=nv12,hwupload[vgpu]") and cmd[cmd.index("-map") + 1] == "[vgpu]"
    assert "-pix_fmt" not in cmd and "h264_vaapi" in cmd and "24" in cmd
    burn = render.burn_cmd("a.mp4", "a.srt", "b.mp4", encoder="vaapi")
    assert burn[burn.index("-vf") + 1].endswith(",format=nv12,hwupload")
    assert "/dev/dri/renderD128" in burn


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
    svc._hardware = H(cpu=8, ram_gb=32, gpu="RTX", vram_gb=8, cuda=True, encoders=("nvenc",))
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


def test_gpu_encoder_failure_falls_back_to_cpu(svc):
    svc._hardware = H(cpu=8, ram_gb=32, encoders=("vaapi",), vaapi_device="/dev/dri/renderD128")
    svc._settings_kunci = None
    sid = svc.fetch_source(str(svc._video))["source_id"]
    asli = svc.run

    def run(cmd, cwd=None):
        if "h264_vaapi" in cmd:
            raise RuntimeError("gagal: ffmpeg ... Failed to initialise VAAPI connection")
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


def test_whisper_apple_mlx(monkeypatch):
    import numpy as np
    dipanggil = {}

    def transcribe(audio, **k):
        dipanggil.update(k)
        return {"language": "id", "segments": [{"start": 0.0, "end": 2.5, "text": " Halo semua."}]}
    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=transcribe))
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=None))
    m = pipeline.muat_whisper("small", "mlx")
    assert m.clipper_perangkat == "mlx"
    seg, info = m.transcribe(np.zeros(32000, dtype=np.float32), language="id",
                             initial_prompt="Halo.")
    assert [(s.start, s.end, s.text) for s in seg] == [(0.0, 2.5, " Halo semua.")]
    assert info.duration == 2.0 and dipanggil["path_or_hf_repo"] == "mlx-community/whisper-small-mlx"
    assert dipanggil["initial_prompt"] == "Halo."


def test_whisper_apple_failure_falls_back_to_cpu(monkeypatch):
    import numpy as np

    def rusak(audio, **k):
        raise RuntimeError("[metal] device not found")

    class Cpu:
        def __init__(self, nama, device, compute_type):
            assert (device, compute_type) == ("cpu", "int8")

        def transcribe(self, audio, **k):
            return iter([types.SimpleNamespace(start=0, end=1, text="cpu")]), None
    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(transcribe=rusak))
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Cpu))
    pesan = []
    m = pipeline.muat_whisper("small", "mlx", lambda t, i: pesan.append(i["pesan"]))
    seg, _ = m.transcribe(np.zeros(16000, dtype=np.float32))
    assert [s.text for s in seg] == ["cpu"] and "metal" in pesan[0]


def test_mlx_missing_falls_back_at_load(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlx_whisper", None)          # impor gagal
    dibuat = []

    class Cpu:
        def __init__(self, nama, device, compute_type):
            dibuat.append(device)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Cpu))
    pesan = []
    assert pipeline.muat_whisper("small", "mlx", lambda t, i: pesan.append(i)).clipper_perangkat == "cpu"
    assert dibuat == ["cpu"] and pesan
