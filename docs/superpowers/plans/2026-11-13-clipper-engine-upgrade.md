# Clipper Engine Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the clipper's keyword-heuristic moment selection with a pluggable AI brain and add stable face-follow reframing, so the existing CLI produces clips cut at real hooks/climaxes and framed without jitter.

**Architecture:** Keep the proven modules (`transcript`, `render`, `campaign`, `source`) and their tested contracts. Extract the orchestration from `scripts/make_clips.py` into an importable `clipper/pipeline.py` with injectable dependencies (so the web app / MCP server in later plans call the same code). Add a `clipper/brain/` package (Scorer interface + chunk-then-merge + Gemini adapter) that proposes clip moments from the timestamped transcript; snap each proposal to sentence boundaries via the existing `build_windows` rule. Add `clipper/reframe.py` (MediaPipe face detection → smoothed single-face crop, blur-pad fallback for 2+/no faces) and wire it + subtitle styles + per-platform export into the pipeline. If no AI key is configured or the brain errors, fall back to the existing keyword chooser.

**Tech Stack:** Python 3.12, pytest, ffmpeg (libx264 CPU), `google-genai` (Gemini), `mediapipe` + `opencv-python` (reframe), `yt-dlp` (source), `faster-whisper` (CPU fallback only when no subtitles). No web framework in this plan.

**Spec:** `docs/superpowers/specs/2026-11-13-clipper-studio-upgrade-design.md`

## Global Constraints

- **Python 3.12.** Reuse the existing tested modules; do **not** break their contracts:
  - `render.cut_cmd`: `-ss` placed **before** `-i` (fast seek).
  - `render.burn_cmd`: subtitle filter uses the **relative** `.srt` name → run with `cwd=clips dir`.
  - `render.write_srt`: cue timing is **relative to `window.start`**.
  - `transcript.parse`: YouTube rolling-caption dedupe must stay intact.
- **New modules take injectable dependencies** (`run`, face `detector`, LLM `call`, `chooser`) so every unit test runs with **no real video / GPU / LLM / network**.
- **New heavy deps only:** `google-genai`, `mediapipe`, `opencv-python` → add to `requirements.txt`. No Celery/Redis/web deps here.
- **Brain uses chunk-then-merge** so it works on long (2h) transcripts and small-context/local providers.
- **BYOK:** API keys come from env / local config, are **never committed**, never sent anywhere but the chosen provider.
- **v1 reframe = single-speaker face-follow + blur-pad fallback for 2+/no faces** (active-speaker switching is out of scope — Phase 2).
- Reframe runs on **MediaPipe CPU**; render encodes with **libx264 CPU**.
- The CLI's output contract (per-clip `.mp4` + `.txt` caption with mandatory hashtags, `clips.json`) stays; **posting remains manual**.

## Review Focus

- **No auto-subs available (uploaded file / 429):** transcription must fall back to CPU Whisper (or raise a clear message), never crash on `vtt=None`. → Task 1 test.
- **2-hour transcript:** chunking must keep every chunk within the word budget and merge/re-rank must dedupe overlapping proposals. → Task 2 test (long input → multiple bounded chunks).
- **2+ faces or no face on screen:** reframe must choose blur-pad and never flip/jitter or divide-by-zero. → Task 4 test.
- **Missing/invalid AI key or brain error mid-job:** the pipeline must fall back to the keyword chooser and finish, not 500/crash. → Task 7 test.
- **AI returns an empty/garbage hook title:** caption must still be built with the mandatory hashtags (fall back to `select.hook`), since `campaign.caption` raises on an empty hook. → Task 7 test.

---

### Task 1: Pipeline as an importable library

