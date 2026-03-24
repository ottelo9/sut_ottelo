from datetime import datetime
from enum import Enum
import struct

import crcmod.predefined

class MsgStatus(Enum):
    NA = -1
    OK = 0
    CRC_ERROR = 1
    INCOMPLETE = 2
    
class Msg:
    PREFIX_FORMAT = 'BBB' # 3 byte prefix -> 0x00 0xHS 0xLL
    PREFIX_VALUE = 0x00   # example prefix byte
    
    SUFFIX_FORMAT = 'H'   # 2 byte suffix -> 0xCC 0xCC

    FORMAT = ''           # subclasses override
    FIELDS = []           # attribute names in order

    def __init__(self):
        self.status: MsgStatus = MsgStatus.NA
        self.status_info: str = '' # calc={calc:04X} recv={msg.crc:04X}
        self.sent_at: datetime | None = None
        self.receieved_at: datetime | None = None

        self.crc_func = crcmod.predefined.mkCrcFun('x-25')

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
        result.seq = msg.seq | 0x80

    def pack(self):
        # 1. Collect payload values
        values = [getattr(self, f) for f in self.FIELDS]

        # 2. Pack payload
        values_bytes = struct.pack(self.FORMAT, *values)
        length = len(values_bytes)
        prefix_bytes = struct.pack("BB", (self.sender | self.seq) & 0xFF, length)
        payload_bytes = prefix_bytes + values_bytes

        # 3. Calculate CRC over payload (or include prefix if your protocol does)
        crc_value = self.crc_func(payload_bytes)
        crc_bytes = struct.pack('<H', crc_value)  # little-endian CRC

        # 4. Prepend prefix and append CRC
        self.data = bytes([self.PREFIX_VALUE]) + payload_bytes + crc_bytes

        return self.data

    @classmethod
    def unpack(cls, data: bytes):
        if not cls.FORMAT or not cls.FIELDS:
            raise NotImplementedError("Subclasses must define FORMAT and FIELDS")

        payload_size = struct.calcsize(cls.FORMAT)
        total_size = 1 + payload_size + 2  # prefix + payload + CRC

        # 1. Check length
        if len(data) < total_size:
            return None, MsgStatus.INCOMPLETE

        # 2. Extract parts
        prefix = data[0]
        payload_bytes = data[1:1 + payload_size]
        crc_bytes = data[1 + payload_size:1 + payload_size + 2]

        # 3. Validate prefix (optional but recommended)
        if prefix != cls.PREFIX_VALUE:
            return None, MsgStatus.CRC_ERROR  # or define PREFIX_ERROR if needed

        # 4. Compute CRC
        received_crc = struct.unpack('<H', crc_bytes)[0]
        calculated_crc = cls.crc16_func(payload_bytes)

        if received_crc != calculated_crc:
            return None, MsgStatus.CRC_ERROR

        # 5. Unpack payload
        values = struct.unpack(cls.FORMAT, payload_bytes)

        obj = cls()
        for field, value in zip(cls.FIELDS, values):
            setattr(obj, field, value)

        return obj, MsgStatus.OK