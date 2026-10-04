from __future__ import annotations
from typing import Optional

try:
    from navdata.models import AirportInfo
    from atis.state import AtisState
    from atc.state_machine import FlightSession, FlightPhase
except ImportError:
    from ..navdata.models import AirportInfo
    from ..atis.state import AtisState
    from .state_machine import FlightSession, FlightPhase


FACILITY_FULL_NAMES: dict[str, str] = {
    "DEL": "Clearance Delivery",
    "GND": "Ground Control",
    "TWR": "Tower Control",
    "DEP": "Departure Control",
    "APP": "Approach Control",
    "CTR": "Area Control Center",
}


def build_system_prompt(
    session: FlightSession,
    airport: AirportInfo,
    atis: AtisState,
) -> str:
    """
    Builds the dynamic system instruction prompt for Gemini Multimodal Live API sessions.
    Configures ATC role, contextual airport navdata, ATIS state, session telemetry,
    bilingual English/Indonesian handling, and strict ICAO readback rules.
    """
    role_code = session.expected_facility_role
    role_full_name = FACILITY_FULL_NAMES.get(role_code, "Tower Control")
    controller_callsign = f"{airport.name} {role_full_name}"

    # Frequencies summary
    freq_items = []
    if airport.facilities:
        for fac_name, freq_hz in airport.facilities.items():
            freq_mhz = round(freq_hz / 1_000_000, 3)
            freq_items.append(f"{fac_name}: {freq_mhz:.3f} MHz")
    facilities_str = ", ".join(freq_items) if freq_items else "Standard Local Frequencies"

    # Runways summary
    runway_idents = [r.ident for r in airport.runways] if airport.runways else ["11", "29"]
    runways_str = ", ".join(runway_idents)

    # ATIS letter and observation
    atis_letter = atis.phonetic_letter
    atis_qnh = int(round(atis.qnh_hpa))

    # Assigned items
    assigned_rwy = session.assigned_runway or atis.active_runway
    assigned_sq = session.assigned_squawk or "Unassigned"
    cleared_sid = session.cleared_sid or "Radar Vectors / Standard Departure"
    target_alt = f"{session.target_alt_ft} ft" if session.target_alt_ft else "Field Elevation"

    prompt = f"""You are the certified Air Traffic Controller ({controller_callsign}) at {airport.name} ({airport.icao}).
You are communicating with pilot '{session.callsign}' flying an aircraft type '{session.aircraft_type}'.

### CURRENT AIRPORT CONTEXT:
- Airport: {airport.name} ({airport.icao})
- Transition Altitude: {airport.transition_alt} ft
- Available Runways: {runways_str}
- Active Runway in Use: {atis.active_runway}
- Facility Frequencies: {facilities_str}
- Active ATIS Information: {atis_letter} ({atis.letter_code})
- Current QNH: {atis_qnh} hPa
- Current Weather: {atis.weather.clouds if atis.weather else 'Clear'}, Wind: {atis.weather.wind_deg if atis.weather else 0:03d}° at {atis.weather.wind_kts if atis.weather else 0} knots

### ACTIVE FLIGHT SESSION:
- Aircraft Callsign: {session.callsign}
- Aircraft Type: {session.aircraft_type}
- Flight Phase: {session.current_phase.value}
- Active Facility Role: {role_full_name} ({role_code})
- Assigned Runway: {assigned_rwy}
- Assigned Squawk: {assigned_sq}
- Cleared SID: {cleared_sid}
- Cleared Altitude: {target_alt}

### BILINGUAL COMMUNICATION PROTOCOL:
1. Primary Language: Use standard ICAO English by default for all transmissions.
2. Pilot Bilingual Adaptation: If the pilot speaks in Indonesian (Bahasa Indonesia), understand accurately and reply politely and professionally in standard Indonesian aviation phraseology. If the pilot speaks English, reply in English.
3. Code-switching: Keep aviation standard terms recognizable (e.g. 'squawk', 'cleared', 'runway' / 'landas pacu', 'QNH', 'pushback and start').

### READBACK VERIFICATION RULES:
1. Strict Enforcement: Mandatory readback items include:
   - Assigned Runway
   - Squawk Transponder Code
   - Altimeter Setting / QNH
   - Level / Altitude instructions
   - Clearance Routing / SID
   - Hold Short instructions
2. Immediate Correction: If the pilot omits or incorrectly reads back any mandatory parameter (e.g. wrong QNH or wrong squawk), state "Negative" followed immediately by the correct parameter. Never let an erroneous readback pass uncorrected.
3. Sub-Second Radiotelephony Brevity: Speak concisely and crisply with strict radio discipline. Do NOT use conversational filler, chitchat, or excessive greetings. Speak clearly and briskly.
"""
    return prompt.strip()
