import pytest

from navdata.models import AirportInfo, Runway, RunwayList
from atis.state import AtisState, TelemetryWeather, PhoneticLetter
from atis.generator import (
    generate_atis_text,
    determine_active_runway,
    evaluate_weather_update,
    create_initial_atis,
    advance_letter,
)


@pytest.fixture
def wahi_airport():
    """Synthetic WAHI AirportInfo with runways 11 and 29."""
    rw11 = Runway(ident="11", name="RW11", elevation_ft=24)
    rw29 = Runway(ident="29", name="RW29", elevation_ft=24)
    return AirportInfo(
        icao="WAHI",
        name="Yogyakarta International Airport",
        transition_alt=11000,
        runways=RunwayList([rw11, rw29]),
        facilities={},
    )


def test_generate_atis_text_icao_phraseology(wahi_airport):
    """Test ATIS text generation produces standardized ICAO phraseology."""
    weather = TelemetryWeather(
        wind_deg=100,
        wind_kts=7,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=29,
        dewpoint_c=23,
        qnh_hpa=1011,
        zulu_sec=6300,  # 01:45 UTC
    )

    text = generate_atis_text(
        airport=wahi_airport,
        letter="CHARLIE",
        weather=weather,
        zulu_sec=6300,
        active_runway="11",
    )

    expected = (
        "Yogyakarta International Airport Information CHARLIE, time 0145 UTC. "
        "Runway in use 11. "
        "Wind 100 degrees 7 knots, visibility 10 kilometers, clouds few 3500 feet, "
        "temperature 29, dewpoint 23, QNH 1011. "
        "Advise controller on initial contact you have information CHARLIE."
    )
    assert text == expected


def test_generate_atis_text_with_single_char_and_padded_wind(wahi_airport):
    """Test generating text with single character 'C' converts to phonetic CHARLIE and 090 wind padding."""
    weather = TelemetryWeather(
        wind_deg=90,
        wind_kts=12,
        visibility_m=8000,
        clouds="scattered 2000 feet",
        temp_c=30,
        dewpoint_c=24,
        qnh_hpa=1010,
        zulu_sec=3600,  # 01:00 UTC
    )

    text = generate_atis_text(
        airport=wahi_airport,
        letter="C",
        weather=weather,
    )

    assert "Information CHARLIE, time 0100 UTC" in text
    assert "Wind 090 degrees 12 knots" in text
    assert "visibility 8000 meters" in text
    assert "clouds scattered 2000 feet" in text
    assert "temperature 30, dewpoint 24, QNH 1010" in text
    assert "Advise controller on initial contact you have information CHARLIE." in text


def test_determine_active_runway_alignment(wahi_airport):
    """Test runway selection selects runway most aligned with headwind."""
    # Runway 11 has heading ~110 deg; Runway 29 has heading ~290 deg.
    # Wind from 100 deg -> Runway 11 has headwind
    assert determine_active_runway(wahi_airport, wind_deg=100) == "11"
    assert determine_active_runway(wahi_airport, wind_deg=120) == "11"

    # Wind from 280 deg -> Runway 29 has headwind
    assert determine_active_runway(wahi_airport, wind_deg=280) == "29"
    assert determine_active_runway(wahi_airport, wind_deg=300) == "29"


def test_determine_active_runway_empty_fallback():
    """Test runway selection with empty runways falls back to empty string."""
    empty_airport = AirportInfo(
        icao="TEST",
        name="Test Airport",
        transition_alt=5000,
        runways=RunwayList([]),
        facilities={},
    )
    assert determine_active_runway(empty_airport, wind_deg=180) == ""
    assert determine_active_runway(None, wind_deg=180) == ""


def test_phonetic_letter_subclass_equality():
    """Test PhoneticLetter comparison between PhoneticLetter instances and strings."""
    pl_a1 = PhoneticLetter("ALPHA", "A")
    pl_a2 = PhoneticLetter("ALPHA", "A")
    pl_b = PhoneticLetter("BRAVO", "B")

    # Instance equality
    assert pl_a1 == pl_a2
    assert pl_a1 != pl_b

    # String equality
    assert pl_a1 == "ALPHA"
    assert pl_a1 == "A"
    assert pl_a1 == "alpha"
    assert pl_a1 == "a"
    assert pl_a1 != "BRAVO"



