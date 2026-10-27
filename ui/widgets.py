"""Komponen antarmuka sederhana untuk Pygame: tombol, isian teks, tabel, dan lainnya.

Setiap komponen punya draw(surface) dan handle(event).
"""

import time

import pygame

from ui import theme


def text(surface, s, pos, size=14, color=theme.TEKS, bold=False, anchor="topleft", max_w=None):
    f = theme.font(size, bold)
    s = str(s)
    if max_w is not None and f.size(s)[0] > max_w:
        while s and f.size(s + "…")[0] > max_w:
            s = s[:-1]
        s += "…"
    img = f.render(s, True, color)
    r = img.get_rect(**{anchor: pos})
    surface.blit(img, r)
    return r


def wrap(s, size, max_w, bold=False):
    f = theme.font(size, bold)
    lines = []
    for para in str(s).split("\n"):
        line = ""
        for word in para.split(" "):
            trial = (line + " " + word).strip()
            if f.size(trial)[0] <= max_w or not line:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def text_block(surface, s, pos, max_w, size=14, color=theme.TEKS, bold=False, line_h=None):
    line_h = line_h or int(size * 1.45)
    x, y = pos
    for ln in wrap(s, size, max_w, bold):
        text(surface, ln, (x, y), size, color, bold)
        y += line_h
    return y


def _clicked(event, rect, state):
    """Klik = tekan dan lepas di dalam kotak yang sama."""
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        state["down"] = rect.collidepoint(event.pos)
        return False
    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        was = state.get("down", False)
        state["down"] = False
        return was and rect.collidepoint(event.pos)
    return False


class Button:
    STYLES = {
        "primary": (theme.NAVY, theme.PUTIH, None),
        "secondary": (theme.PUTIH, theme.NAVY, theme.GARIS),
        "danger": (theme.MERAH, theme.PUTIH, None),
        "tab": (theme.NAVY, theme.PUTIH, None),
        "tab_active": (theme.PUTIH, theme.NAVY, None),
    }

    def __init__(self, rect, label, on_click, kind="primary", enabled=True, size=14):
        self.rect = pygame.Rect(rect)
        self.rect.height = max(self.rect.height, theme.MIN_TARGET)
        self.label = label
        self.on_click = on_click
        self.kind = kind
        self.enabled = enabled
        self.size = size
        self._state = {}

    def draw(self, surface):
        bg, fg, border = self.STYLES[self.kind]
        if not self.enabled:
            bg, fg = theme.LATAR, theme.ABU_UMUM
        hover = self.enabled and self.rect.collidepoint(pygame.mouse.get_pos())
        if hover and self.kind in ("primary", "danger"):
            bg = tuple(max(0, c - 18) for c in bg)
        if hover and self.kind == "tab":
            bg = theme.NAVY_2
        pygame.draw.rect(surface, bg, self.rect, border_radius=8)
        if border:
            pygame.draw.rect(surface, border, self.rect, 1, border_radius=8)
        text(surface, self.label, self.rect.center, self.size, fg, bold=True, anchor="center",
             max_w=self.rect.width - 12)

    def handle(self, event):
        if self.enabled and _clicked(event, self.rect, self._state):
            if self.on_click:
                self.on_click()
            return True
        return False


class TextInput:
    def __init__(self, rect, placeholder, password=False, max_len=120, value=""):
        self.rect = pygame.Rect(rect)
        self.rect.height = max(self.rect.height, theme.MIN_TARGET)
        self.placeholder = placeholder
        self.password = password
        self.max_len = max_len
        self.value = value
        self.focused = False
        self.error = False
        self._state = {}

    def display_text(self):
        return "•" * len(self.value) if self.password else self.value

    def draw(self, surface):
        pygame.draw.rect(surface, theme.PUTIH, self.rect, border_radius=8)
        color = theme.MERAH if self.error else theme.NAVY if self.focused else theme.GARIS
        pygame.draw.rect(surface, color, self.rect, 2 if self.focused or self.error else 1, border_radius=8)
        inner = self.rect.inflate(-24, 0)
        if self.value:
            s = self.display_text()
            f = theme.font(15)
            while s and f.size(s)[0] > inner.width - 4:
                s = s[1:]
            r = text(surface, s, (inner.x, self.rect.centery), 15, theme.TEKS, anchor="midleft")
            cursor_x = r.right + 1
        else:
            text(surface, self.placeholder, (inner.x, self.rect.centery), 15, theme.TEKS_LABEL,
                 anchor="midleft", max_w=inner.width)
            cursor_x = inner.x
        if self.focused and int(time.time() * 2) % 2 == 0:
            pygame.draw.line(surface, theme.TEKS, (cursor_x, self.rect.y + 12), (cursor_x, self.rect.bottom - 12), 2)

    def handle(self, event):
        if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.focused = self.rect.collidepoint(event.pos)
                if self.focused:
                    self.error = False
            return None
        if not self.focused:
            return None
        if event.type == pygame.TEXTINPUT:
            if len(self.value) < self.max_len:
                self.value = (self.value + event.text)[: self.max_len]
            return "change"
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.value = self.value[:-1]
                return "change"
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return "submit"
            if event.key == pygame.K_ESCAPE:
                self.focused = False
        return None


