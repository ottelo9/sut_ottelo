#!/usr/bin/env python3
from collections import deque
from enum import Enum
import sys

import serial
import crcmod.predefined
import os
import select
import time
from config import Config
from logger import NDJSONLogger
from parser import ParserMode, UARTParser
import traceback

# ---------- CONFIG ----------
DEVICE = "/dev/serial0"
BAUD = 9600
PIPE = "/tmp/sut_pipe"
MSG_TIMEOUT = 0.5  # seconds for incomplete message

# Colors
RED = "\033[91m"    # CRC error
YELLOW = "\033[93m" # incomplete / timeout
RESET = "\033[0m"

# ---------- STATIC VARS ----------
START_BYTE = 0x00

# ---------- CRC ----------
crc16_func = crcmod.predefined.mkCrcFun('x-25')  # matches your working parser
#crc16_func = crcmod.mkCrcFun(0x11021, rev=True, initCrc=0xFFFF, xorOut=0x0000)

def ask_bool(prompt: str, default: bool = True) -> bool:
    yes_no = "Y/n" if default else "y/N"
    while True:
        ans = input(f"{prompt} ({yes_no}): ").strip().lower()
        if not ans:
            return default  # Enter pressed → default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        
def make_logger(config_section: dict | bool | None) -> NDJSONLogger | None:
    if config_section is False:
        return None
    if config_section is None:
        if ask_bool("Enable logger", default=True):
            return NDJSONLogger()
        return None
    return NDJSONLogger(config=config_section)

config = Config("config.json")
logger = make_logger(config.get_section("logger"))
rx_parser = UARTParser(crc16_func, MSG_TIMEOUT, ParserMode.RX)
tx_parser = UARTParser(crc16_func, MSG_TIMEOUT, ParserMode.TX)

def handle_rx_result(result, tx: str):
    kind = result[0]
    rx = None
    
    tx_formated = " ".join(f"{b:02X}" for b in tx)
    if kind == "OK":
        _, msg = result
        rx = " ".join(f"{b:02X}" for b in msg)
        print(f"{RESET}R: {rx}{RESET}")

    elif kind == "CRC_ERROR":
        _, msg, calc, recv = result
        rx = " ".join(f"{b:02X}" for b in msg)
        print(f"{RED}R: CRC ERROR {rx} (calc={calc:04X} recv={recv:04X}){RESET}")

    elif kind == "INCOMPLETE":
        _, msg = result
        rx = " ".join(f"{b:02X}" for b in msg)
        print(f"{YELLOW}R: INCOMPLETE {rx}{RESET}")

    logger.log(tx=tx_formated, rx=rx, notes=kind)

# Open serial
try:
    ser = serial.Serial(DEVICE, BAUD, bytesize=8, parity='N', stopbits=1, timeout=0.1)
except:
    print(f"{RED}Serial problem{RESET}") # TODO: Create a bit better of error reporting.
    sys.exit(1)

# Open FIFO
if not os.path.exists(PIPE):
    os.mkfifo(PIPE)
pipe_fd = os.open(PIPE, os.O_RDONLY | os.O_NONBLOCK)
# Open a write end in the same process to prevent EOF
dummy_w_fd = os.open(PIPE, os.O_WRONLY | os.O_NONBLOCK)

TX_TIMEOUT = 1

class TxState(Enum):
    IDLE = 0
    WAIT_RX = 1

tx_state = TxState.IDLE
tx_queue = deque()  # queue for incoming TX messages
current_tx = None
tx_start_time = None

try:
    while True:
        rlist, _, _ = select.select([ser, pipe_fd], [], [], 0.1)
        now = time.time()

        # --- RX handling ---
        if ser in rlist:
            data = ser.read(ser.in_waiting or 1)
            if data and tx_state == TxState.WAIT_RX:
                for result in rx_parser.feed(data): # TODO: For the battery tests this should work, because we'll get a response for every TX, but this will fail when using to spoof a battery.
                    handle_rx_result(result, current_tx)
                    tx_state = TxState.IDLE
                    current_tx = None

        # --- read new TX from pipe and queue them ---
        if pipe_fd in rlist:
            data = os.read(pipe_fd, 1024)
            if data:
                for result in tx_parser.feed(data):
                    tx_queue.append(result[1])  # store the msg_bytes

        # --- send next TX if idle ---
        if tx_state == TxState.IDLE and tx_queue:
            current_tx = tx_queue.popleft()
            ser.write(current_tx)
            # Format bytes as hex string
            formatted = " ".join(f"{b:02X}" for b in current_tx)
            # Print with prefix
            print("S:", formatted)
            tx_start_time = time.time()
            tx_state = TxState.WAIT_RX
            time.sleep(0.5) # just to make sure the RX is complete. Parser doesn't handle incomplete data well right now... well, not at all right now.

        # --- timeout handling ---
        if tx_state == TxState.WAIT_RX and (now - tx_start_time) > TX_TIMEOUT:
            # Format bytes as hex string
            formatted = " ".join(f"{b:02X}" for b in current_tx)
            # Print with prefix
            logger.log(tx=formatted, rx=None, notes="NO_REPLY")
            print("R:")
            tx_state = TxState.IDLE
            current_tx = None

except KeyboardInterrupt:
    print("\nExiting…")
finally:
    ser.close()
    os.close(pipe_fd)
    os.close(dummy_w_fd)
    if(logger):
        logger.flush()
