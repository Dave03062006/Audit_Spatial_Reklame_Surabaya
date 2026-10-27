import geopandas as gpd
from shapely.geometry import LineString, Point

from search import build_index, find, street_name


def test_street_name_strips_house_number():
    assert street_name("KETINTANG BARU NO. 010 BLOK.") == "Ketintang Baru"
    assert street_name("MENANGGAL NO. VII/029 BLOK.") == "Menanggal"
    assert street_name("PAGESANGAN NO. 000 BLOK.000") == "Pagesangan"


def index():
    rek = gpd.GeoDataFrame({"alamat": ["KETINTANG BARU NO. 010", "KETINTANG BARU NO. 020", "JEMURSARI NO. 1"]},
                           geometry=[Point(0, 0), Point(10, 0), Point(500, 500)], crs="EPSG:32749")
    jalan = gpd.GeoDataFrame({"name": ["Jalan Raya Ketintang", None]},
                             geometry=[LineString([(0, 100), (100, 100)]), LineString([(0, 0), (1, 1)])],
                             crs="EPSG:32749")
    return build_index(rek, jalan)


def test_index_groups_same_street():
    labels = [lbl for lbl, x, y in index()]
    assert labels.count("Ketintang Baru") == 1
    hit = [e for e in index() if e[0] == "Ketintang Baru"][0]
    assert hit[1] == 5 and hit[2] == 0


def test_search_blank_returns_empty():
    assert find(index(), "   ") == []


def test_search_prefix_first():
    res = [lbl for lbl, _, _ in find(index(), "ketin")]
    assert res[0] == "Ketintang Baru"
    assert "Jalan Raya Ketintang" in res


def test_search_no_match():
    assert find(index(), "zzz") == []
