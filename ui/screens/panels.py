"""Panel kiri (cari, temuan, lapisan, keterangan), panel kanan (detail), kartu panduan, dan meteran jarak."""

import pygame

import gis
from ui import theme
from ui.map_view import draw_cluster, draw_marker
from ui.screens.base import panel_bg, section_label
from ui.widgets import Button, Checkbox, Modal, TextInput, status_badge, text, text_block, wrap


# ---------------------------------------------------------------
# Meteran: jarak reklame dibandingkan dengan batas aturan
# ---------------------------------------------------------------

def chip(surface, label, pos, fg, bg, anchor="topleft", size=12):
    f = theme.font(size, bold=True)
    r = pygame.Rect(0, 0, f.size(label)[0] + 16, 22)
    setattr(r, anchor, pos)
    pygame.draw.rect(surface, bg, r, border_radius=11)
    text(surface, label, r.center, size, fg, bold=True, anchor="center")
    return r


def draw_meteran(surface, x, y, w, jarak, batas, skala, tujuan, kode, redup=False):
    """Satu meteran. Bagian berarsir (0 sampai batas) adalah zona larangan, seperti arsiran di peta.

    Mengembalikan y di bawah meteran.
    """
    di_dalam = jarak <= batas
    warna = theme.ABU_UMUM if redup else theme.MERAH if di_dalam else theme.BIRU_PATUH
    angka = text(surface, f"{theme.fmt(jarak)} m", (x, y), 34, warna, display=True)
    if di_dalam:
        chip(surface, gis.RULE_SHORT[kode], (x + w, angka.centery), theme.PUTIH,
             theme.ABU_UMUM if redup else theme.MERAH, anchor="midright")
    else:
        chip(surface, "Di luar batas", (x + w, angka.centery), theme.BIRU_PATUH, theme.BIRU_MUDA, anchor="midright")
    text(surface, tujuan, (x, angka.bottom - 2), 13, theme.TEKS_SEKUNDER, max_w=w)

    # pita meteran
    ty = angka.bottom + 30
    track = pygame.Rect(x, ty, w, 10)
    zona = track.copy()
    zona.width = round(w * batas / skala)
    pygame.draw.rect(surface, theme.PUTIH, track, border_radius=3)
    pygame.draw.rect(surface, theme.TEAL_MUDA, zona, border_top_left_radius=3, border_bottom_left_radius=3)
    pygame.draw.rect(surface, theme.GARIS, track, 1, border_radius=3)
    for i in range(11):
        tx = x + round(w * i / 10)
        pygame.draw.line(surface, theme.TEKS_LABEL, (tx, track.bottom), (tx, track.bottom + (6 if i % 5 == 0 else 3)))
    pygame.draw.line(surface, theme.TEAL, (zona.right, track.y - 4), (zona.right, track.bottom + 6), 2)
    lab_y = track.bottom + 8
    text(surface, "0", (x, lab_y), 12, theme.TEKS_LABEL)
    text(surface, f"batas {batas} m", (zona.right, lab_y), 12, theme.TEAL, bold=True, anchor="midtop")
    akhir = f"{skala // 1000} km" if skala >= 1000 else f"{skala} m"
    text(surface, akhir + ("+" if jarak > skala else ""), (x + w, lab_y), 12, theme.TEKS_LABEL, anchor="topright")
    # posisi reklame di pita
    px = x + round(w * min(jarak, skala) / skala)
    status = "Tayang berakhir" if redup else "Melanggar" if di_dalam else "Patuh"
    draw_marker(surface, (px, track.centery), status)
    return lab_y + 22


