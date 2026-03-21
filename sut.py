#!/usr/bin/env python3
import serial
import crcmod.predefined
import os
import select
import time
from config import Config
from logger import NDJSONLogger
from parser import UARTParser
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
parser = UARTParser(crc16_func, MSG_TIMEOUT)

def handle_result(result, tx: str):
    kind = result[0]
    rx = None
    
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

    logger.log(tx=tx, rx=rx, notes=kind)

def handle_pipe_input(pipe_fd: int, ser: serial.Serial) -> str:
    try:
        msg_str = os.read(pipe_fd, 1024)
        if not msg_str:
            return

        payload = (
            msg_str
            .decode('unicode_escape')
            .encode('latin1')
        )

        msg = bytearray([START_BYTE]) + payload
        crc = crc16_func(msg[1:])
        msg += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

        ser.write(msg)

        # Format bytes as hex string
        formatted = " ".join(f"{b:02X}" for b in msg)
        
        # Print with prefix
        print("S:", formatted)

        return formatted

    except BlockingIOError:
        # This is normal for non-blocking reads; just ignore
        pass
    except Exception as e:
        print("PIPE ERROR:", repr(e))

        # show raw input if available
        try:
            print("RAW:", msg_str)
        except UnboundLocalError:
            print("RAW: <not read>")

        # optional: decoded attempt
        try:
            print("AS TEXT:", msg_str.decode(errors="replace"))
        except Exception:
            pass

        # full traceback (very useful while debugging)
        traceback.print_exc()

quit()

# Open serial
ser = serial.Serial(DEVICE, BAUD, bytesize=8, parity='N', stopbits=1, timeout=0.1)

# Open FIFO
if not os.path.exists(PIPE):
    os.mkfifo(PIPE)
pipe_fd = os.open(PIPE, os.O_RDONLY | os.O_NONBLOCK)

pending_tx = []  # store TX events waiting for a response

try:
    while True:
        rlist, _, _ = select.select([ser, pipe_fd], [], [], 0.1)

        for fd in rlist:
            if fd == ser:
                data = ser.read(ser.in_waiting or 1)
                if not data:
                    continue

                for result in parser.feed(data):
                    handle_result(result, pending_tx.pop())
                
                pending_tx.clear() # There was a tx without rx, just clear it for now.

            elif fd == pipe_fd:
                tx_result = handle_pipe_input(pipe_fd, ser)
                if tx_result is not None:
                    pending_tx.append(tx_result)

except KeyboardInterrupt:
    print("\nExiting…")
finally:
    ser.close()
    os.close(pipe_fd)