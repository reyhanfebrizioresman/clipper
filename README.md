# clipper

Mesin pemotong klip untuk campaign clipping (Clippo/TernakKlip).
Dari satu video panjang jadi beberapa klip 9:16 siap unggah + caption berisi hashtag wajib.

**Instalasi (Linux, macOS, Windows, GPU):** [docs/instalasi.md](docs/instalasi.md).
Setelah memasang, periksa dengan `.venv/bin/python scripts/cek_instalasi.py --unduh-model`.

```
python scripts/make_clips.py campaigns/ftm-potrade.json <url-atau-file> --jumlah 5
```

Alur: unduh (yt-dlp) → transkrip (subtitle bawaan, atau Whisper kalau tidak ada)
→ pilih momen (batas kalimat + skor kata kunci brief) → potong 9:16 + subtitle
→ tulis caption.

**Unggah tetap manual.** TikTok/Instagram melarang unggah otomatis; script berhenti
di file siap kirim. Aturan campaign (durasi, hashtag, larangan) ada di `campaigns/*.json`.

## Clipper Studio — web UI (pintu 1)

```
.venv/bin/python scripts/web.py            # http://127.0.0.1:8780
```

- **Sumber**: unduh dari URL atau unggah video; progres & batal di panel Job.
- **Studio**: putar video sumber, pratinjau kandidat (mulai di awal kalimat; yang
  berhenti di tengah kalimat diberi tanda), cari di transkrip, tandai awal/akhir sendiri,
  geser ±1 dtk, tulis hook, lalu render. Ada juga "Klip otomatis" (kata kunci / Gemini).
- **Pustaka klip**: putar, unduh, salin caption per platform (TikTok satu baris).
- **Campaign**: ubah brief; field yang tidak ada di form tetap dipertahankan.

Durasi maks bawaan 60 dtk (batas umum TikTok/Reels/Shorts), bisa dinaikkan sampai batas
campaign. Saat render, waktu ditempel ke kalimat utuh, tapi tidak akan memangkas lebih
dari 40% dari durasi yang dipilih (hasil = yang dipratinjau).

Tanpa login, jadi hanya mendengarkan 127.0.0.1 (host lain ditolak kecuali
`--izinkan-tanpa-auth`). Header `Host` harus loopback dan request yang mengubah data wajib
membawa `X-Clipper: 1`, supaya situs lain tidak bisa memicu aksi lewat browsermu.
Buka dari laptop lewat SSH tunnel, mis. lewat host perantara:

```
ssh -F ~/.ssh/config -L 8780:127.0.0.1:8780 reyhan "ssh -F /home/reyhan/.ssh/config -N -L 8780:127.0.0.1:8780 devodo"
```

## Menyesuaikan perangkat

Saat mulai, clipper mendeteksi CPU, RAM, dan GPU NVIDIA mesin tempat ia berjalan
(`clipper/hardware.py`), lalu mengisi setelan awal yang cocok:

| Mesin | Whisper | Preset encode | Unduhan | Reframe |
|---|---|---|---|---|
| ≥6 core, ≥8 GB | small | veryfast | 1080p | 5 fps |
| 4 core | base | superfast | 1080p | 3 fps |
| ≤2 core / <4 GB | tiny | ultrafast | 720p | 2 fps |
| GPU NVIDIA / AMD-ROCm | medium (≥5 GB VRAM) / large-v3 (≥10 GB) | — | — | — |
| Apple Silicon | small / medium (≥16 GB) / large-v3 (≥32 GB) | — | — | — |

GPU yang dipakai (`Perangkat` di Pengaturan, bawaan otomatis):

| GPU | Encoder video | Whisper |
|---|---|---|
| NVIDIA | NVENC | CUDA (faster-whisper) |
| Apple Silicon (Mac M1+) | VideoToolbox | MLX (`mlx-whisper`, terpasang otomatis lewat requirements di Mac arm64) |
| AMD di Windows | AMF | CPU |
| AMD / Intel di Linux | VAAPI (`/dev/dri/renderD*`, perlu `mesa-va-drivers` / `intel-media-va-driver`) | CPU, atau GPU AMD bila CTranslate2 build ROCm terpasang |

