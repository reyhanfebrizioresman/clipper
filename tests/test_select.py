import pytest
from clipper import select
from clipper.transcript import Segment

def segmen(n: int, panjang: float = 5.0) -> list[Segment]:
    return [Segment(i * panjang, (i + 1) * panjang, f"kalimat {i}.") for i in range(n)]

def test_window_respects_min_and_max_duration():
    jendela = select.build_windows(segmen(40), min_s=15, max_s=60)
    assert jendela, "harus ada kandidat"
    for w in jendela:
        durasi = w.end - w.start
        assert 15 <= durasi <= 60, f"durasi {durasi} di luar batas campaign"

def test_window_starts_and_ends_on_segment_boundary():
    segs = segmen(20)
    batas = {s.start for s in segs} | {s.end for s in segs}
    for w in select.build_windows(segs, min_s=15, max_s=60):
        assert w.start in batas and w.end in batas   # tidak memotong di tengah kalimat

def test_window_keeps_its_own_text():
    jendela = select.build_windows(segmen(10), min_s=15, max_s=30)
    w = jendela[0]
    assert "kalimat 0." in w.text
    assert w.text.count("kalimat") >= 3            # 15 detik = minimal 3 segmen 5 detik

def test_short_transcript_yields_nothing():
    # transkrip 10 detik tidak cukup untuk klip minimal 15 detik
    assert select.build_windows(segmen(2), min_s=15, max_s=60) == []

def test_windows_do_not_overlap():
    jendela = select.build_windows(segmen(60), min_s=15, max_s=45)
    for a, b in zip(jendela, jendela[1:]):
        assert b.start >= a.end, "klip tidak boleh tumpang tindih"

def test_rank_puts_keyword_hits_first():
    segs = [Segment(0, 20, "basa basi pembuka yang biasa saja."),
            Segment(20, 40, "ini rahasia komisi rebate yang disembunyikan broker.")]
    jendela = select.build_windows(segs, min_s=15, max_s=25)
    peringkat = select.rank(jendela, keywords=["rebate", "broker"])
    assert "rebate" in peringkat[0].text
