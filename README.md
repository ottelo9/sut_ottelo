# SUT — Shimano UART Tool
Fork of https://github.com/michielvg/sut with enhancements and ESP32 (Tasmota TinyC) Programm and deeper (with ClaudeAI) shimano protocol analysis  

For details/ installation see original fork!  

Links:  
- https://github.com/michielvg
- https://github.com/michielvg/Shimano_BT-E6000_BMS/discussions
- https://github.com/gregyedlik/BT-E60xx

# Features I have added to Rpi Script
## Dual-Channel Sniffing

When `tx_enabled` is set to `false` in `config.json`, the tool uses both GPIO pins as inputs to passively sniff both directions of the bus simultaneously:

| Channel | Pin | Method | Output |
|---------|-----|--------|--------|
| CH1 | GPIO15 (RX) | Hardware UART `/dev/serial0` | `R:` (normal) |
| CH2 | GPIO14 (TX) | pigpio bit-bang serial | `R2:` (cyan) |

If pigpio is not installed or pigpiod is not running, the tool falls back to single-channel mode (CH1 only) with a warning.

## Battery Simulator Mode

The tool can impersonate a Shimano BT-E6000 battery on the UART bus, responding to charger handshakes and polls with configurable telemetry data.

**WARNING:** Do NOT connect a real battery when using simulator mode. The charger will deliver current without real BMS protection.

### Starting Simulator Mode

Run the tool and select mode 2 at the startup menu:

```
========================================
  Select Mode
========================================
  1) Logging Mode      (RX + RX2 sniffing)
  2) Simulator Mode    (Battery BMS simulation)
========================================
  Select [1/2]: 2
```

The simulator automatically:
- Enables TX on GPIO14
- Responds to charger handshakes (0x40→0xC0)
- Sends telemetry (Cmd 0x10, Length=22) every 3rd poll
- Sends ack pairs between telemetry (CRC=0x0000, like real battery)
- Transitions through states: Init (1s) → Precharge (2s) → Charging

### Config

For simulator mode, `tx_enabled` can remain `false` in config.json — the tool overrides it automatically:

```json
{
    "uart": {
        "port": "/dev/serial0",
        "baud": 9600,
        "tx_enabled": false,
        "tx_gpio": 14
    }
}
```

### Runtime Commands

Adjust simulated values while running:

| Command | Example | Description |
|---------|---------|-------------|
| `voltage <mV>` | `voltage 38300` | Set pack voltage (auto-calculates cell voltages) |
| `soc <percent>` | `soc 62` | Set state of charge |
| `temp <max> <avg> <th002>` | `temp 22 21 22` | Set NTC MAX, NTC AVG, TH002 temperatures |
| `status` | `status` | Show current simulator state and values |
| `help` | `help` | List available commands |

## Colored Output

|Color   |Meaning                    |
|--------|---------------------------|
|(normal)|Valid message received (CH1)|
|Cyan    |Valid message received (CH2)|
|Yellow  |Incomplete message detected|
|Red     |CRC error detected         |


Press Ctrl+C to exit.
The tool will cleanly close the serial port and any open pipes.

## Analyzing Data with DuckDB

Logged data (NDJSON files in `data/`) can be queried with DuckDB.

### Installing DuckDB

Download the prebuilt binary for Raspberry Pi (aarch64):

```bash
wget https://github.com/duckdb/duckdb/releases/latest/download/duckdb_cli-linux-arm64.zip
unzip duckdb_cli-linux-arm64.zip
sudo mv duckdb /usr/local/bin/
```

Alternatively, build from source:

```bash
sudo apt-get update
sudo apt-get install -y git g++ cmake ninja-build

git clone https://github.com/duckdb/duckdb
cd duckdb
GEN=ninja BUILD_EXTENSIONS="icu;json" make
sudo mv build/release/duckdb /usr/local/bin/
```

### Querying Log Data

Run a predefined query:

```bash
duckdb :memory: -f sql/charger_telemetry.sql
```