def test_wind_shift_changes_runway_and_increments_letter(wahi_airport):
    """Test wind shift changing active runway triggers ATIS letter increment."""
    weather_initial = TelemetryWeather(
        wind_deg=100,
        wind_kts=10,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=28,
        dewpoint_c=22,
        qnh_hpa=1012,
        zulu_sec=3600,  # 01:00 UTC
    )

    initial_state = create_initial_atis(wahi_airport, weather_initial, letter="ALPHA")
    assert initial_state.letter == "ALPHA"
    assert initial_state.letter == "A"
    assert initial_state.active_runway == "11"
    assert initial_state.observation_time == "0100 UTC"

    # Wind shifts from 100 to 290 degrees (Runway 11 -> 29)
    weather_shifted = TelemetryWeather(
        wind_deg=290,
        wind_kts=12,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=28,
        dewpoint_c=22,
        qnh_hpa=1012,
        zulu_sec=4200,  # 10 minutes later (not 30 min trigger)
    )

    updated, new_state = evaluate_weather_update(initial_state, wahi_airport, weather_shifted)
    assert updated is True
    assert new_state.letter == "BRAVO"
    assert new_state.letter == "B"
    assert new_state.active_runway == "29"
    assert new_state.observation_time == "0110 UTC"
    assert "Runway in use 29" in new_state.script_text
    assert "Information BRAVO" in new_state.script_text


def test_qnh_shift_speci_trigger(wahi_airport):
    """Test atmospheric pressure shift >= 1.0 hPa triggers SPECI update."""
    weather_initial = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=29,
        dewpoint_c=23,
        qnh_hpa=1012.0,
        zulu_sec=3600,
    )
    state = create_initial_atis(wahi_airport, weather_initial, letter="BRAVO")

    # Shift of 0.5 hPa should NOT trigger
    weather_minor = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=29,
        dewpoint_c=23,
        qnh_hpa=1012.5,
        zulu_sec=4000,
    )
    updated, same_state = evaluate_weather_update(state, wahi_airport, weather_minor)
    assert updated is False
    assert same_state.letter == "BRAVO"

    # Shift of 1.0 hPa (SPECI threshold) MUST trigger
    weather_speci = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=29,
        dewpoint_c=23,
        qnh_hpa=1011.0,
        zulu_sec=4100,
    )
    updated, speci_state = evaluate_weather_update(state, wahi_airport, weather_speci)
    assert updated is True
    assert speci_state.letter == "CHARLIE"
    assert speci_state.letter == "C"
    assert speci_state.qnh_hpa == 1011.0
    assert "QNH 1011" in speci_state.script_text


def test_thirty_minute_timer_advances_letter(wahi_airport):
    """Test 30-minute interval advances ATIS observation letter."""
    weather_initial = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600,  # 01:00 UTC
    )
    state = create_initial_atis(wahi_airport, weather_initial, letter="CHARLIE")

    # 29 minutes elapsed (1740 seconds): should NOT trigger
    weather_29m = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600 + 1740,
    )
    updated, state_29m = evaluate_weather_update(state, wahi_airport, weather_29m)
    assert updated is False
    assert state_29m.letter == "CHARLIE"

    # 30 minutes elapsed (1800 seconds): MUST trigger
    weather_30m = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600 + 1800,  # 01:30 UTC
    )
    updated, state_30m = evaluate_weather_update(state, wahi_airport, weather_30m)
    assert updated is True
    assert state_30m.letter == "DELTA"
    assert state_30m.letter == "D"
    assert state_30m.observation_time == "0130 UTC"
    assert state_30m.zulu_sec == 5400


