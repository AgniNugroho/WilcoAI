from __future__ import annotations
from pathlib import Path
from typing import Optional, Union

from navdata.models import (
    AirportInfo,
    Facility,
    FacilityDict,
    Runway,
    RunwayList,
    SID,
    SidList,
)
from navdata.atc_parser import (
    DEFAULT_AIRPORT_FACILITIES,
    DEFAULT_AIRPORT_NAMES,
    get_facility_by_freq,
    parse_atc_facilities,
    parse_freq_to_hz,
)
from navdata.cifp_parser import (
    parse_arinc_coords,
    parse_cifp,
    parse_transition_altitude,
)


def load_airport(custom_data_path: Union[str, Path], icao: str) -> AirportInfo:
    """
    Load real airport navigation data, ATC controller facilities,
    frequencies, runways, transition altitude, and SIDs.

    Supports ICAO 'WARJ' alias to 'WAHI' (Yogyakarta International Airport).
    """
    target_icao = icao.strip().upper()
    resolved_icao = "WAHI" if target_icao == "WARJ" else target_icao

    # Parse CIFP data (runways, SIDs, transition altitude)
    runways, sids, transition_alt = parse_cifp(custom_data_path, resolved_icao)

    # Parse ATC facilities from atc.dat and regional defaults
    facilities = parse_atc_facilities(custom_data_path, resolved_icao)

    # Resolve friendly airport name
    airport_name = DEFAULT_AIRPORT_NAMES.get(
        resolved_icao, f"Airport {resolved_icao}"
    )

    return AirportInfo(
        icao=resolved_icao,
        name=airport_name,
        transition_alt=transition_alt,
        runways=runways,
        facilities=facilities,
        sids=sids,
    )


__all__ = [
    "AirportInfo",
    "Facility",
    "FacilityDict",
    "Runway",
    "RunwayList",
    "SID",
    "SidList",
    "load_airport",
    "get_facility_by_freq",
    "parse_atc_facilities",
    "parse_cifp",
    "parse_freq_to_hz",
    "parse_transition_altitude",
]
