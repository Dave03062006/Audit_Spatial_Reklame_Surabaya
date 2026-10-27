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


def make_tiny_layers(school_a_xy=(1000, 1000)):
    """Lapisan buatan dalam meter (EPSG:32749), seperti koordinat buatan di notebook."""
    import geopandas as gpd
    from shapely.geometry import LineString, Point, box

    ax, ay = school_a_xy
    # Layer 1 (Fasilitas)
    fasilitas = gpd.GeoDataFrame(
        {"name": ["SDN Contoh", None], "jenis": ["SD", "SMP"]},
        geometry=[box(ax, ay, ax + 20, ay + 20), Point(5000, 5000)], crs="EPSG:32749")
    # Layer 3 (Jalan)
    jalan = gpd.GeoDataFrame(
        {"name": ["Jalan Utama Contoh", "Gang Contoh"], "tipe_jalan": ["jalan utama", "kecil"]},
        geometry=[LineString([(0, 3000), (6000, 3000)]), LineString([(0, 4000), (6000, 4000)])],
        crs="EPSG:32749")
    batas = box(0, 0, 8000, 8000)
    return fasilitas, jalan, batas


@pytest.fixture
def tiny_layers():
    return make_tiny_layers()


@pytest.fixture
def tiny_zones(tiny_layers):
    from gis import Zones
    return Zones.build(*tiny_layers)
