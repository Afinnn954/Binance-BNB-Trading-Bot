# 🚀 Enhanced BNB Trading Bot (Telegram)  BNB Dominator 📈

Selamat datang di **BNB Dominator**, bot Telegram canggih yang dirancang untuk memaksimalkan potensi perdagangan Anda di pasar BNB dan pasangan token terkaitnya di Binance. Bot ini menggabungkan analisis pasar cerdas dengan kontrol intuitif melalui Telegram, memungkinkan Anda untuk trading seperti profesional, kapan saja, di mana saja!

![Bot Banner (Illustrative - you can create one)](https://i.imgur.com/placeholder.png)
*(Anda bisa mengganti link di atas dengan gambar banner bot Anda sendiri jika ada)*

---

## ✨ Fitur Unggulan

*   **🤖 Integrasi Telegram Penuh:** Kontrol bot, terima notifikasi real-time, dan kelola perdagangan langsung dari Telegram.
*   **🔗 Integrasi API Binance (Testnet & Produksi):** Terhubung aman ke akun Binance Anda untuk data pasar live dan eksekusi order.
*   **🎯 Mode Perdagangan Strategis:**
    *   🛡️ `Safe`: Risiko minimal, profit stabil.
    *   ⚖️ `Standard`: Keseimbangan optimal antara risiko dan reward.
    *   ⚔️ `Aggressive`: Potensi profit tinggi dengan risiko terkendali.
    *   ⚡ `Scalping`: Perdagangan kilat untuk profit cepat dari pergerakan kecil.
*   **🐋 Deteksi "Whale" Cerdas:**
    *   Pantau transaksi besar yang berpotensi menggerakkan pasar (saat ini disimulasikan dalam `mock_mode`).
    *   Dapatkan notifikasi "Whale Alert" instan.
    *   Opsi trading otomatis: ikuti (`follow_whale`) atau lawan (`counter_whale`) pergerakan whale.
*   **🧠 Pemilihan Pasangan Otomatis (Auto-Pair Selection):**
    *   Bot secara cerdas memilih pasangan BNB paling prospektif berdasarkan volume transaksi dan volatilitas harga.
*   **📈 Manajemen Perdagangan Lanjutan:**
    *   Pembuatan dan pemantauan perdagangan aktif secara otomatis.
    *   Pengaturan Take Profit (TP) dan Stop Loss (SL) dinamis.
    *   Batas waktu maksimum per perdagangan untuk manajemen risiko.
*   **⚙️ Konfigurasi Fleksibel & Mudah:**
    *   Sesuaikan semua parameter bot (TP, SL, jumlah trading, dll.) melalui perintah Telegram.
    *   Kelola API Key Binance Anda dengan aman.
    *   Beralih dengan mudah antara mode **Testnet** (untuk latihan) dan **Produksi** (untuk trading riil).
*   **💰 Mode Real vs. Simulasi:**
    *   Aktifkan perdagangan nyata (`use_real_trading`) saat Anda siap.
    *   Gunakan mode simulasi (`mock_mode`) untuk pengujian strategi tanpa risiko finansial.
*   **🔐 Keamanan Terjamin:** Akses bot eksklusif untuk Admin yang terdaftar.
*   **📊 Informasi Akun & Pasar:**
    *   Cek saldo akun Binance Anda kapan saja.
    *   Uji konektivitas dan otentikasi API Binance.
    *   Lihat pasangan BNB dengan volume tertinggi dan yang sedang tren.
*   **📄 Logging Aktivitas:** Semua tindakan dan error dicatat untuk kemudahan analisis.

---

## 📋 Prasyarat

Sebelum Anda memulai, pastikan Anda memiliki:

1.  **Python 3.8+**: [Unduh Python](https://www.python.org/downloads/)
2.  **`pip`**: Python package installer (biasanya sudah terinstal dengan Python).
3.  **Akun Telegram**: Untuk berinteraksi dengan bot.
4.  **Token Bot Telegram**: Dapatkan dari @BotFather di Telegram.
5.  **Telegram User ID Anda**: Untuk otorisasi admin. Dapatkan dari @userinfobot di Telegram.
6.  **Akun Binance**: [Daftar Binance](https://www.binance.com/)
7.  **API Key & Secret Key Binance**: (Lihat panduan di bawah untuk mendapatkannya).
    *   Sangat disarankan untuk memulai dengan API Key **Testnet** Binance.

---

## 🛠️ Instalasi dan Setup

Ikuti langkah-langkah ini untuk menjalankan BNB Dominator:

1.  **Clone Repositori (atau Unduh Skrip):**
    ```bash
    # Jika ini adalah repositori git
    # git clone <url-repositori-anda>
    # cd <nama-direktori-proyek>

    # Jika hanya file skrip, simpan sebagai misal bnb_trader_bot.py
    ```

2.  **Buat dan Aktifkan Virtual Environment (Sangat Direkomendasikan):**
    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Install Dependensi:**
    Buat file `requirements.txt` dengan konten berikut:
    ```txt
    python-telegram-bot
    requests
    ```
    Kemudian jalankan:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Konfigurasi Awal Bot:**
    Buka file skrip Python (misal, `bnb_trader_bot.py`) dan edit bagian konfigurasi di awal skrip:

    *   **Telegram Bot Token:**
        ```python
        TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN" # Ganti dengan token Anda
        ```
        Cara mendapatkan token:
        1.  Buka Telegram, cari `@BotFather`.
        2.  Ketik `/newbot`.
        3.  Ikuti instruksi untuk memberi nama bot Anda dan username bot.
        4.  BotFather akan memberikan Anda token API. Salin dan tempel di sini.

    *   **Admin User IDs:**
        ```python
        ADMIN_USER_IDS = [YOUR_TELEGRAM_USER_ID] # Ganti dengan User ID Telegram Anda, contoh: [123456789]
        ```
        Cara mendapatkan User ID Anda:
        1.  Buka Telegram, cari `@userinfobot`.
        2.  Kirim pesan apa saja (misal `/start`) ke `@userinfobot`.
        3.  Bot tersebut akan membalas dengan User ID Anda.

    *   **Binance API Key & Secret Key:**
        ```python
        BINANCE_API_KEY = "YOUR_BINANCE_API_KEY" # Ganti dengan API Key Binance Anda
        BINANCE_API_SECRET = "YOUR_BINANCE_API_SECRET" # Ganti dengan Secret Key Binance Anda
        ```
        Lihat panduan di bawah untuk cara mendapatkan API Key Binance.

    *   **Tinjau `CONFIG` Awal Lainnya:**
        Periksa dan sesuaikan parameter lain dalam dictionary `CONFIG` sesuai kebutuhan awal Anda, seperti:
        *   `trading_pair`: Pasangan default, misal `"BNBUSDT"`.
        *   `amount`: Jumlah aset dasar untuk diperdagangkan, misal `0.5` (untuk 0.5 BNB).
        *   `use_testnet`: `True` (disarankan untuk awal) atau `False`.
        *   `use_real_trading`: `False` (disarankan untuk awal).
        *   `mock_mode`: `True` (jika Anda belum ingin menggunakan API Binance sama sekali, atau untuk demo cepat).

5.  **Panduan Mendapatkan API Key Binance:**

    ⚠️ **PENTING:** API Key Anda sangat sensitif. Jangan pernah membagikannya kepada siapa pun!

    *   **Untuk Akun Produksi (Live Trading):**
        1.  Login ke akun Binance Anda.
        2.  Arahkan mouse ke ikon profil Anda (pojok kanan atas) dan pilih **"Manajemen API"** atau **"API Management"**.
        3.  Klik tombol **"Buat API"** atau **"Create API"**.
        4.  Pilih tipe API Key yang dihasilkan sistem (biasanya default). Beri label yang jelas untuk API Key Anda (misalnya, "TelegramBotBNB").
        5.  Selesaikan verifikasi keamanan (2FA: Google Authenticator/SMS/Email).
        6.  Setelah dibuat, Anda akan melihat **API Key** dan **Secret Key**.
            *   **SALIN KEDUA KEY INI SEGERA DAN SIMPAN DI TEMPAT AMAN.** Secret Key hanya akan ditampilkan sekali.
        7.  Klik **"Edit batasan"** atau **"Edit restrictions"** untuk API Key yang baru dibuat.
        8.  Pastikan izin berikut **DICENTANG**:
            *   ✅ `Aktifkan Membaca` / `Enable Reading`
            *   ✅ `Aktifkan Perdagangan Spot & Margin` / `Enable Spot & Margin Trading`
        9.  Pastikan izin berikut **TIDAK DICENTANG** (kecuali Anda benar-benar tahu apa yang Anda lakukan dan risikonya):
            *   ❌ `Aktifkan Penarikan` / `Enable Withdrawals` (SANGAT BERBAHAYA JIKA BOT TERKOMPROMI)
            *   ❌ `Aktifkan Margin` (jika Anda tidak berniat trading margin)
            *   ❌ `Izinkan Transfer Universal`, `Aktifkan Perdagangan Opsi Vanilla`, dll.
        10. **Batasan Akses IP (Direkomendasikan untuk keamanan ekstra):**
            *   Anda bisa memilih "Batasi akses hanya ke IP tepercaya". Jika Anda menjalankan bot dari server dengan IP statis, masukkan IP tersebut. Jika IP Anda dinamis, ini mungkin lebih rumit. Untuk awal, Anda bisa membiarkannya "Tidak Dibatasi", tetapi pahami risikonya.
        11. Klik **"Simpan"**.

    *   **Untuk Akun Testnet (Latihan):**
        1.  Kunjungi [Binance Spot Testnet](https://testnet.binance.vision/).
        2.  Login menggunakan akun GitHub Anda atau buat akun baru.
        3.  Setelah login, Anda akan melihat API Key dan Secret Key Testnet Anda secara otomatis. Salin dan simpan.
        4.  API Key Testnet tidak memiliki batasan izin yang rumit seperti akun produksi, dan dananya adalah dana virtual (tidak nyata).

    **INGAT:** Gunakan API Key yang sesuai dengan pengaturan `use_testnet` di bot Anda. API Key Produksi tidak akan bekerja di Testnet, dan sebaliknya.

---

## ▶️ Menjalankan Bot

Setelah semua konfigurasi selesai, buka terminal atau command prompt Anda, navigasi ke direktori tempat Anda menyimpan skrip, dan jalankan:
```bash
python bnb_trader_bot.py
