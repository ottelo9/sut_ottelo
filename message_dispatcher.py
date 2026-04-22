from collections import defaultdict, deque
from typing import Callable, Deque, Dict, List, Union, Optional
from message import Msg, MsgStatus
from uart_interface import UARTInterface
from enum import Flag, auto
from datetime import datetime

MAX_PAYLOAD_LENGTH = 32  # max known Shimano payload: 22 bytes (Cmd 0x10 telemetry)

class MessageDirection(Flag):
    RX = auto()    # subscriber wants incoming messages
    TX = auto()    # subscriber wants outgoing messages
    BOTH = RX | TX # convenience flag

# --- Event-driven Dispatcher ---
class MessageDispatcher:
    def __init__(self, uart: UARTInterface, rx_queue=None) -> None:
        """
        uart: any object implementing UARTInterface (e.g., pyserial.Serial or a mock)
        rx_queue: optional queue.Queue for deferred RX dispatch (enables ordered multi-channel output)
        """
        self.uart: UARTInterface = uart
        self.rx_queue = rx_queue
        # Maps command byte or '*' → list of callbacks
        self.subscribers: Dict[Union[int, str], List[tuple[Callable[[Msg, "MessageDispatcher", MessageDirection], None], MessageDirection]]] = defaultdict(list)
        # Maps command byte → Msg subclass
        self.message_map: Dict[int, type[Msg]] = {}
        # Receive buffer for partial messages
        self.rx_buffer: bytearray = bytearray()
        # FIFO send queue
        self.tx_queue: Deque[Msg] = deque()

    # ----------------------------
    def register_message_type(self, cmd_byte: int, msg_cls: type[Msg]) -> None:
        """Associate a command byte with a Msg subclass."""
        self.message_map[cmd_byte] = msg_cls

    # ----------------------------
    def subscribe(
        self,
        cmd_byte: Union[int, str],
        callback: Callable[[Msg, "MessageDispatcher", MessageDirection], None],
        direction: MessageDirection = MessageDirection.RX
    ) -> None:
        """
        Subscribe a callback to a specific command.

        Parameters:
        - cmd_byte: int command or '*' for wildcard subscription
        - callback: function taking three arguments:
            1. Msg object
            2. Dispatcher instance
            3. MessageDirection (RX or TX)
        - direction: MessageDirection flag indicating when to call the subscriber
                    (RX, TX, or BOTH)
        """
        self.subscribers[cmd_byte].append((callback, direction))

    # ----------------------------
    def send_message(self, msg_obj: Msg) -> None:
        """
        Append a message object to the TX queue. The dispatcher will call
        pack() when sending and broadcast TX events after writing.
        """
        self.tx_queue.append(msg_obj)
    
    # ----------------------------
    def poll(self) -> None:
        """
        Process one iteration of the dispatcher.

        This is the method the application should call repeatedly
        in its main loop. It performs two main tasks:

        1. Reads incoming bytes from UART and dispatches any complete messages
        to subscribers. Partial messages are buffered internally.
        2. Flushes any outgoing messages in the TX queue to the UART, ensuring
        that messages queued by subscribers are sent sequentially.

        Usage:
            while True:
                dispatcher.poll()
                # other application logic
        """
        # Handle incoming messages
        self._read_and_dispatch()

        # Handle outgoing messages (skip in deferred mode — use flush_tx() from main thread)
        if self.rx_queue is None:
            self._flush_send_queue()

    # ----------------------------
    def _broadcast(
        self, 
        msg_obj: Msg, 
        direction: MessageDirection
    ) -> None:
        """
        Broadcast a message to all subscribers based on its command and the given direction.

        Subscribers registered for a specific command are called if the message has a 'cmd' attribute.
        Wildcard subscribers ('*') are always called. Each subscriber is only called if
        its MessageDirection flag matches the provided direction.

        Parameters:
        - msg_obj: The message object being broadcast
        - direction: MessageDirection.RX or MessageDirection.TX
        """
        # Determine command if available
        cmd: Optional[int] = getattr(msg_obj, 'cmd', None)

        # Broadcast to specific command subscribers
        if cmd in self.subscribers:
            for cb, dir_flag in self.subscribers[cmd]:
                if direction in dir_flag:
                    cb(msg_obj, self, direction)

        # Broadcast to wildcard subscribers
        for cb, dir_flag in self.subscribers.get('*', []):
            if direction in dir_flag:
                cb(msg_obj, self, direction)

    # ----------------------------
    def flush_tx(self) -> None:
        """Flush the TX queue. Use from main thread when rx_queue is set."""
        self._flush_send_queue()

    # ----------------------------
    def _flush_send_queue(self) -> None:
        """
        Send queued messages to UART.
        """
        while self.tx_queue:
            msg_obj = self.tx_queue.popleft()
            msg_bytes = msg_obj.pack()
            self.uart.write(msg_bytes)
            msg_obj.sent_at = datetime.now()
            self._broadcast(msg_obj, MessageDirection.TX)

    # ----------------------------
    def _read_and_dispatch(self) -> None:
        """
        Read bytes from UART, parse complete messages, and broadcast to subscribers.
        Partial messages are buffered until complete.
        """
        # Check how many bytes are available
        available_bytes = self.uart.in_waiting
        if available_bytes > 0:
            data = self.uart.read(available_bytes)
            self.rx_buffer.extend(data)

        while True:
            # Minimum message size = 5 bytes (prefix + header + length + CRC)
            if len(self.rx_buffer) < 5:
                break
            # Check prefix
            if self.rx_buffer[0] != 0x00:
                # discard until next possible prefix
                self.rx_buffer.pop(0)
                continue
            # Reject unreasonable payload lengths (bit-bang noise protection)
            if self.rx_buffer[2] > MAX_PAYLOAD_LENGTH:
                self.rx_buffer.pop(0)
                continue

            handled: bool = False
            error: bool = False
            # Try all registered Msg classes to unpack
            for msg_cls in self.message_map.values():
                msg_obj, status = msg_cls.unpack(self.rx_buffer)
                if status == MsgStatus.OK:
                    msg_obj.receieved_at = datetime.now()
                    # Remove processed bytes from buffer
                    total_len: int = len(msg_obj.data)
                    self.rx_buffer = self.rx_buffer[total_len:]

                    if self.rx_queue is not None:
                        self.rx_queue.put((msg_obj, self))
                    else:
                        self._broadcast(msg_obj, MessageDirection.RX)

                    handled = True
                    break  # message processed
                if status in [ MsgStatus.CRC_ERROR, MsgStatus.PREFIX_ERROR ]:
                    error = True
            
            # TODO: clean this up, this will be slow and skips unknown types
            if not handled:
                # TODO: this makes receiving a rolling window, but CRC error would take a couple of polls to filter through
                # Not enough bytes yet or CRC error
                # Prevent runaway buffer
                if len(self.rx_buffer) > 1024 or error:
                    self.rx_buffer.pop(0)
                    error = False
                break