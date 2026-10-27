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


# geser lapisan buatan ke sekitar Surabaya (UTM 49S) supaya bisa diubah ke lat/lon dengan wajar
DX, DY = 690000, 9190000


def fake_osm():
    import geopandas as gpd
    from shapely.affinity import translate

    fas, jalan, batas = make_tiny_layers()
    fas = fas.copy()
    fas["geometry"] = fas.geometry.translate(DX, DY)
    fas["amenity"] = ["school", "school"]
    fas = fas.drop(columns=["jenis"]).to_crs("EPSG:4326")
    jalan = jalan.copy()
    jalan["geometry"] = jalan.geometry.translate(DX, DY)
    jalan["highway"] = ["primary", ["residential", "service"]]
    jalan = jalan.drop(columns=["tipe_jalan"]).to_crs("EPSG:4326")
    batas = gpd.GeoDataFrame(geometry=[translate(batas, DX, DY)], crs="EPSG:32749").to_crs("EPSG:4326")
    return {"fasilitas": fas, "jalan": jalan, "batas": batas}


def utm_to_latlon(x, y):
    import geopandas as gpd
    from shapely.geometry import Point
    p = gpd.GeoSeries([Point(x, y)], crs="EPSG:32749").to_crs("EPSG:4326").iloc[0]
    return p.y, p.x


def app_reklame_rows():
    """Reklame contoh di dalam area lapisan buatan (koordinat lokal + DX/DY)."""
    spec = [
        ("T-near", 1300, 1000, "Rokok", "KETINTANG BARU NO. 010 BLOK.", None, "2027-01-01"),
        ("T-road", 5000, 3010, "Rokok elektronik", "JEMURSARI NO. 001", None, "2027-01-01"),
        ("T-far", 7000, 7000, "Rokok", "MASTRIP NO. 020", None, "2027-01-01"),
        ("T-umum", 3000, 2000, "Umum", "KETINTANG MADYA NO. 003", None, "2027-01-01"),
        ("T-cek", 3500, 2500, "Umum", "DARMO NO. 001", "BINTANG bisa merek bir", "2027-01-01"),
        ("T-old", 7200, 7200, "Rokok", "MASTRIP NO. 030", None, "2026-01-01"),
    ]
    rows = []
    for id, x, y, k, alamat, cek, selesai in spec:
        lat, lon = utm_to_latlon(x + DX, y + DY)
        rows.append({"id": id, "alamat": alamat, "alamat_tidak_lengkap": id == "T-far",
                     "detail_lokasi": "-", "jenis_izin": "PERMANEN", "isi_reklame": f"ISI {id}",
                     "kategori_materi": k, "perlu_cek_manual": cek, "media": "BILLBOARD",
                     "letak": "LUAR RUANGAN (OUT DOOR)", "penempatan": "-",
                     "tayang_mulai": "2026-01-01", "tayang_selesai": selesai,
                     "latitude": lat, "longitude": lon})
    return rows


@pytest.fixture
def app_base(tmp_path):
    """Folder aplikasi lengkap: data/ + cache/ yang sudah dibangun dari lapisan buatan."""
    from data_prep import build_cache
    base = tmp_path / "app"
    (base / "data").mkdir(parents=True)
    reklame_path = base / "data" / ORIGINAL_NAME
    reklame_path.write_text(json.dumps({"metadata": {}, "reklame": app_reklame_rows()}))
    build_cache(base / "cache", reklame_path, fetcher=fake_osm)
    return base


@pytest.fixture
def app_with_admin(app_base):
    from storage import Store
    Store(app_base / "data").create_user("dave", "rahasia123")
    return app_base


def make_app(base, **kw):
    from datetime import date
    from app import App
    kw.setdefault("today", date(2026, 10, 27))
    kw.setdefault("headless", True)
    return App(base, **kw)


def click_events(pos):
    import pygame
    return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}),
            pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": 1})]


def type_events(s):
    import pygame
    return [pygame.event.Event(pygame.TEXTINPUT, {"text": ch}) for ch in s]
