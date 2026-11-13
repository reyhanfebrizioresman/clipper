"""Potong transkrip panjang jadi chunk bertumpang-tindih, lalu gabung usulan."""
from clipper.brain.base import Proposal
from clipper.transcript import Segment


def _kata(s: Segment) -> int:
    return len(s.text.split())


def chunk_segments(segmen: list[Segment], maks_kata: int = 1500,
                   overlap_kata: int = 150) -> list[list[Segment]]:
    chunks: list[list[Segment]] = []
    cur: list[Segment] = []
    total = 0
    for s in segmen:
        w = _kata(s)
        if cur and total + w > maks_kata:
            chunks.append(cur)
            # ulang segmen ekor (<= overlap_kata kata) sebagai awal chunk baru
            tail: list[Segment] = []
            tw = 0
            for t in reversed(cur):
                if tw + _kata(t) > overlap_kata:
                    break
                tail.insert(0, t)
                tw += _kata(t)
            # pastikan chunk baru masih muat segmen ini (menjamin kemajuan)
            while tail and tw + w > maks_kata:
                tw -= _kata(tail.pop(0))
            cur, total = tail, tw
        cur.append(s)
        total += w
    if cur:
        chunks.append(cur)
    return chunks


def _iou(a: Proposal, b: Proposal) -> float:
    inter = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    union = (a.end - a.start) + (b.end - b.start) - inter
    return inter / union if union > 0 else 0.0


def merge_rerank(props: list[Proposal], *, iou_min: float = 0.5) -> list[Proposal]:
    kept: list[Proposal] = []
    for p in sorted(props, key=lambda x: x.score, reverse=True):
        if all(_iou(p, k) < iou_min for k in kept):
            kept.append(p)
    return kept
