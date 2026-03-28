# Protocol Analysis: EC-E6002 Charger ↔ BT-E6000 Battery
Generated via ClaudeAI  

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

Either device can initiate the handshake. The handshake sequence number increments across sessions independently from the telemetry sequence number.

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
| 11 | uint8 | **NTC Temperature MAX (°C)** | MAX of 2x 10K NTC sensors (TH003/TH004), value is directly °C |
| 12 | uint8 | **NTC Temperature AVG (°C)** | AVG of 2x 10K NTC sensors (TH003/TH004), value is directly °C |
| 13 | uint8 | **TH002 Temperature (°C)** | Third temperature sensor, value is directly °C |
| 14 | uint8 | ? | Not temperature (values 0x36=54, 0x3D=61 too high for °C). Purpose unknown. |
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

#### Multi-session capture 2026-03-28 (5x connect/disconnect, battery ~60-70% SOC)

Repeated charger connect/disconnect cycles reveal handshake and SOC reset behavior.

**Handshake sequence across sessions:**

| Session | Initiator | Seq | Handshake |
|---------|-----------|-----|-----------|
| 1 | Charger | 0 | `R2: 00 40 00 21 49` → `R: 00 C0 00 ED C5` |
| 2 | Charger | 1 | `R2: 00 41 00 F9 50` → `R: 00 C1 00 35 DC` |
| 3 | Battery | 0 | `R: 00 C0 00 ED C5` → `R2: 00 40 00 21 49` |
| 4 | Battery | 1 | `R: 00 C1 00 35 DC` → `R2: 00 41 00 F9 50` |
| 5 | Charger | 2 | `R2: 00 42 00 91 7A` → `R: 00 C2 00 5D F6` |

**Telemetry across all sessions:**

| Session | State | Pack Voltage | SOC | Current A | Current B | Const Block |
|---------|-------|-------------|-----|-----------|-----------|-------------|
| 1 | 0x00 (Init) | 38241 mV | 0 | 0x1DE2 (7650) | 0x1DDE (7646) | `16 16 16 3D` |
| 1 | 0x02 | 38253 mV | 0 | 0x1DE6 (7654) | 0x1DE0 (7648) | `16 16 16 3D` |
| 2 | 0x00 (Init) | 38265 mV | **22** | 0x1DE8 (7656) | 0x1DE2 (7650) | `16 16 16 3D` |
| 2 | 0x03 (Charging) | 38260 mV | 1 | 0x1DE6 (7654) | 0x1DE2 (7650) | `16 16 16 3D` |
| 3 | 0x00 (Init) | 38278 mV | **4** | 0x1DEA (7658) | 0x1DE6 (7654) | `16 16 16 3D` |
| 3 | 0x03 (Charging) | 38271 mV | 1 | 0x1DE8 (7656) | 0x1DE4 (7652) | `16 16 16 3D` |
| 4 | 0x00 (Init) | 38281 mV | **4** | 0x1DEA (7658) | 0x1DE6 (7654) | `16 16 16 3D` |
| 5 | 0x00 (Init) | 38289 mV | **19** | 0x1DEC (7660) | 0x1DE8 (7656) | `16 16 16 3D` |
| 5 | 0x02 | 38278 mV | 0 | 0x1DEA (7658) | 0x1DE6 (7654) | `16 16 16 3D` |

**Key observations from multi-session data:**

- **SOC reset behavior**: The first telemetry (State=0x00) carries over the **last SOC value from the previous session** (22, 4, 4, 19). After the state transitions to 0x02/0x03, the SOC resets to 0 or 1 and starts counting up again. This means the SOC byte is **not** an absolute state of charge but a **charge counter since session start**.
- **Handshake initiator alternates**: Either device can initiate. The handshake sequence number increments independently across sessions, separate from the telemetry sequence counter.
- **Voltage rises continuously**: 38241 → 38289 mV across all 5 sessions, even between disconnects. The battery retains charge between brief disconnect cycles.
- **Current A always ~4 higher than Current B**: The offset is constant (e.g., 7650 vs 7646, 7660 vs 7656). Possibly two measurement points (before/after shunt, or two cell groups).
- **NTC AVG temperature increased**: Byte 12 changed from `15` (21°C) to `16` (22°C) — battery warming up through repeated charging cycles.

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

## Temperature Sensors

The battery contains 2x 10K NTC temperature sensors. Values at offsets 11–13 are **directly in °C** — no scaling needed.

| Offset | Field | Description |
|--------|-------|-------------|
| 11 | NTC MAX | Maximum of TH003 and TH004 readings |
| 12 | NTC AVG | Average of TH003 and TH004 readings |
| 13 | TH002 | Separate temperature sensor |

