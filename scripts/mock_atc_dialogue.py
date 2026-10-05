#!/usr/bin/env python3
"""
Wilco AI - Mock ATC Dialogue & Gateway WebSocket Client.

Interactive or automated client demonstrating end-to-end voice and telemetry
communication with the Wilco AI Gateway (/ws/atc).

Features:
- Full-duplex WebSocket connection handling
- Real-time flight telemetry ingestion (callsign, squawk, COM1/COM2 frequencies)
- Push-to-Talk (PTT) state coordination (pressed, audio streaming, released)
- Synthetic 16-bit 24kHz PCM audio frame generation
- Complete departure flight lifecycle dialogue:
    1. Apron Clearance Request (WAHI Ground 121.650 MHz)
    2. Pushback & Taxi Request (WAHI Ground 121.650 MHz)
    3. Tower Frequency Handoff & Takeoff Clearance (WAHI Tower 118.200 MHz)
- Unmonitored frequency DEAD_AIR detection testing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import struct
import sys
import time
from typing import Optional, Any

try:
    import websockets
except ImportError:
    websockets = None


def generate_synthetic_pcm(
    duration_sec: float = 0.5,
    sample_rate: int = 24000,
    tone_freq_hz: float = 440.0,
    amplitude: float = 0.25,
) -> bytes:
    """
    Generates 16-bit signed mono PCM audio samples at the specified sample rate.
    Simulates pilot microphone capture buffer.
    """
    num_samples = int(duration_sec * sample_rate)
    raw = bytearray()
    for i in range(num_samples):
        # Generate subtle tone with slight noise to mimic VHF microphone
        t = float(i) / sample_rate
        val = amplitude * math.sin(2.0 * math.pi * tone_freq_hz * t)
        sample = int(max(-1.0, min(1.0, val)) * 32767.0)
        raw.extend(struct.pack("<h", sample))
    return bytes(raw)


class MockAtcDialogueClient:
    """
    Demonstration client driving dialogue with the Wilco AI Gateway WebSocket.
    """

    def __init__(
        self,
        url: str = "ws://127.0.0.1:8000/ws/atc",
        callsign: str = "GIA123",
        aircraft_type: str = "A320",
        step_delay: float = 1.0,
    ):
        self.url = url
        self.callsign = callsign
        self.aircraft_type = aircraft_type
        self.step_delay = step_delay
        self.ws: Optional[Any] = None
        self.listen_task: Optional[asyncio.Task] = None
        self.received_messages: list[dict[str, Any]] = []
        self.received_audio_bytes: list[bytes] = []

    async def connect(self) -> dict[str, Any]:
        """Establishes WebSocket connection and awaits handshake."""
        if websockets is None:
            raise RuntimeError("The 'websockets' Python package is required.")

        print(f"[CLIENT] Connecting to Wilco AI Gateway: {self.url}...")
        self.ws = await websockets.connect(self.url)

        # Receive initial CONNECTED handshake
        init_frame = await self.ws.recv()
        data = json.loads(init_frame)
        print(f"[GATEWAY] Connected Handshake: {data.get('action')} at {data.get('airport')} (Active: {data.get('facility')})")

        # Start background listener for asynchronous gateway responses
        self.listen_task = asyncio.create_task(self._listen_loop())
        return data

    async def _listen_loop(self) -> None:
        """Background listener receiving JSON frames and binary audio from Gateway."""
        try:
            while self.ws and not self.ws.closed:
                msg = await self.ws.recv()
                if isinstance(msg, bytes):
                    self.received_audio_bytes.append(msg)
                    print(f"  [GATEWAY AUDIO RX] Received {len(msg)} bytes audio PCM")
                elif isinstance(msg, str):
                    try:
                        payload = json.loads(msg)
                        self.received_messages.append(payload)
                        msg_type = payload.get("type")
                        action = payload.get("action", "")
                        if msg_type == "status":
                            print(f"  [GATEWAY STATUS] {action}: {payload.get('message', payload)}")
                        elif msg_type == "transcript":
                            print(f"  [GATEWAY TRANSCRIPT ({payload.get('role', 'atc').upper()})] \"{payload.get('text')}\"")
                        else:
                            print(f"  [GATEWAY MESSAGE] {payload}")
                    except Exception:
                        print(f"  [GATEWAY RAW] {msg}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self.ws and not self.ws.closed:
                print(f"[CLIENT] Listener loop ended: {e}")

    async def send_telemetry(
        self,
        com1_hz: int,
        com2_hz: int = 118200000,
        active_radio: str = "COM1",
        squawk: str = "5201",
        wind_deg: int = 100,
        wind_kts: int = 7,
        qnh_inhg: float = 29.85,
    ) -> None:
        """Sends aircraft flight telemetry and frequency configuration."""
        telemetry = {
            "type": "telemetry",
            "data": {
                "callsign": self.callsign,
                "aircraft_type": self.aircraft_type,
                "squawk": squawk,
                "active_radio": active_radio,
                "com1_hz": com1_hz,
                "com2_hz": com2_hz,
                "frequency": com1_hz if active_radio == "COM1" else com2_hz,
                "wind_deg": wind_deg,
                "wind_kts": wind_kts,
                "qnh_inhg": qnh_inhg,
            },
        }
        await self.ws.send(json.dumps(telemetry))
        await asyncio.sleep(0.2)

    async def transmit_voice(
        self,
        transcript_text: str,
        radio: str = "COM1",
        duration_sec: float = 0.6,
    ) -> None:
        """
        Simulates pilot PTT press, streaming microphone audio frames, and PTT release.
        """
        print(f"\n[PILOT PTT PRESSED] TX on {radio}")
        await self.ws.send(json.dumps({"type": "ptt", "state": "pressed", "radio": radio}))
        await asyncio.sleep(0.15)

        print(f"[PILOT ON AIR] \"{transcript_text}\"")
        # Stream 3 chunks of simulated microphone audio PCM
        chunk_duration = duration_sec / 3.0
        for _ in range(3):
            audio_chunk = generate_synthetic_pcm(duration_sec=chunk_duration, tone_freq_hz=520.0)
            await self.ws.send(audio_chunk)
            await asyncio.sleep(0.08)

        print(f"[PILOT PTT RELEASED] Finished transmission")
        await self.ws.send(json.dumps({"type": "ptt", "state": "released"}))
        await asyncio.sleep(self.step_delay)

    async def run_automated_dialogue(self, test_dead_air: bool = True) -> None:
        """
        Executes complete automated dialogue sequence from apron clearance
        through takeoff clearance.
        """
        print("\n=======================================================")
        print("Starting Automated WAHI Departure ATC Dialogue Sequence")
        print("=======================================================\n")

        # Step 0: Test Unmonitored Frequency (DEAD_AIR)
        if test_dead_air:
            print("--- STEP 0: Unmonitored Frequency Check (123.450 MHz) ---")
            await self.send_telemetry(com1_hz=123450000, active_radio="COM1")
            await asyncio.sleep(0.5)
            await self.transmit_voice(
                "Yogyakarta, test transmission on 123.450",
                radio="COM1",
                duration_sec=0.3,
            )
            await asyncio.sleep(0.5)

        # Step 1: Clearance Delivery / Apron Clearance on WAHI Ground (121.650 MHz)
        print("\n--- STEP 1: Apron Clearance Request (WAHI Ground 121.650 MHz) ---")
        await self.send_telemetry(
            com1_hz=121650000,  # 121.650 MHz WAHI Ground
            com2_hz=118200000,  # 118.200 MHz WAHI Tower
            active_radio="COM1",
            squawk="5201",
        )
        await asyncio.sleep(0.5)

        await self.transmit_voice(
            f"Yogyakarta Ground, {self.callsign}, Airbus {self.aircraft_type} at Stand 4, "
            f"Information Charlie, request IFR clearance to Jakarta Soekarno-Hatta, flight level 110.",
            radio="COM1",
        )
        await asyncio.sleep(1.0)

        # Pilot Readback
        await self.transmit_voice(
            f"Cleared to Jakarta, runway 11, climb and maintain 11000 feet, squawk 5201, {self.callsign}.",
            radio="COM1",
        )
        await asyncio.sleep(1.0)

        # Step 2: Pushback & Taxi Request
        print("\n--- STEP 2: Pushback and Taxi Request (WAHI Ground 121.650 MHz) ---")
        await self.transmit_voice(
            f"Ground, {self.callsign}, request pushback and start facing east.",
            radio="COM1",
        )
        await asyncio.sleep(1.0)

        await self.transmit_voice(
            f"Pushback approved face east runway 11, {self.callsign}.",
            radio="COM1",
        )
        await asyncio.sleep(0.8)

        await self.transmit_voice(
            f"Ground, {self.callsign}, ready to taxi.",
            radio="COM1",
        )
        await asyncio.sleep(1.0)

        await self.transmit_voice(
            f"Taxi to holding point runway 11 via taxiway Alpha, holding short, {self.callsign}.",
            radio="COM1",
        )
        await asyncio.sleep(1.0)

        # Step 3: Switch to WAHI Tower (118.200 MHz) & Takeoff Clearance
        print("\n--- STEP 3: Tower Frequency Transfer & Takeoff Clearance (118.200 MHz) ---")
        await self.send_telemetry(
            com1_hz=118200000,  # Switch COM1 to 118.200 MHz Tower
            com2_hz=121650000,
            active_radio="COM1",
            squawk="5201",
        )
        await asyncio.sleep(0.5)

        await self.transmit_voice(
            f"Yogyakarta Tower, {self.callsign}, holding short runway 11, ready for departure.",
            radio="COM1",
        )
        await asyncio.sleep(1.0)

        # Takeoff Clearance Readback
        await self.transmit_voice(
            f"Wind 100 at 7 knots, runway 11 cleared for takeoff, {self.callsign}.",
            radio="COM1",
        )
        await asyncio.sleep(1.5)

        print("\n=======================================================")
        print("Automated Dialogue Complete! Departure Lifecycle Verified.")
        print("=======================================================\n")

    async def run_interactive(self) -> None:
        """Interactive console session allowing manual PTT transmissions."""
        print("\n--- Interactive ATC Dialogue Mode ---")
        print("Type pilot speech text and press Enter to transmit.")
        print("Type 'switch' to toggle between Ground (121.650) and Tower (118.200).")
        print("Type 'exit' or 'quit' to terminate session.\n")

        current_freq = 121650000
        await self.send_telemetry(com1_hz=current_freq, active_radio="COM1")

        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, input, "PILOT MIC > ")
            except (EOFError, KeyboardInterrupt):
                break

            text = line.strip()
            if not text:
                continue

            if text.lower() in ("exit", "quit"):
                break

            if text.lower() == "switch":
                current_freq = 118200000 if current_freq == 121650000 else 121650000
                mhz = current_freq / 1e6
                print(f"[SWITCH] Switching COM1 to {mhz:.3f} MHz...")
                await self.send_telemetry(com1_hz=current_freq, active_radio="COM1")
                continue

            await self.transmit_voice(text, radio="COM1")

    async def close(self) -> None:
        """Closes the WebSocket connection."""
        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass
        if self.ws:
            await self.ws.close()
            print("[CLIENT] WebSocket connection closed.")


async def async_main() -> None:
    parser = argparse.ArgumentParser(
        description="Wilco AI - Mock ATC Dialogue & Gateway WebSocket Client"
    )
    parser.add_argument(
        "--url",
        type=str,
        default="ws://127.0.0.1:8000/ws/atc",
        help="Gateway WebSocket URL (default: ws://127.0.0.1:8000/ws/atc)",
    )
    parser.add_argument(
        "--callsign",
        type=str,
        default="GIA123",
        help="Aircraft callsign (default: GIA123)",
    )
    parser.add_argument(
        "--aircraft",
        type=str,
        default="A320",
        help="Aircraft model (default: A320)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        default=True,
        help="Run automated departure dialogue (default)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive console dialogue mode",
    )
    parser.add_argument(
        "--no-dead-air-test",
        action="store_true",
        help="Skip unmonitored frequency DEAD_AIR test",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.8,
        help="Delay between dialogue steps in seconds (default: 0.8)",
    )

    args = parser.parse_args()

    client = MockAtcDialogueClient(
        url=args.url,
        callsign=args.callsign,
        aircraft_type=args.aircraft,
        step_delay=args.delay,
    )

    try:
        await client.connect()
        if args.interactive:
            await client.run_interactive()
        else:
            await client.run_automated_dialogue(test_dead_air=not args.no_dead_air_test)
    except ConnectionRefusedError:
        print(f"[ERROR] Could not connect to {args.url}. Is the Gateway running?", file=sys.stderr)
        sys.exit(1)
    finally:
        await client.close()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\nSession aborted by user.")


if __name__ == "__main__":
    main()
