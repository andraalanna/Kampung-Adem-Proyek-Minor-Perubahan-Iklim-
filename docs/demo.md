# Panduan demo Kampung Adem

Demo ini berjalan **tanpa perangkat keras**. Semua data sensor adalah **data simulasi**: simulator membuat bacaan suhu dan kelembapan, mengemasnya menjadi payload LoRaWAN v1, lalu mengirimkannya lewat kode ingest yang sama dengan yang akan dipakai sensor sungguhan. Dashboard menampilkan pita "Mode demo" agar tidak ada yang mengira datanya hasil pengukuran nyata.

WhatsApp berjalan dalam **mode simulasi** (`WA_ENABLED=false`): pesan dicatat di log notifikasi dengan status `dry_run`, tidak ada pesan yang benar-benar terkirim. Nomor penerima demo adalah nomor palsu berawalan 0800.

## Yang dibutuhkan

- Docker Desktop (sudah berjalan)
- Node.js 20 atau lebih baru

## Menjalankan

Dari folder utama repositori:

```
docker compose -f infra/docker-compose.dev.yml up --build -d
cd frontend
npm install
npm run dev
```

Buka http://localhost:5173.

Saat pertama dijalankan, sistem otomatis:

1. Menyiapkan database dan menjalankan migrasi.
2. Mengisi data demo: 3 kelurahan fiktif, 10 RW, 13 node sensor simulasi, akun demo, dan penerima WhatsApp palsu.
3. Mengisi riwayat 24 jam terakhir secara cepat (backfill), sehingga grafik dan riwayat peringatan langsung terisi.
4. Setelah itu, worker dan simulator berjalan terus: satu uplink per node tiap 10 menit, status RW dihitung ulang tiap 10 menit.

Langkah 1 sampai 3 memakan waktu sekitar 1 sampai 3 menit. Cek progresnya dengan:

```
docker compose -f infra/docker-compose.dev.yml ps -a
```

Demo siap jika `simulator-backfill` berstatus `Exited (0)` dan `worker` serta `simulator` berstatus `Up`.

## Akun demo

Semua akun memakai kata sandi `adem-demo-2026`. Akun ini hanya untuk demo dan tidak boleh dipakai di server sungguhan.

| Email | Peran | Yang terlihat |
| --- | --- | --- |
| `admin@demo.kampungadem.id` | Administrator | Semua menu, termasuk kelola pengguna dan ambang |
| `kelurahan@demo.kampungadem.id` | Staf kelurahan | Kelurahan Demo Utara: peta, peringatan, sensor, penerima WA, laporan |
| `rw03@demo.kampungadem.id` | Ketua RW | RW 03 Demo Utara saja |
| `kader@demo.kampungadem.id` | Kader posyandu | RW 04 Demo Utara saja |
| `teknis@demo.kampungadem.id` | Tim teknis | Kesehatan sensor, tiket perawatan, laporan |

## Isi data simulasi per RW

| RW | Sensor | Yang ditunjukkan |
| --- | --- | --- |
| RW 01 Demo Utara | 2 | Lingkungan paling sejuk: NORMAL atau WASPADA |
| RW 02 Demo Utara | 2 | WASPADA hampir setiap siang. Node KA-SBY-0004 melaporkan baterai lemah (tiket baterai) |
| RW 03 Demo Utara | 2 | Kampung padat: SIAGA pada siang hari |
| RW 04 Demo Utara | 2 | RW terpanas: mencapai tingkat tertinggi pada siang hari |
| RW 01 Demo Selatan | 2 | Node KA-SBY-0010 terbaca sekitar 7 °C terlalu tinggi (misalnya pelindung sensor terkena matahari langsung). Bacaannya ditandai `suspect`, tidak dipakai untuk status, dan muncul tiket "cek perangkat" |
| RW 02 Demo Selatan | 1 | Hanya satu sensor: tingkat keyakinan "sedang" |
| RW 03 Demo Selatan | 0 | Tidak punya sensor sendiri: nilai diperkirakan dari sensor terdekat (tier B). Ditampilkan sebagai perkiraan, tidak memicu WhatsApp |
| RW 04 Demo Selatan | 2 | Node KA-SBY-0013 sering putus satu jam tiap 4 jam: status terlambat atau offline, dan grafik menunjukkan celah data (tidak diisi nilai buatan) |
| RW 01 dan 02 Demo Pinggir | 0 | Jauh dari sensor mana pun: hanya ada data satelit (LST), status "Tidak ada data" |

