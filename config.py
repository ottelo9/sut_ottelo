import json
from pathlib import Path

class Config:
    def __init__(self, config_file: str):
        self.data: dict = {}
        self.config_file = config_file
        self.load(config_file)

    def load(self, config_file: str):
        path = Path(config_file)
        if not path.is_file():
            print(f"Warning: config file '{config_file}' not found. Using defaults.")
            self.data = {}  # keep empty dict, defaults will be used
            return

        try:
            with open(config_file) as f:
                self.data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: failed to parse config file '{config_file}': {e}")
            self.data = {}  # fallback to empty dict

    def get_section(self, section: str) -> dict | bool | None:
        """
        Return the section dict, False, or None.
        - dict → normal section
        - None → section missing or null
        - False → section explicitly disabled
        """
        return self.data.get(section, None)