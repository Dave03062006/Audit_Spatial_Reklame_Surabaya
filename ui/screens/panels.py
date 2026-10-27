"""Panel kiri (cari, ringkasan, lapisan, keterangan), panel kanan (detail), dan kartu panduan."""

import pygame

from ui import theme
from ui.map_view import draw_marker
from ui.screens.base import panel_bg, section_label
from ui.widgets import Button, Checkbox, Modal, TextInput, status_badge, text, text_block, wrap


class LeftPanel:
    def __init__(self, app):
        self.app = app
        r = app.left_rect
        x, w = r.x + 16, r.width - 32
        self.search = TextInput((x, r.y + 38, w, 44), "Cari jalan atau kelurahan")
        app.search_box = self.search
        y = r.y + 270
        self.checks = []
        labels = [("zona", "Zona 500 m sekolah"), ("koridor", "Koridor jalan utama 25 m"),
                  ("rokok", "Rokok, vape & alkohol"), ("umum", "Reklame umum")]
        for i, (key, label) in enumerate(labels):
            cb = Checkbox((x, y + i * 44, w, 44), label, app.layers[key],
                          on_change=lambda v, k=key: app.set_layer(k, v))
            self.checks.append(cb)

    def result_rect(self, i):
        return pygame.Rect(self.search.rect.x, self.search.rect.bottom + 4 + i * 40, 300, 40)

    def draw(self, surface, rect):
        panel_bg(surface, rect)
        x = rect.x + 16
        section_label(surface, "Cari jalan", (x, rect.y + 16))
        self.search.draw(surface)

        section_label(surface, "Ringkasan", (x, rect.y + 100))
        c = self.app.counts()
        tiles = [("Melanggar", c["Melanggar"], theme.MERAH_MUDA, theme.MERAH),
                 ("Patuh", c["Patuh"], theme.BIRU_MUDA, theme.BIRU_PATUH),
                 ("Rokok + vape", c["rokok_vape"], theme.LATAR, theme.NAVY),
                 ("Perlu cek", c["Perlu cek"], theme.AMBER_MUDA, theme.AMBER)]
        for i, (label, n, bg, fg) in enumerate(tiles):
            tr = pygame.Rect(x + (i % 2) * 112, rect.y + 120 + (i // 2) * 66, 104, 58)
            pygame.draw.rect(surface, bg, tr, border_radius=8)
            text(surface, f"{n:,}".replace(",", "."), (tr.x + 10, tr.y + 8), 20, fg, bold=True)
            text(surface, label, (tr.x + 10, tr.y + 36), 12, theme.TEKS_SEKUNDER)

        section_label(surface, "Lapisan", (x, rect.y + 252))
        for cb in self.checks:
            cb.draw(surface)

        y = rect.y + 452
        section_label(surface, "Keterangan", (x, y))
        y += 26
        for status, desc in [("Melanggar", "Melanggar"), ("Patuh", "Patuh"), ("Perlu cek", "Perlu cek admin"),
                             ("Tayang berakhir", "Tayang berakhir"), ("Tidak diaudit", "Reklame umum")]:
            draw_marker(surface, (x + 10, y + 12), status)
            text(surface, desc, (x + 30, y + 12), 14, theme.TEKS, anchor="midleft")
            y += 28
        pygame.draw.rect(surface, theme.TEAL, (x, y + 4, 20, 14), 2, border_radius=7)
        text(surface, "Radius 500 m sekolah", (x + 30, y + 11), 14, theme.TEKS, anchor="midleft")
        y += 28
        pygame.draw.rect(surface, theme.NAVY, (x + 3, y + 4, 14, 12), border_radius=2)
        text(surface, "Sekolah", (x + 30, y + 10), 14, theme.TEKS, anchor="midleft")

    def draw_overlay(self, surface):
        if not self.search.focused or not self.search.value.strip():
            return
        res = self.app.search_results
        if not res:
            r = self.result_rect(0)
            pygame.draw.rect(surface, theme.PUTIH, r, border_radius=6)
            pygame.draw.rect(surface, theme.GARIS, r, 1, border_radius=6)
            text(surface, self.app.search_message, (r.x + 12, r.centery), 14, theme.TEKS_LABEL, anchor="midleft")
            return
        for i, (label, _, _) in enumerate(res):
            r = self.result_rect(i)
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, theme.LATAR if hover else theme.PUTIH, r)
            pygame.draw.rect(surface, theme.GARIS, r, 1)
            text(surface, label, (r.x + 12, r.centery), 14, anchor="midleft", max_w=r.width - 20)

    def handle(self, event):
        # klik hasil pencarian lebih dulu, karena kotaknya menutupi peta
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.search.focused
                and self.search.value.strip()):
            for i in range(len(self.app.search_results)):
                if self.result_rect(i).collidepoint(event.pos):
                    self.app.pick_search(i)
                    return True
        res = self.search.handle(event)
        if res == "change":
            self.app.update_search(self.search.value)
            return True
        if res == "submit":
            if self.app.search_results:
                self.app.pick_search(0)
            return True
        if event.type in (pygame.TEXTINPUT, pygame.KEYDOWN) and self.search.focused:
            return True
        for cb in self.checks:
            if cb.handle(event):
                return True
        return False


