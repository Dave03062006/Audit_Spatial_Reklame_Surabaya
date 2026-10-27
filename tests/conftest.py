import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ORIGINAL_NAME = "reklame_surabaya_outdoor_semua.json"


def contoh_reklame():
    base = {
        "alamat_tidak_lengkap": False, "detail_lokasi": "-", "jenis_izin": "PERMANEN",
        "perlu_cek_manual": None, "media": "BILLBOARD", "letak": "LUAR RUANGAN (OUT DOOR)",
        "penempatan": "-", "tayang_mulai": "2026-01-01", "tayang_selesai": "2027-01-01",
    }
    return [
        {**base, "id": "T-1", "alamat": "KETINTANG BARU NO. 010", "isi_reklame": "IQOS",
         "kategori_materi": "Rokok", "latitude": -7.3111, "longitude": 112.7270},
        {**base, "id": "T-2", "alamat": "MASTRIP NO. 000", "alamat_tidak_lengkap": True,
         "isi_reklame": "INDOMARET", "kategori_materi": "Umum", "latitude": -7.3300, "longitude": 112.7000},
        {**base, "id": "T-3", "alamat": "DARMO NO. 001", "isi_reklame": "BAR BINTANG",
         "kategori_materi": "Umum", "perlu_cek_manual": "BINTANG bisa merek bir",
         "latitude": -7.2900, "longitude": 112.7300},
    ]


@pytest.fixture
def tmp_data_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / ORIGINAL_NAME).write_text(json.dumps({"metadata": {}, "reklame": contoh_reklame()}))
    return d
