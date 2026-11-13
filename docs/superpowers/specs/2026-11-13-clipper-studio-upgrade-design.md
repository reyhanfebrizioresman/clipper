# Clipper Studio — Design (upgrade of `Projects/clipper`)

- **Date:** 2026-11-13
- **Status:** DRAFT — for human approval before any build
- **Repo:** `/Users/macairm32024/Projects/clipper` (local git; working copy on `reyhan:~/clipper`)
- **Author:** Claude (brainstormed with user)

---

## 1. Intent & Why

The user wants to work as a **professional clipper**: take long-form videos (podcasts,
streams, interviews, campaign footage), cut them into high-quality vertical shorts, post to
TikTok / Instagram / YouTube / Facebook, and earn from **clipping campaigns** (Clippo:
Rp/1k verified views). They already have a working CLI engine (`Projects/clipper`, 32 tests,
real clips published to TikTok `@potongcuan`), but tried a third-party tool
(`opensource-clipping`) today and found its output **bad**: clips were not taken at the
climax/hook moments, the auto-reframe camera jittered left-right, cut points didn't match the
narration, and the style was weak.

**Core insight:** the existing engine's weakness is exactly the complaint — moment selection
is a **keyword-count heuristic** (`select.rank()`), not hook/climax aware. Everything else
(sentence-boundary cutting, 9:16 render, subtitle styling, campaign hashtags) is solid and
tested. So this is an **upgrade**, not a rewrite: keep the proven parts, replace the "brain",
add a "face" (reframe) and a "studio" (web UI), and make it **distributable** so other
clippers can self-host or drive it via MCP with their own AI subscription.

## 2. Goals / Non-goals / Anti-goals

**Goals**
- Pick genuinely good moments: hook in the first ~3 seconds, climax / curiosity / emotion /
  conflict — using an LLM, not keyword counts.
- Stable vertical reframe that follows the speaker's face (no jitter).
- A real **web UI** (dashboard, new job, preview + light edit, render queue, clip library).
- **Pluggable AI brain**: BYOK (Gemini / OpenAI / Anthropic / OpenRouter), local Ollama, or
  **MCP mode** (a Claude/Codex subscription holder drives it from their own client).
- **Self-hostable / distributable** (Model A): each user runs their own copy with their own
  keys; no central login / billing / storage of other people's secrets.
- Keep the campaign workflow: per-campaign caption + mandatory hashtags, per-platform export,
  campaign tracker (incl. Clippo rule: a clip needs ≥1,000 views before it can be submitted).
- Run acceptably on weak hardware by **offloading only the GPU-heavy step (Whisper)** to an
  optional GPU worker; everything else runs CPU-first on `reyhan`.