def draw_alasan(surface, x, y, w, kategori, kode, info, status=None):
    """Alasan hasil cek: meteran untuk rokok/vape, kartu untuk alkohol. Mengembalikan y di bawahnya."""
    redup = status == "Tayang berakhir"
    if kategori == gis.KATEGORI_ALKOHOL:
        box = pygame.Rect(x, y, w, 76)
        pygame.draw.rect(surface, theme.ABU_UMUM if redup else theme.MERAH_MUDA, box, border_radius=8)
        text(surface, "Seluruh Surabaya", (x + 12, y + 8), 26, theme.TEKS if redup else theme.MERAH, display=True)
        text_block(surface, "Reklame minuman beralkohol dilarang di mana pun (Perda 5/2019 Ps. 23).",
                   (x + 12, y + 40), w - 24, 12, theme.TEKS)
        return box.bottom + 12
    if kategori not in gis.KATEGORI_AUDIT:
        return y
    if info.get("sekolah_jarak_m") is not None:
        nama = info["sekolah_nama"]
        y = draw_meteran(surface, x, y, w, info["sekolah_jarak_m"], gis.RADIUS_M, 1000, f"ke {nama}",
                         "449_1_d", redup) + 14
    if info.get("jalan_utama_jarak_m") is not None:
        y = draw_meteran(surface, x, y, w, info["jalan_utama_jarak_m"], gis.KORIDOR_M, 100, "ke jalan utama terdekat",
                         "449_1_c", redup) + 14
    return y


def note_box(surface, s, x, y, w, bg=theme.LATAR, color=theme.TEKS, size=13):
    h = len(wrap(s, size, w - 24)) * int(size * 1.45) + 20
    pygame.draw.rect(surface, bg, (x, y, w, h), border_radius=8)
    text_block(surface, s, (x + 12, y + 10), w - 24, size, color)
    return y + h + 8


# ---------------------------------------------------------------
# Panel kiri
# ---------------------------------------------------------------

def _swatch(surface, key, center):
    cx, cy = center
    if key == "zona":
        pygame.draw.circle(surface, theme.TEAL_MUDA, center, 9)
        pygame.draw.circle(surface, theme.TEAL, center, 9, 2)
    elif key == "koridor":
        pygame.draw.rect(surface, theme.TEAL_MUDA, (cx - 12, cy - 5, 24, 10))
        pygame.draw.line(surface, theme.PUTIH, (cx - 12, cy), (cx + 11, cy), 3)
    elif key == "rokok":
        for i, st in enumerate(("Patuh", "Perlu cek", "Melanggar")):
            draw_marker(surface, (cx - 8 + i * 8, cy), st)
    else:
        draw_marker(surface, center, "Tidak diaudit")


