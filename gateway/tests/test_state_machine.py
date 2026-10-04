import pytest

from navdata.models import AirportInfo, Runway, RunwayList
from atis.state import AtisState, TelemetryWeather, PhoneticLetter

from atc.state_machine import (
    FlightPhase,
    FlightSession,
    FlightStateMachine,
    InvalidTransitionError,
)
from atc.readback import verify_readback, ReadbackResult
from atc.prompt_builder import build_system_prompt
import atc


@pytest.fixture
def wahi_airport() -> AirportInfo:
    """Synthetic WAHI AirportInfo fixture."""
    rw11 = Runway(ident="11", name="RW11", elevation_ft=24)
    rw29 = Runway(ident="29", name="RW29", elevation_ft=24)
    return AirportInfo(
        icao="WAHI",
        name="Yogyakarta International Airport",
        transition_alt=11000,
        runways=RunwayList([rw11, rw29]),
        facilities={
            "DEL": 121900000,
            "GND": 121650000,
            "TWR": 118200000,
            "ATIS": 126400000,
        },
    )


@pytest.fixture
def sample_atis(wahi_airport: AirportInfo) -> AtisState:
    """Synthetic ATIS state fixture."""
    weather = TelemetryWeather(
        wind_deg=100,
        wind_kts=8,
        visibility_m=10000,
        clouds="few 3500 feet",
        temp_c=29,
        dewpoint_c=23,
        qnh_hpa=1011,
        zulu_sec=7200,
    )
    return AtisState(
        letter=PhoneticLetter("CHARLIE", "C"),
        observation_time="0200 UTC",
        active_runway="11",
        script_text="Yogyakarta Information CHARLIE...",
        qnh_hpa=1011.0,
        weather=weather,
        airport=wahi_airport,
    )


@pytest.fixture
def sample_session() -> FlightSession:
    """Synthetic FlightSession fixture."""
    return FlightSession(
        callsign="GIA123",
        aircraft_type="A320",
        current_phase=FlightPhase.APRON_CLEARANCE,
        assigned_runway="11",
        assigned_squawk="5201",
        cleared_sid="CA2L",
        target_alt_ft=5000,
        tuned_facility="DEL",
        atis_letter="C",
    )


# ============================================================================
# 1. Flight Phase & Flight Session Tests
# ============================================================================

def test_flight_phase_enum_values():
    """Verify all 6 standard flight phases are defined with string enum capability."""
    expected_phases = [
        "APRON_CLEARANCE",
        "PUSHBACK_START",
        "TAXI_TO_RUNWAY",
        "HOLDING_SHORT",
        "TAKEOFF_CLEAR",
        "AIRBORNE_HANDOFF",
    ]
    for name in expected_phases:
        assert hasattr(FlightPhase, name)
        phase = getattr(FlightPhase, name)
        assert phase == name
        assert isinstance(phase, FlightPhase)


def test_flight_session_initialization():
    """Verify FlightSession dataclass defaults and property tracking."""
    session = FlightSession(callsign="PK-LION")
    assert session.callsign == "PK-LION"
    assert session.aircraft_type == "A320"
    assert session.current_phase == FlightPhase.APRON_CLEARANCE
    assert session.assigned_runway is None
    assert session.assigned_squawk is None
    assert session.cleared_sid is None
    assert session.target_alt_ft is None
    assert session.tuned_facility is None
    assert session.atis_letter is None


def test_package_exports():
    """Verify top-level atc package exports required classes and functions."""
    assert atc.FlightPhase is FlightPhase
    assert atc.FlightSession is FlightSession
    assert atc.FlightStateMachine is FlightStateMachine
    assert atc.verify_readback is verify_readback
    assert atc.ReadbackResult is ReadbackResult
    assert atc.build_system_prompt is build_system_prompt


# ============================================================================
# 2. State Machine Transitions
# ============================================================================

