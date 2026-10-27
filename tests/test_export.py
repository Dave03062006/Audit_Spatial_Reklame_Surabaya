import csv
from datetime import date

from conftest import click_events, make_app
from export import CSV_COLUMNS, pelanggaran_csv


def test_csv_only_melanggar_rows(app_with_admin, tmp_path):
    app = make_app(app_with_admin)
    p = pelanggaran_csv(list(app.audit.values()), app.zones, tmp_path, date(2026, 10, 27))
    assert p.name == "pelanggaran_20261027.csv"
    rows = list(csv.DictReader(p.open(encoding="utf-8-sig")))
    assert sorted(r["id"] for r in rows) == ["T-near", "T-road"]
    near = [r for r in rows if r["id"] == "T-near"][0]
    assert near["pasal"] == "Ps. 449 (1) d"
    assert near["sekolah_terdekat"] == "SDN Contoh"
    assert near["jarak_sekolah_m"] == "280"


def test_csv_has_bom_and_columns(app_with_admin, tmp_path):
    app = make_app(app_with_admin)
    p = pelanggaran_csv(list(app.audit.values()), app.zones, tmp_path, date(2026, 10, 27))
    raw = p.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    header = raw[3:].split(b"\r\n")[0].decode()
    assert header.split(",") == CSV_COLUMNS


def open_tabel(app):
    app.close_guide()
    app.set_tab("Tabel Pelanggaran")
    app.step([])
    return app.screens["Tabel Pelanggaran"]


def test_table_lists_violations_only(app_with_admin):
    app = make_app(app_with_admin)
    t = open_tabel(app)
    assert sorted(r["id"] for r in t.table.rows) == ["T-near", "T-road"]


def test_table_pasal_filter(app_with_admin):
    app = make_app(app_with_admin)
    t = open_tabel(app)
    t.pasal.value = "Ps. 449 (1) c"
    t.refresh()
    assert [r["id"] for r in t.table.rows] == ["T-road"]


def test_table_alamat_search(app_with_admin):
    app = make_app(app_with_admin)
    t = open_tabel(app)
    t.query.value = "ketintang"
    t.refresh()
    assert [r["id"] for r in t.table.rows] == ["T-near"]


def test_table_row_click_flies_to_map(app_with_admin):
    app = make_app(app_with_admin)
    t = open_tabel(app)
    t.table.sort_key = "id"
    t.refresh()
    y = t.table.row_rect(0).centery
    first = t.table.visible_rows()[0]
    app.step(click_events((t.table.rect.x + 40, y)))
    assert app.tab == "Peta"
    assert app.selected_ids == [first["id"]]
    assert abs(app.vp.cx - app.audit[first["id"]]["x"]) < 1


def test_export_button_writes_file(app_with_admin):
    app = make_app(app_with_admin)
    t = open_tabel(app)
    t.export()
    files = list((app.base / "exports").glob("pelanggaran_*.csv"))
    assert len(files) == 1
