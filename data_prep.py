"""Siapkan cache data: unduh OSM sekali, proyeksikan, lalu hitung zona larangan.

Jalankan sekali dengan internet:
    python data_prep.py              # pakai OSM yang sudah diunduh bila ada
    python data_prep.py --refresh-osm  # unduh ulang OSM

Hasil disimpan di folder cache/:
    osm_raw.gpkg   data OSM mentah (dipakai ulang)
    layers.gpkg    fasilitas, jalan, batas, zona_500, koridor_25, area_boleh
    manifest.json  catatan input, supaya hanya yang berubah yang dihitung ulang
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import osmnx as ox

from gis import CRS_METER, KORIDOR_M, RADIUS_M, Zones

CACHE_VERSION = 1
PLACE = "Surabaya, Indonesia"
PLACE_BATAS = "Kota Surabaya, Jawa Timur, Indonesia"
LAYERS = ["fasilitas", "jalan", "batas", "zona_500", "koridor_25", "area_boleh"]


class OSMDownloadError(Exception):
    def __init__(self, layer, cause=None):
        super().__init__(f"Gagal mengunduh lapisan: {layer} ({cause})")
        self.layer = layer


# ---------------------------------------------------------------
# Layer 1 (Fasilitas): jenis sekolah
# ---------------------------------------------------------------

NAME_RULES = [
    ("TK", r"^(TK|TKN|PAUD|RA|KB)\b"),
    ("SD", r"^(SD|SDN|MI|MIN)\b"),
    ("SMP", r"^(SMP|SMPN|MTS|MTSN)\b"),
    ("SMA/SMK", r"^(SMA|SMAN|SMK|SMKN|MA|MAN)\b"),
]
ISCED = {"0": "TK", "1": "SD", "2": "SMP", "3": "SMA/SMK"}


def jenis_sekolah(tags):
    amenity = tags.get("amenity")
    if amenity in ("university", "college"):
        return None
    if amenity == "kindergarten":
        return "TK"
    level = str(tags.get("isced:level") or "").strip()
    if level[:1] in ISCED:
        return ISCED[level[:1]]
    name = tags.get("name")
    if isinstance(name, str):
        for jenis, pattern in NAME_RULES:
            if re.match(pattern, name.strip(), flags=re.IGNORECASE):
                return jenis
    return "sekolah (lainnya)"


# ---------------------------------------------------------------
# Layer 3 (Jalan): tipe jalan dari tag highway
# ---------------------------------------------------------------

TIPE_RANK = ["tol", "jalan utama", "penghubung", "kecil"]


def _tipe_satu(h):
    h = str(h).strip().replace("_link", "")
    if h == "motorway":
        return "tol"
    if h in ("trunk", "primary"):
        return "jalan utama"
    if h in ("secondary", "tertiary"):
        return "penghubung"
    return "kecil"


def tipe_jalan(highway):
    if highway is None:
        return "kecil"
    if isinstance(highway, str):
        values = highway.split(";")
    else:
        values = list(highway)
    return min((_tipe_satu(h) for h in values), key=TIPE_RANK.index, default="kecil")


# ---------------------------------------------------------------
# Unduh OSM
# ---------------------------------------------------------------

def _flat(v):
    if isinstance(v, (list, tuple, set)):
        return ";".join(str(x) for x in v)
    return v


def _keep(gdf, cols):
    gdf = gdf.reset_index(drop=True)
    for c in cols:
        if c not in gdf.columns:
            gdf[c] = None
    out = gdf[cols + ["geometry"]].copy()
    for c in cols:
        out[c] = out[c].map(_flat)
    return out


def fetch_osm(place=PLACE):
    try:
        fas = ox.features_from_place(place, tags={"amenity": ["school", "kindergarten"]})
    except Exception as e:
        raise OSMDownloadError("fasilitas", e)
    try:
        g = ox.graph_from_place(place, network_type="drive")
        jalan = ox.graph_to_gdfs(g, nodes=False)
    except Exception as e:
        raise OSMDownloadError("jalan", e)
    try:
        batas = ox.geocode_to_gdf(PLACE_BATAS)
    except Exception as e:
        raise OSMDownloadError("batas", e)
    return {"fasilitas": fas, "jalan": jalan, "batas": batas}


# ---------------------------------------------------------------
# Cache
# ---------------------------------------------------------------

def _manifest_inputs(reklame_path):
    st = Path(reklame_path).stat()
    return {"reklame_mtime": st.st_mtime, "reklame_size": st.st_size,
            "radius_m": RADIUS_M, "koridor_m": KORIDOR_M, "cache_version": CACHE_VERSION}


def cache_is_fresh(cache_dir, reklame_path):
    cache_dir = Path(cache_dir)
    mf = cache_dir / "manifest.json"
    if not mf.exists() or not (cache_dir / "layers.gpkg").exists():
        return False
    saved = json.loads(mf.read_text())
    return all(saved.get(k) == v for k, v in _manifest_inputs(reklame_path).items())


def build_cache(cache_dir, reklame_path, fetcher=fetch_osm, progress=lambda pct, msg: None,
                refresh_osm=False):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    raw_path = cache_dir / "osm_raw.gpkg"

    progress(5, "Memeriksa data OpenStreetMap")
    if refresh_osm or not raw_path.exists():
        progress(10, "Mengunduh sekolah, jalan, dan batas kota dari OpenStreetMap")
        raw = fetcher()
        raw = {
            "fasilitas": _keep(raw["fasilitas"], ["amenity", "name", "isced:level"]),
            "jalan": _keep(raw["jalan"], ["highway", "name"]),
            "batas": raw["batas"].reset_index(drop=True)[["geometry"]],
        }
        if raw_path.exists():
            raw_path.unlink()
        for name, gdf in raw.items():
            gdf.to_file(raw_path, layer=name, driver="GPKG")
    else:
        raw = {name: gpd.read_file(raw_path, layer=name) for name in ["fasilitas", "jalan", "batas"]}

    # Layer 1 (Fasilitas)
    progress(35, "Mengelompokkan jenis sekolah")
    fas = raw["fasilitas"].copy()
    fas["jenis"] = [jenis_sekolah(t) for t in fas[["amenity", "name", "isced:level"]].to_dict("records")]
    fas = fas[fas["jenis"].notna()].to_crs(CRS_METER)[["name", "jenis", "geometry"]]

    # Layer 3 (Jalan)
    progress(50, "Mengelompokkan tipe jalan")
    jalan = raw["jalan"].copy()
    jalan["tipe_jalan"] = jalan["highway"].map(tipe_jalan)
    jalan = jalan.to_crs(CRS_METER)[["name", "tipe_jalan", "geometry"]]

    batas = raw["batas"].to_crs(CRS_METER).geometry.union_all()

    progress(65, f"Menghitung zona {RADIUS_M} m sekolah dan koridor {KORIDOR_M} m jalan utama")
    zones = Zones.build(fas, jalan, batas)

    progress(85, "Menyimpan cache")
    layers_path = cache_dir / "layers.gpkg"
    if layers_path.exists():
        layers_path.unlink()
    fas.to_file(layers_path, layer="fasilitas", driver="GPKG")
    jalan.to_file(layers_path, layer="jalan", driver="GPKG")
    for name in ["batas", "zona_500", "koridor_25", "area_boleh"]:
        gpd.GeoDataFrame(geometry=[getattr(zones, name)], crs=CRS_METER).to_file(
            layers_path, layer=name, driver="GPKG")

    manifest = _manifest_inputs(reklame_path)
    manifest["dibuat_pada"] = datetime.now().isoformat(timespec="seconds")
    (cache_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    progress(100, "Selesai")
    return zones


def load_zones(cache_dir):
    p = Path(cache_dir) / "layers.gpkg"
    fas = gpd.read_file(p, layer="fasilitas")
    jalan = gpd.read_file(p, layer="jalan")
    one = {n: gpd.read_file(p, layer=n).geometry.iloc[0] for n in ["batas", "zona_500", "koridor_25", "area_boleh"]}
    return Zones.build(fas, jalan, one["batas"], one["zona_500"], one["koridor_25"], one["area_boleh"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Siapkan cache data audit reklame")
    ap.add_argument("--refresh-osm", action="store_true", help="unduh ulang data OpenStreetMap")
    args = ap.parse_args()
    base = Path(__file__).parent
    zones = build_cache(base / "cache", base / "data" / "reklame_surabaya_outdoor_semua.json",
                        progress=lambda p, m: print(f"[{p:3d}%] {m}"), refresh_osm=args.refresh_osm)
    print()
    print("Layer 1 (Fasilitas):", len(zones.fasilitas), "sekolah")
    print(zones.fasilitas["jenis"].value_counts().to_string())
    print()
    print("Layer 3 (Jalan):", len(zones.jalan), "ruas")
    print(zones.jalan["tipe_jalan"].value_counts().to_string())
    print()
    print(f"Luas zona {RADIUS_M} m  : {zones.zona_500.area / 1e6:.1f} km2")
    print(f"Luas koridor {KORIDOR_M} m: {zones.koridor_25.area / 1e6:.1f} km2")
    print(f"Luas area boleh   : {zones.area_boleh.area / 1e6:.1f} km2")
