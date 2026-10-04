# Wilco AI: System Architecture & Technical Design Document

**Document Version:** 1.0.0  
**Date:** 2026-10-05  
**Status:** Approved for Implementation Planning  
**Target Simulator:** X-Plane 12 (Windows / macOS / Linux)  
**Reference Product:** SayIntentions.AI  

---

## 1. Executive Summary & Objectives

Wilco AI is an advanced, real-time virtual Air Traffic Control (ATC) companion application designed to replace the default synthetic ATC in X-Plane 12. Utilizing bidirectional audio-to-audio streaming via the **Google Gemini Multimodal Live API**, Wilco AI enables realistic voice communications with sub-second latency ($\le 1.2$ s) without traditional discrete multi-stage pipelines (STT $\rightarrow$ LLM $\rightarrow$ TTS).

### Key Architectural Tenets
1. **Best-in-Class Domain Engineering ("Bahasa Unggul Sesuai Keandalannya"):**
   - **Rust (Tauri Core):** Dedicated to high-priority system tasks where memory safety, zero-garbage-collection pauses, and microsecond precision are critical (Audio I/O, DSP filtering, USB HID joystick polling, and UDP telemetry ingestion).
   - **Web Technologies (Tauri Frontend):** Crisp, lightweight, modern UI displaying cockpit radio statuses, VU meters, and configuration.
   - **Python (FastAPI Gateway):** Dedicated to LLM orchestration, bidirectional WebSocket sessions with Gemini Live API, AIRAC 2606 navigation data parsing, and flight phase state tracking.
2. **Authentic Aviation Immersion:**
   - Full VHF radio DSP effects (biquad bandpass 300–3,400 Hz, static white noise, squelch open/tail clicks).
   - Autonomous ATIS generated directly from live X-Plane weather and broadcast in continuous loops.
   - Automated muting of native X-Plane synthetic ATC audio via UDP dataref overrides.
3. **NavData & AIRAC Realism:**
   - Real-world airport and procedure extraction directly from Navigraph AIRAC 2606 (`D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data`).
   - SIDs, STARs, and runway layouts for pilot airports (WAHH / Adisutjipto and WAHI / WARJ Yogyakarta International).
4. **Bilingual Phraseology:**
   - Native adherence to standard ICAO English phraseology by default.
   - Intelligent handling of Indonesian aviation phraseology for domestic flights and Indonesian simmers.

---

## 2. High-Level System Architecture

```
+---------------------------------------------------------------------------------+
|                                 X-Plane 12                                      |
|    - Broadcasts Aircraft Telemetry over UDP port 49000 (10 Hz)                  |
|    - Receives Volume & Dataref Overrides via UDP DREF packets                   |
+-----------------------+---------------------------------+-----------------------+
                        | UDP RREF (Stream Out)           ^ UDP DREF (Mute In)
                        v                                 |
+---------------------------------------------------------------------------------+
|                        Wilco AI Companion App (Tauri v2)                        |
|                                                                                 |
|   +-------------------------------------------------------------------------+   |
|   |                       Frontend UI (React / Svelte)                      |   |
|   |   - Radio Frequencies Display (COM1 / COM2)                             |   |
|   |   - Microphone & Speaker Audio VU Meters                                |   |
|   |   - Callsign, Tail Number, and Flight Plan Config                       |   |
|   |   - Joystick / Keyboard PTT Assignment Wizard                           |   |
|   |   - Live ATC Communications Transcript Log                              |   |
|   +------------------------------------+------------------------------------+   |
|                                        | IPC Events                             |
|   +------------------------------------+------------------------------------+   |
|   |                            Rust Core Engine                             |   |
|   |   1. UDP Telemetry Worker (tokio::net::UdpSocket @ 10 Hz)                |   |
|   |   2. Global PTT Controller (gilrs DirectInput/HID + global-hotkey)      |   |
|   |   3. Audio Capture Pipeline (cpal 16/24kHz PCM mono lock-free ringbuf)  |   |
|   |   4. Audio Playback & DSP Engine (Biquad bandpass + Squelch + Noise)    |   |
|   |   5. Local ATIS Loop Player (Continuous playback when tuned)             |   |
|   +------------------------------------+------------------------------------+   |
+----------------------------------------|----------------------------------------+
                                         | WebSocket (Localhost / LAN / Cloud)
                                         | Binary Audio Frames + Telemetry JSON
                                         v
+---------------------------------------------------------------------------------+
|                     Wilco AI Gateway Server (Python / FastAPI)                  |
|                                                                                 |
|   - Session Manager & Authentication Token Verification                         |
|   - AIRAC 2606 NavData Engine (Parses atc.dat & CIFP for WAHH/WAHI)             |
|   - Real-time Flight Phase State Machine (Clearance, Pushback, Taxi, Takeoff)   |
|   - Weather & ATIS Generator (Synthesizes ICAO ATIS loop from X-Plane Datarefs) |
|   - Gemini Multimodal Live Client (Bidi-streaming WebSocket to Google GenAI)    |
+----------------------------------------+----------------------------------------+
                                         | Secure WSS (google.genai.live)
                                         v
+---------------------------------------------------------------------------------+
|                      Google Gemini Multimodal Live API                          |
|             (Direct Native Audio-to-Audio Ingestion & Generation)               |
+---------------------------------------------------------------------------------+
```

