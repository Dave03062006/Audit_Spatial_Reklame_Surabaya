"""Tab Kelola (admin): tambah, ubah, geser, dan hapus reklame."""

from datetime import date

import pygame

import gis
from ui import theme
from ui.screens.base import Screen, panel_bg
from ui.widgets import Button, Dropdown, Modal, TextInput, text, text_block

KATEGORI_FORM = ["Rokok", "Rokok elektronik", "Minuman beralkohol", "Umum"]
DATE_ERROR = "Tanggal harus berformat YYYY-MM-DD, misalnya 2027-06-30."


def valid_date(s):
    s = s.strip()
    if not s:
        return True
    try:
        date.fromisoformat(s)
        return len(s) == 10
    except ValueError:
        return False


class ConfirmModal:
    def __init__(self, app, title, message, on_yes, yes_label="Hapus"):
        self.app = app
        self.frame = Modal(title, (460, 260))
        self.message = message
        r = self.frame.rect
        self.no = Button((r.x + 24, r.bottom - 68, 120, 44), "Batal", self.close, kind="secondary")
        self.yes = Button((r.right - 168, r.bottom - 68, 144, 44), yes_label, on_yes, kind="danger")

    def close(self):
        self.app.modal = None

    def draw(self, surface):
        body = self.frame.draw_frame(surface)
        text_block(surface, self.message, (body.x, body.y + 6), body.width, 15)
        self.no.draw(surface)
        self.yes.draw(surface)

    def handle(self, event):
        self.no.handle(event) or self.yes.handle(event)


