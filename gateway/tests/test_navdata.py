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


def test_airport_info_contains_objects():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")
    rw11 = airport.runways["11"]
    sid_ca2l = airport.sids["CA2L"]
    twr_facility = get_facility_by_freq(airport, 118200000)

    # Object containment
    assert rw11 in airport
    assert sid_ca2l in airport
    assert twr_facility in airport

    # Foreign objects should not be contained
    foreign_rwy = Runway(ident="99")
    foreign_sid = SID(name="ZZZZ1A")
    foreign_fac = Facility(name="Unknown Tower", role="TWR", frequency_hz=139000000)
    assert foreign_rwy not in airport
    assert foreign_sid not in airport
    assert foreign_fac not in airport


def test_facility_dict_mutation_and_alias_sync():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")

    # Mutation with alias name 'Tower' should update 'TWR', 'twr', etc.
    airport.facilities["Tower"] = 119500000
    assert airport.facilities["TWR"] == 119500000
    assert airport.facilities["twr"] == 119500000
    assert airport.facilities["Tower"] == 119500000

    # Mutation with code 'GND' should update 'Ground', 'gnd', etc.
    airport.facilities["GND"] = 121800000
    assert airport.facilities["Ground"] == 121800000
    assert airport.facilities["gnd"] == 121800000


def test_runway_and_sid_hashability():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")
    rw11 = airport.runways["11"]
    rw29 = airport.runways["29"]
    sid_ca2l = airport.sids["CA2L"]
    sid_clp2f = airport.sids["CLP2F"]

    # Must be hashable in sets
    runway_set = {rw11, rw29}
    assert len(runway_set) == 2
    assert rw11 in runway_set

    sid_set = {sid_ca2l, sid_clp2f}
    assert len(sid_set) == 2
    assert sid_ca2l in sid_set

    # Must be usable as dict keys
    data = {rw11: "Runway 11", sid_ca2l: "Departure CA2L"}
    assert data[rw11] == "Runway 11"
    assert data[sid_ca2l] == "Departure CA2L"


def test_list_get_with_index_out_of_bounds():
    airport = load_airport(CUSTOM_DATA_PATH, "WAHI")

    # Integer index out of bounds should return default without raising IndexError
    assert airport.runways.get(999) is None
    assert airport.runways.get(999, default="NOT_FOUND") == "NOT_FOUND"

    assert airport.sids.get(999) is None
    assert airport.sids.get(999, default="NOT_FOUND") == "NOT_FOUND"

    # Valid integer index should return the item
    assert airport.runways.get(0) is not None
    assert airport.sids.get(0) is not None