---

## 3. Subsystem Specifications

### 3.1 Simulator Telemetry Ingestion (Rust)
- **Protocol:** X-Plane 12 UDP binary socket protocol on port `49000`.
- **RREF Subscription:**
  - Rust UDP worker sends `RREF\0` subscription request on startup and repeats keep-alive every 5 seconds.
  - Frequency: 10 Hz.
- **Monitored Datarefs:**
  | Dataref Path | Data Type | Purpose |
  |---|---|---|
  | `sim/cockpit2/radios/actuators/com1_frequency_hz_833` | `i32` | Active COM1 frequency (8.33 kHz channel spacing) |
  | `sim/cockpit2/radios/actuators/com2_frequency_hz_833` | `i32` | Active COM2 frequency |
  | `sim/cockpit2/radios/actuators/audio_com_selection` | `i32` | Active transmitting radio selector (1 = COM1, 2 = COM2) |
  | `sim/flightmodel/position/latitude` | `f64` | Aircraft latitude |
  | `sim/flightmodel/position/longitude` | `f64` | Aircraft longitude |
  | `sim/flightmodel/position/elevation` | `f64` | True elevation (MSL meters) |
  | `sim/flightmodel/position/y_agl` | `f32` | Radio altitude above ground (AGL meters) |
  | `sim/flightmodel2/gear/on_ground[0]` | `bool` | Weight-on-wheels ground flag |
  | `sim/cockpit/radios/transponder_code` | `i32` | Active squawk code |
  | `sim/cockpit2/gauges/actuators/barometer_setting_in_hg_pilot` | `f32` | Altimeter setting (inHg) |
  | `sim/flightmodel/position/groundspeed` | `f32` | Groundspeed (m/s) |
  | `sim/weather/aircraft/wind_speed_kts` | `f32` | Local wind speed |
  | `sim/weather/aircraft/wind_direction_degs` | `f32` | Local wind direction |
  | `sim/weather/aircraft/temperature_ambient_deg_c` | `f32` | Ambient temperature |
  | `sim/weather/aircraft/barometer_current_inhg` | `f32` | Local station atmospheric pressure |

- **Default ATC Voice Suppression:**
  - To prevent default X-Plane robotic voices from overlapping Wilco AI ATC and ATIS broadcasts, the client automatically writes to X-Plane over UDP:
    - Packet format: `DREF\0` + `[0.0 as f32]` + `"sim/operation/sound/radio_atc_volume_ratio"` (null-padded to 500 bytes).
  - Sent upon connection establishment; restores to original value (`1.0`) on graceful client shutdown.

---

### 3.2 Global Push-to-Talk (PTT) & Dual-Radio Controller (Rust)
- **Primary COM1 PTT & Secondary COM2 PTT:**
  - Supports separate physical triggers or a single master PTT with radio selection determined by X-Plane cockpit audio panel state.
- **Hardware Interception:**
  - **USB Joystick / Flight Controller:** Polled at 50 Hz via `gilrs` or `hidapi`. Captures button events from yoke, joystick, or HOTAS throttles even when X-Plane has OS window focus.
  - **Global Keyboard Hotkey:** Intercepts system-wide keyboard events using low-level hooks (`global-hotkey`), preventing key eating or focus loss.
  - **UI Button Learning:** User clicks "Assign PTT", presses any joystick button or keyboard key, and the ID is mapped and saved into local client configuration.

---

### 3.3 Audio Pipeline & VHF Radio DSP Engine (Rust)
- **Microphone Capture (`cpal`):**
  - Format: Linear PCM, 16-bit signed integer (`i16`), mono.
  - Sample Rate: 16,000 Hz or 24,000 Hz.
  - Buffer Architecture: Lock-free ring buffer (`ringbuf`) in high-priority audio callback thread; zero memory reallocation during streaming.
  - Packet Chunking: 50 ms chunks (1,200 samples @ 24 kHz) packaged into binary WebSocket frames.
