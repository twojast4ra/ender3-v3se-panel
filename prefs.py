"""User preferences for the control panel: everything that used to be a hard-coded number.
Stored as JSON next to the app (config.json, not in git). Missing keys fall back to DEFAULTS.
"""
import json
import os
import sys

# next to the program (the .exe or the Linux binary) when packaged by PyInstaller, next to the source otherwise
HERE = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def _data_dir():
    """config.json and logs/ go next to the program, as before. When that folder is not writable
    (a binary copied to /usr/local/bin, a read-only share) they go to the user's own folder instead."""
    if os.access(HERE, os.W_OK):
        return HERE
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        d = os.path.join(base, "Ender3V3SE-panel")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
        d = os.path.join(base, "ender3-v3se-panel")
    os.makedirs(d, exist_ok=True)
    return d


DATA_DIR = _data_dir()
PATH = os.path.join(DATA_DIR, "config.json")

DEFAULTS = {
    "tooltips": True,
    "port": "",                     # "" = find the printer automatically
    "baud": 0,                      # 0 = try the usual rates until the printer answers
    "geometry": "",                 # window size and position, remembered on close
    "steps_mm": [0.1, 1, 10, 50],   # jog step choices
    "feed_xy": 3000,                # jog speeds, mm/min
    "feed_z": 300,
    "feed_e": 300,
    "extrude_mm": 10,               # default length for Extrude / Retract
    "extrude_min_c": 180,           # refuse to push filament below this nozzle temperature
    "nozzle_max": 300,              # upper limits offered; capped further by what the firmware allows
    "bed_max": 110,
    "presets": {                    # material -> nozzle / bed
        "ABS": {"nozzle": 270, "bed": 100},
        "PLA": {"nozzle": 200, "bed": 60},
        "PETG": {"nozzle": 250, "bed": 70},
        "TPU": {"nozzle": 220, "bed": 50},
    },
    "pid_nozzle_c": 270,            # PID tune temperatures
    "pid_bed_c": 100,
    "probe_repeat_n": 5,            # touches in the probe repeatability test
    "zoffset_step": 0.05,           # the +/- buttons on the Level tab
    "level_min_bed_c": 60,          # warn before levelling with the bed below this
    "log_to_file": True,            # session log under logs/
    "alert_when_done": True,        # sound, message window and desktop notification when a print ends
}


class Prefs:
    def __init__(self, path=PATH):
        self.path = path
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                for k, v in stored.items():
                    if k in DEFAULTS:
                        self.data[k] = v
            except (OSError, json.JSONDecodeError):
                pass

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v

    def reset(self):
        self.data = json.loads(json.dumps(DEFAULTS))
