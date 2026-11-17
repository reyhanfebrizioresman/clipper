# Setup MCP Clipper

Pakai **`clipper-devodo`** untuk mengolah video di server yang sama dengan Clipper
Studio saat ini. Klien AI memilih momen dan menulis hook; Clipper memotong video,
memberi subtitle, dan membuat caption. Unggah hasil ke platform dilakukan manual.

## 1. Pilih server

| Nama MCP | Jalur koneksi dari laptop | Folder proyek | Hubungan dengan web UI di devodo |
| --- | --- | --- | --- |
| `clipper-devodo` | laptop → `reyhan` → `devodo` | `/root/clipper-v2` di devodo | Sumber, klip, campaign, dan pengaturan memakai penyimpanan yang sama secara bawaan. |
| `clipper` | laptop → `reyhan` | `/home/reyhan/clipper-v2` di reyhan | Penyimpanan terpisah; hasilnya tidak otomatis masuk pustaka devodo. |

Keduanya memakai transport **stdio lewat SSH**. Klien memulai proses MCP saat
terhubung; tidak perlu menyalakan HTTP server atau membuat tunnel port untuk cara ini.

## 2. Pastikan SSH siap

Jalankan dari mesin yang akan menjalankan klien AI:

```bash
ssh -F ~/.ssh/config -T -o BatchMode=yes reyhan true
ssh -F ~/.ssh/config -T -o BatchMode=yes reyhan \
  ssh -F /home/reyhan/.ssh/config -T -o BatchMode=yes devodo true
```

Kedua perintah harus selesai tanpa meminta kata sandi. Alias `reyhan` harus ada di
`~/.ssh/config` laptop; alias `devodo` dan kuncinya berada di server `reyhan`.
Untuk koneksi pertama, jalankan SSH secara interaktif dan verifikasi host key bila
diperlukan, lalu ulangi pemeriksaan di atas.

Periksa Python dan entry point di devodo:

```bash
ssh -F ~/.ssh/config -T -o BatchMode=yes reyhan \
  ssh -F /home/reyhan/.ssh/config -T -o BatchMode=yes devodo \
  /root/clipper-v2/.venv/bin/python \
  /root/clipper-v2/scripts/mcp_server.py --help
```

Server yang sudah dipakai Clipper Studio memiliki proyek dan virtualenv ini.
Pada instalasi baru, buat virtualenv di folder proyek dan pasang dependensi dari
`requirements.txt`; pemrosesan video juga memerlukan `ffmpeg`/`ffprobe` di server.

Selalu sertakan `-F` agar SSH memakai config pengguna. Pada lingkungan sandbox yang
dipakai proyek ini, membaca config SSH sistem dapat menghasilkan
`Bad owner or permissions`.

## 3. Codex

Jalankan dari terminal pada mesin tempat Codex dijalankan:

```bash
codex mcp add clipper-devodo -- \
  ssh -F ~/.ssh/config -T \
  -o BatchMode=yes -o ServerAliveInterval=30 reyhan \
  ssh -F /home/reyhan/.ssh/config -T \
  -o BatchMode=yes -o ServerAliveInterval=30 devodo \
  /root/clipper-v2/.venv/bin/python \
  /root/clipper-v2/scripts/mcp_server.py

codex mcp list
```

