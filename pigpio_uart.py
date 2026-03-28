import subprocess
import pigpio
from uart_interface import UARTInterface


class PigpioUART(UARTInterface):
    """
    Bit-bang serial RX on any GPIO pin using pigpio.
    Useful for repurposing the TX pin (GPIO14) as a second RX input.
    Requires pigpiod daemon to be running.
    """

    def __init__(self, gpio: int = 14, baudrate: int = 9600, bits: int = 8):
        self.gpio = gpio
        self.baudrate = baudrate
        self._buffer = bytearray()

        # Ensure pigpiod is running
        try:
            subprocess.run(
                ['pgrep', '-x', 'pigpiod'],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError:
            print("pigpiod not running, starting it...")
            subprocess.run(['sudo', 'pigpiod'], check=True)
            import time
            time.sleep(0.5)

        self.pi = pigpio.pi()
        if not self.pi.connected:
            raise RuntimeError("Could not connect to pigpiod")

        # Set GPIO to input and open bit-bang serial reader
        self.pi.set_mode(gpio, pigpio.INPUT)
        self.pi.bb_serial_read_open(gpio, baudrate, bits)
        print(f"PigpioUART: GPIO{gpio} opened as bit-bang serial RX @ {baudrate} baud")

    @classmethod
    def from_config(cls, config: dict = None):
        gpio: int = 14
        baud: int = 9600

        if config:
            gpio = config.get("tx_gpio", gpio)
            baud = config.get("baud", baud)

        return cls(gpio, baud)

    def _pull(self):
        """Pull any available data from pigpio into internal buffer."""
        count, data = self.pi.bb_serial_read(self.gpio)
        if count > 0:
            self._buffer.extend(data[:count])

    def read(self, size: int = 1) -> bytes:
        self._pull()
        out = bytes(self._buffer[:size])
        del self._buffer[:size]
        return out

    def write(self, data: bytes) -> int:
        return len(data)

    def close(self):
        try:
            self.pi.bb_serial_read_close(self.gpio)
            self.pi.stop()
        except Exception:
            pass

    @property
    def in_waiting(self) -> int:
        self._pull()
        return len(self._buffer)
