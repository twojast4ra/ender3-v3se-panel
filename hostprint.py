"""Reading a sliced gcode file for a print streamed from this computer over USB.
Comments are dropped from what is sent, but read first for the layer count and the slicer's time
estimate. The streaming itself lives in printer.Printer (it owns the serial port).
"""
import os
import re

LAYER_MARKS = (";LAYER_CHANGE", ";LAYER:", "; CHANGE_LAYER")   # Orca/Prusa, Cura, Bambu-style Orca
NUM = re.compile(r"([A-Z])(-?\d*\.?\d+)")
TIME_RES = (
    re.compile(r"^;TIME:\s*([\d.]+)"),                                      # Cura, Orca (Marlin flavour)
    re.compile(r"estimated printing time(?: \(normal mode\))?\s*=\s*(.+)$"),  # Orca, PrusaSlicer
)


def _duration(text):
    """'1d 2h 3m 4s' or '2h 3m' -> seconds."""
    total, found = 0, False
    for n, unit in re.findall(r"(\d+)\s*([dhms])", text):
        total += int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
        found = True
    return total if found else None


class Job:
    """What a host print needs: the commands to send, the layer each one belongs to, the estimate."""

    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.cmds = []           # str, comments and blanks removed
        self.layer_of = []       # layer number (1-based, 0 = before the first layer) per command
        self.layers = 0
        self.estimate_s = None   # slicer's own estimate, when the file carries one
        layer = 0
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                if line.startswith(";"):
                    if line.startswith(LAYER_MARKS):
                        layer += 1
                    elif self.estimate_s is None:
                        for rx in TIME_RES:
                            m = rx.search(line)
                            if m:
                                v = m.group(1).strip()
                                try:
                                    self.estimate_s = float(v)
                                except ValueError:
                                    self.estimate_s = _duration(v)
                                break
                    continue
                cmd = line.split(";", 1)[0].strip()
                if not cmd:
                    continue
                self.cmds.append(cmd)
                self.layer_of.append(layer)
        self.layers = layer
        if not self.cmds:
            raise ValueError(f"{self.name} has no gcode commands")


class Modes:
    """The modal state a pause has to put back: absolute or relative moves and extrusion, the last
    feed rate, and the last commanded position (what the planner was told, a few moves ahead of the head)."""

    def __init__(self):
        self.abs_xyz = True
        self.abs_e = True
        self.feed = None
        self.homed = False
        self.pos = {"x": None, "y": None, "z": None}

    def track(self, cmd):
        w = cmd.split(None, 1)
        word = w[0].upper()
        if word == "G90":
            self.abs_xyz, self.abs_e = True, True
        elif word == "G91":
            self.abs_xyz, self.abs_e = False, False
        elif word == "M82":
            self.abs_e = True
        elif word == "M83":
            self.abs_e = False
        elif word in ("G0", "G1", "G2", "G3", "G92") and len(w) > 1:
            for k, v in NUM.findall(w[1].upper()):
                if k == "F" and word != "G92":
                    self.feed = float(v)
                elif k in "XYZ":
                    key = k.lower()
                    v = float(v)
                    if word == "G92" or self.abs_xyz or self.pos[key] is None:
                        self.pos[key] = v
                    else:
                        self.pos[key] += v
        elif word == "G28":
            self.pos = {"x": None, "y": None, "z": None}
