"""Peta Surabaya yang digambar dengan Pygame.

- Viewport: mengubah koordinat dunia (meter, EPSG:32749) ke piksel layar.
- TileCache: menggambar peta dasar dan lapisan zona per kotak 256 px,
  lalu menyimpannya sebagai PNG di cache/tiles supaya cukup digambar sekali.
- cluster(): menggabungkan reklame yang berdekatan atau di titik yang sama.
- MapView: menggambar semuanya dan mengubah klik/seret menjadi MapEvent.
- Garis ukur: dari reklame terpilih ke sekolah dan jalan utama terdekat, dengan jaraknya.
"""

import math
import shutil
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pygame
from shapely.geometry import box

from ui import theme

ZOOM_MIN = 11
ZOOM_MAX = 17
TILE_PX = 256
TILE_STYLE = "2"   # naikkan bila gaya tile berubah, supaya tile lama di cache digambar ulang
OVERLAY_STYLE = {
    "zona": (theme.TEAL, 38, 150),
    "koridor": (theme.TEAL, 60, 0),
    "area_boleh": (theme.HIJAU_BOLEH, 96, 200),
}
SS = 3   # ikon digambar 3x lebih besar lalu diperkecil, supaya tepinya halus
ROAD_STYLE = {  # tipe: (warna isi, warna tepi, lebar dasar px pada zoom 15)
    "tol": ((246, 214, 160), (205, 160, 90), 6),
    "jalan utama": (theme.PUTIH, (160, 176, 188), 7),
    "penghubung": (theme.PUTIH, (190, 201, 210), 5),
    "kecil": ((222, 227, 231), None, 3),
}


def mpp(z):
    """Meter per piksel pada zoom z (lintang Surabaya)."""
    return 156543.03 * math.cos(math.radians(-7.27)) / 2 ** z


class Viewport:
    def __init__(self, cx, cy, zoom, size):
        self.cx, self.cy, self.zoom = float(cx), float(cy), int(zoom)
        self.size = tuple(size)

    @property
    def m(self):
        return mpp(self.zoom)

    def world_to_screen(self, x, y):
        w, h = self.size
        return (int(round((x - self.cx) / self.m + w / 2)),
                int(round((self.cy - y) / self.m + h / 2)))

    def screen_to_world(self, px, py):
        w, h = self.size
        return self.cx + (px - w / 2) * self.m, self.cy - (py - h / 2) * self.m

    def pan(self, dx_px, dy_px):
        self.cx -= dx_px * self.m
        self.cy += dy_px * self.m

    def zoom_at(self, px, py, step):
        wx, wy = self.screen_to_world(px, py)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.zoom + step))
        w, h = self.size
        self.cx = wx - (px - w / 2) * self.m
        self.cy = wy + (py - h / 2) * self.m

    def fly_to(self, x, y, zoom=16):
        self.cx, self.cy = float(x), float(y)
        self.zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))

    def world_bounds(self):
        x0, y1 = self.screen_to_world(0, 0)
        x1, y0 = self.screen_to_world(*self.size)
        return x0, y0, x1, y1


# ---------------------------------------------------------------
# Tile peta dasar dan lapisan zona
# ---------------------------------------------------------------

def _rings(geom):
    """Semua cincin luar dan lubang dari Polygon/MultiPolygon/GeometryCollection."""
    if geom.is_empty:
        return [], []
    if geom.geom_type == "Polygon":
        return [geom.exterior], list(geom.interiors)
    outer, holes = [], []
    for g in getattr(geom, "geoms", []):
        o, h = _rings(g)
        outer += o
        holes += h
    return outer, holes


def _lines(geom):
    if geom.is_empty:
        return []
    if geom.geom_type in ("LineString", "LinearRing"):
        return [geom]
    if geom.geom_type == "Polygon":
        return [geom.exterior]
    out = []
    for g in getattr(geom, "geoms", []):
        out += _lines(g)
    return out


