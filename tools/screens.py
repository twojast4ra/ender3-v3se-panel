"""Windows only: regenerate the README screenshots in docs/screens/.
Opens the panel against a made-up printer state (no printer needed), shows each tab and captures
the window with PrintWindow, so the window may be taller than the screen and nothing else shows.
Usage: python tools/screens.py [sample.gcode]   (the gcode fills the Plate tab; optional)
"""
import ctypes
import os
import shutil
import struct
import sys
import tempfile
import time
import types
import zlib
from ctypes import wintypes

m = types.ModuleType("serial")
m.Serial = object
m.SerialException = Exception
t = types.ModuleType("serial.tools")
lp = types.ModuleType("serial.tools.list_ports")
lp.comports = lambda: []
sys.modules.update({"serial": m, "serial.tools": t, "serial.tools.list_ports": lp})
REPO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO)
import prefs as P  # noqa: E402
import app  # noqa: E402
import printer  # noqa: E402

OUT = os.path.join(REPO, "docs", "screens")
TABS = [(0, "move"), (1, "heat"), (2, "level"), (3, "print"), (4, "plate"), (6, "tools")]


def write_png(path, w, h, bgra):
    rows = []
    for y in range(h):
        row = bgra[y * w * 4:(y + 1) * w * 4]
        rgb = bytearray(w * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = row[2::4], row[1::4], row[0::4]
        rows.append(b"\x00" + bytes(rgb))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def capture(root, path):
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    hwnd = int(root.wm_frame(), 16)
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)                  # PW_RENDERFULLCONTENT

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                    ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, wdc)
    write_png(path, w, h, buf.raw)


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp()
    pr = P.Prefs(os.path.join(tmp, "config.json"))
    pr["log_to_file"] = False
    pr["tooltips"] = False
    p = printer.Printer(pr)
    st = p.state
    st.update({"connected": True, "firmware": "Marlin V1.1.0_SD", "firmware_kind": "community", "nozzle_cap": 300,
               "bed_cap": 110, "port": "COM4", "baud": 115200, "nozzle": 210.0, "nozzle_target": 210.0,
               "bed": 60.0, "bed_target": 60.0, "fan": 100})
    st["pos"] = {"x": 112.0, "y": 98.0, "z": 26.4}
    st["homed"] = {"x": True, "y": True, "z": True}
    st["endstops"] = {"x_min": "open", "y_min": "open", "z_min": "TRIGGERED", "filament": "TRIGGERED"}
    st["mesh"] = [[0.27, 0.13, -0.06, -0.19, -0.35, -0.52], [0.28, 0.19, 0.02, -0.09, -0.24, -0.35],
                  [0.35, 0.28, 0.13, 0.02, -0.11, -0.26], [0.39, 0.30, 0.19, 0.08, -0.04, -0.13],
                  [0.45, 0.37, 0.26, 0.19, 0.07, -0.05], [0.50, 0.44, 0.29, 0.25, 0.15, 0.08]]
    st["settings"] = {"M593": [{"X": True, "F": 40.0, "D": 0.15}, {"Y": True, "F": 38.5, "D": 0.1}],
                      "M900": {"K": 0.04}, "M412": {"S": 1.0}, "M413": {"S": 0.0}, "M420": {"S": 1.0, "Z": 10.0},
                      "M851": {"X": -24.25, "Y": -15.0, "Z": -1.05}, "M301": {"P": 11.45, "I": 1.49, "D": 22.02}}
    st["report_title"] = "Probe repeatability, 5 touches, 14:02"
    st["report"] = ["Mean: 0.001250 Min: -0.002500 Max: 0.005000 Range: 0.007500", "Standard Deviation: 0.002795"]
    now = time.time()
    for i in range(300):
        k = min(1.0, i / 90)
        p.temps.append((now - 600 + i * 2, 25 + 185 * k + (0.6 if i % 7 == 0 else 0), 210, 25 + 35 * min(1.0, i / 60), 60))
    layers = 312
    st["host"] = {"file": "wall_box_asa.gcode", "path": "", "state": "printing", "sent": 41234, "total": 98000,
                  "layer": 131, "layers": layers, "estimate_s": 17373, "started": now - 7300, "paused_s": 0.0,
                  "paused_at": None, "ended": None, "error": "", "resends": 0, "note": ""}
    p.host_active = lambda: True
    a = app.App(p)
    a.geometry("1240x730+0+0")          # Windows clamps a window to the screen; keep the whole frame on it
    sample = sys.argv[1] if len(sys.argv) > 1 else None
    if sample:
        named = os.path.join(tmp, "wall_box_asa.gcode")
        shutil.copy(sample, named)
        a.plate.load_path(named)
        st["host"]["layers"] = len(a.plate.layers)
        st["host"]["layer"] = min(131, len(a.plate.layers))

    def shoot(i=0):
        if i >= len(TABS):
            a.destroy()
            return
        idx, name = TABS[i]
        a.nb.select(idx)
        a.after(900, lambda: (capture(a, os.path.join(OUT, f"{name}.png")), print("saved", name), shoot(i + 1)))
    a.after(1200, shoot)
    a.after(60000, lambda: os._exit(3))
    a.mainloop()
    shutil.rmtree(tmp, ignore_errors=True)
    os._exit(0)


if __name__ == "__main__":
    main()
