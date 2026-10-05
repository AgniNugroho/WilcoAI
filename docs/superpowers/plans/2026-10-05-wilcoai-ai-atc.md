# Wilco AI (X-Plane 12 AI ATC) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete Wilco AI virtual ATC system for X-Plane 12, featuring a Tauri v2 / Rust companion client (UDP telemetry, VHF DSP audio, global joystick PTT) and a Python FastAPI gateway (AIRAC 2606 NavData, autonomous ATIS, flight state machine, and bidirectional Gemini Multimodal Live API audio-to-audio streaming).

**Architecture:** Polyglot specialized architecture. The client desktop companion is built in Tauri v2 (Rust Core for low-level audio I/O, biquad DSP, USB HID polling, and UDP sockets; modern Webview for UI). The AI Gateway is built in Python FastAPI with the Google GenAI SDK, parsing Navigraph AIRAC 2606 data from X-Plane 12 and orchestrating real-time audio-to-audio WebSocket sessions with Google Gemini Live API.

**Tech Stack:**
- **Client:** Rust 1.80+, Tauri v2, `cpal` (audio I/O), `biquad` (DSP filter), `ringbuf` (lock-free audio buffer), `tokio` (async UDP & WebSocket), `gilrs` (USB Joystick/HID), `global-hotkey` (keyboard hooks), React/TypeScript + Tailwind CSS (UI).
- **Gateway:** Python 3.11+, FastAPI, `uvicorn`, `websockets`, `google-genai` (Multimodal Live API), `pydantic`.
- **NavData Source:** Navigraph AIRAC 2606 at `D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data`.

