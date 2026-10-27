"""Dialog Masuk Admin."""

import time

from ui import theme
from ui.widgets import Button, Modal, TextInput, text


class LoginModal:
    def __init__(self, app):
        self.app = app
        self.frame = Modal("Masuk Admin", (460, 360))
        r = self.frame.rect
        x, w = r.x + 24, r.width - 48
        self.username = TextInput((x, r.y + 92, w, 44), "Username")
        self.password = TextInput((x, r.y + 152, w, 44), "Password", password=True)
        self.username.focused = True
        self.cancel = Button((x, r.bottom - 68, 120, 44), "Batal", self.close, kind="secondary")
        self.ok = Button((r.right - 168, r.bottom - 68, 144, 44), "Masuk", self.submit)
        self.error = ""

    def close(self):
        self.app.modal = None

    def submit(self, now=None):
        now = time.monotonic() if now is None else now
        guard = self.app.login_guard
        if guard.locked(now):
            self.error = f"Terlalu banyak percobaan. Coba lagi dalam {guard.seconds_left(now)} detik."
            return
        ok = self.app.store.check_login(self.username.value, self.password.value)
        guard.record(ok, now)
        if ok:
            self.close()
            self.app.login_as(self.username.value.strip())
        else:
            self.password.value = ""
            self.error = "Username atau password salah."

    def draw(self, surface):
        body = self.frame.draw_frame(surface)
        text(surface, "Khusus petugas yang mengelola data reklame.", (body.x, body.y + 6), 14, theme.TEKS_SEKUNDER)
        self.username.draw(surface)
        self.password.draw(surface)
        if self.error:
            text(surface, self.error, (body.x, self.password.rect.bottom + 14), 14, theme.MERAH, max_w=body.width)
        self.cancel.draw(surface)
        self.ok.draw(surface)

    def handle(self, event):
        for t in (self.username, self.password):
            if t.handle(event) == "submit":
                self.submit()
                return
        self.cancel.handle(event) or self.ok.handle(event)