class KelolaScreen(Screen):
    name = "Kelola"

    def __init__(self, app):
        super().__init__(app)
        r = app.right_rect
        x, w = r.x + 20, r.width - 40
        y0 = r.y + 112
        self.form = {
            "isi": TextInput((x, y0, w, 44), "Teks atau merek reklame"),
            "kategori": Dropdown((x, y0 + 70, w, 44), KATEGORI_FORM, "Rokok"),
            "media": TextInput((x, y0 + 140, w, 44), "Media, mis. BILLBOARD"),
            "tayang_mulai": TextInput((x, y0 + 210, (w - 8) // 2, 44), "YYYY-MM-DD"),
            "tayang_selesai": TextInput((x + (w + 8) // 2, y0 + 210, (w - 8) // 2, 44), "YYYY-MM-DD"),
        }
        self.labels = [("isi", "Isi reklame"), ("kategori", "Kategori"), ("media", "Media"),
                       ("tayang_mulai", "Tayang mulai"), ("tayang_selesai", "Tayang selesai")]
        by = r.bottom - 64
        self.add_btn = Button((x, r.y + 64, w, 44), "Tambah reklame baru", self.start_add)
        self.cancel_btn = Button((x, by, 100, 44), "Batal", self.cancel, kind="secondary")
        self.save_btn = Button((x + 112, by, w - 112, 44), "Simpan", self.save)
        self.mode = None      # None | "tambah" | "ubah" | "geser"
        self.edit_id = None
        self.pin = None
        self.error = None
        self.pending_delete = None

    def on_enter(self):
        self.cancel()

    # --- aksi ---
    def cancel(self):
        self.mode, self.edit_id, self.pin, self.error = None, None, None, None
        self.app.map.pin = None
        self.app.map.draggable_id = None

    def _fill(self, row):
        self.form["isi"].value = row.get("isi_reklame") or ""
        k = row.get("kategori_materi")
        self.form["kategori"].value = k if k in KATEGORI_FORM else "Rokok"
        self.form["media"].value = row.get("media") or ""
        self.form["tayang_mulai"].value = row.get("tayang_mulai") or ""
        self.form["tayang_selesai"].value = row.get("tayang_selesai") or ""

    def start_add(self):
        self.cancel()
        self.mode = "tambah"
        self._fill({})

    def start_edit(self, id):
        self.cancel()
        self.mode, self.edit_id = "ubah", id
        self._fill(self.app.store.get_reklame(id))

    def start_move(self, id):
        self.cancel()
        self.mode, self.edit_id = "geser", id
        self.app.map.draggable_id = id
        self.app.select([id])

    def request_delete(self, id):
        self.pending_delete = id
        r = self.app.audit.get(id, {})
        self.app.modal = ConfirmModal(self.app, "Hapus reklame?",
                                      f"{r.get('isi_reklame', id)} ({id}) akan disembunyikan dari peta dan audit. "
                                      "Data lama tetap tersimpan sebagai riwayat.", self.confirm_delete)

    def confirm_delete(self):
        id, self.pending_delete = self.pending_delete, None
        self.app.modal = None
        if id is None:
            return
        self.app.store.delete_reklame(id, oleh=self.app.admin_name)
        self.app.recheck(id)
        self.cancel()
        self.app.toast.show(f"Reklame {id} dihapus.")

    def save(self):
        f = self.form
        if not f["isi"].value.strip():
            self.error = "Isi reklame wajib diisi."
            return None
        if not (valid_date(f["tayang_mulai"].value) and valid_date(f["tayang_selesai"].value)):
            self.error = DATE_ERROR
            return None
        data = {"isi_reklame": f["isi"].value.strip(), "kategori_materi": f["kategori"].value,
                "media": f["media"].value.strip() or "-",
                "tayang_mulai": f["tayang_mulai"].value.strip() or None,
                "tayang_selesai": f["tayang_selesai"].value.strip() or None}
        oleh = self.app.admin_name
        if self.mode == "tambah":
            if self.pin is None:
                self.error = "Klik peta untuk menandai lokasi reklame."
                return None
            lat, lon = gis.to_latlon(*self.pin)
            data.update(alamat="(ditambahkan admin)", latitude=lat, longitude=lon, kategori_dikonfirmasi=True)
            id = self.app.store.add_reklame(data, oleh=oleh)
        else:
            id = self.edit_id
            data["kategori_dikonfirmasi"] = True
            self.app.store.update_reklame(id, data, oleh=oleh)
        self.app.recheck(id)
        self.cancel()
        self.app.select([id])
        self.app.toast.show(f"Tersimpan. Status: {self.app.audit[id]['status']}.")
        return id

    def on_map_event(self, ev):
        if self.mode == "tambah" and ev.kind in ("empty", "marker"):
            self.pin = (ev.x, ev.y)
            self.app.map.pin = self.pin
            self.error = None
        elif self.mode == "geser" and ev.kind == "drag_end":
            lat, lon = gis.to_latlon(ev.x, ev.y)
            id = ev.ids[0]
            self.app.store.update_reklame(id, {"latitude": lat, "longitude": lon}, oleh=self.app.admin_name)
            self.app.recheck(id)
            self.cancel()
            self.app.select([id])
            self.app.toast.show(f"Lokasi dipindah. Status: {self.app.audit[id]['status']}.")
        elif self.mode is None:
            self.app.select_from_map(ev)

    # --- tampilan ---
    def draw_right(self, surface, rect):
        if self.mode is None:
            panel_bg(surface, rect, border_side="left")
            x, w = rect.x + 20, rect.width - 40
            text(surface, "Kelola Reklame", (x, rect.y + 20), 18, theme.NAVY, bold=True)
            self.add_btn.draw(surface)
            sub = pygame.Rect(rect.x, rect.y + 120, rect.width, rect.height - 120)
            if self.app.selected_ids:
                self.app.detail_panel.draw(surface, sub)
            else:
                text_block(surface, "Pilih titik di peta untuk mengubah, menggeser, atau menghapusnya.",
                           (x, sub.y + 8), w, 14, theme.TEKS_SEKUNDER)
            return
        panel_bg(surface, rect, border_side="left")
        x, w = rect.x + 20, rect.width - 40
        if self.mode == "geser":
            text(surface, "Geser lokasi", (x, rect.y + 20), 18, theme.NAVY, bold=True)
            text_block(surface, f"Seret titik {self.edit_id} di peta ke lokasi yang benar. "
                                "Status audit dihitung ulang setelah dilepas.", (x, rect.y + 56), w, 14,
                       theme.TEKS_SEKUNDER)
            self.cancel_btn.draw(surface)
            return
        title = "Tambah reklame" if self.mode == "tambah" else f"Ubah {self.edit_id}"
        text(surface, title, (x, rect.y + 20), 18, theme.NAVY, bold=True)
        hint = ("Klik peta untuk menandai lokasi." if self.pin is None else "Lokasi sudah ditandai.") \
            if self.mode == "tambah" else "Ubah data lalu tekan Simpan."
        text(surface, hint, (x, rect.y + 52), 13, theme.TEKS_SEKUNDER, max_w=w)
        for key, label in self.labels:
            fr = self.form[key].rect
            text(surface, label, (fr.x, fr.y - 20), 12, theme.TEKS_LABEL, bold=True)
        for key in ("isi", "media", "tayang_mulai", "tayang_selesai", "kategori"):
            self.form[key].draw(surface)
        if self.error:
            text_block(surface, self.error, (x, self.form["tayang_selesai"].rect.bottom + 16), w, 13, theme.MERAH)
        self.cancel_btn.draw(surface)
        self.save_btn.draw(surface)

    def draw_overlay(self, surface):
        if self.mode in ("tambah", "ubah"):
            self.form["kategori"].draw_overlay(surface)

    def handle_right(self, event):
        if self.mode is None:
            if self.add_btn.handle(event):
                return True
            if self.app.selected_ids and self.app.detail_panel.handle(event):
                return True
            return self.app.right_rect.collidepoint(getattr(event, "pos", (-1, -1)))
        if self.mode in ("tambah", "ubah"):
            if self.form["kategori"].handle(event):
                return True
            for key in ("isi", "media", "tayang_mulai", "tayang_selesai"):
                if self.form[key].handle(event) == "submit":
                    self.save()
                    return True
            if event.type in (pygame.TEXTINPUT, pygame.KEYDOWN) and any(
                    self.form[k].focused for k in ("isi", "media", "tayang_mulai", "tayang_selesai")):
                return True
            if self.save_btn.handle(event):
                return True
        if self.cancel_btn.handle(event):
            return True
        return self.app.right_rect.collidepoint(getattr(event, "pos", (-1, -1)))