Ketiga kelurahan dan semua batas RW adalah fiktif (kotak 400 m di atas peta Surabaya).

Tiket perawatan yang wajar terlihat setelah start bersih: baterai KA-SBY-0004 dan anomali KA-SBY-0010. Tiket offline untuk KA-SBY-0013 bisa muncul (disengaja). Node lain seharusnya tidak punya tiket.

## Alur presentasi yang disarankan

1. **Dashboard** (`/`): ringkasan jumlah RW per status, peringatan aktif, RW terpanas, kesehatan sensor.
2. **Peta panas** (`/peta`): warna per RW berdasarkan indeks panas. RW dengan garis putus-putus adalah perkiraan (tanpa sensor sendiri).
3. **Lapisan satelit**: di halaman peta, tekan "Suhu permukaan (satelit)". Tekankan bahwa ini **suhu permukaan tanah (LST)**, bukan suhu udara, datanya tidak real-time (lihat tanggal citra), dan tidak dipakai untuk peringatan.
4. **Detail RW** (`/rw/4`, RW 04 Demo Utara): grafik 24 jam indeks panas dan suhu udara, riwayat status.
5. **Peringatan** (`/peringatan`): riwayat SIAGA/AWAS dan log pesan WhatsApp (status `dry_run`, atau `held` jika ditahan karena jam tenang, batas harian, atau jeda antarpesan).
6. **Sensor bermasalah** (`/sensor/KA-SBY-0010`): bacaan ditandai QC, alasan "beda jauh dari sensor tetangga", dan tiket otomatis.
7. **Ambang** (`/ambang`): ambang status disimpan di database, bukan di kode, dan bisa disesuaikan setelah ditinjau Dinkes.
8. **Penerima WA** (`/penerima`): nomor disamarkan, ada catatan persetujuan (opt-in) untuk setiap penerima.
9. Masuk sebagai `rw03@` atau `kader@` untuk menunjukkan bahwa tiap peran hanya melihat wilayahnya.

## Memicu SIAGA atau AWAS saat presentasi

Status mengikuti jam: siang hari (sekitar 11.00 sampai 16.00 WIB) beberapa RW mencapai SIAGA, malam hari umumnya NORMAL atau WASPADA. Jika presentasi dilakukan pada pagi atau malam hari, tambahkan suhu ke semua node:

```
docker compose -f infra/docker-compose.dev.yml stop simulator
docker compose -f infra/docker-compose.dev.yml run --rm simulator python -m app.sim live --boost 3
```

`--boost 3` menambah 3 °C ke semua bacaan. Karena SIAGA dan AWAS butuh nilai di atas ambang selama 30 menit, perubahan status baru terlihat sekitar 30 sampai 40 menit kemudian. Jalankan lebih awal sebelum sesi. Hentikan dengan Ctrl+C, lalu kembali ke simulasi normal:

```
docker compose -f infra/docker-compose.dev.yml start simulator
```

Catatan: pukul 21.00 sampai 05.00 WIB adalah jam tenang. Pesan SIAGA pada jam itu dicatat sebagai `held` dan tidak dikirim. Hanya AWAS yang tetap dikirim.

## Menghentikan dan mengulang

```
docker compose -f infra/docker-compose.dev.yml stop        # berhenti, data disimpan
docker compose -f infra/docker-compose.dev.yml start       # lanjut lagi
docker compose -f infra/docker-compose.dev.yml down -v     # hapus semua data, mulai dari awal
```

Jika komputer dimatikan lebih dari beberapa jam, data akan memiliki celah (sensor terlihat "offline"). Untuk demo yang bersih, jalankan `down -v` lalu `up --build -d` lagi.

## Batasan demo

- Data sensor, batas RW, citra satelit, dan nomor penerima semuanya fiktif.
- Nilai pembanding BMKG belum terhubung.
- Laporan bulanan hanya tersedia dalam format CSV.
