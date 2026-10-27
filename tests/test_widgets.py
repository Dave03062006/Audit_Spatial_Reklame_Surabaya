import pygame
import pytest

from ui.widgets import Button, Checkbox, Dropdown, Table, TextInput


@pytest.fixture(autouse=True)
def _pg():
    pygame.init()
    pygame.display.set_mode((1280, 800))
    yield


def click(pos):
    return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"pos": pos, "button": 1}),
            pygame.event.Event(pygame.MOUSEBUTTONUP, {"pos": pos, "button": 1})]


def key(k, uni=""):
    return pygame.event.Event(pygame.KEYDOWN, {"key": k, "unicode": uni, "mod": 0})


def test_button_min_height_44():
    assert Button((0, 0, 100, 20), "OK", lambda: None).rect.height == 44


def test_button_click_calls_handler():
    hits = []
    b = Button((10, 10, 100, 44), "OK", lambda: hits.append(1))
    for e in click((20, 20)):
        b.handle(e)
    assert hits == [1]


def test_disabled_button_ignores_click():
    hits = []
    b = Button((10, 10, 100, 44), "OK", lambda: hits.append(1), enabled=False)
    for e in click((20, 20)):
        b.handle(e)
    assert hits == []


def test_textinput_typing_and_backspace():
    t = TextInput((0, 0, 200, 44), "Cari")
    for e in click((5, 5)):
        t.handle(e)
    assert t.focused
    for ch in "Ketintang":
        t.handle(pygame.event.Event(pygame.TEXTINPUT, {"text": ch}))
    t.handle(key(pygame.K_BACKSPACE))
    assert t.value == "Ketintan"
    assert t.handle(key(pygame.K_RETURN)) == "submit"


def test_textinput_ignores_typing_when_not_focused():
    t = TextInput((0, 0, 200, 44), "Cari")
    t.handle(pygame.event.Event(pygame.TEXTINPUT, {"text": "x"}))
    assert t.value == ""


def test_password_input_masks_render_text():
    t = TextInput((0, 0, 200, 44), "Password", password=True)
    t.value = "rahasia"
    assert t.display_text() == "•" * 7


def test_checkbox_toggles():
    c = Checkbox((0, 0, 200, 44), "Zona", True)
    for e in click((5, 5)):
        c.handle(e)
    assert c.checked is False


def test_dropdown_select():
    d = Dropdown((0, 0, 200, 44), ["Semua", "Rokok"], "Semua")
    for e in click((5, 5)):
        d.handle(e)
    assert d.open
    for e in click((5, 44 + 44 + 5)):
        d.handle(e)
    assert d.value == "Rokok" and not d.open


ROWS = [{"id": f"T-{i}", "n": i} for i in range(40)]


def test_table_sort_and_pagination():
    t = Table((0, 0, 600, 700), [("id", "ID", 200), ("n", "Nomor", 200)], ROWS, page_size=15)
    assert t.page_count == 3
    assert t.visible_rows()[0]["n"] == 0
    t.sort_by("n")
    assert t.visible_rows()[0]["n"] == 39
    t.sort_by("n")
    assert t.visible_rows()[0]["n"] == 0
    t.page = 2
    assert len(t.visible_rows()) == 10


def test_table_row_click_returns_row():
    t = Table((0, 0, 600, 700), [("id", "ID", 200), ("n", "Nomor", 200)], ROWS, page_size=15)
    t.draw(pygame.display.get_surface())
    y = t.row_rect(1).centery
    t.handle(click((50, y))[0])
    assert t.handle(click((50, y))[1]) == ROWS[1]
