import pygame

from conftest import click_events, make_app, type_events
from data_prep import OSMDownloadError
from storage import Store

ADMIN_TABS = {"Kelola", "Verifikasi", "Perlu Cek"}


def test_app_starts_on_peta_as_warga_without_login(app_with_admin):
    app = make_app(app_with_admin)
    assert app.state == "main"
    assert app.role == "warga"
    assert app.tab == "Peta"
    assert not ADMIN_TABS & set(app.tab_names())
    app.step([])


def test_audit_counts(app_with_admin):
    app = make_app(app_with_admin)
    c = app.counts()
    assert c["Melanggar"] == 2
    assert c["Patuh"] == 1
    assert c["Perlu cek"] == 1
    assert c["Tayang berakhir"] == 1
    assert app.audit["T-near"]["pelanggaran"] == ["449_1_d"]


def test_first_run_without_users_shows_setup_admin(app_base):
    app = make_app(app_base)
    assert app.state == "setup_admin"
    app.step([])
    s = app.setup
    s.username.value = "dave"
    s.password.value = "rahasia123"
    s.password2.value = "beda12345"
    s.submit()
    assert app.state == "setup_admin" and "sama" in s.error
    s.password2.value = "rahasia123"
    s.submit()
    assert app.state == "main"
    assert Store(app_base / "data").users_exist()


def test_guide_card_shown_once(app_with_admin):
    app = make_app(app_with_admin)
    assert app.guide_open
    app.step([])
    app.close_guide()
    assert not app.guide_open
    assert not make_app(app_with_admin).guide_open


def test_loading_shows_retry_on_osm_error(app_with_admin):
    import shutil
    from conftest import fake_osm
    shutil.rmtree(app_with_admin / "cache")
    state = {"fail": True}

    def fetcher():
        if state["fail"]:
            raise OSMDownloadError("jalan")
        return fake_osm()

    app = make_app(app_with_admin, fetcher=fetcher)
    assert app.state == "loading"
    assert "jalan" in app.loader.error
    app.step([])
    state["fail"] = False
    app.retry_loading()
    assert app.state == "main"


def test_click_marker_selects_and_shows_reasons(app_with_admin):
    app = make_app(app_with_admin)
    app.close_guide()
    r = app.audit["T-near"]
    app.vp.fly_to(r["x"], r["y"], 16)
    app.step([])
    sx, sy = app.vp.world_to_screen(r["x"], r["y"])
    app.step(click_events((app.map.rect.x + sx, app.map.rect.y + sy)))
    assert app.selected_ids == ["T-near"]
    assert any("SDN Contoh" in line for line in app.detail_lines("T-near"))


def test_search_flies_to_street(app_with_admin):
    app = make_app(app_with_admin)
    app.close_guide()
    box = app.search_box
    app.step(click_events(box.rect.center))
    app.step(type_events("Jemur"))
    assert app.search_results[0][0] == "Jemursari"
    app.pick_search(0)
    r = app.audit["T-road"]
    assert abs(app.vp.cx - r["x"]) < 1 and abs(app.vp.cy - r["y"]) < 1


def test_search_no_result_message(app_with_admin):
    app = make_app(app_with_admin)
    app.close_guide()
    app.step(click_events(app.search_box.rect.center))
    app.step(type_events("zzz"))
    assert app.search_results == []
    assert app.search_message == "Jalan tidak ditemukan"


def test_recheck_updates_status_after_move(app_with_admin):
    from conftest import DX, DY, utm_to_latlon
    app = make_app(app_with_admin)
    lat, lon = utm_to_latlon(7500 + DX, 7500 + DY)
    app.store.update_reklame("T-near", {"latitude": lat, "longitude": lon}, oleh="dave")
    app.recheck("T-near")
    assert app.audit["T-near"]["status"] == "Patuh"
    assert app.counts()["Melanggar"] == 1


def test_every_tab_opens(app_with_admin):
    from app import ADMIN_TABS as ADMIN, PUBLIC_TABS
    app = make_app(app_with_admin)
    app.close_guide()
    for name in PUBLIC_TABS:
        app.set_tab(name)
        for _ in range(3):
            app.step([])
        assert app.tab == name
    app.login_as("dave")
    for name in PUBLIC_TABS + ADMIN:
        app.set_tab(name)
        for _ in range(3):
            app.step([])
        assert app.tab == name
