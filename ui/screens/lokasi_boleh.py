"""Tab Lokasi yang Boleh: area di luar radius 500 m sekolah dan di luar koridor jalan utama."""

import pygame

from gis import KATEGORI_AUDIT
from ui import theme
from ui.screens.base import Screen, markers_from, panel_bg
from ui.widgets import text, text_block

NOTE = ("Area hijau memenuhi syarat jarak PP 28/2024 untuk iklan rokok dan rokok elektronik: "
        "di luar radius 500 m dari sekolah dan di luar koridor jalan utama.")
NOTE_ALKOHOL = ("Reklame minuman beralkohol dilarang di seluruh Surabaya (Perda 5/2019), jadi tidak ada lokasi "
                "yang boleh. Pemasang tetap wajib mengurus izin Pemkot.")
HIJAU_ISI = (205, 230, 219)


class LokasiBolehScreen(Screen):
    name = "Lokasi yang Boleh"

    def markers(self):
        rows = [r for r in self.app.audit.values()
                if r["status"] == "Patuh" and r.get("kategori_materi") in KATEGORI_AUDIT]
        return markers_from(rows)

    def overlays(self):
        # zona larangan ikut digambar bila dicentang, supaya area boleh dan area dilarang terbaca bersama
        return {"area_boleh"} | self.app.layer_overlays()

    def draw_right(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        text(surface, "Lokasi yang Boleh", (x, rect.y + 20), 18, theme.NAVY, bold=True)
        y = text_block(surface, NOTE, (x, rect.y + 54), w, 14, theme.TEKS_SEKUNDER)
        for i, (fill, edge, label) in enumerate([(HIJAU_ISI, theme.HIJAU_BOLEH, "Boleh untuk rokok dan vape"),
                                                 (theme.TEAL_MUDA, theme.TEAL, "Dilarang: zona sekolah, koridor")]):
            sw = pygame.Rect(x, y + 14 + i * 28, 24, 16)
            pygame.draw.rect(surface, fill, sw, border_radius=3)
            pygame.draw.rect(surface, edge, sw, 2, border_radius=3)
            text(surface, label, (x + 34, sw.centery), 14, anchor="midleft")
        y += 14 + 2 * 28 + 8
        n = len(self.markers())
        r = text(surface, theme.fmt(n), (x, y), 34, theme.BIRU_PATUH, display=True)
        y = text_block(surface, "reklame rokok dan vape sudah terpasang di area hijau (titik biru).",
                       (r.right + 10, y + 4), x + w - r.right - 10, 13, theme.TEKS)
        y = max(y, r.bottom) + 10
        y = text_block(surface, NOTE_ALKOHOL, (x, y), w, 12, theme.TEKS_LABEL)
        if self.app.selected_ids:
            sub = pygame.Rect(rect.x, y + 12, rect.width, rect.bottom - y - 12)
            pygame.draw.line(surface, theme.GARIS, (x, sub.y), (x + w, sub.y))
            self.app.detail_panel.draw(surface, sub)
