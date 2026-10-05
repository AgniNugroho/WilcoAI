#!/usr/bin/env python3
"""
Wilco AI - Mock X-Plane 12 UDP Telemetry & Dataref Broadcaster.

Simulates X-Plane 12 binary UDP dataref broadcasting conforming to the
Laminar Research UDP network specification and Wilco AI client ingestion format.

Supported Packet Protocol:
- Header: 6 bytes `RREF,\0` (or 5 bytes `RREF\0`)
- Records: Array of 8-byte chunks (4-byte int32 index LE, 4-byte float32 value LE)
- Client DREF parsing: 5 bytes `DREF\0`, 4-byte float32 LE, 500-byte dataref string

Monitored Datarefs (matching client/src-tauri/src/xplane/mod.rs):
  IDX 1:  COM1 frequency (Hz)
  IDX 2:  COM2 frequency (Hz)
  IDX 3:  Active radio audio selector (6 for COM1, 7 for COM2)
  IDX 4:  Latitude (degrees)
  IDX 5:  Longitude (degrees)
  IDX 6:  Elevation MSL (meters)
  IDX 7:  Radio Altitude AGL (meters)
  IDX 8:  Weight on wheels / on ground (1.0 or 0.0)
  IDX 9:  Transponder squawk code (e.g. 5201.0)
  IDX 10: Barometer pilot setting (inHg, e.g. 29.85)
  IDX 11: Groundspeed (m/s)
  IDX 12: Wind speed (kts)
  IDX 13: Wind direction (degrees)
"""

from __future__ import annotations

import argparse
import select
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Optional, Union, Any

# Dataref index mapping matching client/src-tauri/src/xplane/mod.rs
IDX_COM1_FREQ = 1
IDX_COM2_FREQ = 2
IDX_AUDIO_COM_SELECTION = 3
IDX_LATITUDE = 4
IDX_LONGITUDE = 5
IDX_ELEVATION = 6
IDX_Y_AGL = 7
IDX_ON_GROUND = 8
IDX_TRANSPONDER_CODE = 9
IDX_BAROMETER_PILOT = 10
IDX_GROUNDSPEED = 11
IDX_WIND_SPEED = 12
IDX_WIND_DIR = 13

DREF_ATC_VOLUME_RATIO = "sim/operation/sound/radio_atc_volume_ratio"

RREF_HEADER = b"RREF,\0"
RREF_HEADER_5 = b"RREF\0"
DREF_HEADER = b"DREF\0"


@dataclass
class XPlaneSnapshot:
    """Aircraft state snapshot broadcasted via X-Plane UDP datarefs."""
    com1_hz: float = 121650000.0       # 121.650 MHz WAHI Ground
    com2_hz: float = 118200000.0       # 118.200 MHz WAHI Tower
    active_radio_code: float = 6.0     # 6 = COM1, 7 = COM2
    latitude: float = -7.9042
    longitude: float = 110.0528
    elevation_m: float = 7.3
    agl_m: float = 0.0
    on_ground: float = 1.0             # 1.0 = true, 0.0 = false
    squawk: float = 5201.0
    qnh_inhg: float = 29.85            # 1011 hPa
    groundspeed_ms: float = 0.0
    wind_speed_kts: float = 7.0
    wind_dir_deg: float = 100.0

    def to_records(self) -> list[tuple[int, float]]:
        """Converts snapshot to (index, value) tuples."""
        return [
            (IDX_COM1_FREQ, float(self.com1_hz)),
            (IDX_COM2_FREQ, float(self.com2_hz)),
            (IDX_AUDIO_COM_SELECTION, float(self.active_radio_code)),
            (IDX_LATITUDE, float(self.latitude)),
            (IDX_LONGITUDE, float(self.longitude)),
            (IDX_ELEVATION, float(self.elevation_m)),
            (IDX_Y_AGL, float(self.agl_m)),
            (IDX_ON_GROUND, float(self.on_ground)),
            (IDX_TRANSPONDER_CODE, float(self.squawk)),
            (IDX_BAROMETER_PILOT, float(self.qnh_inhg)),
            (IDX_GROUNDSPEED, float(self.groundspeed_ms)),
            (IDX_WIND_SPEED, float(self.wind_speed_kts)),
            (IDX_WIND_DIR, float(self.wind_dir_deg)),
        ]


