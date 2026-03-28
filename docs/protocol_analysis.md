# Protocol Analysis: EC-E6002 Charger ↔ BT-E6000 Battery
Generated via ClaudeAI

## Overview

Analysis of the UART communication between a Shimano EC-E6002 charger and BT-E6000 battery (36V, 10S Li-Ion, 418Wh).
Data captured using dual-channel sniffing on a Raspberry Pi — hardware UART on GPIO15 (battery) and pigpio bit-bang serial on GPIO14 (charger).

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

### 2. Charger Poll — Cmd 0x10 (Length=5)

The charger continuously polls the battery at ~1 second intervals, cycling through sequence numbers 0–3:

```
Charger → 00 00 05 10 00 00 00 00 B7 2C    Seq=0
Charger → 00 01 05 10 00 00 00 00 62 B3    Seq=1
Charger → 00 02 05 10 00 00 00 00 0C 1B    Seq=2
Charger → 00 03 05 10 00 00 00 00 D9 84    Seq=3
```

Payload is always `10 00 00 00 00` — Cmd 0x10 followed by 4 zero bytes. The charger is a "dumb" power supply; all charging logic resides in the battery.

### 3. Battery Telemetry Response — Cmd 0x10 (Length=22)

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

**Capture 2026-03-28 ~09:20 UTC** (battery ~61% SOC, ~22°C ambient, charger connected → idle → reconnect → idle → disconnected):

| # | State | Pack Voltage | SOC | Current A | Current B | NTC MAX | NTC AVG | TH002 | Byte 14 |
|---|-------|-------------|-----|-----------|-----------|---------|---------|-------|---------|
| 1 | 0x02 | 38246 mV | 0 | 7652 | 7646 | 21°C | 21°C | 20°C | 0x3D (61) |
| 2 | 0x03 (Charging) | 38251 mV | 1 | 7654 | 7648 | 21°C | 21°C | 20°C | 0x3D (61) |
| 3 (reconnect) | 0x00 (Init) | 38355 mV | **24** | 7674 | 7668 | 21°C | 21°C | 21°C | 0x3D (61) |

- Pack voltage: 38.2V → 38.4V (10S = ~3.82–3.84V/cell, consistent with ~61% SOC)
- TH002 warmed from 20°C to 21°C during the session
- After reconnect, SOC carried over from previous session (24), then resets on state transition

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

### 4. Idle / Ack Pattern

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

| Date / Capture | NTC MAX | NTC AVG | TH002 | Byte 14 |
|----------------|---------|---------|-------|---------|
| 2026-03-28 session start (61% SOC) | 0x15 (21°C) | 0x15 (21°C) | 0x14 (20°C) | 0x3D (61) |
| 2026-03-28 after charging | 0x15 (21°C) | 0x15 (21°C) | 0x15 (21°C) | 0x3D (61) |
| 2026-03-28 5x reconnect | 0x16 (22°C) | 0x16 (22°C) | 0x16 (22°C) | 0x3D (61) |

- TH002 warmed from 20°C to 21°C during a single session, then 22°C after repeated charging.
- All three temperature fields are consistent with an ambient temperature of ~20-22°C.
- **Byte 14 is NOT a temperature** — value 0x3D=61 is far too high for °C. Interestingly, 61 matches the battery SOC (61%). Needs further investigation.

## Sequence Number Rotation

Both charger and battery use a rotating sequence number (0→1→2→3→0→...) in the lower nibble of the header byte. This is used across all message types.

## Open Questions

- What do Current A and Current B represent exactly? Constant ~4–6 unit offset suggests two measurement points (before/after shunt? two cell groups?)
- Offset 15 ("SOC byte") is not absolute SOC — it resets each session and counts up. What does it represent? Coulomb counter? Charge phase indicator?
- **Byte 14 (offset 14) = actual SOC?** Value 0x3D=61 matches the battery's reported 61% SOC exactly. Needs verification at different charge levels.
- Why does the battery only respond with telemetry to some charger polls? Is it time-based or sequence-based?
- What triggers the state transitions (0x00 → 0x02 → 0x03)?

## Logs

### 2026-03-28 ~09:20 UTC — Charger session with reconnect (61% SOC, ~22°C)

Battery at 61% SOC (2 LEDs solid, 3rd blinking). Charger connected, ran for ~2 minutes idle polling, disconnected and reconnected once, then disconnected.

[Full log](logs/2026-03-28_0920_charger_reconnect.log)

### 2026-03-28 ~08:50 UTC — 5x connect/disconnect (~61% SOC)

Battery ~60-70% SOC, 2 LEDs solid + 3rd blinking. EC-E6002 charger connected and disconnected 5 times rapidly.

[Full log](logs/2026-03-28_0850_5x_connect_disconnect.log)

### 2026-03-28 — Heat test with hair dryer (~61% SOC, starting ~22°C)

Battery slowly heated with a hair dryer while charger connected. Starting temperature ~22°C.

[Full log](logs/2026-03-28_heat_test.log)

#### Telemetry during heat test

| # | State | Pack Voltage | Current A | Current B | NTC MAX | NTC AVG | TH002 | Byte 14 | SOC counter |
|---|-------|-------------|-----------|-----------|---------|---------|-------|---------|-------------|
| 1 | 0x00 (Init) | 38276 mV | 0x1DEA (7658) | 0x1DE4 (7652) | 22°C | 21°C | 22°C | 0x3D (61) | 0 |
| 2 | 0x03 (Charging) | 38456 mV | 0x1E0E (7694) | 0x1E08 (7688) | 22°C | 21°C | 22°C | 0x3D (61) | 32 |

**Observations:**
- Voltage jump of **180 mV** (38276 → 38456 mV) between first and second telemetry — larger than previous sessions
- Current A/B both increased by **36 units** (7658→7694 / 7652→7688) — previously stable, now rising with temperature
- NTC MAX stayed at 22°C, NTC AVG at 21°C, TH002 at 22°C — temperature sensors have not yet reflected the external heating (likely slow thermal conduction to sensor location)
- Byte 14 remains 0x3D (61) — still matches SOC, unaffected by heating
- SOC counter jumped from 0 to 32 in the second telemetry — much higher than in previous sessions (which typically showed 0→1)