Alternatif: gabungkan tabel yang diperlukan dari
[`examples/codex-mcp.toml`](examples/codex-mcp.toml) ke `~/.codex/config.toml`.
Contoh mencakup kedua server serta timeout startup 30 detik dan timeout tool 60 detik.
Jangan mengganti seluruh config atau membuat tabel dengan nama yang sudah ada.
Format ini mengikuti [dokumentasi MCP Codex](https://developers.openai.com/codex/mcp).

Di contoh TOML/JSON, `/home/reyhan/.ssh/config` **pertama** adalah path di mesin
klien; sesuaikan jika home pengguna berbeda. Path setelah host `reyhan` adalah path
di server perantara dan tetap mengikuti pengaturan server tersebut. `~` dalam
array argumen bukan ekspansi shell; gunakan path absolut.

Mulai sesi Codex yang memuat konfigurasi baru, lalu periksa `/mcp` pada CLI.
Keberadaan nama di `codex mcp list` menunjukkan konfigurasi terdaftar; lanjutkan
uji tool di bagian 5 untuk memastikan koneksi bekerja.

## 4. Claude Code dan klien JSON

Untuk Claude Code, jalankan:

```bash
claude mcp add --transport stdio --scope user clipper-devodo -- \
  ssh -F ~/.ssh/config -T \
  -o BatchMode=yes -o ServerAliveInterval=30 reyhan \
  ssh -F /home/reyhan/.ssh/config -T \
  -o BatchMode=yes -o ServerAliveInterval=30 devodo \
  /root/clipper-v2/.venv/bin/python \
  /root/clipper-v2/scripts/mcp_server.py

claude mcp get clipper-devodo
```

`--scope user` menyimpan konfigurasi di `~/.claude.json`. Jika nama server sudah
terdaftar, periksa entri yang ada terlebih dahulu; tidak perlu menambah ulang.
Lihat [dokumentasi MCP Claude Code](https://code.claude.com/docs/en/mcp).

Untuk klien yang memakai bentuk `mcpServers` JSON, gabungkan entri yang diperlukan
dari [`examples/mcp-clients.json`](examples/mcp-clients.json) ke konfigurasi MCP
klien tersebut. Pertahankan server lain yang sudah ada. File contoh memakai path
klien Linux; sesuaikan path config SSH dengan mesin tempat klien berjalan.

## 5. Uji koneksi tanpa memproses video

Minta AI secara eksplisit memakai server `clipper-devodo`:

> Pakai MCP clipper-devodo. Panggil get_summary, list_campaigns, dan list_sources.
> Tampilkan ringkasannya tanpa mengambil video atau memulai render.

Server saat panduan ini diverifikasi menyediakan 20 tool. `get_summary` dan
`list_sources` harus melihat data yang sama dengan web UI di devodo, selama
`CLIPPER_WORK` dan `CLIPPER_CAMPAIGNS` tidak diarahkan ke folder lain.

Contoh setelah koneksi terbukti berjalan:

> Pakai clipper-devodo, baca brief campaign yang saya pilih, ambil video dari
> tautan ini, lalu usulkan tiga momen beserta hook. Tampilkan usulannya dahulu.

## 6. Job, pengaturan, dan hasil

- `fetch_source`, `render_clips`, `auto_clips`, dan `rerender_clip` mengembalikan job.
  Bawaan `tunggu_s` adalah 45 detik. Jika status masih `berjalan`, pantau ID yang
  sama lewat `job_status`; jangan memulai pekerjaan yang sama lagi.
- `list_jobs`, `job_status`, dan `cancel_job` hanya melihat job dalam **sesi proses
  MCP tersebut**. Panel Job web UI memakai pengelola job terpisah. Sesi MCP lain
  juga tidak dapat memantau ID job tersebut.
- Menutup koneksi MCP menghentikan proses server beserta job aktifnya. Sumber dan
  klip yang sudah selesai tetap disimpan di disk.
- `get_settings`/`update_settings` memakai pengaturan engine yang sama dengan web
  UI pada server dan folder kerja yang sama. API key Gemini diatur lewat halaman
  Pengaturan web UI; tidak dapat diubah lewat MCP. Mode biasa tidak memerlukan key
  Gemini karena AI di klien yang memilih momen.
- Path hasil dari tool adalah path **di server tujuan**. Klip devodo dapat diunduh
  dari Pustaka klip di web UI; path `/root/...` bukan file lokal laptop.

## 7. Jika koneksi gagal

| Gejala | Yang diperiksa |
| --- | --- |
| `Bad owner or permissions` | Sertakan `-F` untuk config pengguna pada kedua lompatan SSH. |
| `Permission denied (publickey)` | Ulangi dua tes SSH di bagian 2; periksa kunci pada lompatan yang gagal. |
| Host `devodo` tidak ditemukan dari laptop | Gunakan SSH bertingkat melalui `reyhan`, sesuai contoh. |
| Python atau script tidak ditemukan | Periksa path proyek dan `.venv` pada server tujuan. |
| Handshake MCP gagal | Jalankan perintah dengan `--help`; periksa stderr. Banner dari shell tidak boleh mencemari stdout protokol MCP. |
| Tool belum tersedia di klien | Periksa nama/config server, muat ulang sesi klien, lalu ulangi uji tool. |
| Pustaka klip berbeda dengan web UI | Pastikan memilih `clipper-devodo`, serta folder `CLIPPER_WORK` dan `CLIPPER_CAMPAIGNS` sama. |
| Job tidak dikenal | Pantau dari sesi MCP yang memulainya; job web dan sesi MCP lain terpisah. |

## Mode HTTP opsional

Entry point juga mendukung Streamable HTTP:

```bash
.venv/bin/python scripts/mcp_server.py --http --port 8765
```

Endpoint bawaan adalah `http://127.0.0.1:8765/mcp` **pada mesin yang menjalankan
server**. Ini berbeda dari web UI pada port 8780. Untuk akses dari laptop, gunakan
SSH tunnel ke port tersebut. Server HTTP tidak menyediakan autentikasi; pertahankan
bind loopback. Setup stdio di atas tidak memerlukan mode HTTP.

## Verifikasi panduan

Contoh argumen SSH, JSON, dan TOML diuji dengan handshake MCP dan panggilan baca
saja; tidak memulai unduhan atau render. Sintaks CLI Codex diperiksa dengan
`codex mcp add --help`. Rujukan konfigurasi klien ada di bagian 3 dan 4.
