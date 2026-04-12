#!/usr/bin/env python3
"""
UART / Pipe Test Harness

- Reads messages from a serial device and/or pipe.
- Dispatches messages to handlers for printing, logging, or forwarding.
- Supports empty messages (Ping/Pong) and TX/RX correlation.
- Battery simulator mode: impersonates a BT-E6000 on the bus.
"""

import select
import sys
import time
from collections import deque
from datetime import datetime, timedelta
import traceback
import crcmod.predefined

from config import Config
from logger import NDJSONLogger
from message import Msg, MsgStatus
from message_dispatcher import MessageDirection, MessageDispatcher
from mock_uart import MockUART
from pipe_uart import PipeUART
from pyserial_uart import PySerialUART
from pigpio_uart import PigpioUART
from battery_simulator import BatterySimulator

# ---------- CONFIG ----------
DEVICE = "/dev/serial0"
BAUD = 9600
PIPE = "/tmp/sut_pipe"
MSG_TIMEOUT = 0.5  # seconds for incomplete message
TX_TIMEOUT = 1     # seconds for TX/RX timeout

# ---------- COLORS ----------
RED = "\033[91m"     # CRC error
YELLOW = "\033[93m"  # incomplete / timeout
RESET = "\033[0m"
DIM = "\033[2m"

# ---------- CRC ----------
crc16_func = crcmod.predefined.mkCrcFun('x-25')  # matches parser

# ---------- HELPERS ----------
PROMPT = "SUT> "

def print_prompt():
    sys.stdout.write(PROMPT)
    sys.stdout.flush()

def print_message(msg: str):
    # Clear current line and move cursor to start
    sys.stdout.write("\r")  
    sys.stdout.write(" " * (len(PROMPT) + 80))  # Clear prompt + some space
    sys.stdout.write("\r")  # back to start again
    sys.stdout.write(msg + "\n")
    print_prompt()

GREEN = "\033[92m"

# ---------- MODE ----------
MODE_LOGGING = "logging"
MODE_SIMULATOR = "simulator"

def ask_mode() -> str:
    """Ask user to select operating mode."""
    print()
    print("=" * 40)
    print("  Select Mode")
    print("=" * 40)
    print(f"  1) {GREEN}Logging Mode{RESET}      (RX + RX2 sniffing)")
    print(f"  2) {YELLOW}Simulator Mode{RESET}    (Battery BMS simulation)")
    print("=" * 40)
    while True:
        choice = input("  Select [1/2]: ").strip()
        if choice == "1":
            return MODE_LOGGING
        if choice == "2":
            return MODE_SIMULATOR
        print("  Please enter 1 or 2")

def ask_bool(prompt: str, default: bool = True) -> bool:
    """Prompt user for yes/no input, return boolean."""
    yes_no = "Y/n" if default else "y/N"
    while True:
        ans = input(f"{prompt} ({yes_no}): ").strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False

def read_input_nonblocking() -> str | None:
    rlist, _, _ = select.select([sys.stdin], [], [], 0)
    if sys.stdin in rlist:
        line = sys.stdin.readline().rstrip("\n")
        return line
    return None

def make_logger(config_section: dict | bool | None) -> NDJSONLogger | None:
    """Return an NDJSONLogger based on config, prompt user if needed."""
    if config_section is False:
        return None
    if config_section is None:
        if ask_bool("Enable logger", default=True):
            return NDJSONLogger()
        return None
    return NDJSONLogger(config=config_section)

def print_rx_result(msg: Msg):
    """Print RX message to console with color based on status."""
    color = RESET
    message: str = ""

    if msg.status == MsgStatus.OK:
        message = f"{msg}"
    elif msg.status == MsgStatus.INCOMPLETE:
        color = YELLOW
        message = f"INCOMPLETE {msg}"
    elif msg.status == MsgStatus.CRC_ERROR:
        color = RED
        message = f"CRC ERROR {msg} ({msg.status_info})"
    elif msg.status == MsgStatus.NA:
        color = RED
        message = f"NA {msg}"

    print_message(f"{color}R: {message}{RESET}")

# ---------- GLOBAL QUEUES ----------
tx_queue: dict[int, Msg] = {}  # map sequence → Msg for TX/RX correlation
logger = None

