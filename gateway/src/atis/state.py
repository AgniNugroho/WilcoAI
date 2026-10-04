from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Union, Any
from navdata.models import AirportInfo


PHONETIC_ALPHABET: dict[str, str] = {
    "A": "ALPHA",
    "B": "BRAVO",
    "C": "CHARLIE",
    "D": "DELTA",
    "E": "ECHO",
    "F": "FOXTROT",
    "G": "GOLF",
    "H": "HOTEL",
    "I": "INDIA",
    "J": "JULIETT",
    "K": "KILO",
    "L": "LIMA",
    "M": "MIKE",
    "N": "NOVEMBER",
    "O": "OSCAR",
    "P": "PAPA",
    "Q": "QUEBEC",
    "R": "ROMEO",
    "S": "SIERRA",
    "T": "TANGO",
    "U": "UNIFORM",
    "V": "VICTOR",
    "W": "WHISKEY",
    "X": "X-RAY",
    "Y": "YANKEE",
    "Z": "ZULU",
}

# Reverse lookup with alternative standard spellings (e.g. JULIET, XRAY)
PHONETIC_TO_CODE: dict[str, str] = {v: k for k, v in PHONETIC_ALPHABET.items()}
PHONETIC_TO_CODE["JULIET"] = "J"
PHONETIC_TO_CODE["XRAY"] = "X"


class PhoneticLetter(str):
    """
    String representation of a phonetic letter (e.g. 'ALPHA').
    Provides dual equality matching against both phonetic word ('ALPHA')
    and single character code ('A').
    """

    def __new__(cls, phonetic: str, code: str) -> PhoneticLetter:
        instance = super().__new__(cls, phonetic.upper())
        instance._phonetic = phonetic.upper()
        instance._code = code.upper()
        return instance

    @property
    def code(self) -> str:
        return self._code

    @property
    def phonetic(self) -> str:
        return self._phonetic

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            other_up = other.upper()
            return super().__eq__(other_up) or other_up == self._code or other_up == self._phonetic
        if isinstance(other, PhoneticLetter):
            return self._code == other._code
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self._phonetic)

    def __repr__(self) -> str:
        return f"PhoneticLetter('{self._phonetic}', code='{self._code}')"


def to_phonetic_letter(val: Union[str, PhoneticLetter]) -> PhoneticLetter:
    """Normalize a letter or phonetic name into a PhoneticLetter instance."""
    if isinstance(val, PhoneticLetter):
        return val

    clean = str(val).strip().upper()
    if len(clean) == 1 and clean in PHONETIC_ALPHABET:
        return PhoneticLetter(PHONETIC_ALPHABET[clean], clean)

    if clean in PHONETIC_TO_CODE:
        code = PHONETIC_TO_CODE[clean]
        return PhoneticLetter(PHONETIC_ALPHABET[code], code)

    code = clean[:1] if clean else "A"
    phonetic = PHONETIC_ALPHABET.get(code, clean)
    return PhoneticLetter(phonetic, code)


def advance_letter(current: Union[str, PhoneticLetter]) -> PhoneticLetter:
    """
    Advance phonetic letter sequentially:
    ALPHA -> BRAVO -> ... -> ZULU -> ALPHA (A -> B -> ... -> Z -> A).
    """
    current_pl = to_phonetic_letter(current)
    idx = (ord(current_pl.code) - ord("A") + 1) % 26
    next_code = chr(ord("A") + idx)
    next_phonetic = PHONETIC_ALPHABET[next_code]
    return PhoneticLetter(next_phonetic, next_code)


@dataclass
class TelemetryWeather:
    """Snapshot of simulator weather telemetry from X-Plane 12."""
    wind_deg: Union[int, float] = 0
    wind_kts: Union[int, float] = 0
    visibility_m: Union[int, float] = 10000.0
    clouds: str = "few 3500 feet"
    temp_c: Union[int, float] = 25
    dewpoint_c: Union[int, float] = 18
    qnh_hpa: Union[int, float] = 1013.25
    zulu_sec: int = 0


@dataclass
class AtisState:
    """State of an airport ATIS broadcast cycle."""
    letter: Union[str, PhoneticLetter]
    observation_time: str
    active_runway: str
    script_text: str
    zulu_sec: int = 0
    qnh_hpa: float = 1013.25
    weather: Optional[TelemetryWeather] = None
    airport: Optional[AirportInfo] = None

    def __post_init__(self) -> None:
        if not isinstance(self.letter, PhoneticLetter):
            self.letter = to_phonetic_letter(self.letter)
        if self.weather is not None:
            if not self.zulu_sec:
                self.zulu_sec = int(self.weather.zulu_sec)
            if self.qnh_hpa == 1013.25:
                self.qnh_hpa = float(self.weather.qnh_hpa)

    @property
    def phonetic_letter(self) -> str:
        if isinstance(self.letter, PhoneticLetter):
            return self.letter.phonetic
        return str(self.letter)

    @property
    def letter_code(self) -> str:
        if isinstance(self.letter, PhoneticLetter):
            return self.letter.code
        return str(self.letter)[:1].upper()

    @property
    def text(self) -> str:
        return self.script_text

    @property
    def script(self) -> str:
        return self.script_text

    @property
    def time_utc(self) -> str:
        return self.observation_time

    @property
    def runway(self) -> str:
        return self.active_runway

    @property
    def last_zulu_sec(self) -> int:
        return self.zulu_sec
