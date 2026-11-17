# Instalasi Clipper

*Bahasa Indonesia · [English](installation.md)*

Panduan memasang Clipper di komputer atau server sendiri, dari nol sampai web UI
**Clipper Studio** terbuka di browser.

> **Pasang di mana?** Semua pemrosesan (unduh, transkrip, render) berjalan di mesin
> tempat Clipper dipasang. Komputer yang hanya *membuka* web UI atau memakai klien AI
> (MCP) tidak butuh apa pun selain browser/SSH. Pasang di mesin yang paling kuat.

Ringkasnya, tiap OS sama urutannya:

1. Pasang program sistem: **Python 3.11/3.12, ffmpeg, Deno, git, font Lato**.
2. Ambil kode, buat virtualenv, `pip install -r requirements.txt`.
3. Jalankan `scripts/cek_instalasi.py --unduh-model`: memeriksa semuanya dan mengunduh
   model deteksi wajah.
4. Jalankan `scripts/web.py`, buka http://127.0.0.1:8780.

| Sistem | Status |
|---|---|
| Debian 12 / Ubuntu 24.04 (x86_64) | Dipakai sehari-hari, teruji |
| macOS Apple Silicon (M1 ke atas) | Didukung, belum diuji di mesin sungguhan |
| Windows 10/11 | Seharusnya jalan, belum diuji; alternatif: WSL2 + langkah Linux |

