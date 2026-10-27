"""Warna, huruf, dan ukuran yang dipakai di seluruh aplikasi (arah desain A, Balai Kota)."""

from pathlib import Path

import pygame


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


NAVY = hex_rgb("#173B57")
NAVY_2 = hex_rgb("#2A5476")
MERAH = hex_rgb("#C8452F")
MERAH_MUDA = hex_rgb("#FBEAE7")
BIRU_PATUH = hex_rgb("#1F4FA3")
BIRU_MUDA = hex_rgb("#E4ECF8")
ABU_UMUM = hex_rgb("#9AAAB6")
AMBER = hex_rgb("#B7791F")
AMBER_MUDA = hex_rgb("#FFF4DB")
TEAL = hex_rgb("#2E7A9A")
TANAH = hex_rgb("#F7F5EF")
LUAR_KOTA = hex_rgb("#E6E9EC")
LATAR = hex_rgb("#EEF2F5")
PUTIH = (255, 255, 255)
GARIS = hex_rgb("#D3DEE6")
TEKS = hex_rgb("#14222E")
TEKS_SEKUNDER = hex_rgb("#3D5263")
TEKS_LABEL = hex_rgb("#4A6275")
HIJAU_BOLEH = hex_rgb("#3F9C7A")

STATUS_COLOR = {
    "Melanggar": MERAH,
    "Patuh": BIRU_PATUH,
    "Tidak diaudit": ABU_UMUM,
    "Perlu cek": AMBER,
    "Tayang berakhir": ABU_UMUM,
}
STATUS_ICON = {
    "Melanggar": "!",
    "Patuh": "✓",
    "Tidak diaudit": "",
    "Perlu cek": "?",
    "Tayang berakhir": "–",
}

MIN_TARGET = 44
WINDOW = (1280, 800)
TOPBAR_H = 56
LEFT_W = 248
RIGHT_W = 320

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONTS = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _FONTS:
        if not pygame.font.get_init():
            pygame.font.init()
        name = "PublicSans-Bold.ttf" if bold else "PublicSans-Regular.ttf"
        path = FONT_DIR / name
        if path.exists():
            f = pygame.font.Font(str(path), size)
        else:
            f = pygame.font.Font(None, int(size * 1.3))
            f.set_bold(bold)
        _FONTS[key] = f
    return _FONTS[key]
