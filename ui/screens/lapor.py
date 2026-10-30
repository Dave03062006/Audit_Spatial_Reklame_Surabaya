"""Tab Laporkan Reklame: tiga langkah (lokasi, isi, hasil) lalu kirim ke admin."""

import geopandas as gpd
import pygame
from shapely.geometry import Point

import gis
from ui import theme
from ui.screens.base import Screen, panel_bg, section_label
from ui.screens.panels import draw_alasan, note_box
from ui.widgets import Button, Dropdown, TextInput, text, text_block

KATEGORI_LAPOR = ["Rokok", "Rokok elektronik", "Minuman beralkohol", "Umum"]
STEP_TITLES = ["Lokasi", "Isi reklame", "Kirim"]


class LaporWizard:
    def __init__(self, app):
        self.app = app
        self.reset()

    def reset(self):
        self.step = 1
        self.pin = None
        self.info = {}
        self.isi = ""
        self.kategori = "Rokok"
        self.nama = ""
        self.error = None

    def set_pin(self, x, y):
        self.pin = (x, y)
        self.app.map.pin = self.pin
        self.info = gis.nearest_info(Point(x, y), self.app.zones)
        self.app.map.measures = self.app.measures_for(x, y, self.info)
        self.error = None

    def next(self):
        if self.step == 1 and self.pin is None:
            self.error = "Klik peta untuk menandai lokasi reklame."
        elif self.step == 2 and not self.isi.strip():
            self.error = "Isi teks atau merek pada reklame."
        else:
            if self.step == 2:
                try:
                    self.kategori = gis.normalize_kategori(self.kategori)
                except ValueError:
                    self.error = "Pilih kategori reklame."
                    return self.error
            self.error = None
            self.step = min(3, self.step + 1)
        return self.error

    def back(self):
        self.error = None
        self.step = max(1, self.step - 1)

    def hasil(self):
        pt = Point(*self.pin)
        codes = gis.check_point(pt, self.kategori, self.app.zones)
        if not codes:
            return codes, ["Tidak ditemukan dugaan pelanggaran."]
        return codes, gis.alasan_text(codes, gis.nearest_info(pt, self.app.zones))

    def kirim(self):
        codes, _ = self.hasil()
        ll = gpd.GeoSeries([Point(*self.pin)], crs=gis.CRS_METER).to_crs(gis.CRS_SOURCE).iloc[0]
        rid = self.app.store.add_laporan(round(ll.y, 7), round(ll.x, 7), self.isi.strip(), self.kategori,
                                         codes, self.nama.strip() or None)
        self.reset()
        self.app.map.pin = None
        self.app.map.measures = []
        self.app.toast.show("Laporan terkirim. Menunggu verifikasi admin.")
        return rid