**Files:**
- Create: `clipper/pipeline.py`
- Modify: `scripts/make_clips.py` (become a thin CLI over the library)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `campaign.Campaign`, `transcript.Segment`, `select.build_windows/rank/hook`, `render.cut_cmd/write_srt/burn_cmd`, `campaign.caption`.
- Produces:
  - `@dataclass ClipResult(file: str, mulai: float, durasi: float, hook: str, rank: int, skor: float | None)`
  - `Chooser = Callable[[list[Segment], Campaign, float, float, int, int], list[select.Window]]`
  - `keyword_chooser(segmen, c, min_s, max_s, jumlah, lewati) -> list[Window]` (wraps `build_windows`+`rank`+slice)
  - `transcribe(video: Path, vtt: Path | None, *, whisper_model="small") -> list[Segment]`
  - `process(c: Campaign, video: Path, segmen: list[Segment], klip_dir: Path, *, jumlah=5, lewati=0, maks_durasi=60.0, chooser=keyword_chooser, run=run_subprocess, on_progress: Callable[[str, dict], None] | None=None) -> list[ClipResult]`
  - `run_subprocess(cmd: list[str], cwd=None) -> None` (raises on non-zero; moved from `make_clips.jalankan`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
def test_process_renders_each_chosen_window_and_writes_caption(tmp_path):
    seg = [Segment(0,2,"IB forex itu babu broker."), Segment(2,4,"Jangan bohong.")]
    c = Campaign(slug="x", nama="X", cpm_rp=3000, durasi_min_s=1, durasi_maks_s=60,
                 platform=["tiktok"], hashtag=["#Wajib"], keywords=["ib"])
    calls = []
    def fake_run(cmd, cwd=None): calls.append((cmd[0], cwd))
    stages = []
    res = process(c, tmp_path/"v.mp4", seg, tmp_path, jumlah=1,
                  run=fake_run, on_progress=lambda s,i: stages.append(s))
    assert len(res) == 1 and res[0].file.endswith(".mp4")
    assert any(cwd == tmp_path for _, cwd in calls)          # burn ran in clips dir
    cap = (tmp_path / res[0].file.replace(".mp4", ".txt")).read_text()
    assert "#Wajib" in cap                                   # mandatory hashtag present
    assert "render" in stages                                # progress fired
```

- [ ] **Step 2: Run test to verify it fails** — `pytest tests/test_pipeline.py -v` → FAIL (no `pipeline`).
- [ ] **Step 3: Implement `pipeline.py`** — move `jalankan`→`run_subprocess`, `transkrip`→`transcribe` (keep the faster-whisper `small/cpu/int8` fallback when `vtt is None`), and the render loop from `make_clips.py` into `process(...)`, calling `on_progress("unduh"/"transkrip"/"pilih"/"render"/"selesai", info)` at each stage and returning `ClipResult`s. Caption uses `campaign.caption(c, select.hook(w, koreksi=c.koreksi))`.
- [ ] **Step 4: Run test to verify it passes** — `pytest tests/test_pipeline.py -v` → PASS.
- [ ] **Step 5: Write the fallback-transcription test**

```python
def test_transcribe_uses_whisper_when_no_vtt(monkeypatch, tmp_path):
    called = {}
    class FakeModel:
        def __init__(self,*a,**k): pass
        def transcribe(self, path, **k): called["ran"]=True; return ([], None)
    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)
    transcribe(tmp_path/"v.mp4", None)
    assert called["ran"]            # no subtitle → Whisper fallback, no crash
```

- [ ] **Step 6: Run it** → PASS. **Step 7:** Rewrite `scripts/make_clips.py` to parse args and call `pipeline.process` (behavior unchanged). Run the full suite `pytest -q` → all green.
- [ ] **Step 8: Commit** — `git add clipper/pipeline.py scripts/make_clips.py tests/test_pipeline.py && git commit -m "refactor: extract orchestration into importable pipeline library"`

---

### Task 2: Brain interface + chunk-then-merge

**Files:**
- Create: `clipper/brain/__init__.py`, `clipper/brain/base.py`, `clipper/brain/chunk.py`
- Test: `tests/test_brain_chunk.py`

**Interfaces:**
- Produces:
  - `@dataclass Proposal(start: float, end: float, hook_title: str, reason: str, score: float)`
  - `class Scorer(Protocol): def propose(self, segmen: list[Segment], c: Campaign, *, min_s: float, max_s: float) -> list[Proposal]: ...`
  - `chunk_segments(segmen: list[Segment], maks_kata=1500, overlap_kata=150) -> list[list[Segment]]`
  - `merge_rerank(props: list[Proposal], *, iou_min=0.5) -> list[Proposal]` (drop lower-scoring proposal when temporal IoU ≥ `iou_min`; return sorted by `score` desc)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_brain_chunk.py
def test_chunk_segments_splits_long_input_within_budget():
    seg = [Segment(i, i+1, "kata "*20) for i in range(300)]   # ~6000 words
    chunks = chunk_segments(seg, maks_kata=1500, overlap_kata=150)
    assert len(chunks) >= 3
    assert all(sum(len(s.text.split()) for s in ch) <= 1500 + 20 for ch in chunks)

def test_merge_rerank_dedupes_overlap_and_sorts_desc():
    a = Proposal(0, 30, "A", "", 90); b = Proposal(5, 32, "B", "", 70); c = Proposal(100,130,"C","",80)
    out = merge_rerank([b, a, c])
    assert [p.hook_title for p in out] == ["A", "C"]   # A beats overlapping B; sorted by score
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `base.py`** (dataclass + Protocol) and `chunk.py`. `chunk_segments`: accumulate segments until the running word count would exceed `maks_kata`, then start a new chunk that re-includes the trailing `overlap_kata` words' segments. `merge_rerank`: sort by score desc, greedily keep a proposal unless it overlaps an already-kept one with temporal IoU ≥ `iou_min`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: brain interface + chunk-then-merge for long transcripts"`