class TileCache:
    def __init__(self, zones, cache_dir, mem_limit=256):
        self.zones = zones
        self.dir = Path(cache_dir) / "tiles"
        self._check_style()
        self.mem = OrderedDict()
        self.mem_limit = mem_limit
        self.render_count = 0
        minx, miny, maxx, maxy = zones.batas.bounds
        self.ox, self.oy = minx, maxy
        self.overlay_geom = {"zona": zones.zona_500, "koridor": zones.koridor_25,
                             "area_boleh": zones.area_boleh}

    def _check_style(self):
        stamp = self.dir / "style.txt"
        if self.dir.exists() and (not stamp.exists() or stamp.read_text().strip() != TILE_STYLE):
            shutil.rmtree(self.dir, ignore_errors=True)
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp.write_text(TILE_STYLE)

    def tile_world_size(self, z):
        return TILE_PX * mpp(z)

    def tile_bounds(self, z, tx, ty):
        s = self.tile_world_size(z)
        x0 = self.ox + tx * s
        y1 = self.oy - ty * s
        return x0, y1 - s, x0 + s, y1

    def tile_index(self, z, x, y):
        s = self.tile_world_size(z)
        return math.floor((x - self.ox) / s), math.floor((self.oy - y) / s)

    def path(self, layer, z, tx, ty):
        return self.dir / layer / str(z) / f"{tx}_{ty}.png"

    def get(self, z, tx, ty, layer="base"):
        key = (layer, z, tx, ty)
        if key in self.mem:
            self.mem.move_to_end(key)
            return self.mem[key]
        p = self.path(layer, z, tx, ty)
        surf = None
        if p.exists():
            try:
                surf = pygame.image.load(str(p))
                if layer != "base" and pygame.display.get_init() and pygame.display.get_surface():
                    surf = surf.convert_alpha()
            except pygame.error:
                surf = None
        if surf is None:
            surf = self.render(layer, z, tx, ty)
            p.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(surf, str(p))
        self.mem[key] = surf
        if len(self.mem) > self.mem_limit:
            self.mem.popitem(last=False)
        return surf

    def _to_px(self, coords, x0, y1, m):
        a = np.asarray(coords)[:, :2]
        px = (a[:, 0] - x0) / m
        py = (y1 - a[:, 1]) / m
        return np.column_stack([px, py]).tolist()

    def render(self, layer, z, tx, ty):
        self.render_count += 1
        x0, y0, x1, y1 = self.tile_bounds(z, tx, ty)
        m = mpp(z)
        tile_box = box(x0, y0, x1, y1)
        if layer == "base":
            surf = pygame.Surface((TILE_PX, TILE_PX))
            surf.fill(theme.LUAR_KOTA)
            self._draw_poly(surf, self.zones.batas.intersection(tile_box), theme.TANAH, x0, y1, m)
            self._draw_roads(surf, tile_box, x0, y1, m, z)
            self._draw_schools(surf, tile_box, x0, y1, m)
            return surf
        surf = pygame.Surface((TILE_PX, TILE_PX), pygame.SRCALPHA)
        geom = self.overlay_geom[layer]
        if geom is None or not geom.intersects(tile_box):
            return surf
        color, alpha, line_alpha = OVERLAY_STYLE[layer]
        part = geom.intersection(tile_box)
        self._draw_poly(surf, part, (*color, alpha), x0, y1, m, hole_color=(0, 0, 0, 0))
        if line_alpha:
            # garis tepi dari bentuk asli, bukan dari potongan tile (supaya tidak ada garis sambungan tile)
            edge = geom.boundary.intersection(tile_box.buffer(2 * m))
            for ring in _lines(edge):
                pts = self._to_px(ring.coords, x0, y1, m)
                if len(pts) >= 2:
                    pygame.draw.lines(surf, (*color, line_alpha), False, pts, 2)
        return surf

    def _draw_poly(self, surf, geom, color, x0, y1, m, hole_color=None):
        outer, holes = _rings(geom)
        for ring in outer:
            pts = self._to_px(ring.coords, x0, y1, m)
            if len(pts) >= 3:
                pygame.draw.polygon(surf, color, pts)
        fill_hole = hole_color if hole_color is not None else theme.LUAR_KOTA
        for ring in holes:
            pts = self._to_px(ring.coords, x0, y1, m)
            if len(pts) >= 3:
                pygame.draw.polygon(surf, fill_hole, pts)

    def _draw_roads(self, surf, tile_box, x0, y1, m, z):
        jalan = self.zones.jalan
        if jalan.empty:
            return
        idx = jalan.sindex.query(tile_box.buffer(20 * m))
        if len(idx) == 0:
            return
        part = jalan.iloc[idx]
        scale = 2 ** (z - 15)
        order = ["kecil", "penghubung", "jalan utama", "tol"]
        for tipe in order:
            if z < 13 and tipe == "kecil":
                continue
            fill, edge, base_w = ROAD_STYLE[tipe]
            w = max(2 if tipe != "kecil" else 1, int(round(base_w * scale)))
            geoms = part.geometry[part["tipe_jalan"] == tipe]
            lines = [ln for g in geoms for ln in _lines(g)]
            if edge:
                for ln in lines:
                    pygame.draw.lines(surf, edge, False, self._to_px(ln.coords, x0, y1, m), w + 2)
            for ln in lines:
                pygame.draw.lines(surf, fill, False, self._to_px(ln.coords, x0, y1, m), w)

    def _draw_schools(self, surf, tile_box, x0, y1, m):
        fas = self.zones.fasilitas
        if fas.empty:
            return
        idx = fas.sindex.query(tile_box.buffer(10 * m))
        for g in fas.geometry.iloc[idx]:
            if g.geom_type == "Point":
                px, py = self._to_px([g.coords[0]], x0, y1, m)[0]
                r = 4
                pygame.draw.rect(surf, theme.TEAL_TUA, (px - r, py - r, 2 * r, 2 * r), border_radius=2)
            else:
                self._draw_poly(surf, g, theme.TEAL_TUA, x0, y1, m, hole_color=theme.TANAH)


