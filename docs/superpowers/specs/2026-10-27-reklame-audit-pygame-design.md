# Audit Spasial Reklame Rokok dan Alkohol: Pygame App Design

Date: 2026-10-27
Team: Kelompok DAD (Angga Dhammika Jaya, Muhammad Althaf Hilmi, Dave Tristian Nurcahyo), Computer Graphics AFL2
Source proposal: "Audit Spasial Reklame Rokok dan Alkohol Dekat Sekolah Surabaya"
Visual mockups: https://claude.ai/artifact/6zyQZxfJA9gheCNo4vBUKD (direction A, "Balai Kota")

## 1. Goal and audience

A desktop app written in Python and Pygame. It checks every outdoor billboard (reklame) in Surabaya against the advertising rules for cigarettes, e-cigarettes and alcohol, and flags the ones that break them.

The audience is the general public (the main users), plus journalists and the course lecturer at the presentation. Ease of reading and navigation takes priority over visual effects.

Success means:
- A first-time user can open the app, find their street, and understand why a billboard is flagged, without instructions from the team.
- The audit covers all of Surabaya using real data: the Bapenda list plus OpenStreetMap.
- Admin edits and accepted reports change the audit result right away.

## 2. Rules (legal basis)

| Kategori materi | Rule | Check |
|---|---|---|
| Rokok, Rokok elektronik | PP 28/2024 Ps. 449 (1) d: no ads within 500 m of a satuan pendidikan | Point inside the dissolved 500 m buffer of the schools |
| Rokok, Rokok elektronik | PP 28/2024 Ps. 449 (1) c: no ads on jalan utama / protokol | Point intersects the dissolved 25 m buffer of jalan utama (team's working definition: OSM `trunk`/`primary` and their `_link` roads) |
| Minuman beralkohol | Perda Surabaya 5/2019 Ps. 23: banned citywide | Always a violation |
| Umum | none | Not audited |

Education facilities are TK/PAUD, SD/MI, SMP/MTs and SMA/SMK/MA. Universities are excluded, as in the proposal.

Billboard status values:
- `Melanggar`: one or more rules broken. The list of broken rules is kept.
- `Patuh`: an audited category with no rule broken.
- `Tidak diaudit`: kategori Umum.
- `Perlu cek`: the row has `perlu_cek_manual` set and no admin has confirmed its category yet. It is shown separately and not counted as Melanggar or Patuh.
- `Tayang berakhir`: `tayang_selesai` is before today. It is greyed out on the map and excluded from the violation counts. The rule result is still computed and shown.

Rows with `alamat_tidak_lengkap = true` (1,441 rows) show a "lokasi perkiraan" note, because their coordinates sit on the road segment and are not exact.

## 3. Screens and flow

1. **Loading screen.** The app checks `cache/`. If the cache is missing or stale, it runs the data prep with a progress bar. If there is no internet on the first run, it shows "Butuh internet untuk run pertama" and a retry button.
2. **First-admin setup** (only when `data/users.json` is missing). The app asks for a username and password for the first admin.
3. **Main window, 1280×800, opened straight away without login** in public (warga) mode. A one-time guide card explains the map in 3 steps and can be skipped. The skip is remembered in `data/settings.json`.
4. **Top bar:** app name, the tabs, a search box (street or kelurahan, built from the `alamat` values and OSM road names), and the **Masuk Admin** button.
5. **Public tabs:**
   - **Peta:** a pan/zoom map. Left panel: summary counts, layer toggles, legend. Right panel: details of the selected billboard, its status badge, its reasons ("312 m dari SDN …", the distance to jalan utama), and the "lokasi perkiraan" note when it applies. Billboards that share a coordinate are grouped into one numbered cluster marker, and clicking it lists them.
   - **Tabel Pelanggaran:** a paginated table that can be sorted and filtered by category, rule and kecamatan/kelurahan text. Clicking a row jumps to it on the map. An "Ekspor CSV" button writes to `exports/`.
   - **Lokasi yang Boleh:** draws `area_boleh` and the Patuh cigarette billboards inside it. A note explains that alcohol billboards have no allowed area.
   - **Laporkan Reklame:** a 3-step wizard with a step indicator. (1) Click the map to place the pin. (2) Enter the billboard text, the category, and optionally a name. (3) See the instant check result, then press Kirim. The report is saved as `menunggu`.
6. **Admin login.** A modal asks for the username and password. A successful login adds three tabs and shows the admin name in the top bar, with a Keluar button.
   - **Kelola:** add a billboard (click the map, then fill a form), edit its attributes, drag its pin to a new spot, or soft-delete it.
   - **Verifikasi:** a list of pending reports. **Terima** turns the report into a billboard with `sumber = laporan warga`, and the pin can be adjusted first. **Tolak** requires a reason.
   - **Perlu Cek:** the 24 ambiguous rows. The admin sets the category, and that clears the flag.
   - Every change re-checks only that point and updates the map, table and counts immediately.

Visual direction A: light civic dashboard. Navy `#173B57` top bar, white panels, a cream map background. Violations are red `#C8452F` with a "!" icon. Patuh is blue `#1F4FA3` with a check icon, chosen to be safe for red-green colour blindness. Umum is grey. School zones are teal dashed circles, and the main-road corridor is a translucent teal band. All UI text is in Bahasa Indonesia. Click targets are at least 44 px. The font is Public Sans, bundled as a TTF, with a fallback to Pygame's default font.

## 4. Architecture

```
reklame-audit/
  data_prep.py      # build cache: load reklame, download OSM, project, buffer, dissolve
  gis.py            # rules: load layers, audit_all(), check_point(), nearest info, area_boleh
  storage.py        # JSON read/write (atomic + .bak), users (pbkdf2), laporan, reklame_db
  app.py            # Pygame entry point, main loop, screen switching
  ui/               # widgets.py (button, input, table, modal), map_view.py (tiles, markers), screens/*.py
  assets/fonts/     # Public Sans TTF
  data/             # reklame_surabaya_outdoor_semua.json (original, read-only), reklame_db.json, laporan.json, users.json, settings.json
  cache/            # layers.gpkg, manifest.json, tiles/z/x_y.png
  exports/          # CSV exports
  tests/            # pytest
```

Each module has one job:
- `data_prep.py` is the only module that touches the network.
- `gis.py` takes GeoDataFrames and returns results. It has no Pygame and no file writes.
- `storage.py` is the only module that writes to `data/`.
- `ui/` only reads results through `gis.py` and saves through `storage.py`.

Code style follows Althaf's week 5 notebook:
- GeoPandas and Shapely objects (`Point`, `LineString`, `Polygon`) with `within`, `intersects`, `distance` and `buffer`.
- `# Layer 1 / 2 / 3` comments.
- Small, plain functions.
- `data_prep.py` and `gis.py` print readable summaries when run directly.

## 5. Data and cache

Inputs:
- Layer 2 (Reklame): `data/reklame_surabaya_outdoor_semua.json`. It has 22,483 rows, already geocoded (lat/lon in EPSG:4326), and is loaded as GeoDataFrame points.
- Layer 1 (Fasilitas): `osmnx.features_from_place("Surabaya, Indonesia", tags={"amenity": ["school", "kindergarten"]})`. Points and polygons are both kept. `jenis` is set from the `isced:level` tag or name prefixes (TK/PAUD/RA, SD/MI, SMP/MTs, SMA/SMK/MA). Rows with an unknown type are kept as `sekolah (lainnya)`, and universities (`amenity=university/college`) are not fetched.
- Layer 3 (Jalan): `osmnx.graph_from_place(..., network_type="drive")` converted to edges. `tipe_jalan` is set from `highway`: motorway becomes tol, trunk/primary(+link) become jalan utama, secondary/tertiary become penghubung, and everything else becomes kecil.
- Boundary: `osmnx.geocode_to_gdf("Kota Surabaya")`.

Everything is projected to EPSG:32749 (UTM 49S) before buffering or measuring distance.

Cache (`cache/`):
- `layers.gpkg` holds these layers: `fasilitas`, `jalan`, `batas`, `zona_500` (dissolved), `koridor_25` (dissolved), `area_boleh`.
- `manifest.json` stores the reklame file mtime and size, the OSM download date, `radius_m = 500`, `koridor_m = 25` and a cache version. A layer is rebuilt only when one of its inputs changed. OSM is re-downloaded only when it is missing or when `data_prep.py --refresh-osm` is run.
- `tiles/{z}/{x}_{y}.png` are 256 px base-map tiles (water, roads by type, school polygons) drawn with Pygame the first time they are needed and saved to disk. Zoom levels run from 11 to 17. Markers and zones are drawn live on top.
- In memory, the projected layers and prepared geometries (`shapely.prepared.prep`) of `zona_500` and `koridor_25` are kept for instant single-point checks.

## 6. Saved data (`data/`)

- `reklame_db.json` is created from the original file on first run. Each row gets the original fields plus `sumber` (`Bapenda` | `laporan warga` | `admin`), `status_verifikasi`, `dihapus` (bool), `diubah_oleh` and `diubah_pada`. The original file is never modified.
- `laporan.json` holds: id, lat, lon, isi_reklame, kategori_materi, nama_pelapor (optional), waktu, hasil_cek (the rules broken at submission time), status (`menunggu` | `diterima` | `ditolak`), alasan_tolak, diproses_oleh.
- `users.json` holds: username, salt and `pbkdf2_hmac('sha256', …, 200_000)` hash, dibuat_pada.
- `settings.json` holds UI preferences, such as whether the guide card was seen.
- Every write goes to `file.tmp`, then `os.replace` swaps it in. The previous version is kept as `file.bak`. On load, if the JSON is invalid, the app restores from `.bak` and logs a warning.

## 7. Error handling

- No network on the first run: a clear message plus a retry button. Later runs work offline from the cache.
- OSM download partly fails: the layers that did download are kept, and the screen names the layer that failed.
- A bad reklame row (missing coordinates): it is skipped, with a printed count.
- Wrong admin password: an inline message. After 5 failures in a row, there is a 30-second wait.
- An empty search result: "Jalan tidak ditemukan".

## 8. Testing

- `tests/test_gis.py` uses tiny synthetic layers with metre coordinates, in the style of the notebook's artificial geometry. It covers: a point inside 500 m, a point outside, a point exactly on the boundary (counted as violating via `intersects`), the road corridor, both rules at once, alcohol anywhere, Umum not audited, expired billboards, and `area_boleh` excluding zones and the corridor.
- `tests/test_storage.py`: atomic write, `.bak` recovery, password hash and verify, and the report accept/reject transitions.
- `tests/test_app_smoke.py`: runs with `SDL_VIDEODRIVER=dummy`, starts the app on a tiny fixture cache, opens every tab, and runs the report wizard end to end.
- The OSM download is not tested in CI, because the build sandbox has no OSM access. It is run manually on a team laptop.

## 9. Out of scope

Playgrounds, health facilities and places of worship (future work in the proposal), merging duplicate reports, permit and zoning rules, multi-user network sync, and a mobile version.