class LeftPanel:
    LAYERS = [("zona", "Zona 500 m sekolah"), ("koridor", "Koridor jalan utama"),
              ("rokok", "Rokok, vape & alkohol"), ("umum", "Reklame umum")]

    def __init__(self, app):
        self.app = app
        r = app.left_rect
        x, w = r.x + 16, r.width - 32
        self.search = TextInput((x, r.y + 38, w, 44), "Cari jalan atau kelurahan")
        app.search_box = self.search
        self.layer_y = r.y + 290
        self.checks = []
        for i, (key, label) in enumerate(self.LAYERS):
            cb = Checkbox((x, self.layer_y + i * 44, w - 40, 44), label, app.layers[key],
                          on_change=lambda v, k=key: app.set_layer(k, v))
            self.checks.append(cb)

    def result_rect(self, i):
        return pygame.Rect(self.search.rect.x, self.search.rect.bottom + 4 + i * 40, 300, 40)

    def draw_temuan(self, surface, x, y, w):
        """Angka utama: berapa reklame yang diaudit ternyata melanggar."""
        c = self.app.counts()
        m, p, tb = c["Melanggar"], c["Patuh"], c["Tayang berakhir"]
        total = m + p + tb
        big = text(surface, theme.fmt(m), (x - 2, y - 6), 50, theme.MERAH, display=True)
        tx = big.right + 10
        text(surface, "melanggar", (tx, y + 6), 15, theme.TEKS, bold=True)
        pct = round(100 * m / total) if total else 0
        text(surface, f"{pct}% dari {theme.fmt(total)} diaudit", (tx, y + 26), 12, theme.TEKS_SEKUNDER,
             max_w=x + w - tx)
        bar = pygame.Rect(x, y + 58, w, 10)
        pygame.draw.rect(surface, theme.LATAR, bar, border_radius=5)
        segs = [(n, col) for n, col in ((m, theme.MERAH), (p, theme.BIRU_PATUH), (tb, (196, 206, 214))) if n]
        bx = bar.x
        for i, (n, col) in enumerate(segs):
            last = i == len(segs) - 1
            sw = bar.right - bx if last else max(3, round(w * n / total))
            pygame.draw.rect(surface, col, (bx, bar.y, sw, bar.height),
                             border_top_left_radius=5 if i == 0 else 0, border_bottom_left_radius=5 if i == 0 else 0,
                             border_top_right_radius=5 if last else 0, border_bottom_right_radius=5 if last else 0)
            if not last:   # celah putih tipis antar bagian
                pygame.draw.line(surface, theme.PUTIH, (bx + sw - 1, bar.y), (bx + sw - 1, bar.bottom - 1))
            bx += sw
        ly = bar.bottom + 10
        for label, col in ((f"{theme.fmt(p)} patuh", theme.BIRU_PATUH),
                           (f"{theme.fmt(tb)} tayang berakhir", (196, 206, 214))):
            pygame.draw.rect(surface, col, (x, ly + 4, 8, 8), border_radius=2)
            r = text(surface, label, (x + 13, ly), 12, theme.TEKS_SEKUNDER)
            x = r.right + 14
        return c

    def draw(self, surface, rect):
        panel_bg(surface, rect)
        x, w = rect.x + 16, rect.width - 32
        section_label(surface, "Cari jalan", (x, rect.y + 16))
        self.search.draw(surface)

        section_label(surface, "Temuan audit", (x, rect.y + 104))
        c = self.draw_temuan(surface, x, rect.y + 130, w)
        if c["Perlu cek"]:
            chip(surface, f"{c['Perlu cek']} perlu cek admin", (x, rect.y + 228), theme.AMBER, theme.AMBER_MUDA)

        section_label(surface, "Lapisan peta", (x, self.layer_y - 18))
        for (key, _), cb in zip(self.LAYERS, self.checks):
            cb.draw(surface)
            _swatch(surface, key, (rect.right - 30, cb.rect.centery))

        y = self.layer_y + 4 * 44 + 18
        section_label(surface, "Keterangan", (x, y))
        y += 24
        for i, status in enumerate(("Melanggar", "Patuh", "Perlu cek", "Tayang berakhir")):
            cx, cy = x + (i % 2) * 100, y + (i // 2) * 26
            draw_marker(surface, (cx + 10, cy + 10), status)
            text(surface, status, (cx + 26, cy + 10), 12, theme.TEKS, anchor="midleft")
        y += 56
        pygame.draw.rect(surface, theme.TEAL_TUA, (x + 4, y + 4, 12, 12), border_radius=2)
        text(surface, "Sekolah", (x + 26, y + 10), 13, theme.TEKS, anchor="midleft")
        y += 34
        draw_cluster(surface, (x + 12, y + 12), ["Melanggar"] * 3 + ["Patuh"])
        text_block(surface, "Kumpulan reklame. Merah pada cincin = porsi yang melanggar.", (x + 36, y),
                   w - 36, 12, theme.TEKS_SEKUNDER)

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


# ---------------------------------------------------------------
# Panel kanan
# ---------------------------------------------------------------

RULES = [("500 m", "dari sekolah (TK sampai SMA)", "Rokok & vape · PP 28/2024 Ps. 449 (1) d"),
         ("25 m", "dari jalan utama", "Rokok & vape · PP 28/2024 Ps. 449 (1) c"),
         ("Seluruh kota", "untuk alkohol", "Minuman beralkohol · Perda 5/2019 Ps. 23")]


class DetailPanel:
    def __init__(self, app):
        self.app = app
        self.buttons = []
        self.list_buttons = []

    def draw_empty(self, surface, rect, x, w):
        text(surface, "Pilih reklame di peta", (x, rect.y + 20), 18, theme.NAVY, bold=True)
        y = rect.y + 58
        rows = [("marker", "Klik titik untuk melihat alasannya dan jaraknya ke sekolah terdekat."),
                ("cluster", "Lingkaran berangka berisi beberapa reklame. Klik untuk melihat daftarnya."),
                ("garis", "Garis putus-putus mengukur jarak ke sekolah dan jalan utama terdekat.")]
        for kind, s in rows:
            c = (x + 14, y + 12)
            if kind == "marker":
                draw_marker(surface, c, "Melanggar")
            elif kind == "cluster":
                draw_cluster(surface, c, ["Melanggar"] * 3 + ["Patuh"])
            else:
                for i in range(3):
                    pygame.draw.line(surface, theme.TEAL_TUA, (x + i * 10, y + 12), (x + i * 10 + 6, y + 12), 2)
                pygame.draw.circle(surface, theme.TEAL_TUA, (x + 28, y + 12), 4)
            y = max(y + 30, text_block(surface, s, (x + 40, y), w - 40, 13, theme.TEKS_SEKUNDER)) + 12
        y += 8
        pygame.draw.line(surface, theme.GARIS, (x, y), (x + w, y))
        section_label(surface, "Aturan yang diperiksa", (x, y + 16))
        y += 44
        for big, sub, dasar in RULES:
            r = text(surface, big, (x, y - 4), 28, theme.NAVY, display=True)
            text(surface, sub, (r.right + 8, r.centery + 2), 13, theme.TEKS, anchor="midleft",
                 max_w=x + w - r.right - 8)
            text(surface, dasar, (x, r.bottom), 12, theme.TEKS_LABEL, max_w=w)
            y = r.bottom + 30

    def draw(self, surface, rect):
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        ids = self.app.selected_ids
        self.buttons, self.list_buttons = [], []
        if not ids:
            self.draw_empty(surface, rect, x, w)
            return
        if len(ids) > 1:
            text(surface, f"{len(ids)} reklame di titik ini", (x, rect.y + 20), 18, theme.NAVY, bold=True)
            rank = {"Melanggar": 0, "Perlu cek": 1, "Patuh": 2, "Tayang berakhir": 3, "Tidak diaudit": 4}
            rows = sorted((self.app.audit[i] for i in ids if i in self.app.audit),
                          key=lambda r: rank.get(r["status"], 9))
            n_m = sum(r["status"] == "Melanggar" for r in rows)
            if n_m:
                text(surface, f"{n_m} melanggar", (x, rect.y + 46), 13, theme.MERAH, bold=True)
            y = rect.y + 72
            for r in rows[:12]:
                br = pygame.Rect(x - 8, y, w + 16, 48)
                hover = br.collidepoint(pygame.mouse.get_pos())
                pygame.draw.rect(surface, theme.LATAR if hover else theme.PUTIH, br, border_radius=6)
                draw_marker(surface, (br.x + 18, br.centery), r["status"])
                text(surface, r.get("isi_reklame") or "-", (br.x + 38, br.y + 6), 14, bold=True, max_w=w - 36)
                text(surface, f"{r['status']} · {r['id']}", (br.x + 38, br.y + 26), 12, theme.TEKS_LABEL)
                self.list_buttons.append((br, r["id"]))
                y += 52
            if len(rows) > 12:
                text(surface, f"dan {len(rows) - 12} lainnya. Perbesar peta untuk memisahkan.", (x, y + 4),
                     12, theme.TEKS_LABEL, max_w=w)
            return

        r = self.app.audit.get(ids[0])
        if r is None:
            return
        self.draw_reklame(surface, rect, r, x, w)

    def draw_reklame(self, surface, rect, r, x, w):
        y = rect.y + 20
        status_badge(surface, (x, y), r["status"])
        text(surface, r["id"], (x + w, y + 14), 12, theme.TEKS_LABEL, anchor="midright")
        y = text_block(surface, r.get("isi_reklame") or "-", (x, y + 40), w, 18, theme.TEKS, bold=True)
        y = text_block(surface, r.get("alamat") or "-", (x, y + 4), w, 13, theme.TEKS)
        meta = [r.get("media") or "-"]
        if r.get("tayang_mulai") or r.get("tayang_selesai"):
            meta.append(f"Tayang {r.get('tayang_mulai') or '?'} s.d. {r.get('tayang_selesai') or '?'}")
        meta.append(f"{r.get('kategori_materi')} · sumber {r.get('sumber', 'Bapenda')}")
        for line in meta:
            y = text_block(surface, line, (x, y + 2), w, 12, theme.TEKS_SEKUNDER)
        if r.get("alamat_tidak_lengkap"):
            y = note_box(surface, "Lokasi perkiraan: alamat tanpa nomor rumah, titik diletakkan di ruas jalannya. "
                                  "Jarak bisa meleset.", x, y + 8, w, theme.AMBER_MUDA, theme.TEKS, 12) - 8
        y += 14
        pygame.draw.line(surface, theme.GARIS, (x, y), (x + w, y))
        y += 14
        st = r["status"]
        if st in ("Perlu cek", "Tidak diaudit") or r.get("kategori_materi") not in (
                *gis.KATEGORI_AUDIT, gis.KATEGORI_ALKOHOL):
            section_label(surface, "Alasan", (x, y))
            y += 26
            for line in self.app.detail_lines(r["id"]):
                y = note_box(surface, line, x, y, w)
        else:
            label = "Diukur dari titik reklame" if r.get("kategori_materi") in gis.KATEGORI_AUDIT else "Aturan"
            section_label(surface, label, (x, y))
            y += 26
            if st == "Tayang berakhir":
                y = note_box(surface, f"Masa tayang berakhir {r.get('tayang_selesai')}. Tidak dihitung sebagai "
                                      "pelanggaran.", x, y, w, size=12)
            draw_alasan(surface, x, y, w, r.get("kategori_materi"), r["pelanggaran"], self.app.info(r["id"]), st)

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


# ---------------------------------------------------------------
# Kartu panduan (sekali tampil)
# ---------------------------------------------------------------

class GuideCard:
    STEPS = [
        ("marker", "Titik merah berarti reklame melanggar aturan. Klik untuk melihat alasannya."),
        ("zona", "Area biru kehijauan adalah radius 500 m dari sekolah. Reklame rokok di dalamnya melanggar."),
        ("garis", "Setelah titik dipilih, garis putus-putus menunjukkan jaraknya ke sekolah terdekat."),
        ("cari", "Cari jalan Anda di kotak pencarian, atau laporkan reklame yang belum tercatat."),
    ]

    def __init__(self, app):
        self.app = app
        self.modal = Modal("Cara membaca peta ini", (560, 372))
        r = self.modal.rect
        self.skip = Button((r.x + 24, r.bottom - 68, 150, 44), "Lewati", app.close_guide, kind="secondary")
        self.ok = Button((r.right - 174, r.bottom - 68, 150, 44), "Mulai", app.close_guide)

    def draw(self, surface):
        body = self.modal.draw_frame(surface)
        y = body.y + 8
        for kind, s in self.STEPS:
            c = (body.x + 14, y + 11)
            if kind == "marker":
                draw_marker(surface, c, "Melanggar")
            elif kind == "zona":
                _swatch(surface, "zona", c)
            elif kind == "garis":
                for i in range(2):
                    pygame.draw.line(surface, theme.TEAL_TUA, (body.x + i * 10, c[1]), (body.x + i * 10 + 6, c[1]), 2)
                pygame.draw.circle(surface, theme.TEAL_TUA, (body.x + 24, c[1]), 4)
            else:
                pygame.draw.circle(surface, theme.TEKS_LABEL, (c[0] - 2, c[1] - 2), 7, 2)
                pygame.draw.line(surface, theme.TEKS_LABEL, (c[0] + 3, c[1] + 3), (c[0] + 8, c[1] + 8), 3)
            y = text_block(surface, s, (body.x + 44, y), body.width - 44, 15) + 14
        self.skip.draw(surface)
        self.ok.draw(surface)

    def handle(self, event):
        self.skip.handle(event) or self.ok.handle(event)
