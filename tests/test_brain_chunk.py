from clipper.brain.base import Proposal
from clipper.brain.chunk import chunk_segments, merge_rerank
from clipper.transcript import Segment


def test_chunk_segments_splits_long_input_within_budget():
    seg = [Segment(i, i+1, "kata "*20) for i in range(300)]   # ~6000 words
    chunks = chunk_segments(seg, maks_kata=1500, overlap_kata=150)
    assert len(chunks) >= 3
    assert all(sum(len(s.text.split()) for s in ch) <= 1500 + 20 for ch in chunks)


def test_chunk_segments_overlap_and_coverage():
    seg = [Segment(i, i+1, "kata "*20) for i in range(300)]
    chunks = chunk_segments(seg, maks_kata=1500, overlap_kata=150)
    assert chunks[0][0] is seg[0] and chunks[-1][-1] is seg[-1]
    for a, b in zip(chunks, chunks[1:]):
        assert b[0].start <= a[-1].start  # chunk berikutnya mengulang ekor


def test_chunk_segments_short_and_empty():
    assert chunk_segments([]) == []
    seg = [Segment(0, 1, "a b c")]
    assert chunk_segments(seg) == [seg]


def test_merge_rerank_dedupes_overlap_and_sorts_desc():
    a = Proposal(0, 30, "A", "", 90); b = Proposal(5, 32, "B", "", 70); c = Proposal(100,130,"C","",80)
    out = merge_rerank([b, a, c])
    assert [p.hook_title for p in out] == ["A", "C"]   # A beats overlapping B; sorted by score
