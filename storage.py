"""Penyimpanan data aplikasi (folder data/).

Semua penulisan file JSON lewat modul ini, supaya aman dari crash:
tulis ke file .tmp dulu, simpan versi lama sebagai .bak, lalu ganti.
"""

import hashlib
import hmac
import json
import os
import secrets
import shutil
from datetime import datetime
from pathlib import Path

ORIGINAL_NAME = "reklame_surabaya_outdoor_semua.json"
PBKDF2_ROUNDS = 200_000
MIN_PASSWORD = 8


def now_text():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------
# File JSON yang aman
# ---------------------------------------------------------------

def write_json_atomic(path, data):
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    bak = path.with_name(path.name + ".bak")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if path.exists():
        shutil.copy2(path, bak)
    os.replace(tmp, path)


def read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        bak = path.with_name(path.name + ".bak")
        print(f"Peringatan: {path.name} rusak, memakai cadangan {bak.name}")
        if bak.exists():
            return json.loads(bak.read_text(encoding="utf-8"))
        return default


# ---------------------------------------------------------------
# Password admin
# ---------------------------------------------------------------

def hash_password(pw, salt=None):
    if salt is None:
        salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt.hex(), h.hex()


def verify_password(pw, salt_hex, hash_hex):
    _, h = hash_password(pw, bytes.fromhex(salt_hex))
    return hmac.compare_digest(h, hash_hex)


class LoginGuard:
    """Kunci login sementara setelah beberapa kali salah password."""

    def __init__(self, max_fail=5, lock_s=30):
        self.max_fail = max_fail
        self.lock_s = lock_s
        self.fails = 0
        self.locked_until = 0.0

    def record(self, ok, now):
        if ok:
            self.fails = 0
            return
        self.fails += 1
        if self.fails >= self.max_fail:
            self.locked_until = now + self.lock_s
            self.fails = 0

    def locked(self, now):
        return now < self.locked_until

    def seconds_left(self, now):
        return max(0, int(self.locked_until - now + 0.999))


# ---------------------------------------------------------------
# Store: reklame, laporan, user, pengaturan
# ---------------------------------------------------------------

