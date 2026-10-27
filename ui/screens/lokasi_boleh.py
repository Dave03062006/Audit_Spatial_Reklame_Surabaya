"""Tab Lokasi yang Boleh: area di luar radius 500 m sekolah dan di luar koridor jalan utama."""

import pygame

from gis import KATEGORI_AUDIT
from ui import theme
from ui.screens.base import Screen, markers_from, panel_bg
from ui.widgets import text, text_block

NOTE = ("Area hijau memenuhi syarat jarak PP 28/2024 untuk iklan rokok dan rokok elektronik: "
        "di luar radius 500 m dari sekolah dan di luar koridor jalan utama. "
        "Reklame minuman beralkohol dilarang di seluruh Surabaya (Perda 5/2019), jadi tidak ada lokasi yang boleh. "
        "Pemasang tetap wajib mengurus izin Pemkot.")


class LokasiBolehScreen(Screen):
    name = "Lokasi yang Boleh"

    def markers(self):
        rows = [r for r in self.app.audit.values()
                if r["status"] == "Patuh" and r.get("kategori_materi") in KATEGORI_AUDIT]
        return markers_from(rows)

    def overlays(self):
        return {"area_boleh"}

    def draw_right(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        text(surface, "Lokasi yang Boleh", (x, rect.y + 20), 18, theme.NAVY, bold=True)
        y = text_block(surface, NOTE, (x, rect.y + 54), w, 14, theme.TEKS_SEKUNDER)
        pygame.draw.rect(surface, (*theme.HIJAU_BOLEH,), (x, y + 14, 22, 14), border_radius=3)
        text(surface, "Area yang boleh", (x + 32, y + 21), 14, anchor="midleft")
        n = len(self.markers())
        y = text_block(surface, f"{n} reklame rokok dan rokok elektronik terpasang sudah berada di area ini "
                                "(titik biru).", (x, y + 44), w, 14, theme.TEKS)
        if self.app.selected_ids:
            sub = pygame.Rect(rect.x, y + 12, rect.width, rect.bottom - y - 12)
            pygame.draw.line(surface, theme.GARIS, (x, sub.y), (x + w, sub.y))
            self.app.detail_panel.draw(surface, sub)
