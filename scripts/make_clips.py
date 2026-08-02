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


def jalankan(cmd: list[str]) -> None:
    hasil = subprocess.run(cmd, capture_output=True)
    if hasil.returncode != 0:
        raise RuntimeError(f"gagal: {' '.join(cmd[:3])}...\n"
                           f"{hasil.stderr.decode(errors='replace')[-700:]}")


def ambil_sumber(target: str, kerja: Path) -> tuple[Path, Path | None]:
    """Kembalikan (video, subtitle-vtt-atau-None)."""
    lokal = Path(target)
    if lokal.exists():
        vtt = next(iter(lokal.parent.glob(lokal.stem + "*.vtt")), None)
        return lokal, vtt
    kerja.mkdir(parents=True, exist_ok=True)
    print(f"[unduh] {target}")
    jalankan(source.download_cmd(target, kerja))
    video = max(kerja.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
    return video, next(iter(kerja.glob(video.stem + "*.vtt")), None)


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

    jendela = select.build_windows(segmen, c.durasi_min_s, min(c.durasi_maks_s, 90))
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
        jalankan(render.burn_cmd(mentah.resolve(), srt.name, final.resolve()))
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
