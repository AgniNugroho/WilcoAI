from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Union, Any


class RunwayList(list):
    """List of Runway instances that supports lookup and containment by runway identifier string."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            clean = key.upper().replace("RWY", "").replace("RW", "")
            for r in self:
                if r.ident == key or r.name == key or r.ident == clean or r.ident.lstrip("0") == clean.lstrip("0"):
                    return r
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, Runway):
            return any(r == item for r in self)
        if isinstance(item, str):
            clean = item.upper().replace("RWY", "").replace("RW", "")
            return any(
                r.ident == item or r.name == item or r.ident == clean or r.ident.lstrip("0") == clean.lstrip("0")
                for r in self
            )
        return super().__contains__(item)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


@dataclass
class Runway:
    ident: str  # e.g. "11", "09", "29", "27"
    name: str = ""  # e.g. "RW11"
    elevation_ft: int = 0
    heading: Optional[float] = None
    ils_ident: Optional[str] = None
    lat: float = 0.0
    lon: float = 0.0
    length_m: Optional[float] = None

    def __post_init__(self) -> None:
        if not self.name:
            self.name = f"RW{self.ident}"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            clean = other.upper().replace("RWY", "").replace("RW", "")
            return (
                self.ident == other
                or self.name == other
                or self.ident == clean
                or self.ident.lstrip("0") == clean.lstrip("0")
            )
        if isinstance(other, Runway):
            return self.ident == other.ident
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.ident)


@dataclass
class SID:
    name: str  # e.g. "CA2L"
    runway: str = ""  # e.g. "RW11" or "11"
    waypoints: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.fixes and self.waypoints:
            self.fixes = list(self.waypoints)
        elif not self.waypoints and self.fixes:
            self.waypoints = list(self.fixes)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, str):
            return self.name == other
        if isinstance(other, SID):
            return self.name == other.name
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash(self.name)


class SidList(list):
    """List of SID instances that supports dict-like and string-containment operations."""

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, str):
            key_upper = key.upper()
            for s in self:
                if s.name.upper() == key_upper:
                    return s
            raise KeyError(key)
        return super().__getitem__(key)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, SID):
            return any(s == item for s in self)
        if isinstance(item, str):
            item_upper = item.upper()
            return any(s.name.upper() == item_upper for s in self)
        return super().__contains__(item)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except (KeyError, IndexError):
            return default

    def keys(self) -> list[str]:
        return [s.name for s in self]

    def values(self) -> list[SID]:
        return list(self)

    def items(self) -> list[tuple[str, SID]]:
        return [(s.name, s) for s in self]


class FacilityDict(dict):
    """Dictionary supporting standard ATC role aliases and case-insensitive access with synchronized mutation."""

    @staticmethod
    def _normalize_key(k: Any) -> str:
        s = str(k).strip().upper()
        mapping = {
            "TOWER": "TWR",
            "GROUND": "GND",
            "DELIVERY": "DEL",
            "CLEARANCE": "DEL",
            "APPROACH": "APP",
            "DEPARTURE": "DEP",
            "CENTER": "CTR",
            "CONTROL": "CTR",
        }
        return mapping.get(s, s)

    def __getitem__(self, key: Any) -> int:
        norm = self._normalize_key(key)
        for k, v in self.items():
            if self._normalize_key(k) == norm:
                return v
        return super().__getitem__(key)

    def __setitem__(self, key: Any, value: int) -> None:
        norm = self._normalize_key(key)
        # Update any existing alias keys matching the same normalized role
        for k in list(self.keys()):
            if self._normalize_key(k) == norm:
                super().__setitem__(k, value)
        super().__setitem__(key, value)
        if norm not in self:
            super().__setitem__(norm, value)

    def __delitem__(self, key: Any) -> None:
        norm = self._normalize_key(key)
        deleted = False
        for k in list(self.keys()):
            if self._normalize_key(k) == norm:
                super().__delitem__(k)
                deleted = True
        if not deleted:
            super().__delitem__(key)

    def __contains__(self, key: Any) -> bool:
        norm = self._normalize_key(key)
        for k in self.keys():
            if self._normalize_key(k) == norm:
                return True
        return super().__contains__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


@dataclass
class Facility:
    name: str
    role: str
    frequency_hz: int
    frequency_mhz: float = 0.0
    facility_id: str = ""

    def __post_init__(self) -> None:
        if not self.frequency_mhz and self.frequency_hz:
            self.frequency_mhz = round(self.frequency_hz / 1_000_000, 3)


@dataclass
class AirportInfo:
    icao: str
    name: str
    transition_alt: int
    runways: RunwayList = field(default_factory=RunwayList)
    facilities: Union[FacilityDict, dict[Any, Any]] = field(default_factory=FacilityDict)
    sids: SidList = field(default_factory=SidList)

    def __post_init__(self) -> None:
        if not isinstance(self.runways, RunwayList):
            self.runways = RunwayList(self.runways)
        if not isinstance(self.facilities, FacilityDict):
            fd = FacilityDict()
            fd.update(self.facilities)
            self.facilities = fd
        if not isinstance(self.sids, SidList):
            self.sids = SidList(self.sids)

    @property
    def tower_freq(self) -> Optional[int]:
        return self.facilities.get("TWR")

    @property
    def ground_freq(self) -> Optional[int]:
        return self.facilities.get("GND")

    @property
    def atis_freq(self) -> Optional[int]:
        return self.facilities.get("ATIS")

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, Runway):
            return item in self.runways
        if isinstance(item, SID):
            return item in self.sids
        if isinstance(item, Facility):
            return item.frequency_hz in self.facilities.values()
        if isinstance(item, str):
            return item in self.sids or item in self.runways or item in self.facilities
        return item in self.runways or item in self.sids