class LaporScreen(Screen):
    name = "Laporkan Reklame"

    def __init__(self, app):
        super().__init__(app)
        self.wizard = LaporWizard(app)
        r = app.right_rect
        x, w = r.x + 20, r.width - 40
        self.isi = TextInput((x, r.y + 160, w, 44), "Teks atau merek, mis. SAMPOERNA")
        self.kategori = Dropdown((x, r.y + 244, w, 44), KATEGORI_LAPOR, "Rokok")
        self.nama = TextInput((x, r.y + 328, w, 44), "Nama Anda (boleh dikosongkan)")
        by = r.bottom - 64
        self.back_btn = Button((x, by, 100, 44), "Kembali", self.back, kind="secondary")
        self.next_btn = Button((x + 112, by, w - 112, 44), "Lanjut", self.forward)

    def on_enter(self):
        self.wizard.reset()

    def back(self):
        self.wizard.back()

    def forward(self):
        w = self.wizard
        w.isi, w.kategori, w.nama = self.isi.value, self.kategori.value, self.nama.value
        if w.step == 3:
            w.kirim()
            self.isi.value = self.nama.value = ""
            self.kategori.value = "Rokok"
            return
        w.next()

    def on_map_event(self, ev):
        if self.wizard.step == 1 and ev.kind in ("empty", "marker"):
            self.wizard.set_pin(ev.x, ev.y)

    def draw_right(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        w = self.wizard
        x, width = rect.x + 20, rect.width - 40
        text(surface, "Laporkan Reklame", (x, rect.y + 20), 18, theme.NAVY, bold=True)
        # penanda langkah 1-2-3
        sw = (width - 16) // 3
        for i, title in enumerate(STEP_TITLES, start=1):
            sx = x + (i - 1) * (sw + 8)
            active = i == w.step
            done = i < w.step
            color = theme.NAVY if active or done else theme.GARIS
            pygame.draw.rect(surface, color, (sx, rect.y + 56, sw, 6), border_radius=3)
            text(surface, f"{i}. {title}", (sx, rect.y + 70), 12, theme.NAVY if active else theme.TEKS_LABEL,
                 bold=active, max_w=sw)

        if w.step == 1:
            text_block(surface, "Klik peta tepat di lokasi reklame. Geser atau perbesar peta bila perlu. "
                                "Titik merah dan biru adalah reklame yang sudah tercatat.",
                       (x, rect.y + 110), width, 14, theme.TEKS_SEKUNDER)
            if w.pin:
                text(surface, "Lokasi sudah ditandai", (x, rect.y + 196), 14, theme.TEKS, bold=True)
                text_block(surface, "Garis di peta menunjukkan jaraknya ke sekolah dan jalan utama terdekat. "
                                    "Klik tempat lain untuk memindahkan.", (x, rect.y + 220), width, 13,
                           theme.TEKS_SEKUNDER)
            else:
                text(surface, "Belum ada lokasi", (x, rect.y + 196), 14, theme.TEKS_LABEL)
        elif w.step == 2:
            text(surface, "Teks atau merek pada reklame", (x, rect.y + 136), 13, theme.TEKS_LABEL, bold=True)
            self.isi.error = w.error is not None and "Isi teks" in (w.error or "")
            self.isi.draw(surface)
            text(surface, "Kategori", (x, rect.y + 220), 13, theme.TEKS_LABEL, bold=True)
            text(surface, "Nama pelapor (opsional)", (x, rect.y + 304), 13, theme.TEKS_LABEL, bold=True)
            self.nama.draw(surface)
            self.kategori.draw(surface)
        else:
            codes, _ = w.hasil()
            text(surface, w.isi, (x, rect.y + 104), 17, theme.TEKS, bold=True, max_w=width)
            text(surface, w.kategori, (x, rect.y + 128), 13, theme.TEKS_SEKUNDER)
            section_label(surface, "Hasil cek otomatis", (x, rect.y + 160))
            y = rect.y + 186
            if w.kategori in gis.KATEGORI_AUDIT or w.kategori == gis.KATEGORI_ALKOHOL:
                y = draw_alasan(surface, x, y, width, w.kategori, codes, w.info)
            else:
                y = note_box(surface, "Reklame umum tidak diperiksa terhadap aturan rokok atau alkohol.", x, y, width)
            text_block(surface, "Ini dugaan awal. Admin akan memeriksa laporan sebelum masuk ke data resmi.",
                       (x, y + 4), width, 13, theme.TEKS_LABEL)
        if w.error:
            text_block(surface, w.error, (x, rect.bottom - 110), width, 14, theme.MERAH)
        self.back_btn.enabled = w.step > 1
        self.next_btn.label = "Kirim laporan" if w.step == 3 else "Lanjut"
        self.back_btn.draw(surface)
        self.next_btn.draw(surface)

    def draw_overlay(self, surface):
        if self.wizard.step == 2:
            self.kategori.draw_overlay(surface)

    def handle_right(self, event):
        if self.wizard.step == 2:
            if self.kategori.handle(event):
                return True
            for t in (self.isi, self.nama):
                if t.handle(event) == "submit":
                    self.forward()
                    return True
            if event.type in (pygame.TEXTINPUT, pygame.KEYDOWN) and (self.isi.focused or self.nama.focused):
                return True
        for b in (self.back_btn, self.next_btn):
            if b.handle(event):
                return True
        return self.app.right_rect.collidepoint(getattr(event, "pos", (-1, -1)))
