#!/usr/bin/env python3
"""
Wilco AI - End-to-End System Verification Test Suite.

Comprehensive integration tests covering:
1. UDP binary serialization & parsing (X-Plane 12 RREF / DREF protocol):
   - Encoding & parsing 13 monitored flight dataref records
   - Testing 5-byte and 6-byte RREF packet headers
   - Mock X-Plane server & client UDP socket communication
   - Ingestion and verification of DREF native ATC volume mute command
2. Gateway WebSocket (/ws/atc):
   - Initial connection handshake (CONNECTED)
   - Telemetry ingestion & frequency validation
   - DEAD_AIR status for unmonitored frequencies (and blocking transmission)
   - Valid facility tuning (WAHI Ground 121.650 MHz, WAHI Tower 118.200 MHz)
   - Push-to-Talk (PTT) state coordination (TRANSMITTING -> IDLE)
   - Mock Gemini Live bidirectional audio and transcript relay
3. Complete departure flight phase lifecycle and bilingual readback verification:
   - Ordered phase transitions: APRON_CLEARANCE -> PUSHBACK_START -> TAXI_TO_RUNWAY -> HOLDING_SHORT -> TAKEOFF_CLEAR -> AIRBORNE_HANDOFF
   - Rejection of invalid phase skips (InvalidTransitionError)
   - Bilingual voice readback verification (English and Indonesian phraseology)
4. ATIS generation and phonetic letter cycle engine:
   - Initial ATIS generation for WAHI (Runway 11 headwind alignment)
   - Weather shift evaluation, runway change to RW29, and phonetic letter advancement

Runnable via:
  pytest tests/e2e_verification.py -v
  python tests/e2e_verification.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import struct
import sys
import time
from pathlib import Path

import pytest

# Ensure root directory, gateway/src, and scripts are on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
GATEWAY_SRC = ROOT_DIR / "gateway" / "src"
SCRIPTS_DIR = ROOT_DIR / "scripts"

for p in (ROOT_DIR, GATEWAY_SRC, SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from fastapi.testclient import TestClient

# Gateway imports
from server import app, get_gemini_client, safe_load_airport
from live.gemini_client import MockGeminiLiveClient
from atc.state_machine import FlightSession, FlightStateMachine, FlightPhase, InvalidTransitionError
from atc.readback import verify_readback
from atis.state import TelemetryWeather, AtisState, advance_letter
from atis.generator import create_initial_atis, evaluate_weather_update, generate_atis_text
from navdata.models import AirportInfo, Runway, RunwayList, FacilityDict
from navdata.atc_parser import get_facility_by_freq

# Scripts imports
from mock_xplane_sender import (
    XPlaneSnapshot,
    MockXPlaneSender,
    build_rref_packet,
    parse_rref_packet,
    parse_dref_packet,
    IDX_COM1_FREQ,
    IDX_COM2_FREQ,
    IDX_AUDIO_COM_SELECTION,
    IDX_LATITUDE,
    IDX_LONGITUDE,
    IDX_ELEVATION,
    IDX_Y_AGL,
    IDX_ON_GROUND,
    IDX_TRANSPONDER_CODE,
    IDX_BAROMETER_PILOT,
    IDX_GROUNDSPEED,
    IDX_WIND_SPEED,
    IDX_WIND_DIR,
    DREF_ATC_VOLUME_RATIO,
)
import websockets
from mock_atc_dialogue import MockAtcDialogueClient, generate_synthetic_pcm


# ==============================================================================
# 1. UDP Binary Serialization, Parsing & Mock Sender Tests
# ==============================================================================

class TestUdpBinaryProtocol:
    """Verifies X-Plane 12 UDP binary packet builders, parsers, and mute commands."""

    def test_rref_packet_encoding_and_decoding_13_records(self):
        """
        Verify all 13 datarefs matching client/src-tauri/src/xplane/mod.rs
        are accurately packed and unpacked with 6-byte header 'RREF,\\0'.
        """
        snapshot = XPlaneSnapshot(
            com1_hz=121650000.0,
            com2_hz=118200000.0,
            active_radio_code=6.0,
            latitude=-7.9042,
            longitude=110.0528,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=12.5,
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        )

        records = snapshot.to_records()
        assert len(records) == 13

        packet = build_rref_packet(records, header=b"RREF,\0")
        assert len(packet) == 6 + 13 * 8  # 110 bytes total
        assert packet[:6] == b"RREF,\0"

        parsed = parse_rref_packet(packet)
        assert len(parsed) == 13

        records_map = dict(parsed)
        assert records_map[IDX_COM1_FREQ] == pytest.approx(121650000.0, abs=1.0)
        assert records_map[IDX_COM2_FREQ] == pytest.approx(118200000.0, abs=1.0)
        assert records_map[IDX_AUDIO_COM_SELECTION] == pytest.approx(6.0, abs=0.01)
        assert records_map[IDX_LATITUDE] == pytest.approx(-7.9042, abs=1e-4)
        assert records_map[IDX_LONGITUDE] == pytest.approx(110.0528, abs=1e-4)
        assert records_map[IDX_ELEVATION] == pytest.approx(7.3, abs=0.1)
        assert records_map[IDX_Y_AGL] == pytest.approx(0.0, abs=0.1)
        assert records_map[IDX_ON_GROUND] == pytest.approx(1.0, abs=0.01)
        assert records_map[IDX_TRANSPONDER_CODE] == pytest.approx(5201.0, abs=0.1)
        assert records_map[IDX_BAROMETER_PILOT] == pytest.approx(29.85, abs=0.01)
        assert records_map[IDX_GROUNDSPEED] == pytest.approx(12.5, abs=0.1)
        assert records_map[IDX_WIND_SPEED] == pytest.approx(7.0, abs=0.1)
        assert records_map[IDX_WIND_DIR] == pytest.approx(100.0, abs=0.1)

    def test_rref_packet_5_byte_header_support(self):
        """Verify parser also handles standard 5-byte 'RREF\\0' header without corruption."""
        sample_records = [(1, 118200000.0), (4, -7.9042)]
        payload = bytearray(b"RREF\0")
        for idx, val in sample_records:
            payload.extend(struct.pack("<if", idx, val))

        parsed = parse_rref_packet(bytes(payload))
        assert len(parsed) == 2
        assert parsed[0] == (1, pytest.approx(118200000.0, abs=1.0))
        assert parsed[1] == (4, pytest.approx(-7.9042, abs=1e-4))

    def test_dref_mute_packet_parsing(self):
        """
        Verify DREF parser extracts volume ratio 0.0 and dataref string
        matching client/src-tauri/src/xplane/sender.rs.
        """
        value = 0.0
        dref_name = DREF_ATC_VOLUME_RATIO
        payload = bytearray(b"DREF\0")
        payload.extend(struct.pack("<f", value))
        name_bytes = dref_name.encode("ascii")
        payload.extend(name_bytes + b"\x00" * (500 - len(name_bytes)))

        res = parse_dref_packet(bytes(payload))
        assert res is not None
        parsed_val, parsed_name = res
        assert parsed_val == pytest.approx(0.0, abs=1e-4)
        assert parsed_name == DREF_ATC_VOLUME_RATIO

    def test_mock_xplane_sender_socket_and_mute_reception(self):
        """
        End-to-end socket test: MockXPlaneSender binds to UDP port,
        a simulated client sends ATC volume mute DREF packet,
        and MockXPlaneSender verifies it and transmits back an RREF telemetry packet.
        """
        mock_server = MockXPlaneSender(
            listen_host="127.0.0.1",
            listen_port=49152,  # Ephemeral high port for testing
            rate_hz=10.0,
        )
        mock_server.start_socket()

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client_sock.settimeout(2.0)

        try:
            # 1. Client sends DREF mute packet (volume = 0.0)
            mute_packet = bytearray(b"DREF\0")
            mute_packet.extend(struct.pack("<f", 0.0))
            name_bytes = DREF_ATC_VOLUME_RATIO.encode("ascii")
            mute_packet.extend(name_bytes + b"\x00" * (500 - len(name_bytes)))
            client_sock.sendto(bytes(mute_packet), ("127.0.0.1", 49152))

            # 2. Server polls incoming packets
            time.sleep(0.05)
            read_count = mock_server.poll_incoming()
            assert read_count >= 1
            assert mock_server.mute_command_received is True
            assert mock_server.last_mute_value == pytest.approx(0.0, abs=1e-4)
            assert mock_server.known_client_addr is not None

            # 3. Server sends RREF snapshot back to discovered client
            snapshot = XPlaneSnapshot(
                com1_hz=121650000.0,
                latitude=-7.9042,
                squawk=5201.0,
            )
            sent = mock_server.send_snapshot(snapshot)
            assert sent is True
            assert mock_server.packets_sent == 1

            # 4. Client receives RREF packet and validates
            data, _ = client_sock.recvfrom(2048)
            records = parse_rref_packet(data)
            assert len(records) == 13
            rec_map = dict(records)
            assert rec_map[IDX_COM1_FREQ] == pytest.approx(121650000.0, abs=1.0)
            assert rec_map[IDX_TRANSPONDER_CODE] == pytest.approx(5201.0, abs=0.1)

        finally:
            client_sock.close()
            mock_server.close()


# ==============================================================================
# 2. Gateway WebSocket (/ws/atc) Full-Duplex Tests
# ==============================================================================

@pytest.fixture
def mock_gemini():
    """Provides a fresh MockGeminiLiveClient overridden in app dependencies."""
    client = MockGeminiLiveClient()
    app.dependency_overrides[get_gemini_client] = lambda: client
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client(mock_gemini):
    """Provides FastAPI TestClient connected to gateway."""
    return TestClient(app)


class TestGatewayWebSocket:
    """Verifies Gateway /ws/atc telemetry, frequency validation, PTT, and audio relay."""

    def test_connection_handshake(self, client):
        """Verify initial WebSocket connection receives CONNECTED status for WAHI."""
        with client.websocket_connect("/ws/atc") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "status"
            assert msg["action"] == "CONNECTED"
            assert msg["airport"] == "WAHI"
            assert msg["callsign"] == "GIA123"

    def test_frequency_validation_dead_air_and_tuning(self, client):
        """
        Verify:
        - Unmonitored frequency (123.450 MHz) receives DEAD_AIR.
        - PTT press on unmonitored frequency receives DEAD_AIR error.
        - Tuning WAHI Ground (121.650 MHz) receives TUNED status with role 'GND'.
        - Tuning WAHI Tower (118.200 MHz) receives TUNED status with role 'TWR'.
        """
        with client.websocket_connect("/ws/atc") as ws:
            ws.receive_json()  # Consume CONNECTED

            # 1. Unmonitored frequency: 123.450 MHz
            ws.send_json({
                "type": "telemetry",
                "data": {
                    "com1_hz": 123450000,
                    "frequency": 123.450,
                    "active_radio": "COM1",
                },
            })
            dead_air_msg = ws.receive_json()
            assert dead_air_msg["type"] == "status"
            assert dead_air_msg["action"] == "DEAD_AIR"
            assert "unmonitored" in dead_air_msg["message"].lower()

            # PTT press on unmonitored frequency
            ws.send_json({"type": "ptt", "state": "pressed", "radio": "COM1"})
            ptt_dead_msg = ws.receive_json()
            assert ptt_dead_msg["type"] == "status"
            assert ptt_dead_msg["action"] == "DEAD_AIR"

            # 2. Valid WAHI Ground: 121.650 MHz
            ws.send_json({
                "type": "telemetry",
                "data": {
                    "com1_hz": 121650000,
                    "frequency": 121.650,
                    "active_radio": "COM1",
                },
            })
            gnd_msg = ws.receive_json()
            assert gnd_msg["type"] == "status"
            assert gnd_msg["action"] == "TUNED"
            assert gnd_msg["role"] == "GND"
            assert gnd_msg["frequency_hz"] == 121650000

            # 3. Valid WAHI Tower: 118.200 MHz
            ws.send_json({
                "type": "telemetry",
                "data": {
                    "com1_hz": 118200000,
                    "frequency": 118.200,
                    "active_radio": "COM1",
                },
            })
            twr_msg = ws.receive_json()
            assert twr_msg["type"] == "status"
            assert twr_msg["action"] == "TUNED"
            assert twr_msg["role"] == "TWR"
            assert twr_msg["frequency_hz"] == 118200000

    @pytest.mark.asyncio
    async def test_ptt_lifecycle_and_mock_gemini_relay(self, client, mock_gemini):
        """
        Verify:
        - PTT press transitions to TRANSMITTING.
        - Audio chunk is relayed to Gemini Live client.
        - PTT release triggers send_end_of_turn and transitions to IDLE.
        - Mock Gemini model responses (transcript and audio) stream back to WebSocket client.
        """
        with client.websocket_connect("/ws/atc") as ws:
            ws.receive_json()  # Consume CONNECTED

            # Tune Ground
            ws.send_json({
                "type": "telemetry",
                "data": {"com1_hz": 121650000, "active_radio": "COM1"},
            })
            ws.receive_json()  # Consume TUNED

            # PTT Press
            ws.send_json({"type": "ptt", "state": "pressed", "radio": "COM1"})
            tx_msg = ws.receive_json()
            assert tx_msg["type"] == "status"
            assert tx_msg["action"] == "TRANSMITTING"
            assert tx_msg["radio"] == "COM1"

            # Stream audio chunk
            pcm = generate_synthetic_pcm(duration_sec=0.2, sample_rate=24000)
            ws.send_bytes(pcm)

            # Let async loop handle audio chunk and initiate Gemini session
            time.sleep(0.1)
            assert mock_gemini.is_connected is True
            assert len(mock_gemini.sent_audio_chunks) >= 1

            # Simulate Gemini Live ATC transcript response
            atc_response_text = "Garuda 123, cleared to Jakarta runway 11, climb 11000, squawk 5201."
            await mock_gemini.push_mock_response(text=atc_response_text)
            transcript_frame = ws.receive_json()
            assert transcript_frame["type"] == "transcript"
            assert transcript_frame["role"] == "atc"
            assert transcript_frame["text"] == atc_response_text

            # Simulate Gemini Live ATC synthesized audio response
            atc_audio_bytes = b"SIMULATED_ATC_VHF_AUDIO_BYTES_12345"
            await mock_gemini.push_mock_response(audio=atc_audio_bytes)
            received_audio = ws.receive_bytes()
            assert received_audio == atc_audio_bytes

            # PTT Release
            ws.send_json({"type": "ptt", "state": "released"})
            idle_msg = ws.receive_json()
            assert idle_msg["type"] == "status"
            assert idle_msg["action"] == "IDLE"
            assert mock_gemini.end_of_turn_count >= 1

    @pytest.mark.asyncio
    async def test_mock_atc_dialogue_client_e2e_communication(self):
        """
        Verify MockAtcDialogueClient connects to gateway WebSocket, starts background
        _listen_loop without AttributeError on websockets v14+, ingests telemetry,
        handles PTT voice transmission, receives transcripts and audio, and disconnects cleanly.
        """
        received_payloads: list[dict] = []
        received_audio_chunks: list[bytes] = []

        async def mock_gateway_handler(ws):
            # Send initial CONNECTED handshake frame
            await ws.send(json.dumps({
                "type": "status",
                "action": "CONNECTED",
                "airport": "WAHI",
                "callsign": "GIA123",
                "facility": "WAHI Ground",
            }))

            async for message in ws:
                if isinstance(message, bytes):
                    received_audio_chunks.append(message)
                else:
                    data = json.loads(message)
                    received_payloads.append(data)
                    msg_type = data.get("type")
                    if msg_type == "telemetry":
                        await ws.send(json.dumps({
                            "type": "status",
                            "action": "TUNED",
                            "facility": "WAHI Ground",
                            "role": "GND",
                            "frequency_hz": 121650000,
                        }))
                    elif msg_type == "ptt":
                        state = data.get("state")
                        if state == "pressed":
                            await ws.send(json.dumps({
                                "type": "status",
                                "action": "TRANSMITTING",
                                "radio": data.get("radio", "COM1"),
                            }))
                        else:
                            await ws.send(json.dumps({
                                "type": "status",
                                "action": "IDLE",
                            }))
                            # Relay simulated ATC response and audio
                            await ws.send(json.dumps({
                                "type": "transcript",
                                "role": "atc",
                                "text": "Garuda 123, pushback approved.",
                            }))
                            await ws.send(b"MOCK_ATC_AUDIO_BYTES_24K")

        server = await websockets.serve(mock_gateway_handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        client = MockAtcDialogueClient(
            url=f"ws://127.0.0.1:{port}",
            callsign="GIA123",
            aircraft_type="A320",
            step_delay=0.05,
        )

        try:
            # 1. Connect & verify handshake
            handshake = await client.connect()
            assert handshake["action"] == "CONNECTED"
            assert handshake["airport"] == "WAHI"

            # 2. Telemetry ingestion
            await client.send_telemetry(com1_hz=121650000, active_radio="COM1")
            await asyncio.sleep(0.05)
            assert any(p.get("type") == "telemetry" for p in received_payloads)
            assert any(m.get("action") == "TUNED" for m in client.received_messages)

            # 3. Voice transmission (PTT pressed, audio streaming, PTT released)
            await client.transmit_voice("Ground, Garuda 123, request pushback.", radio="COM1", duration_sec=0.15)
            await asyncio.sleep(0.08)

            assert any(p.get("type") == "ptt" and p.get("state") == "pressed" for p in received_payloads)
            assert len(received_audio_chunks) >= 3
            assert any(p.get("type") == "ptt" and p.get("state") == "released" for p in received_payloads)

            # 4. Verify client received ATC transcript and binary audio
            assert any(
                m.get("type") == "transcript" and "pushback approved" in m.get("text", "")
                for m in client.received_messages
            )
            assert b"MOCK_ATC_AUDIO_BYTES_24K" in client.received_audio_bytes

        finally:
            await client.close()
            server.close()
            await server.wait_closed()


# ==============================================================================
# 3. Departure Flight Phase Lifecycle & Bilingual Readback Verification
# ==============================================================================

class TestFlightLifecycleAndReadback:
    """Verifies state machine transitions and bilingual readback verification."""

    def test_full_departure_lifecycle_progression(self):
        """
        Verify sequential flight phase transitions:
        APRON_CLEARANCE -> PUSHBACK_START -> TAXI_TO_RUNWAY -> HOLDING_SHORT -> TAKEOFF_CLEAR -> AIRBORNE_HANDOFF
        """
        session = FlightSession(
            callsign="GIA123",
            aircraft_type="A320",
            current_phase=FlightPhase.APRON_CLEARANCE,
            assigned_runway="11",
            assigned_squawk="5201",
            target_alt_ft=11000,
        )
        sm = FlightStateMachine(session)

        # 1. APRON_CLEARANCE -> PUSHBACK_START
        assert sm.current_phase == FlightPhase.APRON_CLEARANCE
        assert sm.expected_facility_role == "DEL"
        assert sm.can_transition_to(FlightPhase.PUSHBACK_START) is True
        assert sm.can_transition_to(FlightPhase.TAKEOFF_CLEAR) is False  # Cannot skip

        sm.advance()
        assert sm.current_phase == FlightPhase.PUSHBACK_START
        assert sm.expected_facility_role == "GND"

        # 2. PUSHBACK_START -> TAXI_TO_RUNWAY
        sm.advance()
        assert sm.current_phase == FlightPhase.TAXI_TO_RUNWAY
        assert sm.expected_facility_role == "GND"

        # 3. TAXI_TO_RUNWAY -> HOLDING_SHORT
        sm.advance()
        assert sm.current_phase == FlightPhase.HOLDING_SHORT
        assert sm.expected_facility_role == "TWR"

        # 4. HOLDING_SHORT -> TAKEOFF_CLEAR
        sm.advance()
        assert sm.current_phase == FlightPhase.TAKEOFF_CLEAR
        assert sm.expected_facility_role == "TWR"

        # 5. TAKEOFF_CLEAR -> AIRBORNE_HANDOFF
        sm.advance()
        assert sm.current_phase == FlightPhase.AIRBORNE_HANDOFF
        assert sm.expected_facility_role == "DEP"

        # Terminal state: cannot advance further
        with pytest.raises(InvalidTransitionError):
            sm.advance()

    def test_invalid_skip_transitions_rejected(self):
        """Verify illegal phase skips raise InvalidTransitionError."""
        session = FlightSession(callsign="GIA123", current_phase=FlightPhase.APRON_CLEARANCE)
        sm = FlightStateMachine(session)

        with pytest.raises(InvalidTransitionError):
            sm.transition_to(FlightPhase.HOLDING_SHORT)

        with pytest.raises(InvalidTransitionError):
            sm.transition_to(FlightPhase.TAKEOFF_CLEAR)

    def test_english_clearance_readback_verification(self):
        """
        Verify English clearance readback accurately matches runway,
        altitude, and squawk, advancing the state machine.
        """
        session = FlightSession(callsign="GIA123", current_phase=FlightPhase.APRON_CLEARANCE)
        sm = FlightStateMachine(session)

        pilot_readback = "Garuda 123, cleared to Jakarta, runway 11, climb and maintain 11000 feet, squawk 5201."
        expected = {
            "runway": "11",
            "altitude": 11000,
            "squawk": "5201",
        }

        valid, result = sm.process_clearance_readback(pilot_readback, expected)
        assert valid is True
        assert result.is_valid is True
        assert sm.current_phase == FlightPhase.PUSHBACK_START

    def test_indonesian_bilingual_readback_verification(self):
        """
        Verify Indonesian voice readbacks for pushback, taxi, and takeoff
        advance their corresponding flight phases.
        """
        session = FlightSession(callsign="GIA123", current_phase=FlightPhase.PUSHBACK_START)
        sm = FlightStateMachine(session)

        # 1. Indonesian Pushback readback: "landasan satu satu" (runway 11)
        pushback_text = "Disetujui pushback hadap timur landasan satu satu, Garuda 123."
        valid, res = sm.process_clearance_readback(pushback_text, {"runway": "11"})
        assert valid is True
        assert sm.current_phase == FlightPhase.TAXI_TO_RUNWAY

        # 2. Indonesian Taxi readback
        taxi_text = "Taksi ke holding point landasan satu satu lewat Alfa, Garuda satu dua tiga."
        valid, res = sm.process_clearance_readback(taxi_text, {"runway": "11"})
        assert valid is True
        assert sm.current_phase == FlightPhase.HOLDING_SHORT

        # 3. Indonesian Takeoff clearance readback
        takeoff_text = "Landasan satu satu diizinkan lepas landas, Garuda 123."
        valid, res = sm.process_clearance_readback(takeoff_text, {"runway": "11"})
        assert valid is True
        assert sm.current_phase == FlightPhase.TAKEOFF_CLEAR

    def test_incorrect_readback_rejected(self):
        """Verify mismatched readback items (e.g. incorrect runway or squawk) are rejected."""
        session = FlightSession(callsign="GIA123", current_phase=FlightPhase.APRON_CLEARANCE)
        sm = FlightStateMachine(session)

        # Pilot mistakenly reads back runway 29 instead of 11
        mistaken_text = "Garuda 123, cleared runway 29, climb 11000, squawk 5201."
        expected = {
            "runway": "11",
            "altitude": 11000,
            "squawk": "5201",
        }

        valid, result = sm.process_clearance_readback(mistaken_text, expected)
        assert valid is False
        assert result.is_valid is False
        assert len(result.errors) > 0
        # Phase MUST NOT advance
        assert sm.current_phase == FlightPhase.APRON_CLEARANCE


# ==============================================================================
# 4. ATIS Generation & Phonetic Letter Cycle Engine Tests
# ==============================================================================

class TestAtisCycleAndPhoneticProgression:
    """Verifies ATIS generation, headwind runway selection, and letter cycling."""

    @pytest.fixture
    def wahi_airport_fixture(self):
        """Constructs synthetic WAHI airport navigation model."""
        rw11 = Runway(ident="11", heading=110.0, elevation_ft=24)
        rw29 = Runway(ident="29", heading=290.0, elevation_ft=24)
        return AirportInfo(
            icao="WAHI",
            name="Yogyakarta International Airport",
            transition_alt=11000,
            runways=RunwayList([rw11, rw29]),
            facilities={},
        )

    def test_initial_atis_generation_and_headwind_runway_11(self, wahi_airport_fixture):
        """
        Verify wind 100@7 kts selects Runway 11 and generates standard ICAO ATIS text
        with phonetic information letter.
        """
        weather = TelemetryWeather(
            wind_deg=100,
            wind_kts=7,
            visibility_m=10000,
            clouds="few 3500 feet",
            temp_c=29,
            dewpoint_c=23,
            qnh_hpa=1011.0,
            zulu_sec=25200,  # 07:00 UTC
        )

        atis = create_initial_atis(wahi_airport_fixture, weather, letter="CHARLIE")
        assert atis.active_runway == "11"
        assert atis.letter == "CHARLIE"
        assert atis.letter_code == "C"
        assert atis.phonetic_letter == "CHARLIE"

        text = generate_atis_text(
            airport=wahi_airport_fixture,
            letter="CHARLIE",
            weather=weather,
            zulu_sec=25200,
            active_runway="11",
        )
        assert "Yogyakarta International Airport Information CHARLIE" in text
        assert "Runway in use 11" in text
        assert "Wind 100 degrees 7 knots" in text
        assert "QNH 1011" in text
        assert "Advise controller on initial contact you have information CHARLIE" in text

    def test_significant_weather_shift_runway_change_and_letter_advancement(self, wahi_airport_fixture):
        """
        Verify wind shift to 290@14 kts triggers ATIS update:
        - Active runway switches from 11 to 29
        - Phonetic letter advances from CHARLIE to DELTA
        - New broadcast text references Information DELTA and Runway 29
        """
        initial_weather = TelemetryWeather(
            wind_deg=100,
            wind_kts=7,
            qnh_hpa=1011.0,
            temp_c=29,
            zulu_sec=25200,
        )
        current_atis = create_initial_atis(wahi_airport_fixture, initial_weather, letter="CHARLIE")
        assert current_atis.active_runway == "11"
        assert current_atis.letter == "CHARLIE"
        assert current_atis.letter_code == "C"
        assert current_atis.phonetic_letter == "CHARLIE"

        # Shift wind to 290 degrees (190 degree shift, favoring RW29)
        shifted_weather = TelemetryWeather(
            wind_deg=290,
            wind_kts=14,
            qnh_hpa=1012.0,
            temp_c=28,
            zulu_sec=28800,  # 08:00 UTC
        )

        updated, new_atis = evaluate_weather_update(current_atis, wahi_airport_fixture, shifted_weather)
        assert updated is True
        assert new_atis.active_runway == "29"
        assert new_atis.letter == "DELTA"
        assert new_atis.letter_code == "D"
        assert new_atis.phonetic_letter == "DELTA"
        assert "Information DELTA" in new_atis.text
        assert "Runway in use 29" in new_atis.text
        assert "Wind 290 degrees 14 knots" in new_atis.text


# ==============================================================================
# Standalone CLI entrypoint
# ==============================================================================

if __name__ == "__main__":
    ret = pytest.main(["-v", __file__])
    sys.exit(ret)
