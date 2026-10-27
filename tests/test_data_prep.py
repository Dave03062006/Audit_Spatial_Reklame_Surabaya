import json
import os

import geopandas as gpd
import pytest
from shapely.affinity import translate
from shapely.geometry import Point

import data_prep
from conftest import make_tiny_layers
from data_prep import (OSMDownloadError, build_cache, cache_is_fresh,
                       jenis_sekolah, load_zones, tipe_jalan)
from gis import check_point

from conftest import DX, DY, fake_osm


class CountingFetcher:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return fake_osm()


@pytest.fixture
def reklame_file(tmp_path):
    p = tmp_path / "reklame.json"
    p.write_text(json.dumps({"reklame": []}))
    return p


def test_jenis_sekolah_cases():
    assert jenis_sekolah({"amenity": "kindergarten", "name": "Pelangi"}) == "TK"
    assert jenis_sekolah({"amenity": "school", "name": "SDN Ketintang I"}) == "SD"
    assert jenis_sekolah({"amenity": "school", "name": "SMPN 12 Surabaya"}) == "SMP"
    assert jenis_sekolah({"amenity": "school", "name": "MTs Al-Huda"}) == "SMP"
    assert jenis_sekolah({"amenity": "school", "name": "SMK Negeri 1"}) == "SMA/SMK"
    assert jenis_sekolah({"amenity": "school", "isced:level": "3", "name": "Sekolah X"}) == "SMA/SMK"
    assert jenis_sekolah({"amenity": "school", "name": "PAUD Melati"}) == "TK"
    assert jenis_sekolah({"amenity": "university", "name": "Universitas Ciputra"}) is None
    assert jenis_sekolah({"amenity": "school", "name": "Sekolah Alam"}) == "sekolah (lainnya)"
    assert jenis_sekolah({"amenity": "school", "name": None}) == "sekolah (lainnya)"


def test_tipe_jalan_cases():
    assert tipe_jalan("motorway") == "tol"
    assert tipe_jalan("primary_link") == "jalan utama"
    assert tipe_jalan("trunk") == "jalan utama"
    assert tipe_jalan("tertiary") == "penghubung"
    assert tipe_jalan("residential") == "kecil"
    assert tipe_jalan(["primary", "secondary"]) == "jalan utama"
    assert tipe_jalan("secondary;residential") == "penghubung"
    assert tipe_jalan(None) == "kecil"


def test_build_cache_then_fresh(tmp_path, reklame_file):
    cache = tmp_path / "cache"
    seen = []
    assert not cache_is_fresh(cache, reklame_file)
    build_cache(cache, reklame_file, fetcher=CountingFetcher(), progress=lambda p, m: seen.append(p))
    assert cache_is_fresh(cache, reklame_file)
    assert len(seen) >= 5 and seen == sorted(seen) and seen[-1] == 100
    assert (cache / "layers.gpkg").exists()


def test_reklame_change_makes_stale(tmp_path, reklame_file):
    cache = tmp_path / "cache"
    build_cache(cache, reklame_file, fetcher=CountingFetcher())
    reklame_file.write_text(json.dumps({"reklame": [], "x": 1}))
    os.utime(reklame_file, (1, 1))
    assert not cache_is_fresh(cache, reklame_file)


def test_osm_raw_reused(tmp_path, reklame_file):
    cache = tmp_path / "cache"
    build_cache(cache, reklame_file, fetcher=CountingFetcher())
    f2 = CountingFetcher()
    build_cache(cache, reklame_file, fetcher=f2)
    assert f2.calls == 0
    build_cache(cache, reklame_file, fetcher=f2, refresh_osm=True)
    assert f2.calls == 1


def test_fetch_failure_names_layer(tmp_path, reklame_file):
    def broken():
        raise OSMDownloadError("jalan")
    with pytest.raises(OSMDownloadError) as e:
        build_cache(tmp_path / "cache", reklame_file, fetcher=broken)
    assert e.value.layer == "jalan"


def test_fetch_osm_wraps_errors(monkeypatch):
    def boom(*a, **k):
        raise ConnectionError("no network")
    monkeypatch.setattr(data_prep.ox, "features_from_place", boom)
    with pytest.raises(OSMDownloadError) as e:
        data_prep.fetch_osm()
    assert e.value.layer == "fasilitas"


def test_load_zones_roundtrip(tmp_path, reklame_file):
    cache = tmp_path / "cache"
    build_cache(cache, reklame_file, fetcher=CountingFetcher())
    zones = load_zones(cache)
    assert set(zones.jalan["tipe_jalan"]) == {"jalan utama", "kecil"}
    assert set(zones.fasilitas["jenis"]) == {"SD", "sekolah (lainnya)"}
    near = Point(1300 + DX, 1000 + DY)
    on_road = Point(5000 + DX, 3010 + DY)
    far = Point(7000 + DX, 7000 + DY)
    assert check_point(near, "Rokok", zones) == ["449_1_d"]
    assert check_point(on_road, "Rokok", zones) == ["449_1_c"]
    assert check_point(far, "Rokok", zones) == []
    assert zones.area_boleh.contains(far)
