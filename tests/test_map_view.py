import pygame
import pytest

from ui.map_view import (TILE_PX, ZOOM_MAX, ZOOM_MIN, MapView, Marker, TileCache,
                         Viewport, cluster, mpp)


@pytest.fixture(autouse=True)
def _pg():
    pygame.init()
    yield


def test_mpp_halves_per_zoom():
    assert mpp(14) == pytest.approx(mpp(13) / 2)
    assert 70 < mpp(11) < 80


def test_world_screen_roundtrip():
    vp = Viewport(1000.0, 2000.0, 14, (800, 600))
    assert vp.world_to_screen(1000.0, 2000.0) == (400, 300)
    px, py = vp.world_to_screen(1100.0, 2050.0)
    x, y = vp.screen_to_world(px, py)
    assert x == pytest.approx(1100.0, abs=mpp(14))
    assert y == pytest.approx(2050.0, abs=mpp(14))
    assert px > 400 and py < 300  # utara = atas layar


def test_zoom_at_keeps_point_under_cursor():
    vp = Viewport(1000.0, 2000.0, 14, (800, 600))
    before = vp.screen_to_world(600, 150)
    vp.zoom_at(600, 150, +1)
    assert vp.zoom == 15
    after = vp.screen_to_world(600, 150)
    assert after[0] == pytest.approx(before[0], abs=0.01)
    assert after[1] == pytest.approx(before[1], abs=0.01)


def test_zoom_clamped():
    vp = Viewport(0, 0, ZOOM_MAX, (100, 100))
    vp.zoom_at(50, 50, +1)
    assert vp.zoom == ZOOM_MAX
    vp.zoom = ZOOM_MIN
    vp.zoom_at(50, 50, -1)
    assert vp.zoom == ZOOM_MIN


def test_pan_moves_center():
    vp = Viewport(0.0, 0.0, 14, (100, 100))
    vp.pan(10, 0)  # seret peta ke kanan -> pusat bergeser ke barat
    assert vp.cx == pytest.approx(-10 * mpp(14))


def test_tile_written_to_disk_and_reused(tiny_zones, tmp_path):
    tc = TileCache(tiny_zones, tmp_path)
    s = tc.get(14, 0, 0)
    assert s.get_size() == (TILE_PX, TILE_PX)
    assert (tmp_path / "tiles" / "base" / "14" / "0_0.png").exists()
    assert tc.render_count == 1
    tc.get(14, 0, 0)
    assert tc.render_count == 1  # dari memori
    tc2 = TileCache(tiny_zones, tmp_path)
    tc2.get(14, 0, 0)
    assert tc2.render_count == 0  # dari disk


def test_tile_outside_bounds_is_blank(tiny_zones, tmp_path):
    tc = TileCache(tiny_zones, tmp_path)
    s = tc.get(14, 5000, -5000)
    assert s.get_size() == (TILE_PX, TILE_PX)
    overlay = tc.get(14, 5000, -5000, layer="zona")
    assert overlay.get_at((10, 10)).a == 0


def test_identical_coords_cluster_together():
    vp = Viewport(0, 0, 17, (800, 600))
    cl = cluster([("a", 5, 5), ("b", 5, 5), ("c", 5, 5)], vp)
    assert len(cl) == 1 and sorted(cl[0].ids) == ["a", "b", "c"]


def test_far_points_not_clustered():
    vp = Viewport(0, 0, 17, (800, 600))
    cl = cluster([("a", 0, 0), ("b", 200, 0)], vp)
    assert len(cl) == 2


def test_offscreen_points_skipped():
    vp = Viewport(0, 0, 17, (800, 600))
    assert cluster([("a", 100000, 0)], vp) == []


def _ev(kind, pos, button=1):
    return pygame.event.Event(kind, {"pos": pos, "button": button, "buttons": (1, 0, 0), "rel": (0, 0)})


def test_click_on_marker_returns_ids(tiny_zones, tmp_path):
    rect = pygame.Rect(100, 50, 800, 600)
    vp = Viewport(1300, 1000, 16, rect.size)
    mv = MapView(rect, tiny_zones, TileCache(tiny_zones, tmp_path), vp)
    mv.set_markers([Marker("r1", 1300, 1000, "Melanggar"), Marker("r2", 1400, 1000, "Patuh")])
    surf = pygame.Surface((1280, 800))
    mv.draw(surf, overlays={"zona"})
    sx, sy = vp.world_to_screen(1300, 1000)
    pos = (rect.x + sx, rect.y + sy)
    assert mv.handle(_ev(pygame.MOUSEBUTTONDOWN, pos)) is None
    ev = mv.handle(_ev(pygame.MOUSEBUTTONUP, pos))
    assert ev.kind == "marker" and ev.ids == ["r1"]


def test_click_empty_returns_world_xy(tiny_zones, tmp_path):
    rect = pygame.Rect(0, 0, 800, 600)
    vp = Viewport(1300, 1000, 16, rect.size)
    mv = MapView(rect, tiny_zones, TileCache(tiny_zones, tmp_path), vp)
    mv.set_markers([])
    mv.draw(pygame.Surface((800, 600)), overlays=set())
    mv.handle(_ev(pygame.MOUSEBUTTONDOWN, (400, 300)))
    ev = mv.handle(_ev(pygame.MOUSEBUTTONUP, (400, 300)))
    assert ev.kind == "empty"
    assert ev.x == pytest.approx(1300, abs=2) and ev.y == pytest.approx(1000, abs=2)


def test_drag_marker_emits_drag_end(tiny_zones, tmp_path):
    rect = pygame.Rect(0, 0, 800, 600)
    vp = Viewport(1300, 1000, 16, rect.size)
    mv = MapView(rect, tiny_zones, TileCache(tiny_zones, tmp_path), vp)
    mv.set_markers([Marker("r1", 1300, 1000, "Melanggar")])
    mv.draggable_id = "r1"
    mv.draw(pygame.Surface((800, 600)), overlays=set())
    mv.handle(_ev(pygame.MOUSEBUTTONDOWN, (400, 300)))
    mv.handle(_ev(pygame.MOUSEMOTION, (500, 300)))
    ev = mv.handle(_ev(pygame.MOUSEBUTTONUP, (500, 300)))
    assert ev.kind == "drag_end" and ev.ids == ["r1"]
    assert ev.x == pytest.approx(1300 + 100 * mpp(16), abs=2)
    assert vp.cx == 1300  # peta tidak ikut bergeser
