from clipper.brain.base import Proposal
from clipper.select import snap_to_windows
from clipper.transcript import Segment


def test_snap_to_windows_lands_on_sentence_boundary_within_bounds():
    seg = [Segment(0, 3, "Halo semua."), Segment(3, 30, "Ini bagian paling penting banget."),
           Segment(30, 33, "Selesai.")]
    w = snap_to_windows([Proposal(4, 29, "x", "", 80)], seg, min_s=5, max_s=60)
    assert w[0].start == 3.0 and w[0].end >= 4.0 + 5


def test_snap_dedups_and_preserves_order():
    seg = [Segment(0, 3, "Halo semua."), Segment(3, 30, "Ini bagian penting."),
           Segment(30, 60, "Lanjut lagi.")]
    ps = [Proposal(31, 59, "b", "", 50), Proposal(4, 29, "a", "", 80), Proposal(5, 28, "c", "", 70)]
    w = snap_to_windows(ps, seg, min_s=5, max_s=60)
    assert [x.start for x in w] == [30.0, 3.0]


def test_snap_carries_hook_title_and_score_from_source_proposal():
    from clipper.brain.base import Proposal
    from clipper.select import snap_to_windows
    seg = [Segment(i * 5, i * 5 + 5, f"Kalimat {i} lengkap.") for i in range(14)]
    ws = snap_to_windows([Proposal(0, 20, "A", "", 90), Proposal(40, 60, "B", "", 70)],
                         seg, 10, 30)
    assert [(w.hook_title, w.skor) for w in ws] == [("A", 90), ("B", 70)]


def test_snap_keeps_requested_length_when_sentence_end_would_halve_it():
    # kalimat terakhir melewati max_s: akhir kalimat terdekat (detik 30) membuang separuh
    # pilihan 0-57. Hasil harus tetap ~57 dtk (batas segmen), bukan 30 dtk.
    seg = [Segment(0, 30, "Kalimat pertama selesai."), Segment(30, 57, "kalimat kedua panjang"),
           Segment(57, 70, "baru berakhir di sini.")]
    w = snap_to_windows([Proposal(0, 57, "x", "", 50)], seg, min_s=5, max_s=60)
    assert (w[0].start, w[0].end) == (0, 57)


def test_snap_still_prefers_sentence_end_when_trim_is_small():
    seg = [Segment(0, 50, "Kalimat panjang selesai."), Segment(50, 57, "lalu penggalan"),
           Segment(57, 70, "baru berakhir.")]
    w = snap_to_windows([Proposal(0, 57, "x", "", 50)], seg, min_s=5, max_s=60)
    assert w[0].end == 50                           # pangkas 12% -> akhir kalimat menang
