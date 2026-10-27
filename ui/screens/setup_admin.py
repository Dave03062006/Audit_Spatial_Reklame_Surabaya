"""Layar pertama kali: membuat akun admin pertama."""

import pygame

from ui import theme
from ui.widgets import Button, TextInput, text, text_block


class SetupAdmin:
    def __init__(self, app):
        self.app = app
        self.card = pygame.Rect(0, 0, 520, 470)
        self.card.center = (theme.WINDOW[0] // 2, theme.WINDOW[1] // 2)
        x, w = self.card.x + 32, self.card.width - 64
        y = self.card.y + 130
        self.username = TextInput((x, y, w, 44), "Username admin")
        self.password = TextInput((x, y + 64, w, 44), "Password (minimal 8 karakter)", password=True)
        self.password2 = TextInput((x, y + 128, w, 44), "Ulangi password", password=True)
        self.button = Button((x, y + 220, w, 48), "Buat akun admin", self.submit)
        self.error = ""

    def submit(self):
        if self.password.value != self.password2.value:
            self.error = "Password dan ulangan password tidak sama."
            return
        try:
            self.app.store.create_user(self.username.value, self.password.value)
        except ValueError as e:
            self.error = str(e)
            return
        self.error = ""
        self.app.state = "main"
        self.app.toast.show("Akun admin dibuat. Aplikasi siap dipakai.")

    def draw(self, surface):
        surface.fill(theme.LATAR)
        pygame.draw.rect(surface, theme.PUTIH, self.card, border_radius=12)
        x, w = self.card.x + 32, self.card.width - 64
        text(surface, "Buat akun admin pertama", (x, self.card.y + 28), 22, theme.NAVY, bold=True)
        text_block(surface, "Akun ini dipakai untuk mengelola data reklame dan memverifikasi laporan warga. "
                            "Warga tidak perlu akun.", (x, self.card.y + 68), w, 14, theme.TEKS_SEKUNDER)
        for t in (self.username, self.password, self.password2):
            t.draw(surface)
        if self.error:
            text(surface, self.error, (x, self.password2.rect.bottom + 14), 14, theme.MERAH, max_w=w)
        self.button.draw(surface)

    def handle(self, event):
        for t in (self.username, self.password, self.password2):
            if t.handle(event) == "submit":
                self.submit()
        self.button.handle(event)
