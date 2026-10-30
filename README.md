# Audit Spasial Reklame Rokok dan Alkohol Dekat Sekolah Surabaya

Aplikasi desktop (Python + Pygame) yang memeriksa setiap reklame luar ruang di Surabaya terhadap aturan iklan rokok,
rokok elektronik, dan minuman beralkohol, lalu menandai yang melanggar.

Kelompok DAD (Angga Dhammika Jaya, Muhammad Althaf Hilmi, Dave Tristian Nurcahyo), Computer Graphics, Informatika
Universitas Ciputra 2026/2027.

## Aturan yang diperiksa

| Kategori materi | Aturan | Cara cek |
|---|---|---|
| Rokok, Rokok elektronik | PP 28/2024 Ps. 449 (1) d: dilarang dalam radius 500 m dari satuan pendidikan | Titik reklame di dalam buffer 500 m sekolah (TK/PAUD, SD/MI, SMP/MTs, SMA/SMK/MA) |
| Rokok, Rokok elektronik | PP 28/2024 Ps. 449 (1) c: dilarang di jalan utama/protokol | Titik di dalam koridor 25 m jalan utama (OSM `trunk`/`primary`) |
| Minuman beralkohol | Perda Surabaya 5/2019 Ps. 23: dilarang di seluruh kota | Selalu melanggar |
| Umum | – | Tidak diaudit |

Status: **Melanggar**, **Patuh**, **Tidak diaudit**, **Perlu cek** (nama ambigu, menunggu admin), **Tayang berakhir**
(masa tayang sudah lewat, tidak dihitung sebagai pelanggaran).

## Instalasi

Butuh Python 3.11 atau lebih baru.

```bash
pip install -r requirements.txt
```

## Menjalankan

1. **Run pertama (butuh internet).** Siapkan cache data OpenStreetMap. Ini memakan beberapa menit:

   ```bash
   python data_prep.py
   ```

   Langkah ini juga otomatis dijalankan oleh aplikasi (dengan progress bar) bila cache belum ada.
   Untuk mengunduh ulang data OSM: `python data_prep.py --refresh-osm`.

2. **Buka aplikasi:**

   ```bash
   python app.py
   ```

3. Saat pertama kali dibuka, aplikasi meminta Anda **membuat akun admin pertama**. Setelah itu aplikasi langsung
   terbuka di peta untuk warga, tanpa login. Admin masuk lewat tombol **Masuk Admin** di kanan atas.

## Cara pakai

- **Peta**: titik merah melanggar, biru patuh, kuning perlu cek. Klik titik untuk melihat alasannya: garis putus-putus
  di peta mengukur jarak ke sekolah dan jalan utama terdekat, dan panel kanan membandingkan jarak itu dengan batas
  aturan (500 m dan 25 m). Lingkaran bernomor adalah kumpulan reklame; bagian merah pada cincinnya menunjukkan porsi
  yang melanggar. Klik untuk melihat daftarnya. Seret untuk menggeser peta, scroll atau tombol +/− untuk zoom.
  Cari jalan di kotak kiri atas.
- **Tabel Pelanggaran**: filter per kategori, pasal, atau alamat. Klik baris untuk melihatnya di peta.
  **Ekspor CSV** menyimpan file ke folder `exports/`.
- **Lokasi yang Boleh**: area hijau yang memenuhi syarat jarak untuk iklan rokok.
- **Laporkan Reklame**: 1) klik lokasi di peta, 2) isi teks dan kategori, 3) lihat hasil cek lalu kirim.
- **Admin**: **Kelola** (tambah, ubah, geser, hapus), **Verifikasi** (terima atau tolak laporan warga),
  **Perlu Cek** (tetapkan kategori untuk 24 reklame yang namanya ambigu). Setiap perubahan langsung dihitung ulang.

## Struktur folder

```
app.py            aplikasi Pygame (jalankan ini)
data_prep.py      unduh OSM dan bangun cache (buffer + dissolve)
gis.py            aturan spasial: Layer 1 Fasilitas, Layer 2 Reklame, Layer 3 Jalan
storage.py        penyimpanan JSON yang aman (tulis .tmp lalu ganti, cadangan .bak)
search.py         pencarian nama jalan
export.py         ekspor CSV pelanggaran
ui/               peta, komponen, dan layar tiap tab
data/             data Bapenda asli (tidak pernah diubah) dan data kerja aplikasi
cache/            hasil OSM, zona, dan tile peta (dibuat otomatis)
exports/          hasil ekspor CSV
tests/            pengujian pytest
```

Data kerja di `data/` (`reklame_db.json`, `laporan.json`, `users.json`, `settings.json`) dibuat otomatis dan tidak
masuk git. Hapus `reklame_db.json` untuk mulai lagi dari data Bapenda asli.

## Pengujian

```bash
pytest
```

Pengujian memakai lapisan buatan kecil (seperti koordinat buatan di notebook week 5), jadi tidak butuh internet.

## Catatan

- Data reklame: Sistem Informasi Reklame Bapenda Kota Surabaya (akses publik), diambil 26 Oktober 2026,
  sudah di-geocode. 1.441 alamat tanpa nomor rumah ditandai "lokasi perkiraan".
- Batas 25 m koridor jalan utama adalah asumsi kelompok karena PP 28/2024 tidak menyebut jarak.
- Lokasi yang boleh hanya memenuhi syarat jarak PP 28/2024. Pemasang tetap wajib mengurus izin Pemkot.
- Font: Public Sans dan Barlow Condensed (SIL Open Font License).
