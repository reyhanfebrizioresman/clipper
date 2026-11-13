"""Dari satu video sumber jadi beberapa klip 9:16 siap unggah.

    python scripts/make_clips.py campaigns/ftm-potrade.json <url-atau-file> --jumlah 5

Hasil di work/<slug>/clips/: file .mp4 + .txt caption berisi hashtag wajib.
Unggah tetap manual (aturan platform) — script ini berhenti di file siap kirim.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import campaign as camp
from clipper import pipeline, source
from clipper.pipeline import run_subprocess as jalankan


def ambil_sumber(target: str, kerja: Path) -> tuple[Path, Path | None]:
    """Kembalikan (video, subtitle-vtt-atau-None)."""
    lokal = Path(target)
    if lokal.exists():
        teks = sorted(lokal.parent.glob(lokal.stem + "*.vtt")) + \
               sorted(lokal.parent.glob(lokal.stem + "*.srt"))
        return lokal, (teks[0] if teks else None)
    kerja.mkdir(parents=True, exist_ok=True)
    print(f"[unduh] {target}")
    jalankan(source.download_cmd(target, kerja))
    # subtitle boleh gagal (YouTube sering balas 429) — Whisper jadi cadangan
    try:
        jalankan(source.subtitle_cmd(target, kerja))
    except RuntimeError as e:
        print(f"[unduh] subtitle tidak dapat diambil ({str(e)[:80]}...)")
    video = max(kerja.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    teks = sorted(kerja.glob(video.stem + "*.vtt")) + sorted(kerja.glob(video.stem + "*.srt"))
    return video, (teks[0] if teks else None)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief", help="file JSON brief campaign")
    ap.add_argument("sumber", help="URL video atau path file lokal")
    ap.add_argument("--jumlah", type=int, default=5)
    ap.add_argument("--lewati", type=int, default=0,
                    help="lewati N kandidat teratas (untuk membuat batch lanjutan)")
    ap.add_argument("--maks-durasi", type=float, default=60,
                    help="klip pendek lebih disukai algoritma TikTok/Reels (default 60 dtk)")
    ap.add_argument("--keluaran", default="work")
    args = ap.parse_args()

    c = camp.load(args.brief)
    kerja = Path(args.keluaran) / c.slug
    klip_dir = kerja / "clips"
    klip_dir.mkdir(parents=True, exist_ok=True)

    video, vtt = ambil_sumber(args.sumber, kerja / "sumber")
    print(f"[transkrip] {'subtitle bawaan: ' + vtt.name if vtt else 'tidak ada subtitle — Whisper (butuh beberapa menit)'}")
    segmen = pipeline.transcribe(video, vtt)
    if not segmen:
        raise SystemExit("transkrip kosong — tidak bisa memilih momen")
    print(f"[transkrip] {len(segmen)} segmen, {segmen[-1].end/60:.1f} menit")

    def lapor(tahap: str, info: dict) -> None:
        if tahap == "pilih" and "dipilih" in info:
            print(f"[pilih] ambil {info['dipilih']} "
                  f"(peringkat {info['dari']}-{info['sampai']})")
        elif tahap == "render":
            print(f"[render] {info['nama']} ({info['durasi']:.0f} dtk) ...")

    hasil = pipeline.process(c, video, segmen, klip_dir, jumlah=args.jumlah,
                             lewati=args.lewati, maks_durasi=args.maks_durasi,
                             on_progress=lapor)
    catatan = [{"file": r.file, "mulai": r.mulai, "durasi": r.durasi, "hook": r.hook}
               for r in hasil]

    (kerja / "clips.json").write_text(json.dumps(catatan, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"\nSELESAI: {len(catatan)} klip di {klip_dir}")
    print("Caption ada di file .txt berpasangan — hashtag wajib sudah disertakan.")
    print("Unggah manual ke " + " / ".join(c.platform) + ", lalu submit link ke Clippo.")


if __name__ == "__main__":
    main()
