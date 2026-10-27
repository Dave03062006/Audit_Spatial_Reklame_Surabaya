"""Aturan spasial audit reklame.

Tiga lapisan, seperti di notebook week 5:
  Layer 1 (Fasilitas) : sekolah, Polygon atau Point
  Layer 2 (Reklame)   : titik reklame, Point
  Layer 3 (Jalan)     : ruas jalan, LineString

Dua operasi GIS: buffer (+ dissolve) dan spatial join (intersects).
Semua hitungan jarak memakai EPSG:32749 (UTM 49S) supaya satuannya meter.
"""

from dataclasses import dataclass, field
from datetime import date

import geopandas as gpd
from shapely.geometry import LineString, Point, box
from shapely.prepared import prep

CRS_SOURCE = "EPSG:4326"
CRS_METER = "EPSG:32749"
RADIUS_M = 500
KORIDOR_M = 25

KATEGORI = ["Umum", "Rokok", "Rokok elektronik", "Minuman beralkohol"]
KATEGORI_AUDIT = {"Rokok", "Rokok elektronik"}
KATEGORI_ALKOHOL = "Minuman beralkohol"

RULE_LABELS = {
    "449_1_d": "PP 28/2024 Ps. 449 (1) d: radius 500 m dari satuan pendidikan",
    "449_1_c": "PP 28/2024 Ps. 449 (1) c: di jalan utama atau jalan protokol",
    "perda_5_2019_23": "Perda Surabaya 5/2019 Ps. 23: reklame minuman beralkohol dilarang",
}
RULE_SHORT = {
    "449_1_d": "Ps. 449 (1) d",
    "449_1_c": "Ps. 449 (1) c",
    "perda_5_2019_23": "Perda 5/2019",
}

STATUS = ["Melanggar", "Patuh", "Tidak diaudit", "Perlu cek", "Tayang berakhir"]


def normalize_kategori(s):
    key = " ".join(str(s).split()).lower()
    for k in KATEGORI:
        if k.lower() == key:
            return k
    raise ValueError(f"Kategori tidak dikenal: {s!r}")


# ---------------------------------------------------------------
# Layer 2 (Reklame)
# ---------------------------------------------------------------

def load_reklame(records):
    """Ubah daftar reklame (lat/lon) menjadi GeoDataFrame dalam meter."""
    ok = [r for r in records
          if not r.get("dihapus") and r.get("latitude") is not None and r.get("longitude") is not None]
    skipped = len(records) - len(ok)
    if skipped:
        print(f"Reklame dilewati (tanpa koordinat atau dihapus): {skipped}")
    gdf = gpd.GeoDataFrame(
        ok,
        geometry=[Point(r["longitude"], r["latitude"]) for r in ok],
        crs=CRS_SOURCE,
    ).to_crs(CRS_METER)
    gdf.index = [r["id"] for r in ok]
    return gdf


# ---------------------------------------------------------------
# Operasi GIS: buffer + dissolve -> zona larangan
# ---------------------------------------------------------------

@dataclass
class Zones:
    fasilitas: gpd.GeoDataFrame       # Layer 1 (Fasilitas)
    jalan: gpd.GeoDataFrame           # Layer 3 (Jalan)
    batas: object                     # batas kota Surabaya (Polygon)
    zona_500: object
    koridor_25: object
    area_boleh: object
    zona_prep: object = field(repr=False, default=None)
    koridor_prep: object = field(repr=False, default=None)

    @classmethod
    def build(cls, fasilitas, jalan, batas, zona_500=None, koridor_25=None, area_boleh=None):
        if zona_500 is None:
            # Layer 1 (Fasilitas): buffer 500 m lalu digabung (dissolve)
            zona_500 = fasilitas.geometry.buffer(RADIUS_M).union_all()
        if koridor_25 is None:
            # Layer 3 (Jalan): hanya jalan utama, buffer 25 m
            utama = jalan[jalan["tipe_jalan"] == "jalan utama"]
            koridor_25 = utama.geometry.buffer(KORIDOR_M).union_all()
        if area_boleh is None:
            area_boleh = batas.difference(zona_500).difference(koridor_25)
        return cls(fasilitas, jalan, batas, zona_500, koridor_25, area_boleh,
                   prep(zona_500), prep(koridor_25))

    @property
    def jalan_utama(self):
        return self.jalan[self.jalan["tipe_jalan"] == "jalan utama"]


def check_point(pt, kategori, zones):
    """Cek satu titik reklame (dalam meter). Hasil: daftar kode pasal yang dilanggar."""
    hasil = []
    if kategori in KATEGORI_AUDIT:
        if zones.zona_prep.intersects(pt):
            hasil.append("449_1_d")
        if zones.koridor_prep.intersects(pt):
            hasil.append("449_1_c")
    elif kategori == KATEGORI_ALKOHOL:
        hasil.append("perda_5_2019_23")
    return hasil


def _parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def status_of(row, pelanggaran, today):
    if row.get("perlu_cek_manual") and not row.get("kategori_dikonfirmasi"):
        return "Perlu cek"
    if row.get("kategori_materi") == "Umum":
        return "Tidak diaudit"
    selesai = _parse_date(row.get("tayang_selesai"))
    if selesai is not None and selesai < today:
        return "Tayang berakhir"
    return "Melanggar" if pelanggaran else "Patuh"


