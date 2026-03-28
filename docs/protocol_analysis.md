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

#### Byte-by-byte breakdown

| Byte(s) | Hex | Field | Value |
|---------|-----|-------|-------|
| 0 | `00` | PREFIX | Always 0x00 |
| 1 | `80` | HEADER | Sender=0x80 (Battery), Seq=0 |
| 2 | `16` | LENGTH | 22 payload bytes |
| 3 | `10` | Cmd | 0x10 (Telemetry) |
| 4 | `03` | State | 0x03 = Charging |
| 5–7 | `00 00 00` | ? | Usually zero |
| 8–9 | `F7 95` | Pack Voltage | 0x95F7 = 38391 mV (LE) |
| 10–11 | `04 1E` | Cell V MAX | 0x1E04 = 7684 → 3842 mV |
| 12–13 | `FC 1D` | Cell V MIN | 0x1DFC = 7676 → 3838 mV |
| 14 | `16` | NTC MAX | 22°C |
| 15 | `15` | NTC AVG | 21°C |
| 16 | `16` | TH002 (MOSFET) | 22°C |
| 17 | `3D` | **SOC** | **61%** |
| 18 | `12` | Charge counter | 18 |
| 19–23 | `00 00 00 00 00` | Reserved | Always zero |
| 24–25 | `87 F1` | CRC-16/X-25 | Over bytes 1–23 (LE) |

#### Telemetry Field Map (payload offsets, starting after LENGTH byte)

| Offset | Bytes | Type | Field | Notes |
|--------|-------|------|-------|-------|
| 0 | `10` | uint8 | Cmd | Always 0x10 |
| 1 | | uint8 | State | 0x00=Init, 0x02=Precharge?, 0x03=Charging |
| 2–4 | | | ? | Usually `00 00 00` |
| 5–6 | LE uint16 | **Pack Voltage (mV)** | See voltage table below |
| 7–8 | LE uint16 | **Cell Voltage MAX (0.5 mV)** | Likely max cell group voltage. Divide by 2 for mV. Matches multimeter readings. |
| 9–10 | LE uint16 | **Cell Voltage MIN (0.5 mV)** | Likely min cell group voltage. Always ~4–8 less than MAX (~2–4 mV). |
| 11 | uint8 | **NTC Temperature MAX (°C)** | MAX of 2x 10K NTC sensors, value is directly °C. BT-E6000: TH003/TH004, BT-E6001: TH001/TH002. |
| 12 | uint8 | **NTC Temperature AVG (°C)** | AVG of 2x 10K NTC sensors, value is directly °C |
| 13 | uint8 | **TH002 Temperature (°C)** | MOSFET temperature sensor (mounted next to MOSFETs), value is directly °C. Consistently hottest reading in heat tests. |
| 14 | uint8 | **SOC (%)** | **Confirmed**: actual state of charge percentage. Changed from 0x3D (61%) to 0x3E (62%) after charging. |
| 15 | uint8 | Charge counter | Resets each session, counts up during charging. Not absolute SOC. |
| 16–20 | | | Reserved | Always `00 00 00 00 00` |

#### Voltage & SOC observations

**Capture 2026-03-28 ~09:20 UTC** (battery ~61% SOC, ~22°C ambient, charger connected → idle → reconnect → idle → disconnected):

| # | State | Pack Voltage | Cell V MAX | Cell V MIN | NTC MAX | NTC AVG | TH002 | SOC (%) | Charge ctr |
|---|-------|-------------|-----------|-----------|---------|---------|-------|---------|------------|
| 1 | 0x02 | 38246 mV | 3826 mV | 3823 mV | 21°C | 21°C | 20°C | 61% | 0 |
| 2 | 0x03 (Charging) | 38251 mV | 3827 mV | 3824 mV | 21°C | 21°C | 20°C | 61% | 1 |
| 3 (reconnect) | 0x00 (Init) | 38355 mV | 3837 mV | 3834 mV | 21°C | 21°C | 21°C | 61% | 24 |

