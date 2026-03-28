# Protocol Analysis: EC-E6002 Charger ↔ BT-E6000 Battery

## Overview

Analysis of the UART communication between a Shimano EC-E6002 charger and BT-E6000 battery (36V, 10S Li-Ion, 418Wh).
Data captured using dual-channel sniffing on a Raspberry Pi — hardware UART on GPIO15 (battery) and pigpio bit-bang serial on GPIO14 (charger).

## Log data
```
ottelo@raspberrypi:~/sut_ottelo $ ./run.sh
Activating venv
Start tool
================
Logging enabled for device BT-E6000 from source ott: battery-charger-test
/dev/serial0,9600,8,N,1,0.1
pigpiod not running, starting it...
PigpioUART: GPIO14 opened as bit-bang serial RX @ 9600 baud
R: 00 C1 00 35 DC
R2: 00 41 00 F9 50
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 80 16 10 00 00 00 00 00 56 95 E0 1D DC 1D 16 15 16 3D 00 00 00 00 00 00 7E 85
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 02 00 00 00
R: 00 00 00 00 00
R: 00 02 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 80 16 10 00 03 00 00 00 F7 95 04 1E FC 1D 16 15 16 3D 12 00 00 00 00 00 87 F1
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 03 00 00 00
R: 00 00 00 00 00
```

## Bus Topology

Half-duplex UART bus at 9600 baud (8N1). Both devices share the bus but use separate TX/RX lines.

| Channel | Pin | Device | Sender Addresses |
|---------|-----|--------|-----------------|
| CH1 (R:) | GPIO15 (RX) | Battery (BT-E6000) | 0x80, 0xC0 |
| CH2 (R2:) | GPIO14 (TX) | Charger (EC-E6002) | 0x00, 0x40 |

## Message Frame Format

```
[PREFIX] [HEADER] [LENGTH] [PAYLOAD...] [CRC16-LO] [CRC16-HI]
  0x00    1 byte   1 byte   N bytes       2 bytes (x-25)
```

- **PREFIX**: Always `0x00`
- **HEADER**: Upper nibble = sender address, lower nibble = sequence number (0–3)
- **LENGTH**: Number of payload bytes
- **CRC**: CRC-16/X-25 (little-endian), calculated over HEADER + LENGTH + PAYLOAD. A CRC of `0x0000` is treated as "no CRC" and always passes.

## Communication Flow

### 1. Handshake

When the charger is connected, the battery initiates with a ping:

```
Battery → 00 C1 00 35 DC       Ping (Sender=0xC0, Seq=1, Length=0, CRC valid)
Charger → 00 41 00 F9 50       Pong (Sender=0x40, Seq=1, Length=0, CRC valid)
```

### 2. Identification — Cmd 0x30 (Length=18)

After handshake, the battery sends identification data. This message differs between sessions — likely contains a session token or nonce.

```
Session 1: 00 81 12 30 00 FB 05 A1 D1 AD 20 32 55 DF 91 30 7A 0C 8C 53 45 E0 E0
Session 2: 00 80 12 30 00 5E D6 2D EE 79 04 15 10 19 A9 8E B2 EB 05 1E 63 C8 51
```

### 3. Battery Parameters — Cmd 0x31 (Length=18)

Sent once after identification. Identical across sessions — static battery configuration data.

```
00 82 12 31 00 9F 01 A9 01 01 00 05 00 28 00 6E 00 D8 01 78 00 D0 FD
```

Payload (18 bytes after header+length):

| Offset | Bytes | Decimal (LE) | Possible Meaning |
|--------|-------|-------------|------------------|
| 0–1 | `00 9F` | 159 | ? |
| 2–3 | `01 A9` | 425 | Capacity? (~418Wh for BT-E6000) |
| 4–5 | `01 01` | 257 | ? |
| 6–7 | `00 05` | 5 | ? |
| 8–9 | `00 28` | 40 | ? |
| 10–11 | `00 6E` | 110 | ? |
| 12–13 | `00 D8` | 216 | ? |
| 14–15 | `01 78` | 376 | ? |
| 16 | `00` | 0 | ? |

### 4. Charger Poll — Cmd 0x10 (Length=5)

The charger continuously polls the battery at ~1 second intervals, cycling through sequence numbers 0–3:

```
Charger → 00 00 05 10 00 00 00 00 B7 2C    Seq=0
Charger → 00 01 05 10 00 00 00 00 62 B3    Seq=1
Charger → 00 02 05 10 00 00 00 00 0C 1B    Seq=2
Charger → 00 03 05 10 00 00 00 00 D9 84    Seq=3
```