**Non-goals (v1)**
- Multi-tenant SaaS (accounts, billing, hosting other people's data) — that is Model B, later.
- Automated posting to TikTok/IG (platform ToS forbids automation; posting stays **manual**,
  the tool only prepares files + captions and can open the upload tab via remote Chrome).
- Running the whole pipeline on Kaggle like the third-party tool did.

**Anti-goals (these mean failure even if it "works")**
- Clips that open on a filler fragment ("jadi gini…", "Iya.") instead of a real hook.
- A reframe that pans/jitters unpredictably.
- Forcing a specific paid AI provider — the brain must be swappable, including free/local and
  subscription-via-MCP.
- Holding other users' API keys on a server they don't control.

## 3. Users & Use

- **Primary:** the user, as a clipper, via the web UI on `reyhan`.
- **Secondary:** other clippers who self-host the tool, or who have a Claude/Codex
  subscription and attach the **MCP server** to their own AI client.
- Posting is always done by a human (ToS); the tool stops at "ready-to-upload file + caption".

## 4. Constraints (verified 2026-11-13)

- **`reyhan`:** 4 CPU cores, 15 GB RAM (~10 GB free), **no NVIDIA GPU**, ffmpeg 6.1.1,
  Python 3.12.3. (ffmpeg lists `h264_nvenc` but with no GPU present it is unusable → **CPU
  encode / libx264 only**.) Good enough for orchestration, FFmpeg CPU render, and CPU
  MediaPipe face-tracking; **too slow for Whisper on long footage** → offload.
- **Ollama** lives on **devodo**, not reyhan.
- **Kaggle T4** GPU is already set up and working this session (free, 30h/week, ~12h sessions,
  no persistence, needs a tunnel) — the known GPU-offload target. (See the Kaggle setup notes:
  Python-3.13→3.12 via `uv`, and `av>=11,<13` pin for faster-whisper.)
- **Platform ToS:** no automated posting; "normal" volume 3–5 clips/day/account; dedicated
  clipping accounts only.
- **Clippo:** clip must reach ≥1,000 views before it can be submitted; CPM equal for TikTok &
  IG; max 10 clips per submission.
- **Copyright:** only clip footage the campaign explicitly licenses, or the user's own content.

## 5. Architecture overview — one engine, two doors

```
                 ┌──────────────────────────────────────────────┐
                 │                CLIPPER CORE (Python)           │
  source ──────▶ │  source → transcript → SELECT(brain) →         │ ──▶ clips + captions
 (url/file)      │  REFRAME(face) → render(cut/srt/burn) →        │     (ready to post)
                 │  campaign(caption+hashtags)                     │
                 └───────▲───────────────▲──────────────▲─────────┘
                         │               │              │
        ┌────────────────┴───┐   ┌───────┴────────┐  ┌──┴───────────────┐
        │  WEB APP (door 1)  │   │  MCP SERVER     │  │ COMPUTE WORKERS   │
        │ FastAPI + UI       │   │  (door 2)       │  │ CPU(reyhan) +     │
        │ BYOK / local brain │   │ client's AI     │  │ optional GPU      │
        │ job queue, preview │   │ (Claude/Codex)  │  │ (Kaggle/devodo)   │
        └────────────────────┘   └─────────────────┘  └───────────────────┘
```

- **Door 1 — Web app:** FastAPI backend wrapping the core, with a browser UI. The backend
  calls the configured AI brain (BYOK provider or local Ollama) to score/choose moments.
- **Door 2 — MCP server:** exposes the core as MCP tools. An external AI client (the user's
  Claude Code / Claude Desktop / Codex, paid by **their** subscription) does the hook
  reasoning and calls the tools. The core does the mechanical work; no LLM call is billed by us.
- **Pluggable compute:** the heavy GPU step (Whisper word-level) runs on an optional GPU
  worker; everything else runs CPU-first on reyhan, with graceful fallback.

## 6. Reuse / Replace / Add

| Part | Decision | Notes |
|---|---|---|
| `transcript.py` (Segment, filler/koreksi/kapital) | **Reuse** | data model + text cleanup stay |
| `source.py` (yt-dlp download + subs) | **Reuse, extend** | add non-YouTube sources, uploaded files |
| `select.build_windows` (sentence-boundary windows) | **Reuse as a constraint** | LLM picks moments, we snap to these boundaries |
| `select.rank` (keyword count) | **REPLACE** | → AI brain (pluggable) |
| `select.hook` (caption opener) | **Reuse / let AI improve** | AI can suggest a stronger hook title |
| `render.cut_cmd / write_srt / burn_cmd` (9:16 crop+blur, Lato subs) | **Reuse, extend** | add face-reframe path + subtitle style templates |
| `campaign.py` (brief JSON, caption + mandatory hashtags) | **Reuse, extend** | add per-platform export + campaign tracker |
| `scripts/make_clips.py` (CLI orchestration) | **Reuse as the core library** | web app + MCP call the same functions |
| **face-tracking reframe** | **ADD** | MediaPipe (CPU), smoothed crop path |
| **AI brain (pluggable)** | **ADD** | providers + MCP delegation |
| **web app + UI** | **ADD** | FastAPI + frontend |
| **MCP server** | **ADD** | expose core as tools |
| **GPU-offload worker** | **ADD** | optional, for Whisper |
| **job queue + storage/library** | **ADD** | SQLite + files |

## 7. The AI brain (pluggable)

**Interface (concept):** given the timestamped transcript (+ campaign brief), return a ranked
list of clip proposals: `{start, end, hook_title, reason, score}`. The engine then **snaps each
proposal to sentence boundaries** (reusing `build_windows`' rule) and validates duration
(campaign min/max, prefer ≤60s). This lets the LLM find the *real* climax even when the
heuristic windows miss it, while keeping cuts clean.

**Prompt intent:** "From this timestamped transcript, find the segments most likely to go
viral as a standalone short. Reward: a hook that lands in the first ~3s, a climax or payoff,
curiosity, strong emotion, conflict, a quotable line. Penalize: starting mid-sentence, context
the viewer won't have, slow build-ups. Honor the campaign angle. Return JSON with start/end,
a punchy hook title, a one-line reason, and a 0–100 score."

**Providers (each is a small adapter behind one interface):**
- `gemini` (BYOK) — **default for v1**.
- `openai`, `anthropic`, `openrouter` (BYOK).
- `ollama` (local, points at devodo; free; for volume).
- `mcp` — not an adapter the server calls; instead the **MCP door** hands the transcript to the
  client's AI, which returns the proposals via the `propose_clips` tool.

Keys are read from the user's own config/env; in Model A the server only ever holds the running
user's own key.

**Long transcripts (locked):** a 1–2h podcast is ~20–40k+ tokens — fine for long-context cloud
models but over the window of small/local Ollama models, which are exactly the "volume" case. So
the brain uses a **chunk-then-merge-and-rerank** strategy: split the timestamped transcript into
overlapping windows, score each chunk, then merge + globally re-rank the proposals. This makes the
brain work on *any* provider (incl. small-context local) and on long footage, at the cost of more
LLM calls per job (acceptable; local = free, cloud = still cheap at low volume).

## 8. Compute — CPU-first, optional GPU worker

- **Transcript:** prefer **YouTube auto-subs** (existing behavior) → no Whisper needed in the
  common case. When subs are missing (uploaded files, other platforms) or when word-level
  timing is wanted for karaoke: run **Whisper**.
- **Whisper location (pluggable "compute backend"):**
  - `cpu` — faster-whisper small/int8 on reyhan (works, slow on long videos; fine for short).
  - `gpu` — offload to a GPU worker: **Kaggle T4** (reuse the tunnel pattern we already have),
    or **devodo** if a GPU is available there. Worker exposes a tiny transcribe endpoint over a
    tunnel; the core posts audio, gets back word-level segments.
  - Graceful fallback: if no GPU worker is configured/reachable, fall back to CPU (or to
    auto-subs only) and warn.
- **Face-tracking reframe (v1 scope — locked):** MediaPipe face detection per sampled frame →
  smoothed crop centre path (no per-frame jitter) → crop expression for ffmpeg. Runs on **reyhan
  CPU**; sample frames (e.g. 5–10 fps) and interpolate to keep it fast.
  - **Single-speaker:** follow the one face smoothly.
  - **2+ faces on screen:** fall back to **blur-pad** (both visible, blurred background) — stable,
    never flips between faces. This fixes the "jittery camera" complaint without heavy work.
  - **Active-speaker switching** (detect who is talking via lip-motion / audio-visual sync and cut
    the crop to the speaker) is **deferred to Phase 2** — it is the premium feature but too heavy
    for a CPU-only v1.
- **Render:** ffmpeg **libx264 CPU** on reyhan (nvenc unavailable).

## 9. Web app (door 1)

Pages (mirrors the good parts of the Studio UI we saw, cleaner):
- **Dashboard** — jobs list, status, quick stats, worker/brain health.
- **New Job** — paste URL or upload file; choose campaign, #clips, aspect, subtitle style, AI
  provider, Whisper on/off + compute backend.
- **Job detail** — live progress per stage; **candidate review**: preview each proposed clip,
  nudge start/end, edit hook title / subtitle, approve or reject, then render approved ones.
  **Preview is lightweight (locked):** HTML5 playback of the *source segment* at the proposed
  in/out points + the hook title + subtitle text — NOT a rendered proxy. The final reframe +
  burned subtitles are rendered **only for approved** candidates. (Keeps the approve loop fast and
  avoids doubling ffmpeg work on reyhan's CPU-only encode.)
- **Clip library** — all rendered clips, filter by campaign; per-platform export; caption copy.
- **Campaigns** — brief, mandatory hashtags, rate, submit status (Clippo ≥1,000-views rule).
- **Settings** — API keys (stored locally), compute backend / GPU worker URL, Ollama host.

Backend: FastAPI serving a JSON API + the core; a background job runner; SQLite for jobs,
clips, campaigns; files under a work dir. Previews are served locally (self-host → no ngrok
browser-warning problem).

## 10. MCP server (door 2)

Exposes the core as tools so a subscription AI client does the reasoning:
- `get_campaign_brief(slug)` · `fetch_source(url_or_file)` → transcript + metadata
- `list_candidate_windows(min_s, max_s)` → sentence-boundary windows with text + timing
- `propose_clips(...)` ← the client returns its chosen moments (this is where the client's AI
  thinks) · or the client just calls `render_clips(selections, style, campaign)`
- `render_clips(...)` → rendered files + captions · `list_clips()` / `get_clip(id)`

The MCP server runs alongside (or instead of) the web app; same core, same storage.

## 11. Data & storage

- **SQLite** (self-contained, fits Model A): `campaigns`, `jobs`, `candidates`, `clips`,
  `settings`. Files (source, raw, srt, final mp4, caption .txt) on disk under a work dir.
- Secrets (API keys, worker URLs) in a local config / `.env`, never committed, never sent
  anywhere except the provider the user chose.

## 12. Phasing

**Phase 1 — "clips that don't suck" (MVP):**
1. Wrap the existing core as an importable library + FastAPI backend + minimal web UI
   (new job, progress, candidate review, library).
2. **AI brain** with the Gemini adapter (BYOK) replacing `rank`; snap-to-sentence + duration
   validation; AI-suggested hook titles.
3. **Face-tracking reframe** (MediaPipe CPU) as the default 9:16 path, keeping blur-pad as a
   fallback.
4. Keep existing subtitle render; add **1–2 subtitle style templates** (incl. karaoke).
5. Campaign caption/hashtags (reuse) + per-platform export.

**Phase 2 — reach & polish:**
- **Active-speaker-switching reframe** (multi-face: cut crop to whoever is talking).
- Pluggable compute: GPU Whisper worker (Kaggle) + graceful fallback; word-level karaoke subs.
- More providers (OpenAI/Anthropic/OpenRouter/Ollama) + provider picker.
- Silence trim, audio loudness normalize, hook-text overlay, more subtitle styles.
- Campaign tracker (rates, submit status, Clippo ≥1,000-views gate).

**Phase 3 — distribution & extras:**
- **MCP server** door (subscription-driven).
- Packaging for self-host (one-command run), docs.
- Analytics (pull per-clip views → estimated earnings), scheduling, creator-face-required
  detection, A/B hook titles, B-roll.

(Phases are a default order; the user can re-prioritise.)

## 13. Decisions made by Claude (my calls — veto welcome)

- **Host on `reyhan`** for the user's own instance; CPU-first; GPU worker optional.
- **Core stays Python**, wrapped as a library both doors import (no logic duplicated).
- **Backend: FastAPI**; **DB: SQLite**; **job runner**: simple in-process background worker
  (not Celery/Redis — keep Model A single-process and easy to self-host).
- **Default AI brain: Gemini (BYOK)**, swappable.
- **Reframe: MediaPipe on CPU** with frame sampling + smoothing; blur-pad fallback retained.
- **Whisper only when needed** (auto-subs preferred); GPU offload target = **Kaggle** reusing
  the tunnel pattern.
- **Keep posting manual**; the tool may *assist* via remote Chrome but never auto-posts.

## 14. Decisions locked after review (2026-11-13)

A builder reviewed this doc; the user then settled the forks that would reshape the plan:

- **Frontend:** **(a) UI built into FastAPI** (one process, easiest to self-host / distribute —
  Model A). Not a separate Next.js app.
- **v1 reframe:** single-speaker face-follow + **blur-pad fallback for 2+ faces**; active-speaker
  switching → Phase 2 (see §8, §12).
- **Candidate preview:** **lightweight** (source segment + in/out + hook/subtitle text); final
  render only on approve (see §9).
- **Brain on long transcripts:** **chunk-then-merge** so it works on any provider incl. local
  Ollama (see §7).

## 15. Left to the builder

- Concrete module/API layout, the exact brain prompt + JSON schema + snap-to-boundary logic,
  the MediaPipe→crop-path math and smoothing, the FastAPI routes + job-runner, the SQLite
  schema, the Whisper-worker protocol, and the subtitle style templates. All constrained by the
  reuse map (§6) and the existing tested modules.
