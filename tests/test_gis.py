from datetime import date

import geopandas as gpd
import pytest
from shapely.geometry import Point

from conftest import make_tiny_layers
from gis import (Zones, alasan_text, audit_all, check_point, load_reklame,
                 nearest_info, normalize_kategori, status_of)

TODAY = date(2026, 10, 27)


def test_rokok_inside_500m_violates_d(tiny_zones):
    assert check_point(Point(1300, 1000), "Rokok", tiny_zones) == ["449_1_d"]


def test_rokok_outside_patuh(tiny_zones):
    assert check_point(Point(7000, 7000), "Rokok", tiny_zones) == []


def test_exactly_500m_counts(tiny_zones):
    # sisi kanan sekolah A ada di x=1020, jadi x=1520 tepat 500 m
    assert "449_1_d" in check_point(Point(1520, 1010), "Rokok elektronik", tiny_zones)


def test_on_main_road_violates_c(tiny_zones):
    assert check_point(Point(5000, 3010), "Rokok", tiny_zones) == ["449_1_c"]


def test_kecil_road_not_corridor(tiny_zones):
    assert check_point(Point(5000, 4005), "Rokok", tiny_zones) == []


def test_both_rules():
    zones = Zones.build(*make_tiny_layers(school_a_xy=(1000, 2700)))
    assert check_point(Point(1000, 3000), "Rokok", zones) == ["449_1_d", "449_1_c"]


def test_alkohol_anywhere(tiny_zones):
    assert check_point(Point(7000, 7000), "Minuman beralkohol", tiny_zones) == ["perda_5_2019_23"]


def test_umum_not_checked(tiny_zones):
    assert check_point(Point(1300, 1000), "Umum", tiny_zones) == []


def row(**kw):
    base = {"kategori_materi": "Rokok", "perlu_cek_manual": None,
            "kategori_dikonfirmasi": False, "tayang_selesai": "2027-01-01"}
    return {**base, **kw}


def test_umum_tidak_diaudit():
    assert status_of(row(kategori_materi="Umum"), [], TODAY) == "Tidak diaudit"


def test_perlu_cek_precedence():
    r = row(kategori_materi="Umum", perlu_cek_manual="BINTANG bisa bir")
    assert status_of(r, [], TODAY) == "Perlu cek"
    r["kategori_dikonfirmasi"] = True
    assert status_of(r, [], TODAY) == "Tidak diaudit"


def test_expired_tayang_berakhir():
    assert status_of(row(tayang_selesai="2026-10-26"), ["449_1_d"], TODAY) == "Tayang berakhir"


def test_status_missing_tayang_is_not_expired():
    assert status_of(row(tayang_selesai=None), ["449_1_d"], TODAY) == "Melanggar"
    assert status_of(row(tayang_selesai="-"), [], TODAY) == "Patuh"


def test_area_boleh_excludes_zones_and_corridor(tiny_zones):
    assert not tiny_zones.area_boleh.contains(Point(1300, 1000))
    assert not tiny_zones.area_boleh.contains(Point(5000, 3010))
    assert tiny_zones.area_boleh.contains(Point(7000, 7000))


def to_lonlat(x, y):
    p = gpd.GeoSeries([Point(x, y)], crs="EPSG:32749").to_crs("EPSG:4326").iloc[0]
    return p.y, p.x


def test_load_reklame_skips_bad_rows(capsys):
    lat, lon = to_lonlat(1300, 1000)
    recs = [
        {"id": "a", "latitude": lat, "longitude": lon, "kategori_materi": "Rokok"},
        {"id": "b", "latitude": None, "longitude": None, "kategori_materi": "Rokok"},
        {"id": "c", "latitude": lat, "longitude": lon, "kategori_materi": "Rokok", "dihapus": True},
    ]
    gdf = load_reklame(recs)
    assert list(gdf.index) == ["a"]
    assert gdf.crs.to_epsg() == 32749
    assert abs(gdf.geometry.iloc[0].x - 1300) < 0.5
    assert "2" in capsys.readouterr().out


def test_audit_all_matches_check_point(tiny_zones):
    pts = {"r1": (1300, 1000, "Rokok"), "r2": (7000, 7000, "Rokok"), "r3": (5000, 3010, "Rokok elektronik"),
           "r4": (1300, 1000, "Umum"), "r5": (7000, 7000, "Minuman beralkohol"), "r6": (5000, 4005, "Rokok")}
    recs = []
    for id, (x, y, k) in pts.items():
        lat, lon = to_lonlat(x, y)
        recs.append({"id": id, "latitude": lat, "longitude": lon, "kategori_materi": k,
                     "perlu_cek_manual": None, "tayang_selesai": "2027-01-01"})
    audit = audit_all(load_reklame(recs), tiny_zones, TODAY)
    for id, (x, y, k) in pts.items():
        assert audit.loc[id, "pelanggaran"] == check_point(audit.loc[id, "geometry"], k, tiny_zones)
    assert audit.loc["r1", "status"] == "Melanggar"
    assert audit.loc["r2", "status"] == "Patuh"
    assert audit.loc["r4", "status"] == "Tidak diaudit"
    assert audit.loc["r5", "status"] == "Melanggar"


def test_nearest_info_named_school(tiny_zones):
    info = nearest_info(Point(1300, 1010), tiny_zones)
    assert info["sekolah_nama"] == "SDN Contoh"
    assert info["sekolah_jenis"] == "SD"
    assert info["sekolah_jarak_m"] == 280
    assert info["jalan_utama_jarak_m"] == 1990


def test_nearest_info_unnamed_school(tiny_zones):
    info = nearest_info(Point(5100, 5000), tiny_zones)
    assert info["sekolah_nama"] == "Sekolah tanpa nama"
    assert info["sekolah_jarak_m"] == 100


def test_alasan_text(tiny_zones):
    info = nearest_info(Point(1300, 1010), tiny_zones)
    lines = alasan_text(["449_1_d"], info)
    assert lines == ["280 m dari SDN Contoh (di dalam radius 500 m). Melanggar PP 28/2024 Ps. 449 (1) d."]
    assert alasan_text(["perda_5_2019_23"], info)[0].startswith("Reklame minuman beralkohol dilarang")


def test_normalize_kategori():
    assert normalize_kategori(" rokok ") == "Rokok"
    assert normalize_kategori("ROKOK  ELEKTRONIK") == "Rokok elektronik"
    assert normalize_kategori("minuman beralkohol") == "Minuman beralkohol"
    with pytest.raises(ValueError):
        normalize_kategori("bir")


def test_audit_all_mixed_perlu_cek_none_is_not_flagged(tiny_zones):
    # pandas mengubah None menjadi NaN bila kolom bercampur teks; NaN tidak boleh dianggap "perlu cek"
    lat, lon = to_lonlat(1300, 1000)
    recs = [
        {"id": "a", "latitude": lat, "longitude": lon, "kategori_materi": "Rokok",
         "perlu_cek_manual": None, "tayang_selesai": None},
        {"id": "b", "latitude": lat, "longitude": lon, "kategori_materi": "Umum",
         "perlu_cek_manual": "BINTANG bisa bir", "tayang_selesai": None},
    ]
    audit = audit_all(load_reklame(recs), tiny_zones, TODAY)
    assert audit.loc["a", "status"] == "Melanggar"
    assert audit.loc["b", "status"] == "Perlu cek"