# ---------------------------------------------------------------
# Operasi GIS: spatial join (intersects) untuk semua reklame
# ---------------------------------------------------------------

def _ids_intersecting(reklame, geom):
    if geom is None or geom.is_empty or reklame.empty:
        return set()
    zona = gpd.GeoDataFrame(geometry=[geom], crs=reklame.crs)
    joined = gpd.sjoin(reklame[["geometry"]], zona, predicate="intersects", how="inner")
    return set(joined.index)


def audit_all(reklame, zones, today):
    audit = reklame.copy()
    dalam_zona = _ids_intersecting(audit, zones.zona_500)
    dalam_koridor = _ids_intersecting(audit, zones.koridor_25)

    pelanggaran = []
    for id, kategori in zip(audit.index, audit["kategori_materi"]):
        p = []
        if kategori in KATEGORI_AUDIT:
            if id in dalam_zona:
                p.append("449_1_d")
            if id in dalam_koridor:
                p.append("449_1_c")
        elif kategori == KATEGORI_ALKOHOL:
            p.append("perda_5_2019_23")
        pelanggaran.append(p)
    audit["pelanggaran"] = pelanggaran
    audit["status"] = [status_of(r, p, today)
                       for r, p in zip(audit.to_dict("records"), pelanggaran)]
    return audit


def recheck_row(row, zones, today):
    """Hitung ulang satu reklame setelah diubah admin (row dari Store)."""
    pt = gpd.GeoSeries([Point(row["longitude"], row["latitude"])], crs=CRS_SOURCE).to_crs(CRS_METER).iloc[0]
    p = check_point(pt, row.get("kategori_materi"), zones)
    return pt, p, status_of(row, p, today)


def nearest_info(pt, zones):
    titik = gpd.GeoDataFrame(geometry=[pt], crs=CRS_METER)
    info = {"sekolah_nama": None, "sekolah_jenis": None,
            "sekolah_jarak_m": None, "jalan_utama_jarak_m": None}
    if not zones.fasilitas.empty:
        s = gpd.sjoin_nearest(titik, zones.fasilitas[["name", "jenis", "geometry"]], distance_col="jarak").iloc[0]
        nama = s["name"]
        info["sekolah_nama"] = nama if isinstance(nama, str) and nama.strip() else "Sekolah tanpa nama"
        info["sekolah_jenis"] = s["jenis"]
        info["sekolah_jarak_m"] = int(round(s["jarak"]))
    utama = zones.jalan_utama
    if not utama.empty:
        j = gpd.sjoin_nearest(titik, utama[["geometry"]], distance_col="jarak").iloc[0]
        info["jalan_utama_jarak_m"] = int(round(j["jarak"]))
    return info


def alasan_text(pelanggaran, info):
    lines = []
    if "449_1_d" in pelanggaran:
        lines.append(f"{info['sekolah_jarak_m']} m dari {info['sekolah_nama']} "
                     f"(di dalam radius {RADIUS_M} m). Melanggar PP 28/2024 Ps. 449 (1) d.")
    if "449_1_c" in pelanggaran:
        lines.append(f"{info['jalan_utama_jarak_m']} m dari jalan utama "
                     f"(di dalam koridor {KORIDOR_M} m). Melanggar PP 28/2024 Ps. 449 (1) c.")
    if "perda_5_2019_23" in pelanggaran:
        lines.append("Reklame minuman beralkohol dilarang di seluruh Surabaya (Perda 5/2019 Ps. 23).")
    return lines


if __name__ == "__main__":
    # Contoh dengan koordinat buatan (meter), seperti di notebook week 5
    sekolah = box(1000, 1000, 1020, 1020)
    jalan_utama = LineString([(0, 3000), (6000, 3000)])
    fasilitas = gpd.GeoDataFrame({"name": ["SDN Contoh"], "jenis": ["SD"]}, geometry=[sekolah], crs=CRS_METER)
    jalan = gpd.GeoDataFrame({"name": ["Jalan Utama"], "tipe_jalan": ["jalan utama"]},
                             geometry=[jalan_utama], crs=CRS_METER)
    zones = Zones.build(fasilitas, jalan, box(0, 0, 8000, 8000))

    print("Luas zona 500 m      :", round(zones.zona_500.area), "m2")
    print("Luas koridor 25 m    :", round(zones.koridor_25.area), "m2")
    print("Luas area boleh      :", round(zones.area_boleh.area), "m2")
    print()
    contoh = {
        "Rokok dekat sekolah": (Point(1300, 1000), "Rokok"),
        "Rokok di jalan utama": (Point(5000, 3010), "Rokok"),
        "Rokok jauh": (Point(7000, 7000), "Rokok"),
        "Alkohol di mana saja": (Point(7000, 7000), "Minuman beralkohol"),
    }
    for nama, (pt, k) in contoh.items():
        print(f"{nama:<22}: {check_point(pt, k, zones)}")
