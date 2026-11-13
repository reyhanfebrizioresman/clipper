from clipper.brain.base import Proposal
from clipper.campaign import Campaign
from clipper.config import Settings, load_settings
from clipper.pipeline import brain_chooser, keyword_chooser, make_chooser, process
from clipper.select import Window
from clipper.transcript import Segment

SEG = [Segment(i * 5, i * 5 + 5, f"Kalimat nomor {i} yang cukup panjang ya.") for i in range(14)]
CAMP = Campaign(slug="x", nama="X", cpm_rp=3000, durasi_min_s=5, durasi_maks_s=60,
                platform=["tiktok"], hashtag=["#Wajib"], keywords=["ib"])


class FakeScorer:
    def __init__(self, props): self.props = props
    def propose(self, segmen, c, *, min_s, max_s): return self.props


def test_brain_chooser_orders_by_ai_score():
    ws = brain_chooser(FakeScorer([Proposal(40, 70, "B", "", 70), Proposal(5, 35, "A", "", 95)]))(
        SEG, CAMP, 5, 60, 2, 0)
    assert ws[0].hook_title == "A" and ws[0].skor == 95
    assert ws[1].hook_title == "B" and ws[0].text


def test_brain_chooser_slices():
    ch = brain_chooser(FakeScorer([Proposal(0, 30, "A", "", 90), Proposal(40, 70, "B", "", 80)]))
    assert [w.hook_title for w in ch(SEG, CAMP, 5, 60, 1, 1)] == ["B"]


def test_pipeline_falls_back_to_keyword_when_brain_errors(tmp_path):
    def boom(*a, **k): raise RuntimeError("no api key")
    warns = []
    res = process(CAMP, tmp_path / "v.mp4", SEG, tmp_path, jumlah=1, chooser=boom,
                  run=lambda c, cwd=None: None, on_progress=lambda s, i: warns.append(s))
    assert res and "peringatan" in warns


def test_ai_hook_title_and_score_used(tmp_path):
    w = Window(0, 10, "Teks biasa saja ya.", [], hook_title="Judul AI", skor=88.0)
    res = process(CAMP, tmp_path / "v.mp4", SEG, tmp_path, jumlah=1,
                  chooser=lambda *a: [w], run=lambda c, cwd=None: None)
    assert res[0].skor == 88.0 and res[0].hook == "Judul AI"
    assert "Judul AI" in (tmp_path / res[0].file.replace(".mp4", ".txt")).read_text()


def test_empty_ai_hook_title_falls_back_to_select_hook(tmp_path):
    w = Window(0, 10, "Ini kalimat pembuka yang cukup panjang.", SEG[:2])
    res = process(CAMP, tmp_path / "v.mp4", SEG, tmp_path, jumlah=1,
                  chooser=lambda *a: [w], run=lambda c, cwd=None: None)
    assert res[0].hook.startswith("Ini kalimat")
    assert "#Wajib" in (tmp_path / res[0].file.replace(".mp4", ".txt")).read_text()


def test_reframe_planner_filtergraph_passed_to_cut(tmp_path):
    cmds = []
    process(CAMP, tmp_path / "v.mp4", SEG, tmp_path, jumlah=1,
            run=lambda c, cwd=None: cmds.append(c), reframe_planner=lambda v, w: "FG_MARK")
    assert any("FG_MARK" in " ".join(c) for c in cmds)


def test_make_chooser():
    assert make_chooser(Settings()) is keyword_chooser
    assert make_chooser(Settings(ai_provider="gemini", gemini_api_key="k")) is not keyword_chooser


def test_load_settings(tmp_path):
    assert load_settings({}, tmp_path / "none.toml") == Settings()
    t = tmp_path / "c.toml"
    t.write_text('ai_provider = "gemini"\nsubtitle_style = "bold"\n')
    s = load_settings({"GEMINI_API_KEY": "abc"}, t)
    assert (s.ai_provider, s.subtitle_style, s.gemini_api_key) == ("gemini", "bold", "abc")
