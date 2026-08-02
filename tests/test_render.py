import pytest
from clipper import render
from clipper.transcript import Segment
from clipper.select import Window

def test_cut_cmd_is_vertical_and_seeks_before_input(tmp_path):
    cmd = render.cut_cmd(tmp_path / "src.mp4", start=12.5, end=45.0,
                         out_mp4=tmp_path / "out.mp4")
    joined = " ".join(cmd)
    assert (render.W, render.H) == (1080, 1920)
    assert f"crop={render.W}:{render.H}" in joined     # hasil akhir 9:16
    assert "boxblur" in joined                         # latar blur, bukan bilah hitam
    # -ss harus SEBELUM -i supaya seek cepat (kalau sesudah, ffmpeg dekode dari awal)
    assert cmd.index("-ss") < cmd.index("-i")
    assert "32.500" in joined                          # durasi = end - start

def test_srt_from_window_starts_at_zero(tmp_path):
    w = Window(start=100.0, end=130.0, text="",
               segments=[Segment(100.0, 105.0, "kalimat pertama."),
                         Segment(105.0, 130.0, "kalimat kedua.")])
    out = tmp_path / "w.srt"
    render.write_srt(w, out)
    isi = out.read_text(encoding="utf-8")
    # waktu digeser relatif ke awal klip, bukan waktu asli di video sumber
    assert "00:00:00,000 --> 00:00:05,000" in isi
    assert "00:01:40" not in isi
    assert "kalimat pertama." in isi

def test_burn_cmd_subtitle_sized_for_phone(tmp_path):
    cmd = render.burn_cmd(tmp_path / "in.mp4", "w.srt", tmp_path / "out.mp4")
    joined = " ".join(cmd)
    skala = render.H / 288                              # libass memakai tinggi referensi 288
    size_px = int(joined.split("FontSize=")[1].split(",")[0]) * skala
    margin_px = int(joined.split("MarginV=")[1].split(",")[0]) * skala
    assert 60 <= size_px <= 120
    assert 250 <= margin_px <= 500                      # aman dari UI TikTok yang lebih tinggi

@pytest.mark.integration
def test_cut_produces_1080x1920(tmp_path):
    import subprocess, json
    src = tmp_path / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
                    "-t", "20", str(src)], check=True, capture_output=True)
    out = tmp_path / "out.mp4"
    subprocess.run(render.cut_cmd(src, start=2.0, end=8.0, out_mp4=out),
                   check=True, capture_output=True)
    probe = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json",
                            "-show_streams", str(out)], check=True, capture_output=True)
    v = next(s for s in json.loads(probe.stdout)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
