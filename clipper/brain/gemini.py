"""Scorer berbasis Gemini: LLM memilih momen yang berpotensi viral."""
import json
import re
from typing import Callable

from clipper.brain.base import BrainError, Proposal
from clipper.brain.chunk import chunk_segments, merge_rerank
from clipper.campaign import Campaign
from clipper.transcript import Segment

PROMPT = """Kamu editor video pendek (TikTok/Reels/Shorts). Dari transkrip bertimestamp \
di bawah, pilih segmen yang paling berpotensi viral sebagai klip mandiri.

Kriteria: hook kuat di ~3 detik pertama, klimaks/payoff, rasa penasaran, emosi, \
konflik, kutipan yang bisa dikutip. Hindari klip yang dimulai di tengah kalimat \
atau kehilangan konteks. Sesuaikan dengan angle campaign: {angle}.

Durasi tiap klip antara {min_s:.0f} dan {max_s:.0f} detik. start/end dalam detik \
sesuai timestamp transkrip.

Balas HANYA JSON array valid, tanpa teks lain, format:
[{{"start": 12.5, "end": 58.0, "hook_title": "...", "reason": "...", "score": 0-100}}]
Jika tidak ada yang layak, balas [].

Transkrip:
{transkrip}
"""


def _default_call(api_key: str, model: str) -> Callable[[str], str]:
    def call(prompt: str) -> str:
        if not api_key:
            raise BrainError("GEMINI/GOOGLE_API_KEY kosong")
        from google import genai  # lazy: hanya dibutuhkan saat benar-benar memanggil API
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(model=model, contents=prompt)
        return resp.text or ""
    return call


def _parse(teks: str) -> list[Proposal]:
    """Ekstraksi JSON toleran: kembalikan [] kalau gagal, tidak pernah raise."""
    try:
        m = re.search(r"\[.*\]", teks or "", re.DOTALL)
        data = json.loads(m.group(0)) if m else None
        if not isinstance(data, list):
            return []
    except (ValueError, TypeError):
        return []
    out: list[Proposal] = []
    for d in data:
        try:
            p = Proposal(start=float(d["start"]), end=float(d["end"]),
                         hook_title=str(d.get("hook_title", "")),
                         reason=str(d.get("reason", "")), score=float(d["score"]))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if p.end > p.start:
            out.append(p)
    return out


class GeminiScorer:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash",
                 call: Callable[[str], str] | None = None):
        self.api_key = api_key
        self.model = model
        self._call = call or _default_call(api_key, model)

    def _prompt(self, chunk: list[Segment], c: Campaign, min_s: float, max_s: float) -> str:
        angle = ", ".join(c.keywords) if c.keywords else c.nama
        transkrip = "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in chunk)
        return PROMPT.format(angle=angle, min_s=min_s, max_s=max_s, transkrip=transkrip)

    def propose(self, segmen: list[Segment], c: Campaign, *,
                min_s: float, max_s: float) -> list[Proposal]:
        props: list[Proposal] = []
        chunks = chunk_segments(segmen)
        gagal = 0
        terakhir: Exception | None = None
        for chunk in chunks:
            try:
                reply = self._call(self._prompt(chunk, c, min_s, max_s))
            except Exception as e:
                gagal += 1
                terakhir = e
                continue
            props.extend(_parse(reply))
        if chunks and gagal == len(chunks):
            raise BrainError(f"semua chunk gagal dipanggil: {terakhir}") from terakhir
        return merge_rerank(props)
