from __future__ import annotations
import math
from typing import Optional, Union
try:
    from navdata.models import AirportInfo, Runway
except ImportError:
    from ..navdata.models import AirportInfo, Runway

from .state import (
    AtisState,
    TelemetryWeather,
    PhoneticLetter,
    advance_letter,
    to_phonetic_letter,
)


def format_zulu_time(zulu_sec: int) -> str:
    """Format simulator Zulu seconds into 4-digit HHMM string."""
    hours = (zulu_sec // 3600) % 24
    minutes = (zulu_sec % 3600) // 60
    return f"{hours:02d}{minutes:02d}"


def format_visibility(visibility: Union[float, int, str]) -> str:
    """Format visibility in meters or kilometers according to ICAO conventions."""
    if isinstance(visibility, str):
        return visibility
    vis_num = float(visibility)
    if vis_num >= 10000:
        return "10 kilometers"
    return f"{round(vis_num)} meters"


def get_runway_heading(rwy: Runway) -> float:
    """Extract magnetic orientation heading (degrees) from runway identifier."""
    if rwy.heading is not None:
        return float(rwy.heading)

    digits = "".join(c for c in rwy.ident if c.isdigit())
    if digits:
        val = int(digits) * 10
        return 360.0 if val == 0 else float(val)
    return 0.0


def determine_active_runway(airport: Optional[AirportInfo], wind_deg: Union[int, float]) -> str:
    """
    Select the runway most aligned with the wind direction to maximize headwind.
    Calculates headwind component = cos(radians(wind_deg - runway_heading)).
    """
    if not airport or not hasattr(airport, "runways") or not airport.runways:
        return ""

    best_rwy: Optional[Runway] = None
    best_headwind: float = -float("inf")

    for rwy in airport.runways:
        rwy_hdg = get_runway_heading(rwy)
        # Calculate angle difference between wind and runway heading
        diff_rad = math.radians(float(wind_deg) - rwy_hdg)
        headwind = math.cos(diff_rad)

        if headwind > best_headwind:
            best_headwind = headwind
            best_rwy = rwy

    if best_rwy is not None:
        # Return clean ident (e.g. '11' or '29')
        return best_rwy.ident.upper().replace("RWY", "").replace("RW", "").strip()

    return airport.runways[0].ident.upper().replace("RWY", "").replace("RW", "").strip() if airport.runways else ""


def generate_atis_text(
    airport: AirportInfo,
    letter: Union[str, PhoneticLetter],
    weather: TelemetryWeather,
    zulu_sec: Optional[int] = None,
    active_runway: Optional[str] = None,
) -> str:
    """
    Generate authentic ICAO standard ATIS script text.

    Format:
    "{airport_name} Information {letter_word}, time {hhmm} UTC. Runway in use {runway}. \
    Wind {wind_deg:03d} degrees {wind_kts} knots, visibility {vis_str}, clouds {clouds}, \
    temperature {temp}, dewpoint {dewpoint}, QNH {qnh}. Advise controller on initial contact you have information {letter_word}."
    """
    pl = to_phonetic_letter(letter)
    letter_word = pl.phonetic

    sec = zulu_sec if zulu_sec is not None else weather.zulu_sec
    hhmm = format_zulu_time(sec)

    if active_runway is not None:
        runway = active_runway.upper().replace("RWY", "").replace("RW", "").strip()
    else:
        runway = determine_active_runway(airport, weather.wind_deg)

    airport_name = airport.name if hasattr(airport, "name") and airport.name else str(airport)
    wind_deg = round(float(weather.wind_deg))
    wind_kts = round(float(weather.wind_kts))
    vis_str = format_visibility(weather.visibility_m)
    clouds = weather.clouds
    temp = round(float(weather.temp_c))
    dewpoint = round(float(weather.dewpoint_c))
    qnh = round(float(weather.qnh_hpa))

    return (
        f"{airport_name} Information {letter_word}, time {hhmm} UTC. "
        f"Runway in use {runway}. "
        f"Wind {wind_deg:03d} degrees {wind_kts} knots, visibility {vis_str}, clouds {clouds}, "
        f"temperature {temp}, dewpoint {dewpoint}, QNH {qnh}. "
        f"Advise controller on initial contact you have information {letter_word}."
    )


def create_initial_atis(
    airport: AirportInfo,
    weather: TelemetryWeather,
    letter: Union[str, PhoneticLetter] = "ALPHA",
    active_runway: Optional[str] = None,
) -> AtisState:
    """Initialize an AtisState for a given airport and weather condition."""
    pl = to_phonetic_letter(letter)
    rwy = (
        active_runway
        if active_runway is not None
        else determine_active_runway(airport, weather.wind_deg)
    )
    script = generate_atis_text(
        airport=airport,
        letter=pl,
        weather=weather,
        zulu_sec=weather.zulu_sec,
        active_runway=rwy,
    )
    obs_time = f"{format_zulu_time(weather.zulu_sec)} UTC"
    return AtisState(
        letter=pl,
        observation_time=obs_time,
        active_runway=rwy,
        script_text=script,
        zulu_sec=weather.zulu_sec,
        qnh_hpa=float(weather.qnh_hpa),
        weather=weather,
        airport=airport,
    )


def evaluate_weather_update(
    current_state: AtisState,
    arg2: Union[AirportInfo, TelemetryWeather],
    weather: Optional[TelemetryWeather] = None,
) -> tuple[bool, AtisState]:
    """
    Evaluate weather telemetry update against current ATIS state.

    Triggers letter increment if:
    1. Active runway changes due to wind shift.
    2. QNH shifts by >= 1.0 hPa (SPECI trigger).
    3. Simulator Zulu time advances by >= 30 minutes (1800 sec).

    Returns:
        (True, new_state) if updated, or (False, current_state) if unchanged.
    """
    if isinstance(arg2, AirportInfo):
        airport = arg2
        weather_update = weather
    elif isinstance(arg2, TelemetryWeather):
        weather_update = arg2
        airport = current_state.airport
    else:
        airport = current_state.airport
        weather_update = weather

    if weather_update is None:
        return False, current_state

    # 1. Runway in use check
    new_runway = (
        determine_active_runway(airport, weather_update.wind_deg)
        if airport
        else current_state.active_runway
    )
    runway_changed = (new_runway != current_state.active_runway)

    # 2. QNH change check (>= 1.0 hPa)
    prev_qnh = float(current_state.qnh_hpa)
    curr_qnh = float(weather_update.qnh_hpa)
    qnh_changed = round(abs(curr_qnh - prev_qnh), 4) >= 1.0

    # 3. Time elapsed check (>= 30 min / 1800 s, handling midnight rollover)
    prev_time = current_state.zulu_sec
    curr_time = weather_update.zulu_sec
    elapsed_sec = (curr_time - prev_time) if curr_time >= prev_time else (curr_time + 86400 - prev_time)
    time_advanced = elapsed_sec >= 1800

    if runway_changed or qnh_changed or time_advanced:
        next_let = advance_letter(current_state.letter)
        target_airport = airport or current_state.airport
        if target_airport is not None:
            new_script = generate_atis_text(
                airport=target_airport,
                letter=next_let,
                weather=weather_update,
                zulu_sec=weather_update.zulu_sec,
                active_runway=new_runway,
            )
        else:
            new_script = ""
        obs_time = f"{format_zulu_time(weather_update.zulu_sec)} UTC"
        new_state = AtisState(
            letter=next_let,
            observation_time=obs_time,
            active_runway=new_runway,
            script_text=new_script,
            zulu_sec=weather_update.zulu_sec,
            qnh_hpa=curr_qnh,
            weather=weather_update,
            airport=airport or current_state.airport,
        )
        return True, new_state

    return False, current_state