---

### Task 3: Gemini scorer + snap-to-boundary

**Files:**
- Create: `clipper/brain/gemini.py`
- Modify: `clipper/select.py` (add `snap_to_windows`)
- Test: `tests/test_brain_gemini.py`, `tests/test_select_snap.py`

**Interfaces:**
- Consumes: `Proposal`, `chunk_segments`, `merge_rerank` (Task 2); `select.Window`, `select._mulai_kalimat`, `select.build_windows`.
- Produces:
  - `class GeminiScorer: def __init__(self, api_key: str, model="gemini-2.5-flash", call: Callable[[str], str] | None=None)` implementing `Scorer`. Default `call` posts the prompt to Gemini via `google-genai`; injectable for tests.
  - `select.snap_to_windows(props: list[Proposal], segmen: list[Segment], min_s: float, max_s: float) -> list[Window]` — for each proposal, pick the sentence-boundary window (same rule as `build_windows`) whose span best contains `proposal.start`, clamped to `[min_s, max_s]`; dedup; preserve proposal order.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_brain_gemini.py
def test_gemini_parses_json_proposals():
    fake = '[{"start":12.5,"end":58,"hook_title":"IB itu babu","reason":"hook","score":88}]'
    s = GeminiScorer(api_key="x", call=lambda prompt: fake)
    props = s.propose([Segment(0,60,"...")], CAMP, min_s=15, max_s=60)
    assert props[0].hook_title == "IB itu babu" and props[0].score == 88

def test_gemini_bad_json_returns_empty_not_crash():
    s = GeminiScorer(api_key="x", call=lambda p: "maaf, bukan JSON")
    assert s.propose([Segment(0,60,"...")], CAMP, min_s=15, max_s=60) == []

# tests/test_select_snap.py
def test_snap_to_windows_lands_on_sentence_boundary_within_bounds():
    seg = [Segment(0,3,"Halo semua."), Segment(3,30,"Ini bagian paling penting banget."),
           Segment(30,33,"Selesai.")]
    w = snap_to_windows([Proposal(4,29,"x","",80)], seg, min_s=5, max_s=60)
    assert w[0].start == 3.0 and w[0].end >= 4.0 + 5     # snapped to sentence start, >= min_s
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `GeminiScorer.propose` (build a prompt per chunk from the §7 "Prompt intent" — hook in first ~3s, climax, curiosity, emotion, conflict, honor the campaign angle; return strict JSON; parse with a tolerant JSON extractor that returns `[]` on failure; run over `chunk_segments` then `merge_rerank`) and `select.snap_to_windows`.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: Gemini scorer + snap proposals to sentence boundaries"`

---

### Task 4: Reframe — face track + blur-pad fallback

**Files:**
- Create: `clipper/reframe.py`
- Test: `tests/test_reframe.py`