# ---------------------------------------------------------------
# Pengelompokan titik (cluster)
# ---------------------------------------------------------------

@dataclass
class Cluster:
    x: float
    y: float
    ids: list = field(default_factory=list)


def cluster_arrays(ids, xs, ys, vp, radius_px=18):
    if len(ids) == 0:
        return []
    w, h = vp.size
    m = vp.m
    px = (xs - vp.cx) / m + w / 2
    py = (vp.cy - ys) / m + h / 2
    vis = (px >= -radius_px) & (px <= w + radius_px) & (py >= -radius_px) & (py <= h + radius_px)
    if not vis.any():
        return []
    sel = np.nonzero(vis)[0]
    gx = np.floor(px[sel] / radius_px).astype(np.int64)
    gy = np.floor(py[sel] / radius_px).astype(np.int64)
    keys = gx * 1_000_003 + gy
    order = np.argsort(keys, kind="stable")
    keys_sorted = keys[order]
    splits = np.nonzero(np.diff(keys_sorted))[0] + 1
    out = []
    for grp in np.split(order, splits):
        members = sel[grp]
        out.append(Cluster(float(xs[members].mean()), float(ys[members].mean()),
                           [ids[i] for i in members]))
    return out


def cluster(points, vp, radius_px=18):
    if not points:
        return []
    ids = [p[0] for p in points]
    xs = np.array([p[1] for p in points], dtype=float)
    ys = np.array([p[2] for p in points], dtype=float)
    return cluster_arrays(ids, xs, ys, vp, radius_px)


# ---------------------------------------------------------------
# MapView
# ---------------------------------------------------------------

@dataclass
class Marker:
    id: str
    x: float
    y: float
    status: str


@dataclass
class MapEvent:
    kind: str          # "marker" | "empty" | "drag_end"
    ids: list
    x: float
    y: float


_SPRITES = {}
# urutan cincin cluster searah jarum jam, mulai dari atas
RING_ORDER = ["Melanggar", "Perlu cek", "Patuh", "Tayang berakhir", "Tidak diaudit"]
RING_COLOR = {**theme.STATUS_COLOR, "Tayang berakhir": (196, 206, 214)}