Encoder GPU hanya dipilih bila lolos uji encode sungguhan saat server mulai (argumen sama
dengan render), jadi build ffmpeg/driver yang tidak mendukung otomatis memakai CPU. GPU yang
gagal saat dipakai juga jatuh ke CPU dengan peringatan di panel Job. Rekomendasi ini lapisan paling bawah:
setelan yang diatur di web UI, `~/.clipper.toml`, atau env selalu menang. Proses berjalan
di mesin server clipper, bukan di komputer yang membuka web UI / klien MCP.

## Server MCP (pintu 2)

**Panduan setup lengkap:** [Codex, Claude, SSH reyhan/devodo, dan tes koneksi](docs/mcp-setup.md).
Pilih `clipper-devodo` untuk memakai sumber dan pustaka yang sama dengan web UI
di devodo. Contoh di bawah menjalankan engine pada server `reyhan`.

Klien AI kamu sendiri (Claude Code / Claude Desktop / Codex) yang memilih momen dan menulis
hook; engine yang memotong, memberi subtitle, dan menulis caption. Server tidak memanggil LLM.

```
.venv/bin/python scripts/mcp_server.py                     # stdio
.venv/bin/python scripts/mcp_server.py --http --port 8765  # streamable HTTP (127.0.0.1)
```

Dari mesin lain lewat SSH (konfigurasi Claude Code, `~/.claude.json` → `mcpServers`):

```json
"clipper": {"type": "stdio", "command": "ssh",
  "args": ["-F", "/home/reyhan/.ssh/config", "-T", "-o", "BatchMode=yes", "reyhan",
           "/home/reyhan/clipper-v2/.venv/bin/python",
           "/home/reyhan/clipper-v2/scripts/mcp_server.py"]}
```

Tool cepat: `list_campaigns`, `get_campaign_brief`, `save_campaign_brief`, `list_sources`,
`get_transcript`, `list_candidate_windows`, `list_clips`, `get_clip`, `get_summary`.

Kelola klip: `update_clip` (ubah hook/caption tanpa render, status baru/diunggah/disubmit,
tautan postingan), `delete_clip` (wajib `konfirmasi=true`), `rerender_clip` (job).
Pengaturan: `get_settings` / `update_settings`, sama dengan halaman Pengaturan web UI;
API key Gemini hanya bisa diatur dari web UI supaya tidak masuk riwayat percakapan AI.

Tool job (kerja panjang): `fetch_source`, `render_clips`, `auto_clips`, `rerender_clip` berjalan di latar.
Tool menunggu paling lama `tunggu_s` (bawaan 45 dtk, aman untuk batas waktu Codex), lalu
mengembalikan `{job_id, status}`; pantau dengan `job_status`, hentikan dengan `cancel_job`
(ffmpeg/yt-dlp dibunuh), lihat semua dengan `list_jobs`. Job hidup selama sesi server;
hasilnya (transkrip, klip) tetap di disk.

Reframe ikut-wajah memakai MediaPipe Tasks `FaceDetector` (dideteksi per 3 petak lebar frame
lalu digabung NMS, karena model short-range melewatkan wajah di bidikan lebar) dengan model
`models/blaze_face_short_range.tflite` (atau env `CLIPPER_FACE_MODEL`). API lama
`mp.solutions` sudah dihapus sejak mediapipe 0.10.30. Tanpa model, klip memakai blur-pad
dan peringatannya muncul di progres job / stderr. Hasil deteksi wajah di-cache per sumber
di `work/_sources/<source_id>/wajah-5fps.json`. Inti logikanya di `clipper/service.py` (dipakai ulang web app nanti).

Penyimpanan: `work/_sources/<source_id>/` (cache unduhan + transkrip) dan
`work/<campaign>/<source_id>/clips/` (mp4 + srt + caption .txt, manifest `clips.json`).
Env opsional: `CLIPPER_WORK`, `CLIPPER_CAMPAIGNS`, `GEMINI_API_KEY` (untuk `auto_clips ai=gemini`).