def build_rref_packet(
    records: list[tuple[int, float]],
    header: bytes = RREF_HEADER,
) -> bytes:
    """
    Encodes records into an X-Plane RREF response binary payload.
    Header: 6 bytes `RREF,\0` or 5 bytes `RREF\0`.
    Each record: 8 bytes (i32 index LE, f32 value LE).
    """
    payload = bytearray(header)
    for idx, val in records:
        payload.extend(struct.pack("<if", int(idx), float(val)))
    return bytes(payload)


def parse_rref_packet(data: bytes) -> list[tuple[int, float]]:
    """
    Decodes an X-Plane RREF binary payload into (index, value) pairs.
    Handles 4, 5, or 6 byte headers.
    """
    if len(data) < 5 or not data.startswith(b"RREF"):
        return []

    if len(data) >= 6 and data[:6] == b"RREF,\0":
        offset = 6
    elif (len(data) - 5) % 8 == 0:
        offset = 5
    elif len(data) >= 6 and (len(data) - 6) % 8 == 0:
        offset = 6
    elif (len(data) - 4) % 8 == 0:
        offset = 4
    else:
        offset = 5

    remaining = data[offset:]
    num_records = len(remaining) // 8
    records: list[tuple[int, float]] = []
    for i in range(num_records):
        chunk = remaining[i * 8 : (i + 1) * 8]
        idx, val = struct.unpack("<if", chunk)
        records.append((idx, val))
    return records


def parse_dref_packet(data: bytes) -> Optional[tuple[float, str]]:
    """
    Decodes an incoming X-Plane DREF write command packet.
    Layout: 5 bytes `DREF\0`, 4 bytes float LE, 500 bytes null-padded name string.
    """
    if len(data) < 9 or not data.startswith(b"DREF"):
        return None

    offset = 5 if data[4:5] == b"\x00" else 4
    val = struct.unpack("<f", data[offset : offset + 4])[0]
    name_bytes = data[offset + 4 :]
    name = name_bytes.split(b"\x00", 1)[0].decode("ascii", errors="replace")
    return val, name


