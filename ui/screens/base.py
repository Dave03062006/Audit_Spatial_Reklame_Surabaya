"""Dasar untuk setiap tab. Tab yang memakai peta cukup mengubah bagian yang berbeda."""

from ui import theme
from ui.map_view import Marker


class Screen:
    name = ""
    uses_map = True

    def __init__(self, app):
        self.app = app

    # --- peta ---
    def markers(self):
        return self.app.default_markers()

    def overlays(self):
        return self.app.layer_overlays()

    def on_map_event(self, ev):
        self.app.select_from_map(ev)

    # --- panel ---
    def draw_left(self, surface, rect):
        self.app.left_panel.draw(surface, rect)

    def handle_left(self, event):
        return self.app.left_panel.handle(event)

    def draw_right(self, surface, rect):
        self.app.detail_panel.draw(surface, rect)

    def handle_right(self, event):
        return self.app.detail_panel.handle(event)

    # --- tab tanpa peta ---
    def draw_content(self, surface, rect):
        pass

    def handle_content(self, event):
        return False

    def on_enter(self):
        pass

    def draw_overlay(self, surface):
        pass


def markers_from(rows, statuses=None):
    out = []
    for r in rows:
        if statuses is None or r["status"] in statuses:
            out.append(Marker(r["id"], r["x"], r["y"], r["status"]))
    return out


def panel_bg(surface, rect, border_side="right"):
    import pygame
    pygame.draw.rect(surface, theme.PUTIH, rect)
    if border_side == "right":
        pygame.draw.line(surface, theme.GARIS, (rect.right - 1, rect.top), (rect.right - 1, rect.bottom))
    else:
        pygame.draw.line(surface, theme.GARIS, rect.topleft, rect.bottomleft)


def section_label(surface, s, pos):
    from ui.widgets import text
    return text(surface, s.upper(), pos, 12, theme.TEKS_LABEL, bold=True)
