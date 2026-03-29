from uart_interface import UARTInterface

class MockUART(UARTInterface):
    def __init__(self):
        self.in_buffer = bytearray()
        self.out_buffer = bytearray()

    def read(self, size: int = 1) -> bytes:
        data = self.in_buffer[:size]
        self.in_buffer = self.in_buffer[size:]
        return bytes(data)

    def write(self, data: bytes) -> int:
        # self.out_buffer.extend(data)
        self.in_buffer.extend(data) # echo input
        return len(data)
    
    def close(self):
        pass
    
    @property
    def in_waiting(self) -> int:
        return len(self.out_buffer)