# ---------- MESSAGE HANDLERS ----------
def print_handler(msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
    """Print all messages to stdout."""
    if direction & MessageDirection.RX:
        print_rx_result(msg)
    if direction & MessageDirection.TX:
        print_message(f"{DIM}S: {msg}{RESET}")

def print_handler_ch2(msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
    """Print messages from the second channel (TX pin as RX)."""
    if direction & MessageDirection.RX:
        print_rx_result_ch2(msg)

def print_rx_result_ch2(msg: Msg):
    """Print CH2 RX message to console with color based on status."""
    CYAN = "\033[96m"
    color = CYAN
    message: str = ""

    if msg.status == MsgStatus.OK:
        message = f"{msg}"
    elif msg.status == MsgStatus.INCOMPLETE:
        color = YELLOW
        message = f"INCOMPLETE {msg}"
    elif msg.status == MsgStatus.CRC_ERROR:
        color = RED
        message = f"CRC ERROR {msg} ({msg.status_info})"
    elif msg.status == MsgStatus.NA:
        color = RED
        message = f"NA {msg}"

    print_message(f"{color}R2: {message}{RESET}")

def log_handler(msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
    """Log TX/RX pairs and manage TX queue."""
    global tx_queue, logger
    if direction & MessageDirection.TX:
        if msg.seq in tx_queue:
            print_message(f"{RED}TX sequence collision: {msg.seq}{RESET}")
        tx_queue[msg.seq] = msg
    if direction & MessageDirection.RX:
        tx_msg = tx_queue.pop(msg.seq, None)
        if logger:
            logger.log(tx=f"{tx_msg}", rx=f"{msg}", notes=msg.status.name if msg.status else "")

def log_handler_ch2(msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
    """Log messages from second channel."""
    global logger
    if direction & MessageDirection.RX:
        if logger:
            logger.log(tx=None, rx=f"{msg}", notes=f"CH2 {msg.status.name}" if msg.status else "CH2")

def clean_tx_queue():
    """Remove TX messages older than TX_TIMEOUT."""
    now = datetime.now()
    old_keys = [seq for seq, msg in tx_queue.items() if getattr(msg, 'sent_at', now) < now - timedelta(seconds=TX_TIMEOUT)]
    for seq in old_keys:
        tx_msg = tx_queue.pop(seq)
        if logger:
            logger.log(tx=f"{tx_msg}", rx="", notes="TIMEOUT")

def ping_handler(msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
    """Reply to empty messages with a 'pong'."""
    if direction & MessageDirection.RX:
        reply = Msg.reply_for_msg(msg)
        disp.send_message(reply)

def make_pipe_forwarder(target_dispatcher: MessageDispatcher):
    """Return a handler that forwards RX messages from one dispatcher to another."""
    def handler(msg: Msg, disp: MessageDispatcher, direction: MessageDirection):
        if direction & MessageDirection.RX:
            target_dispatcher.send_message(msg)
    return handler

# --------- COMMAND HANDLER ---------
simulator: BatterySimulator | None = None

def handle_user_command(line: str, dispatcher: MessageDispatcher) -> None:
    """Handle a line typed by the user."""
    global simulator
    line = line.strip()
    if not line:
        return

    parts = line.lower().split()
    cmd = parts[0]

    if cmd == "ping":
        print_message("User requested PING")
        ping = Msg()
        ping.sender = 0x40
        ping.seq = 0x01
        dispatcher.send_message(ping)
    elif cmd == "status":
        print_message(f"TX queue size:{len(tx_queue)}")
        if simulator:
            b = simulator.battery
            state_name = {0x00: "Init", 0x02: "Precharge", 0x03: "Charging"}.get(b.state, f"0x{b.state:02X}")
            print_message(f"SIM: State={state_name} V={b.pack_voltage_mv}mV SOC={b.soc_percent}% T={b.ntc_max}/{b.ntc_avg}/{b.th002_mosfet}°C")
    elif cmd == "voltage" and len(parts) >= 2:
        if simulator:
            try:
                simulator.set_voltage(int(parts[1]))
            except ValueError:
                print_message("Usage: voltage <mV>  (e.g. voltage 38300)")
    elif cmd == "soc" and len(parts) >= 2:
        if simulator:
            try:
                simulator.set_soc(int(parts[1]))
            except ValueError:
                print_message("Usage: soc <percent>  (e.g. soc 62)")
    elif cmd == "temp" and len(parts) >= 4:
        if simulator:
            try:
                simulator.set_temperatures(int(parts[1]), int(parts[2]), int(parts[3]))
            except ValueError:
                print_message("Usage: temp <ntc_max> <ntc_avg> <th002>  (e.g. temp 22 21 22)")
    elif cmd == "help":
        print_message("Commands: ping, status, help")
        if simulator:
            print_message("Simulator: voltage <mV>, soc <percent>, temp <max> <avg> <th002>")
    else:
        print_message(f"Unknown command: {line}  (type 'help')")

# ---------- MAIN ----------
def main():
    global logger, simulator

    # Load config
    config = Config("config.json")
    uart_config = config.get_section("uart") or {}

    # Mode selection
    mode = ask_mode()

    if mode == MODE_SIMULATOR:
        print(f"\n{YELLOW}=== BATTERY SIMULATOR MODE ==={RESET}")
        print(f"{YELLOW}WARNING: TX pin will be active! Do NOT connect a real battery.{RESET}\n")
        # Force TX enabled for simulator
        uart_config["tx_enabled"] = True
    else:
        print(f"\n{GREEN}=== LOGGING MODE ==={RESET}\n")

    # Logger
    logger = make_logger(config.get_section("logger"))

    # Open serial device (CH1: hardware UART)
    try:
        serial_uart = PySerialUART.from_config(uart_config)
    except Exception as e:
        print(f"{RED}Serial problem{RESET}")
        sys.exit(1)

    # Disable internal pull-ups AFTER serial is opened.
    # The kernel UART driver sets GPIO15 to ALT0 with pull-up,
    # which disturbs the battery bus. We override just the pull setting.
    if mode == MODE_LOGGING:
        try:
            import pigpio
            pi = pigpio.pi()
            if pi.connected:
                pi.set_pull_up_down(14, pigpio.PUD_OFF)
                pi.set_pull_up_down(15, pigpio.PUD_OFF)
                pi.stop()
        except Exception:
            pass

    dispatcher = MessageDispatcher(serial_uart)
    dispatcher.register_message_type(None, Msg)
    dispatcher.subscribe(None, print_handler, direction=MessageDirection.BOTH)
    dispatcher.subscribe(None, log_handler, direction=MessageDirection.BOTH)

    # Mode-specific setup
    ch2_dispatcher = None
    ch2_uart = None

    if mode == MODE_LOGGING:
        # Open second channel (CH2: bit-bang RX on TX pin via pigpio)
        if not uart_config.get("tx_enabled", True):
            try:
                ch2_uart = PigpioUART.from_config(uart_config)
                ch2_dispatcher = MessageDispatcher(ch2_uart)
                ch2_dispatcher.register_message_type(None, Msg)
                ch2_dispatcher.subscribe(None, print_handler_ch2, direction=MessageDirection.RX)
                ch2_dispatcher.subscribe(None, log_handler_ch2, direction=MessageDirection.RX)
            except Exception as e:
                print(f"{YELLOW}CH2 (pigpio) not available: {e}{RESET}")
                print(f"{YELLOW}Install pigpio and start pigpiod for dual-channel sniffing{RESET}")

    elif mode == MODE_SIMULATOR:
        simulator = BatterySimulator(dispatcher, print_fn=print_message)
        simulator.start()

    # Open pipe
    try:
        pipe_uart = PipeUART(PIPE)
    except Exception:
        print(f"{RED}Pipe problem{RESET}")
        sys.exit(1)

    pipe_dispatcher = MessageDispatcher(pipe_uart)
    pipe_dispatcher.register_message_type(None, Msg)
    pipe_dispatcher.subscribe('*', make_pipe_forwarder(dispatcher), direction=MessageDirection.RX)

    # Main loop
    try:
        print_prompt()
        while True:
            dispatcher.poll()
            if ch2_dispatcher:
                ch2_dispatcher.poll()
            pipe_dispatcher.poll()
            clean_tx_queue()

            # Check for user input
            user_line = read_input_nonblocking()
            if user_line is not None:
                handle_user_command(user_line, dispatcher)

            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nExiting…")
    finally:
        pipe_uart.close()
        serial_uart.close()
        if ch2_uart:
            ch2_uart.close()
        if logger:
            logger.flush()

if __name__ == "__main__":
    main()