def test_state_machine_sequential_progression(sample_session: FlightSession):
    """Test full sequential lifecycle progression through all flight phases."""
    sm = FlightStateMachine(sample_session)
    assert sm.current_phase == FlightPhase.APRON_CLEARANCE

    # APRON_CLEARANCE -> PUSHBACK_START
    assert sm.can_transition_to(FlightPhase.PUSHBACK_START)
    next_phase = sm.advance()
    assert next_phase == FlightPhase.PUSHBACK_START
    assert sample_session.current_phase == FlightPhase.PUSHBACK_START

    # PUSHBACK_START -> TAXI_TO_RUNWAY
    assert sm.can_transition_to(FlightPhase.TAXI_TO_RUNWAY)
    next_phase = sm.advance()
    assert next_phase == FlightPhase.TAXI_TO_RUNWAY
    assert sample_session.current_phase == FlightPhase.TAXI_TO_RUNWAY

    # TAXI_TO_RUNWAY -> HOLDING_SHORT
    assert sm.can_transition_to(FlightPhase.HOLDING_SHORT)
    next_phase = sm.advance()
    assert next_phase == FlightPhase.HOLDING_SHORT
    assert sample_session.current_phase == FlightPhase.HOLDING_SHORT

    # HOLDING_SHORT -> TAKEOFF_CLEAR
    assert sm.can_transition_to(FlightPhase.TAKEOFF_CLEAR)
    next_phase = sm.advance()
    assert next_phase == FlightPhase.TAKEOFF_CLEAR
    assert sample_session.current_phase == FlightPhase.TAKEOFF_CLEAR

    # TAKEOFF_CLEAR -> AIRBORNE_HANDOFF
    assert sm.can_transition_to(FlightPhase.AIRBORNE_HANDOFF)
    next_phase = sm.advance()
    assert next_phase == FlightPhase.AIRBORNE_HANDOFF
    assert sample_session.current_phase == FlightPhase.AIRBORNE_HANDOFF

    # Beyond terminal phase
    assert not sm.can_transition_to(FlightPhase.APRON_CLEARANCE)
    with pytest.raises(InvalidTransitionError):
        sm.advance()


def test_state_machine_invalid_transitions(sample_session: FlightSession):
    """Verify state machine disallows skipping steps without explicit transition."""
    sm = FlightStateMachine(sample_session)
    assert sm.current_phase == FlightPhase.APRON_CLEARANCE

    # Cannot skip directly to TAKEOFF_CLEAR
    assert not sm.can_transition_to(FlightPhase.TAKEOFF_CLEAR)
    with pytest.raises(InvalidTransitionError):
        sm.transition_to(FlightPhase.TAKEOFF_CLEAR)

    # Cannot skip directly to AIRBORNE_HANDOFF
    assert not sm.can_transition_to(FlightPhase.AIRBORNE_HANDOFF)
    with pytest.raises(InvalidTransitionError):
        sm.transition_to(FlightPhase.AIRBORNE_HANDOFF)


def test_state_machine_facility_role_resolution(sample_session: FlightSession):
    """Verify state machine identifies the appropriate ATC facility role for each phase."""
    sm = FlightStateMachine(sample_session)
    assert sm.expected_facility_role == "DEL"

    sm.transition_to(FlightPhase.PUSHBACK_START)
    assert sm.expected_facility_role == "GND"

    sm.transition_to(FlightPhase.TAXI_TO_RUNWAY)
    assert sm.expected_facility_role == "GND"

    sm.transition_to(FlightPhase.HOLDING_SHORT)
    assert sm.expected_facility_role == "TWR"

    sm.transition_to(FlightPhase.TAKEOFF_CLEAR)
    assert sm.expected_facility_role == "TWR"

    sm.transition_to(FlightPhase.AIRBORNE_HANDOFF)
    assert sm.expected_facility_role in ("DEP", "APP", "CTR")


def test_state_machine_transition_with_readback_success(sample_session: FlightSession):
    """Verify transition succeeds when pilot readback matches all clearance items."""
    sm = FlightStateMachine(sample_session)
    assert sm.current_phase == FlightPhase.APRON_CLEARANCE

    pilot_text = "Garuda 123, cleared to Surabaya, runway 11, CA2L departure, climb 5000, squawk 5201, QNH 1011"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
        "sid": "CA2L",
        "alt": 5000,
    }

    success, result = sm.process_clearance_readback(pilot_text, expected)
    assert success is True
    assert result.is_valid is True
    assert result.errors == []
    # Advanced to PUSHBACK_START
    assert sm.current_phase == FlightPhase.PUSHBACK_START
    assert sample_session.current_phase == FlightPhase.PUSHBACK_START


def test_state_machine_transition_with_readback_failure(sample_session: FlightSession):
    """Verify transition is blocked and phase is unchanged when readback has errors."""
    sm = FlightStateMachine(sample_session)
    assert sm.current_phase == FlightPhase.APRON_CLEARANCE

    # Pilot reads back wrong squawk (5200 instead of 5201)
    pilot_text = "Garuda 123, runway 11, squawk 5200, QNH 1011"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }

    success, result = sm.process_clearance_readback(pilot_text, expected)
    assert success is False
    assert result.is_valid is False
    assert len(result.errors) > 0
    # Phase must remain APRON_CLEARANCE
    assert sm.current_phase == FlightPhase.APRON_CLEARANCE
    assert sample_session.current_phase == FlightPhase.APRON_CLEARANCE


# ============================================================================
# 3. Readback Verification Engine Tests
# ============================================================================

