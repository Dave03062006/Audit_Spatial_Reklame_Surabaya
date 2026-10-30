"""Audit Spasial Reklame Rokok dan Alkohol Dekat Sekolah Surabaya.

Jalankan:  python app.py
"""

import sys
import time
from datetime import date
from pathlib import Path

import pygame

import gis
import search
from storage import ORIGINAL_NAME, LoginGuard, Store
from ui import theme
from ui.map_view import MapView, Measure, TileCache, Viewport
from ui.screens.loading import LoadingScreen, Loader
from ui.screens.panels import DetailPanel, GuideCard, LeftPanel
from ui.screens.perlu_cek import PerluCekScreen
from ui.screens.peta import PetaScreen
from ui.screens.setup_admin import SetupAdmin
from ui.screens.kelola import KelolaScreen
from ui.screens.lapor import LaporScreen
from ui.screens.login import LoginModal
from ui.screens.lokasi_boleh import LokasiBolehScreen
from ui.screens.tabel import TabelScreen
from ui.screens.verifikasi import VerifikasiScreen
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
        self._info_cache = {}
        self._badges, self._badges_at = {}, 0.0
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
        self.screens["Lokasi yang Boleh"] = LokasiBolehScreen(self)
        self.screens["Laporkan Reklame"] = LaporScreen(self)
        self.screens["Kelola"] = KelolaScreen(self)
        self.screens["Verifikasi"] = VerifikasiScreen(self)
        self.screens["Perlu Cek"] = PerluCekScreen(self)

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
        self._info_cache.pop(id, None)
        if row.get("dihapus") or row.get("latitude") is None:
            self.audit.pop(id, None)
            self.selected_ids = [i for i in self.selected_ids if i != id]
        else:
            pt, p, status = gis.recheck_row(row, self.zones, self.today)
            rec = dict(row)
            rec.update(x=pt.x, y=pt.y, pelanggaran=p, status=status)
            self.audit[id] = rec
        self.markers_dirty = True
        if id in self.selected_ids:
            self.select(self.selected_ids)   # garis ukur ikut pindah

    def info(self, id):
        """Sekolah dan jalan utama terdekat untuk satu reklame (disimpan supaya tidak dihitung tiap frame)."""
        if id not in self._info_cache:
            from shapely.geometry import Point
            r = self.audit[id]
            self._info_cache[id] = gis.nearest_info(Point(r["x"], r["y"]), self.zones)
        return self._info_cache[id]

    def measures_for(self, x, y, info):
        """Garis ukur di peta dari (x, y) ke sekolah dan jalan utama terdekat. Yang lebih dari 1 km tidak digambar."""
        out = []
        if info.get("sekolah_xy") and info["sekolah_jarak_m"] <= 1000:
            nama = info["sekolah_nama"]
            nama = nama if len(nama) <= 24 else nama[:23] + "…"
            out.append(Measure(x, y, *info["sekolah_xy"], f"{nama} · {theme.fmt(info['sekolah_jarak_m'])} m",
                               theme.TEAL_TUA))
        if info.get("jalan_utama_xy") and info["jalan_utama_jarak_m"] <= 1000:
            out.append(Measure(x, y, *info["jalan_utama_xy"],
                               f"Jalan utama · {theme.fmt(info['jalan_utama_jarak_m'])} m", theme.NAVY))
        return out

    def detail_lines(self, id):
        if id in self._detail_cache:
            return self._detail_cache[id]
        r = self.audit[id]
        info = self.info(id)
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
        if self.role != "admin":
            return []
        kelola = self.screens["Kelola"]

        def edit():
            self.set_tab("Kelola")
            kelola.start_edit(id)

        def move():
            self.set_tab("Kelola")
            kelola.start_move(id)

        actions = [("Ubah data", edit), ("Geser lokasi", move)]
        if self.tab == "Kelola":
            actions.append(("Hapus", lambda: kelola.request_delete(id)))
        return actions

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
        self.map.measures = []
        r = self.audit.get(ids[0]) if len(ids) == 1 else None
        if r is not None and r.get("kategori_materi") in gis.KATEGORI_AUDIT:
            self.map.measures = self.measures_for(r["x"], r["y"], self.info(r["id"]))

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
        self.modal = LoginModal(self)

    def login_as(self, username):
        self.role, self.admin_name = "admin", username
        self._build_topbar()
        self.toast.show(f"Masuk sebagai admin {username}.")

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

    def badges(self):
        """Angka kecil di tab admin: laporan menunggu dan reklame perlu cek. Dihitung ulang tiap detik."""
        if self.role != "admin":
            return {}
        if time.time() - self._badges_at > 1:
            self._badges = {"Verifikasi": sum(lap["status"] == "menunggu" for lap in self.store.laporan()),
                            "Perlu Cek": sum(r["status"] == "Perlu cek" for r in self.audit.values())}
            self._badges_at = time.time()
        return self._badges

    def _build_topbar(self):
        self.tab_buttons = []
        self._badges_at = 0
        self._tab_badges = dict(self.badges())
        self.admin_divider_x = None
        x = 168
        f = theme.font(14, bold=True)
        for name in self.tab_names():
            if name == ADMIN_TABS[0]:
                self.admin_divider_x = x + 6
                x += 16
            w = f.size(name)[0] + 28
            kind = "tab_active" if name == self.tab else "tab"
            self.tab_buttons.append(Button((x, 6, w, 50), name, lambda n=name: self.set_tab(n), kind=kind))
            x += w + 2 + (26 if self._tab_badges.get(name) else 0)
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

    def _draw_topbar(self, s):
        pygame.draw.rect(s, theme.NAVY, (0, 0, theme.WINDOW[0], theme.TOPBAR_H))
        text(s, "Audit Reklame", (16, 7), 24, theme.PUTIH, display=True)
        text(s, "Kota Surabaya", (17, 35), 11, theme.TAB_REDUP, bold=True)
        if self.admin_divider_x is not None:
            pygame.draw.line(s, theme.NAVY_2, (self.admin_divider_x, 14), (self.admin_divider_x, theme.TOPBAR_H - 14), 2)
        badges = self.badges()
        if badges != self._tab_badges:   # jumlah berubah: atur ulang lebar tab
            self._build_topbar()
        for b in self.tab_buttons:
            b.draw(s)
            n = badges.get(b.label)
            if n:
                f = theme.font(11, bold=True)
                r = pygame.Rect(0, 0, max(20, f.size(str(n))[0] + 10), 20)
                r.midleft = (b.rect.right - 4, b.rect.centery - 3)
                pygame.draw.rect(s, theme.AMBER, r, border_radius=10)
                text(s, n, r.center, 11, theme.PUTIH, bold=True, anchor="center")
        if self.role == "admin":
            ax = self.auth_button.rect.x - 12
            text(s, "ADMIN", (ax, 12), 10, theme.TAB_REDUP, bold=True, anchor="topright")
            text(s, self.admin_name, (ax, 26), 14, theme.PUTIH, bold=True, anchor="topright", max_w=120)
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