Kebutuhan minimum: 2 core, 4 GB RAM, ±3 GB untuk program + model, dan ruang untuk video
(video 1080p sekitar 1 GB per jam). Disarankan 6 core / 8 GB RAM atau lebih. Clipper
menyesuaikan setelan awal dengan mesinnya sendiri (lihat [GPU & performa](#gpu--performa)).

---

## Linux (Debian / Ubuntu)

### 1. Program sistem

```bash
sudo apt update
sudo apt install -y git python3 python3-venv ffmpeg fonts-lato fontconfig libegl1 libgles2
curl -fsSL https://deno.land/install.sh | sh
```

- `libegl1 libgles2` dibutuhkan MediaPipe (deteksi wajah), terutama di server tanpa layar.
- Deno dipasang di `~/.deno/bin/deno`; Clipper menemukannya di situ walau tidak ada di PATH.
- Python harus **3.11 atau 3.12**. Cek dengan `python3 --version`. Ubuntu 22.04 masih
  membawa 3.10, jadi pasang 3.12 dulu:

  ```bash
  sudo add-apt-repository -y ppa:deadsnakes/ppa
  sudo apt install -y python3.12 python3.12-venv
  ```

  lalu pakai `python3.12` menggantikan `python3` di langkah berikutnya.

### 2. Kode & dependensi Python

```bash
git clone https://github.com/reyhanfebrizioresman/clipper.git
cd clipper
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

Folder `.venv` jadi sekitar 1,2 GB. Model Whisper diunduh otomatis saat pertama kali
dipakai (model `small` sekitar 500 MB), hanya untuk video yang tidak punya subtitle.

### 3. Periksa & unduh model

```bash
.venv/bin/python scripts/cek_instalasi.py --unduh-model
```

Semua baris harus `[ OK ]`. Baris `[GAGAL]` wajib diperbaiki (sarannya tercetak di
bawahnya); `[PERINGATAN]` boleh diabaikan bila fiturnya tidak dipakai.

### 4. Jalankan

```bash
.venv/bin/python scripts/web.py
```

Buka http://127.0.0.1:8780. Lanjut ke [Membuka dari komputer lain](#membuka-dari-komputer-lain)
bila Clipper dipasang di server, dan [Jalan otomatis saat boot](#jalan-otomatis-saat-boot-linux)
supaya tidak perlu menyalakan manual.

---

## macOS (Apple Silicon)

### 1. Program sistem

Pasang [Homebrew](https://brew.sh) bila belum ada, lalu:

```bash
brew install python@3.12 ffmpeg deno git
brew install --cask font-lato
```

ffmpeg dari Homebrew sudah membawa libass (subtitle) dan VideoToolbox (encoder GPU Apple).

### 2. Kode & dependensi Python

```bash
git clone https://github.com/reyhanfebrizioresman/clipper.git
cd clipper
python3.12 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
```

Di Mac Apple Silicon, `requirements.txt` ikut memasang `mlx-whisper`, sehingga transkrip
Whisper berjalan di GPU Apple. Di Mac Intel paket itu dilewati dan Whisper memakai CPU.

### 3–4. Periksa & jalankan

```bash
.venv/bin/python scripts/cek_instalasi.py --unduh-model
.venv/bin/python scripts/web.py
```

Buka http://127.0.0.1:8780.

---

## Windows 10/11

> Belum diuji di Windows. Kalau ada langkah yang gagal, cara paling aman adalah
> [WSL2](https://learn.microsoft.com/windows/wsl/install) (`wsl --install -d Ubuntu-24.04`)
> lalu ikuti langkah **Linux** di dalam Ubuntu tersebut. Laporkan masalahnya di GitHub.

### 1. Program sistem

Buka **PowerShell**, lalu:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Gyan.FFmpeg
winget install -e --id DenoLand.Deno
winget install -e --id Git.Git
```

Tutup lalu buka lagi PowerShell supaya PATH yang baru terbaca. Font Lato: unduh dari
[Google Fonts](https://fonts.google.com/specimen/Lato), ekstrak, klik kanan semua file
`.ttf` → **Install for all users**.

### 2. Kode & dependensi Python

```powershell
git clone https://github.com/reyhanfebrizioresman/clipper.git
cd clipper
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -U pip
.venv\Scripts\python -m pip install -r requirements.txt
```

### 3–4. Periksa & jalankan

```powershell
.venv\Scripts\python scripts\cek_instalasi.py --unduh-model
.venv\Scripts\python scripts\web.py
```

Buka http://127.0.0.1:8780. Bila Windows Firewall bertanya, akses jaringan tidak perlu
diizinkan: web UI hanya mendengarkan komputer itu sendiri.

---

## GPU & performa

Tidak ada yang perlu diatur untuk mulai: saat server menyala Clipper mendeteksi CPU, RAM,
dan GPU, lalu memilih setelan awal yang cocok. Hasilnya terlihat di **Pengaturan →
Perangkat server** dan di bagian akhir `cek_instalasi.py`.

| GPU | Render video | Transkrip Whisper | Yang perlu dipasang |
|---|---|---|---|
| Tidak ada / tidak didukung | CPU (libx264) | CPU | — |
| NVIDIA | NVENC | CUDA | driver NVIDIA (+ library CUDA untuk Whisper, lihat di bawah) |
| Apple Silicon | VideoToolbox | MLX | sudah otomatis lewat Homebrew + `requirements.txt` |
| AMD di Linux | VAAPI | CPU (GPU bila CTranslate2 build ROCm) | `mesa-va-drivers` |
| Intel di Linux | VAAPI | CPU | `intel-media-va-driver` |
| AMD di Windows | AMF | CPU | driver AMD Adrenalin terbaru |

Encoder GPU hanya dipakai bila **lolos uji encode sungguhan** saat server mulai, dan bila
gagal di tengah job Clipper pindah ke CPU dengan peringatan di panel Job. Jadi memasang
langkah GPU di bawah tidak akan merusak apa pun; paling buruk Clipper tetap memakai CPU.
Setelah memasang driver/library GPU, **jalankan ulang** web UI supaya deteksi diulang.

Pilihan otomatis bisa ditimpa di **Pengaturan → Perangkat** (Whisper: CPU/CUDA/MLX;
encoder: CPU/NVENC/VideoToolbox/AMF/VAAPI).

### NVIDIA

1. Pasang driver NVIDIA resmi; `nvidia-smi` harus menampilkan GPU-nya. Render (NVENC)
   langsung jalan dengan ffmpeg dari apt/winget.
2. Untuk Whisper di GPU, faster-whisper butuh cuBLAS (CUDA 12) dan cuDNN 9. Cara termudah
   di Linux, dari folder `clipper`:

   ```bash
   .venv/bin/pip install nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
   export LD_LIBRARY_PATH=$(.venv/bin/python -c 'import os, nvidia.cublas.lib, nvidia.cudnn.lib; print(os.path.dirname(nvidia.cublas.lib.__file__) + ":" + os.path.dirname(nvidia.cudnn.lib.__file__))')
   .venv/bin/python scripts/web.py
   ```

   `LD_LIBRARY_PATH` harus diset setiap kali menjalankan Clipper (untuk systemd: baris
   `Environment=LD_LIBRARY_PATH=...` berisi hasil perintah di atas). Di Windows, pasang
   CUDA Toolkit 12 dan cuDNN 9 dari situs NVIDIA. Bila library ini tidak ada, Whisper
   tetap jalan di CPU dengan peringatan.

### AMD / Intel di Linux (VAAPI)

```bash
sudo apt install -y mesa-va-drivers vainfo      # AMD
sudo apt install -y intel-media-va-driver vainfo  # Intel generasi 8 ke atas (i965-va-driver untuk yang lama)
sudo usermod -aG render $USER                    # lalu logout/login
vainfo | grep -i "H264.*EncSlice"
```

Baris terakhir harus menampilkan `VAProfileH264... : VAEntrypointEncSlice`; kalau kosong,
driver tidak menyediakan encode H.264 dan Clipper akan memakai CPU.

Whisper di GPU AMD (opsional, lanjutan): butuh ROCm dan CTranslate2 versi ROCm (lihat
dokumentasi CTranslate2). Tanpa itu Whisper memakai CPU; render tetap memakai GPU.

### AMD di Windows (AMF)

Perbarui driver AMD Adrenalin. ffmpeg dari `winget install Gyan.FFmpeg` sudah membawa
encoder `h264_amf`. Whisper memakai CPU.

---

## Membuka dari komputer lain

Web UI tidak punya login, jadi sengaja hanya mendengarkan `127.0.0.1`. Untuk membukanya
dari laptop, pakai SSH tunnel (jalankan di laptop, biarkan terminalnya terbuka):

```bash
ssh -N -L 8780:127.0.0.1:8780 user@alamat-server
```

lalu buka http://127.0.0.1:8780 di browser laptop. Lewat host perantara (server hanya
bisa dicapai dari host lain):

```bash
ssh -L 8780:127.0.0.1:8780 user@perantara "ssh -N -L 8780:127.0.0.1:8780 user@server"
```

Jangan menjalankan `--host 0.0.0.0` di jaringan yang tidak dipercaya: siapa pun yang bisa
menjangkau port itu bisa memakai dan menghapus klip.

## Jalan otomatis saat boot (Linux)

Buat `/etc/systemd/system/clipper-web.service` (ganti `USER` dan path sesuai instalasimu):

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
journalctl -u clipper-web -f      # lihat log
```

## Memakai lewat klien AI (MCP)

Claude Code, Claude Desktop, dan Codex bisa memakai Clipper sebagai tool lewat MCP:
AI-nya yang memilih momen dan menulis hook, Clipper yang memotong dan memberi subtitle.
Panduan lengkapnya ada di [mcp-setup.md](mcp-setup.md). Untuk instalasi lokal, perintahnya:

```bash
claude mcp add --transport stdio --scope user clipper -- /path/ke/clipper/.venv/bin/python /path/ke/clipper/scripts/mcp_server.py
```

## Pengaturan

Hampir semua setelan diatur dari halaman **Pengaturan** web UI (tersimpan di
`work/settings.json`) dan berlaku untuk job berikutnya tanpa restart. Urutan prioritas:
variabel lingkungan > Pengaturan web UI > `~/.clipper.toml` > rekomendasi perangkat > bawaan.

| Variabel lingkungan | Fungsi |
|---|---|
| `CLIPPER_WORK` | folder kerja (video sumber, transkrip, klip). Bawaan `work/` di folder proyek |
| `CLIPPER_CAMPAIGNS` | folder brief campaign. Bawaan `campaigns/` |
| `GEMINI_API_KEY` | API key Gemini untuk pemilih momen otomatis (bisa juga diisi di Pengaturan) |
| `CLIPPER_DENO` | lokasi Deno bila tidak di PATH atau `~/.deno/bin` |
| `CLIPPER_FACE_MODEL` | lokasi model deteksi wajah bila bukan `models/blaze_face_short_range.tflite` |
| `FFMPEG_BIN` | lokasi ffmpeg bila bukan `ffmpeg` di PATH |

## Memperbarui

```bash
cd clipper
git pull
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/cek_instalasi.py
```

Lalu jalankan ulang web UI (`sudo systemctl restart clipper-web` bila memakai systemd).
Pastikan tidak ada job yang sedang berjalan di panel Job: restart menghentikannya.
Versi yang sedang berjalan terlihat di kaki halaman web UI.

## Masalah umum

| Gejala | Penyebab & solusi |
|---|---|
| `pip install` gagal di mediapipe | Python terlalu baru/lama. Pakai 3.11 atau 3.12 |
| Unduhan YouTube gagal / hanya 360p / subtitle tidak terambil | Deno belum terpasang, atau yt-dlp kedaluwarsa: `.venv/bin/pip install -U "yt-dlp[default]"` |
| `HTTP Error 429` dari YouTube | Dibatasi YouTube sementara; Clipper otomatis memakai Whisper untuk transkrip. Coba lagi nanti |
| Subtitle memakai font lain | Font Lato belum terpasang (cek: `fc-list : family \| grep -i lato`) |
| Klip selalu bergaya blur (tidak mengikuti wajah) | Model wajah belum diunduh (`cek_instalasi.py --unduh-model`) atau `libegl1 libgles2` belum terpasang |
| Transkrip Whisper sangat lama | Normal di CPU, bisa belasan menit untuk video 1 jam. Pilih model lebih kecil di Pengaturan, pakai GPU, atau pakai video yang sudah punya subtitle (YouTube) |
| Kartu Perangkat bilang "CPU saja" padahal ada GPU | Lihat bagian [GPU & performa](#gpu--performa); jalankan `cek_instalasi.py` untuk saran spesifik, lalu restart web UI |
| `Address already in use` saat membuat tunnel | Port 8780 di laptop sudah dipakai (tunnel lama masih jalan). Tutup yang lama atau pakai port lain: `-L 8781:127.0.0.1:8780` |
| Halaman web UI tampak versi lama setelah update | Muat ulang paksa (Ctrl+Shift+R) |
