from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union, Any

try:
    from atc.readback import verify_readback, ReadbackResult
except ImportError:
    from .readback import verify_readback, ReadbackResult


class FlightPhase(str, Enum):
    """Phases of flight managed by Wilco AI ATC Gateway."""
    APRON_CLEARANCE = "APRON_CLEARANCE"
    PUSHBACK_START = "PUSHBACK_START"
    TAXI_TO_RUNWAY = "TAXI_TO_RUNWAY"
    HOLDING_SHORT = "HOLDING_SHORT"
    TAKEOFF_CLEAR = "TAKEOFF_CLEAR"
    AIRBORNE_HANDOFF = "AIRBORNE_HANDOFF"


class InvalidTransitionError(Exception):
    """Raised when an illegal or unsupported flight phase transition is attempted."""
    pass


# Ordered phase progression
PHASE_ORDER: list[FlightPhase] = [
    FlightPhase.APRON_CLEARANCE,
    FlightPhase.PUSHBACK_START,
    FlightPhase.TAXI_TO_RUNWAY,
    FlightPhase.HOLDING_SHORT,
    FlightPhase.TAKEOFF_CLEAR,
    FlightPhase.AIRBORNE_HANDOFF,
]

# Next valid phase in sequential flight lifecycle
SEQUENTIAL_TRANSITIONS: dict[FlightPhase, FlightPhase] = {
    PHASE_ORDER[i]: PHASE_ORDER[i + 1] for i in range(len(PHASE_ORDER) - 1)
}

# Mapping of flight phase to ATC facility role
PHASE_FACILITY_MAP: dict[FlightPhase, str] = {
    FlightPhase.APRON_CLEARANCE: "DEL",
    FlightPhase.PUSHBACK_START: "GND",
    FlightPhase.TAXI_TO_RUNWAY: "GND",
    FlightPhase.HOLDING_SHORT: "TWR",
    FlightPhase.TAKEOFF_CLEAR: "TWR",
    FlightPhase.AIRBORNE_HANDOFF: "DEP",
}


@dataclass
class FlightSession:
    """Maintains active flight session parameters, clearances, and progression."""
    callsign: str
    aircraft_type: str = "A320"
    current_phase: FlightPhase = FlightPhase.APRON_CLEARANCE
    assigned_runway: Optional[str] = None
    assigned_squawk: Optional[str] = None
    cleared_sid: Optional[str] = None
    target_alt_ft: Optional[int] = None
    tuned_facility: Optional[str] = None
    atis_letter: Optional[str] = None

    def can_transition_to(self, target: Union[str, FlightPhase]) -> bool:
        """Check if transitioning directly to target phase is permitted."""
        target_phase = FlightPhase(target) if isinstance(target, str) else target
        expected_next = SEQUENTIAL_TRANSITIONS.get(self.current_phase)
        return target_phase == expected_next

    def transition_to(self, target: Union[str, FlightPhase]) -> FlightPhase:
        """Transition current phase directly to target phase if valid."""
        target_phase = FlightPhase(target) if isinstance(target, str) else target
        if not self.can_transition_to(target_phase):
            raise InvalidTransitionError(
                f"Cannot transition from {self.current_phase} to {target_phase}. "
                f"Expected next phase is {SEQUENTIAL_TRANSITIONS.get(self.current_phase)}."
            )
        self.current_phase = target_phase
        return self.current_phase

    def advance(self) -> FlightPhase:
        """Advance sequentially to the next flight phase."""
        next_phase = SEQUENTIAL_TRANSITIONS.get(self.current_phase)
        if next_phase is None:
            raise InvalidTransitionError(
                f"Flight session is already at terminal phase {self.current_phase}."
            )
        self.current_phase = next_phase
        return self.current_phase

    @property
    def expected_facility_role(self) -> str:
        """Get the standard ATC facility role (DEL, GND, TWR, DEP) for current phase."""
        return PHASE_FACILITY_MAP.get(self.current_phase, "TWR")


class FlightStateMachine:
    """State machine governing flight phases and readback validation progression."""

    def __init__(self, session: FlightSession):
        self.session = session

    @property
    def current_phase(self) -> FlightPhase:
        return self.session.current_phase

    @property
    def expected_facility_role(self) -> str:
        return self.session.expected_facility_role

    def can_transition_to(self, target: Union[str, FlightPhase]) -> bool:
        return self.session.can_transition_to(target)

    def transition_to(self, target: Union[str, FlightPhase]) -> FlightPhase:
        return self.session.transition_to(target)

    def advance(self) -> FlightPhase:
        return self.session.advance()

    def process_clearance_readback(
        self,
        pilot_text: str,
        expected_items: dict[str, Any],
    ) -> tuple[bool, ReadbackResult]:
        """
        Validates pilot voice readback against expected clearance items.
        If readback is valid, advances to the next flight phase.
        """
        result = verify_readback(pilot_text, expected_items)
        if result.is_valid:
            self.advance()
            return True, result
        return False, result