def test_verify_readback_standard_english():
    """Verify standard English readback with digits and standard phrasing."""
    pilot_text = "Runway 11, squawk 5201, QNH 1011, Garuda 123"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is True
    assert result.errors == []
    assert result.missing_items == []
    assert result.matched_items["runway"] == "11"
    assert result.matched_items["squawk"] == "5201"
    assert result.matched_items["qnh"] == 1011


def test_verify_readback_spoken_english_words():
    """Verify English spoken number words: 'one one', 'five two zero one', 'one zero one one'."""
    pilot_text = (
        "Runway one one, squawk five two zero one, QNH one zero one one, Garuda one two three"
    )
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is True
    assert result.errors == []
    assert result.missing_items == []


def test_verify_readback_indonesian_bilingual_words():
    """Verify Indonesian words: 'landas pacu satu satu', 'lima dua kosong satu', 'satu kosong satu satu'."""
    pilot_text = (
        "Garuda 123, landas pacu satu satu, squawk lima dua kosong satu, "
        "QNH satu kosong satu satu"
    )
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is True
    assert result.errors == []
    assert result.missing_items == []


def test_verify_readback_indonesian_with_nol_and_landasan():
    """Verify Indonesian alternative phrasing: 'nol' for zero and 'landasan' for runway."""
    pilot_text = "Landasan 11, squawk lima dua nol satu, QNH satu nol satu satu, Garuda 123"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is True
    assert result.errors == []


def test_verify_readback_wrong_qnh_error():
    """Verify error detected when pilot reads back incorrect QNH pressure."""
    pilot_text = "Runway 11, squawk 5201, QNH 1013, Garuda 123"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is False
    assert any("QNH" in err.upper() or "1011" in err for err in result.errors)


def test_verify_readback_wrong_squawk_error():
    """Verify error detected when pilot reads back incorrect squawk transponder code."""
    pilot_text = "Runway 11, squawk 7000, QNH 1011, Garuda 123"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is False
    assert any("SQUAWK" in err.upper() or "5201" in err for err in result.errors)


def test_verify_readback_wrong_runway_error():
    """Verify error detected when pilot reads back incorrect runway."""
    pilot_text = "Runway 29, squawk 5201, QNH 1011, Garuda 123"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is False
    assert any("RUNWAY" in err.upper() or "11" in err for err in result.errors)


def test_verify_readback_missing_items():
    """Verify missing items list flags omitted mandatory readback parameters."""
    # Pilot reads runway and squawk, but omits QNH
    pilot_text = "Runway 11, squawk 5201, Garuda 123"
    expected = {
        "runway": "11",
        "squawk": "5201",
        "qnh": 1011,
    }
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is False
    assert "qnh" in result.missing_items
    assert "runway" not in result.missing_items
    assert "squawk" not in result.missing_items


def test_verify_readback_sid_and_altitude():
    """Verify SID alphanumeric code and target altitude readback in both NATO words and numbers."""
    # Direct SID name
    pilot_text = "Cleared CA2L, climb 5000, Garuda 123"
    expected = {"sid": "CA2L", "alt": 5000}
    result = verify_readback(pilot_text, expected)
    assert result.is_valid is True

    # Phonetic NATO words
    pilot_nato = "Charlie Alpha 2 Lima departure, climb five thousand feet, Garuda 123"
    result_nato = verify_readback(pilot_nato, expected)
    assert result_nato.is_valid is True

    # Mismatched SID
    pilot_wrong_sid = "Cleared ELANG1, climb 5000, Garuda 123"
    result_wrong = verify_readback(pilot_wrong_sid, expected)
    assert result_wrong.is_valid is False
    assert any("SID" in err.upper() or "CA2L" in err for err in result_wrong.errors)


def test_verify_readback_hold_short_instructions():
    """Verify hold short runway compliance check in English and Indonesian."""
    # English hold short
    pilot_en = "Holding short runway 11, Garuda 123"
    expected = {"hold_short": "11"}
    result_en = verify_readback(pilot_en, expected)
    assert result_en.is_valid is True

    # Indonesian hold short
    pilot_id = "Tahan sebelum landas pacu 11, Garuda 123"
    result_id = verify_readback(pilot_id, expected)
    assert result_id.is_valid is True

    # Failed hold short (did not read back hold short)
    pilot_no_hold = "Taxi to runway 11, Garuda 123"
    result_no_hold = verify_readback(pilot_no_hold, expected)
    assert result_no_hold.is_valid is False
    assert "hold_short" in result_no_hold.missing_items


# ============================================================================
# 4. Gemini Multimodal Live API Prompt Builder Tests
# ============================================================================

