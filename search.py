"""Pencarian nama jalan dari alamat reklame dan nama jalan OSM."""

import re
from collections import defaultdict

NO_PATTERN = re.compile(r"\s+NO\.?\s.*$", flags=re.IGNORECASE)


def street_name(alamat):
    """'KETINTANG BARU NO. 010 BLOK.' -> 'Ketintang Baru'"""
    s = NO_PATTERN.sub("", str(alamat or "")).strip(" .,-")
    return s.title()


def build_index(reklame, jalan):
    """Daftar (label, x, y): satu entri per nama jalan, di titik tengah semua kemunculannya."""
    pts = defaultdict(list)
    for alamat, geom in zip(reklame["alamat"], reklame.geometry):
        name = street_name(alamat)
        if name and geom is not None:
            pts[name].append((geom.x, geom.y))
    if jalan is not None and "name" in jalan.columns:
        for name, geom in zip(jalan["name"], jalan.geometry):
            if isinstance(name, str) and name.strip() and geom is not None:
                c = geom.interpolate(0.5, normalized=True) if geom.geom_type == "LineString" else geom.centroid
                pts[name.strip()].append((c.x, c.y))
    index = []
    for name, xy in pts.items():
        index.append((name, sum(p[0] for p in xy) / len(xy), sum(p[1] for p in xy) / len(xy)))
    index.sort(key=lambda e: e[0])
    return index


def find(index, q, limit=8):
    q = " ".join(str(q).split()).lower()
    if not q:
        return []
    prefix = [e for e in index if e[0].lower().startswith(q)]
    inside = [e for e in index if q in e[0].lower() and not e[0].lower().startswith(q)]
    return (prefix + inside)[:limit]
