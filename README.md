# clipper

Mesin pemotong klip untuk campaign clipping (Clippo/TernakKlip).
Dari satu video panjang jadi beberapa klip 9:16 siap unggah + caption berisi hashtag wajib.

```
python scripts/make_clips.py campaigns/ftm-potrade.json <url-atau-file> --jumlah 5
```

Alur: unduh (yt-dlp) → transkrip (subtitle bawaan, atau Whisper kalau tidak ada)
→ pilih momen (batas kalimat + skor kata kunci brief) → potong 9:16 + subtitle
→ tulis caption.

**Unggah tetap manual.** TikTok/Instagram melarang unggah otomatis; script berhenti
di file siap kirim. Aturan campaign (durasi, hashtag, larangan) ada di `campaigns/*.json`.
