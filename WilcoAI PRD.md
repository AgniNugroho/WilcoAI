# Product Requirement Document (PRD)

**Nama Proyek:** Wilco AI  
**Versi:** 1.1.0 (MVP)  
**Status:** Approved Architecture Draft  
**Target Platform:** X-Plane 12 (Windows / macOS / Linux)  
**Core AI Engine:** Multimodal Live API (Direct Audio-to-Audio Streaming over WebSocket)

---

## 1. Executive Summary & Problem Statement

### 1.1 Background
ATC bawaan pada X-Plane 12 mengandalkan pohon dialog teks yang kaku dan suara sintesis robotik tanpa kemampuan memproses transmisi suara alami (*natural speech*). Di sisi lain, jaringan online dengan kontroler manusia (VATSIM/IVAO) kerap memiliki kekosongan frekuensi di wilayah tertentu serta memicu *mic anxiety* bagi pilot yang masih belajar.

### 1.2 Objective
Membangun asisten radio ATC virtual pintar untuk X-Plane 12 yang beroperasi secara *real-time*. Sistem ini memanfaatkan arsitektur **Multimodal Live Audio-to-Audio API** dua arah melalui WebSocket. Sistem menerima audio mentah dari mikrofon pilot, menyinkronkannya dengan telemetri simulator lokal, dan mengembalikan suara kontroler ATC dengan latensi sub-detik tanpa melalui tahapan modular terpisah (STT $\rightarrow$ LLM $\rightarrow$ TTS).

---

## 2. User Persona & Core User Flow

### 2.1 Target Persona
* **The Procedural Simmer:** Pilot simulator yang ingin melatih prosedur komunikasi IFR/VFR, *readback* altimeter/squawk, dan alur keberangkatan secara autentik kapan saja.
* **The Flight Student:** Siswa penerbang yang membutuhkan media repetisi fraseologi radio standar ICAO/FAA tanpa tekanan kontroler manusia.

### 2.2 Core User Flow
1. Pilot menyalakan X-Plane 12, memarkir pesawat di apron bandara uji coba (misal: Bandara Adisutjipto / YIA), dan menyetel radio COM1 ke frekuensi fasilitas aktif (misal: Ground 121.900 MHz).
2. Klien lokal Wilco AI mendeteksi status pesawat dan membuka sesi streaming ke Multimodal Live API.
3. Pilot menekan tombol Push-to-Talk (PTT) pada joystick/yoke dan berbicara:  
   > *"Jogja Ground, Indonesia 123, stand 4, request taxi for departure runway 09."*
4. Klien lokal mengalirkan chunk audio PCM bersama status telemetri terkini.
5. Pilot melepas PTT.
6. Server Multimodal AI memproses konteks audio + telemetri secara terpadu, lalu mengalirkan balik audio respon suara kontroler secara instan ($\le 1.2$ detik):  
   > *"Indonesia 123, Jogja Ground, taxi to holding point runway 09 via taxiway Alpha, Bravo. QNH 1010."*
7. Audio respons dimainkan melalui output suara simulator dengan efek filter radio VHF lokal.

---

## 3. Scope & Phasing

### Phase 1: MVP Scope
* Bandara rujukan awal: 1–2 bandara dengan pemetaan frekuensi dan layout runway jelas (contoh: WAHH / WARJ).
* Fasilitas ATC: **Clearance Delivery, Ground, dan Tower**.
* Validasi radio: Hanya merespons jika frekuensi COM1 aktif sesuai dengan stasiun yang dipanggil.
* Siklus penerbangan dasar: Request Clearance $\rightarrow$ Push & Start $\rightarrow$ Taxi to Runway $\rightarrow$ Takeoff Clearance $\rightarrow$ Initial Airborne Hand-off.
* Integrasi telemetri satu arah dari X-Plane 12 via UDP Datarefs.

### Phase 2: Post-MVP Roadmap
* Layanan Approach / Departure Radar Vectoring dinamis dan Enroute Center.
* Integrasi pembacaan lalu lintas AI di sekitar pesawat untuk separasi runway dan *traffic alert*.
* Efek co-pilot cerdas dan *ambient radio chatter* dari pesawat lain di frekuensi yang sama.

---

## 4. Functional Requirements

### 4.1 Simulator Telemetry (UDP Ingestion)
* **FR-1.1:** Klien lokal harus menangkap paket UDP X-Plane 12 (default port `49000`) pada interval 10 Hz tanpa mengganggu thread rendering simulator.
* **FR-1.2:** Klien harus mengekstrak parameter dataref berikut:
  * `sim/cockpit2/radios/actuators/com1_frequency_hz_833`: Frekuensi radio COM1 aktif.
  * `sim/flightmodel/position/latitude` & `longitude`: Koordinat pesawat untuk validasi posisi.
  * `sim/flightmodel2/gear/on_ground[0]`: Status fisik apakah pesawat di darat atau di udara.
  * `sim/cockpit/radios/transponder_code`: Kode squawk aktif.
  * `sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot`: Pengaturan altimeter (QNH).

### 4.2 Local Audio & PTT Controller
* **FR-2.1 Global PTT Hook:** Sistem harus mendeteksi input PTT dari tombol keyboard maupun direct USB Joystick/HID saat jendela simulator aktif di latar belakang.
* **FR-2.2 Audio Streaming:** Saat PTT ditekan, sistem merekam audio mikrofon dalam format 16 kHz atau 24 kHz Linear PCM 16-bit mono dan mengalirkannya langsung sebagai binary chunk ke gateway backend.
* **FR-2.3 Squelch & VHF DSP:** Setiap audio respons dari AI harus diproses secara lokal menggunakan filter DSP:
  * Bandpass filter (300 Hz – 3.400 Hz).
  * Lapisan desisan radio statis (*white noise floor* tipis).
  * Suara klik *mic-keying / squelch tail* di awal dan akhir transmisi.

### 4.3 Multimodal Live AI Session Management
* **FR-3.1 Native Audio-to-Audio Connection:** Backend mengelola koneksi WebSocket dua arah ke endpoint Multimodal Live API, mengeliminasi kebutuhan konversi teks perantara.
* **FR-3.2 Real-time Telemetry Injection:** Sebelum transmisi audio pilot diproses (atau secara berkala via metadata frame), status penerbangan dikirimkan ke model sebagai injeksi konteks:
  ```json
  {
    "callsign": "Indonesia 123",
    "airport": "WARJ",
    "active_com1_hz": 118200000,
    "on_ground": true,
    "current_altitude_ft": 350,
    "current_phase": "HOLDING_SHORT_09"
  }