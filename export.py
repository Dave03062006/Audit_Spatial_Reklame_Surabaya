"""Ekspor daftar pelanggaran ke CSV (bisa dibuka di Excel)."""

import csv
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from gis import CRS_METER, CRS_SOURCE, RULE_SHORT

CSV_COLUMNS = ["id", "isi_reklame", "kategori_materi", "alamat", "pasal",
               "jarak_sekolah_m", "sekolah_terdekat", "lat", "lon"]


def pasal_text(pelanggaran):
    return "; ".join(RULE_SHORT[p] for p in pelanggaran)


def pelanggaran_csv(rows, zones, out_dir, today):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"pelanggaran_{today:%Y%m%d}.csv"
    melanggar = [r for r in rows if r["status"] == "Melanggar"]

    # sekolah terdekat untuk semua pelanggaran sekaligus (satu spatial join)
    terdekat = {}
    if melanggar and not zones.fasilitas.empty:
        pts = gpd.GeoDataFrame({"id": [r["id"] for r in melanggar]},
                               geometry=[Point(r["x"], r["y"]) for r in melanggar], crs=CRS_METER)
        j = gpd.sjoin_nearest(pts, zones.fasilitas[["name", "geometry"]], distance_col="jarak")
        j = j[~j["id"].duplicated()]
        for id, name, jarak in zip(j["id"], j["name"], j["jarak"]):
            nama = name if isinstance(name, str) and name.strip() else "Sekolah tanpa nama"
            terdekat[id] = (nama, int(round(jarak)))
    lonlat = gpd.GeoSeries([Point(r["x"], r["y"]) for r in melanggar], crs=CRS_METER).to_crs(CRS_SOURCE)

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r, ll in zip(melanggar, lonlat):
            nama, jarak = terdekat.get(r["id"], ("", ""))
            w.writerow([r["id"], r.get("isi_reklame"), r.get("kategori_materi"), r.get("alamat"),
                        pasal_text(r["pelanggaran"]), jarak, nama, round(ll.y, 7), round(ll.x, 7)])
    return path
