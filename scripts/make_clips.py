"""Dari satu video sumber jadi beberapa klip 9:16 siap unggah.

    python scripts/make_clips.py campaigns/ftm-potrade.json <url-atau-file> --jumlah 5

Hasil di work/<slug>/clips/: file .mp4 + .txt caption berisi hashtag wajib.
Unggah tetap manual (aturan platform) — script ini berhenti di file siap kirim.
"""
import argparse
import json
from dataclasses import replace
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import campaign as camp
from clipper import pipeline, source
from clipper import hardware
from clipper.config import load_settings
from clipper.styles import STYLES, semua_gaya
from clipper.pipeline import run_subprocess as jalankan


def ambil_sumber(target: str, kerja: Path, settings) -> tuple[Path, Path | None]:
    """Kembalikan (video, subtitle-vtt-atau-None)."""
    lokal = Path(target)
    if lokal.exists():
        teks = sorted(lokal.parent.glob(lokal.stem + "*.vtt")) + \
               sorted(lokal.parent.glob(lokal.stem + "*.srt"))
        return lokal, (teks[0] if teks else None)
    kerja.mkdir(parents=True, exist_ok=True)
    print(f"[unduh] {target}")
    jalankan(source.download_cmd(target, kerja, tinggi=settings.tinggi_unduh))
    # subtitle boleh gagal (YouTube sering balas 429) — Whisper jadi cadangan
    try:
        jalankan(source.subtitle_cmd(target, kerja, bahasa=settings.bahasa_subtitle))
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
    ap.add_argument("--maks-durasi", type=float, default=None,
                    help="default dari Pengaturan (umumnya 60 dtk, disukai TikTok/Reels)")
    ap.add_argument("--ai", choices=["keyword", "gemini"], default=None,
                    help="pemilih momen (default: dari Pengaturan / env, else keyword)")
    ap.add_argument("--keluaran", default="work")
    args = ap.parse_args()

    # setelan yang sama dengan web UI & MCP: <keluaran>/settings.json
    hw = hardware.terdeteksi()
    settings = load_settings(json_path=Path(args.keluaran) / "settings.json",
                             rekomendasi=hardware.rekomendasi(hw))
    settings = replace(settings, encoder=hardware.encoder_efektif(settings.encoder, hw))
    if args.ai:
        settings = replace(settings, ai_provider=args.ai)
    c = camp.load(args.brief)
    kerja = Path(args.keluaran) / c.slug
    klip_dir = kerja / "clips"
    klip_dir.mkdir(parents=True, exist_ok=True)

    video, vtt = ambil_sumber(args.sumber, kerja / "sumber", settings)
    print(f"[transkrip] {'subtitle bawaan: ' + vtt.name if vtt else 'tidak ada subtitle — Whisper (butuh beberapa menit)'}")
    segmen = pipeline.transcribe(video, vtt, whisper_model=settings.whisper_model,
                                 language=settings.bahasa,
                                 perangkat=hardware.whisper_efektif(settings.perangkat_whisper, hw))
    if not segmen:
        raise SystemExit("transkrip kosong — tidak bisa memilih momen")
    print(f"[transkrip] {len(segmen)} segmen, {segmen[-1].end/60:.1f} menit")

    def lapor(tahap: str, info: dict) -> None:
        if tahap == "pilih" and "dipilih" in info:
            print(f"[pilih] ambil {info['dipilih']} "
                  f"(peringkat {info['dari']}-{info['sampai']})")
        elif tahap == "peringatan":
            print(f"[peringatan] {info.get('pesan')}")
        elif tahap == "render":
            print(f"[render] {info['nama']} ({info['durasi']:.0f} dtk) ...")

    hasil = pipeline.process(c, video, segmen, klip_dir, jumlah=args.jumlah,
                             lewati=args.lewati, maks_durasi=args.maks_durasi or settings.maks_durasi,
                             chooser=pipeline.make_chooser(settings),
                             reframe_planner=pipeline.make_reframe_planner(settings),
                             style=semua_gaya(settings.gaya_kustom).get(settings.subtitle_style,
                                                                        STYLES["lato"]),
                             settings=settings,
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
