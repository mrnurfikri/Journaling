# Jurnal otomatis (GitHub Pages + GitHub Actions)

Setiap Minggu malam (Senin 00:00 WIB), GitHub mengambil dokumen jurnal dari Google Docs,
mengurainya per hari, mengenkripsinya dengan kata sandi, lalu memperbarui `index.html`.
Isi jurnal tidak pernah tersimpan sebagai teks biasa di repo.

## File di repo
- `template.html` : tampilan halaman (tanpa data)
- `scripts/build.py` : pengambil + pengurai + enkripsi
- `.github/workflows/sync.yml` : jadwal mingguan
- `requirements.txt`
- `index.html` dan `.last-hash` : dibuat otomatis oleh Actions (jangan diedit)

## A. Siapkan akses Google (sekali saja)
1. Buka https://console.cloud.google.com, buat proyek baru (nama bebas).
2. *APIs & Services -> Library*, cari **Google Drive API**, klik **Enable**.
3. *IAM & Admin -> Service Accounts -> Create service account* (nama bebas, mis. `jurnal-reader`), lewati langkah peran.
4. Buka akun layanan itu, tab **Keys -> Add key -> Create new key -> JSON**. File JSON akan terunduh. Simpan, jangan dibagikan, jangan diunggah ke repo.
5. Salin email akun layanan (berakhiran `.iam.gserviceaccount.com`).
6. Di setiap dokumen jurnal: **Bagikan** -> tambahkan email itu sebagai **Pelihat (Viewer)**. Tidak perlu mengubah ke "siapa saja yang memiliki link".

## B. Siapkan GitHub
1. Buat repo baru dan unggah semua file di atas (termasuk folder `.github`).
   Di web GitHub, untuk membuat file berfolder: *Add file -> Create new file*, lalu ketik nama seperti `.github/workflows/sync.yml`.
2. *Settings -> Secrets and variables -> Actions -> New repository secret*, buat tiga secret:
   - `GOOGLE_SA_JSON` : tempel seluruh isi file JSON dari langkah A4
   - `JOURNAL_DOCS` : `2025=<ID dokumen 2025>,2026=<ID dokumen 2026>`
     (ID = bagian di link antara `/d/` dan `/edit`)
   - `JOURNAL_PASSWORD` : kata sandi untuk membuka halaman
3. *Settings -> Actions -> General -> Workflow permissions*: pilih **Read and write permissions**.
4. *Settings -> Pages*: Deploy from a branch, `main`, folder `/ (root)`.
5. Tab **Actions -> Sinkron jurnal -> Run workflow** untuk menjalankan pertama kali. Cek lognya: harus muncul jumlah entri per tahun dan "index.html diperbarui".

## Mengganti kata sandi
Ubah secret `JOURNAL_PASSWORD`, lalu jalankan workflow secara manual dengan opsi **force** dicentang.

## Jika gagal
- "HTTP 403/404": Drive API belum aktif, dokumen belum dibagikan ke email akun layanan, atau ID salah.
- "Hanya N entri": format hasil ekspor Google berbeda dari yang diharapkan. Halaman lama sengaja tidak ditimpa. Kirim pesan galat (bukan isi jurnal) ke Claude untuk diperbaiki.
- Jadwal berhenti: GitHub bisa menonaktifkan jadwal otomatis pada repo yang lama tidak aktif. Aktifkan lagi di tab Actions.
