from __future__ import annotations
from pathlib import Path
from typing import Optional, Union, Any

from navdata.models import Facility, FacilityDict, AirportInfo

# Standard / reference ATC facilities for known regional airports
DEFAULT_AIRPORT_FACILITIES: dict[str, dict[str, int]] = {
    "WAHI": {
        "TWR": 118200000,
        "Tower": 118200000,
        "twr": 118200000,
        "GND": 121650000,
        "Ground": 121650000,
        "gnd": 121650000,
        "ATIS": 127800000,
        "atis": 127800000,
    },
    "WARJ": {
        "TWR": 118200000,
        "Tower": 118200000,
        "twr": 118200000,
        "GND": 121650000,
        "Ground": 121650000,
        "gnd": 121650000,
        "ATIS": 127800000,
        "atis": 127800000,
    },
    "WAHH": {
        "TWR": 118100000,
        "Tower": 118100000,
        "twr": 118100000,
        "GND": 121900000,
        "Ground": 121900000,
        "gnd": 121900000,
        "ATIS": 126400000,
        "atis": 126400000,
    },
}

DEFAULT_AIRPORT_NAMES: dict[str, str] = {
    "WAHI": "Yogyakarta International Airport",
    "WARJ": "Yogyakarta International Airport",
    "WAHH": "Adisutjipto International Airport",
}


def parse_freq_to_hz(freq_str: Union[str, int, float]) -> int:
    """Convert an atc.dat frequency or MHz/kHz frequency to Hz."""
    if isinstance(freq_str, (int, float)):
        val = freq_str
    else:
        freq_s = str(freq_str).strip()
        if "." in freq_s:
            val = float(freq_s)
        else:
            val = int(freq_s)

    if isinstance(val, float):
        return int(round(val * 1_000_000))
    elif val < 1000:
        return int(round(val * 1_000_000))
    elif val < 100000:  # 5 digits from atc.dat, e.g. 11820 -> 118.200 MHz
        return val * 10000
    elif val < 1000000:  # 6 digits, e.g. 118200 or 121650
        return val * 1000
    return int(val)


def parse_atc_facilities(custom_data_path: Union[str, Path], icao: str) -> FacilityDict:
    """
    Parse 1200 atc data/Earth nav data/atc.dat for controller facilities matching icao.
    Falls back to known regional airport facilities if not present in atc.dat.
    """
    path = Path(custom_data_path)
    atc_candidates = [
        path / "1200 atc data" / "Earth nav data" / "atc.dat",
        path / "atc.dat",
        path / "Earth nav data" / "atc.dat",
    ]

    target_icao = icao.upper()
    if target_icao == "WARJ":
        target_icao = "WAHI"

    facilities = FacilityDict()

    # Pre-populate known defaults if available
    defaults = DEFAULT_AIRPORT_FACILITIES.get(target_icao, {})
    for k, v in defaults.items():
        facilities[k] = v

    atc_file = None
    for cand in atc_candidates:
        if cand.exists():
            atc_file = cand
            break

    if atc_file is not None:
        try:
            with open(atc_file, "r", encoding="utf-8", errors="ignore") as f:
                in_controller = False
                controller_icao = ""
                controller_name = ""
                controller_role = ""
                controller_freqs: list[int] = []

                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue

                    if line == "CONTROLLER":
                        in_controller = True
                        controller_icao = ""
                        controller_name = ""
                        controller_role = ""
                        controller_freqs = []
                    elif line == "CONTROLLER_END":
                        if in_controller and controller_icao.upper() == target_icao:
                            role_upper = controller_role.upper()
                            role_key = {
                                "TWR": "TWR",
                                "GND": "GND",
                                "DEL": "DEL",
                                "CLR": "DEL",
                                "APP": "APP",
                                "DEP": "DEP",
                                "ATIS": "ATIS",
                                "CTR": "CTR",
                                "TRACON": "APP",
                            }.get(role_upper, role_upper)

                            for freq_hz in controller_freqs:
                                facilities[role_key] = freq_hz
                                if role_key == "TWR":
                                    facilities["Tower"] = freq_hz
                                    facilities["twr"] = freq_hz
                                elif role_key == "GND":
                                    facilities["Ground"] = freq_hz
                                    facilities["gnd"] = freq_hz
                                elif role_key == "ATIS":
                                    facilities["atis"] = freq_hz
                        in_controller = False
                    elif in_controller:
                        if line.startswith("ICAO "):
                            controller_icao = line.split(maxsplit=1)[1].strip()
                        elif line.startswith("FACILITY_ID ") and not controller_icao:
                            controller_icao = line.split(maxsplit=1)[1].strip()
                        elif line.startswith("NAME "):
                            controller_name = line.split(maxsplit=1)[1].strip()
                        elif line.startswith("ROLE "):
                            controller_role = line.split(maxsplit=1)[1].strip()
                        elif line.startswith("FREQ "):
                            parts = line.split()
                            if len(parts) > 1:
                                freq_hz = parse_freq_to_hz(parts[1])
                                controller_freqs.append(freq_hz)
        except Exception:
            pass

    return facilities


def get_facility_by_freq(airport: AirportInfo, frequency_hz: Union[int, float]) -> Optional[Facility]:
    """Find ATC facility for an airport matching a given frequency."""
    freq_hz = parse_freq_to_hz(frequency_hz)

    # Check facilities mapping
    for role, f_hz in airport.facilities.items():
        if f_hz == freq_hz:
            norm_role = FacilityDict._normalize_key(role)
            name_map = {
                "TWR": "Tower",
                "GND": "Ground",
                "DEL": "Delivery",
                "ATIS": "ATIS",
                "APP": "Approach",
                "DEP": "Departure",
                "CTR": "Center",
            }
            display_role = name_map.get(norm_role, norm_role)
            facility_name = f"{airport.name} {display_role}" if airport.name else display_role
            return Facility(
                name=facility_name,
                role=norm_role,
                frequency_hz=freq_hz,
                facility_id=airport.icao,
            )

    return None
