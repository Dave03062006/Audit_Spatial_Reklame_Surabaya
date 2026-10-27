# Reklame Audit (Pygame) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Pygame desktop app that audits every outdoor billboard in Surabaya against PP 28/2024 Ps. 449 (1) c/d and Perda 5/2019 Ps. 23, for the public (no login) and admins (login).

**Architecture:** `data_prep.py` downloads OSM once and caches projected layers + dissolved zones in `cache/layers.gpkg`. `gis.py` is pure GeoPandas/Shapely rule logic. `storage.py` owns every write to `data/`. `ui/` is Pygame only, and reads through `gis.py` and writes through `storage.py`. Base-map tiles are rendered by Pygame on demand and cached as PNGs.

**Tech Stack:** Python 3.11+, pygame-ce 2.5, geopandas ≥1.0, shapely ≥2.0, osmnx ≥2.0, pyogrio, pytest.

**Spec:** `docs/superpowers/specs/2026-10-27-reklame-audit-pygame-design.md`

## Global Constraints

- Window 1280×800. All UI copy is in Bahasa Indonesia. Click targets are ≥44 px.
- Colours: navy `#173B57`, Melanggar red `#C8452F` + "!" icon, Patuh blue `#1F4FA3` + check icon, Umum grey `#9AAAB6`, zone teal `#2E7A9A`, map ground `#F7F5EF`.
- Metric CRS `EPSG:32749`. Source CRS `EPSG:4326`. `RADIUS_M = 500`, `KORIDOR_M = 25`.
- Jalan utama = OSM `highway` in {`trunk`, `trunk_link`, `primary`, `primary_link`}. Tol = `motorway`, `motorway_link`. Penghubung = `secondary`, `tertiary` (+`_link`). Everything else is kecil.
- Education facilities: TK/PAUD/RA, SD/MI, SMP/MTs, SMA/SMK/MA. Universities are excluded.
- Status values (exact strings): `Melanggar`, `Patuh`, `Tidak diaudit`, `Perlu cek`, `Tayang berakhir`.
- Rule codes (exact): `449_1_d`, `449_1_c`, `perda_5_2019_23`.
- Kategori values (exact): `Umum`, `Rokok`, `Rokok elektronik`, `Minuman beralkohol`.
- `data/reklame_surabaya_outdoor_semua.json` is never written to.
- Password hash: `hashlib.pbkdf2_hmac('sha256', pw, salt, 200_000)`, with a 16-byte salt.
- Code style follows the week 5 notebook: small plain functions, `# Layer 1 (Fasilitas)` / `# Layer 2 (Reklame)` / `# Layer 3 (Jalan)` comments, and `if __name__ == "__main__":` blocks that print readable summaries.
- Only `data_prep.py` touches the network.

## Review Focus

1. **Missing or `"-"` `tayang_selesai`** is not "Tayang berakhir". The test is in Task 2 (`test_status_missing_tayang_is_not_expired`).
2. **A school with no `name` tag** shows "Sekolah tanpa nama" in the reasons and does not crash. The test is in Task 2 (`test_nearest_info_unnamed_school`).
3. **Kategori typed in a different case or with extra spaces** (" rokok ") in a report or admin form is normalised before checking. The test is in Task 2 (`test_normalize_kategori`).
4. **A report submitted with an empty `isi_reklame` or with no pin placed** is blocked with an inline message, not saved. The test is in Task 8 (`test_lapor_requires_pin_and_isi`).
5. **Panning to a tile outside the data bounds** renders an empty ground tile, not an exception. The test is in Task 4 (`test_tile_outside_bounds_is_blank`).

---

### Task 1: Project scaffold and storage

