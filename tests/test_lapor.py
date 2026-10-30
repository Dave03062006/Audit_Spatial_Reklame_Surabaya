from conftest import DX, DY, click_events, make_app
from storage import Store


def wizard(app_base):
    app = make_app(app_base)
    app.close_guide()
    app.set_tab("Laporkan Reklame")
    app.step([])
    return app, app.screens["Laporkan Reklame"].wizard


def test_lapor_requires_pin_and_isi(app_with_admin):
    app, w = wizard(app_with_admin)
    assert w.step == 1
    assert w.next() == "Klik peta untuk menandai lokasi reklame."
    w.set_pin(1300 + DX, 1000 + DY)
    assert w.next() is None and w.step == 2
    w.isi = "   "
    assert w.next() == "Isi teks atau merek pada reklame."
    assert w.step == 2


def test_lapor_step3_shows_violation_for_pin_near_school(app_with_admin):
    app, w = wizard(app_with_admin)
    w.set_pin(1300 + DX, 1000 + DY)
    w.next()
    w.isi, w.kategori = "SAMPOERNA MILD", " rokok "
    assert w.next() is None and w.step == 3
    codes, lines = w.hasil()
    assert codes == ["449_1_d"]
    assert "SDN Contoh" in lines[0]


def test_lapor_step3_no_violation_text(app_with_admin):
    app, w = wizard(app_with_admin)
    w.set_pin(7000 + DX, 7000 + DY)
    w.next()
    w.isi, w.kategori = "DJARUM", "Rokok"
    w.next()
    assert w.hasil() == ([], ["Tidak ditemukan dugaan pelanggaran."])


def test_lapor_kirim_saves_menunggu_with_hasil_cek(app_with_admin):
    app, w = wizard(app_with_admin)
    w.set_pin(1300 + DX, 1000 + DY)
    w.next()
    w.isi, w.kategori, w.nama = "SAMPOERNA MILD", "Rokok", "Budi"
    w.next()
    rid = w.kirim()
    lap = Store(app_with_admin / "data").laporan()[0]
    assert lap["id"] == rid and lap["status"] == "menunggu"
    assert lap["hasil_cek"] == ["449_1_d"]
    assert lap["nama_pelapor"] == "Budi"
    assert -7.5 < lap["lat"] < -7.0 and 112.0 < lap["lon"] < 113.5
    assert w.step == 1 and w.pin is None
    assert app.toast.msg == "Laporan terkirim. Menunggu verifikasi admin."


def test_map_click_places_pin(app_with_admin):
    app, w = wizard(app_with_admin)
    app.vp.fly_to(3000 + DX, 6000 + DY, 15)
    app.step([])
    app.step(click_events(app.map.rect.center))
    assert w.pin is not None
    assert abs(w.pin[0] - (3000 + DX)) < 5
    assert app.map.pin == w.pin


def test_kategori_alkohol_has_no_allowed_area_note(app_with_admin):
    from ui.screens.lokasi_boleh import NOTE_ALKOHOL
    app = make_app(app_with_admin)
    app.close_guide()
    app.set_tab("Lokasi yang Boleh")
    app.step([])
    assert "dilarang di seluruh Surabaya" in NOTE_ALKOHOL
    scr = app.screens["Lokasi yang Boleh"]
    assert scr.overlays() == {"area_boleh", "zona", "koridor"}
    # centang lapisan di panel kiri juga berlaku di tab ini
    app.set_layer("zona", False)
    app.set_layer("koridor", False)
    assert scr.overlays() == {"area_boleh"}
    assert {m.id for m in scr.markers()} == {"T-far"}
