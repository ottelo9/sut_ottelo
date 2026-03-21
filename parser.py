import time
from logger import NDJSONLogger

START_BYTE = 0x00

STATE_WAIT_START = 0
STATE_HEADER = 1
STATE_LENGTH = 2

PROGRESS = object()

class UARTParser:
    def __init__(self, crc_func, timeout):
        self.buffer = bytearray()
        self.state = STATE_WAIT_START
        self.msg_start_time = None
        self.crc_func = crc_func
        self.timeout = timeout

    def feed(self, data):
        self.buffer.extend(data)
        messages = []

        # mark start time
        if self.state == STATE_WAIT_START and self.buffer and self.buffer[-1] == START_BYTE:
            self.msg_start_time = time.time()

        self._check_timeout(messages)

        while True:
            result = self._parse_one()

            if result is None:
                break
            elif result is PROGRESS:
                continue
            else:
                messages.append(result)

        return messages

    def _check_timeout(self, messages):
        if self.msg_start_time and (time.time() - self.msg_start_time > self.timeout):
            if self.buffer:
                messages.append(("INCOMPLETE", bytes(self.buffer)))
            self._reset()

    def _reset(self):
        self.buffer.clear()
        self.state = STATE_WAIT_START
        self.msg_start_time = None

    def _parse_one(self):
        if self.state == STATE_WAIT_START:
            return self._handle_wait_start()
        elif self.state == STATE_HEADER:
            return self._handle_header()
        elif self.state == STATE_LENGTH:
            return self._handle_length()
        else:
            self._reset()
            return None

    def _handle_wait_start(self):
        while self.buffer and self.buffer[0] != START_BYTE:
            self.buffer.pop(0)

        if not self.buffer:
            return None

        self.state = STATE_HEADER
        return PROGRESS

    def _handle_header(self):
        if len(self.buffer) < 2:
            return None
        self.state = STATE_LENGTH
        return PROGRESS

    def _handle_length(self):
        if len(self.buffer) < 3:
            return None

        length = self.buffer[2]
        total_len = 1 + 1 + 1 + length + 2

        if len(self.buffer) < total_len:
            return None

        msg = self.buffer[:total_len]
        self.buffer = self.buffer[total_len:]

        crc_calc = self.crc_func(msg[1:-2])
        crc_msg = msg[-2] | (msg[-1] << 8)

        self.state = STATE_WAIT_START
        self.msg_start_time = None

        if crc_calc == crc_msg:
            return ("OK", msg)
        else:
            return ("CRC_ERROR", msg, crc_calc, crc_msg)