"""
Battery Simulator — impersonates a Shimano BT-E6000 battery on the UART bus.

Listens for charger handshakes and polls, responds with correct protocol messages.
All charging logic is simulated; no real battery is connected.
"""

import struct
import time
from datetime import datetime

from message import Msg, MsgStatus
from message_dispatcher import MessageDirection, MessageDispatcher


# Charger sender addresses
CHARGER_HANDSHAKE_BASE = 0x40  # 0x40..0x43
CHARGER_POLL_BASE = 0x00       # 0x00..0x03

# Battery sender addresses
BATTERY_HANDSHAKE_BASE = 0xC0  # 0xC0..0xC3
BATTERY_TELEMETRY_BASE = 0x80  # 0x80..0x83

CMD_TELEMETRY = 0x10


class BatteryState:
    """Simulated battery telemetry values."""

    def __init__(self):
        # State machine: 0x00=Init, 0x02=Precharge, 0x03=Charging
        self.state: int = 0x00
        self.state_time: float = time.monotonic()

        # Configurable telemetry
        self.pack_voltage_mv: int = 38300       # ~61% SOC for 10S
        self.cell_v_max_half_mv: int = 7660     # 3830 mV * 2
        self.cell_v_min_half_mv: int = 7656     # 3828 mV * 2
        self.ntc_max: int = 22                  # °C
        self.ntc_avg: int = 21                  # °C
        self.th002_mosfet: int = 22             # °C
        self.soc_percent: int = 62              # %
        self.charge_counter: int = 0

        # Sequence tracking
        self.telemetry_seq: int = 0
        self.polls_since_telemetry: int = 0

    def advance_state(self):
        """Advance through state transitions: Init → Precharge → Charging."""
        elapsed = time.monotonic() - self.state_time
        if self.state == 0x00 and elapsed > 1.0:
            self.state = 0x02
            self.state_time = time.monotonic()
        elif self.state == 0x02 and elapsed > 2.0:
            self.state = 0x03
            self.state_time = time.monotonic()

    def reset(self):
        """Reset state for new charger session."""
        self.state = 0x00
        self.state_time = time.monotonic()
        self.charge_counter = 0
        self.polls_since_telemetry = 0

    def build_telemetry_payload(self) -> bytes:
        """Build 22-byte Cmd 0x10 telemetry payload."""
        self.advance_state()

        # Increment charge counter when charging
        if self.state == 0x03:
            self.charge_counter = min(self.charge_counter + 1, 255)

        # Pack voltage as LE uint16
        v_lo = self.pack_voltage_mv & 0xFF
        v_hi = (self.pack_voltage_mv >> 8) & 0xFF

        # Cell voltages as LE uint16 (0.5 mV units)
        cv_max_lo = self.cell_v_max_half_mv & 0xFF
        cv_max_hi = (self.cell_v_max_half_mv >> 8) & 0xFF
        cv_min_lo = self.cell_v_min_half_mv & 0xFF
        cv_min_hi = (self.cell_v_min_half_mv >> 8) & 0xFF

        payload = bytes([
            CMD_TELEMETRY,              # 0: Cmd
            0x00,                       # 1: Unknown (always 0x00)
            self.state,                 # 2: State
            0x00, 0x00, 0x00,           # 3-5: Unknown
            v_lo, v_hi,                 # 6-7: Pack voltage (LE)
            cv_max_lo, cv_max_hi,       # 8-9: Cell V MAX (LE, 0.5mV)
            cv_min_lo, cv_min_hi,       # 10-11: Cell V MIN (LE, 0.5mV)
            self.ntc_max,               # 12: NTC MAX (°C)
            self.ntc_avg,               # 13: NTC AVG (°C)
            self.th002_mosfet,          # 14: TH002 MOSFET (°C)
            self.soc_percent,           # 15: SOC (%)
            self.charge_counter,        # 16: Charge counter
            0x00, 0x00, 0x00, 0x00, 0x00  # 17-21: Reserved
        ])
        return payload


