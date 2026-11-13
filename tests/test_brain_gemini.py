import pytest

from clipper.brain.base import BrainError
from clipper.brain.gemini import GeminiScorer
from clipper.campaign import Campaign
from clipper.transcript import Segment

CAMP = Campaign(slug="c", nama="C", cpm_rp=1, durasi_min_s=15, durasi_maks_s=60,
                platform=["tiktok"], hashtag=["#a"], keywords=["ib"])


def test_gemini_parses_json_proposals():
    fake = '[{"start":12.5,"end":58,"hook_title":"IB itu babu","reason":"hook","score":88}]'
    s = GeminiScorer(api_key="x", call=lambda prompt: fake)
    props = s.propose([Segment(0, 60, "...")], CAMP, min_s=15, max_s=60)
    assert props[0].hook_title == "IB itu babu" and props[0].score == 88


def test_gemini_bad_json_returns_empty_not_crash():
    s = GeminiScorer(api_key="x", call=lambda p: "maaf, bukan JSON")
    assert s.propose([Segment(0, 60, "...")], CAMP, min_s=15, max_s=60) == []


def test_gemini_tolerates_code_fence_and_bad_items():
    fake = '```json\n[{"start":1,"end":30,"hook_title":"a","reason":"r","score":70},{"oops":1}]\n```'
    s = GeminiScorer(api_key="x", call=lambda p: fake)
    props = s.propose([Segment(0, 60, "...")], CAMP, min_s=15, max_s=60)
    assert len(props) == 1 and props[0].score == 70


def test_gemini_all_chunks_fail_raises():
    def boom(p):
        raise RuntimeError("net")
    s = GeminiScorer(api_key="x", call=boom)
    with pytest.raises(BrainError):
        s.propose([Segment(0, 60, "...")], CAMP, min_s=15, max_s=60)


def test_gemini_partial_chunk_failure_keeps_successes():
    seg = [Segment(i, i + 1, "kata " * 20) for i in range(200)]   # >=2 chunks
    n = {"i": 0}

    def call(p):
        n["i"] += 1
        if n["i"] == 1:
            raise RuntimeError("transient")
        return '[{"start":1,"end":30,"hook_title":"a","reason":"r","score":70}]'
    s = GeminiScorer(api_key="x", call=call)
    props = s.propose(seg, CAMP, min_s=15, max_s=60)
    assert n["i"] >= 2 and len(props) == 1


def test_gemini_default_call_empty_key_fails_fast():
    s = GeminiScorer(api_key="")
    with pytest.raises(BrainError):
        s.propose([Segment(0, 60, "...")], CAMP, min_s=15, max_s=60)
