import numpy as np

from clipper import reframe


def test_nms_merges_overlap_duplicate_keeps_best_score():
    a = (100, 50, 40, 40, 0.9)
    a_dup = (104, 52, 38, 40, 0.7)        # wajah yang sama, tertangkap di petak sebelah
    b = (400, 60, 40, 40, 0.8)            # orang kedua
    hasil = reframe.gabung_deteksi([a_dup, b, a])
    assert hasil == [a, b]


def test_deteksi_petak_shifts_tile_coordinates_and_dedupes():
    frame = np.zeros((720, 1280, 3), np.uint8)
    dipanggil = []

    def palsu(rgb):
        # petak memberi wajah di x=10 (koordinat lokal petak); petak tengah-kanan mulai x=560
        dipanggil.append(rgb.shape[1])
        return [(10, 100, 40, 40, 0.9)]

    petak = ((0.0, 0.5), (0.4375, 1.0))
    hasil = reframe.deteksi_petak(palsu, frame, petak)
    assert dipanggil == [640, 720]
    xs = sorted(k[0] for k in hasil)
    assert xs == [10, 560 + 10]                # digeser ke koordinat frame, tidak digabung


def test_deteksi_petak_full_and_tile_see_same_face_counts_once():
    frame = np.zeros((720, 1280, 3), np.uint8)

    def palsu(rgb):
        lebar = rgb.shape[1]
        # frame utuh melihat wajah di x=300; petak kiri (lebar 720) melihatnya di tempat sama
        return [(300, 100, 60, 60, 0.6 if lebar == 1280 else 0.8)] if lebar in (1280, 720) else []

    hasil = reframe.deteksi_petak(palsu, frame, ((0.0, 1.0), (0.0, 0.5625)))
    assert len(hasil) == 1 and hasil[0][4] == 0.8