# Predefined flight phases for departure_wahi scenario
DEPARTURE_WAHI_WAYPOINTS: list[tuple[str, XPlaneSnapshot, float]] = [
    # (Label, Snapshot, Duration in seconds)
    (
        "RAMP_STAND",
        XPlaneSnapshot(
            com1_hz=121650000.0,  # 121.650 WAHI Ground
            com2_hz=118200000.0,  # 118.200 WAHI Tower
            active_radio_code=6.0,  # COM1
            latitude=-7.9042,
            longitude=110.0528,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=0.0,
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        2.0,
    ),
    (
        "PUSHBACK",
        XPlaneSnapshot(
            com1_hz=121650000.0,
            com2_hz=118200000.0,
            active_radio_code=6.0,
            latitude=-7.9045,
            longitude=110.0522,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=1.5,
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        2.0,
    ),
    (
        "TAXI_TO_RUNWAY",
        XPlaneSnapshot(
            com1_hz=121650000.0,
            com2_hz=118200000.0,
            active_radio_code=6.0,
            latitude=-7.9036,
            longitude=110.0488,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=6.5,
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        2.5,
    ),
    (
        "HOLDING_SHORT",
        XPlaneSnapshot(
            com1_hz=118200000.0,  # Switched to WAHI Tower 118.200
            com2_hz=121650000.0,  # COM2 Ground
            active_radio_code=6.0,
            latitude=-7.9025,
            longitude=110.0460,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=0.0,
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        2.0,
    ),
    (
        "LINE_UP_RW11",
        XPlaneSnapshot(
            com1_hz=118200000.0,
            com2_hz=121650000.0,
            active_radio_code=6.0,
            latitude=-7.9023,
            longitude=110.0465,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=2.0,
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        1.5,
    ),
    (
        "TAKEOFF_ROLL",
        XPlaneSnapshot(
            com1_hz=118200000.0,
            com2_hz=121650000.0,
            active_radio_code=6.0,
            latitude=-7.9032,
            longitude=110.0535,
            elevation_m=7.3,
            agl_m=0.0,
            on_ground=1.0,
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=45.0,  # ~88 knots
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        2.0,
    ),
    (
        "AIRBORNE_CLIMB",
        XPlaneSnapshot(
            com1_hz=118200000.0,
            com2_hz=121650000.0,
            active_radio_code=6.0,
            latitude=-7.9048,
            longitude=110.0640,
            elevation_m=65.0,
            agl_m=57.7,
            on_ground=0.0,  # Airborne
            squawk=5201.0,
            qnh_inhg=29.85,
            groundspeed_ms=72.0,  # ~140 knots
            wind_speed_kts=7.0,
            wind_dir_deg=100.0,
        ),
        2.0,
    ),
]


class MockXPlaneSender:
    """
    Mock X-Plane 12 UDP dataref broadcasting service.
    Binds to a UDP port (e.g. 49000), accepts client commands, and
    broadcasts simulated aircraft telemetry snapshots.
    """

    def __init__(
        self,
        listen_host: str = "127.0.0.1",
        listen_port: int = 49000,
        target_host: str = "127.0.0.1",
        target_port: Optional[int] = None,
        rate_hz: float = 10.0,
    ):
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.rate_hz = rate_hz
        self.interval_sec = 1.0 / max(rate_hz, 0.1)

        self.sock: Optional[socket.socket] = None
        self.known_client_addr: Optional[tuple[str, int]] = (
            (target_host, target_port) if target_port else None
        )
        self.mute_command_received = False
        self.last_mute_value: Optional[float] = None
        self.received_drefs: list[tuple[float, str]] = []
        self.received_subscriptions: list[tuple[int, int, str]] = []
        self.packets_sent = 0

    def start_socket(self) -> None:
        """Initializes and binds the UDP socket."""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.listen_host, self.listen_port))
        self.sock.setblocking(False)

    def close(self) -> None:
        """Closes the active socket."""
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def poll_incoming(self) -> int:
        """
        Polls non-blocking for incoming datagrams (DREF mute, RREF subscriptions).
        Returns number of packets processed.
        """
        if not self.sock:
            return 0

        packets_read = 0
        while True:
            try:
                data, addr = self.sock.recvfrom(2048)
            except BlockingIOError:
                break
            except Exception:
                break

            packets_read += 1
            if self.known_client_addr is None:
                self.known_client_addr = addr

            # Check DREF command
            dref_res = parse_dref_packet(data)
            if dref_res:
                val, name = dref_res
                self.received_drefs.append((val, name))
                if name == DREF_ATC_VOLUME_RATIO:
                    self.mute_command_received = True
                    self.last_mute_value = val
                continue

            # Check RREF subscription request
            if data.startswith(b"RREF\0") and len(data) >= 13:
                freq, idx = struct.unpack("<ii", data[5:13])
                name = data[13:].split(b"\x00", 1)[0].decode("ascii", errors="replace")
                self.received_subscriptions.append((freq, idx, name))

        return packets_read

    def send_snapshot(
        self,
        snapshot: XPlaneSnapshot,
        target_addr: Optional[tuple[str, int]] = None,
    ) -> bool:
        """Encodes and transmits a single snapshot to destination."""
        if not self.sock:
            return False

        dest = target_addr or self.known_client_addr
        if not dest:
            return False

        payload = build_rref_packet(snapshot.to_records())
        try:
            self.sock.sendto(payload, dest)
            self.packets_sent += 1
            return True
        except Exception as exc:
            print(f"[MockXPlane] Error transmitting UDP packet: {exc}", file=sys.stderr)
            return False

    def run_scenario(
        self,
        scenario_name: str = "departure_wahi",
        count: Optional[int] = None,
        once: bool = False,
        verbose: bool = False,
        loop: bool = False,
    ) -> None:
        """Executes a simulation scenario broadcasting telemetry over UDP."""
        self.start_socket()
        print(f"[MockXPlane] UDP Server listening on {self.listen_host}:{self.listen_port}")
        if self.known_client_addr:
            print(f"[MockXPlane] Destination target set to {self.known_client_addr[0]}:{self.known_client_addr[1]}")
        else:
            print(f"[MockXPlane] Waiting for client connection or incoming subscription on port {self.listen_port}...")

        waypoints = (
            DEPARTURE_WAHI_WAYPOINTS
            if scenario_name == "departure_wahi"
            else [("STATIC_RAMP", DEPARTURE_WAHI_WAYPOINTS[0][1], 999999.0)]
        )

        total_sent = 0
        try:
            # If no target was specified, pause at initial waypoint until a client connects
            if self.known_client_addr is None and not (once and self.target_port):
                initial_phase_name = waypoints[0][0]
                print(f"[MockXPlane] Aircraft parked at {initial_phase_name}. Awaiting client UDP connection...")
                wait_log_interval = 3.0
                last_wait_log = time.time()
                while self.known_client_addr is None:
                    self.poll_incoming()
                    if self.known_client_addr is not None:
                        print(
                            f"[MockXPlane] Client connected from "
                            f"{self.known_client_addr[0]}:{self.known_client_addr[1]}! "
                            f"Commencing scenario '{scenario_name}'."
                        )
                        break
                    time.sleep(0.05)
                    if time.time() - last_wait_log >= wait_log_interval:
                        if verbose:
                            print(f"[MockXPlane] Still waiting for client on port {self.listen_port}...")
                        last_wait_log = time.time()

            scenario_active = True
            while scenario_active:
                for phase_name, snapshot, duration in waypoints:
                    phase_start = time.time()
                    print(
                        f"\n>>> [PHASE: {phase_name}] COM1: {snapshot.com1_hz / 1e6:.3f} MHz | "
                        f"COM2: {snapshot.com2_hz / 1e6:.3f} MHz | Radio: COM{int(snapshot.active_radio_code) - 5} | "
                        f"Alt AGL: {snapshot.agl_m:.1f}m | Spd: {snapshot.groundspeed_ms:.1f} m/s | "
                        f"Ground: {bool(snapshot.on_ground)}"
                    )

                    while time.time() - phase_start < duration:
                        # Ingest any incoming mute or subscription commands
                        self.poll_incoming()

                        if self.mute_command_received and self.last_mute_value is not None:
                            action = "MUTED (0.0)" if self.last_mute_value == 0.0 else f"UNMUTED ({self.last_mute_value})"
                            # Print once per transition
                            if verbose:
                                print(f"[MockXPlane] Native ATC Audio {action}")

                        if self.known_client_addr:
                            sent = self.send_snapshot(snapshot)
                            if sent:
                                total_sent += 1
                                if verbose:
                                    print(
                                        f"  -> Sent 110-byte RREF packet #{total_sent} to "
                                        f"{self.known_client_addr[0]}:{self.known_client_addr[1]}"
                                    )

                        if once:
                            print("[MockXPlane] Single packet transmission complete (--once).")
                            return

                        if count and total_sent >= count:
                            print(f"[MockXPlane] Reached packet count limit ({count}). Exiting.")
                            return

                        time.sleep(self.interval_sec)

                if not loop:
                    scenario_active = False
                else:
                    print("\n[MockXPlane] Scenario iteration complete. Looping from start (--loop)...")

        except KeyboardInterrupt:
            print("\n[MockXPlane] Simulation interrupted by user.")
        finally:
            self.close()
            print(f"[MockXPlane] Terminated. Total packets sent: {total_sent}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wilco AI - Mock X-Plane 12 UDP Telemetry & Dataref Broadcaster"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="departure_wahi",
        help="Simulation scenario (default: departure_wahi)",
    )
    parser.add_argument(
        "--listen-port",
        type=int,
        default=49000,
        help="UDP listen port (default: 49000)",
    )
    parser.add_argument(
        "--target-port",
        type=int,
        default=None,
        help="Target client UDP port (optional; defaults to sender port)",
    )
    parser.add_argument(
        "--target-host",
        type=str,
        default="127.0.0.1",
        help="Target client host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=10.0,
        help="Telemetry broadcast frequency in Hz (default: 10.0)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of packets to transmit before exiting",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Send a single packet and exit",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Continuously loop the scenario sequence until interrupted",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args()

    sender = MockXPlaneSender(
        listen_host="127.0.0.1",
        listen_port=args.listen_port,
        target_host=args.target_host,
        target_port=args.target_port,
        rate_hz=args.rate,
    )

    sender.run_scenario(
        scenario_name=args.scenario,
        count=args.count,
        once=args.once,
        verbose=args.verbose,
        loop=args.loop,
    )


if __name__ == "__main__":
    main()