def _sprite(key, size, paint):
    """Ikon dari cache. paint(surface, s) menggambar pada skala s (SS kali ukuran akhir)."""
    if key not in _SPRITES:
        big = pygame.Surface((size * SS, size * SS), pygame.SRCALPHA)
        paint(big, SS)
        _SPRITES[key] = pygame.transform.smoothscale(big, (size, size))
    return _SPRITES[key]


def _paint_marker(status, selected):
    def paint(surf, s):
        c = surf.get_width() // 2
        color = theme.STATUS_COLOR.get(status, theme.ABU_UMUM)
        if selected:
            pygame.draw.circle(surf, (*color, 60), (c, c), 20 * s)
            pygame.draw.circle(surf, color, (c, c), 15 * s, 3 * s)
        if status == "Tidak diaudit":
            pygame.draw.circle(surf, theme.PUTIH, (c, c), 5 * s)
            pygame.draw.circle(surf, color, (c, c), 4 * s)
            return
        if status == "Tayang berakhir":
            pygame.draw.circle(surf, (*theme.PUTIH, 200), (c, c), 8 * s)
            pygame.draw.circle(surf, (*color, 170), (c, c), 7 * s)
            return
        pygame.draw.circle(surf, theme.PUTIH, (c, c), 10 * s)
        pygame.draw.circle(surf, color, (c, c), 8 * s)
        if status == "Patuh":
            pygame.draw.lines(surf, theme.PUTIH, False,
                              [(c - 4 * s, c), (c - 1 * s, c + 3 * s), (c + 4 * s, c - 3 * s)], 2 * s)
        else:
            icon = theme.STATUS_ICON.get(status, "")
            if icon:
                t = theme.font(12 * s, bold=True).render(icon, True, theme.PUTIH)
                surf.blit(t, t.get_rect(center=(c, c + s)))
    return paint


def draw_marker(surf, pos, status, selected=False):
    size = 44 if selected else 22
    img = _sprite(("marker", status, selected), size, _paint_marker(status, selected))
    surf.blit(img, img.get_rect(center=pos))


def ring_parts(statuses, steps=48):
    """Porsi tiap status pada cincin cluster, dibulatkan ke 1/steps supaya ikonnya bisa di-cache."""
    n = len(statuses)
    counts = {k: 0 for k in RING_ORDER}
    for st in statuses:
        counts[st if st in counts else "Tidak diaudit"] += 1
    parts, used = [], 0
    for k in RING_ORDER:
        if counts[k]:
            q = max(1, round(counts[k] / n * steps))
            parts.append((k, q))
            used += q
    if parts and used != steps:   # koreksi pembulatan pada potongan terbesar
        i = max(range(len(parts)), key=lambda j: parts[j][1])
        parts[i] = (parts[i][0], parts[i][1] + steps - used)
    return tuple(parts)


def _paint_cluster(r, parts, steps):
    def paint(surf, s):
        c = surf.get_width() // 2
        outer, inner = r * s, (r - 5) * s
        pygame.draw.circle(surf, theme.PUTIH, (c, c), outer + 2 * s)
        a = -math.pi / 2
        for status, q in parts:
            span = 2 * math.pi * q / steps
            n = max(2, int(span * 24))
            pts = [(c, c)] + [(c + outer * math.cos(a + span * i / n), c + outer * math.sin(a + span * i / n))
                              for i in range(n + 1)]
            pygame.draw.polygon(surf, RING_COLOR.get(status, theme.ABU_UMUM), pts)
            a += span
        pygame.draw.circle(surf, theme.PUTIH, (c, c), inner)
    return paint


def draw_cluster(surf, pos, statuses, selected=False):
    """Lingkaran berangka. Cincinnya dibagi menurut porsi status, merah = bagian yang melanggar."""
    n = len(statuses)
    r = 14 if n < 10 else 17 if n < 100 else 20
    parts = ring_parts(statuses)
    img = _sprite(("cluster", r, parts), 2 * (r + 3), _paint_cluster(r, parts, 48))
    if selected:
        pygame.draw.circle(surf, theme.NAVY, pos, r + 7, 2)
    surf.blit(img, img.get_rect(center=pos))
    t = theme.display(15 if n < 100 else 14).render(str(n), True, theme.TEKS)
    surf.blit(t, t.get_rect(center=pos))