**Files:**
- Create: `requirements.txt`, `.gitignore` (ignore `cache/`, `exports/`, `data/*.bak`, `data/*.tmp`, `data/reklame_db.json`, `data/laporan.json`, `data/users.json`, `data/settings.json`, `__pycache__/`), `README.md` (setup + run steps, in Indonesian and English)
- Create: `data/reklame_surabaya_outdoor_semua.json` (copy of Dave's upload)
- Create: `storage.py`
- Test: `tests/test_storage.py`, `tests/conftest.py` (fixture `tmp_data_dir` holding a 3-row copy of the original JSON format)

**Interfaces:**
- Produces:
  - `write_json_atomic(path: Path, data) -> None`: writes `path.tmp`, copies the current file to `path.bak` if one exists, then `os.replace`.
  - `read_json(path: Path, default) -> Any`: on a missing file returns `default`; on invalid JSON loads `path.bak` and prints a warning.
  - `hash_password(pw: str, salt: bytes | None = None) -> tuple[str, str]` returns (salt_hex, hash_hex). `verify_password(pw, salt_hex, hash_hex) -> bool` uses `hmac.compare_digest`.
  - `class LoginGuard(max_fail=5, lock_s=30)`: `.record(ok: bool, now: float)`, `.locked(now: float) -> bool`, `.seconds_left(now) -> int`.
  - `class Store(data_dir: Path)` with:
    - `users_exist() -> bool`, `create_user(username, pw) -> None` (ValueError if the name is taken or the password is shorter than 8 characters), `check_login(username, pw) -> bool`
    - `reklame() -> list[dict]`: on first call it builds `reklame_db.json` from the original, adding `sumber="Bapenda"`, `status_verifikasi="terverifikasi"`, `dihapus=False`, `diubah_oleh=None`, `diubah_pada=None`, `kategori_dikonfirmasi=False`
    - `add_reklame(row: dict, oleh: str, sumber: str = "admin") -> str`: new id `A-<n>` for admin rows, `L-<n>` for laporan
    - `update_reklame(id: str, changes: dict, oleh: str) -> dict`
    - `delete_reklame(id, oleh) -> None`: soft delete
    - `laporan() -> list[dict]`, `add_laporan(lat, lon, isi_reklame, kategori_materi, hasil_cek: list[str], nama_pelapor: str | None) -> str`: id `R-<n>`, status `menunggu`
    - `terima_laporan(id, oleh, lat=None, lon=None) -> str`: returns the new reklame id
    - `tolak_laporan(id, oleh, alasan: str) -> None`: ValueError if `alasan.strip()` is empty
    - `settings() -> dict`, `save_settings(d: dict) -> None`

- [ ] **Step 1: Write the failing tests.** `test_atomic_write_keeps_bak`, `test_read_json_recovers_from_bak` (write valid data, then corrupt the main file, then `read_json` returns the valid data), `test_password_roundtrip_and_wrong_pw`, `test_login_guard_locks_after_5_fails_for_30s` (locked at now+29, unlocked at now+31), `test_reklame_db_created_with_extra_fields`, `test_original_file_untouched` (compare mtime and bytes after `update_reklame`), `test_terima_laporan_creates_reklame_with_sumber_laporan_warga`, `test_tolak_requires_alasan`, `test_soft_delete_keeps_row`.
- [ ] **Step 2: Run** `pytest tests/test_storage.py -v`. Expected: all FAIL (ImportError).
- [ ] **Step 3: Implement `storage.py`** with the signatures above. Timestamps are `datetime.now().isoformat(timespec="seconds")`.
- [ ] **Step 4: Run** `pytest tests/test_storage.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: scaffold project and JSON storage with atomic writes`.

### Task 2: GIS rules (`gis.py`)

**Files:**
- Create: `gis.py`
- Test: `tests/test_gis.py`, plus `tests/conftest.py` fixtures `tiny_layers`. These are synthetic, already in EPSG:32749 metres: school A as a 20×20 m polygon at (1000,1000) named "SDN Contoh"; school B as a point at (5000,5000) with no name; jalan utama as the line (0,3000)→(6000,3000); a kecil road as (0,4000)→(6000,4000); batas as box(0,0,8000,8000).

**Interfaces:**
- Consumes: none (pure).
- Produces:
  - Constants `RADIUS_M`, `KORIDOR_M`, `CRS_METER`, `CRS_SOURCE`, `KATEGORI_AUDIT = {"Rokok", "Rokok elektronik"}`, `KATEGORI_ALKOHOL = "Minuman beralkohol"`, `RULE_LABELS: dict[str, str]` (code → "PP 28/2024 Ps. 449 (1) d: radius 500 m dari satuan pendidikan", etc.)
  - `normalize_kategori(s: str) -> str`: case- and space-insensitive match to the 4 exact values. ValueError otherwise.
  - `load_reklame(records: list[dict]) -> gpd.GeoDataFrame` in EPSG:32749. It skips rows with a null lat/lon and dihapus=True, and prints how many were skipped.
  - `@dataclass Zones`: `fasilitas: GeoDataFrame`, `jalan: GeoDataFrame`, `batas: Polygon`, `zona_500`, `koridor_25`, `area_boleh` (shapely geometries), plus `zona_prep`, `koridor_prep` (prepared). `Zones.build(fasilitas, jalan, batas) -> Zones` computes the three geometries with `buffer` + `union_all()` and `batas.difference(...)`.
  - `check_point(pt: Point, kategori: str, zones: Zones) -> list[str]`: returns rule codes in the order `449_1_d`, `449_1_c`, `perda_5_2019_23`. It uses `intersects`, so a point exactly 500 m away counts.
  - `status_of(row: dict, pelanggaran: list[str], today: date) -> str`. Precedence: `perlu_cek_manual` set and not `kategori_dikonfirmasi` gives `Perlu cek`; then `Umum` gives `Tidak diaudit`; then a parseable `tayang_selesai` < today gives `Tayang berakhir`; then a non-empty pelanggaran gives `Melanggar`; otherwise `Patuh`.
  - `audit_all(reklame: GeoDataFrame, zones: Zones, today: date) -> GeoDataFrame`: adds `pelanggaran: list[str]` and `status: str`. It uses one `gpd.sjoin(..., predicate="intersects")` against each of the zona and koridor single-row frames. It does not loop `check_point` over all rows.
  - `nearest_info(pt: Point, zones: Zones) -> dict` with keys `sekolah_nama` ("Sekolah tanpa nama" if missing), `sekolah_jenis`, `sekolah_jarak_m: int`, `jalan_utama_jarak_m: int`. It uses `sjoin_nearest` with `distance_col`.
  - `alasan_text(pelanggaran: list[str], info: dict) -> list[str]`: the human sentences shown in the detail panel, e.g. `"312 m dari SDN Contoh (di dalam radius 500 m)"`.

- [ ] **Step 1: Write the failing tests:**
  - `test_rokok_inside_500m_violates_d`: Point(1300,1000) → `["449_1_d"]`
  - `test_rokok_outside_patuh`: Point(7000,7000) → `[]`
  - `test_exactly_500m_counts`: a point 500 m from school A's polygon edge → contains `449_1_d`
  - `test_on_main_road_violates_c`: Point(7000,3010) → `["449_1_c"]`
  - `test_kecil_road_not_corridor`: Point(7000,4005) → `[]`
  - `test_both_rules`: Point(1000,3000) with school A shifted so it is within 500 m → `["449_1_d","449_1_c"]` (use a fixture variant)
  - `test_alkohol_anywhere`: `["perda_5_2019_23"]` at (7000,7000)
  - `test_umum_tidak_diaudit`, `test_perlu_cek_precedence`, `test_expired_tayang_berakhir`, `test_status_missing_tayang_is_not_expired` (values `None` and `"-"`)
  - `test_area_boleh_excludes_zones_and_corridor`: Point(1300,1000) and Point(7000,3010) are not in `area_boleh`, and Point(7000,7000) is
  - `test_audit_all_matches_check_point` on 6 mixed rows
  - `test_nearest_info_unnamed_school`
  - `test_normalize_kategori` (" rokok " → "Rokok", "ROKOK ELEKTRONIK" → "Rokok elektronik", "bir" → ValueError)
- [ ] **Step 2: Run** `pytest tests/test_gis.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `gis.py`.** Group the code under `# Layer 1 (Fasilitas)`, `# Layer 2 (Reklame)`, `# Layer 3 (Jalan)` and `# Operasi GIS: buffer + spatial join` comments. Add a `__main__` that builds zones from the tiny layers and prints the check results, the way the notebook does.
- [ ] **Step 4: Run** `pytest tests/test_gis.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: GIS rule engine for PP 28/2024 and Perda 5/2019`.

### Task 3: Data prep and cache (`data_prep.py`)

**Files:**
- Create: `data_prep.py`
- Test: `tests/test_data_prep.py` (uses a fake fetcher that returns the `tiny_layers` in EPSG:4326, so there is no network)

**Interfaces:**
- Consumes: `gis.Zones`, `gis.CRS_METER`, `gis.RADIUS_M`, `gis.KORIDOR_M`
- Produces:
  - `class OSMDownloadError(Exception)` with `.layer: str` (`"fasilitas"` | `"jalan"` | `"batas"`)
  - `jenis_sekolah(tags: dict) -> str | None`: uses `amenity=kindergarten` → `"TK"`, then `isced:level` (0→TK, 1→SD, 2→SMP, 3→SMA/SMK), then the name prefix regex (`^(TK|PAUD|RA|KB)\b`, `^(SD|MI)\b`, `^(SMP|MTS)\b`, `^(SMA|SMK|MA)\b`, case-insensitive, also matching after "SDN"/"SMPN"/"SMAN"/"SMKN"), and otherwise `"sekolah (lainnya)"`. It returns `None` for `amenity` in {`university`, `college`}.
  - `tipe_jalan(highway: str | list) -> str`: for a list, it takes the highest-ranked value.
  - `fetch_osm(place: str = "Surabaya, Indonesia") -> dict[str, GeoDataFrame]` with keys `fasilitas`, `jalan`, `batas`. It wraps each osmnx call and raises `OSMDownloadError(layer)` on failure.
  - `cache_is_fresh(cache_dir: Path, reklame_path: Path) -> bool`: compares the `manifest.json` fields `reklame_mtime`, `reklame_size`, `radius_m`, `koridor_m` and `cache_version` (= 1).
  - `build_cache(cache_dir: Path, reklame_path: Path, fetcher=fetch_osm, progress=lambda pct, msg: None, refresh_osm: bool = False) -> None`. It writes `cache/osm_raw.gpkg` (reused unless `refresh_osm` is set or it is missing) and `cache/layers.gpkg` with the layers `fasilitas`, `jalan`, `batas`, `zona_500`, `koridor_25`, `area_boleh`, then writes `manifest.json`. It calls `progress` at least 5 times with increasing pct between 0 and 100.
  - `load_zones(cache_dir: Path) -> gis.Zones`
  - CLI: `python data_prep.py [--refresh-osm]` prints counts per layer and per jenis/tipe.

- [ ] **Step 1: Write the failing tests:** `test_jenis_sekolah_cases` (kindergarten, "SDN Ketintang I", "SMPN 12", "MTs Al-Huda", an `isced:level=3` tag, a university → None, "Sekolah Alam" → "sekolah (lainnya)"), `test_tipe_jalan_cases` (including `["primary","secondary"]` → "jalan utama"), `test_build_cache_then_fresh`, `test_reklame_change_makes_stale` (touch the file → not fresh), `test_osm_raw_reused` (the fake fetcher counts calls, so a second `build_cache` after a reklame change calls it 0 times), `test_fetch_failure_names_layer`, `test_load_zones_roundtrip` (`check_point` gives the same results as Task 2).
- [ ] **Step 2: Run** `pytest tests/test_data_prep.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `data_prep.py`.** Use `osmnx.features_from_place(place, {"amenity": ["school", "kindergarten"]})`, `osmnx.graph_from_place(place, network_type="drive")` → `osmnx.graph_to_gdfs(G, nodes=False)`, and `osmnx.geocode_to_gdf("Kota Surabaya, Jawa Timur, Indonesia")`. Write with `pyogrio` via `GeoDataFrame.to_file(..., layer=...)`.
- [ ] **Step 4: Run** `pytest tests/test_data_prep.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: OSM data prep with manifest-based cache`.

### Task 4: Map view: viewport, tiles, clustering (`ui/map_view.py`)

**Files:**
- Create: `ui/__init__.py`, `ui/theme.py`, `ui/map_view.py`
- Test: `tests/test_map_view.py` (`SDL_VIDEODRIVER=dummy`, set in conftest)

**Interfaces:**
- Consumes: `gis.Zones`
- Produces:
  - `ui/theme.py`: the colour constants named in Global Constraints (`NAVY`, `MERAH`, `BIRU_PATUH`, `ABU_UMUM`, `TEAL`, `TANAH`, `PUTIH`, `TEKS`, `TEKS_SEKUNDER`), `STATUS_COLOR: dict[str, tuple]`, `MIN_TARGET = 44`, and `font(size: int, bold=False) -> pygame.font.Font`. It loads `assets/fonts/PublicSans-*.ttf` if present, otherwise `pygame.font.Font(None, size)`, and caches per size.
  - `ZOOM_MIN = 11`, `ZOOM_MAX = 17`, `TILE_PX = 256`, `mpp(z: int) -> float = 156543.03 * cos(radians(-7.27)) / 2**z`
  - `class Viewport(cx: float, cy: float, zoom: int, size: tuple[int, int])` with `world_to_screen(x, y) -> (int, int)`, `screen_to_world(px, py) -> (float, float)`, `pan(dx_px, dy_px)`, `zoom_at(px, py, step: int)` (keeps the world point under the cursor fixed and clamps to 11–17), and `fly_to(x, y, zoom=16)`
  - `class TileCache(zones: Zones, cache_dir: Path, mem_limit: int = 256)`: `.get(z, tx, ty) -> pygame.Surface`. The tile grid origin is `zones.batas.bounds` minx/maxy. It renders water/ground, roads by tipe (width by tipe, jalan utama white with a grey casing), and school shapes in navy. It saves to `cache/tiles/{z}/{tx}_{ty}.png`, loads from disk on a hit, and evicts LRU in memory.
  - `cluster(points: list[tuple[str, float, float]], vp: Viewport, radius_px: int = 18) -> list[Cluster]`, where `Cluster` is a dataclass with `x, y, ids: list[str]`. It buckets by screen grid; identical coordinates always share a cluster.
  - `class MapView(rect: pygame.Rect, zones, tiles: TileCache, vp: Viewport)`: `.draw(surface, markers: list[Marker], overlays: set[str])`, where overlays are a subset of {"zona", "koridor", "area_boleh"}, drawn as translucent `SRCALPHA` polygons. `.handle(event) -> MapEvent | None`, where `MapEvent` is a dataclass with `kind` ("marker" | "empty" | "drag_end"), `ids`, `x`, `y`. `Marker` is a dataclass with `id, x, y, status`.

- [ ] **Step 1: Write the failing tests:** `test_world_screen_roundtrip`, `test_zoom_at_keeps_point_under_cursor`, `test_zoom_clamped`, `test_tile_written_to_disk_and_reused` (second get with mem cleared loads the PNG; mock the render to count calls), `test_tile_outside_bounds_is_blank`, `test_identical_coords_cluster_together`, `test_far_points_not_clustered`, `test_click_on_marker_returns_ids`.
- [ ] **Step 2: Run** `pytest tests/test_map_view.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `ui/theme.py` and `ui/map_view.py`. Draw markers by status: Melanggar is a red circle with a white "!", Patuh is a blue circle with a white check, Umum is a 3.5 px grey dot, Perlu cek is amber `#B7791F` with "?", and Tayang berakhir is grey at 40% alpha. A cluster is a navy circle with its count.
- [ ] **Step 4: Run** `pytest tests/test_map_view.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: pygame map view with cached tiles and clustering`.

### Task 5: Widgets (`ui/widgets.py`)

**Files:**
- Create: `ui/widgets.py`, `assets/fonts/` (Public Sans Regular/SemiBold/ExtraBold TTF, OFL; if the download is blocked, leave the folder with a README and rely on the fallback)
- Test: `tests/test_widgets.py`

**Interfaces:**
- Produces (every widget has `.draw(surface)` and `.handle(event) -> bool | Any`):
  - `Button(rect, text, on_click, kind="primary"|"secondary"|"danger", enabled=True)`. The rect height is raised to ≥44.
  - `TextInput(rect, placeholder, password=False, max_len=120)` with `.value`. It uses `pygame.TEXTINPUT` events, Backspace, and Enter → returns `"submit"`.
  - `Checkbox(rect, label, checked)`, `Dropdown(rect, options: list[str], value)`
  - `Table(rect, columns: list[tuple[key, label, width]], rows: list[dict], page_size=15)` with `.sort_by(key)` (toggles asc/desc), `.page`, and `.handle` → returns the clicked row dict
  - `Modal(title, body_widgets, buttons)`, `Toast.show(text, seconds=3)`
  - `StatusBadge.draw(surface, pos, status)`: colour + icon + word

- [ ] **Step 1: Write the failing tests:** `test_button_min_height_44`, `test_button_click_calls_handler`, `test_disabled_button_ignores_click`, `test_textinput_typing_and_backspace`, `test_password_input_masks_render_text` (check `.display_text()` is bullets), `test_table_sort_and_pagination`, `test_table_row_click_returns_row`.
- [ ] **Step 2: Run** `pytest tests/test_widgets.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `ui/widgets.py`.
- [ ] **Step 4: Run** `pytest tests/test_widgets.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: basic pygame widgets`.

### Task 6: App shell, loading, first admin, guide card, Peta tab, search

**Files:**
- Create: `app.py`, `search.py`, `ui/screens/__init__.py`, `ui/screens/loading.py`, `ui/screens/setup_admin.py`, `ui/screens/peta.py`, `ui/screens/detail_panel.py`
- Test: `tests/test_search.py`, `tests/test_app_smoke.py` (first part)

**Interfaces:**
- Consumes: `Store`, `gis.*`, `data_prep.cache_is_fresh/build_cache/load_zones/OSMDownloadError`, `MapView`, widgets
- Produces:
  - `search.build_index(reklame: GeoDataFrame, jalan: GeoDataFrame) -> list[tuple[str, float, float]]`. Labels are street names (with the `NO.` part stripped from `alamat`) and OSM `name` values; each label maps to the centroid of its matches. `search.find(index, q: str, limit=8) -> list[tuple[str, float, float]]` does a case-insensitive substring search, with prefix matches first, and returns `[]` for a blank `q`. When there are no results, the search dropdown shows "Jalan tidak ditemukan".
  - `class App(base_dir: Path, today: date | None = None, headless: bool = False)` with attributes `store`, `zones`, `audit: GeoDataFrame` (indexed by id), `role: "warga" | "admin"`, `admin_name`, and `tab: str`. Methods:
    - `run()`
    - `step(events) -> None`: one frame, used by tests
    - `recheck(id: str) -> None`: rebuilds that one row with `check_point` + `status_of` and updates `self.audit`
    - `set_tab(name)`
    - `counts() -> dict[str, int]`, counting only kategori in KATEGORI_AUDIT ∪ {alkohol}
  - Tab names (exact): `Peta`, `Tabel Pelanggaran`, `Lokasi yang Boleh`, `Laporkan Reklame`. Admin adds `Kelola`, `Verifikasi`, `Perlu Cek`.
  - Loading screen: it runs `build_cache` in a `threading.Thread`, draws the progress bar with the latest `(pct, msg)`, and on `OSMDownloadError` shows "Butuh internet untuk run pertama" (or "Gagal mengunduh lapisan: {layer}") with an **Coba lagi** button.
  - Guide card: three steps, shown while `settings["panduan_dilihat"]` is false. **Lewati** / **Mengerti** set it to true. Copy: "1. Titik merah berarti reklame melanggar aturan. Klik untuk melihat alasannya." / "2. Lingkaran biru muda adalah radius 500 m dari sekolah." / "3. Cari jalan Anda di kotak pencarian, atau laporkan reklame yang belum tercatat."
  - Detail panel: the badge, `isi_reklame`, `id`, `alamat`, media, the tayang range, `alasan_text`, "Lokasi perkiraan: alamat tanpa nomor rumah" when `alamat_tidak_lengkap`, and a list when a cluster is clicked. Admin-only buttons ("Ubah data", "Geser lokasi") are hidden for warga.

- [ ] **Step 1: Write the failing tests:** `test_search_blank_returns_empty`, `test_search_prefix_first`, `test_search_strips_house_number`, and in the smoke test `test_app_starts_on_peta_as_warga_without_login` (tiny cache fixture, `headless=True`), `test_first_run_without_users_shows_setup_admin`, `test_guide_card_shown_once`, `test_loading_shows_retry_on_osm_error` (fake fetcher raises), `test_recheck_updates_status_after_move`.
- [ ] **Step 2: Run** `pytest tests/test_search.py tests/test_app_smoke.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.** The layout follows the A mockup: 56 px navy top bar (title, tabs, search box with dropdown results, Masuk Admin), 248 px left panel (summary tiles, layer checkboxes, legend), fluid map, and a 320 px right detail panel. The frame cap is 60 fps.
- [ ] **Step 4: Run** the same tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat: app shell with loading, guide card, map tab and search`.

### Task 7: Tabel Pelanggaran and CSV export

**Files:**
- Create: `ui/screens/tabel.py`, `export.py`
- Test: `tests/test_export.py`, plus smoke test additions

**Interfaces:**
- Consumes: `App.audit`, `Table`, `gis.RULE_LABELS`
- Produces:
  - `export.pelanggaran_csv(audit: GeoDataFrame, out_dir: Path, today: date) -> Path`. It writes `pelanggaran_YYYYMMDD.csv` (UTF-8 with BOM, for Excel) with columns `id, isi_reklame, kategori_materi, alamat, pasal, jarak_sekolah_m, sekolah_terdekat, lat, lon`, and only the rows with status `Melanggar`.
  - The table filters are kategori (dropdown), pasal (dropdown: Semua / 449 (1) d / 449 (1) c / Perda 5/2019) and a text search on alamat. Clicking a row → `App.set_tab("Peta")` + `vp.fly_to` + select.

- [ ] **Step 1: Write the failing tests:** `test_csv_only_melanggar_rows`, `test_csv_has_bom_and_columns`, smoke `test_table_row_click_flies_to_map`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** them. Expected: PASS.
- [ ] **Step 5: Commit** `feat: violation table with CSV export`.

### Task 8: Lokasi yang Boleh and Laporkan Reklame wizard

**Files:**
- Create: `ui/screens/lokasi_boleh.py`, `ui/screens/lapor.py`
- Test: `tests/test_lapor.py`, plus smoke additions

**Interfaces:**
- Consumes: `Zones.area_boleh`, `check_point`, `normalize_kategori`, `Store.add_laporan`
- Produces:
  - Lokasi yang Boleh: the overlay `{"area_boleh"}` in green-teal at 25% alpha, only Patuh rokok/vape markers, and a side note: "Area ini memenuhi syarat jarak PP 28/2024 untuk iklan rokok. Reklame minuman beralkohol dilarang di seluruh Surabaya (Perda 5/2019), jadi tidak ada lokasi yang boleh. Pemasang tetap wajib mengurus izin Pemkot."
  - `class LaporWizard(app)` with `.step: 1 | 2 | 3`, `.pin: (x, y) | None`, `.isi`, `.kategori`, `.nama`, `.next() -> str | None` (returns an error message or None), and `.kirim() -> str` (report id). Error copy: "Klik peta untuk menandai lokasi reklame." / "Isi teks atau merek pada reklame." Step 3 shows the `alasan_text` of `check_point` or "Tidak ditemukan dugaan pelanggaran." After Kirim it shows the toast "Laporan terkirim. Menunggu verifikasi admin." and resets to step 1.

- [ ] **Step 1: Write the failing tests:** `test_lapor_requires_pin_and_isi`, `test_lapor_step3_shows_violation_for_pin_near_school`, `test_lapor_kirim_saves_menunggu_with_hasil_cek`, `test_kategori_alkohol_has_no_allowed_area_note` (smoke: the tab shows the note text).
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** them. Expected: PASS.
- [ ] **Step 5: Commit** `feat: allowed-area view and 3-step report wizard`.

### Task 9: Admin login, Kelola, Verifikasi, Perlu Cek

**Files:**
- Create: `ui/screens/login.py`, `ui/screens/kelola.py`, `ui/screens/verifikasi.py`, `ui/screens/perlu_cek.py`
- Test: `tests/test_admin_flow.py`

**Interfaces:**
- Consumes: `Store` (users, reklame, laporan), `LoginGuard`, `App.recheck`, `MapView` drag events
- Produces:
  - Login modal: on success `App.role = "admin"`, `App.admin_name = username`, the admin tabs appear, and the top bar shows "Admin · {name}" + **Keluar**. Wrong password shows "Username atau password salah." Locked shows "Terlalu banyak percobaan. Coba lagi dalam {n} detik."
  - Kelola: the modes "Tambah" (click the map → form: isi_reklame, kategori dropdown, media, tayang_mulai, tayang_selesai as YYYY-MM-DD with validation), "Ubah" (the form prefilled from the selection), "Geser" (drag the pin; a `drag_end` → `update_reklame` with the new lat/lon converted back to EPSG:4326) and "Hapus" (a confirm modal). Each one → `App.recheck(id)`.
  - Verifikasi: a list of `menunggu` reports with their hasil_cek. **Terima** (optionally after dragging the pin) → `terima_laporan` → `recheck(new_id)`. **Tolak** opens a modal with a required alasan.
  - Perlu Cek: the rows with `perlu_cek_manual` and not `kategori_dikonfirmasi`, showing the reason text from the data. Choosing a kategori → `update_reklame(id, {"kategori_materi": k, "kategori_dikonfirmasi": True})` → `recheck`.

- [ ] **Step 1: Write the failing tests:** `test_admin_tabs_hidden_for_warga`, `test_login_success_shows_admin_tabs`, `test_login_lockout_message`, `test_add_reklame_near_school_becomes_melanggar`, `test_move_pin_out_of_zone_becomes_patuh`, `test_terima_report_adds_marker`, `test_tolak_without_alasan_blocked`, `test_perlu_cek_confirm_clears_flag`, `test_logout_returns_to_warga`.
- [ ] **Step 2: Run** `pytest tests/test_admin_flow.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `pytest tests/test_admin_flow.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `feat: admin login, manage, verify and review screens`.

### Task 10: Full-run check and README

**Files:**
- Modify: `README.md` (install, `python data_prep.py` on first run with internet, `python app.py`, how to create the first admin, folder layout, the rule table from the spec)
- Test: `tests/test_app_smoke.py` (add `test_every_tab_opens` for warga and admin)

- [ ] **Step 1: Add** `test_every_tab_opens`, which loops through every tab name and runs 3 `step([])` frames each, with no exception.
- [ ] **Step 2: Run** `pytest -v`. Expected: all PASS.
- [ ] **Step 3: Run** `python gis.py` and `SDL_VIDEODRIVER=dummy python -c "from app import App; ..."` against the real reklame file + tiny OSM fixture. Expected: a printed audit summary that includes 22,483 loaded, 1,930 Rokok, 67 Rokok elektronik and 24 Perlu cek.
- [ ] **Step 4: Update README** and commit `docs: README with setup and run steps`.