- Pack voltage: 38.2V → 38.4V (10S = ~3.82–3.84V/cell, consistent with ~61% SOC)
- Cell voltage spread only 3 mV — well balanced pack
- TH002 warmed from 20°C to 21°C during the session
- After reconnect, charge counter carried over from previous session (24), then resets on state transition

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

| Session | State | Pack Voltage | Cell V MAX | Cell V MIN | Spread | Temps | SOC | Charge ctr |
|---------|-------|-------------|-----------|-----------|--------|-------|-----|------------|
| 1 | 0x00 (Init) | 38241 mV | 3825 mV | 3823 mV | 2 mV | 22/22/22°C | 61% | 0 |
| 1 | 0x02 | 38253 mV | 3827 mV | 3824 mV | 3 mV | 22/22/22°C | 61% | 0 |
| 2 | 0x00 (Init) | 38265 mV | 3828 mV | 3825 mV | 3 mV | 22/22/22°C | 61% | **22** |
| 2 | 0x03 (Charging) | 38260 mV | 3827 mV | 3825 mV | 2 mV | 22/22/22°C | 61% | 1 |
| 3 | 0x00 (Init) | 38278 mV | 3829 mV | 3827 mV | 2 mV | 22/22/22°C | 61% | **4** |
| 3 | 0x03 (Charging) | 38271 mV | 3828 mV | 3826 mV | 2 mV | 22/22/22°C | 61% | 1 |
| 4 | 0x00 (Init) | 38281 mV | 3829 mV | 3827 mV | 2 mV | 22/22/22°C | 61% | **4** |
| 5 | 0x00 (Init) | 38289 mV | 3830 mV | 3828 mV | 2 mV | 22/22/22°C | 61% | **19** |
| 5 | 0x02 | 38278 mV | 3829 mV | 3827 mV | 2 mV | 22/22/22°C | 61% | 0 |

**Key observations from multi-session data:**

- **Charge counter reset behavior**: The first telemetry (State=0x00) carries over the **last charge counter value from the previous session** (22, 4, 4, 19). After the state transitions to 0x02/0x03, the counter resets to 0 or 1 and starts counting up again.
- **Handshake initiator alternates**: Either device can initiate. The handshake sequence number increments independently across sessions, separate from the telemetry sequence counter.
- **Voltage rises continuously**: 38241 → 38289 mV across all 5 sessions, even between disconnects. The battery retains charge between brief disconnect cycles.
- **Cell voltage spread consistently 2–3 mV** — very well balanced pack. Matches multimeter measurement (3834.9–3836.1 mV, spread ~1.2 mV unloaded).
- **NTC AVG temperature increased**: from 21°C to 22°C — battery warming up through repeated charging cycles.

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

## Charge Current Measurement

Measured externally via the battery's shunt resistors: 2x 1mΩ (SMD marking "1L00") in parallel, in series with GND → **R_shunt = 0.5 mΩ**.

| Phase | U_shunt | Calculated I | Multimeter I |
|-------|---------|-------------|-------------|
| State 0x00 (Init) | 0–0.02 mV | ~0 A | — |
| State 0x02 (Precharge) | 0.91 mV | 1.82 A | ~1.7 A |
| Charging steady (~30s) | 0.95 mV | 1.9 A | — |

**Charge current is NOT reported in the Cmd 0x10 telemetry.** No field correlates with the measured 1.7–1.9 A. This makes sense: the charger is a "dumb" power supply, and all charging logic resides in the battery BMS — it has no need to report the current back to the charger.

## Temperature Sensors

The battery contains 3 temperature sensors. Each NTC is connected to a separate GPIO on the battery's microcontroller. Values at offsets 11–13 are **directly in °C** — no scaling needed.

