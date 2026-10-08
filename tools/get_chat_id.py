"""
get_chat_id.py
==============
Menampilkan chat_id Telegram yang bisa dipakai sebagai tujuan notifikasi.

Bot Telegram tidak bisa mengirim pesan ke siapa pun yang belum menyapanya lebih
dulu, dan chat_id-nya tidak ditampilkan di aplikasi Telegram. Satu-satunya cara
mengetahuinya adalah menanyakan ke API, dan itulah yang dilakukan alat ini.

Dijalankan dari folder repo:

    .venv\\Scripts\\python.exe tools\\get_chat_id.py

Setelah melihat daftarnya, simpan yang dipilih:

    .venv\\Scripts\\python.exe tools\\get_chat_id.py --simpan -1001234567890

Token dibaca dari backend/.env dan TIDAK PERNAH ditampilkan, termasuk saat
terjadi error -- pesan kesalahan dari API sengaja dibersihkan dari token
sebelum dicetak, supaya aman di-screenshot atau dikirim ke anggota tim.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "backend" / ".env"

# Token berbentuk <angka>:<rahasia>. Pola ini dipakai untuk menyensornya dari
# pesan kesalahan sebelum apa pun dicetak ke layar.
POLA_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_\-]{20,}")


def sensor(teks: str) -> str:
    """Ganti token apa pun di dalam teks dengan penanda."""
    return POLA_TOKEN.sub("<TOKEN-DISENSOR>", teks)


def baca_env() -> dict[str, str]:
    """Baca pasangan KEY=VALUE dari backend/.env."""
    if not ENV.exists():
        print(f"[GAGAL] {ENV} tidak ada.")
        print("        Salin templatnya dulu: cp deployment/.env.example backend/.env")
        sys.exit(1)

    hasil: dict[str, str] = {}
    for baris in ENV.read_text(encoding="utf-8-sig").splitlines():
        baris = baris.strip()
        if not baris or baris.startswith("#") or "=" not in baris:
            continue
        kunci, _, nilai = baris.partition("=")
        hasil[kunci.strip()] = nilai.strip().strip('"').strip("'")
    return hasil


def panggil(token: str, metode: str, params: str = "") -> dict:
    """Panggil satu metode Bot API. Error dibersihkan dari token sebelum dicetak."""
    url = f"https://api.telegram.org/bot{token}/{metode}{params}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        badan = e.read().decode("utf-8", "replace")
        return {"ok": False, "error_code": e.code, "description": sensor(badan)}
    except urllib.error.URLError as e:
        return {"ok": False, "error_code": 0, "description": sensor(str(e.reason))}


def diagnosa(token: str) -> None:
    """Cetak keterangan yang menjelaskan kenapa getUpdates bisa kosong.

    Pertanyaan terpentingnya: token ini milik bot yang mana? Kalau tokennya sah
    tapi miliknya bot lain, getUpdates memang akan kosong walau kita sudah
    mengirim banyak pesan ke bot yang kita kira benar.
    """
    print("=" * 60)
    print("DIAGNOSA TELEGRAM")
    print("=" * 60)

    me = panggil(token, "getMe")
    if not me.get("ok"):
        kode = me.get("error_code")
        print(f"[GAGAL] getMe ditolak (HTTP {kode}): {me.get('description', '')[:200]}")
        if kode == 401:
            print("        Token tidak sah. Ambil yang baru lewat BotFather: /token")
        return

    bot = me["result"]
    print(f"Token ini milik bot : @{bot.get('username')}  (id {bot.get('id')})")
    print(f"Nama tampilan       : {bot.get('first_name')}")
    print(f"Boleh masuk grup    : {bot.get('can_join_groups')}")
    print(f"Baca semua pesan grup: {bot.get('can_read_all_group_messages')}"
          "   <- kalau False, privacy mode aktif")
    print()

    wh = panggil(token, "getWebhookInfo")
    if wh.get("ok"):
        info = wh["result"]
        url_wh = info.get("url") or ""
        print(f"Webhook terpasang   : {'YA -> ' + url_wh if url_wh else 'tidak'}")
        print(f"Update tertunda     : {info.get('pending_update_count', 0)}")
        if url_wh:
            print()
            print("  PENYEBAB DITEMUKAN: selama webhook terpasang, Telegram mengirim")
            print("  update ke alamat itu dan getUpdates tidak akan pernah berisi apa pun.")
            print("  Lepaskan dengan membuka alamat ini di browser (ganti <TOKEN>):")
            print("    https://api.telegram.org/bot<TOKEN>/deleteWebhook")
        if info.get("last_error_message"):
            print(f"Error webhook terakhir: {sensor(info['last_error_message'])[:120]}")
    print()

    upd = panggil(token, "getUpdates", "?limit=100")
    if upd.get("ok"):
        hasil = upd.get("result", [])
        print(f"getUpdates          : {len(hasil)} update")
        if hasil:
            print(f"update_id pertama   : {hasil[0].get('update_id')}")
            print(f"update_id terakhir  : {hasil[-1].get('update_id')}")
    else:
        print(f"getUpdates GAGAL    : {upd.get('description', '')[:200]}")

    print("=" * 60)


def ambil_updates(token: str) -> list[dict]:
    """Panggil getUpdates. Pesan error dibersihkan dari token sebelum dicetak."""
    url = f"https://api.telegram.org/bot{token}/getUpdates?limit=100"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        badan = e.read().decode("utf-8", "replace")
        if e.code == 401:
            print("[GAGAL] Token ditolak Telegram (401 Unauthorized).")
            print("        Kemungkinan token lama yang sudah dicabut, atau ada spasi/kutip")
            print("        yang ikut tersalin. Ambil ulang lewat BotFather: /token")
        else:
            print(f"[GAGAL] Telegram menjawab HTTP {e.code}: {sensor(badan)[:300]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"[GAGAL] Tidak bisa menghubungi api.telegram.org: {sensor(str(e.reason))}")
        print("        Telegram butuh koneksi internet. Kalau laptop sedang memakai")
        print("        hotspot tanpa internet, langkah ini memang tidak akan jalan.")
        sys.exit(1)

    if not data.get("ok"):
        print(f"[GAGAL] Telegram menolak permintaan: {sensor(json.dumps(data))[:300]}")
        sys.exit(1)
    return data.get("result", [])


def kumpulkan_chat(updates: list[dict]) -> dict[int, dict]:
    """Kumpulkan chat unik dari semua jenis update."""
    chats: dict[int, dict] = {}
    for u in updates:
        for kunci in ("message", "edited_message", "channel_post", "my_chat_member"):
            obj = u.get(kunci)
            if isinstance(obj, dict) and isinstance(obj.get("chat"), dict):
                c = obj["chat"]
                chats[c["id"]] = c
    return chats


def simpan_chat_id(chat_id: str) -> None:
    """Tulis TELEGRAM_CHAT_ID ke backend/.env tanpa menyentuh baris lain."""
    baris = ENV.read_text(encoding="utf-8-sig").splitlines()
    ketemu = False
    for i, b in enumerate(baris):
        if b.strip().startswith("TELEGRAM_CHAT_ID"):
            baris[i] = f"TELEGRAM_CHAT_ID={chat_id}"
            ketemu = True
            break
    if not ketemu:
        baris.append(f"TELEGRAM_CHAT_ID={chat_id}")
    ENV.write_text("\n".join(baris) + "\n", encoding="utf-8")
    print(f"[OK] TELEGRAM_CHAT_ID={chat_id} disimpan ke backend/.env")
    print("     Jalankan ulang backend supaya nilainya terbaca.")


def main() -> None:
    p = argparse.ArgumentParser(description="Tampilkan chat_id Telegram untuk notifikasi.")
    p.add_argument("--simpan", metavar="CHAT_ID",
                   help="Simpan chat_id pilihan ke backend/.env")
    p.add_argument("--diagnosa", action="store_true",
                   help="Tampilkan bot pemilik token, status webhook, dan jumlah update")
    args = p.parse_args()

    env = baca_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")

    if not token:
        print("[GAGAL] TELEGRAM_BOT_TOKEN belum ada di backend/.env.")
        lain = [k for k in env if "TELE" in k.upper()]
        if lain:
            print(f"        Yang ada di sana: {', '.join(lain)}")
            print("        Namanya harus persis TELEGRAM_BOT_TOKEN agar terbaca backend.")
        sys.exit(1)

    if args.simpan:
        simpan_chat_id(args.simpan)
        return

    if args.diagnosa:
        diagnosa(token)
        return

    updates = ambil_updates(token)
    chats = kumpulkan_chat(updates)

    if not chats:
        print("Tidak ada percakapan yang terlihat oleh bot ini.")
        print()
        print("Penyebab yang paling sering:")
        print("  1. Token ini milik bot LAIN, bukan bot yang kamu kirimi pesan.")
        print("  2. Ada webhook terpasang; selama itu getUpdates selalu kosong.")
        print("  3. Bot belum pernah disapa. Kirim /start ke botnya dulu.")
        print("  4. Di dalam grup, bot hanya melihat pesan yang menyebut namanya.")
        print("     Kirim /start@NamaBot_bot di grup itu, bukan sekadar /start.")
        print("  5. Update Telegram kedaluwarsa setelah 24 jam. Kirim pesan baru.")
        print()
        print("Jalankan ini untuk tahu yang mana:")
        print(r"  .venv\Scripts\python.exe tools\get_chat_id.py --diagnosa")
        sys.exit(1)

    print(f"Ditemukan {len(chats)} percakapan:\n")
    for cid, c in sorted(chats.items(), key=lambda kv: kv[0]):
        jenis = c.get("type", "?")
        nama = c.get("title") or " ".join(
            x for x in (c.get("first_name"), c.get("last_name")) if x
        ) or c.get("username") or "(tanpa nama)"
        catatan = "  <- grup, disarankan" if jenis in ("group", "supergroup") else ""
        print(f"  chat_id = {cid:<16} {jenis:<11} {nama}{catatan}")

    print()
    print("Grup disarankan karena alert yang hanya masuk ke satu HP adalah titik")
    print("kegagalan tunggal. chat_id grup selalu bernilai negatif.")
    print()
    print("Simpan pilihanmu dengan:")
    print(r"  .venv\Scripts\python.exe tools\get_chat_id.py --simpan <chat_id>")


if __name__ == "__main__":
    main()