class BatterySimulator:
    """Handles charger messages and sends battery responses."""

    def __init__(self, dispatcher: MessageDispatcher, print_fn=None):
        self.dispatcher = dispatcher
        self.battery = BatteryState()
        self.print_fn = print_fn or (lambda s: print(s))
        self.active = False

        # Subscribe to all RX messages
        dispatcher.subscribe(None, self._on_message, direction=MessageDirection.RX)

    def start(self):
        self.active = True
        self.battery.reset()
        self.print_fn("Battery simulator ACTIVE — waiting for charger handshake")

    def stop(self):
        self.active = False
        self.print_fn("Battery simulator STOPPED")

    def _on_message(self, msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
        if not self.active:
            return

        sender = msg.sender
        seq = msg.seq
        data = msg.data
        length = data[2] if len(data) > 2 else 0

        # Charger handshake: sender 0x40, length 0
        if sender == 0x40 and length == 0:
            self._handle_handshake(seq)
            return

        # Charger poll: sender 0x00, length 5, cmd 0x10
        if sender == 0x00 and length == 5:
            payload = data[3:3 + length]
            if len(payload) >= 1 and payload[0] == CMD_TELEMETRY:
                self._handle_poll(seq)
                return

    def _handle_handshake(self, seq: int):
        """Respond to charger handshake with battery handshake."""
        reply = Msg()
        reply.sender = BATTERY_HANDSHAKE_BASE
        reply.seq = seq
        # pack() builds: PREFIX + header(sender|seq) + length(0) + CRC
        self.dispatcher.send_message(reply)
        self.battery.reset()
        self.print_fn(f"  ← Handshake reply (Seq={seq})")

    def _handle_poll(self, seq: int):
        """Respond to charger poll with telemetry or ack."""
        self.battery.polls_since_telemetry += 1

        # Send telemetry every 3-4 polls (like real battery)
        if self.battery.polls_since_telemetry >= 3:
            self._send_telemetry(seq)
            self.battery.polls_since_telemetry = 0
        else:
            self._send_ack(seq)

    def _send_telemetry(self, seq: int):
        """Build and send a full telemetry response."""
        payload = self.battery.build_telemetry_payload()

        reply = Msg()
        reply.sender = BATTERY_TELEMETRY_BASE
        reply.seq = self.battery.telemetry_seq & 0x0F

        # Build raw message: PREFIX + header + length + payload + CRC
        header_byte = (reply.sender | reply.seq) & 0xFF
        length = len(payload)
        prefix_bytes = struct.pack("BB", header_byte, length)
        payload_bytes = prefix_bytes + payload
        crc_value = Msg.crc_func(payload_bytes)
        crc_bytes = struct.pack('<H', crc_value)
        reply.data = bytes([0x00]) + payload_bytes + crc_bytes

        self.dispatcher.send_message(reply)
        self.battery.telemetry_seq = (self.battery.telemetry_seq + 1) & 0x03

        state_name = {0x00: "Init", 0x02: "Precharge", 0x03: "Charging"}.get(
            self.battery.state, f"0x{self.battery.state:02X}")
        self.print_fn(
            f"  ← Telemetry [State={state_name}, "
            f"V={self.battery.pack_voltage_mv}mV, "
            f"SOC={self.battery.soc_percent}%, "
            f"T={self.battery.ntc_max}/{self.battery.ntc_avg}/{self.battery.th002_mosfet}°C]"
        )

    def _send_ack(self, seq: int):
        """Send short ack pair (like real battery idle pattern)."""
        # Real battery sends acks with CRC=0x0000 (no-CRC marker)
        # Build raw: PREFIX + header + length(0) + CRC(0x0000)
        ack1 = Msg()
        ack1.sender = 0x00
        ack1.seq = seq
        ack1.data = bytes([0x00, (0x00 | seq) & 0xFF, 0x00, 0x00, 0x00])
        self.dispatcher.send_message(ack1)

        ack2 = Msg()
        ack2.sender = 0x00
        ack2.seq = 0x00
        ack2.data = bytes([0x00, 0x00, 0x00, 0x00, 0x00])
        self.dispatcher.send_message(ack2)

    def set_voltage(self, mv: int):
        self.battery.pack_voltage_mv = mv
        # Auto-calculate cell voltages (10S)
        cell_avg = mv // 10
        self.battery.cell_v_max_half_mv = (cell_avg + 2) * 2
        self.battery.cell_v_min_half_mv = (cell_avg - 2) * 2
        self.print_fn(f"  Voltage set to {mv} mV ({cell_avg} mV/cell)")

    def set_soc(self, percent: int):
        self.battery.soc_percent = max(0, min(100, percent))
        self.print_fn(f"  SOC set to {self.battery.soc_percent}%")

    def set_temperatures(self, ntc_max: int, ntc_avg: int, th002: int):
        self.battery.ntc_max = ntc_max
        self.battery.ntc_avg = ntc_avg
        self.battery.th002_mosfet = th002
        self.print_fn(f"  Temperatures set to MAX={ntc_max}°C AVG={ntc_avg}°C TH002={th002}°C")
