from __future__ import annotations
import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Optional, Union, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import JSONResponse

try:
    from config import Settings, get_settings
    from live.gemini_client import GeminiLiveClient, MockGeminiLiveClient
    from atc.state_machine import FlightSession, FlightPhase
    from atc.prompt_builder import build_system_prompt
    from navdata.models import AirportInfo, Runway, RunwayList, FacilityDict
    from navdata.atc_parser import (
        DEFAULT_AIRPORT_FACILITIES,
        DEFAULT_AIRPORT_NAMES,
        get_facility_by_freq,
        parse_freq_to_hz,
    )
    from navdata import load_airport
    from atis.state import TelemetryWeather, AtisState
    from atis.generator import create_initial_atis, evaluate_weather_update
except (ImportError, ValueError):
    from .config import Settings, get_settings
    from .live.gemini_client import GeminiLiveClient, MockGeminiLiveClient
    from .atc.state_machine import FlightSession, FlightPhase
    from .atc.prompt_builder import build_system_prompt
    from .navdata.models import AirportInfo, Runway, RunwayList, FacilityDict
    from .navdata.atc_parser import (
        DEFAULT_AIRPORT_FACILITIES,
        DEFAULT_AIRPORT_NAMES,
        get_facility_by_freq,
        parse_freq_to_hz,
    )
    from .navdata import load_airport
    from .atis.state import TelemetryWeather, AtisState
    from .atis.generator import create_initial_atis, evaluate_weather_update

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Wilco AI Gateway",
    description="FastAPI WebSocket Gateway for AI ATC and Gemini Multimodal Live API",
    version="0.1.0",
)


def get_gemini_client() -> GeminiLiveClient:
    """Dependency provider for Gemini Live client session."""
    cfg = get_settings()
    return GeminiLiveClient(api_key=cfg.GEMINI_API_KEY, model=cfg.MODEL_NAME)


def safe_load_airport(custom_data_path: Union[str, Path], icao: str = "WAHI") -> AirportInfo:
    """
    Load airport navigation data with graceful fallback to regional defaults
    if CIFP data directory is unavailable.
    """
    target_icao = "WAHI" if icao.strip().upper() == "WARJ" else icao.strip().upper()
    try:
        return load_airport(custom_data_path, target_icao)
    except Exception as exc:
        logger.warning(
            f"CIFP navigation data not found in '{custom_data_path}' ({exc}). "
            f"Falling back to default regional profile for {target_icao}."
        )
        fac_defaults = DEFAULT_AIRPORT_FACILITIES.get(target_icao, {})
        facilities = FacilityDict()
        for k, v in fac_defaults.items():
            facilities[k] = v

        return AirportInfo(
            icao=target_icao,
            name=DEFAULT_AIRPORT_NAMES.get(target_icao, f"Airport {target_icao}"),
            transition_alt=11000,
            runways=RunwayList([
                Runway(ident="11", heading=110.0, elevation_ft=24),
                Runway(ident="29", heading=290.0, elevation_ft=24),
            ]),
            facilities=facilities,
        )


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint confirming gateway operational status."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "wilcoai-gateway",
            "version": "0.1.0",
        },
    )


