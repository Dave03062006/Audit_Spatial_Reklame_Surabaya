"""Audit Spasial Reklame Rokok dan Alkohol Dekat Sekolah Surabaya.

Jalankan:  python app.py
"""

import sys
from datetime import date
from pathlib import Path

import pygame

import gis
import search
from storage import ORIGINAL_NAME, LoginGuard, Store
from ui import theme
from ui.map_view import MapView, TileCache, Viewport
from ui.screens.loading import LoadingScreen, Loader
from ui.screens.panels import DetailPanel, GuideCard, LeftPanel
from ui.screens.peta import PetaScreen
from ui.screens.setup_admin import SetupAdmin
from ui.screens.tabel import TabelScreen
from ui.widgets import Button, Toast, text

PUBLIC_TABS = ["Peta", "Tabel Pelanggaran", "Lokasi yang Boleh", "Laporkan Reklame"]
ADMIN_TABS = ["Kelola", "Verifikasi", "Perlu Cek"]


class App:
    def __init__(self, base_dir, today=None, headless=False, fetcher=None):
        self.base = Path(base_dir)
        self.today = today or date.today()
        self.headless = headless
        pygame.init()
        self.screen = pygame.display.set_mode(theme.WINDOW)
        pygame.display.set_caption("Audit Reklame Surabaya")
        pygame.key.start_text_input()
        self.clock = pygame.time.Clock()
        self.running = True

        self.store = Store(self.base / "data")
        self.cache_dir = self.base / "cache"
        self.reklame_path = self.base / "data" / ORIGINAL_NAME
        self.toast = Toast()
        self.login_guard = LoginGuard()

        self.role, self.admin_name = "warga", None
        self.tab = "Peta"
        self.layers = {"zona": True, "koridor": True, "rokok": True, "umum": False}
        self.selected_ids = []
        self.search_results, self.search_message = [], ""
        self.modal = None
        self.guide_open = False
        self._detail_cache = {}
        self.markers_dirty = True

        self.left_rect = pygame.Rect(0, theme.TOPBAR_H, theme.LEFT_W, theme.WINDOW[1] - theme.TOPBAR_H)
        self.right_rect = pygame.Rect(theme.WINDOW[0] - theme.RIGHT_W, theme.TOPBAR_H, theme.RIGHT_W,
                                      theme.WINDOW[1] - theme.TOPBAR_H)
        self.map_rect = pygame.Rect(self.left_rect.right, theme.TOPBAR_H,
                                    self.right_rect.x - self.left_rect.right, self.left_rect.height)
        self.content_rect = pygame.Rect(0, theme.TOPBAR_H, theme.WINDOW[0], self.left_rect.height)

        self.loader = Loader(self.cache_dir, self.reklame_path, fetcher=fetcher, sync=headless)
        self.loading_screen = LoadingScreen(self)
        self.state = "loading"
        self.loader.start()
        self._check_loader()

    # ------------------------------------------------------------
    # Memuat data
    # ------------------------------------------------------------
    def retry_loading(self):
        self.state = "loading"
        self.loader.start()
        self._check_loader()

    def _check_loader(self):
        if self.state == "loading" and self.loader.done:
            self._after_load(self.loader.zones)

    def _after_load(self, zones):
        self.zones = zones
        rows = {r["id"]: r for r in self.store.reklame()}
        reklame = gis.load_reklame(list(rows.values()))
        audit_gdf = gis.audit_all(reklame, zones, self.today)
        self.audit = {}
        for id, p, st, geom in zip(audit_gdf.index, audit_gdf["pelanggaran"], audit_gdf["status"],
                                   audit_gdf.geometry):
            rec = dict(rows[id])  # nilai asli dari Store, tanpa NaN dari pandas
            rec.update(x=geom.x, y=geom.y, pelanggaran=p, status=st)
            self.audit[id] = rec
        self.search_index = search.build_index(reklame, zones.jalan)
        self.tiles = TileCache(zones, self.cache_dir)
        c = zones.batas.centroid
        self.vp = Viewport(c.x, c.y, 12, self.map_rect.size)
        self.map = MapView(self.map_rect, zones, self.tiles, self.vp)
        self.left_panel = LeftPanel(self)
        self.detail_panel = DetailPanel(self)
        self.guide = GuideCard(self)
        self.screens = {}
        self.register_screens()
        self.setup = SetupAdmin(self)
        self.guide_open = not self.store.settings().get("panduan_dilihat", False)
        self.state = "main" if self.store.users_exist() else "setup_admin"
        self._build_topbar()
        self.markers_dirty = True

    def register_screens(self):
        self.screens["Peta"] = PetaScreen(self)
        self.screens["Tabel Pelanggaran"] = TabelScreen(self)

    # ------------------------------------------------------------
    # Data audit
    # ------------------------------------------------------------
    def counts(self):
        c = {s: 0 for s in gis.STATUS}
        c["rokok_vape"] = 0
        for r in self.audit.values():
            k = r.get("kategori_materi")
            if k in gis.KATEGORI_AUDIT:
                c["rokok_vape"] += 1
            if k in gis.KATEGORI_AUDIT or k == gis.KATEGORI_ALKOHOL or r["status"] == "Perlu cek":
                c[r["status"]] += 1
        return c

    def recheck(self, id):
        row = self.store.get_reklame(id)
        self._detail_cache.pop(id, None)
        if row.get("dihapus") or row.get("latitude") is None:
            self.audit.pop(id, None)
            self.selected_ids = [i for i in self.selected_ids if i != id]
        else:
            pt, p, status = gis.recheck_row(row, self.zones, self.today)
            rec = dict(row)
            rec.update(x=pt.x, y=pt.y, pelanggaran=p, status=status)
            self.audit[id] = rec
        self.markers_dirty = True

    def detail_lines(self, id):
        if id in self._detail_cache:
            return self._detail_cache[id]
        r = self.audit[id]
        from shapely.geometry import Point
        info = gis.nearest_info(Point(r["x"], r["y"]), self.zones)
        st = r["status"]
        lines = []
        if st == "Perlu cek":
            lines.append(f"Kategori perlu dicek admin: {r.get('perlu_cek_manual')}.")
        elif st == "Tidak diaudit":
            lines.append("Reklame umum, tidak termasuk aturan reklame rokok atau minuman beralkohol.")
        else:
            if st == "Tayang berakhir":
                lines.append(f"Masa tayang berakhir {r.get('tayang_selesai')}, tidak dihitung sebagai pelanggaran.")
            lines += gis.alasan_text(r["pelanggaran"], info)
            if not r["pelanggaran"]:
                parts = []
                if info["sekolah_jarak_m"] is not None:
                    parts.append(f"{info['sekolah_jarak_m']} m dari sekolah terdekat ({info['sekolah_nama']})")
                if info["jalan_utama_jarak_m"] is not None:
                    parts.append(f"{info['jalan_utama_jarak_m']} m dari jalan utama")
                lines.append("Tidak ditemukan pelanggaran: " + ", ".join(parts) + ".")
        self._detail_cache[id] = lines
        return lines

    def admin_detail_actions(self, id):
        return []

    # ------------------------------------------------------------
    # Peta dan pilihan
    # ------------------------------------------------------------
    def default_markers(self):
        from ui.screens.base import markers_from
        statuses = set()
        if self.layers["rokok"]:
            statuses |= {"Melanggar", "Patuh", "Perlu cek", "Tayang berakhir"}
        if self.layers["umum"]:
            statuses.add("Tidak diaudit")
        return markers_from(self.audit.values(), statuses)

    def layer_overlays(self):
        return {k for k in ("zona", "koridor") if self.layers[k]}

    def set_layer(self, key, value):
        self.layers[key] = value
        self.markers_dirty = True

    def select(self, ids):
        self.selected_ids = list(ids)
        self.map.selected_id = ids[0] if len(ids) == 1 else None

    def select_from_map(self, ev):
        if ev.kind == "marker":
            self.select(ev.ids)
        elif ev.kind == "empty":
            self.select([])

    def show_on_map(self, id):
        self.set_tab("Peta")
        r = self.audit[id]
        self.vp.fly_to(r["x"], r["y"], 16)
        self.select([id])

    def update_search(self, q):
        self.search_results = search.find(self.search_index, q)
        self.search_message = "" if self.search_results or not q.strip() else "Jalan tidak ditemukan"

    def pick_search(self, i):
        label, x, y = self.search_results[i]
        self.vp.fly_to(x, y, 16)
        self.left_panel.search.value = label
        self.left_panel.search.focused = False
        self.search_results = []

    # ------------------------------------------------------------
    # Tab dan peran
    # ------------------------------------------------------------
    def tab_names(self):
        names = PUBLIC_TABS + (ADMIN_TABS if self.role == "admin" else [])
        return [n for n in names if n in self.screens]

    def set_tab(self, name):
        if name not in self.screens:
            return
        self.tab = name
        self.select([])
        self.map.draggable_id = None
        self.map.pin = None
        self.screens[name].on_enter()
        self.markers_dirty = True
        self._build_topbar()

    @property
    def current(self):
        return self.screens[self.tab]

    def open_login(self):
        pass

    def logout(self):
        self.role, self.admin_name = "warga", None
        if self.tab in ADMIN_TABS:
            self.tab = "Peta"
        self.set_tab(self.tab)
        self.toast.show("Anda keluar dari mode admin.")

    def close_guide(self):
        self.guide_open = False
        s = self.store.settings()
        s["panduan_dilihat"] = True
        self.store.save_settings(s)

    def _build_topbar(self):
        self.tab_buttons = []
        x = 220
        f = theme.font(14, bold=True)
        for name in self.tab_names():
            w = f.size(name)[0] + 24
            kind = "tab_active" if name == self.tab else "tab"
            self.tab_buttons.append(Button((x, 6, w, 44), name, lambda n=name: self.set_tab(n), kind=kind))
            x += w + 4
        if self.role == "admin":
            self.auth_button = Button((theme.WINDOW[0] - 96, 6, 84, 44), "Keluar", self.logout, kind="secondary")
        else:
            self.auth_button = Button((theme.WINDOW[0] - 140, 6, 128, 44), "Masuk Admin", self.open_login,
                                      kind="secondary")

    # ------------------------------------------------------------
    # Loop utama
    # ------------------------------------------------------------
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.running = False
            return
        if self.state == "loading":
            self.loading_screen.handle(e)
            return
        if self.state == "setup_admin":
            self.setup.handle(e)
            return
        if self.guide_open:
            self.guide.handle(e)
            return
        if self.modal is not None:
            self.modal.handle(e)
            return
        for b in self.tab_buttons + [self.auth_button]:
            if b.handle(e):
                return
        scr = self.current
        if scr.uses_map:
            if scr.handle_left(e) or scr.handle_right(e):
                return
            if e.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION, pygame.MOUSEWHEEL):
                ev = self.map.handle(e)
                if ev is not None:
                    scr.on_map_event(ev)
        else:
            scr.handle_content(e)

    def draw(self):
        s = self.screen
        if self.state == "loading":
            self.loading_screen.draw(s)
            return
        if self.state == "setup_admin":
            self.setup.draw(s)
            self.toast.draw(s)
            return
        s.fill(theme.LATAR)
        scr = self.current
        if scr.uses_map:
            if self.markers_dirty:
                self.map.set_markers(scr.markers())
                self.markers_dirty = False
            self.map.draw(s, scr.overlays())
            scr.draw_left(s, self.left_rect)
            scr.draw_right(s, self.right_rect)
            self._draw_map_hint(s)
        else:
            scr.draw_content(s, self.content_rect)
        self._draw_topbar(s)
        if scr.uses_map:
            self.left_panel.draw_overlay(s)
        scr.draw_overlay(s)
        if self.modal is not None:
            self.modal.draw(s)
        if self.guide_open:
            self.guide.draw(s)
        self.toast.draw(s)

    def _draw_map_hint(self, s):
        r = pygame.Rect(self.map_rect.x + 12, self.map_rect.bottom - 44, 340, 32)
        pygame.draw.rect(s, theme.PUTIH, r, border_radius=8)
        pygame.draw.rect(s, theme.GARIS, r, 1, border_radius=8)
        text(s, f"Zoom {self.vp.zoom} · seret untuk geser, scroll untuk zoom", (r.x + 10, r.centery), 12,
             theme.TEKS_SEKUNDER, anchor="midleft", max_w=r.width - 16)

    def _draw_topbar(self, s):
        pygame.draw.rect(s, theme.NAVY, (0, 0, theme.WINDOW[0], theme.TOPBAR_H))
        text(s, "Audit Reklame Surabaya", (16, theme.TOPBAR_H // 2), 17, theme.PUTIH, bold=True, anchor="midleft")
        for b in self.tab_buttons:
            b.draw(s)
        if self.role == "admin":
            text(s, f"Admin · {self.admin_name}", (self.auth_button.rect.x - 12, theme.TOPBAR_H // 2), 13,
                 theme.PUTIH, anchor="midright")
        self.auth_button.draw(s)

    def step(self, events):
        for e in events:
            self.handle_event(e)
        self._check_loader()
        self.draw()
        pygame.display.flip()

    def run(self):
        while self.running:
            self.step(pygame.event.get())
            self.clock.tick(60)
        pygame.quit()


if __name__ == "__main__":
    App(Path(__file__).resolve().parent).run()
    sys.exit(0)