def test_thirty_minute_timer_crosses_midnight_rollover(wahi_airport):
    """Test 30-minute interval advances ATIS observation letter across 00:00 UTC midnight rollover."""
    # 23:50 UTC = 85800 seconds
    weather_initial = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=85800,  # 23:50 UTC
    )
    state = create_initial_atis(wahi_airport, weather_initial, letter="ECHO")

    # 20 minutes later: 00:10 UTC (600 seconds) -> total elapsed 1200 sec, should NOT trigger
    weather_20m = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=600,  # 00:10 UTC
    )
    updated, state_20m = evaluate_weather_update(state, wahi_airport, weather_20m)
    assert updated is False
    assert state_20m.letter == "ECHO"

    # 35 minutes later: 00:25 UTC (1500 seconds) -> total elapsed 2100 sec, MUST trigger
    weather_35m = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=1500,  # 00:25 UTC
    )
    updated, state_35m = evaluate_weather_update(state, wahi_airport, weather_35m)
    assert updated is True
    assert state_35m.letter == "FOXTROT"
    assert state_35m.letter == "F"
    assert state_35m.observation_time == "0025 UTC"
    assert state_35m.zulu_sec == 1500



def test_letter_wrap_around_zulu_to_alpha(wahi_airport):
    """Test letter wrap around from ZULU to ALPHA."""
    assert advance_letter("ZULU") == "ALPHA"
    assert advance_letter("Z") == "ALPHA"
    assert advance_letter("ALPHA") == "BRAVO"

    weather_initial = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600,
    )
    state_z = create_initial_atis(wahi_airport, weather_initial, letter="ZULU")
    assert state_z.letter == "ZULU"
    assert state_z.letter == "Z"

    weather_next = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600 + 1800,
    )
    updated, state_a = evaluate_weather_update(state_z, wahi_airport, weather_next)
    assert updated is True
    assert state_a.letter == "ALPHA"
    assert state_a.letter == "A"


def test_evaluate_weather_update_two_argument_signature(wahi_airport):
    """Test evaluate_weather_update works when state stores airport reference."""
    weather_initial = TelemetryWeather(
        wind_deg=110,
        wind_kts=8,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600,
    )
    state = create_initial_atis(wahi_airport, weather_initial, letter="ALPHA")

    weather_shifted = TelemetryWeather(
        wind_deg=290,
        wind_kts=12,
        visibility_m=10000,
        clouds="clear",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3900,
    )
    # Calling with (current_state, weather)
    updated, new_state = evaluate_weather_update(state, weather_shifted)
    assert updated is True
    assert new_state.letter == "BRAVO"
    assert new_state.active_runway == "29"


def test_atis_state_properties_and_accessors(wahi_airport):
    """Test AtisState convenience property accessors."""
    weather = TelemetryWeather(
        wind_deg=110,
        wind_kts=5,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=25,
        dewpoint_c=20,
        qnh_hpa=1013.0,
        zulu_sec=3600,
    )
    state = create_initial_atis(wahi_airport, weather, letter="KILO", active_runway="11")
    assert state.phonetic_letter == "KILO"
    assert state.letter_code == "K"
    assert state.letter == "KILO"
    assert state.letter == "K"
    assert state.time_utc == "0100 UTC"
    assert state.runway == "11"
    assert state.last_zulu_sec == 3600
    assert state.text == state.script_text
    assert state.script == state.script_text


def test_atis_with_real_navdata_if_available():
    """Test ATIS integration with real NavData if X-Plane 12 Custom Data is present."""
    from pathlib import Path
    from navdata import load_airport

    custom_data_path = Path(r"D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data")
    if not custom_data_path.exists():
        pytest.skip("X-Plane 12 Custom Data not found")

    airport = load_airport(custom_data_path, "WAHI")
    weather = TelemetryWeather(
        wind_deg=100,
        wind_kts=7,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=29,
        dewpoint_c=23,
        qnh_hpa=1011,
        zulu_sec=6300,
    )

    state = create_initial_atis(airport, weather, letter="CHARLIE")
    assert state.active_runway == "11"
    assert state.letter == "CHARLIE"
    assert "Yogyakarta International Airport Information CHARLIE" in state.script_text
    assert "Runway in use 11" in state.script_text

