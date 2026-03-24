import serial
from uart_interface import UARTInterface

class PySerialUART(UARTInterface):
    def __init__(self, port: str, baudrate: int = 9600, bytesize: int = 8, parity: str = 'N', stopbits: float = 1, timeout : float | None = 0.1):
        self.ser = serial.Serial(port, baudrate, bytesize = bytesize, parity=parity, stopbits=stopbits, timeout=timeout)

    @classmethod
    def from_config(cls, config:dict=None):
        port: str = '/dev/serial0'
        baud: int = 9600
        bytesize: int = 8
        parity: str = 'N'
        stopbits: float = 1
        timeout: float | None = 0.1

        if config:
            port = config.get("port", port)
            baud = config.get("baud", baud)
            bytesize = config.get("bytesize", bytesize)
            parity = config.get("parity", parity)
            stopbits = config.get("stopbits", stopbits)
            timeout = config.get("timeout", timeout)

        return cls(port, baud, bytesize, parity, stopbits, timeout)

    def read(self, size: int = 1) -> bytes:
        return self.ser.read(size)

    def write(self, data: bytes) -> int:
        return self.ser.write(data)
    
    def close(self):
        """Close cleanly."""
        try:
            self.ser.close()
        except Exception:
            pass
    
    @property
    def in_waiting(self) -> int:
        return self.ser.in_waiting