Available queries in `sql/`:

| File | Description |
|------|-------------|
| `00_80_16_10.sql` | PCB telemetry analysis (Cmd 0x10, Seq 0) |
| `charger_telemetry.sql` | Charger/battery telemetry (all Cmd 0x10) |

Or run an ad-hoc query:

```bash
duckdb :memory: -c "SELECT * FROM read_ndjson_auto('data/2026/03/28.ndjson') LIMIT 10;"
```

## ESP32 TinyC Variant — `Tasmota-TinyC/ShimanoSniffer.tc`

A second implementation runs on an ESP32 with [Tasmota TinyC](https://github.com/gemu2015/Sonoff-Tasmota/tree/universal/tasmota/tinyc) for standalone, network-connected operation (no Pi needed). The same Shimano protocol decoder, plus three operating modes selectable from a Tasmota web UI:

| Mode | Behavior |
|------|----------|
| **Sniffer** | Passive dual-channel capture on GPIO18 (charger/motor TX) and GPIO19 (battery TX). Logs decoded frames live, optionally to flash file `/shimano.log`. |
| **Simulator** | ESP32 acts as motor or charger. `[Sim-Motor]` runs the full motor wake (cold-wake handshake bursts → Auth replay → Boot Poll → DevInfo → First Ready → Trip → continuous steady polling) — verified to release the **discharge MOSFETs** on BT-E6000 without bike present (battery powers a load via main contacts). `[Sim-Charger]` does the charger wake (HS-Pong → 80ms gap → Auth replay → Specs-Req → polls) — verified to release the **charge MOSFETs** when paired with a 41.5 V bench supply at the main contacts (state advances Init→Pre→Chg, Vbat climbs through IR-drop, no real Shimano charger needed). `[Shutdown]` cleanly powers the BMS down. |
| **Sim-BMS** | ESP32 impersonates the battery, responds to motor/charger requests with configurable fake telemetry (SOC, Vbat). Useful for testing motor/display behavior without an actual battery. |

### Hardware

ESP32 dev board, 3 wires to the battery connector (GND, B-TX → GPIO19, B-RX → GPIO18). Recommended: 5 kΩ pull-up on GPIO19 to 3.3V (stable UART idle when battery disconnected) and 5 kΩ pull-down on GPIO18 to GND (prevents accidental BMS wake while sniffing).

### Critical implementation details

1. **Inter-byte UART timing** — the BMS validates that bytes within a frame arrive with ~1-3 ms gaps. The TinyC code sends each byte via `serialWriteByte` with `delayMicroseconds(2500)` between calls. Sending whole frames via `serialWriteBytes(buf, len)` (back-to-back) is silently rejected by the BMS even with valid CRCs, returning a degraded `30 12` Auth-Resp and flipping fault byte to `0x15` after ~8 s.

2. **Inter-frame gap before charger Auth-Req** — in Sim-Charger mode, HS-Pong and Auth-Req must be sent as two **separate** UART transmissions with ~80 ms gap between them. Combined into a single 27-byte burst (even with proper inter-byte timing) the Auth-Req is silently ignored — battery only acknowledges the HS-Pong with `00 C1 00 35 DC`.

3. **Auth-Req replay must come from a real session of the same battery.** Random bytes with the correct structural format are silently rejected — the BMS validates more than just structure. For Sim-Charger especially, Auth-Req appears to be per-battery (bytes from one battery's session don't work on another's).

See [docs/protocol_analysis.md](docs/protocol_analysis.md) for the full protocol decode.

### Deploy

Flash a Tasmota-TinyC build onto an ESP32 (instructions: gemu2015 repo above), then upload `Tasmota-TinyC/ShimanoSniffer.tc` via Tasmota's file manager. Restart, open the device's web UI, and the Shimano page appears in the menu.

## Notes

Requires Python 3.8+
CRC16 calculation and UART parsing are handled automatically
Currently only tested on BT-E6000