def nice_scale(m_per_px, max_px=120):
    """Panjang skala yang enak dibaca (meter) dan panjangnya dalam piksel."""
    best = 50
    for d in (50, 100, 200, 250, 500, 1000, 2000, 2500, 5000):
        if d / m_per_px <= max_px:
            best = d
    return best, int(round(best / m_per_px))


def _dashed(surf, color, a, b, width=2, dash=7, gap=5):
    (x0, y0), (x1, y1) = a, b
    length = math.hypot(x1 - x0, y1 - y0)
    if length == 0:
        return
    ux, uy = (x1 - x0) / length, (y1 - y0) / length
    t = 0.0
    while t < length:
        e = min(t + dash, length)
        pygame.draw.line(surf, color, (x0 + ux * t, y0 + uy * t), (x0 + ux * e, y0 + uy * e), width)
        t = e + gap


def tag(surf, label, pos, color, anchor="center", bounds=None):
    """Label jarak berbentuk pil, mis. 'TK Diana · 210 m'. bounds menjaga label tetap di dalam peta."""
    img = theme.display(16).render(label, True, theme.PUTIH)
    r = img.get_rect().inflate(14, 4)
    setattr(r, anchor, pos)
    if bounds is not None:
        r.clamp_ip(bounds.inflate(-12, -12))
    pygame.draw.rect(surf, theme.PUTIH, r.inflate(4, 4), border_radius=r.height // 2 + 2)
    pygame.draw.rect(surf, color, r, border_radius=r.height // 2)
    surf.blit(img, img.get_rect(center=r.center))
    return r


@dataclass
class Measure:
    """Garis ukur dari reklame (x0, y0) ke titik terdekat (x1, y1) pada sekolah atau jalan utama."""
    x0: float
    y0: float
    x1: float
    y1: float
    label: str
    color: tuple


class MapView:
    CLICK_SLOP = 4

    def __init__(self, rect, zones, tiles, vp):
        self.rect = pygame.Rect(rect)
        self.zones = zones
        self.tiles = tiles
        self.vp = vp
        self.vp.size = self.rect.size
        self.ids, self.xs, self.ys, self.status = [], np.zeros(0), np.zeros(0), {}
        self.clusters = []
        self.selected_id = None
        self.draggable_id = None
        self.pin = None             # (x, y) pin laporan, digambar di atas semua titik
        self.measures = []          # Measure untuk reklame terpilih
        self.zoom_in_rect = pygame.Rect(self.rect.right - 56, self.rect.bottom - 112, 44, 44)
        self.zoom_out_rect = pygame.Rect(self.rect.right - 56, self.rect.bottom - 64, 44, 44)
        self._down = None
        self._dragging = False
        self._drag_marker = False
        self._drag_pos = None

    def set_markers(self, markers):
        self.ids = [mk.id for mk in markers]
        self.xs = np.array([mk.x for mk in markers], dtype=float)
        self.ys = np.array([mk.y for mk in markers], dtype=float)
        self.status = {mk.id: mk.status for mk in markers}

    def _local(self, pos):
        return pos[0] - self.rect.x, pos[1] - self.rect.y

    def draw(self, surface, overlays=frozenset()):
        clip = surface.get_clip()
        surface.set_clip(self.rect)
        surface.fill(theme.LUAR_KOTA, self.rect)
        z = self.vp.zoom
        x0, y0, x1, y1 = self.vp.world_bounds()
        tx0, ty0 = self.tiles.tile_index(z, x0, y1)
        tx1, ty1 = self.tiles.tile_index(z, x1, y0)
        layers = ["base"] + [o for o in ("area_boleh", "zona", "koridor") if o in overlays]
        for layer in layers:
            for tx in range(tx0, tx1 + 1):
                for ty in range(ty0, ty1 + 1):
                    bx0, _, _, by1 = self.tiles.tile_bounds(z, tx, ty)
                    sx, sy = self.vp.world_to_screen(bx0, by1)
                    surface.blit(self.tiles.get(z, tx, ty, layer), (self.rect.x + sx, self.rect.y + sy))

        xs, ys = self.xs, self.ys
        if self._drag_marker and self._drag_pos is not None and self.draggable_id in self.ids:
            xs = xs.copy()
            ys = ys.copy()
            i = self.ids.index(self.draggable_id)
            xs[i], ys[i] = self._drag_pos
        self.clusters = cluster_arrays(self.ids, xs, ys, self.vp)
        # gambar titik umum dulu, pelanggaran paling atas
        rank = {"Tidak diaudit": 0, "Tayang berakhir": 1, "Patuh": 2, "Perlu cek": 3, "Melanggar": 4}
        def top_status(c):
            return max((self.status[i] for i in c.ids), key=lambda s: rank.get(s, 0))
        selected_pos = None
        for c in sorted(self.clusters, key=lambda c: (len(c.ids) > 1, rank.get(top_status(c), 0))):
            sx, sy = self.vp.world_to_screen(c.x, c.y)
            pos = (self.rect.x + sx, self.rect.y + sy)
            if len(c.ids) == 1:
                if c.ids[0] == self.selected_id:
                    selected_pos = pos   # digambar terakhir, di atas garis ukur
                    continue
                draw_marker(surface, pos, self.status[c.ids[0]])
            else:
                draw_cluster(surface, pos, [self.status[i] for i in c.ids], selected=self.selected_id in c.ids)
        self._draw_measures(surface)
        if selected_pos is not None:
            draw_marker(surface, selected_pos, self.status[self.selected_id], selected=True)
        if self.pin is not None:
            sx, sy = self.vp.world_to_screen(*self.pin)
            px, py = self.rect.x + sx, self.rect.y + sy
            pygame.draw.circle(surface, theme.NAVY, (px, py - 18), 10)
            pygame.draw.polygon(surface, theme.NAVY, [(px - 7, py - 12), (px + 7, py - 12), (px, py)])
            pygame.draw.circle(surface, theme.PUTIH, (px, py - 18), 4)
        self._draw_controls(surface)
        surface.set_clip(clip)

    def _to_screen(self, x, y):
        sx, sy = self.vp.world_to_screen(x, y)
        return self.rect.x + sx, self.rect.y + sy

    def _draw_measures(self, surface):
        for mz in self.measures:
            a, b = self._to_screen(mz.x0, mz.y0), self._to_screen(mz.x1, mz.y1)
            _dashed(surface, theme.PUTIH, a, b, width=5)
            _dashed(surface, mz.color, a, b, width=2)
            pygame.draw.circle(surface, theme.PUTIH, b, 6)
            pygame.draw.circle(surface, mz.color, b, 4)
            # label di luar titik ujung, searah garis, supaya garis dan reklame tetap terlihat
            dx, dy = b[0] - a[0], b[1] - a[1]
            if abs(dx) >= abs(dy):
                anchor, off = ("midleft", (12, 0)) if dx >= 0 else ("midright", (-12, 0))
            else:
                anchor, off = ("midtop", (0, 12)) if dy > 0 else ("midbottom", (0, -12))
            tag(surface, mz.label, (b[0] + off[0], b[1] + off[1]), mz.color, anchor, bounds=self.rect)

    def _draw_controls(self, surface):
        """Tombol zoom dan skala jarak di pojok peta."""
        mouse = pygame.mouse.get_pos()
        for r, sign in ((self.zoom_in_rect, 1), (self.zoom_out_rect, -1)):
            enabled = ZOOM_MIN <= self.vp.zoom + sign <= ZOOM_MAX
            pygame.draw.rect(surface, theme.LATAR if r.collidepoint(mouse) else theme.PUTIH, r, border_radius=8)
            pygame.draw.rect(surface, theme.GARIS, r, 1, border_radius=8)
            col = theme.TEKS if enabled else theme.ABU_UMUM
            pygame.draw.line(surface, col, (r.centerx - 8, r.centery), (r.centerx + 7, r.centery), 2)
            if sign > 0:
                pygame.draw.line(surface, col, (r.centerx, r.centery - 8), (r.centerx, r.centery + 7), 2)

        d, px = nice_scale(self.vp.m)
        lab = theme.display(15).render(f"{d // 1000} km" if d >= 1000 else f"{d} m", True, theme.TEKS)
        hint = theme.font(12).render("Seret untuk geser, scroll untuk zoom", True, theme.TEKS_LABEL)
        box_ = pygame.Rect(self.rect.x + 12, self.rect.bottom - 52, px + lab.get_width() + hint.get_width() + 56, 40)
        pygame.draw.rect(surface, theme.PUTIH, box_, border_radius=8)
        pygame.draw.rect(surface, theme.GARIS, box_, 1, border_radius=8)
        x0, y = box_.x + 14, box_.y + 27
        pygame.draw.line(surface, theme.TEKS, (x0, y), (x0 + px, y), 2)
        for i in range(5):   # garis kecil seperti meteran
            tx = x0 + round(px * i / 4)
            pygame.draw.line(surface, theme.TEKS, (tx, y), (tx, y - (9 if i in (0, 4) else 5)), 2)
        surface.blit(lab, lab.get_rect(midleft=(x0 + px + 8, y - 7)))
        pygame.draw.line(surface, theme.GARIS, (x0 + px + lab.get_width() + 16, box_.y + 10),
                         (x0 + px + lab.get_width() + 16, box_.bottom - 10))
        surface.blit(hint, hint.get_rect(midleft=(x0 + px + lab.get_width() + 26, box_.centery)))

    def hit(self, local_pos, radius=14):
        best, best_d = None, radius + 1
        for c in self.clusters:
            sx, sy = self.vp.world_to_screen(c.x, c.y)
            d = math.hypot(sx - local_pos[0], sy - local_pos[1])
            if d < best_d:
                best, best_d = c, d
        return best

    def zoom_button(self, step):
        self.vp.zoom_at(self.rect.width / 2, self.rect.height / 2, step)

    def handle(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for r, step in ((self.zoom_in_rect, 1), (self.zoom_out_rect, -1)):
                if r.collidepoint(event.pos):
                    self.zoom_button(step)
                    self._down = None
                    return None
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if self.rect.collidepoint(mx, my):
                lx, ly = self._local((mx, my))
                self.vp.zoom_at(lx, ly, 1 if event.y > 0 else -1)
            return None
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(event.pos):
            self._down = event.pos
            self._last = event.pos
            self._dragging = False
            self._drag_marker = False
            if self.draggable_id is not None:
                c = self.hit(self._local(event.pos))
                if c is not None and self.draggable_id in c.ids:
                    self._drag_marker = True
            return None
        if event.type == pygame.MOUSEMOTION and self._down is not None:
            dx, dy = event.pos[0] - self._down[0], event.pos[1] - self._down[1]
            if not self._dragging and math.hypot(dx, dy) > self.CLICK_SLOP:
                self._dragging = True
            if self._dragging:
                if self._drag_marker:
                    self._drag_pos = self.vp.screen_to_world(*self._local(event.pos))
                else:
                    rx, ry = getattr(event, "rel", (0, 0))
                    if (rx, ry) == (0, 0):
                        rx, ry = event.pos[0] - self._last[0], event.pos[1] - self._last[1]
                    self.vp.pan(rx, ry)
            self._last = event.pos
            return None
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._down is not None:
            down, self._down = self._down, None
            local = self._local(event.pos)
            wx, wy = self.vp.screen_to_world(*local)
            if self._drag_marker and self._dragging:
                self._drag_marker = False
                self._drag_pos = None
                return MapEvent("drag_end", [self.draggable_id], wx, wy)
            self._drag_marker = False
            if self._dragging:
                self._dragging = False
                return None
            c = self.hit(local)
            if c is not None:
                return MapEvent("marker", list(c.ids), c.x, c.y)
            return MapEvent("empty", [], wx, wy)
        return None
