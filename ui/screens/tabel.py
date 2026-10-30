"""Tab Tabel Pelanggaran: daftar yang bisa difilter, diurutkan, dan diekspor ke CSV."""

import pygame

from export import pasal_text, pelanggaran_csv
from gis import KATEGORI_ALKOHOL, RULE_SHORT
from ui import theme
from ui.screens.base import Screen
from ui.screens.panels import chip
from ui.widgets import Button, Dropdown, Table, TextInput, text

PASAL_OPTIONS = {"Semua pasal": None, "Ps. 449 (1) d": "449_1_d", "Ps. 449 (1) c": "449_1_c",
                 "Perda 5/2019": "perda_5_2019_23"}
KATEGORI_OPTIONS = ["Semua kategori", "Rokok", "Rokok elektronik", KATEGORI_ALKOHOL]


class TabelScreen(Screen):
    name = "Tabel Pelanggaran"
    uses_map = False

    def __init__(self, app):
        super().__init__(app)
        r = app.content_rect
        x, y = r.x + 24, r.y + 76
        self.kategori = Dropdown((x, y, 200, 44), KATEGORI_OPTIONS, KATEGORI_OPTIONS[0], lambda v: self.refresh())
        self.pasal = Dropdown((x + 212, y, 180, 44), list(PASAL_OPTIONS), "Semua pasal", lambda v: self.refresh())
        self.query = TextInput((x + 404, y, 300, 44), "Cari alamat atau isi reklame")
        self.export_btn = Button((r.right - 184, y, 160, 44), "Ekspor CSV", self.export)
        cols = [("id", "ID", 130), ("isi_reklame", "Isi reklame", 330), ("kategori_materi", "Kategori", 150),
                ("alamat", "Alamat", 360), ("pasal", "Pasal", 262)]
        self.table = Table((x, y + 60, r.width - 48, 40 + 40 * 12), cols, [], page_size=12)
        by = self.table.rect.bottom + 12
        self.prev = Button((x, by, 110, 44), "Sebelumnya", self.prev_page, kind="secondary", size=13)
        self.next = Button((x + 290, by, 110, 44), "Berikutnya", self.next_page, kind="secondary", size=13)

    def on_enter(self):
        self.refresh()

    def refresh(self):
        kat = self.kategori.value
        pasal = PASAL_OPTIONS[self.pasal.value]
        q = self.query.value.strip().lower()
        rows = []
        for r in self.app.audit.values():
            if r["status"] != "Melanggar":
                continue
            if kat != KATEGORI_OPTIONS[0] and r.get("kategori_materi") != kat:
                continue
            if pasal and pasal not in r["pelanggaran"]:
                continue
            if q and q not in str(r.get("alamat", "")).lower() and q not in str(r.get("isi_reklame", "")).lower():
                continue
            rows.append({**r, "pasal": pasal_text(r["pelanggaran"])})
        self.table.set_rows(rows)

    def prev_page(self):
        self.table.page = max(0, self.table.page - 1)

    def next_page(self):
        self.table.page = min(self.table.page_count - 1, self.table.page + 1)

    def export(self):
        p = pelanggaran_csv(list(self.app.audit.values()), self.app.zones, self.app.base / "exports", self.app.today)
        self.app.toast.show(f"Tersimpan: exports/{p.name}")

    def draw_cell(self, surface, key, row, rect):
        if key != "pasal":
            return False
        cx = rect.x + 12
        for code in row["pelanggaran"]:
            cx = chip(surface, RULE_SHORT[code], (cx, rect.centery), theme.MERAH, theme.MERAH_MUDA,
                      anchor="midleft").right + 6
        return True

    def draw_content(self, surface, rect):
        x = rect.x + 24
        title = text(surface, "Tabel Pelanggaran", (x, rect.y + 14), 34, theme.NAVY, display=True)
        n = theme.fmt(len(self.table.rows))
        text(surface, f"{n} reklame melanggar sesuai filter. Klik baris untuk melihatnya di peta.",
             (title.right + 16, title.centery + 2), 14, theme.TEKS_SEKUNDER, anchor="midleft")
        self.query.draw(surface)
        self.export_btn.draw(surface)
        self.table.draw(surface, cell_color=lambda k, r: theme.TEKS_LABEL if k == "id" else theme.TEKS,
                        cell_draw=self.draw_cell)
        if not self.table.rows:
            text(surface, "Tidak ada pelanggaran yang cocok dengan filter.", self.table.rect.center, 15,
                 theme.TEKS_LABEL, anchor="center")
        self.prev.enabled = self.table.page > 0
        self.next.enabled = self.table.page < self.table.page_count - 1
        self.prev.draw(surface)
        self.next.draw(surface)
        text(surface, f"Halaman {self.table.page + 1} dari {theme.fmt(self.table.page_count)}",
             (self.prev.rect.right + 90, self.prev.rect.centery), 14, theme.TEKS_SEKUNDER, anchor="center")
        self.kategori.draw(surface)
        self.pasal.draw(surface)

    def draw_overlay(self, surface):
        self.kategori.draw_overlay(surface)
        self.pasal.draw_overlay(surface)

    def handle_content(self, event):
        for d in (self.kategori, self.pasal):
            if d.handle(event):
                return True
        if self.query.handle(event) == "change":
            self.refresh()
            return True
        for b in (self.export_btn, self.prev, self.next):
            if b.handle(event):
                return True
        row = self.table.handle(event)
        if row is not None:
            self.app.show_on_map(row["id"])
            return True
        return False
