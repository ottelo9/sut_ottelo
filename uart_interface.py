from abc import ABC, abstractmethod

class UARTInterface(ABC):
    """
    Abstract base class defining the interface for a UART-like object.
    Any concrete UART must implement read() and write().
    """

    @abstractmethod
    def read(self, size: int = 1) -> bytes:
        """
        Read up to `size` bytes from the UART.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def write(self, data: bytes) -> int:
        """
        Write bytes to the UART.
        Returns the number of bytes written.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def close(self):
        pass

    @property
    @abstractmethod
    def in_waiting(self) -> int:
        """
        Return the number of bytes currently available to read.
        Must be implemented by subclasses.
        """
        pass