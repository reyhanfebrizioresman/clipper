import pytest

from clipper import hardware

# Mesin "standar" untuk semua tes: hasil tidak bergantung pada CPU/GPU mesin penguji,
# dan tes tidak menjalankan nvidia-smi / ffmpeg sungguhan. Rekomendasinya = bawaan lama.
STANDAR = hardware.Hardware(cpu=6, ram_gb=16.0)


@pytest.fixture(autouse=True)
def _perangkat_standar(monkeypatch):
    monkeypatch.setattr(hardware, "terdeteksi", lambda: STANDAR)