@app.websocket("/ws/atc")
async def websocket_atc(
    websocket: WebSocket,
    gemini_client: GeminiLiveClient = Depends(get_gemini_client),
):
    """
    Full-duplex WebSocket gateway managing simulator telemetry ingestion,
    VHF frequency validation, push-to-talk state, and bidirectional audio streaming
    with the Gemini Multimodal Live API.
    """
    await websocket.accept()
    cfg = get_settings()

    airport = safe_load_airport(cfg.CUSTOM_DATA_PATH, cfg.DEFAULT_ICAO)
    initial_weather = TelemetryWeather(
        wind_deg=100,
        wind_kts=7,
        qnh_hpa=1013.25,
        temp_c=28,
        zulu_sec=25200,
    )
    atis_state = create_initial_atis(airport, initial_weather)
    flight_session = FlightSession(
        callsign="GIA123",
        aircraft_type="A320",
        current_phase=FlightPhase.APRON_CLEARANCE,
        assigned_runway=atis_state.active_runway,
        assigned_squawk="5201",
        target_alt_ft=11000,
        atis_letter=atis_state.letter_code,
    )

    active_radio = "COM1"
    com1_hz = 118200000  # Default WAHI Tower
    com2_hz = 121650000  # Default WAHI Ground

    current_facility = get_facility_by_freq(airport, com1_hz)
    is_frequency_valid = current_facility is not None
    if current_facility:
        flight_session.tuned_facility = current_facility.role

    # Initial connection handshake
    await websocket.send_json({
        "type": "status",
        "action": "CONNECTED",
        "airport": airport.icao,
        "callsign": flight_session.callsign,
        "active_radio": active_radio,
        "active_frequency_hz": com1_hz,
        "facility": current_facility.name if current_facility else None,
    })

    relay_task: Optional[asyncio.Task] = None
    last_injected_prompt: Optional[str] = None
    is_new_ptt_burst: bool = False

    async def relay_gemini_to_client():
        try:
            async for event in gemini_client.receive_stream():
                if event.get("type") == "audio" and "data" in event:
                    await websocket.send_bytes(event["data"])
                elif event.get("type") == "transcript":
                    await websocket.send_json(event)
                elif event.get("type") == "status":
                    await websocket.send_json(event)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Relay stream exception: {e}")

    async def handle_audio_payload(audio_bytes: bytes):
        nonlocal is_frequency_valid, flight_session, airport, atis_state, relay_task, last_injected_prompt, is_new_ptt_burst
        # Guard: Ignore empty audio chunks
        if not audio_bytes:
            return

        if not is_frequency_valid:
            return

        prompt = build_system_prompt(flight_session, airport, atis_state)
        if not gemini_client.is_connected:
            await gemini_client.connect(system_instruction=prompt)
            if relay_task is None or relay_task.done():
                relay_task = asyncio.create_task(relay_gemini_to_client())
            last_injected_prompt = prompt
            is_new_ptt_burst = False
        elif prompt != last_injected_prompt or is_new_ptt_burst:
            await gemini_client.send_text_context(prompt)
            last_injected_prompt = prompt
            is_new_ptt_burst = False

        await gemini_client.send_audio_chunk(audio_bytes)

    try:
        while True:
            message = await websocket.receive()

            if "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                except Exception:
                    continue

                msg_type = payload.get("type")

                if msg_type == "telemetry":
                    data = payload.get("data", payload)
                    if isinstance(data, dict):
                        if "callsign" in data:
                            flight_session.callsign = str(data["callsign"])
                        if "aircraft_type" in data:
                            flight_session.aircraft_type = str(data["aircraft_type"])
                        if "squawk" in data:
                            flight_session.assigned_squawk = str(data["squawk"])
                        if "active_radio" in data:
                            active_radio = str(data["active_radio"]).upper()

                        if "com1_hz" in data or "com1" in data:
                            raw_c1 = data.get("com1_hz") if data.get("com1_hz") is not None else data.get("com1")
                            if raw_c1 is not None:
                                com1_hz = parse_freq_to_hz(raw_c1)
                        if "com2_hz" in data or "com2" in data:
                            raw_c2 = data.get("com2_hz") if data.get("com2_hz") is not None else data.get("com2")
                            if raw_c2 is not None:
                                com2_hz = parse_freq_to_hz(raw_c2)

                        direct_freq = (
                            data.get("frequency")
                            or data.get("freq_hz")
                            or payload.get("frequency")
                            or payload.get("freq_hz")
                        )
                        if direct_freq is not None:
                            freq_parsed = parse_freq_to_hz(direct_freq)
                            if active_radio == "COM2":
                                com2_hz = freq_parsed
                            else:
                                com1_hz = freq_parsed

                        # Weather update evaluation
                        if any(k in data for k in ("wind_deg", "wind_dir", "wind_kts", "wind_speed", "qnh_hpa", "qnh_inhg")):
                            wind_d = data.get("wind_deg", data.get("wind_dir", initial_weather.wind_deg))
                            wind_s = data.get("wind_kts", data.get("wind_speed", initial_weather.wind_kts))
                            qnh_v = data.get("qnh_hpa", initial_weather.qnh_hpa)
                            if "qnh_inhg" in data and "qnh_hpa" not in data:
                                qnh_v = round(float(data["qnh_inhg"]) * 33.8639, 2)
                            tw = TelemetryWeather(
                                wind_deg=wind_d,
                                wind_kts=wind_s,
                                qnh_hpa=qnh_v,
                                visibility_m=data.get("visibility_m", initial_weather.visibility_m),
                                clouds=data.get("clouds", initial_weather.clouds),
                                temp_c=data.get("temp_c", initial_weather.temp_c),
                                zulu_sec=data.get("zulu_sec", initial_weather.zulu_sec),
                            )
                            updated, new_atis = evaluate_weather_update(atis_state, airport, tw)
                            if updated:
                                atis_state = new_atis
                                flight_session.atis_letter = atis_state.letter_code
                                flight_session.assigned_runway = atis_state.active_runway

                    # Determine active frequency and validate against airport facilities
                    active_freq_hz = com2_hz if active_radio == "COM2" else com1_hz
                    facility = get_facility_by_freq(airport, active_freq_hz)

                    if facility is not None:
                        is_frequency_valid = True
                        current_facility = facility
                        flight_session.tuned_facility = facility.role
                        await websocket.send_json({
                            "type": "status",
                            "action": "TUNED",
                            "facility": facility.name,
                            "role": facility.role,
                            "frequency_hz": facility.frequency_hz,
                            "active_radio": active_radio,
                            "message": f"Tuned to {facility.name} on {facility.frequency_mhz:.3f} MHz",
                        })
                    else:
                        is_frequency_valid = False
                        current_facility = None
                        flight_session.tuned_facility = None
                        await websocket.send_json({
                            "type": "status",
                            "action": "DEAD_AIR",
                            "frequency_hz": active_freq_hz,
                            "active_radio": active_radio,
                            "message": f"Frequency {active_freq_hz / 1_000_000:.3f} MHz is unmonitored at {airport.icao}",
                        })

                elif msg_type == "ptt":
                    state = str(payload.get("state", "")).lower()
                    if "radio" in payload:
                        active_radio = str(payload["radio"]).upper()
                        active_freq_hz = com2_hz if active_radio == "COM2" else com1_hz
                        current_facility = get_facility_by_freq(airport, active_freq_hz)
                        is_frequency_valid = current_facility is not None

                    if state == "pressed":
                        is_new_ptt_burst = True
                        if not is_frequency_valid:
                            await websocket.send_json({
                                "type": "status",
                                "action": "DEAD_AIR",
                                "message": "Cannot transmit on unmonitored frequency",
                            })
                        else:
                            await websocket.send_json({
                                "type": "status",
                                "action": "TRANSMITTING",
                                "radio": active_radio,
                                "facility": current_facility.name if current_facility else None,
                            })
                    else:
                        is_new_ptt_burst = False
                        if gemini_client.is_connected:
                            await gemini_client.send_end_of_turn()
                        await websocket.send_json({
                            "type": "status",
                            "action": "IDLE",
                        })

                elif msg_type == "audio":
                    raw_b64 = payload.get("data", "")
                    try:
                        audio_data = base64.b64decode(raw_b64)
                    except Exception:
                        audio_data = b""
                    await handle_audio_payload(audio_data)

            elif "bytes" in message and message["bytes"]:
                await handle_audio_payload(message["bytes"])

    except WebSocketDisconnect:
        logger.info("Client WebSocket disconnected from /ws/atc.")
    except Exception as exc:
        logger.error(f"WebSocket error in /ws/atc loop: {exc}")
    finally:
        if relay_task and not relay_task.done():
            relay_task.cancel()
        await gemini_client.close()
