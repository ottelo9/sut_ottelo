from device import Device
import json
import os
from datetime import datetime, timezone

class NDJSONLogger:
    def __init__(self, src="NA", dev=None, intent=None, base_path="data", buffer_size=100, fsync=False, config:dict=None):
        self.base_path = base_path
        self.buffer = []
        self.buffer_size = buffer_size
        self.fsync = fsync
        self.current_date = None
        self.src = src
        self.dev = dev
        self.intent = intent

        # Override with config file if provided
        if config:
            self._load_from_config(config)

        # If no device set yet, ask user
        if  self.dev is None:
            self._print_dev_menu()

        print(f"Logging enabled for device {self.dev} from source {self.src}: {self.intent}")
    
    def _load_from_config(self, config:dict):
        if "source" in config:
            self.src = config["source"]
        if "device" in config:
            self.dev = config["device"]
        if "intent" in config:
            self.intent = config["intent"]
        if "buffer_size" in config:
            self.buffer_size = config["buffer_size"]
        if "fsync" in config:
            self.fsync = config["fsync"]

    def _print_dev_menu(self):
        devices = [d.value for d in Device]
        n_cols = 4
        n_rows = (len(devices) + n_cols - 1) // n_cols  # ceiling division
        col_width = 20  # adjust depending on longest device name

        # build a matrix of row-wise top-to-bottom per column
        for row in range(n_rows):
            for col in range(n_cols):
                idx = row + col * n_rows
                if idx < len(devices):
                    print(f"{idx+1:2}: {devices[idx]:<{col_width}}", end='')
            print()  # newline per row

        # prompt selection
        choice = int(input("> ")) - 1
        self.dev = devices[choice]

    def _get_file_path(self):
        now = datetime.now(timezone.utc)
        date_path = now.strftime("%Y/%m")   # folder = YYYY/MM
        filename = now.strftime("%d.ndjson")  # file = DD.ndjson

        path = os.path.join(self.base_path, date_path, filename)
        return path, now.strftime("%Y-%m-%d")  # optional date string for tracking

    def _ensure_file(self, path):
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)

    def log(self, tx, rx, notes=None):
        record = {
            "v": 1,
            "src": self.src,
            "t": datetime.now(timezone.utc).isoformat() + "Z",
            "dev": self.dev,
            "intent": self.intent,
            "tx": tx,
            "rx": rx,
        }

        if notes:
            record["notes"] = notes

        self.buffer.append(record)

        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return

        path, date_str = self._get_file_path()

        # Handle date rollover
        if self.current_date != date_str:
            self.current_date = date_str

        self._ensure_file(path)

        with open(path, "a") as f:
            for record in self.buffer:
                line = json.dumps(record, separators=(",", ":"))
                f.write(line + "\n")

            if self.fsync:
                f.flush()
                os.fsync(f.fileno())

        self.buffer.clear()

    def close(self):
        self.flush()
