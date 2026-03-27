import os
import subprocess
import serial
from uart_interface import UARTInterface

class PySerialUART(UARTInterface):
    def __init__(self, port: str, baudrate: int = 9600, bytesize: int = 8, parity: str = 'N', stopbits: float = 1, timeout: float | None = 0.1, tx_enabled: bool = True, tx_gpio: int | None = 14):
        print(f"{port},{baudrate},{bytesize},{parity},{stopbits},{timeout}")
        self.tx_enabled = tx_enabled
        self.tx_gpio = tx_gpio
        self.ser = serial.Serial(
            port,
            baudrate,
            bytesize = bytesize,
            parity = parity,
            stopbits = stopbits,
            timeout = timeout
        )
        if not self.tx_enabled and self.tx_gpio is not None:
            self._disable_tx_pin()

    @classmethod
    def from_config(cls, config:dict=None):
        port: str = '/dev/serial0'
        baud: int = 9600
        bytesize: int = 8
        parity: str = 'N'
        stopbits: float = 1
        timeout: float | None = 0.1
        tx_enabled: bool = True
        tx_gpio: int | None = 14

        if config:
            port = config.get("port", port)
            baud = config.get("baud", baud)
            bytesize = config.get("bytesize", bytesize)
            parity = config.get("parity", parity)
            stopbits = config.get("stopbits", stopbits)
            timeout = config.get("timeout", timeout)
            tx_enabled = config.get("tx_enabled", tx_enabled)
            tx_gpio = config.get("tx_gpio", tx_gpio)

        return cls(port, baud, bytesize, parity, stopbits, timeout, tx_enabled, tx_gpio)

    def _disable_tx_pin(self):
        """Set TX GPIO pin to input (high-impedance) so it doesn't drive the bus."""
        gpio = str(self.tx_gpio)
        # Try pinctrl (newer Raspberry Pi OS)
        try:
            subprocess.run(['pinctrl', 'set', gpio, 'ip'], check=True, capture_output=True)
            print(f"TX pin GPIO{gpio} disabled via pinctrl (input mode)")
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        # Try raspi-gpio (older Raspberry Pi OS)
        try:
            subprocess.run(['raspi-gpio', 'set', gpio, 'ip'], check=True, capture_output=True)
            print(f"TX pin GPIO{gpio} disabled via raspi-gpio (input mode)")
            return
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass
        # Fallback: direct sysfs GPIO (works if pin is not claimed by serial driver)
        try:
            gpio_path = f'/sys/class/gpio/gpio{gpio}'
            if not os.path.exists(gpio_path):
                with open('/sys/class/gpio/export', 'w') as f:
                    f.write(gpio)
            with open(f'{gpio_path}/direction', 'w') as f:
                f.write('in')
            print(f"TX pin GPIO{gpio} disabled via sysfs (input mode)")
            return
        except OSError:
            pass
        print(f"WARNING: Could not disable TX pin GPIO{gpio} - disconnect TX manually")

    def read(self, size: int = 1) -> bytes:
        return self.ser.read(size)

    def write(self, data: bytes) -> int:
        if not self.tx_enabled:
            return len(data)
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
