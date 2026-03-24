import os
from uart_interface import UARTInterface

class PipeUART(UARTInterface):
    """Reads/writes from a pipe (FIFO)."""
    def __init__(self, path: str = '/tmp/sut_pipe'):
        # Open FIFO
        if not os.path.exists(path):
            os.mkfifo(path)
        self.fd_read = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        # Open a write end in the same process to prevent EOF
        self.fd_write = os.open(path, os.O_WRONLY | os.O_NONBLOCK)

    def read(self, size: int = 1) -> bytes:
        try:
            return os.read(self.fd_read, size)
        except BlockingIOError:
            return b''

    def write(self, data: bytes) -> int:
        raise NotImplementedError("PipeUART is read-only for now.")
        return os.write(self.fd_write, data)

    @property
    def in_waiting(self) -> int:
        """Return number of bytes available to read."""
        return os.fstat(self.fd_read).st_size  # rough estimate
    
    def close(self):
        """Close both ends of the pipe cleanly."""
        try:
            os.close(self.fd_read)
        except Exception:
            pass
        try:
            os.close(self.fd_write)
        except Exception:
            pass