- **Audio Output & VHF DSP Filter:**
  - **Biquad IIR Bandpass Filter:**
    - Low-cut cutoff: 300 Hz.
    - High-cut cutoff: 3,400 Hz.
    - Emulates the characteristic frequency response of aeronautical VHF AM radios.
  - **White Noise Generator:**
    - Algorithmic Gaussian noise floor (-28 dB to -34 dB adjustable) dynamically blended during incoming ATC transmission.
  - **Squelch Click Management:**
    - **Squelch Open:** Short audio burst (25 ms) triggered immediately upon receiving the first audio buffer of an ATC response.
    - **Squelch Tail (Close):** Classic VHF static tail burst (60 ms) played when incoming turn completes.
  - **Real-Time VU Meter:**
    - RMS energy calculated per frame: $\text{RMS} = \sqrt{\frac{1}{N}\sum_{i=1}^N x_i^2}$.
    - Throttled events emitted to Tauri UI to render mic levels and ATC audio levels.

---

### 3.4 Navigation Data & AIRAC 2606 Engine (Python)
- **Data Source:** `D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data`
- **Modules:**
  - `atc_parser.py`:
    - Parses `1200 atc data/Earth nav data/atc.dat`.
    - Extracts ATC facilities for target airports: Delivery, Ground, Tower, Approach/Departure, and ATIS frequencies.
    - Validates pilot transmission frequency against facility role.
  - `cifp_parser.py`:
    - Parses ARINC 424 CIFP files (`CIFP/WAHH.dat` and `CIFP/WAHI.dat` / `WARJ`).
    - Extracts active runway identifiers (WAHH: 09/27; WAHI: 11/29), transition altitude (11,000 ft), standard instrument departures (e.g. `CA2L`, `CLP2F`), and terminal fixes (`NASWA`, `SEGTU`, `SUWUN`, `IGRIT`, etc.).
  - **Airports Initialized in MVP:**
    - **WAHH** (Adisutjipto International Airport, Yogyakarta):
      - Runway: 09 / 27 (Length: 2,200m).
      - Facilities: Tower (118.10 MHz), Ground (121.90 MHz), ATIS (126.40 MHz).
    - **WAHI** (Yogyakarta International Airport, Kulon Progo - YIA):
      - Runway: 11 / 29 (Length: 3,250m).
      - Facilities: Tower (118.20 MHz), Ground (121.65 MHz), ATIS (127.80 MHz).

---

### 3.5 Autonomous ATIS Broadcast Subsystem (Python Gateway + Rust Player)
1. **Weather & Simulator Time Ingestion:**
   - Gateway reads X-Plane 12 weather parameters and Zulu time: `sim/time/zulu_time_sec`, wind direction/speed, ambient temperature, QNH, and runway orientation.
2. **Automatic Update Triggers (Schedule & SPECI):**
   - **Periodic Schedule:** Automatically advances every 30–60 minutes synced to simulator Zulu time (matching standard METAR observation intervals).
   - **Significant Weather Trigger (SPECI):** Automatically triggers immediate regeneration if:
     - Wind direction shift changes active runway in use.
     - Atmospheric pressure (QNH) shifts by $\ge 1$ hPa ($\ge 0.03$ inHg).
     - Visibility or cloud ceiling changes significantly.
   - **Phonetic Letter Progression:**
     - The phonetic letter automatically increments sequentially: **Alpha $\rightarrow$ Bravo $\rightarrow$ Charlie $\dots \rightarrow$ Zulu $\rightarrow$ Alpha**.
3. **ATIS Script Generator:**
   - Generates standardized ICAO phonetic text matching the current ATIS phonetic letter and updated timestamp:
     > *"Yogyakarta International Information Charlie, time 0145 UTC. Runway in use 11. Wind 100 degrees 7 knots, visibility 10 kilometers, clouds few 3500 feet, temperature 29, dewpoint 23, QNH 1011. Advise controller on initial contact you have information Charlie."*
4. **Seamless Audio Loop Synthesizer & Cache:**
   - Gateway synthesizes ATIS voice audio with continuous background static and caches the audio stream.
   - Transitions between old and new ATIS loops seamlessly at loop boundary without cutting off in mid-sentence.
5. **Local Radio Tuning Playback:**
   - When pilot tunes COM1 or COM2 to the airport's ATIS frequency (e.g. 127.80 MHz), the Rust audio engine plays the ATIS loop seamlessly. Tuning away immediately stops playback.
6. **Controller Synchronization & Readback Enforcement:**
   - The active ATIS phonetic letter is immediately synchronized into the AI Controller's context.
   - If a pilot checks in with an outdated letter, the AI Controller automatically corrects the pilot:
     > *"Indonesia 123, Information Charlie is now current, QNH 1011. Cleared to..."*

---

### 3.6 Multimodal Live AI Session Management (Python)
- **Bidirectional WebSocket Connection:**
  - Maintains continuous connection with `google.genai.live` WebSocket endpoint using the official Python SDK.
