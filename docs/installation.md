# Installing Clipper

*English · [Bahasa Indonesia](instalasi.md)*

How to install Clipper on your own computer or server, from scratch until the
**Clipper Studio** web UI is open in your browser.

> **Where to install it?** All processing (download, transcription, rendering) runs on the
> machine where Clipper is installed. A computer that only *opens* the web UI or uses an
> AI client (MCP) needs nothing more than a browser/SSH. Install it on your strongest machine.

> **Language note:** the web UI, the install checker's output and the settings names are in
> Indonesian. This guide gives the English meaning next to each label you need, e.g.
> **Pengaturan** (Settings).

In short, the order is the same on every OS:

1. Install the system programs: **Python 3.11/3.12, ffmpeg, Deno, git, the Lato font**.
2. Get the code, create a virtualenv, `pip install -r requirements.txt`.
3. Run `scripts/cek_instalasi.py --unduh-model` ("check installation, download model"):
   it checks everything and downloads the face detection model.
4. Run `scripts/web.py` and open http://127.0.0.1:8780.

| System | Status |
|---|---|
| Debian 12 / Ubuntu 24.04 (x86_64) | Used daily, tested |
| macOS Apple Silicon (M1 and later) | Supported, not yet tested on a real machine |
| Windows 10/11 | Should work, not yet tested; alternative: WSL2 + the Linux steps |