def test_build_system_prompt_contains_core_atc_context(
    sample_session: FlightSession,
    wahi_airport: AirportInfo,
    sample_atis: AtisState,
):
    """Verify generated system prompt incorporates airport, ATIS, flight session, and ICAO rules."""
    prompt = build_system_prompt(sample_session, wahi_airport, sample_atis)

    # 1. Airport details
    assert "WAHI" in prompt
    assert "Yogyakarta" in prompt
    assert "11000" in prompt  # Transition altitude

    # 2. ATIS information
    assert "CHARLIE" in prompt or "Information C" in prompt
    assert "1011" in prompt  # QNH
    assert "11" in prompt    # Active runway

    # 3. Aircraft and flight session details
    assert "GIA123" in prompt
    assert "A320" in prompt
    assert "APRON_CLEARANCE" in prompt
    assert "5201" in prompt  # Squawk
    assert "CA2L" in prompt  # SID

    # 4. Bilingual instructions
    assert "English" in prompt
    assert "Indonesian" in prompt or "Bahasa Indonesia" in prompt

    # 5. Readback and brevity rules
    assert "readback" in prompt.lower()
    assert "brevity" in prompt.lower() or "concise" in prompt.lower()


def test_build_system_prompt_dynamic_phase_updates(
    sample_session: FlightSession,
    wahi_airport: AirportInfo,
    sample_atis: AtisState,
):
    """Verify prompt adapts controller role and instructions dynamically across flight phases."""
    # In APRON_CLEARANCE -> Delivery role
    prompt_del = build_system_prompt(sample_session, wahi_airport, sample_atis)
    assert "Delivery" in prompt_del or "Clearance Delivery" in prompt_del or "DEL" in prompt_del

    # In TAXI_TO_RUNWAY -> Ground role
    sample_session.current_phase = FlightPhase.TAXI_TO_RUNWAY
    prompt_gnd = build_system_prompt(sample_session, wahi_airport, sample_atis)
    assert "Ground" in prompt_gnd or "GND" in prompt_gnd

    # In HOLDING_SHORT -> Tower role
    sample_session.current_phase = FlightPhase.HOLDING_SHORT
    prompt_twr = build_system_prompt(sample_session, wahi_airport, sample_atis)
    assert "Tower" in prompt_twr or "TWR" in prompt_twr


# ============================================================================
# 5. Robustness & Edge Cases
# ============================================================================

def test_verify_readback_empty_and_whitespace():
    """Verify empty or whitespace transmissions fail gracefully with missing items."""
    expected = {"runway": "11", "qnh": 1011}
    res_empty = verify_readback("", expected)
    assert res_empty.is_valid is False
    assert len(res_empty.errors) > 0

    res_ws = verify_readback("   \n\t  ", expected)
    assert res_ws.is_valid is False
    assert "runway" in res_ws.missing_items
    assert "qnh" in res_ws.missing_items


def test_verify_readback_runway_leading_zero_and_parallel():
    """Verify runway 09 matches 9, and parallel designators (e.g. 25L)."""
    # Leading zero in expected, pilot omits zero
    res1 = verify_readback("Runway 9, QNH 1011", {"runway": "09", "qnh": 1011})
    assert res1.is_valid is True

    # Pilot includes leading zero, expected omits zero
    res2 = verify_readback("Runway 09, QNH 1011", {"runway": "9", "qnh": 1011})
    assert res2.is_valid is True

    # Parallel runway designator L
    res3 = verify_readback("Runway 25L, QNH 1011", {"runway": "25L", "qnh": 1011})
    assert res3.is_valid is True

    # Parallel runway designator mismatch (25R vs 25L)
    res4 = verify_readback("Runway 25R, QNH 1011", {"runway": "25L", "qnh": 1011})
    assert res4.is_valid is False


def test_verify_readback_type_flexibility():
    """Verify squawk as integer, QNH as float, and alt as string."""
    pilot = "Runway 11, squawk 5201, QNH 1011, climb 5000"
    expected = {
        "runway": "11",
        "squawk": 5201,      # int instead of str
        "qnh": 1011.0,       # float instead of int
        "alt": "5000",       # str instead of int
    }
    result = verify_readback(pilot, expected)
    assert result.is_valid is True
    assert result.errors == []


def test_build_system_prompt_empty_facilities_and_runways():
    """Verify prompt builder handles airport with empty facilities and runways gracefully."""
    empty_airport = AirportInfo(
        icao="WAHH",
        name="Adisutjipto",
        transition_alt=11000,
        runways=RunwayList([]),
        facilities={},
    )
    weather = TelemetryWeather()
    atis = AtisState(
        letter=PhoneticLetter("ALPHA", "A"),
        observation_time="0000 UTC",
        active_runway="09",
        script_text="ATIS script",
        weather=weather,
    )
    session = FlightSession(callsign="PK-TST")
    prompt = build_system_prompt(session, empty_airport, atis)
    assert "WAHH" in prompt
    assert "PK-TST" in prompt

