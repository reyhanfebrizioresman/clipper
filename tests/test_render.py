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
    assert "Kalimat pertama." in isi   # awal kalimat dibesarkan

def test_burn_cmd_subtitle_sized_for_phone(tmp_path):
    cmd = render.burn_cmd(tmp_path / "in.mp4", "w.srt", tmp_path / "out.mp4")
    joined = " ".join(cmd)
    skala = render.H / 288                              # libass memakai tinggi referensi 288
    size_px = int(joined.split("FontSize=")[1].split(",")[0]) * skala
    margin_px = int(joined.split("MarginV=")[1].split(",")[0]) * skala
    assert 60 <= size_px <= 120
    # menempel di bawah video, tapi ~30% layar bawah tetap bebas untuk UI TikTok
    assert 400 <= margin_px <= 800

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

@pytest.mark.integration
def test_burn_needs_cwd_at_srt_folder(tmp_path):
    """Kontrak: burn_cmd memakai NAMA file srt, jadi harus dijalankan dari foldernya.
    Menjalankannya dari cwd lain membuat ffmpeg gagal membuka subtitle."""
    import subprocess
    from clipper.transcript import Segment
    from clipper.select import Window

    src = tmp_path / "in.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30",
                    "-t", "3", str(src)], check=True, capture_output=True)
    w = Window(start=0.0, end=3.0, text="", segments=[Segment(0.0, 3.0, "halo dunia.")])
    render.write_srt(w, tmp_path / "s.srt")

    out = tmp_path / "out.mp4"
    subprocess.run(render.burn_cmd(src.resolve(), "s.srt", out.resolve()),
                   check=True, capture_output=True, cwd=tmp_path)
    assert out.exists() and out.stat().st_size > 0

    salah = subprocess.run(render.burn_cmd(src.resolve(), "s.srt", (tmp_path / "x.mp4").resolve()),
                           capture_output=True, cwd=tmp_path.parent)
    assert salah.returncode != 0, "harusnya gagal kalau dijalankan dari folder lain"

