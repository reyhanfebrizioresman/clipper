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

def test_windows_start_at_sentence_beginning():
    """Subtitle otomatis dipotong per beberapa kata; kalau jendela mulai di
    sembarang segmen, klip dibuka dengan penggalan seperti 'gini' atau 'Iya.'"""
    segs = [Segment(0, 5, "ini kalimat pertama."),
            Segment(5, 10, "lalu"),
            Segment(10, 15, "sambungannya begini."),
            Segment(15, 20, "kalimat baru dimulai di sini."),
            Segment(20, 25, "dan"),
            Segment(25, 30, "terus berlanjut."),
            Segment(30, 35, "penutupnya."),
            Segment(35, 40, "kalimat terakhir ya.")]
    for w in select.build_windows(segs, min_s=15, max_s=25):
        awal = w.segments[0]
        idx = segs.index(awal)
        assert idx == 0 or segs[idx - 1].text.rstrip().endswith((".", "!", "?")), \
            f"klip dibuka di tengah kalimat: '{awal.text}'"

def test_hook_takes_first_full_sentence():
    w = select.Window(start=0, end=30, text="gini. Jadi rebate itu dibayar broker ke IB tiap transaksi. Nah.",
                      segments=[])
    assert select.hook(w) == "Jadi rebate itu dibayar broker ke IB tiap transaksi."

def test_hook_falls_back_to_start_when_no_long_sentence():
    w = select.Window(start=0, end=30, text="ya. oke. betul.", segments=[])
    assert select.hook(w)

def test_hook_removes_speech_fillers():
    """Transkrip otomatis penuh 'ee'/'eh'; di caption itu terlihat tidak rapi.
    (Subtitle klip tetap apa adanya — aturan campaign melarang mengubah makna.)"""
    w = select.Window(start=0, end=30, segments=[],
                      text="Nah, ee sebetulnya ee IB ini ee mereka cuma jadi perantara broker.")
    h = select.hook(w)
    assert " ee " not in h and not h.startswith("ee ")
    assert "sebetulnya" in h and "perantara broker" in h

def test_hook_applies_term_corrections():
    """Kamus koreksi harus berlaku di caption juga, bukan cuma subtitle —
    kalau tidak, caption menulis 'IBIB' sementara subtitle menulis 'IB-IB'."""
    w = select.Window(start=0, end=30, segments=[],
                      text="IBIB di Indonesia ini mereka dapat rebit dari broker.")
    h = select.hook(w, koreksi={"IBIB": "IB-IB", "rebit": "rebate"})
    assert "IB-IB" in h and "IBIB" not in h
    assert "rebate" in h
