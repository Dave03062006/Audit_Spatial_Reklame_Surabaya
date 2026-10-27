import json

import pytest

from storage import (LoginGuard, Store, hash_password, read_json,
                     verify_password, write_json_atomic)


def test_atomic_write_keeps_bak(tmp_path):
    p = tmp_path / "x.json"
    write_json_atomic(p, {"v": 1})
    write_json_atomic(p, {"v": 2})
    assert json.loads(p.read_text()) == {"v": 2}
    assert json.loads((tmp_path / "x.json.bak").read_text()) == {"v": 1}
    assert not (tmp_path / "x.json.tmp").exists()


def test_read_json_recovers_from_bak(tmp_path):
    p = tmp_path / "x.json"
    write_json_atomic(p, {"v": 1})
    write_json_atomic(p, {"v": 2})
    p.write_text("{rusak")
    assert read_json(p, default=None) == {"v": 1}


def test_read_json_missing_returns_default(tmp_path):
    assert read_json(tmp_path / "tidak_ada.json", default=[]) == []


def test_password_roundtrip_and_wrong_pw():
    salt, h = hash_password("rahasia123")
    assert verify_password("rahasia123", salt, h)
    assert not verify_password("salah", salt, h)


def test_login_guard_locks_after_5_fails_for_30s():
    g = LoginGuard()
    for _ in range(5):
        g.record(False, now=100.0)
    assert g.locked(100.0 + 29)
    assert g.seconds_left(100.0 + 29) == 1
    assert not g.locked(100.0 + 31)


def test_login_guard_success_resets():
    g = LoginGuard()
    for _ in range(4):
        g.record(False, now=0)
    g.record(True, now=0)
    g.record(False, now=0)
    assert not g.locked(1)


def test_create_user_and_login(tmp_data_dir):
    s = Store(tmp_data_dir)
    assert not s.users_exist()
    s.create_user("dave", "rahasia123")
    assert s.users_exist()
    assert s.check_login("dave", "rahasia123")
    assert not s.check_login("dave", "salah")
    assert not s.check_login("orang", "rahasia123")
    with pytest.raises(ValueError):
        s.create_user("dave", "lainlain99")
    with pytest.raises(ValueError):
        s.create_user("baru", "pendek")


def test_reklame_db_created_with_extra_fields(tmp_data_dir):
    rows = Store(tmp_data_dir).reklame()
    assert len(rows) == 3
    r = rows[0]
    assert r["sumber"] == "Bapenda"
    assert r["status_verifikasi"] == "terverifikasi"
    assert r["dihapus"] is False
    assert r["diubah_oleh"] is None and r["diubah_pada"] is None
    assert r["kategori_dikonfirmasi"] is False
    assert (tmp_data_dir / "reklame_db.json").exists()


def test_original_file_untouched(tmp_data_dir):
    orig = tmp_data_dir / "reklame_surabaya_outdoor_semua.json"
    before = orig.read_bytes()
    s = Store(tmp_data_dir)
    s.update_reklame("T-1", {"isi_reklame": "IQOS BARU"}, oleh="dave")
    assert orig.read_bytes() == before
    r = [x for x in Store(tmp_data_dir).reklame() if x["id"] == "T-1"][0]
    assert r["isi_reklame"] == "IQOS BARU"
    assert r["diubah_oleh"] == "dave" and r["diubah_pada"]


def test_add_reklame_ids(tmp_data_dir):
    s = Store(tmp_data_dir)
    a = s.add_reklame({"isi_reklame": "X", "kategori_materi": "Rokok", "latitude": -7.3, "longitude": 112.7}, oleh="dave")
    b = s.add_reklame({"isi_reklame": "Y", "kategori_materi": "Rokok", "latitude": -7.3, "longitude": 112.7}, oleh="dave")
    assert a == "A-1" and b == "A-2"
    row = [x for x in s.reklame() if x["id"] == a][0]
    assert row["sumber"] == "admin" and row["dihapus"] is False


def test_terima_laporan_creates_reklame_with_sumber_laporan_warga(tmp_data_dir):
    s = Store(tmp_data_dir)
    rid = s.add_laporan(-7.31, 112.72, "SAMPOERNA", "Rokok", ["449_1_d"], None)
    assert rid == "R-1"
    assert s.laporan()[0]["status"] == "menunggu"
    new_id = s.terima_laporan(rid, oleh="dave", lat=-7.312, lon=112.721)
    assert new_id == "L-1"
    row = [x for x in s.reklame() if x["id"] == new_id][0]
    assert row["sumber"] == "laporan warga"
    assert row["latitude"] == -7.312 and row["longitude"] == 112.721
    lap = s.laporan()[0]
    assert lap["status"] == "diterima" and lap["diproses_oleh"] == "dave"


def test_tolak_requires_alasan(tmp_data_dir):
    s = Store(tmp_data_dir)
    rid = s.add_laporan(-7.31, 112.72, "X", "Rokok", [], "Budi")
    with pytest.raises(ValueError):
        s.tolak_laporan(rid, oleh="dave", alasan="   ")
    s.tolak_laporan(rid, oleh="dave", alasan="Bukan reklame rokok")
    lap = s.laporan()[0]
    assert lap["status"] == "ditolak" and lap["alasan_tolak"] == "Bukan reklame rokok"


def test_soft_delete_keeps_row(tmp_data_dir):
    s = Store(tmp_data_dir)
    s.delete_reklame("T-2", oleh="dave")
    row = [x for x in s.reklame() if x["id"] == "T-2"][0]
    assert row["dihapus"] is True


def test_settings_roundtrip(tmp_data_dir):
    s = Store(tmp_data_dir)
    assert s.settings() == {}
    s.save_settings({"panduan_dilihat": True})
    assert Store(tmp_data_dir).settings() == {"panduan_dilihat": True}
