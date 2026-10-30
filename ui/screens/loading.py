"""Layar memuat: membangun cache saat run pertama, dengan progress bar."""

import threading

import pygame

from data_prep import OSMDownloadError, build_cache, cache_is_fresh, fetch_osm, load_zones
from ui import theme
from ui.widgets import Button, text, text_block


class Loader:
    def __init__(self, cache_dir, reklame_path, fetcher=None, sync=False):
        self.cache_dir = cache_dir
        self.reklame_path = reklame_path
        self.fetcher = fetcher or fetch_osm
        self.sync = sync
        self.pct, self.msg = 0, "Menyiapkan data"
        self.error = None
        self.zones = None
        self.done = False
        self._thread = None

    def _progress(self, pct, msg):
        self.pct, self.msg = pct, msg

    def _work(self):
        try:
            if cache_is_fresh(self.cache_dir, self.reklame_path):
                self._progress(50, "Membaca cache")
                self.zones = load_zones(self.cache_dir)
            else:
                self.zones = build_cache(self.cache_dir, self.reklame_path, fetcher=self.fetcher,
                                         progress=self._progress)
            self.done = True
        except OSMDownloadError as e:
            if not self.cache_dir.joinpath("osm_raw.gpkg").exists():
                self.error = f"Butuh internet untuk run pertama. Gagal mengunduh lapisan: {e.layer}"
            else:
                self.error = f"Gagal mengunduh lapisan: {e.layer}"
        except Exception as e:  # pesan jelas, bukan crash
            self.error = f"Gagal menyiapkan data: {e}"

    def start(self):
        self.error = None
        self.done = False
        self.pct, self.msg = 0, "Menyiapkan data"
        if self.sync:
            self._work()
        else:
            self._thread = threading.Thread(target=self._work, daemon=True)
            self._thread.start()


class LoadingScreen:
    def __init__(self, app):
        self.app = app
        self.card = pygame.Rect(0, 0, 560, 260)
        self.card.center = (theme.WINDOW[0] // 2, theme.WINDOW[1] // 2)
        self.retry = Button((self.card.x + 32, self.card.bottom - 76, 160, 44), "Coba lagi", app.retry_loading)

    def draw(self, surface):
        surface.fill(theme.LATAR)
        pygame.draw.rect(surface, theme.PUTIH, self.card, border_radius=12)
        x = self.card.x + 32
        text(surface, "Audit Reklame Surabaya", (x, self.card.y + 24), 32, theme.NAVY, display=True)
        loader = self.app.loader
        if loader.error:
            text_block(surface, loader.error, (x, self.card.y + 76), self.card.width - 64, 15, theme.MERAH)
            text_block(surface, "Periksa koneksi internet, lalu tekan Coba lagi.", (x, self.card.y + 130),
                       self.card.width - 64, 14, theme.TEKS_SEKUNDER)
            self.retry.draw(surface)
            return
        text(surface, loader.msg, (x, self.card.y + 84), 15, theme.TEKS_SEKUNDER, max_w=self.card.width - 64)
        bar = pygame.Rect(x, self.card.y + 120, self.card.width - 64, 14)
        pygame.draw.rect(surface, theme.LATAR, bar, border_radius=7)
        fill = bar.copy()
        fill.width = max(14, int(bar.width * loader.pct / 100))
        pygame.draw.rect(surface, theme.TEAL, fill, border_radius=7)
        text(surface, f"{loader.pct}%", (x, self.card.y + 146), 13, theme.TEKS_LABEL)
        text_block(surface, "Run pertama mengunduh data OpenStreetMap dan bisa memakan beberapa menit. "
                            "Run berikutnya langsung memakai cache.", (x, self.card.y + 180),
                   self.card.width - 64, 13, theme.TEKS_LABEL)

    def handle(self, event):
        if self.app.loader.error:
            self.retry.handle(event)