Minimum: 2 cores, 4 GB RAM, ~3 GB for the programs + models, plus space for videos
(1080p video is about 1 GB per hour). Recommended: 6 cores / 8 GB RAM or more. Clipper
tunes its starting settings to the machine it runs on (see [GPU & performance](#gpu--performance)).

---

## Linux (Debian / Ubuntu)

### 1. System programs

```bash
sudo apt update
sudo apt install -y git python3 python3-venv ffmpeg fonts-lato fontconfig libegl1 libgles2
curl -fsSL https://deno.land/install.sh | sh
```

- `libegl1 libgles2` are needed by MediaPipe (face detection), especially on headless servers.
- Deno is installed to `~/.deno/bin/deno`; Clipper finds it there even if it is not on PATH.
- Python must be **3.11 or 3.12**. Check with `python3 --version`. Ubuntu 22.04 still
  ships 3.10, so install 3.12 first:

  ```bash
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt install -y python3.12 python3.12-venv
  ```

  then use `python3.12` instead of `python3` in the next step.

### 2. Code & Python dependencies

```bash
git clone https://github.com/reyhanfebrizioresman/clipper.git
cd clipper
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

The `.venv` folder ends up around 1.2 GB. The Whisper model is downloaded automatically the
first time it is needed (the `small` model is about 500 MB), only for videos without subtitles.

### 3. Check & download the model

```bash
.venv/bin/python scripts/cek_instalasi.py --unduh-model
```

Every line should say `[ OK ]`. Lines marked `[GAGAL]` (failed) must be fixed; the fix is
printed underneath. `[PERINGATAN]` (warning) can be ignored if you don't need that feature.

### 4. Run

```bash
.venv/bin/python scripts/web.py
```

Open http://127.0.0.1:8780. Continue with [Opening it from another computer](#opening-it-from-another-computer)
if Clipper is installed on a server, and [Start automatically on boot](#start-automatically-on-boot-linux)
so you don't have to start it by hand.

---

## macOS (Apple Silicon)

### 1. System programs

Install [Homebrew](https://brew.sh) if you don't have it, then:

```bash
brew install python@3.12 ffmpeg deno git
brew install --cask font-lato
```

Homebrew's ffmpeg already includes libass (subtitles) and VideoToolbox (Apple GPU encoder).

### 2. Code & Python dependencies

```bash
git clone https://github.com/reyhanfebrizioresman/clipper.git
cd clipper
python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

On Apple Silicon Macs, `requirements.txt` also installs `mlx-whisper`, so Whisper
transcription runs on the Apple GPU. On Intel Macs that package is skipped and Whisper uses
the CPU.

### 3–4. Check & run

```bash
.venv/bin/python scripts/cek_instalasi.py --unduh-model
.venv/bin/python scripts/web.py
```

Open http://127.0.0.1:8780.

---

## Windows 10/11

> Not yet tested on Windows. If a step fails, the safest route is
> [WSL2](https://learn.microsoft.com/windows/wsl/install) (`wsl --install -d Ubuntu-24.04`),
> then follow the **Linux** steps inside that Ubuntu. Please report the problem on GitHub.

### 1. System programs

Open **PowerShell**, then:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
winget install -e --id DenoLand.Deno
winget install -e --id Git.Git
```

Close and reopen PowerShell so the new PATH is picked up. Lato font: download it from
[Google Fonts](https://fonts.google.com/specimen/Lato), extract it, right-click all the
`.ttf` files → **Install for all users**.

### 2. Code & Python dependencies

```powershell
git clone https://github.com/reyhanfebrizioresman/clipper.git
cd clipper
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -r requirements.txt
```

### 3–4. Check & run

```powershell
.venv\Scripts\python scripts\cek_instalasi.py --unduh-model
.venv\Scripts\python scripts\web.py
```

Open http://127.0.0.1:8780. If Windows Firewall asks, you don't need to allow network
access: the web UI only listens on the computer itself.

---

## GPU & performance

Nothing needs configuring to get started: when the server starts, Clipper detects the CPU,
RAM and GPU and picks matching starting settings. You can see the result under
**Pengaturan → Perangkat server** (Settings → Server hardware) and at the end of
`cek_instalasi.py`.

| GPU | Video rendering | Whisper transcription | What to install |
|---|---|---|---|
| None / unsupported | CPU (libx264) | CPU | — |
| NVIDIA | NVENC | CUDA | NVIDIA driver (+ CUDA libraries for Whisper, see below) |
| Apple Silicon | VideoToolbox | MLX | already handled by Homebrew + `requirements.txt` |
| AMD on Linux | VAAPI | CPU (GPU with a ROCm build of CTranslate2) | `mesa-va-drivers` |
| Intel on Linux | VAAPI | CPU | `intel-media-va-driver` |
| AMD on Windows | AMF | CPU | latest AMD Adrenalin driver |

A GPU encoder is only used if it **passes a real test encode** when the server starts, and
if it fails in the middle of a job Clipper switches to the CPU with a warning in the Job
panel. So the GPU steps below can't break anything; at worst Clipper keeps using the CPU.
After installing GPU drivers/libraries, **restart** the web UI so detection runs again.

The automatic choice can be overridden under **Pengaturan → Perangkat** (Settings → Hardware):
Whisper on CPU/CUDA/MLX; encoder CPU/NVENC/VideoToolbox/AMF/VAAPI.

### NVIDIA

1. Install the official NVIDIA driver; `nvidia-smi` should list the GPU. Rendering (NVENC)
   works right away with ffmpeg from apt/winget.
2. For Whisper on the GPU, faster-whisper needs cuBLAS (CUDA 12) and cuDNN 9. The easiest
   way on Linux, from the `clipper` folder:

   ```bash
   .venv/bin/pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
   export LD_LIBRARY_PATH=$(.venv/bin/python -c 'import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))')
   .venv/bin/python scripts/web.py
   ```

   `LD_LIBRARY_PATH` must be set every time Clipper starts (for systemd: an
   `Environment=LD_LIBRARY_PATH=...` line with the output of the command above). On Windows,
   install CUDA Toolkit 12 and cuDNN 9 from NVIDIA's site. Without these libraries Whisper
   still runs, on the CPU, with a warning.

### AMD / Intel on Linux (VAAPI)

```bash
sudo apt install -y mesa-va-drivers vainfo      # AMD
sudo apt install -y intel-media-va-driver vainfo  # Intel 8th gen and newer (i965-va-driver for older)
sudo usermod -aG render $USER                    # then log out and back in
vainfo | grep -i "H264.*EncSlice"
```

The last command should print `VAProfileH264... : VAEntrypointEncSlice`; if it prints
nothing, the driver offers no H.264 encoding and Clipper will use the CPU.

Whisper on an AMD GPU (optional, advanced): needs ROCm and a ROCm build of CTranslate2 (see
the CTranslate2 documentation). Without it Whisper uses the CPU; rendering still uses the GPU.

### AMD on Windows (AMF)

Update the AMD Adrenalin driver. ffmpeg from `winget install Gyan.FFmpeg` already includes
the `h264_amf` encoder. Whisper uses the CPU.

---

## Opening it from another computer

The web UI has no login, so on purpose it only listens on `127.0.0.1`. To open it from your
laptop, use an SSH tunnel (run it on the laptop and keep that terminal open):

```bash
ssh -N -L 8780:127.0.0.1:8780 user@server-address
```

then open http://127.0.0.1:8780 in the laptop's browser. Through a jump host (when the
server is only reachable from another host):

```bash
ssh -L 8780:127.0.0.1:8780 user@jump-host "ssh -N -L 8780:127.0.0.1:8780 user@server"
```

Don't run it with `--host 0.0.0.0` on an untrusted network: anyone who can reach that port
can use and delete your clips.

## Start automatically on boot (Linux)

Create `/etc/systemd/system/clipper-web.service` (replace `USER` and the paths to match
your install):

```ini
[Unit]
Description=Clipper Studio web UI
After=network-online.target

[Service]
User=USER
WorkingDirectory=/home/USER/clipper
ExecStart=/home/USER/clipper/.venv/bin/python scripts/web.py --host 127.0.0.1 --port 8780
Restart=on-failure
RestartSec=5
Environment=PATH=/home/USER/.deno/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now clipper-web
journalctl -u clipper-web -f      # follow the logs
```

## Using it from an AI client (MCP)

Claude Code, Claude Desktop and Codex can use Clipper as a tool over MCP: the AI picks the
moments and writes the hooks, Clipper cuts the clips and adds subtitles. The full guide is
in [mcp-setup.md](mcp-setup.md) (Indonesian). For a local install, the command is:

```bash
claude mcp add --transport stdio --scope user clipper -- /path/to/clipper/.venv/bin/python /path/to/clipper/scripts/mcp_server.py
```

## Settings

Almost every setting is changed on the web UI's **Pengaturan** (Settings) page (stored in
`work/settings.json`) and applies to the next job without a restart. Priority order:
environment variables > web UI settings > `~/.clipper.toml` > hardware recommendation > defaults.

| Environment variable | Purpose |
|---|---|
| `CLIPPER_WORK` | working folder (source videos, transcripts, clips). Default `work/` in the project folder |
| `CLIPPER_CAMPAIGNS` | campaign brief folder. Default `campaigns/` |
| `GEMINI_API_KEY` | Gemini API key for the automatic moment picker (can also be set in Settings) |
| `CLIPPER_DENO` | Deno location if it is not on PATH or in `~/.deno/bin` |
| `CLIPPER_FACE_MODEL` | face detection model location if not `models/blaze_face_short_range.tflite` |
| `FFMPEG_BIN` | ffmpeg location if not `ffmpeg` on PATH |

## Updating

```bash
cd clipper
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/cek_instalasi.py
```

Then restart the web UI (`sudo systemctl restart clipper-web` if you use systemd). Make
sure no job is running in the Job panel first: a restart stops it. The running version is
shown in the web UI's footer.

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `pip install` fails on mediapipe | Python too new/old. Use 3.11 or 3.12 |
| YouTube download fails / only 360p / no subtitles | Deno not installed, or yt-dlp outdated: `.venv/bin/pip install -U "yt-dlp[default]"` |
| `HTTP Error 429` from YouTube | Temporarily rate-limited by YouTube; Clipper falls back to Whisper for the transcript. Try again later |
| Subtitles use a different font | Lato is not installed (check: `fc-list : family \| grep -i lato`) |
| Clips always use the blurred layout (not following faces) | Face model not downloaded (`cek_instalasi.py --unduh-model`) or `libegl1 libgles2` not installed |
| Whisper transcription is very slow | Normal on CPU, can take well over ten minutes for a 1-hour video. Pick a smaller model in Settings, use a GPU, or use videos that already have subtitles (YouTube) |
| The hardware card says "CPU saja" (CPU only) although there is a GPU | See [GPU & performance](#gpu--performance); run `cek_instalasi.py` for specific advice, then restart the web UI |
| `Address already in use` when opening the tunnel | Port 8780 on the laptop is taken (an old tunnel is still running). Close it or use another port: `-L 8781:127.0.0.1:8780` |
| Web UI looks like the old version after an update | Hard reload (Ctrl+Shift+R) |