class Checkbox:
    def __init__(self, rect, label, checked=False, on_change=None):
        self.rect = pygame.Rect(rect)
        self.rect.height = max(self.rect.height, theme.MIN_TARGET)
        self.label = label
        self.checked = checked
        self.on_change = on_change
        self._state = {}

    def draw(self, surface):
        b = pygame.Rect(self.rect.x, self.rect.centery - 10, 20, 20)
        if self.checked:
            pygame.draw.rect(surface, theme.NAVY, b, border_radius=4)
            pygame.draw.lines(surface, theme.PUTIH, False,
                              [(b.x + 4, b.centery), (b.x + 8, b.bottom - 5), (b.right - 4, b.y + 5)], 3)
        else:
            pygame.draw.rect(surface, theme.PUTIH, b, border_radius=4)
            pygame.draw.rect(surface, theme.TEKS_LABEL, b, 2, border_radius=4)
        text(surface, self.label, (b.right + 10, self.rect.centery), 14, theme.TEKS, anchor="midleft",
             max_w=self.rect.right - b.right - 12)

    def handle(self, event):
        if _clicked(event, self.rect, self._state):
            self.checked = not self.checked
            if self.on_change:
                self.on_change(self.checked)
            return True
        return False


class Dropdown:
    def __init__(self, rect, options, value, on_change=None):
        self.rect = pygame.Rect(rect)
        self.rect.height = max(self.rect.height, theme.MIN_TARGET)
        self.options = list(options)
        self.value = value
        self.on_change = on_change
        self.open = False
        self._state = {}

    def option_rect(self, i):
        h = self.rect.height
        if self.rect.bottom + len(self.options) * h > theme.WINDOW[1]:
            # tidak muat ke bawah: buka ke atas
            return pygame.Rect(self.rect.x, self.rect.y - (len(self.options) - i) * h, self.rect.width, h)
        return pygame.Rect(self.rect.x, self.rect.bottom + i * h, self.rect.width, h)

    def draw(self, surface):
        pygame.draw.rect(surface, theme.PUTIH, self.rect, border_radius=8)
        pygame.draw.rect(surface, theme.GARIS, self.rect, 1, border_radius=8)
        text(surface, self.value, (self.rect.x + 12, self.rect.centery), 14, anchor="midleft",
             max_w=self.rect.width - 40)
        cx, cy = self.rect.right - 18, self.rect.centery
        pygame.draw.polygon(surface, theme.TEKS_LABEL, [(cx - 5, cy - 3), (cx + 5, cy - 3), (cx, cy + 3)])

    def draw_overlay(self, surface):
        if not self.open:
            return
        for i, opt in enumerate(self.options):
            r = self.option_rect(i)
            hover = r.collidepoint(pygame.mouse.get_pos())
            pygame.draw.rect(surface, theme.LATAR if hover or opt == self.value else theme.PUTIH, r)
            pygame.draw.rect(surface, theme.GARIS, r, 1)
            text(surface, opt, (r.x + 12, r.centery), 14, anchor="midleft", max_w=r.width - 20)

    def handle(self, event):
        if self.open and event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            for i, opt in enumerate(self.options):
                if _clicked(event, self.option_rect(i), self._state.setdefault(i, {})):
                    self.value = opt
                    self.open = False
                    if self.on_change:
                        self.on_change(opt)
                    return True
            if event.type == pygame.MOUSEBUTTONUP and not self.rect.collidepoint(event.pos):
                self.open = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                return any(self.option_rect(i).collidepoint(event.pos) for i in range(len(self.options)))
        if _clicked(event, self.rect, self._state.setdefault("main", {})):
            self.open = not self.open
            return True
        return False