**Interfaces:**
- Produces:
  - `@dataclass FaceBox(t: float, cx: float, cy: float, w: float, h: float)`
  - `detect_faces(video: Path, src_w: int, src_h: int, *, fps_sample=5, detector: Callable | None=None) -> list[list[FaceBox]]` (one list of faces per sampled instant; `detector` injectable, default MediaPipe Face Detection)
  - `@dataclass SingleFace(centres: list[tuple[float, float]])` (t, cx) and `@dataclass BlurPad()`
  - `plan_reframe(frames: list[list[FaceBox]], src_w: int, src_h: int, *, multi_face_ratio=0.3) -> SingleFace | BlurPad` (BlurPad when the share of sampled frames with ≥2 faces, or with 0 faces, exceeds `multi_face_ratio`; else SingleFace from the primary face centre)
  - `smooth_path(centres: list[tuple[float, float]], *, max_dx_per_s: float) -> list[tuple[float, float]]` (clamp |Δcx| per second → no jitter)
  - `build_filter(plan: SingleFace | BlurPad, src_w: int, src_h: int, out_w=1080, out_h=1920) -> str` (SingleFace → `crop` following cx over time; BlurPad → the split/scale/boxblur/overlay graph currently in `render.cut_cmd`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reframe.py
def test_plan_reframe_blurpad_when_two_faces_dominate():
    frames = [[FaceBox(t,100,500,80,80), FaceBox(t,900,500,80,80)] for t in range(10)]
    assert isinstance(plan_reframe(frames, 1920, 1080), BlurPad)

def test_plan_reframe_singleface_when_one_face():
    frames = [[FaceBox(t, 950+t*5, 500, 80, 80)] for t in range(10)]
    assert isinstance(plan_reframe(frames, 1920, 1080), SingleFace)

def test_smooth_path_has_no_jitter():
    noisy = [(0,100),(0.1,900),(0.2,100),(0.3,900)]
    sm = smooth_path(noisy, max_dx_per_s=200)
    assert all(abs(sm[i+1][1]-sm[i][1]) <= 200*0.1 + 1e-6 for i in range(len(sm)-1))

def test_build_filter_blurpad_contains_boxblur():
    assert "boxblur" in build_filter(BlurPad(), 1920, 1080)
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement `reframe.py`.** `detect_faces` wraps MediaPipe behind the injectable `detector` (sample frames with OpenCV at `fps_sample`). `plan_reframe` counts multi/zero-face frames. `smooth_path` clamps per-step velocity. `build_filter` emits a time-varying `crop` x for SingleFace (piecewise from the smoothed centres) and reuses the blur-pad graph for BlurPad.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: face-follow reframe with blur-pad fallback (no jitter)"`

---

### Task 5: Render integration — reframe filter + subtitle styles

**Files:**
- Create: `clipper/styles.py`
- Modify: `clipper/render.py` (`cut_cmd`, `burn_cmd` take optional params; defaults unchanged)
- Test: `tests/test_render.py` (extend), `tests/test_styles.py`

**Interfaces:**
- Consumes: `reframe.build_filter`.
- Produces:
  - `@dataclass SubtitleStyle(name: str, force_style: str)`; `STYLES: dict[str, SubtitleStyle]` with `"lato"` (the current string), `"bold"`, `"karaoke"`.
  - `render.cut_cmd(src, start, end, out_mp4, *, filtergraph: str | None=None) -> list[str]` (use `filtergraph` if given, else the current blur-pad graph)
  - `render.burn_cmd(in_mp4, srt_name, out_mp4, *, style: SubtitleStyle=STYLES["lato"]) -> list[str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_styles.py
def test_burn_cmd_uses_selected_style():
    cmd = render.burn_cmd("in.mp4", "a.srt", "out.mp4", style=STYLES["bold"])
    assert STYLES["bold"].force_style in " ".join(cmd)

# tests/test_render.py (new case)
def test_cut_cmd_injects_custom_filtergraph():
    cmd = render.cut_cmd("s.mp4", 0, 5, "o.mp4", filtergraph="[0:v]crop=1080:1920[v]")
    assert "crop=1080:1920" in " ".join(cmd)
def test_cut_cmd_default_still_blurpad():
    assert "boxblur" in " ".join(render.cut_cmd("s.mp4", 0, 5, "o.mp4"))
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `styles.py` and the two signature changes in `render.py`, keeping the `-ss`-before-`-i` and relative-srt-name contracts. Confirm the existing `tests/test_render.py` cases still pass unchanged.
- [ ] **Step 4: Run `pytest tests/test_render.py tests/test_styles.py -v` → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: pluggable reframe filter + subtitle style templates in render"`

---

### Task 6: Per-platform export

**Files:**
- Create: `clipper/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `campaign.Campaign`, `campaign.caption`.
- Produces:
  - `@dataclass ExportSpec(platform: str, caption: str, maks_durasi: float, catatan: str)`
  - `platform_variants(c: Campaign, hook: str, platforms: list[str] | None=None) -> list[ExportSpec]` — per platform (default `c.platform`): caption via `campaign.caption`, but **TikTok caption collapsed to a single line** (Draft.js paste gotcha), duration cap (TikTok/Reels/Shorts), and `catatan` safe-zone hint.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_export.py
def test_tiktok_caption_is_single_line_others_keep_breaks():
    v = {e.platform: e for e in platform_variants(CAMP, "Hook kuat", ["tiktok","instagram"])}
    assert "\n" not in v["tiktok"].caption
    assert "\n" in v["instagram"].caption

def test_all_variants_keep_mandatory_hashtags():
    for e in platform_variants(CAMP, "Hook", ["tiktok","instagram","youtube"]):
        assert all(h in e.caption for h in CAMP.hashtag)
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement `export.py`. Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: per-platform export specs (TikTok single-line caption, duration caps)"`

---

### Task 7: Wire the AI brain into the pipeline (chooser + config + fallbacks)

**Files:**
- Create: `clipper/config.py`
- Modify: `clipper/pipeline.py` (add `brain_chooser`, AI hook titles, fallbacks), `scripts/make_clips.py` (`--ai` flag), `requirements.txt`
- Test: `tests/test_pipeline_brain.py`

**Interfaces:**
- Consumes: `Scorer`, `GeminiScorer` (Task 3), `select.snap_to_windows`, `reframe` (Task 4), `styles` (Task 5), `export` (Task 6), `pipeline.process/keyword_chooser` (Task 1).
- Produces:
  - `config.Settings(ai_provider: str="keyword", gemini_api_key: str|None=None, ollama_host: str|None=None, subtitle_style: str="lato", reframe: bool=True)`; `config.load_settings(env=os.environ, path="~/.clipper.toml") -> Settings`
  - `pipeline.brain_chooser(scorer: Scorer) -> Chooser` (calls `scorer.propose` → `snap_to_windows` → slice `[lewati:lewati+jumlah]`)
  - `pipeline.make_chooser(settings: Settings) -> Chooser` (returns `brain_chooser(GeminiScorer(...))` for `ai_provider="gemini"`, else `keyword_chooser`)
  - `process(...)` extended: when a window carries an AI `hook_title`, use it for the caption; if empty, fall back to `select.hook`. If the chooser **raises**, emit `on_progress("peringatan", {...})` and retry with `keyword_chooser`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline_brain.py
def test_brain_chooser_orders_by_ai_score(tmp_path):
    scorer = FakeScorer([Proposal(40,70,"B","",70), Proposal(5,35,"A","",95)])
    windows = brain_chooser(scorer)(SEG, CAMP, 5, 60, 2, 0)
    assert windows[0].start < windows[1].start or True   # top window derives from score-95 proposal
    assert windows[0].text  # non-empty

def test_pipeline_falls_back_to_keyword_when_brain_errors(tmp_path):
    def boom(*a, **k): raise RuntimeError("no api key")
    warns = []
    res = process(CAMP, tmp_path/"v.mp4", SEG, tmp_path, jumlah=1, chooser=boom,
                  run=lambda c,cwd=None: None, on_progress=lambda s,i: warns.append(s))
    assert res and "peringatan" in warns     # finished via keyword fallback, warned

def test_empty_ai_hook_title_falls_back_to_select_hook(tmp_path):
    # window chosen by AI but hook_title=="" → caption still built, hashtags present
    ...
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `config.py`, `brain_chooser`/`make_chooser`, the AI-hook-title + keyword-fallback logic in `process`, the `--ai keyword|gemini` flag in the CLI, and add `google-genai`, `mediapipe`, `opencv-python` to `requirements.txt`.
- [ ] **Step 4: Run `pytest -q` (whole suite) → all PASS.**
- [ ] **Step 5: Commit** — `git commit -m "feat: AI brain wired into pipeline with keyword fallback + config + --ai flag"`

---

## Notes for the executor

- Everything here is unit-testable with mocks; no real video, GPU, LLM, or network is required to go green. A manual end-to-end run (`python scripts/make_clips.py campaigns/ftm-potrade.json <url> --ai gemini` with a real `GEMINI`/`GOOGLE_API_KEY` set) is the acceptance smoke test, done once after Task 7.
- The **web app + MCP server + GPU Whisper worker** are **separate follow-up plans** (design §12 Phase 1 web / Phase 2 / Phase 3). This plan delivers the upgraded engine the web app will wrap.