### Temperature observations across sessions

| Date | NTC MAX | NTC AVG | TH002 | Byte 14 |
|------|---------|---------|-------|---------|
| 2026-03-27 (session 1) | 0x16 (22°C) | 0x15 (21°C) | 0x16 (22°C) | 0x36 (54) |
| 2026-03-27 (session 2) | 0x16 (22°C) | 0x15 (21°C) | 0x16 (22°C) | 0x36–0x37 |
| 2026-03-28 (first capture) | 0x16 (22°C) | 0x15 (21°C) | 0x16 (22°C) | 0x3D (61) |
| 2026-03-28 (multi-session) | 0x16 (22°C) | 0x16 (22°C) | 0x16 (22°C) | 0x3D (61) |

- NTC AVG increased from 21°C to 22°C during repeated charging cycles (battery warming up).
- All three temperature fields are consistent with an ambient temperature of ~20-22°C.
- **Byte 14 is NOT a temperature** — values of 54 and 61 are far too high for °C. Its purpose remains unknown.

## Sequence Number Rotation

Both charger and battery use a rotating sequence number (0→1→2→3→0→...) in the lower nibble of the header byte. This is used across all message types.

## Open Questions

- What do Current A and Current B represent exactly? Constant ~4 unit offset suggests two measurement points (before/after shunt? two cell groups?)
- The SOC byte is not absolute SOC — it resets each session and counts up. What does it represent? Coulomb counter? Charge phase indicator?
- What does byte 14 represent? Values 54–61, too high for °C, changes with SOC — possibly a battery state indicator or internal resistance metric?
- Cmd 0x31 field mapping — which bytes encode capacity (425 ≈ 418Wh?), cycle count, cell config, etc.?
- Why does the battery only respond with telemetry to some charger polls? Is it time-based or sequence-based?
- What triggers the state transitions (0x00 → 0x02 → 0x03)?
- Cmd 0x30 payload differs between sessions — session token, nonce, or timestamp?

## Raw Data

### Multi-session capture 2026-03-28 (5x connect/disconnect)

Battery ~60-70% SOC, 2 LEDs solid + 3rd blinking. EC-E6002 charger connected and disconnected 5 times.

```
R2: 00 40 00 21 49
R: 00 C0 00 ED C5
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 83 16 10 00 00 00 00 00 61 95 E2 1D DE 1D 16 16 16 3D 00 00 00 00 00 00 10 19
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 02 00 00 00
R: 00 00 00 00 00
R: 00 81 16 10 00 02 00 00 00 6D 95 E6 1D E0 1D 16 16 16 3D 00 00 00 00 00 00 73 A1
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 41 00 F9 50
R: 00 C1 00 35 DC
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 80 16 10 00 00 00 00 00 79 95 E8 1D E2 1D 16 16 16 3D 16 00 00 00 00 00 9F 7C
R: 00 02 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 02 00 00 00
R: 00 00 00 00 00
R: 00 83 16 10 00 03 00 00 00 74 95 E6 1D E2 1D 16 16 16 3D 01 00 00 00 00 00 61 B1
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 C0 00 ED C5
R2: 00 40 00 21 49
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 83 16 10 00 00 00 00 00 86 95 EA 1D E6 1D 16 16 16 3D 04 00 00 00 00 00 0E 99
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 02 00 00 00
R: 00 00 00 00 00
R: 00 81 16 10 00 03 00 00 00 7F 95 E8 1D E4 1D 16 16 16 3D 01 00 00 00 00 00 CF 2B
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 C1 00 35 DC
R2: 00 41 00 F9 50
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 80 16 10 00 00 00 00 00 89 95 EA 1D E6 1D 16 16 16 3D 04 00 00 00 00 00 45 96
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 02 00 00 00
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
R2: 00 42 00 91 7A
R: 00 C2 00 5D F6
R2: 00 01 05 10 00 00 00 00 62 B3
R: 00 81 16 10 00 00 00 00 00 91 95 EC 1D E8 1D 16 16 16 3D 13 00 00 00 00 00 60 61
R: 00 02 00 00 00
R: 00 00 00 00 00
R2: 00 03 05 10 00 00 00 00 D9 84
R: 00 83 16 10 00 02 00 00 00 86 95 EA 1D E6 1D 16 16 16 3D 00 00 00 00 00 00 1F 3F
R2: 00 00 05 10 00 00 00 00 B7 2C
R: 00 03 00 00 00
R: 00 00 00 00 00
R: 00 03 00 00 00
R: 00 00 00 00 00
R2: 00 02 05 10 00 00 00 00 0C 1B
R: 00 03 00 00 00
R: 00 00 00 00 00
```
