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

## Notes

Requires Python 3.8+
CRC16 calculation and UART parsing are handled automatically
Currently only tested on BT-E6000
