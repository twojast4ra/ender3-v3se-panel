"""Offline smoke test: fake serial module, build the window, exercise the refreshers. Not shipped."""
import os
import sys
import time
import types

m = types.ModuleType("serial")
m.Serial = object
m.SerialException = Exception
t = types.ModuleType("serial.tools")
lp = types.ModuleType("serial.tools.list_ports")
lp.comports = lambda: []
sys.modules.update({"serial": m, "serial.tools": t, "serial.tools.list_ports": lp})

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import prefs as P  # noqa: E402

P.PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_config.json")
import app  # noqa: E402
import printer  # noqa: E402
import ui_help  # noqa: E402
import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

pr = P.Prefs(P.PATH)
pr["log_to_file"] = False
p = printer.Printer(pr)
p.state.update({"connected": True, "firmware": "Marlin V1.1.0_SD", "firmware_kind": "community",
                "nozzle_cap": 300, "bed_cap": 110, "port": "COM4", "baud": 115200})
p.state["pos"] = {"x": 134.2, "y": 125.0, "z": 10.05}
p.state["homed"] = {"x": True, "y": True, "z": True}
p.state["mesh"] = [[0.27, 0.13, -0.06, -0.19, -0.35, -0.52], [0.28, 0.19, 0.02, -0.09, -0.24, -0.35],
                   [0.35, 0.28, 0.13, 0.02, -0.11, -0.26], [0.39, 0.30, 0.19, 0.08, -0.04, -0.13],
                   [0.45, 0.37, 0.26, 0.19, 0.07, -0.05], [0.50, 0.44, 0.29, 0.25, 0.15, 0.08]]
for i in range(300):
    p.temps.append((time.time() - 600 + i * 2, 200 + i * 0.2, 270, 60 + i * 0.1, 100))
a = app.App(p)
found = set()
stack = [a]
while stack:
    w = stack.pop()
    try:
        if isinstance(w, (ttk.Button, ttk.Radiobutton, ttk.Checkbutton, ttk.Label, ttk.LabelFrame)):
            found.add(w.cget("text"))
    except Exception:  # noqa: BLE001
        pass
    stack.extend(w.winfo_children())
print("tooltip keys without widget:", [k for k in ui_help.TOOLTIPS if k not in found])


def step():
    a._refresh_mesh()
    a._refresh_graph()
    a._refresh_settings()
    print("mesh stats:", a.v_meshstats.get())
    print("graph items", len(a.graph.find_all()))
    a._save_prefs()
    print("prefs saved, steps", pr["steps_mm"])
    a.destroy()


import traceback
def guarded():
    try:
        step()
    except Exception:
        traceback.print_exc()
        a.destroy()
a.after(500, guarded)
a.after(8000, lambda: os._exit(3))
a.mainloop()
os.remove(P.PATH)
print("ui ok")