class Table:
    ROW_H = 40
    HEAD_H = 40

    def __init__(self, rect, columns, rows, page_size=15):
        self.rect = pygame.Rect(rect)
        self.columns = columns
        self.page_size = page_size
        self.sort_key = None
        self.sort_desc = False
        self.page = 0
        self.set_rows(rows)
        self._state = {}

    def set_rows(self, rows):
        self.rows = list(rows)
        self._apply_sort()
        self.page = min(self.page, max(0, self.page_count - 1))

    @property
    def page_count(self):
        return max(1, -(-len(self.rows) // self.page_size))

    def _apply_sort(self):
        if self.sort_key is not None:
            def k(r):
                v = r.get(self.sort_key)
                return (v is None, v if not isinstance(v, list) else ", ".join(v))
            self.rows.sort(key=k, reverse=self.sort_desc)

    def sort_by(self, key):
        if self.sort_key == key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, True
        self._apply_sort()

    def visible_rows(self):
        start = self.page * self.page_size
        return self.rows[start:start + self.page_size]

    def header_rect(self, i):
        x = self.rect.x + sum(c[2] for c in self.columns[:i])
        return pygame.Rect(x, self.rect.y, self.columns[i][2], self.HEAD_H)

    def row_rect(self, i):
        return pygame.Rect(self.rect.x, self.rect.y + self.HEAD_H + i * self.ROW_H, self.rect.width, self.ROW_H)

    def draw(self, surface, cell_color=None):
        pygame.draw.rect(surface, theme.PUTIH, self.rect, border_radius=8)
        pygame.draw.rect(surface, theme.LATAR, (self.rect.x, self.rect.y, self.rect.width, self.HEAD_H),
                         border_top_left_radius=8, border_top_right_radius=8)
        for i, (key, label, w) in enumerate(self.columns):
            hr = self.header_rect(i)
            mark = ""
            if key == self.sort_key:
                mark = " ↓" if self.sort_desc else " ↑"
            text(surface, label + mark, (hr.x + 12, hr.centery), 13, theme.TEKS_LABEL, bold=True,
                 anchor="midleft", max_w=w - 16)
        mouse = pygame.mouse.get_pos()
        for i, row in enumerate(self.visible_rows()):
            rr = self.row_rect(i)
            if rr.collidepoint(mouse):
                pygame.draw.rect(surface, theme.BIRU_MUDA, rr)
            pygame.draw.line(surface, theme.GARIS, rr.topleft, rr.topright)
            x = rr.x
            for key, label, w in self.columns:
                v = row.get(key)
                if isinstance(v, list):
                    v = ", ".join(v)
                color = cell_color(key, row) if cell_color else theme.TEKS
                text(surface, "" if v is None else v, (x + 12, rr.centery), 14, color, anchor="midleft",
                     max_w=w - 16)
                x += w

    def handle(self, event):
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            return None
        for i, (key, _, _) in enumerate(self.columns):
            if _clicked(event, self.header_rect(i), self._state.setdefault(("h", i), {})):
                self.sort_by(key)
                return None
        for i, row in enumerate(self.visible_rows()):
            if _clicked(event, self.row_rect(i), self._state.setdefault(("r", i), {})):
                return row
        return None


class Toast:
    def __init__(self):
        self.msg = None
        self.until = 0

    def show(self, msg, seconds=3):
        self.msg = msg
        self.until = time.time() + seconds

    def draw(self, surface):
        if not self.msg or time.time() > self.until:
            return
        f = theme.font(15, bold=True)
        w = f.size(self.msg)[0] + 40
        r = pygame.Rect(0, 0, w, 48)
        r.midbottom = (surface.get_width() // 2, surface.get_height() - 28)
        pygame.draw.rect(surface, theme.TEKS, r, border_radius=10)
        text(surface, self.msg, r.center, 15, theme.PUTIH, bold=True, anchor="center")


def status_badge(surface, pos, status, size=13):
    color = theme.STATUS_COLOR.get(status, theme.ABU_UMUM)
    label = status.upper()
    f = theme.font(size, bold=True)
    w = f.size(label)[0] + 36
    r = pygame.Rect(pos[0], pos[1], w, 28)
    pygame.draw.rect(surface, color, r, border_radius=6)
    cx, cy = r.x + 14, r.centery
    if status == "Patuh":
        pygame.draw.lines(surface, theme.PUTIH, False, [(cx - 5, cy), (cx - 1, cy + 4), (cx + 5, cy - 4)], 2)
    else:
        icon = theme.STATUS_ICON.get(status, "")
        if icon:
            text(surface, icon, (cx, cy), size, theme.PUTIH, bold=True, anchor="center")
    text(surface, label, (r.x + 26, cy), size, theme.PUTIH, bold=True, anchor="midleft")
    return r


class Modal:
    """Kotak dialog di tengah layar. Isi digambar oleh fungsi draw_body(surface, rect)."""

    def __init__(self, title, size=(460, 320)):
        self.title = title
        self.rect = pygame.Rect(0, 0, *size)
        self.rect.center = (theme.WINDOW[0] // 2, theme.WINDOW[1] // 2)

    def draw_frame(self, surface):
        shade = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        shade.fill((20, 34, 46, 120))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, theme.PUTIH, self.rect, border_radius=12)
        text(surface, self.title, (self.rect.x + 24, self.rect.y + 22), 20, theme.NAVY, bold=True)
        return self.rect.inflate(-48, -48).move(0, 24)