Payload is always `10 00 00 00 00` — Cmd 0x10 followed by 4 zero bytes. The charger is a "dumb" power supply; all charging logic resides in the battery.

### 5. Battery Telemetry Response — Cmd 0x10 (Length=22)

The battery responds to charger polls with full telemetry data. Not every poll gets a telemetry response — on some polls only a short ack pair is sent.

Example response:
```
Battery → 00 80 16 10 00 03 00 00 00 F7 95 04 1E FC 1D 16 15 16 3D 12 00 00 00 00 00 87 F1
```

#### Telemetry Field Map

| Offset | Bytes | Type | Field | Notes |
|--------|-------|------|-------|-------|
| 0 | `10` | uint8 | Cmd | Always 0x10 |
| 1 | | uint8 | State | 0x00=Init, 0x02=Precharge?, 0x03=Charging |
| 2–4 | | | ? | Usually `00 00 00` |
| 5–6 | LE uint16 | **Pack Voltage (mV)** | See voltage table below |
| 7–8 | LE uint16 | Current A | Possibly discharge current |
| 9–10 | LE uint16 | Current B | Possibly charge current |
| 11 | uint8 | TH003/TH004 MAX | Temperature sensor (see notes) |
| 12 | uint8 | TH003/TH004 AVG | Temperature sensor (see notes) |
| 13 | uint8 | TH002 | Temperature sensor |
| 14 | uint8 | Constant | Varies per session (0x36, 0x37, 0x3D) |
| 15 | uint8 | **SOC / Charge indicator** | Increases during charging |
| 16–20 | | | Reserved | Always `00 00 00 00 00` |

#### Voltage & SOC observations

**Session 2026-03-27** (battery nearly empty, ~0% SOC):

| Time | Pack Voltage | SOC | State |
|------|-------------|-----|-------|
| 19:53:38 | 37441 mV (37.4V) | 0 | 0x00 (Init) |
| 19:53:39 | 37450 mV | 1 | 0x02 |
| 19:53:40 | 37450 mV | 2 | 0x03 (Charging) |
| 19:54:00 | 37621 mV | 32 | 0x03 |
| 19:54:15 | 37696 mV (37.7V) | 34 | 0x03 |

**Session 2026-03-28** (battery ~60-70% SOC, 2 LEDs solid + 3rd blinking):

| Time | Pack Voltage | SOC | State |
|------|-------------|-----|-------|
| Start | 38230 mV (38.2V) | 0 | 0x00 (Init) |
| +few sec | 38391 mV (38.4V) | 18 | 0x03 (Charging) |

At 10S configuration: 38.2V = ~3.82V/cell, consistent with 60-70% SOC.

### 6. Idle / Ack Pattern

Between telemetry responses, the battery sends short ack pairs (Length=0, CRC=0x0000):

```
Battery → 00 03 00 00 00       Ping
Battery → 00 00 00 00 00       Ack
```

These appear on CH1 (battery side) and repeat at ~1 second intervals.

## State Transitions

```
State 0x00 (Init)       → First telemetry after charger connects
State 0x02 (Precharge?) → Brief transition state
State 0x03 (Charging)   → Steady state during active charging
```

## Constant Block Variations

The 4-byte constant block at offsets 11–14 changes between sessions:

| Date | Battery SOC | Constant Block | Last Byte |
|------|-------------|---------------|-----------|
| 2026-03-27 (session 1) | ~0% | `16 15 16 36` | 0x36 (54) |
| 2026-03-27 (session 2) | ~0% | `16 15 16 36` / `37` | 0x36–0x37 |
| 2026-03-28 | ~60-70% | `16 15 16 3D` | 0x3D (61) |

The last byte increases with SOC/temperature — possibly a temperature reading or battery state indicator.

## Sequence Number Rotation

Both charger and battery use a rotating sequence number (0→1→2→3→0→...) in the lower nibble of the header byte. This is used across all message types.

## Open Questions

- What do Current A and Current B represent exactly? (Charge vs discharge? Two measurement points?)
- What is the exact meaning of the SOC byte? (It doesn't map linearly to the LED display)
- What does the constant block represent? (Temperature sensors? Configuration?)
- Cmd 0x31 field mapping — which bytes encode capacity, cycle count, etc.?
- Why does the battery only respond with telemetry to some charger polls?
- What triggers the state transitions (0x00 → 0x02 → 0x03)?
