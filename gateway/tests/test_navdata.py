from pathlib import Path
import pytest

from navdata import (
    AirportInfo,
    Facility,
    Runway,
    SID,
    load_airport,
    get_facility_by_freq,
)

CUSTOM_DATA_PATH = r"D:\SteamLibrary\steamapps\common\X-Plane 12\Custom Data"


def test_load_airport_wahi():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")

    assert isinstance(airport, AirportInfo)
    assert airport.icao == "WAHI"
    assert "Yogyakarta" in airport.name
    assert airport.transition_alt == 11000

    # Facilities & Frequencies
    assert airport.facilities["TWR"] == 118200000
    assert airport.facilities["GND"] == 121650000
    assert airport.tower_freq == 118200000
    assert airport.ground_freq == 121650000

    # Runways
    runway_idents = [r.ident for r in airport.runways]
    assert "11" in runway_idents
    assert "29" in runway_idents
    assert "11" in airport.runways
    assert "RW11" in airport.runways
    rw11 = airport.runways["11"]
    assert rw11.elevation_ft == 24
    assert rw11.ils_ident == "IKLP"
    assert round(rw11.lat, 2) == -7.90
    assert round(rw11.lon, 2) == 110.04

    # SIDs
    assert "CA2L" in airport.sids
    assert "CLP2F" in airport.sids
    assert "CA2L" in airport
    assert "NASWA" in airport.sids["CA2L"].waypoints
    assert "CA" in airport.sids["CA2L"].waypoints


def test_load_airport_wahh():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHH")

    assert isinstance(airport, AirportInfo)
    assert airport.icao == "WAHH"
    assert "Adisutjipto" in airport.name
    assert airport.transition_alt == 11000

    # Facilities & Frequencies
    assert airport.facilities["TWR"] == 118100000
    assert airport.facilities["GND"] == 121900000
    assert airport.tower_freq == 118100000
    assert airport.ground_freq == 121900000

    # Runways
    runway_idents = [r.ident for r in airport.runways]
    assert "09" in runway_idents
    assert "27" in runway_idents
    rw09 = airport.runways["09"]
    assert rw09.elevation_ft == 374
    assert rw09.ils_ident == "IJOG"

    # SIDs
    assert "LILP1A" in airport.sids
    assert "YOGY1A" in airport.sids


def test_warj_alias_to_wahi():
    # WARJ should alias to WAHI (Yogyakarta International Airport)
    airport = load_airport(CUSTOM_DATA_PATH, "WARJ")

    assert airport.icao in ("WAHI", "WARJ")
    assert "Yogyakarta" in airport.name
    assert airport.facilities["TWR"] == 118200000
    assert airport.facilities["GND"] == 121650000
    assert "CA2L" in airport.sids


def test_get_facility_by_freq():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")

    # In Hz
    twr_facility = get_facility_by_freq(airport, 118200000)
    assert twr_facility is not None
    assert isinstance(twr_facility, Facility)
    assert twr_facility.role in ("TWR", "Tower", "twr")
    assert twr_facility.frequency_hz == 118200000
    assert twr_facility.frequency_mhz == 118.2

    gnd_facility = get_facility_by_freq(airport, 121650000)
    assert gnd_facility is not None
    assert gnd_facility.role in ("GND", "Ground", "gnd")
    assert gnd_facility.frequency_hz == 121650000
    assert gnd_facility.frequency_mhz == 121.65

    # In MHz
    twr_mhz = get_facility_by_freq(airport, 118.200)
    assert twr_mhz is not None
    assert twr_mhz.frequency_hz == 118200000

    # Unknown frequency returns None
    assert get_facility_by_freq(airport, 135000000) is None


def test_facility_dict_case_insensitivity():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")

    assert airport.facilities["Tower"] == 118200000
    assert airport.facilities["twr"] == 118200000
    assert airport.facilities["Ground"] == 121650000
    assert airport.facilities["gnd"] == 121650000
    assert "Tower" in airport.facilities
    assert "Ground" in airport.facilities


def test_load_airport_not_found():
    with pytest.raises(FileNotFoundError):
        load_airport(CUSTOM_DATA_PATH, "ZZZZ")
