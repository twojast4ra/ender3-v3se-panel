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
    # Tools: the boxes and switches show what the printer has
    p.state["settings"] = {"M593": [{"X": True, "F": 40.0, "D": 0.15}, {"Y": True, "F": 38.5, "D": 0.1}],
                           "M900": {"K": 0.04}, "M412": {"S": 1.0}, "M420": {"S": 0.0, "Z": 10.0}}
    a._refresh_tools()
    vals = (a.is_x.get(), a.is_xd.get(), a.is_y.get(), a.is_yd.get(), a.la_k.get())
    assert vals == ("40", "0.15", "38.5", "0.1", "0.04"), vals
    sw = {g: (var.get(), cb.instate(["alternate"])) for cb, var, g in a._switches}
    assert sw == {"M412": (1, False), "M413": (0, True), "M420": (0, False)}, sw
    print("tools boxes", vals, "switches", sw, "pid choices", a.pid_nz["values"][:3], "...", a.pid_bd["values"][-2:])
    # Last report
    p.state["report_title"] = "Probe repeatability, 5 touches, 12:00"
    p.state["report"] = ["Mean: 0.002 Min: -0.003 Max: 0.006 Range: 0.009", "Standard Deviation: 0.003"]
    a._refresh_report()
    txt = a.report_boxes[0][1].get("1.0", "end").strip()
    assert "Standard Deviation" in txt and len(a.report_boxes) == 2, txt
    # a print from this computer, half way
    p.state["host"] = {"file": "cambox.gcode", "path": "", "state": "printing", "sent": 500, "total": 1000, "layer": 6,
                       "layers": 12, "estimate_s": 3600, "started": time.time() - 1800, "paused_s": 0.0,
                       "paused_at": None, "ended": None, "error": "", "resends": 2, "note": ""}
    a._refresh_host()
    print("host line:", a.v_host.get(), "|", a.v_host_note.get(), "| top bar:", a._progress_text())
    assert "50%" in a.v_host.get() and "layer 6 / 12" in a.v_host.get()
    p.host_active = lambda: True                 # the top bar and the 3D view during a print from this computer
    a._tick()
    assert "PRINTING from this computer" in a.v_busy.get() and a.view3d.homed, (a.v_busy.get(), a.view3d.homed)
    del p.host_active
    p.state["host"]["state"] = "done"
    p.state["host"]["ended"] = time.time()
    # the finished alert: a message window that does not block
    a._print_ended({"kind": "host", "how": "done", "file": "cambox.gcode", "elapsed": 3725, "detail": "", "t": time.time()})
    tops = [w for w in a.winfo_children() if isinstance(w, tk.Toplevel)]
    assert tops, "no alert window"
    print("alert:", a.status_msg.get())
    for w in tops:
        w.destroy()
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
