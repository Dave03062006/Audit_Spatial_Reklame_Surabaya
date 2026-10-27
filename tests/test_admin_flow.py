from conftest import DX, DY, make_app
from storage import Store
from ui.map_view import MapEvent

ADMIN_TABS = {"Kelola", "Verifikasi", "Perlu Cek"}


def admin_app(base):
    app = make_app(base)
    app.close_guide()
    app.open_login()
    m = app.modal
    m.username.value, m.password.value = "dave", "rahasia123"
    m.submit(now=0)
    assert app.modal is None
    return app


def test_admin_tabs_hidden_for_warga(app_with_admin):
    app = make_app(app_with_admin)
    assert not ADMIN_TABS & set(app.tab_names())
    assert app.admin_detail_actions("T-near") == []


def test_login_success_shows_admin_tabs(app_with_admin):
    app = admin_app(app_with_admin)
    assert app.role == "admin" and app.admin_name == "dave"
    assert ADMIN_TABS <= set(app.tab_names())
    assert [label for label, _ in app.admin_detail_actions("T-near")] == ["Ubah data", "Geser lokasi"]
    app.step([])


def test_login_wrong_password_message(app_with_admin):
    app = make_app(app_with_admin)
    app.open_login()
    m = app.modal
    m.username.value, m.password.value = "dave", "salah"
    m.submit(now=0)
    assert m.error == "Username atau password salah."
    assert app.role == "warga"


def test_login_lockout_message(app_with_admin):
    app = make_app(app_with_admin)
    app.open_login()
    m = app.modal
    m.username.value, m.password.value = "dave", "salah"
    for _ in range(5):
        m.submit(now=0)
    m.password.value = "rahasia123"
    m.submit(now=1)
    assert m.error == "Terlalu banyak percobaan. Coba lagi dalam 29 detik."
    assert app.role == "warga"
    m.submit(now=31)
    assert app.role == "admin"


def kelola(app):
    app.set_tab("Kelola")
    app.step([])
    return app.screens["Kelola"]


def test_add_reklame_near_school_becomes_melanggar(app_with_admin):
    app = admin_app(app_with_admin)
    k = kelola(app)
    k.start_add()
    k.on_map_event(MapEvent("empty", [], 1200 + DX, 1100 + DY))
    k.form["isi"].value = "GUDANG GARAM"
    k.form["kategori"].value = "Rokok"
    k.form["tayang_selesai"].value = "2027-06-30"
    new_id = k.save()
    assert new_id == "A-1"
    assert app.audit[new_id]["status"] == "Melanggar"
    assert Store(app_with_admin / "data").get_reklame(new_id)["sumber"] == "admin"


def test_form_rejects_bad_date(app_with_admin):
    app = admin_app(app_with_admin)
    k = kelola(app)
    k.start_edit("T-far")
    assert k.form["isi"].value == "ISI T-far"
    k.form["tayang_selesai"].value = "30-06-2027"
    assert k.save() is None
    assert k.error == "Tanggal harus berformat YYYY-MM-DD, misalnya 2027-06-30."


def test_edit_kategori_rechecks(app_with_admin):
    app = admin_app(app_with_admin)
    k = kelola(app)
    k.start_edit("T-umum")
    k.form["kategori"].value = "Minuman beralkohol"
    assert k.save() == "T-umum"
    assert app.audit["T-umum"]["status"] == "Melanggar"


def test_move_pin_out_of_zone_becomes_patuh(app_with_admin):
    app = admin_app(app_with_admin)
    k = kelola(app)
    k.start_move("T-near")
    assert app.map.draggable_id == "T-near"
    k.on_map_event(MapEvent("drag_end", ["T-near"], 7600 + DX, 7600 + DY))
    assert app.audit["T-near"]["status"] == "Patuh"
    assert app.map.draggable_id is None


def test_delete_needs_confirm(app_with_admin):
    app = admin_app(app_with_admin)
    k = kelola(app)
    k.request_delete("T-far")
    assert "T-far" in app.audit
    k.confirm_delete()
    assert "T-far" not in app.audit
    assert Store(app_with_admin / "data").get_reklame("T-far")["dihapus"] is True


def verifikasi_with_report(base):
    s = Store(base / "data")
    from conftest import utm_to_latlon
    lat, lon = utm_to_latlon(1250 + DX, 1050 + DY)
    rid = s.add_laporan(lat, lon, "SAMPOERNA", "Rokok", ["449_1_d"], "Budi")
    app = admin_app(base)
    app.set_tab("Verifikasi")
    app.step([])
    v = app.screens["Verifikasi"]
    return app, v, rid


def test_terima_report_adds_marker(app_with_admin):
    app, v, rid = verifikasi_with_report(app_with_admin)
    assert [r["id"] for r in v.pending()] == [rid]
    v.select_report(rid)
    v.on_map_event(MapEvent("empty", [], 1300 + DX, 1000 + DY))
    new_id = v.terima()
    assert new_id == "L-1"
    assert app.audit[new_id]["status"] == "Melanggar"
    assert abs(app.audit[new_id]["x"] - (1300 + DX)) < 1
    assert v.pending() == []


def test_tolak_without_alasan_blocked(app_with_admin):
    app, v, rid = verifikasi_with_report(app_with_admin)
    v.select_report(rid)
    assert v.tolak("  ") == "Alasan penolakan wajib diisi."
    assert len(v.pending()) == 1
    assert v.tolak("Foto tidak jelas, bukan iklan rokok") is None
    assert v.pending() == []


def test_perlu_cek_confirm_clears_flag(app_with_admin):
    app = admin_app(app_with_admin)
    app.set_tab("Perlu Cek")
    app.step([])
    p = app.screens["Perlu Cek"]
    assert [r["id"] for r in p.rows()] == ["T-cek"]
    p.confirm("T-cek", "Minuman beralkohol")
    assert app.audit["T-cek"]["status"] == "Melanggar"
    assert p.rows() == []


def test_logout_returns_to_warga(app_with_admin):
    app = admin_app(app_with_admin)
    app.set_tab("Kelola")
    app.logout()
    assert app.role == "warga" and app.tab == "Peta"
    assert not ADMIN_TABS & set(app.tab_names())
