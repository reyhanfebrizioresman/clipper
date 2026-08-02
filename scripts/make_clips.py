"""Dari satu video sumber jadi beberapa klip 9:16 siap unggah.

    python scripts/make_clips.py campaigns/ftm-potrade.json <url-atau-file> --jumlah 5

Hasil di work/<slug>/clips/: file .mp4 + .txt caption berisi hashtag wajib.
Unggah tetap manual (aturan platform) — script ini berhenti di file siap kirim.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from clipper import campaign as camp
from clipper import render, select, source, transcript


def jalankan(cmd: list[str], cwd=None) -> None:
    hasil = subprocess.run(cmd, capture_output=True, cwd=cwd)
    if hasil.returncode != 0:
        raise RuntimeError(f"gagal: {' '.join(cmd[:3])}...\n"
                           f"{hasil.stderr.decode(errors='replace')[-700:]}")


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


def transkrip(video: Path, vtt: Path | None) -> list:
    if vtt:
        print(f"[transkrip] pakai subtitle bawaan: {vtt.name}")
        return transcript.parse(vtt.read_text(encoding="utf-8"))
    print("[transkrip] tidak ada subtitle — jalankan Whisper (butuh beberapa menit)")
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segmen, _ = model.transcribe(str(video), language="id", vad_filter=True)
    return [transcript.Segment(s.start, s.end, s.text.strip()) for s in segmen]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief", help="file JSON brief campaign")
    ap.add_argument("sumber", help="URL video atau path file lokal")
    ap.add_argument("--jumlah", type=int, default=5)
    ap.add_argument("--maks-durasi", type=float, default=60,
                    help="klip pendek lebih disukai algoritma TikTok/Reels (default 60 dtk)")
    ap.add_argument("--keluaran", default="work")
    args = ap.parse_args()

    c = camp.load(args.brief)
    kerja = Path(args.keluaran) / c.slug
    klip_dir = kerja / "clips"
    klip_dir.mkdir(parents=True, exist_ok=True)

    video, vtt = ambil_sumber(args.sumber, kerja / "sumber")
    segmen = transkrip(video, vtt)
    if not segmen:
        raise SystemExit("transkrip kosong — tidak bisa memilih momen")
    print(f"[transkrip] {len(segmen)} segmen, {segmen[-1].end/60:.1f} menit")

    batas_atas = min(c.durasi_maks_s, args.maks_durasi)
    jendela = select.build_windows(segmen, c.durasi_min_s, batas_atas)
    terbaik = select.rank(jendela, c.keywords)[: args.jumlah]
    print(f"[pilih] {len(jendela)} kandidat -> ambil {len(terbaik)} teratas")

    catatan = []
    for n, w in enumerate(terbaik, 1):
        nama = f"{c.slug}-{n:02d}"
        mentah = klip_dir / f"{nama}-raw.mp4"
        srt = klip_dir / f"{nama}.srt"
        final = klip_dir / f"{nama}.mp4"
        print(f"[render] {nama} ({w.end - w.start:.0f} dtk) ...")
        jalankan(render.cut_cmd(video, w.start, w.end, mentah))
        render.write_srt(w, srt)
        # dijalankan dari folder klip: filter subtitles ffmpeg memakai nama file
        # relatif (path absolut butuh escaping yang rapuh)
        jalankan(render.burn_cmd(mentah.resolve(), srt.name, final.resolve()),
                 cwd=klip_dir)
        mentah.unlink(missing_ok=True)

        hook = w.segments[0].text.strip()
        (klip_dir / f"{nama}.txt").write_text(camp.caption(c, hook), encoding="utf-8")
        catatan.append({"file": final.name, "mulai": round(w.start, 1),
                        "durasi": round(w.end - w.start, 1), "hook": hook[:80]})

    (kerja / "clips.json").write_text(json.dumps(catatan, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(f"\nSELESAI: {len(catatan)} klip di {klip_dir}")
    print("Caption ada di file .txt berpasangan — hashtag wajib sudah disertakan.")
    print("Unggah manual ke " + " / ".join(c.platform) + ", lalu submit link ke Clippo.")


if __name__ == "__main__":
    main()