NTC sensor designators vary by battery model:
- **BT-E6000**: TH003, TH004 (NTC pair, separate GPIOs)
- **BT-E6001**: TH001, TH002 (NTC pair, separate GPIOs)

| Offset | Field | Description |
|--------|-------|-------------|
| 11 | NTC MAX | Maximum of TH003/TH004 (cell temperature NTCs) |
| 12 | NTC AVG | Average of TH003/TH004 (cell temperature NTCs) |
| 13 | TH002 | MOSFET temperature sensor, mounted next to the MOSFETs |

### Temperature observations across sessions

| Date / Capture | NTC MAX | NTC AVG | TH002 | SOC (Byte 14) |
|----------------|---------|---------|-------|---------------|
| 2026-03-28 session start (61% SOC, cold) | 0x15 (21°C) | 0x15 (21°C) | 0x14 (20°C) | 0x3D (61%) |
| 2026-03-28 after charging (cold) | 0x15 (21°C) | 0x15 (21°C) | 0x15 (21°C) | 0x3D (61%) |
| 2026-03-28 5x reconnect (cold) | 0x16 (22°C) | 0x16 (22°C) | 0x16 (22°C) | 0x3D (61%) |
| 2026-03-28 heat test 1 (warm start) | 0x16 (22°C) | 0x15 (21°C) | 0x16 (22°C) | 0x3D (61%) |
| **2026-03-28 heat test 2 (pre-warmed)** | **0x27 (39°C)** | **0x1E (30°C)** | **0x2B (43°C)** | **0x3E (62%)** |
| heat test 2 — cooling | 0x25 (37°C) | 0x1C (28°C) | 0x2A (42°C) | 0x3E (62%) |
| heat test 2 — further cooling | 0x24 (36°C) | 0x1B (27°C) | 0x29 (41°C) | 0x3E (62%) |

- **TH002 is the hottest sensor** — 43°C vs NTC MAX 39°C. TH002 sits next to the MOSFETs, which conduct heat faster than the cell pack.
- **NTC AVG lags significantly behind NTC MAX**: 30°C vs 39°C — confirms one NTC sensor heats faster than the other (asymmetric placement).
- Temperatures **cool down across sessions** as the hair dryer was removed: 39→37→36 (MAX), 43→42→41 (TH002).
- At room temperature (~22°C), all three sensors read within 1-2°C of each other.

## Sequence Number Rotation

Both charger and battery use a rotating sequence number (0→1→2→3→0→...) in the lower nibble of the header byte. This is used across all message types.

## Open Questions

- **Cell V MAX/MIN (offsets 7–10)**: Likely max/min cell group voltages in 0.5 mV units. Multimeter confirms cells at 3834.9–3836.1 mV (unloaded), matching telemetry values. Still needs full verification under different SOC levels.
- Offset 15 ("Charge counter") resets each session and counts up. What does it represent? Coulomb counter? Charge phase indicator?
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

| # | State | Pack Voltage | Cell V MAX | Cell V MIN | NTC MAX | NTC AVG | TH002 | SOC | Charge ctr |
|---|-------|-------------|-----------|-----------|---------|---------|-------|-----|------------|
| 1 | 0x00 (Init) | 38276 mV | 3829 mV | 3826 mV | 22°C | 21°C | 22°C | 61% | 0 |
| 2 | 0x03 (Charging) | 38456 mV | 3847 mV | 3844 mV | 22°C | 21°C | 22°C | 61% | 32 |

**Observations:**
- Voltage jump of **180 mV** (38276 → 38456 mV) between first and second telemetry — larger than previous sessions
- Cell voltages rose by 18 mV (3829→3847 / 3826→3844) — consistent with pack voltage increase
- NTC MAX stayed at 22°C, NTC AVG at 21°C, TH002 at 22°C — temperature sensors have not yet reflected the external heating (likely slow thermal conduction to sensor location)
- SOC remains 61%, unaffected by heating
- Charge counter jumped from 0 to 32 in the second telemetry — much higher than in previous sessions (which typically showed 0→1)