def test_write_srt_splits_long_segment_into_short_cues(tmp_path):
    """Segmen transkrip bisa panjang; di layar HP itu jadi 4 baris menutupi gambar."""
    from clipper.transcript import Segment
    from clipper.select import Window
    panjang = ("Jadi sebenarnya komisi rebate itu dibayarkan broker ke IB setiap kali "
               "klien melakukan transaksi, bukan dari hasil trading pribadi mereka.")
    w = Window(start=0.0, end=10.0, text=panjang,
               segments=[Segment(0.0, 10.0, panjang)])
    out = tmp_path / "s.srt"
    render.write_srt(w, out)
    cues = [b for b in out.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    assert len(cues) >= 2, "segmen panjang harus dipecah jadi beberapa cue"
    baris = [l for b in cues for l in b.splitlines()[2:] if l.strip()]
    assert all(len(l) <= 46 for l in baris), f"ada baris kepanjangan: {max(map(len, baris))}"
    assert "00:00:00,000" in cues[0] and "00:00:10,000" in cues[-1]

def test_write_srt_removes_speech_fillers(tmp_path):
    """Filler 'ee'/'eh' bikin subtitle sulit dibaca di layar HP. Membuangnya
    tidak mengubah makna, jadi tetap patuh aturan campaign."""
    from clipper.transcript import Segment
    from clipper.select import Window
    w = Window(start=0.0, end=8.0, text="",
               segments=[Segment(0.0, 8.0, "tapi gimana caranya ee cari posisi untuk jackpot")])
    out = tmp_path / "s.srt"
    render.write_srt(w, out)
    isi = out.read_text(encoding="utf-8")
    assert " ee " not in isi and " eh " not in isi
    assert "cari posisi untuk jackpot" in isi

def test_write_srt_capitalizes_after_sentence_end(tmp_path):
    from clipper.transcript import Segment
    from clipper.select import Window
    w = Window(start=0.0, end=8.0, text="", segments=[
        Segment(0.0, 8.0, "betul. pertama rebate terus kedua komisi.")])
    out = tmp_path / "s.srt"
    render.write_srt(w, out)
    isi = out.read_text(encoding="utf-8")
    assert "Betul." in isi
    assert "betul." not in isi

def test_write_srt_applies_term_corrections(tmp_path):
    """Transkrip otomatis salah dengar istilah teknis: 'rebit' untuk 'rebate'."""
    from clipper.transcript import Segment
    from clipper.select import Window
    w = Window(start=0.0, end=8.0, text="", segments=[
        Segment(0.0, 8.0, "pertama rebit terus kedua IBMB itu")])
    out = tmp_path / "s.srt"
    render.write_srt(w, out, koreksi={"rebit": "rebate", "IBMB": "IB"})
    isi = out.read_text(encoding="utf-8")
    assert "rebate" in isi and "rebit" not in isi
    assert "IB " in isi and "IBMB" not in isi

def test_write_srt_only_capitalizes_real_sentence_starts(tmp_path):
    """Subtitle otomatis dipecah per beberapa kata. Mengapitalkan tiap potongan
    membuat teks seperti 'Tapi gimana caranya' / 'Jackpot.' — padahal itu tengah kalimat."""
    from clipper.transcript import Segment
    from clipper.select import Window
    w = Window(start=0.0, end=12.0, text="", segments=[
        Segment(0.0, 4.0, "karena yang diajarkan sama IB"),
        Segment(4.0, 8.0, "bukan caranya survive"),
        Segment(8.0, 12.0, "tapi cari jackpot. lalu mereka rugi"),
    ])
    out = tmp_path / "s.srt"
    render.write_srt(w, out)
    isi = out.read_text(encoding="utf-8")
    assert "Karena yang diajarkan" in isi      # awal klip dibesarkan
    assert "Bukan caranya" not in isi          # ini sambungan kalimat, jangan dibesarkan
    assert "Lalu mereka rugi" in isi           # setelah titik, dibesarkan

def test_burn_cmd_uses_bold_font(tmp_path):
    cmd = render.burn_cmd(tmp_path / "in.mp4", "s.srt", tmp_path / "out.mp4")
    joined = " ".join(cmd)
    assert "FontName=" in joined and "Bold=1" in joined

def test_srt_cues_rebuilt_from_words_not_raw_segments(tmp_path):
    """Potongan VTT otomatis berantakan (mis. '. Lebih ... D'). Cue harus disusun
    ulang dari kata supaya tiap baris utuh dan tidak diawali tanda baca."""
    from clipper.transcript import Segment
    from clipper.select import Window
    w = Window(start=0.0, end=12.0, text="", segments=[
        Segment(0.0, 4.0, "lebih ke hoki-hokian"),
        Segment(4.0, 8.0, ". cap"),
        Segment(8.0, 12.0, "cip cup gitu pak."),
    ])
    out = tmp_path / "s.srt"
    render.write_srt(w, out)
    cues = [b for b in out.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    teks = [b.splitlines()[2] for b in cues]
    assert all(not t.startswith((".", ",")) for t in teks), teks
    assert all(len(t.split()) >= 2 or t.endswith((".", "!", "?")) for t in teks), teks
    assert "cap cip cup" in " ".join(teks)      # kata tidak tercerai antar cue

def test_srt_timing_stays_within_window(tmp_path):
    from clipper.transcript import Segment
    from clipper.select import Window
    w = Window(start=10.0, end=25.0, text="", segments=[
        Segment(10.0, 17.0, "satu dua tiga empat lima enam tujuh delapan."),
        Segment(17.0, 25.0, "sembilan sepuluh sebelas dua belas tiga belas."),
    ])
    out = tmp_path / "s.srt"
    render.write_srt(w, out)
    isi = out.read_text(encoding="utf-8")
    assert isi.startswith("1\n00:00:00,000")
    assert "00:00:15,000" in isi                 # berakhir di durasi window (25-10)

def test_video_sits_in_upper_area_not_center(tmp_path):
    """Kalau video ditaruh persis di tengah, subtitle mengambang jauh di bawahnya
    dan masuk zona UI TikTok. Video dinaikkan supaya subtitle menempel di bawahnya."""
    cmd = render.cut_cmd(tmp_path / "s.mp4", start=0, end=10, out_mp4=tmp_path / "o.mp4")
    joined = " ".join(cmd)
    assert "(H-h)/2" not in joined, "video masih dipusatkan vertikal"
    assert "overlay=" in joined

def test_subtitle_margin_clears_tiktok_ui_but_stays_near_video(tmp_path):
    cmd = render.burn_cmd(tmp_path / "i.mp4", "s.srt", tmp_path / "o.mp4")
    joined = " ".join(cmd)
    margin_px = int(joined.split("MarginV=")[1].split(",")[0]) * render.H / 288
    # cukup tinggi supaya tidak ketutup caption/tombol TikTok (~15% bawah = 288px),
    # tapi tidak sampai menempel ke video di area atas
    assert 400 <= margin_px <= 800, f"margin {margin_px:.0f}px"
