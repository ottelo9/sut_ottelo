#!/usr/bin/env python3
import serial
import crcmod.predefined
import os
import select
import time

# ---------- CONFIG ----------
DEVICE = "/dev/serial0"
BAUD = 9600
PIPE = "/tmp/bt_pipe"
MSG_TIMEOUT = 0.5  # seconds for incomplete message

# Colors
RED = "\033[91m"    # CRC error
YELLOW = "\033[93m" # incomplete / timeout
RESET = "\033[0m"

# ---------- OPEN UART ----------
ser = serial.Serial(DEVICE, BAUD, bytesize=8, parity='N', stopbits=1, timeout=0.1)

# ---------- OPEN FIFO ----------
if not os.path.exists(PIPE):
    os.mkfifo(PIPE)
pipe_fd = os.open(PIPE, os.O_RDONLY | os.O_NONBLOCK)

# ---------- CRC ----------
crc16_func = crcmod.predefined.mkCrcFun('x-25')  # matches your working parser
#crc16_func = crcmod.mkCrcFun(0x11021, rev=True, initCrc=0xFFFF, xorOut=0x0000)

# ---------- RECEIVER STATE ----------
buffer = bytearray()
state = 0
msg_start_time = None

# ---------- MAIN LOOP ----------
while True:
    # wait for data from UART or pipe
    rlist, _, _ = select.select([ser, pipe_fd], [], [], 0.1)
    for fd in rlist:
        # -------- UART RECEIVE --------
        if fd == ser:
            data = ser.read(ser.in_waiting or 1)
            if not data:
                continue
            buffer.extend(data)
            if state == 0 and buffer[-1] == 0x00:
                msg_start_time = time.time()
            # timeout for incomplete messages
            if msg_start_time and (time.time() - msg_start_time > MSG_TIMEOUT):
                if buffer:
                    msg_hex = " ".join(f"{x:02X}" for x in buffer)
                    print(f"{YELLOW}R: INCOMPLETE {msg_hex}{RESET}")
                buffer = bytearray()
                state = 0
                msg_start_time = None
            # -------- PARSER --------
            while True:
                if state == 0:
                    if buffer and buffer[0] == 0x00:
                        state = 1
                    else:
                        if buffer:
                            buffer.pop(0)
                        else:
                            break
                elif state == 1:
                    if len(buffer) < 2:
                        break
                    header = buffer[1]
                    state = 2
                elif state == 2:
                    if len(buffer) < 3:
                        break
                    length = buffer[2]
                    total_len = 1 + 1 + 1 + length + 2
                    if len(buffer) < total_len:
                        break
                    msg = buffer[:total_len]
                    crc_calc = crc16_func(msg[1:-2])
                    crc_msg = msg[-2] | (msg[-1] << 8)  # little-endian
                    msg_hex = " ".join(f"{x:02X}" for x in msg)
                    if crc_calc == crc_msg:
                        print(f"R: {msg_hex}")
                    else:
                        print(f"{RED}R: CRC ERROR {msg_hex} (calc={crc_calc:04X} recv={crc_msg:04X}){RESET}")
                    buffer = buffer[total_len:]
                    state = 0
                    msg_start_time = None
                else:
                    state = 0
                    msg_start_time = None

        # -------- PIPE SEND --------
        elif fd == pipe_fd:
            try:
                msg_str = os.read(pipe_fd, 1024)
                if msg_str:
                    # convert '\x41\x00' into bytes
                    payload_bytes = msg_str.decode('latin1').encode('latin1').decode('unicode_escape').encode('latin1')
                    # build message: 0x00 + payload
                    msg_to_send = bytearray([0x00]) + payload_bytes
                    # calculate CRC over everything except leading 0x00
                    crc = crc16_func(msg_to_send[1:])
                    # append CRC in little-endian
                    msg_to_send.append(crc & 0xFF)
                    msg_to_send.append((crc >> 8) & 0xFF)
                    ser.write(msg_to_send)
                    print("S:", " ".join(f"{b:02X}" for b in msg_to_send))
            except Exception:
                pass
