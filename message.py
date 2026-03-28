from datetime import datetime
from enum import Enum
import struct

import crcmod.predefined

class MsgStatus(Enum):
    NA = -1
    OK = 0
    PREFIX_ERROR = 1
    CRC_ERROR = 2
    INCOMPLETE = 3
    
class Msg:
    PREFIX_FORMAT = 'BBB' # 3 byte prefix -> 0x00 0xHS 0xLL
    PREFIX_VALUE = 0x00   # example prefix byte
    
    SUFFIX_FORMAT = 'H'   # 2 byte suffix -> 0xCC 0xCC

    FORMAT = ''           # subclasses override
    FIELDS = []           # attribute names in order

    crc_func = crcmod.predefined.mkCrcFun('x-25')

    def __init__(self):
        self.status: MsgStatus = MsgStatus.NA
        self.status_info: str = '' # calc={calc:04X} recv={msg.crc:04X}
        self.sent_at: datetime | None = None
        self.receieved_at: datetime | None = None

        self.data: bytes =  bytes()
        
        self.sender: int = 0x00
        self.seq: int = 0x00
        self.cmd: int | None = None
        self.crc: int | None = None

    def __str__(self):
        return " ".join(f"{b:02X}" for b in self.data)

    @classmethod
    def reply_for_msg(cls, msg:"Msg"):
        result = cls()
        result.cmd = msg.cmd
        result.seq = msg.seq 
        result.sender = msg.sender | 0x80

    def pack(self):
        # 1. Collect payload values
        values = [getattr(self, f) for f in self.FIELDS]

        # 2. Pack payload
        values_bytes = struct.pack(self.FORMAT, *values)
        length = len(values_bytes)
        prefix_bytes = struct.pack("BB", (self.sender | self.seq) & 0xFF, length)
        payload_bytes = prefix_bytes + values_bytes

        # 3. Calculate CRC over payload (or include prefix if your protocol does)
        crc_value = Msg.crc_func(payload_bytes)
        crc_bytes = struct.pack('<H', crc_value)  # little-endian CRC

        # 4. Prepend prefix and append CRC
        self.data = bytes([self.PREFIX_VALUE]) + payload_bytes + crc_bytes

        return self.data

    @classmethod
    def unpack(cls, data: bytes):
        if len(data) < 5:  # minimal message size
            return None, MsgStatus.INCOMPLETE

        prefix = data[0]
        header = data[1]
        length = data[2]

        total_size = 1 + 2 + length + 2  # prefix + header+length + payload + CRC
        if len(data) < total_size:
            return None, MsgStatus.INCOMPLETE

        payload_bytes = data[1:3 + length]  # header + payload
        crc_bytes = data[3 + length:3 + length + 2]

        if prefix != cls.PREFIX_VALUE:
            return None, MsgStatus.PREFIX_ERROR

        received_crc = struct.unpack('<H', crc_bytes)[0]
        calculated_crc = Msg.crc_func(payload_bytes)
        if received_crc == 0:
            received_crc = calculated_crc
        if received_crc != calculated_crc:
            return None, MsgStatus.CRC_ERROR

        values_bytes = payload_bytes[2:]  # skip header
        if cls.FORMAT:
            values = struct.unpack(cls.FORMAT, values_bytes)
        else:
            values = ()

        obj = cls()
        for field, value in zip(cls.FIELDS, values):
            setattr(obj, field, value)

        obj.seq = header & 0x0F
        obj.sender = header & 0xF0

        obj.data = data[:total_size]  # full message including CRC
        obj.crc = received_crc
        obj.status = MsgStatus.OK

        return obj, MsgStatus.OK