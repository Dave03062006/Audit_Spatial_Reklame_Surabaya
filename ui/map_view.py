"""Peta Surabaya yang digambar dengan Pygame.

- Viewport: mengubah koordinat dunia (meter, EPSG:32749) ke piksel layar.
- TileCache: menggambar peta dasar dan lapisan zona per kotak 256 px,
  lalu menyimpannya sebagai PNG di cache/tiles supaya cukup digambar sekali.
- cluster(): menggabungkan reklame yang berdekatan atau di titik yang sama.
- MapView: menggambar semuanya dan mengubah klik/seret menjadi MapEvent.
"""

import math
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
OVERLAY_STYLE = {
    "zona": (theme.TEAL, 38, 150),
    "koridor": (theme.TEAL, 60, 0),
    "area_boleh": (theme.HIJAU_BOLEH, 64, 0),
}
ROAD_STYLE = {  # tipe: (warna isi, warna tepi, lebar dasar px pada zoom 15)
    "tol": ((246, 214, 160), (205, 160, 90), 6),
    "jalan utama": (theme.PUTIH, (185, 198, 207), 7),
    "penghubung": (theme.PUTIH, (205, 214, 221), 5),
    "kecil": ((236, 239, 241), None, 3),
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
        self.mem = OrderedDict()
        self.mem_limit = mem_limit
        self.render_count = 0
        minx, miny, maxx, maxy = zones.batas.bounds
        self.ox, self.oy = minx, maxy
        self.overlay_geom = {"zona": zones.zona_500, "koridor": zones.koridor_25,
                             "area_boleh": zones.area_boleh}

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
            for ring in _lines(part.boundary) if not part.is_empty else []:
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
            w = max(1, int(round(base_w * scale)))
            geoms = part.geometry[part["tipe_jalan"] == tipe]
            lines = [ln for g in geoms for ln in _lines(g)]
            if edge and w >= 3:
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
                pygame.draw.rect(surf, theme.NAVY, (px - r, py - r, 2 * r, 2 * r), border_radius=2)
            else:
                self._draw_poly(surf, g, theme.NAVY, x0, y1, m, hole_color=theme.TANAH)


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


def draw_marker(surf, pos, status, selected=False, alpha=255):
    x, y = pos
    color = theme.STATUS_COLOR.get(status, theme.ABU_UMUM)
    if status == "Tidak diaudit":
        pygame.draw.circle(surf, color, pos, 4)
        return
    if selected:
        pygame.draw.circle(surf, color, pos, 15, 3)
    if status == "Tayang berakhir":
        s = pygame.Surface((20, 20), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, 110), (10, 10), 7)
        surf.blit(s, (x - 10, y - 10))
        return
    pygame.draw.circle(surf, theme.PUTIH, pos, 10)
    pygame.draw.circle(surf, color, pos, 8)
    if status == "Patuh":
        pygame.draw.lines(surf, theme.PUTIH, False, [(x - 4, y), (x - 1, y + 3), (x + 4, y - 3)], 2)
    else:
        icon = theme.STATUS_ICON.get(status, "")
        if icon:
            t = theme.font(12, bold=True).render(icon, True, theme.PUTIH)
            surf.blit(t, t.get_rect(center=(x, y)))


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
        for c in sorted(self.clusters, key=lambda c: (len(c.ids) > 1, rank.get(top_status(c), 0))):
            sx, sy = self.vp.world_to_screen(c.x, c.y)
            pos = (self.rect.x + sx, self.rect.y + sy)
            if len(c.ids) == 1:
                draw_marker(surface, pos, self.status[c.ids[0]], selected=c.ids[0] == self.selected_id)
            else:
                n = len(c.ids)
                r = 13 if n < 10 else 16 if n < 100 else 19
                ring = theme.MERAH if top_status(c) == "Melanggar" else theme.PUTIH
                pygame.draw.circle(surface, ring, pos, r + 3)
                pygame.draw.circle(surface, theme.NAVY, pos, r)
                if self.selected_id in c.ids:
                    pygame.draw.circle(surface, theme.NAVY, pos, r + 7, 2)
                t = theme.font(12, bold=True).render(str(n), True, theme.PUTIH)
                surface.blit(t, t.get_rect(center=pos))
        if self.pin is not None:
            sx, sy = self.vp.world_to_screen(*self.pin)
            px, py = self.rect.x + sx, self.rect.y + sy
            pygame.draw.circle(surface, theme.NAVY, (px, py - 18), 10)
            pygame.draw.polygon(surface, theme.NAVY, [(px - 7, py - 12), (px + 7, py - 12), (px, py)])
            pygame.draw.circle(surface, theme.PUTIH, (px, py - 18), 4)
        surface.set_clip(clip)

    def hit(self, local_pos, radius=14):
        best, best_d = None, radius + 1
        for c in self.clusters:
            sx, sy = self.vp.world_to_screen(c.x, c.y)
            d = math.hypot(sx - local_pos[0], sy - local_pos[1])
            if d < best_d:
                best, best_d = c, d
        return best

    def handle(self, event):
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
