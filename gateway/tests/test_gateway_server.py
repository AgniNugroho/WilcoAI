import base64
import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from live.gemini_client import MockGeminiLiveClient
from server import app, get_gemini_client


@pytest.fixture
def mock_gemini():
    """Provides a fresh MockGeminiLiveClient instance."""
    client = MockGeminiLiveClient()
    app.dependency_overrides[get_gemini_client] = lambda: client
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def client(mock_gemini):
    """Provides FastAPI TestClient with mocked Gemini client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Verify /health endpoint returns 200 OK and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "wilcoai-gateway" in data["service"]


def test_websocket_connection(client, mock_gemini):
    """Verify WebSocket /ws/atc connects and receives initial connection handshake."""
    with client.websocket_connect("/ws/atc") as ws:
        init_frame = ws.receive_json()
        assert init_frame["type"] == "status"
        assert init_frame["action"] == "CONNECTED"
        assert init_frame["airport"] == "WAHI"


def test_valid_frequency_and_audio_forwarded_to_gemini(client, mock_gemini):
    """
    Verify sending a valid facility frequency (118.200 MHz / WAHI Tower)
    tunes successfully and forwards incoming audio to Gemini Live with context injection.
    """
    with client.websocket_connect("/ws/atc") as ws:
        init_msg = ws.receive_json()
        assert init_msg["type"] == "status"

        # 1. Send telemetry with valid frequency 118.200 MHz (WAHI Tower)
        telemetry_frame = {
            "type": "telemetry",
            "data": {
                "callsign": "GIA123",
                "frequency": 118.200,
                "active_radio": "COM1",
            },
        }
        ws.send_json(telemetry_frame)

        status_msg = ws.receive_json()
        assert status_msg["type"] == "status"
        assert status_msg["action"] == "TUNED"
        assert "Tower" in status_msg["facility"]
        assert status_msg["frequency_hz"] == 118200000

        # 2. Send audio chunk
        pcm_chunk = b"\x00\x01\x02\x03\x04\x05"
        ws.send_bytes(pcm_chunk)

        # Allow Starlette background test thread to process async audio frame
        import time
        time.sleep(0.1)

        # 3. Assert mock Gemini received context injection and audio chunk
        assert len(mock_gemini.sent_contexts) >= 1
        injected_context = mock_gemini.sent_contexts[-1]
        assert "WAHI" in injected_context
        assert "GIA123" in injected_context
        assert "Tower" in injected_context

        assert len(mock_gemini.sent_audio_chunks) >= 1
        assert mock_gemini.sent_audio_chunks[-1] == pcm_chunk


def test_unmonitored_frequency_triggers_dead_air(client, mock_gemini):
    """
    Verify sending an unmonitored frequency (120.000 MHz)
    triggers DEAD_AIR status and discards audio without sending to Gemini.
    """
    with client.websocket_connect("/ws/atc") as ws:
        ws.receive_json()  # Consume initial CONNECTED frame

        # Send telemetry frame with unmonitored frequency 120.000 MHz
        telemetry_frame = {
            "type": "telemetry",
            "data": {
                "callsign": "GIA123",
                "frequency": 120.000,
                "active_radio": "COM1",
            },
        }
        ws.send_json(telemetry_frame)

        # Assert gateway responds with DEAD_AIR action
        dead_air_msg = ws.receive_json()
        assert dead_air_msg["type"] == "status"
        assert dead_air_msg["action"] == "DEAD_AIR"
        assert "unmonitored" in dead_air_msg["message"].lower()

        # Send audio chunk on invalid frequency
        initial_chunks_count = len(mock_gemini.sent_audio_chunks)
        ws.send_bytes(b"\x99\x88\x77\x66")

        # Discard message response
        discard_msg = ws.receive_json()
        assert discard_msg["type"] == "status"
        assert discard_msg["action"] == "DEAD_AIR"

        # Assert audio was NOT forwarded to Gemini
        assert len(mock_gemini.sent_audio_chunks) == initial_chunks_count


def test_json_audio_frame_and_base64_support(client, mock_gemini):
    """Verify audio chunks sent as JSON base64 payloads are decoded and forwarded."""
    with client.websocket_connect("/ws/atc") as ws:
        ws.receive_json()

        # Tune to Tower
        ws.send_json({"type": "telemetry", "data": {"com1_hz": 118200000, "active_radio": "COM1"}})
        ws.receive_json()  # TUNED

        pcm_data = b"raw_pcm_audio_bytes_1234"
        b64_audio = base64.b64encode(pcm_data).decode()
        ws.send_json({"type": "audio", "data": b64_audio})

        import time
        time.sleep(0.1)

        assert len(mock_gemini.sent_audio_chunks) >= 1
        assert mock_gemini.sent_audio_chunks[-1] == pcm_data


def test_ptt_keying_and_radio_switching(client, mock_gemini):
    """Verify PTT pressed/released events and COM1/COM2 switching."""
    with client.websocket_connect("/ws/atc") as ws:
        ws.receive_json()

        # Send telemetry defining COM1 (Tower 118.2) and COM2 (Ground 121.65)
        ws.send_json({
            "type": "telemetry",
            "data": {
                "com1_hz": 118200000,
                "com2_hz": 121650000,
                "active_radio": "COM1",
            },
        })
        tune1 = ws.receive_json()
        assert tune1["action"] == "TUNED"
        assert "Tower" in tune1["facility"]

        # Press PTT on COM2 (switching active radio to Ground)
        ws.send_json({"type": "ptt", "state": "pressed", "radio": "COM2"})
        ptt_resp = ws.receive_json()
        assert ptt_resp["type"] == "status"
        assert ptt_resp["action"] == "TRANSMITTING"
        assert ptt_resp["radio"] == "COM2"
        assert "Ground" in ptt_resp["facility"]

        # Release PTT
        ws.send_json({"type": "ptt", "state": "released"})
        rel_resp = ws.receive_json()
        assert rel_resp["type"] == "status"
        assert rel_resp["action"] == "IDLE"


@pytest.mark.asyncio
async def test_gemini_relay_transcript_and_audio(client, mock_gemini):
    """Verify audio chunks and transcripts emitted by Gemini Live are relayed to client."""
    with client.websocket_connect("/ws/atc") as ws:
        ws.receive_json()  # CONNECTED

        # Tune to Tower and send audio to activate Gemini session
        ws.send_json({"type": "telemetry", "data": {"frequency": 118.200}})
        ws.receive_json()  # TUNED
        ws.send_bytes(b"\x01\x02\x03")

        # Push mock transcript and audio from Gemini Live
        await mock_gemini.push_mock_response(text="Garuda 123, wind 100 at 7 knots, runway 11 cleared for takeoff.")
        transcript_frame = ws.receive_json()
        assert transcript_frame["type"] == "transcript"
        assert transcript_frame["role"] == "atc"
        assert "cleared for takeoff" in transcript_frame["text"]

        # Push audio chunk from Gemini
        mock_audio = b"\x10\x20\x30\x40\x50"
        await mock_gemini.push_mock_response(audio=mock_audio)
        received_audio = ws.receive_bytes()
        assert received_audio == mock_audio


def test_full_gateway_atc_workflow_step_by_step(client, mock_gemini):
    """
    Executes the exact end-to-end sequence specified in Task 5 plan:
    1. Connect client mock WebSocket.
    2. Send telemetry frame with frequency 118.200 MHz (WAHI Tower).
    3. Send audio chunk.
    4. Assert that mock Gemini Live receives context injection frame and audio chunk.
    5. Send telemetry frame with invalid frequency 120.000 MHz.
    6. Assert that gateway responds with DEAD_AIR action without forwarding to Gemini.
    """
    with client.websocket_connect("/ws/atc") as ws:
        init_frame = ws.receive_json()
        assert init_frame["action"] == "CONNECTED"

        # Step 2: Send telemetry frame with frequency 118.200 MHz
        ws.send_json({
            "type": "telemetry",
            "data": {
                "callsign": "GIA123",
                "frequency": 118.200,
                "active_radio": "COM1",
            },
        })
        tune_resp = ws.receive_json()
        assert tune_resp["action"] == "TUNED"
        assert "Tower" in tune_resp["facility"]

        # Step 3: Send audio chunk
        audio_payload = b"\x11\x22\x33\x44"
        ws.send_bytes(audio_payload)

        import time
        time.sleep(0.1)

        # Step 4: Assert that mock Gemini Live receives context injection frame and audio chunk
        assert len(mock_gemini.sent_contexts) >= 1
        assert "WAHI" in mock_gemini.sent_contexts[-1]
        assert len(mock_gemini.sent_audio_chunks) == 1
        assert mock_gemini.sent_audio_chunks[0] == audio_payload

        # Step 5: Send telemetry frame with invalid frequency 120.000 MHz
        ws.send_json({
            "type": "telemetry",
            "data": {
                "frequency": 120.000,
                "active_radio": "COM1",
            },
        })

        # Step 6: Assert that gateway responds with DEAD_AIR action without forwarding to Gemini
        dead_air_resp = ws.receive_json()
        assert dead_air_resp["action"] == "DEAD_AIR"

        # Discard verification: audio chunk sent on invalid frequency is not forwarded
        ws.send_bytes(b"\x55\x66\x77\x88")
        discard_resp = ws.receive_json()
        assert discard_resp["action"] == "DEAD_AIR"
        assert len(mock_gemini.sent_audio_chunks) == 1


def test_weather_telemetry_updates_atis(client, mock_gemini):
    """Verify incoming telemetry weather updates trigger ATIS evaluation and context updates."""
    with client.websocket_connect("/ws/atc") as ws:
        init_frame = ws.receive_json()
        assert init_frame["action"] == "CONNECTED"

        # Send telemetry with significant QNH shift (>= 1.0 hPa) to trigger ATIS update
        ws.send_json({
            "type": "telemetry",
            "data": {
                "frequency": 118.200,
                "wind_deg": 280,
                "wind_kts": 14,
                "qnh_hpa": 1008.0,
                "zulu_sec": 30000,
            },
        })
        status_msg = ws.receive_json()
        assert status_msg["action"] == "TUNED"

        # Send audio chunk
        ws.send_bytes(b"\xaa\xbb\xcc")
        import time
        time.sleep(0.1)

        # Context prompt should reflect the updated QNH and active runway 29
        last_context = mock_gemini.sent_contexts[-1]
        assert "1008 hPa" in last_context or "1008" in last_context

