"""Tab Verifikasi (admin): terima atau tolak laporan warga."""

import pygame
from shapely.geometry import Point

import gis
from export import pasal_text
from ui import theme
from ui.screens.base import Screen, panel_bg
from ui.screens.panels import draw_alasan
from ui.widgets import Button, Modal, TextInput, text, text_block


class TolakModal:
    def __init__(self, screen):
        self.screen = screen
        self.frame = Modal("Tolak laporan", (480, 300))
        r = self.frame.rect
        self.alasan = TextInput((r.x + 24, r.y + 120, r.width - 48, 44), "Alasan penolakan")
        self.alasan.focused = True
        self.no = Button((r.x + 24, r.bottom - 68, 120, 44), "Batal", self.close, kind="secondary")
        self.yes = Button((r.right - 168, r.bottom - 68, 144, 44), "Tolak", self.submit, kind="danger")
        self.error = None

    def close(self):
        self.screen.app.modal = None

    def submit(self):
        self.error = self.screen.tolak(self.alasan.value)
        if self.error is None:
            self.close()

    def draw(self, surface):
        body = self.frame.draw_frame(surface)
        text(surface, "Tulis alasan singkat. Alasan ini disimpan bersama laporan.", (body.x, body.y + 6), 14,
             theme.TEKS_SEKUNDER, max_w=body.width)
        self.alasan.error = bool(self.error)
        self.alasan.draw(surface)
        if self.error:
            text(surface, self.error, (body.x, self.alasan.rect.bottom + 10), 14, theme.MERAH)
        self.no.draw(surface)
        self.yes.draw(surface)

    def handle(self, event):
        if self.alasan.handle(event) == "submit":
            self.submit()
            return
        self.no.handle(event) or self.yes.handle(event)


class VerifikasiScreen(Screen):
    name = "Verifikasi"

    def __init__(self, app):
        super().__init__(app)
        r = app.right_rect
        x, w = r.x + 20, r.width - 40
        by = r.bottom - 64
        self.tolak_btn = Button((x, by, (w - 8) // 2, 44), "Tolak", self.open_tolak, kind="secondary")
        self.terima_btn = Button((x + (w + 8) // 2, by, (w - 8) // 2, 44), "Terima", self.terima)
        self.back_btn = Button((x, r.y + 16, 110, 44), "‹ Daftar", self.deselect, kind="secondary", size=13)
        self.current = None
        self.pin = None
        self.card_rects = []

    def pending(self):
        return [r for r in self.app.store.laporan() if r["status"] == "menunggu"]

    def on_enter(self):
        self.deselect()

    def deselect(self):
        self.current, self.pin = None, None
        self.app.map.pin = None

    def select_report(self, rid):
        lap = [r for r in self.pending() if r["id"] == rid][0]
        self.current = lap
        pt = gis.load_reklame([{"id": rid, "latitude": lap["lat"], "longitude": lap["lon"]}]).geometry.iloc[0]
        self.pin = (pt.x, pt.y)
        self.app.map.pin = self.pin
        self.app.vp.fly_to(pt.x, pt.y, 16)

    def on_map_event(self, ev):
        if self.current is not None and ev.kind == "empty":
            self.pin = (ev.x, ev.y)
            self.app.map.pin = self.pin
        else:
            self.app.select_from_map(ev)

    def terima(self):
        if self.current is None:
            return None
        lat, lon = gis.to_latlon(*self.pin)
        new_id = self.app.store.terima_laporan(self.current["id"], oleh=self.app.admin_name, lat=lat, lon=lon)
        self.app.recheck(new_id)
        self.deselect()
        self.app.toast.show(f"Laporan diterima sebagai {new_id}.")
        return new_id

    def open_tolak(self):
        if self.current is not None:
            self.app.modal = TolakModal(self)

    def tolak(self, alasan):
        try:
            self.app.store.tolak_laporan(self.current["id"], oleh=self.app.admin_name, alasan=alasan)
        except ValueError as e:
            return str(e)
        self.deselect()
        self.app.toast.show("Laporan ditolak.")
        return None

    def draw_right(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        self.card_rects = []
        if self.current is None:
            items = self.pending()
            text(surface, f"Laporan menunggu ({len(items)})", (x, rect.y + 20), 18, theme.NAVY, bold=True)
            if not items:
                text_block(surface, "Tidak ada laporan yang menunggu verifikasi.", (x, rect.y + 60), w, 14,
                           theme.TEKS_SEKUNDER)
            y = rect.y + 60
            for lap in items[:9]:
                cr = pygame.Rect(x, y, w, 70)
                hover = cr.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, theme.LATAR if hover else theme.PUTIH, cr, border_radius=8)
                pygame.draw.rect(surface, theme.GARIS, cr, 1, border_radius=8)
                text(surface, lap["isi_reklame"], (cr.x + 12, cr.y + 8), 15, bold=True, max_w=w - 24)
                hasil = pasal_text(lap["hasil_cek"]) or "tanpa dugaan pelanggaran"
                text(surface, f"{lap['kategori_materi']} · {hasil}", (cr.x + 12, cr.y + 30), 12,
                     theme.MERAH if lap["hasil_cek"] else theme.TEKS_SEKUNDER, max_w=w - 24)
                text(surface, f"{lap['waktu'][:16].replace('T', ' ')} · {lap.get('nama_pelapor') or 'anonim'}",
                     (cr.x + 12, cr.y + 48), 12, theme.TEKS_LABEL, max_w=w - 24)
                self.card_rects.append((cr, lap["id"]))
                y += 78
            return
        lap = self.current
        self.back_btn.draw(surface)
        y = text_block(surface, lap["isi_reklame"], (x, rect.y + 76), w, 20, bold=True)
        y = text_block(surface, f"Kategori: {lap['kategori_materi']} · Pelapor: {lap.get('nama_pelapor') or 'anonim'}",
                       (x, y + 4), w, 13, theme.TEKS_SEKUNDER)
        y = text_block(surface, f"Dikirim {lap['waktu'].replace('T', ' ')}", (x, y), w, 13, theme.TEKS_SEKUNDER)
        codes = gis.check_point(Point(*self.pin), lap["kategori_materi"], self.app.zones)
        info = gis.nearest_info(Point(*self.pin), self.app.zones)
        y += 14
        if lap["kategori_materi"] in gis.KATEGORI_AUDIT or lap["kategori_materi"] == gis.KATEGORI_ALKOHOL:
            y = draw_alasan(surface, x, y, w, lap["kategori_materi"], codes, info)
        else:
            y = text_block(surface, "Reklame umum, tidak diperiksa.", (x, y), w, 13, theme.TEKS) + 6
        text_block(surface, "Klik peta untuk memindahkan titik bila lokasi laporan kurang tepat, lalu tekan Terima.",
                   (x, y + 10), w, 13, theme.TEKS_LABEL)
        self.tolak_btn.draw(surface)
        self.terima_btn.draw(surface)

    def handle_right(self, event):
        if self.current is None:
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for cr, rid in self.card_rects:
                    if cr.collidepoint(event.pos):
                        self.select_report(rid)
                        return True
        else:
            for b in (self.back_btn, self.tolak_btn, self.terima_btn):
                if b.handle(event):
                    return True
        return self.app.right_rect.collidepoint(getattr(event, "pos", (-1, -1)))
