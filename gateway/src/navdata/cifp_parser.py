from __future__ import annotations
from pathlib import Path
from typing import Optional, Union

from .models import Runway, RunwayList, SID, SidList


def parse_arinc_coords(lat_s: str, lon_s: str) -> tuple[float, float]:
    """Parse ARINC 424 formatted coordinates (e.g. S07540093, E110023628)."""
    try:
        lat_s = lat_s.strip()
        lon_s = lon_s.strip()
        lat_sign = -1.0 if lat_s[0] == "S" else 1.0
        lat_deg = int(lat_s[1:3])
        lat_min = int(lat_s[3:5])
        lat_sec = float(lat_s[5:]) / 100.0
        lat = lat_sign * (lat_deg + lat_min / 60.0 + lat_sec / 3600.0)

        lon_sign = -1.0 if lon_s[0] == "W" else 1.0
        lon_deg = int(lon_s[1:4])
        lon_min = int(lon_s[4:6])
        lon_sec = float(lon_s[6:]) / 100.0
        lon = lon_sign * (lon_deg + lon_min / 60.0 + lon_sec / 3600.0)
        return round(lat, 6), round(lon, 6)
    except Exception:
        return 0.0, 0.0


def parse_transition_altitude(custom_data_path: Union[str, Path], icao: str) -> int:
    """Extract transition altitude from earth_aptmeta.dat or fallback default."""
    path = Path(custom_data_path)
    meta_path = path / "earth_aptmeta.dat"
    target_icao = icao.upper()
    if target_icao == "WARJ":
        target_icao = "WAHI"

    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith(target_icao):
                        parts = line.split()
                        if "I" in parts:
                            idx = parts.index("I")
                            if idx + 1 < len(parts) and parts[idx + 1].isdigit():
                                return int(parts[idx + 1])
        except Exception:
            pass

    # Regional default
    return 11000


def parse_cifp(
    custom_data_path: Union[str, Path], icao: str
) -> tuple[RunwayList, SidList, int]:
    """
    Parse ARINC 424 CIFP file for runway identifiers, SIDs, waypoints,
    and transition altitude.
    """
    path = Path(custom_data_path)
    target_icao = icao.upper()
    if target_icao == "WARJ":
        target_icao = "WAHI"

    cifp_candidates = [
        path / "CIFP" / f"{target_icao}.dat",
        path / f"{target_icao}.dat",
    ]

    cifp_file: Optional[Path] = None
    for cand in cifp_candidates:
        if cand.exists():
            cifp_file = cand
            break

    if cifp_file is None:
        raise FileNotFoundError(
            f"CIFP navigation data for ICAO '{icao}' not found in '{custom_data_path}'"
        )

    runways = RunwayList()
    sids_dict: dict[str, SID] = {}
    sid_trans_alt: Optional[int] = None

    with open(cifp_file, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            # Runway records: RWY:RW11 , ... ;S07540093,E110023628,...;
            if line.startswith("RWY:"):
                parts = line.split(";")[0].split(",")
                raw_ident = parts[0].split(":")[1].strip()
                ident = raw_ident[2:] if raw_ident.startswith("RW") else raw_ident
                elev = int(parts[3].strip()) if len(parts) > 3 and parts[3].strip().isdigit() else 0
                ils = parts[5].strip() if len(parts) > 5 and parts[5].strip() else None

                lat, lon = 0.0, 0.0
                if ";" in line:
                    coord_parts = line.split(";")[1].split(",")
                    if len(coord_parts) >= 2:
                        lat, lon = parse_arinc_coords(coord_parts[0], coord_parts[1])

                runway = Runway(
                    ident=ident,
                    name=raw_ident,
                    elevation_ft=elev,
                    ils_ident=ils,
                    lat=lat,
                    lon=lon,
                )
                if runway not in runways:
                    runways.append(runway)

            # SID records: SID:010,5,CA2L,RW11,...
            elif line.startswith("SID:"):
                parts = [p.strip() for p in line.split(";")[0].split(",")]
                if len(parts) >= 4:
                    sid_name = parts[2]
                    rwy = parts[3]
                    fix = parts[4] if len(parts) > 4 else ""

                    # Check for transition altitude indicator in first leg
                    if len(parts) > 23 and parts[23].isdigit() and sid_trans_alt is None:
                        val = int(parts[23])
                        if val > 1000:
                            sid_trans_alt = val

                    if sid_name not in sids_dict:
                        sids_dict[sid_name] = SID(name=sid_name, runway=rwy)

                    if fix and fix not in sids_dict[sid_name].waypoints:
                        sids_dict[sid_name].waypoints.append(fix)
                        sids_dict[sid_name].fixes.append(fix)

    sids = SidList(sids_dict.values())
    trans_alt = parse_transition_altitude(path, target_icao)

    return runways, sids, trans_alt