class Store:
    def __init__(self, data_dir):
        self.dir = Path(data_dir)
        self.p_original = self.dir / ORIGINAL_NAME
        self.p_reklame = self.dir / "reklame_db.json"
        self.p_laporan = self.dir / "laporan.json"
        self.p_users = self.dir / "users.json"
        self.p_settings = self.dir / "settings.json"
        self._reklame = None

    # --- user admin ---
    def _users(self):
        return read_json(self.p_users, default=[])

    def users_exist(self):
        return len(self._users()) > 0

    def create_user(self, username, pw):
        username = username.strip()
        users = self._users()
        if not username:
            raise ValueError("Username wajib diisi.")
        if any(u["username"] == username for u in users):
            raise ValueError("Username sudah dipakai.")
        if len(pw) < MIN_PASSWORD:
            raise ValueError(f"Password minimal {MIN_PASSWORD} karakter.")
        salt, h = hash_password(pw)
        users.append({"username": username, "salt": salt, "hash": h, "dibuat_pada": now_text()})
        write_json_atomic(self.p_users, users)

    def check_login(self, username, pw):
        for u in self._users():
            if u["username"] == username.strip():
                return verify_password(pw, u["salt"], u["hash"])
        return False

    # --- reklame ---
    def reklame(self):
        if self._reklame is None:
            rows = read_json(self.p_reklame, default=None)
            if rows is None:
                original = json.loads(self.p_original.read_text(encoding="utf-8"))["reklame"]
                rows = [self._with_extra_fields(r) for r in original]
                write_json_atomic(self.p_reklame, rows)
            self._reklame = rows
        return self._reklame

    @staticmethod
    def _with_extra_fields(r, sumber="Bapenda"):
        row = dict(r)
        row.setdefault("sumber", sumber)
        row.setdefault("status_verifikasi", "terverifikasi")
        row.setdefault("dihapus", False)
        row.setdefault("diubah_oleh", None)
        row.setdefault("diubah_pada", None)
        row.setdefault("kategori_dikonfirmasi", False)
        row.setdefault("perlu_cek_manual", None)
        row.setdefault("alamat_tidak_lengkap", False)
        return row

    def _save_reklame(self):
        write_json_atomic(self.p_reklame, self._reklame)

    def get_reklame(self, id):
        for r in self.reklame():
            if r["id"] == id:
                return r
        raise KeyError(id)

    def _next_id(self, rows, prefix):
        nums = [int(r["id"].split("-", 1)[1]) for r in rows
                if r["id"].startswith(prefix + "-") and r["id"].split("-", 1)[1].isdigit()]
        return f"{prefix}-{max(nums, default=0) + 1}"

    def add_reklame(self, row, oleh, sumber="admin"):
        rows = self.reklame()
        prefix = "L" if sumber == "laporan warga" else "A"
        new = self._with_extra_fields(row, sumber=sumber)
        new["id"] = self._next_id(rows, prefix)
        new["sumber"] = sumber
        new["diubah_oleh"] = oleh
        new["diubah_pada"] = now_text()
        rows.append(new)
        self._save_reklame()
        return new["id"]

    def update_reklame(self, id, changes, oleh):
        r = self.get_reklame(id)
        r.update(changes)
        r["diubah_oleh"] = oleh
        r["diubah_pada"] = now_text()
        self._save_reklame()
        return r

    def delete_reklame(self, id, oleh):
        self.update_reklame(id, {"dihapus": True}, oleh)

    # --- laporan warga ---
    def laporan(self):
        return read_json(self.p_laporan, default=[])

    def _get_laporan(self, rows, id):
        for r in rows:
            if r["id"] == id:
                return r
        raise KeyError(id)

    def add_laporan(self, lat, lon, isi_reklame, kategori_materi, hasil_cek, nama_pelapor):
        rows = self.laporan()
        lap = {
            "id": self._next_id(rows, "R"), "lat": lat, "lon": lon,
            "isi_reklame": isi_reklame, "kategori_materi": kategori_materi,
            "nama_pelapor": nama_pelapor or None, "waktu": now_text(),
            "hasil_cek": list(hasil_cek), "status": "menunggu",
            "alasan_tolak": None, "diproses_oleh": None,
        }
        rows.append(lap)
        write_json_atomic(self.p_laporan, rows)
        return lap["id"]

    def terima_laporan(self, id, oleh, lat=None, lon=None):
        rows = self.laporan()
        lap = self._get_laporan(rows, id)
        new_id = self.add_reklame({
            "alamat": "(laporan warga)", "isi_reklame": lap["isi_reklame"],
            "kategori_materi": lap["kategori_materi"], "media": "-",
            "tayang_mulai": None, "tayang_selesai": None,
            "latitude": lap["lat"] if lat is None else lat,
            "longitude": lap["lon"] if lon is None else lon,
        }, oleh=oleh, sumber="laporan warga")
        lap.update(status="diterima", diproses_oleh=oleh)
        write_json_atomic(self.p_laporan, rows)
        return new_id

    def tolak_laporan(self, id, oleh, alasan):
        if not alasan or not alasan.strip():
            raise ValueError("Alasan penolakan wajib diisi.")
        rows = self.laporan()
        lap = self._get_laporan(rows, id)
        lap.update(status="ditolak", alasan_tolak=alasan.strip(), diproses_oleh=oleh)
        write_json_atomic(self.p_laporan, rows)

    # --- pengaturan tampilan ---
    def settings(self):
        return read_json(self.p_settings, default={})

    def save_settings(self, d):
        write_json_atomic(self.p_settings, d)


if __name__ == "__main__":
    s = Store(Path(__file__).parent / "data")
    rows = s.reklame()
    print("Jumlah reklame      :", len(rows))
    print("Laporan warga       :", len(s.laporan()))
    print("Akun admin tersedia :", s.users_exist())
