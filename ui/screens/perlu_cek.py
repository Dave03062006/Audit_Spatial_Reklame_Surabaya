"""Tab Perlu Cek (admin): tetapkan kategori untuk reklame yang namanya ambigu."""

import pygame

from ui import theme
from ui.screens.base import Screen, markers_from, panel_bg
from ui.widgets import Button, Dropdown, text, text_block

KATEGORI_CEK = ["Umum", "Rokok", "Rokok elektronik", "Minuman beralkohol"]


class PerluCekScreen(Screen):
    name = "Perlu Cek"

    def __init__(self, app):
        super().__init__(app)
        r = app.right_rect
        x, w = r.x + 20, r.width - 40
        self.kategori = Dropdown((x, r.bottom - 124, w, 44), KATEGORI_CEK, "Umum")
        self.save_btn = Button((x, r.bottom - 64, w, 44), "Simpan kategori", self.save_current)
        self.back_btn = Button((x, r.y + 16, 110, 44), "‹ Daftar", self.deselect, kind="secondary", size=13)
        self.current = None
        self.card_rects = []
        self.offset = 0

    def rows(self):
        return [r for r in self.app.audit.values() if r["status"] == "Perlu cek"]

    def markers(self):
        return markers_from(self.rows())

    def on_enter(self):
        self.deselect()

    def deselect(self):
        self.current = None

    def pick(self, id):
        self.current = id
        r = self.app.audit[id]
        self.kategori.value = r.get("kategori_materi") if r.get("kategori_materi") in KATEGORI_CEK else "Umum"
        self.app.vp.fly_to(r["x"], r["y"], 16)
        self.app.select([id])

    def confirm(self, id, kategori):
        self.app.store.update_reklame(id, {"kategori_materi": kategori, "kategori_dikonfirmasi": True},
                                      oleh=self.app.admin_name)
        self.app.recheck(id)
        self.app.toast.show(f"{id}: kategori {kategori}, status {self.app.audit[id]['status']}.")
        self.current = None

    def save_current(self):
        if self.current is not None:
            self.confirm(self.current, self.kategori.value)

    def on_map_event(self, ev):
        if ev.kind == "marker" and len(ev.ids) == 1:
            self.pick(ev.ids[0])

    def draw_right(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        self.card_rects = []
        if self.current is None:
            items = self.rows()
            text(surface, f"Perlu cek kategori ({len(items)})", (x, rect.y + 20), 18, theme.NAVY, bold=True)
            text_block(surface, "Nama reklame ini ambigu. Pilih satu untuk menetapkan kategorinya.",
                       (x, rect.y + 50), w, 13, theme.TEKS_SEKUNDER)
            y = rect.y + 96
            for r in items[:10]:
                cr = pygame.Rect(x, y, w, 60)
                hover = cr.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, theme.LATAR if hover else theme.PUTIH, cr, border_radius=8)
                pygame.draw.rect(surface, theme.GARIS, cr, 1, border_radius=8)
                text(surface, r.get("isi_reklame") or r["id"], (cr.x + 12, cr.y + 8), 14, bold=True, max_w=w - 24)
                text(surface, str(r.get("perlu_cek_manual")), (cr.x + 12, cr.y + 32), 12, theme.AMBER, max_w=w - 24)
                self.card_rects.append((cr, r["id"]))
                y += 66
            if len(items) > 10:
                text(surface, f"dan {len(items) - 10} lainnya (tampil setelah yang atas selesai).", (x, y + 4), 12,
                     theme.TEKS_LABEL, max_w=w)
            return
        r = self.app.audit[self.current]
        self.back_btn.draw(surface)
        y = text_block(surface, r.get("isi_reklame") or r["id"], (x, rect.y + 76), w, 20, bold=True)
        y = text_block(surface, r.get("alamat") or "-", (x, y + 4), w, 13, theme.TEKS_SEKUNDER)
        y = text_block(surface, f"Alasan dicek: {r.get('perlu_cek_manual')}", (x, y + 8), w, 13, theme.AMBER)
        text(surface, "Kategori yang benar", (x, self.kategori.rect.y - 22), 12, theme.TEKS_LABEL, bold=True)
        self.save_btn.draw(surface)
        self.kategori.draw(surface)

    def draw_overlay(self, surface):
        if self.current is not None:
            self.kategori.draw_overlay(surface)

    def handle_right(self, event):
        if self.current is None:
            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for cr, id in self.card_rects:
                    if cr.collidepoint(event.pos):
                        self.pick(id)
                        return True
        else:
            if self.kategori.handle(event):
                return True
            for b in (self.back_btn, self.save_btn):
                if b.handle(event):
                    return True
        return self.app.right_rect.collidepoint(getattr(event, "pos", (-1, -1)))