### 2026-03-28 — Heat test pre-warmed (62% SOC, starting ~39°C)

Battery pre-warmed with hair dryer for several minutes before connecting charger. Charger connected and disconnected multiple times while battery cooled.

[Full log](logs/2026-03-28_heat_test_prewarmed.log)

#### Telemetry during pre-warmed heat test

| Session | State | Pack Voltage | Cell V MAX | Cell V MIN | NTC MAX | NTC AVG | TH002 | SOC | Charge ctr |
|---------|-------|-------------|-----------|-----------|---------|---------|-------|-----|------------|
| 1 | 0x00 (Init) | 38296 mV | 3831 mV | 3829 mV | **39°C** | **30°C** | **43°C** | **62%** | 0 |
| 2 | 0x00 (Init) | 38327 mV | 3834 mV | 3831 mV | 37°C | 28°C | 42°C | 62% | 22 |
| 3 | 0x00 (Init) | 38330 mV | 3834 mV | 3832 mV | 37°C | 28°C | 42°C | 62% | 14 |
| 4 | 0x00 (Init) | 38341 mV | 3836 mV | 3833 mV | 36°C | 27°C | 41°C | 62% | 23 |
| 4 | 0x02 (Precharge) | 38336 mV | 3835 mV | 3833 mV | 36°C | 27°C | 41°C | 62% | 0 |

**Key findings:**

- **SOC confirmed: Byte 14 = actual SOC percentage.** Changed from 0x3D (61%) in all previous cold captures to **0x3E (62%)** — the battery charged by 1% during the earlier sessions.
- **Temperature sensors clearly respond to heating**: NTC MAX 39°C, NTC AVG 30°C, TH002 43°C (vs ~22°C at room temperature)
- **TH002 is the hottest sensor** — consistently 4-6°C above NTC MAX. Located next to the MOSFETs, which conduct heat faster.
- **NTC AVG confirms asymmetric NTC placement**: 30°C vs MAX 39°C means one NTC sensor reached ~39°C while the other was much cooler (~21°C), averaging to 30°C.
- **Battery cooling visible** across sessions: TH002 43→42→42→41°C, NTC MAX 39→37→37→36°C, NTC AVG 30→28→28→27°C
- **Cell voltages increase with temperature**: ~3831/3829 mV at 39°C vs ~3825/3823 mV at 22°C. Consistent with Li-Ion OCV temperature coefficient.

### 2026-03-28 — Charge current measurement (62% SOC, ~28°C)

Shunt voltage measured across 2x 1mΩ parallel resistors (R_shunt = 0.5 mΩ) in series with GND. Simultaneously with multimeter on charger cable.

[Full log](logs/2026-03-28_current_measurement.log)

#### Telemetry vs measured current

| Telemetry | State | U_shunt | I_calc | I_multimeter | Cell V MAX | Cell V MIN |
|-----------|-------|---------|--------|-------------|-----------|-----------|
| 1 | 0x00 (Init) | 0–0.02 mV | ~0 A | — | 3834 mV | 3830 mV |
| 2 | 0x02 (Precharge) | 0.91 mV | 1.82 A | ~1.7 A | 3834 mV | 3832 mV |

**Conclusion:** Offsets 7–10 do not represent charge current. Cell voltages remain nearly constant (3834 mV) despite current changing from 0 to 1.82 A — consistent with cell voltage interpretation.

#### Cell voltage verification

Multimeter measurement of all 10 cell groups (charger disconnected, 62% SOC):
- Range: **3834.9 – 3836.1 mV** (spread 1.2 mV)
- Telemetry Cell V MAX/MIN at same SOC: 3834/3830 mV (under load)
- Values match within measurement tolerance, confirming offsets 7–10 as cell group voltages in 0.5 mV units.