- **Flight Context Injection:**
  - Injects contextual metadata before pilot transmission chunks are evaluated:
    ```json
    {
      "aircraft": {
        "callsign": "Indonesia 123",
        "type": "B738",
        "squawk": 1200,
        "altimeter_inhg": 29.82
      },
      "position": {
        "airport": "WAHI",
        "on_ground": true,
        "altitude_msl_ft": 55,
        "groundspeed_kts": 0
      },
      "radio": {
        "tuned_radio": "COM1",
        "frequency_hz": 121650000,
        "facility": "WAHI_GROUND",
        "atis_letter": "CHARLIE"
      },
      "flight_phase": "APRON_PUSHBACK_REQUEST"
    }
    ```
- **Language & Phraseology Policy:**
  - **Standard ICAO English:** Primary instruction language for ATC clearances, runway assignments, squawk codes, and readbacks.
  - **Bilingual Indonesian Support:** Naturally interprets Indonesian transmissions (*"Jogja Ground, Garuda 123 mohon izin pushback dan start stand empat"*), replying with appropriate professional bilingual ATC phraseology.
- **Validation Engine:**
  - **Frequency Check:** If pilot transmits on an invalid or unassigned frequency, the system does not invoke the LLM; instead, it returns dead air or momentary VHF static.
  - **Readback Verification:** Explicitly verifies pilot readback of critical flight safety parameters (QNH, assigned runway, assigned squawk, hold short instructions). Issues immediate corrections if discrepancies occur.

---

## 4. User Interface Specification (Tauri v2 Frontend)

The companion application features an aviation-themed dark interface:
1. **Header Bar:**
   - Connection status indicators: `X-Plane 12: Connected (10 Hz)` | `AI Gateway: Online` | `AIRAC: 2606 Active`.
2. **Radio & Audio Monitor Panel:**
   - **COM1 & COM2 Active Displays:** Digital 6-digit frequency display (e.g., `121.650 MHz`) with auto-detected facility label (`[WAHI GND]`).
   - **Audio Level VU Meters:** Real-time LED-style bar for Mic input and ATC output.
   - **PTT Status Indicator:** Visual glowing "TX" badge when PTT is pressed.
3. **Flight Information Input:**
   - Pilot Callsign (e.g., `GIA123`), Flight Rules (`IFR / VFR`), Dep/Dest Airport.
4. **Settings & Hardware Setup:**
   - PTT keybinding assignment for USB joystick buttons and keyboard keys.
   - VHF Radio Effect sliders (Bandpass effect intensity, Squelch volume, White noise level).
   - Audio input and output device selectors.
5. **Live Communications Transcript:**
   - Scrollable chat-style log showing pilot transmissions and ATC controller readouts with timestamps.

---

## 5. Resilience, Error Handling, & Edge Cases

1. **X-Plane Simulator Disconnection:**
   - If UDP packets stop for $> 3.0$ s, the Rust client flags simulator state as `DISCONNECTED`, pauses streaming to the Gateway, and displays an unobtrusive reconnections alert in the UI. Automatically resumes when packets reappear.
2. **Gateway / Internet Disconnection:**
   - If the WebSocket drops, the client plays a subtle radio disconnect chime. The Gateway implements exponential backoff reconnection to the Gemini Live endpoint.
3. **Audio Buffer Underrun / Overrun:**
   - Handled via `ringbuf` atomic head/tail pointers. If buffer underrun occurs during playback, silence is inserted rather than stalling the OS audio thread.
4. **Dead / Unmonitored Frequencies:**
   - Transmissions on inactive frequencies generate instant local VHF sidetone and dead air, eliminating unnecessary AI API token consumption.

---

## 6. Testing & Quality Assurance Strategy

1. **Unit Testing:**
   - `udp_parser_test.rs`: Validates byte deserialization of X-Plane `RREF` packets against real hex payloads.
   - `dsp_filter_test.rs`: Confirms biquad frequency attenuation at 200 Hz (< -20 dB) and 4,000 Hz (< -18 dB).
   - `airac_parser_test.py`: Verifies extraction of WAHH and WAHI frequencies, runways, and SIDs from `atc.dat` and `CIFP`.
2. **Integration & Mock Testing:**
   - `mock_xplane_sender.py`: Standalone UDP test script sending simulated flight data (pushback, taxi, takeoff) to verify client ingestion without running X-Plane 12.
   - `mock_audio_loopback.py`: Tests full audio capture $\rightarrow$ DSP $\rightarrow$ playback cycle.
3. **End-to-End Simulation Testing:**
   - Live testing in X-Plane 12 at WAHI with Cessna 172 and Boeing 737:
     - ATIS reception on COM2.
     - Clearance Delivery $\rightarrow$ Push & Start $\rightarrow$ Taxi to holding point RW11 $\rightarrow$ Takeoff clearance on COM1.