class DetailPanel:
    def __init__(self, app):
        self.app = app
        self.buttons = []
        self.list_buttons = []

    def draw(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        ids = self.app.selected_ids
        self.buttons, self.list_buttons = [], []
        if not ids:
            text(surface, "Detail reklame", (x, rect.y + 20), 18, theme.NAVY, bold=True)
            text_block(surface, "Klik titik di peta untuk melihat detail dan alasan pelanggarannya. "
                                "Angka di lingkaran biru tua adalah jumlah reklame di sekitar titik itu; "
                                "perbesar peta atau klik lingkarannya untuk melihat daftarnya.",
                       (x, rect.y + 56), w, 14, theme.TEKS_SEKUNDER)
            return
        if len(ids) > 1:
            text(surface, f"{len(ids)} reklame di sekitar titik ini", (x, rect.y + 20), 17, theme.NAVY, bold=True)
            rank = {"Melanggar": 0, "Perlu cek": 1, "Patuh": 2, "Tayang berakhir": 3, "Tidak diaudit": 4}
            rows = sorted((self.app.audit[i] for i in ids if i in self.app.audit),
                          key=lambda r: rank.get(r["status"], 9))
            y = rect.y + 56
            for r in rows[:13]:
                br = pygame.Rect(x, y, w, 48)
                hover = br.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, theme.LATAR if hover else theme.PUTIH, br, border_radius=6)
                draw_marker(surface, (br.x + 14, br.centery), r["status"])
                text(surface, r.get("isi_reklame") or "-", (br.x + 32, br.y + 6), 14, bold=True, max_w=w - 40)
                text(surface, f"{r['status']} · {r['id']}", (br.x + 32, br.y + 26), 12, theme.TEKS_LABEL)
                self.list_buttons.append((br, r["id"]))
                y += 52
            if len(rows) > 13:
                text(surface, f"dan {len(rows) - 13} lainnya. Perbesar peta untuk memisahkan.", (x, y + 4),
                     12, theme.TEKS_LABEL, max_w=w)
            return

        r = self.app.audit.get(ids[0])
        if r is None:
            return
        y = rect.y + 20
        status_badge(surface, (x, y), r["status"])
        text(surface, r["id"], (rect.right - 20, y + 14), 12, theme.TEKS_LABEL, anchor="midright")
        y = text_block(surface, r.get("isi_reklame") or "-", (x, y + 42), w, 20, theme.TEKS, bold=True)
        info = [r.get("alamat") or "-", r.get("media") or "-"]
        if r.get("tayang_mulai") or r.get("tayang_selesai"):
            info.append(f"Tayang {r.get('tayang_mulai') or '?'} s.d. {r.get('tayang_selesai') or '?'}")
        info.append(f"Kategori: {r.get('kategori_materi')} · Sumber: {r.get('sumber', 'Bapenda')}")
        for line in info:
            y = text_block(surface, line, (x, y + 4), w, 13, theme.TEKS_SEKUNDER)
        y += 10
        pygame.draw.line(surface, theme.GARIS, (x, y), (x + w, y))
        section_label(surface, "Alasan", (x, y + 12))
        y += 36
        for line in self.app.detail_lines(r["id"]):
            bg = theme.MERAH_MUDA if r["status"] == "Melanggar" else theme.LATAR
            box = pygame.Rect(x, y, w, len(wrap(line, 13, w - 24)) * int(13 * 1.45) + 20)
            pygame.draw.rect(surface, bg, box, border_radius=8)
            text_block(surface, line, (x + 12, y + 10), w - 24, 13, theme.TEKS)
            y = box.bottom + 8
        if r.get("alamat_tidak_lengkap"):
            y = text_block(surface, "Lokasi perkiraan: alamat tanpa nomor rumah, titik diletakkan di ruas jalannya.",
                           (x, y + 4), w, 12, theme.AMBER)
        actions = self.app.admin_detail_actions(r["id"])
        by = rect.bottom - 64
        for i, (label, fn) in enumerate(actions):
            bw = (w - 8 * (len(actions) - 1)) // len(actions)
            b = Button((x + i * (bw + 8), by, bw, 44), label, fn, kind="primary" if i == 0 else "secondary", size=13)
            b._state = self._button_state(label)
            self.buttons.append(b)
            b.draw(surface)

    _states = {}

    def _button_state(self, label):
        return self._states.setdefault(label, {})

    def handle(self, event):
        for b in self.buttons:
            if b.handle(event):
                return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for br, id in self.list_buttons:
                if br.collidepoint(event.pos):
                    self.app.select([id])
                    return True
        return False


class GuideCard:
    STEPS = [
        "1. Titik merah berarti reklame melanggar aturan. Klik untuk melihat alasannya.",
        "2. Lingkaran biru muda adalah radius 500 m dari sekolah.",
        "3. Cari jalan Anda di kotak pencarian, atau laporkan reklame yang belum tercatat.",
    ]

    def __init__(self, app):
        self.app = app
        self.modal = Modal("Cara membaca peta ini", (560, 380))
        r = self.modal.rect
        self.skip = Button((r.x + 24, r.bottom - 68, 150, 44), "Lewati", app.close_guide, kind="secondary")
        self.ok = Button((r.right - 174, r.bottom - 68, 150, 44), "Mengerti", app.close_guide)

    def draw(self, surface):
        body = self.modal.draw_frame(surface)
        y = body.y + 16
        for s in self.STEPS:
            y = text_block(surface, s, (body.x, y), body.width, 15) + 14
        self.skip.draw(surface)
        self.ok.draw(surface)

    def handle(self, event):
        self.skip.handle(event) or self.ok.handle(event)