**Spec:** [docs/superpowers/specs/2026-10-05-wilcoai-ai-atc-design.md](file:///d:/Code/WilcoAI/docs/superpowers/specs/2026-10-05-wilcoai-ai-atc-design.md)

## Global Constraints

- Python Gateway must use Python 3.11+ and official `google-genai` SDK for Multimodal Live WebSocket connection.
- Client audio capture and playback format must be Linear PCM 16-bit mono at 24,000 Hz or 16,000 Hz.
- X-Plane UDP dataref ingestion must run on port `49000` using standard `RREF` protocol at 10 Hz without blocking UI or audio callbacks.
- Client must automatically send UDP `DREF` packet setting `sim/operation/sound/radio_atc_volume_ratio` to `0.0` to suppress native X-Plane robotic voices.
- VHF DSP audio pipeline must filter frequencies with 300 Hz low-cut and 3,400 Hz high-cut bandpass, subtle white noise (-30 dB), and squelch open/tail clicks.
- Initial airport reference models: WAHH (Adisutjipto) and WAHI (Yogyakarta International Airport / YIA, alias WARJ).
- Phraseology must support bilingual operations: standard ICAO English as primary, with natural Indonesian ATC phraseology recognition and response.

## Review Focus

1. **UDP Packet Deserialization Jitter:** X-Plane sends varying sizes of `RREF,\0` payloads. Ensure the byte parser handles multi-dataref chunks without buffer panics or dropping values.
2. **Audio Buffer Underrun/Overrun:** Audio callback thread must remain strictly non-blocking (lock-free `ringbuf`). Dropped frames must insert silence instead of crashing the audio driver.
3. **Ghost Transmissions on Inactive Radios:** Transmitting on an untuned COM frequency must result in immediate local dead air/sidetone static, strictly avoiding LLM API token consumption.
4. **Out-of-Sync ATIS Information Letter:** Ensure transitions from letter to letter (e.g. Bravo to Charlie) atomically update both the streaming loop and the AI Controller's context so readback validation is always synchronized.
5. **Simulated Disconnection & Reconnection:** Gracefully handle X-Plane simulator pauses, crash/restarts, or flight reloads without requiring the companion app or gateway to be killed.

---

### Task 1: Project Repository Scaffolding & Environment Setup

**Files:**
- Create: `gateway/requirements.txt`
- Create: `gateway/pyproject.toml`
- Create: `client/src-tauri/Cargo.toml`
- Create: `client/src-tauri/tauri.conf.json`
- Create: `client/package.json`
- Create: `client/tsconfig.json`
- Create: `client/vite.config.ts`

**Interfaces:**
- Produces: Base project structure for `gateway` and `client`, buildable via `pip` and `cargo`/`npm`.

- [x] **Step 1: Create Python gateway environment configuration**
  Define `requirements.txt` with `fastapi>=0.115.0`, `uvicorn[standard]>=0.30.0`, `google-genai>=0.1.1`, `websockets>=13.0`, `pydantic>=2.8.0`, `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`.
- [x] **Step 2: Create Tauri v2 client workspace & Cargo configuration**
  Define `Cargo.toml` with dependencies: `tauri = { version = "2", features = [] }`, `tokio = { version = "1", features = ["full"] }`, `cpal = "0.15"`, `ringbuf = "0.3"`, `biquad = "0.4"`, `gilrs = "0.10"`, `global-hotkey = "0.5"`, `serde = { version = "1", features = ["derive"] }`, `serde_json = "1"`.
- [x] **Step 3: Setup Vite/React package.json and tsconfig**
  Setup modern lightweight web frontend dependencies (React 18 / Lucide icons / Tailwind CSS).
- [x] **Step 4: Verify build scaffolding**
  Run: `python -m pip install -r gateway/requirements.txt`
  Expected: Clean install without conflicts.
- [x] **Step 5: Commit**
  Run: `git add gateway client; git commit -m "chore: scaffold project structure for gateway and tauri client"`

---

### Task 2: Gateway AIRAC 2606 NavData Parser

**Files:**
- Create: `gateway/src/navdata/atc_parser.py`
- Create: `gateway/src/navdata/cifp_parser.py`
- Create: `gateway/src/navdata/models.py`
- Create: `gateway/src/navdata/__init__.py`
- Test: `gateway/tests/test_navdata.py`

**Interfaces:**
- Produces:
  - `AirportInfo`: dataclass with `icao: str`, `name: str`, `transition_alt: int`, `runways: list[Runway]`, `facilities: dict[str, int]`.
  - `load_airport(custom_data_path: str, icao: str) -> AirportInfo`
  - `get_facility_by_freq(airport: AirportInfo, frequency_hz: int) -> Optional[Facility]`

- [x] **Step 1: Write failing test in `gateway/tests/test_navdata.py`**
  Write tests that point to `D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data`, load `WAHI` and `WAHH`, and assert:
  - WAHI (YIA) has Tower frequency `118.200` MHz (`118200000` Hz) and Ground `121.650` MHz (`121650000` Hz).
  - WAHI has Runways `11` and `29`, transition altitude `11000`.
  - WAHI contains SID `CA2L` and `CLP2F`.
  - WAHH has Tower `118.100` MHz and Ground `121.900` MHz.
- [x] **Step 2: Run test to verify it fails**
  Run: `pytest gateway/tests/test_navdata.py -v`
  Expected: FAIL (modules not found).
- [x] **Step 3: Implement `models.py`, `atc_parser.py`, and `cifp_parser.py`**
  - Parse `1200 atc data/Earth nav data/atc.dat` for `CONTROLLER`, `FACILITY_ID`, `ROLE`, `FREQ`.
  - Parse `CIFP/WAHI.dat` and `CIFP/WAHH.dat` for runway identifiers, SIDs, and waypoints.
- [x] **Step 4: Run test to verify it passes**
  Run: `pytest gateway/tests/test_navdata.py -v`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add gateway/src/navdata gateway/tests; git commit -m "feat(gateway): implement AIRAC 2606 NavData parser for ATC facilities and SIDs"`

---

### Task 3: Autonomous ATIS Generator & Cycle Subsystem

**Files:**
- Create: `gateway/src/atis/generator.py`
- Create: `gateway/src/atis/state.py`
- Create: `gateway/src/atis/__init__.py`
- Test: `gateway/tests/test_atis.py`

**Interfaces:**
- Consumes: `AirportInfo` from `gateway.src.navdata.models`
- Produces:
  - `AtisState`: tracks current phonetic letter (A-Z), observation UTC time, active runway, and audio text script.
  - `evaluate_weather_update(current_state: AtisState, weather: TelemetryWeather) -> tuple[bool, AtisState]`
  - `generate_atis_text(airport: AirportInfo, letter: str, weather: TelemetryWeather, zulu_sec: int) -> str`

- [x] **Step 1: Write failing test in `gateway/tests/test_atis.py`**
  Test that:
  - Generating ATIS text produces standardized ICAO phraseology with phonetic letter, time in UTC, wind, visibility, clouds, temperature, dew point, QNH, and active runway.
  - Changing wind direction shifts active runway from 11 to 29 and triggers automatic letter increment (e.g. Alpha -> Bravo).
  - Shifting QNH by $\ge 1$ hPa triggers automatic SPECI update and increments phonetic letter.
  - Advancing time by 30+ minutes increments phonetic letter.
- [x] **Step 2: Run test to verify it fails**
  Run: `pytest gateway/tests/test_atis.py -v`
  Expected: FAIL.
- [x] **Step 3: Implement `generator.py` and `state.py`**
  Implement runway selection logic based on wind component, letter progression (A -> B -> ... -> Z -> A), and standardized phonetic generation.
- [x] **Step 4: Run test to verify it passes**
  Run: `pytest gateway/tests/test_atis.py -v`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add gateway/src/atis gateway/tests/test_atis.py; git commit -m "feat(gateway): implement autonomous ATIS state and ICAO script generator"`

---

### Task 4: Flight Phase State Machine & Readback Verification Engine

**Files:**
- Create: `gateway/src/atc/state_machine.py`
- Create: `gateway/src/atc/readback.py`
- Create: `gateway/src/atc/prompt_builder.py`
- Create: `gateway/src/atc/__init__.py`
- Test: `gateway/tests/test_state_machine.py`

**Interfaces:**
- Consumes: `AirportInfo`, `AtisState`
- Produces:
  - `FlightPhase`: Enum (`APRON_CLEARANCE`, `PUSHBACK_START`, `TAXI_TO_RUNWAY`, `HOLDING_SHORT`, `TAKEOFF_CLEAR`, `AIRBORNE_HANDOFF`).
  - `FlightSession`: maintains callsign, current phase, assigned runway, assigned squawk, cleared SID, target altitude.
  - `verify_readback(pilot_text: str, expected_items: dict) -> ReadbackResult`
  - `build_system_prompt(session: FlightSession, airport: AirportInfo, atis: AtisState) -> str`

- [x] **Step 1: Write failing test in `gateway/tests/test_state_machine.py`**
  Test:
  - Transition from `APRON_CLEARANCE` to `PUSHBACK_START` upon successful clearance readback.
  - Detection of readback error when pilot reads back wrong QNH or wrong squawk.
  - Bilingual prompt rules inclusion (standard ICAO English prompt with Indonesian phraseology recognition guidelines).
- [x] **Step 2: Run test to verify it fails**
  Run: `pytest gateway/tests/test_state_machine.py -v`
  Expected: FAIL.
- [x] **Step 3: Implement `state_machine.py`, `readback.py`, and `prompt_builder.py`**
  Write regex/rule-based readback validator and dynamic system instruction generator for Gemini Live API session.
- [x] **Step 4: Run test to verify it passes**
  Run: `pytest gateway/tests/test_state_machine.py -v`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add gateway/src/atc gateway/tests/test_state_machine.py; git commit -m "feat(gateway): implement flight phase state machine and readback validation"`


---

### Task 5: Gateway Gemini Multimodal Live API WebSocket Client & Server Gateway

**Files:**
- Create: `gateway/src/live/gemini_client.py`
- Create: `gateway/src/server.py`
- Create: `gateway/src/config.py`
- Test: `gateway/tests/test_gateway_server.py`

**Interfaces:**
- Consumes: `FlightSession`, `build_system_prompt`, `AirportInfo`
- Produces:
  - FastAPI WebSocket endpoint at `/ws/atc` accepting client audio PCM chunks and telemetry frames.
  - Bidirectional relay to `google.genai.live` WebSocket.
  - Dead air generation when transmission is made on invalid/unmonitored frequency.

- [x] **Step 1: Write failing integration test in `gateway/tests/test_gateway_server.py`**
  Test FastAPI WebSocket connection `/ws/atc`:
  - Connect client mock WebSocket.
  - Send telemetry frame with frequency `118.200` MHz (WAHI Tower).
  - Send audio chunk.
  - Assert that mock Gemini Live receives context injection frame and audio chunk.
  - Send telemetry frame with invalid frequency `120.000` MHz.
  - Assert that gateway responds with `DEAD_AIR` action without forwarding to Gemini.
- [x] **Step 2: Run test to verify it fails**
  Run: `pytest gateway/tests/test_gateway_server.py -v`
  Expected: FAIL.
- [x] **Step 3: Implement `gemini_client.py`, `config.py`, and `server.py`**
  Implement async session manager connecting via Google GenAI Live SDK or raw WSS with authentication, streaming PCM back to client.
- [x] **Step 4: Run test to verify it passes**
  Run: `pytest gateway/tests/test_gateway_server.py -v`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add gateway/src gateway/tests; git commit -m "feat(gateway): implement FastAPI WebSocket gateway and Gemini Live client"`

---

### Task 6: Client Rust X-Plane UDP Telemetry Ingestion & Native ATC Volume Muter

**Files:**
- Create: `client/src-tauri/src/xplane/packet.rs`
- Create: `client/src-tauri/src/xplane/listener.rs`
- Create: `client/src-tauri/src/xplane/sender.rs`
- Create: `client/src-tauri/src/xplane/mod.rs`
- Test: `client/src-tauri/tests/udp_test.rs`

**Interfaces:**
- Produces:
  - `AircraftSnapshot`: struct containing `com1_hz`, `com2_hz`, `active_radio`, `lat`, `lon`, `elevation_m`, `agl_m`, `on_ground`, `squawk`, `qnh_inhg`, `groundspeed_ms`, `wind_speed`, `wind_dir`.
  - `XPlaneUdpManager`: runs background `UdpSocket` loop, sends `RREF` keepalive, parses `RREF,\0` stream, and sends `DREF` mute packet for `sim/operation/sound/radio_atc_volume_ratio`.

- [x] **Step 1: Write failing test in `client/src-tauri/tests/udp_test.rs`**
  Test byte parsing of:
  - Formatted `RREF\0` subscription packet.
  - Simulated `RREF,\0` incoming payload with custom index and float32 values.
  - Formatted `DREF\0` packet setting volume to `0.0f32`.
- [x] **Step 2: Run test to verify it fails**
  Run: `cargo test --test udp_test`
  Expected: FAIL.
- [x] **Step 3: Implement `packet.rs`, `listener.rs`, and `sender.rs` in Rust**
  Use `tokio::net::UdpSocket` and byte parsing logic without memory allocations in hot paths.
- [x] **Step 4: Run test to verify it passes**
  Run: `cargo test --test udp_test`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add client/src-tauri; git commit -m "feat(client): implement X-Plane 12 UDP telemetry ingestion and ATC muter"`

---

### Task 7: Client Rust Audio Pipeline & VHF Radio DSP Engine

**Files:**
- Create: `client/src-tauri/src/audio/capture.rs`
- Create: `client/src-tauri/src/audio/playback.rs`
- Create: `client/src-tauri/src/audio/dsp.rs`
- Create: `client/src-tauri/src/audio/mod.rs`
- Test: `client/src-tauri/tests/dsp_test.rs`

**Interfaces:**
- Produces:
  - `VhfDspFilter`: Biquad bandpass filter (300 Hz - 3400 Hz), white noise generator (-30 dB), squelch burst generator.
  - `AudioCapture`: initializes `cpal` input stream (24 kHz PCM 16-bit mono), stores frames in `ringbuf`.
  - `AudioPlayback`: plays incoming ATC chunks processed through `VhfDspFilter`.
  - `calculate_rms(samples: &[i16]) -> f32` (for VU meter).

- [x] **Step 1: Write failing test in `client/src-tauri/tests/dsp_test.rs`**
  Test that:
  - Frequency response below 300 Hz is attenuated by at least 18 dB.
  - Frequency response above 3400 Hz is attenuated by at least 18 dB.
  - Squelch open click (25 ms) and squelch tail click (60 ms) buffers are generated correctly without NaN/overflow.
- [x] **Step 2: Run test to verify it fails**
  Run: `cargo test --test dsp_test`
  Expected: FAIL.
- [x] **Step 3: Implement `dsp.rs`, `capture.rs`, and `playback.rs` in Rust**
  Implement 2nd-order biquad IIR bandpass filter, Gaussian noise generator, and lock-free ring buffer audio streaming.
- [x] **Step 4: Run test to verify it passes**
  Run: `cargo test --test dsp_test`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add client/src-tauri; git commit -m "feat(client): implement VHF radio DSP bandpass, noise, and squelch engine"`

---

### Task 8: Client Rust Global PTT & Hardware Controller

**Files:**
- Create: `client/src-tauri/src/ptt/joystick.rs`
- Create: `client/src-tauri/src/ptt/hotkey.rs`
- Create: `client/src-tauri/src/ptt/mod.rs`
- Test: `client/src-tauri/tests/ptt_test.rs`

**Interfaces:**
- Produces:
  - `PttManager`: monitors joystick button via `gilrs` and keyboard global hotkeys.
  - Emits `PttEvent::Pressed { radio: RadioType }` and `PttEvent::Released { radio: RadioType }` (supporting COM1 and COM2).
  - Button learning mode for UI mapping.

- [x] **Step 1: Write failing test in `client/src-tauri/tests/ptt_test.rs`**
  Test state transitions of PTT state machine from `Idle` to `Active(COM1)` and `Active(COM2)` to `Released`.
- [x] **Step 2: Run test to verify it fails**
  Run: `cargo test --test ptt_test`
  Expected: FAIL.
- [x] **Step 3: Implement `joystick.rs`, `hotkey.rs`, and `ptt/mod.rs`**
  Implement background polling thread using `gilrs` and Windows low-level global hotkey listener.
- [x] **Step 4: Run test to verify it passes**
  Run: `cargo test --test ptt_test`
  Expected: PASS.
- [x] **Step 5: Commit**
  Run: `git add client/src-tauri; git commit -m "feat(client): implement global PTT joystick and keyboard controller"`

---

### Task 9: Desktop Frontend UI & Tauri IPC Wiring

**Files:**
- Create: `client/src/App.tsx`
- Create: `client/src/components/RadioPanel.tsx`
- Create: `client/src/components/VuMeter.tsx`
- Create: `client/src/components/PttConfig.tsx`
- Create: `client/src/components/TranscriptLog.tsx`
- Create: `client/src-tauri/src/main.rs`
- Create: `client/src-tauri/src/commands.rs`

**Interfaces:**
- Consumes: Tauri IPC events: `telemetry_update`, `audio_level_update`, `atc_transcript_update`, `ptt_state_change`.
- Produces: Complete, responsive desktop UI running via Tauri v2.

- [x] **Step 1: Implement Tauri command handlers in `commands.rs`**
  Expose commands to frontend: `set_callsign`, `set_ptt_binding`, `set_dsp_settings`, `connect_gateway`.
- [x] **Step 2: Implement UI components**
  - `RadioPanel.tsx`: Digital COM1/COM2 LED displays, active facility badge, and status indicators.
  - `VuMeter.tsx`: Real-time audio level bars for Mic in and ATC out.
  - `PttConfig.tsx`: Joystick button detection and assignment modal.
  - `TranscriptLog.tsx`: Live scrollable chat feed with pilot & ATC dialogue.
- [x] **Step 3: Build frontend and verify Tauri integration**
  Run: `npm --prefix client run build`
  Expected: Clean build without TypeScript or bundling errors.
- [x] **Step 4: Commit**
  Run: `git add client; git commit -m "feat(client): implement modern aviation UI and Tauri IPC bindings"`

---

### Task 10: Simulator Mock Tooling & End-to-End System Verification

**Files:**
- Create: `scripts/mock_xplane_sender.py`
- Create: `scripts/mock_atc_dialogue.py`
- Test: `tests/e2e_verification.py`

**Interfaces:**
- Produces:
  - Interactive simulator harness sending simulated WAHI flight telemetry over UDP `49000`.
  - Comprehensive end-to-end verification script testing the complete chain.

- [ ] **Step 1: Create `scripts/mock_xplane_sender.py`**
  Python script broadcasting X-Plane UDP datarefs simulating:
  - Aircraft at WAHI Ramp (COM1: 121.650 MHz WAHI Ground).
  - Weather: Wind 100@7 kts, QNH 1011 hPa, Temp 29 C.
  - Pushback, taxi to RW11 holding short, switch to Tower 118.200 MHz, takeoff run.
- [ ] **Step 2: Run End-to-End integration test**
  Run: `python scripts/mock_xplane_sender.py --scenario departure_wahi` and verify telemetry ingestion in companion app.
  Expected: Klien receives 10 Hz UDP packets, UI displays `WAHI GND (121.650 MHz)`, and native ATC volume mute command is dispatched.
- [ ] **Step 3: Verify Audio & DSP loop**
  Trigger PTT transmisi, verify audio streaming to Gateway `/ws/atc`, verify response playback with VHF DSP squelch click and bandpass.
- [ ] **Step 4: Commit**
  Run: `git add scripts tests; git commit -m "test: add mock X-Plane UDP harness and end-to-end verification tests"`
