"""Desktop control panel for the Creality Ender-3 V3 SE. Tkinter window, no server, no browser.
Usage: pythonw app.py on Windows (start.cmd), python3 app.py on Linux (start.sh).
Close Pronterface or OctoPrint's connection first: one program per port.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import desktop
from desktop import font, mono
from plateview import PlateView
from prefs import Prefs
from printer import FIRMWARE, Printer, list_serial_ports
from ui_help import GLOSSARY, Tooltip, attach_tooltips
from view3d import PrinterView

VERSION = "0.2.0"

# Readable names for the stored settings (M503). (gcode, letter, label, editable)
SETTING_ROWS = [
    ("M92", "X", "Steps per mm, head (X)", 1), ("M92", "Y", "Steps per mm, bed (Y)", 1),
    ("M92", "Z", "Steps per mm, gantry (Z)", 1), ("M92", "E", "Steps per mm, extruder", 1),
    ("M203", "X", "Max speed, head (mm/s)", 1), ("M203", "Y", "Max speed, bed (mm/s)", 1),
    ("M203", "Z", "Max speed, gantry (mm/s)", 1), ("M203", "E", "Max speed, extruder (mm/s)", 1),
    ("M201", "X", "Max acceleration, head", 1), ("M201", "Y", "Max acceleration, bed", 1),
    ("M201", "Z", "Max acceleration, gantry", 1), ("M201", "E", "Max acceleration, extruder", 1),
    ("M204", "P", "Acceleration while printing", 1), ("M204", "R", "Acceleration while retracting", 1),
    ("M204", "T", "Acceleration while travelling", 1), ("M205", "J", "Junction deviation (cornering)", 1),
    ("M206", "X", "Home offset X", 1), ("M206", "Y", "Home offset Y", 1), ("M206", "Z", "Home offset Z", 1),
    ("M851", "X", "Probe offset X (negative = probe left of nozzle)", 1),
    ("M851", "Y", "Probe offset Y (negative = probe in front of nozzle)", 1),
    ("M851", "Z", "Z offset (nozzle vs probe trigger, mm)", 1),
    ("M420", "Z", "Mesh fade height (mm)", 1),
    ("M301", "P", "Nozzle PID P", 1), ("M301", "I", "Nozzle PID I", 1), ("M301", "D", "Nozzle PID D", 1),
    ("M304", "P", "Bed PID P", 1), ("M304", "I", "Bed PID I", 1), ("M304", "D", "Bed PID D", 1),
    ("M900", "K", "Linear advance K", 1),
    ("M413", "S", "Power-loss recovery (1 on, 0 off)", 1), ("M412", "S", "Filament runout sensor (1 on, 0 off)", 1),
    ("M603", "L", "Filament load length (mm)", 1), ("M603", "U", "Filament unload length (mm)", 1),
    ("M852", "S", "Skew factor", 0), ("M200", "D", "Filament diameter", 0),
]


class App(tk.Tk):
    def __init__(self, printer: Printer):
        super().__init__()
        self.p = printer
        self.prefs = printer.prefs
        self.title(f"Ender-3 V3 SE control  {VERSION}")
        if not desktop.WINDOWS and "clam" in ttk.Style(self).theme_names():
            ttk.Style(self).theme_use("clam")       # Tk's Linux default theme looks like 1995
        self._finished_seen = printer.state["finished_seq"]
        self.geometry(self.prefs["geometry"] or "1240x860")
        self.minsize(1000, 700)
        self.q = queue.Queue()
        self.step = tk.StringVar(value=str(self.prefs["steps_mm"][2] if len(self.prefs["steps_mm"]) > 2 else self.prefs["steps_mm"][0]))
        self._ticks = 0
        self._log_len = 0
        self._last_entry = None
        self._switch_test_until = 0
        Tooltip.enabled = bool(self.prefs["tooltips"])
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(300, self._tick)
        self.after(100, self._drain)

    # ---------- plumbing ----------
    def run(self, action, params=None, confirm=None, then=None):
        """Run an action on a worker thread; replies and refusals come back on the UI thread."""
        if confirm and not messagebox.askyesno("Confirm", confirm):
            return

        def work():
            try:
                r = self.p.act(action, params or {})
                self.q.put(("done", action, r, then))
            except Exception as e:  # noqa: BLE001
                self.q.put(("err", action, str(e), None))
        threading.Thread(target=work, daemon=True).start()

    def _drain(self):
        try:
            while True:
                kind, action, payload, then = self.q.get_nowait()
                if kind == "err":
                    self.status_msg.set(f"{action}: {payload}")
                    messagebox.showwarning("Not done", f"{action}: {payload}")
                else:
                    self.status_msg.set(f"{action}: done   {time.strftime('%H:%M:%S')}")
                    if then:
                        then(payload)
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _close(self):
        if self.p.host_active():
            if not messagebox.askyesno("A print is running from this computer",
                                       "Closing the panel stops the print. Cancel it (heaters off, head moved clear) and close?"):
                return
            try:
                self.p.host_request("cancel")
            except ValueError:
                pass
            t_end = time.time() + 20
            while self.p.host_active() and time.time() < t_end:
                self.update()
                time.sleep(0.1)
        self.prefs["geometry"] = self.geometry()
        try:
            self.prefs.save()
        except OSError:
            pass
        self.destroy()

    def _tick(self):
        st = self.p.state
        if st["connected"]:
            kind = FIRMWARE[st["firmware_kind"]]["label"]
            self.v_conn.set(f"Connected {st['port']} @ {st['baud']}")
            self.v_fw.set(f"{st['firmware']}   ·   {kind}   ·   limits nozzle {self.p.nozzle_limit()} / bed {self.p.bed_limit()} °C")
        else:
            self.v_conn.set("Not connected")
            self.v_fw.set(st["last_error"] or "waiting for the printer")

        def t(v):
            return "--" if v is None else f"{v:.0f}"
        self.v_nozzle.set(f"Nozzle {t(st['nozzle'])} / {t(st['nozzle_target'])} °C")
        self.v_bed.set(f"Bed {t(st['bed'])} / {t(st['bed_target'])} °C")
        pos = st["pos"]
        if pos:
            self.v_pos.set("Head X {x:.1f}   Bed Y {y:.1f}   Nozzle {z:.2f} mm above the plate".format(**pos))
        else:
            self.v_pos.set("position unknown")
        h = st["homed"]
        self.v_homed.set("Homed: " + "  ".join(f"{a.upper()} {'yes' if v else 'no'}" for a, v in h.items()))
        if not st["connected"]:
            self.v_busy.set("no printer")
            self.lab_busy.config(foreground="#b00020")
        elif self.p.host_active():
            word = {"paused": "PAUSED", "pausing": "PAUSING", "resuming": "RESUMING"}.get(st["host"]["state"], "PRINTING")
            self.v_busy.set(f"{word} from this computer " + self._progress_text())
            self.lab_busy.config(foreground="#c77700" if word != "PRINTING" else "#1f6fb0")
        elif st["busy"]:
            self.v_busy.set("BUSY")
            self.lab_busy.config(foreground="#c77700")
        elif st["printing"]:
            self.v_busy.set("PRINTING " + self._progress_text())
            self.lab_busy.config(foreground="#1f6fb0")
        else:
            self.v_busy.set("idle")
            self.lab_busy.config(foreground="#2e7d32")
        es = st["endstops"]
        self.v_endstops.set("Head switch: {}   Bed switch: {}   Probe: {}   Filament: {}".format(
            es.get("x_min", "?"), es.get("y_min", "?"), es.get("z_min", "?"), es.get("filament", "?")))
        self.v_task.set(st["task"])
        self._ticks += 1
        if self._ticks % 4 == 0:            # the heavy widgets once a second
            self._refresh_mesh()
            self._refresh_settings()
            self._refresh_log()
            self._refresh_graph()
            self._refresh_tools()
            self._refresh_report()
        self._refresh_host()
        if st["finished_seq"] != self._finished_seen:
            self._finished_seen = st["finished_seq"]
            self._print_ended(st["finished"])
        if self._switch_test_until and time.time() < self._switch_test_until and not self.p.lock.locked():
            self.run("endstops")
        elif self._switch_test_until and time.time() >= self._switch_test_until:
            self._switch_test_until = 0
            self.v_switchtest.set("switch test finished")
        self._refresh_upload()
        self.view3d.set_position(pos, all(h.values()))
        if self.nb.index(self.nb.select()) == self.plate_tab_index:
            hp = st["host"]
            if self.p.host_active() and hp["layers"] and self.plate.layers and len(self.plate.layers) == hp["layers"]:
                self.plate.set_layer(hp["layer"] - 1)    # the layer being sent, from the file's own markers
            else:
                self.plate.set_position(pos)
        zo = st["settings"].get("M851", {}).get("Z")
        if zo is not None and self.focus_get() is not self.zoff_entry:
            self.v_zoff.set(f"{zo:.2f}")
        bs = st["babysteps"]
        self.v_babysteps.set(f"unsaved nudges this print: {bs:+.2f} mm" if bs else "")
        self.after(300, self._tick)

    @staticmethod
    def _dur(s):
        if s is None:
            return "?"
        s = int(s)
        return f"{s // 3600}h {s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m {s % 60:02d}s"

    def _host_numbers(self, h):
        """(percent, elapsed s, left s or None) for a print from this computer."""
        pct = 100.0 * h["sent"] / h["total"] if h["total"] else 0.0
        end = h["ended"] or time.time()
        paused = h["paused_s"] + ((time.time() - h["paused_at"]) if h["paused_at"] else 0)
        elapsed = max(0.0, end - h["started"] - paused)
        left = None
        if h["estimate_s"]:
            left = max(0.0, h["estimate_s"] * (1 - pct / 100))
        elif pct >= 5:
            left = elapsed * (100 - pct) / pct
        return pct, elapsed, left

    def _progress_text(self):
        h = self.p.state["host"]
        if self.p.host_active():
            pct, elapsed, left = self._host_numbers(h)
            txt = f"{pct:.0f}%"
            if h["layers"]:
                txt += f"   layer {max(1, h['layer'])} / {h['layers']}"
            return txt + f"   {self._dur(left)} left"
        a, b = self.p.state["print_bytes"]
        if not b:
            return self.p.state["print_progress"]
        pct = 100.0 * a / b
        txt = f"{pct:.0f}%"
        if self.plate.layers:
            n = len(self.plate.layers)
            txt += f"   ~layer {max(1, int(pct / 100 * n))} / {n}"
        return txt

    # ---------- layout ----------
    def _build(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        self.v_conn, self.v_fw, self.v_task = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v_nozzle, self.v_bed, self.v_pos, self.v_homed, self.v_busy = (tk.StringVar() for _ in range(5))
        self.v_endstops, self.status_msg, self.v_zoff, self.v_babysteps = (tk.StringVar() for _ in range(4))
        self.v_switchtest = tk.StringVar()
        bold = font(11, "bold")
        ttk.Label(top, textvariable=self.v_conn, font=bold).grid(row=0, column=0, padx=12, sticky="w")
        ttk.Label(top, textvariable=self.v_nozzle, font=bold).grid(row=0, column=1, padx=12, sticky="w")
        ttk.Label(top, textvariable=self.v_bed, font=bold).grid(row=0, column=2, padx=12, sticky="w")
        self.lab_busy = ttk.Label(top, textvariable=self.v_busy, font=bold)
        self.lab_busy.grid(row=0, column=3, padx=12, sticky="w")
        ttk.Label(top, textvariable=self.v_pos).grid(row=1, column=0, columnspan=2, padx=12, sticky="w")
        self.lab_homed = ttk.Label(top, textvariable=self.v_homed)
        self.lab_homed.grid(row=1, column=2, columnspan=2, padx=12, sticky="w")
        self.lab_endstops = ttk.Label(top, textvariable=self.v_endstops)
        self.lab_endstops.grid(row=2, column=0, columnspan=3, padx=12, sticky="w")
        ttk.Button(top, text="Reconnect", command=self._reconnect).grid(row=2, column=3, sticky="e")
        ttk.Label(top, textvariable=self.v_fw, foreground="#666").grid(row=3, column=0, columnspan=4, padx=12, sticky="w")
        ttk.Label(top, textvariable=self.v_task, foreground="#1f6fb0").grid(row=4, column=0, columnspan=4, padx=12, sticky="w")

        nb = ttk.Notebook(self)
        self.nb = nb
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._tab_move(nb)
        self._tab_heat(nb)
        self._tab_level(nb)
        self._tab_print(nb)
        self._tab_plate(nb)
        self._tab_settings(nb)
        self._tab_tools(nb)
        self._tab_prefs(nb)
        self._tab_console(nb)
        self._tab_help(nb)
        self.status_bar = ttk.Label(self, textvariable=self.status_msg, relief="sunken", anchor="w", padding=(6, 2))
        self.status_bar.pack(fill="x", side="bottom")
        attach_tooltips(self)
        for lab, txt in ((self.lab_endstops, "Switch states straight from the printer. 'open' = not pressed. The head switch reads TRIGGERED only when the head is at the left stop. The probe is different: on this printer it reads TRIGGERED while its pin is up, and should read open with the pin down. To check it: Level tab, Probe pin down, Read switches (open), push the pin up with a finger, Read switches (TRIGGERED), Probe pin up."),
                         (self.lab_homed, "Whether each axis has been homed since power-on. All three must say yes before moves are allowed."),
                         (self.lab_busy, "idle: ready. BUSY: the printer is in a move it will not interrupt (homing, levelling, heating wait). PRINTING: a print is running, from the card or from this computer; only speed, flow, fan, Z nudges, pause and cancel are allowed then.")):
            Tooltip(lab, txt)
        self.status_msg.set("Ready. Hover over a control for a hint; switch hints off under Preferences.")

    # ----- Move -----
    def _tab_move(self, nb):
        outer = ttk.Frame(nb, padding=10)
        nb.add(outer, text="Move")
        f = ttk.Frame(outer)
        f.grid(row=0, column=0, sticky="nw")
        self.view3d = PrinterView(outer)
        self.view3d.grid(row=0, column=1, sticky="ne", padx=(16, 0))
        self.view3d.bind("<Button-1>", lambda e: self.view3d.focus_set())
        for key, axis, sign in (("<Left>", "X", -1), ("<Right>", "X", +1), ("<Up>", "Y", -1), ("<Down>", "Y", +1),
                                ("<Prior>", "Z", +1), ("<Next>", "Z", -1)):
            self.view3d.bind(key, lambda e, a=axis, s=sign: self._jog(a, s))

        sf = ttk.LabelFrame(f, text="Start here", padding=8)
        sf.grid(row=0, column=0, columnspan=6, sticky="we", pady=(0, 8))
        ttk.Label(sf, text="Material:").grid(row=0, column=0)
        self.prep_material = ttk.Combobox(sf, width=8, state="readonly", values=list(self.prefs["presets"]))
        self.prep_material.grid(row=0, column=1, padx=4)
        if self.prefs["presets"]:
            self.prep_material.current(0)
        ttk.Button(sf, text="Prepare to print", command=self._prepare).grid(row=0, column=2, padx=8)
        ttk.Button(sf, text="Check Z offset (paper test)", command=self._zcheck).grid(row=0, column=3, padx=8)

        ttk.Label(f, text="Step (mm):").grid(row=1, column=0, sticky="w")
        self.step_frame = ttk.Frame(f)
        self.step_frame.grid(row=1, column=1, columnspan=5, sticky="w")
        self._build_steps()

        def jog(text, axis, sign, element, row, col, padx=4):
            b = ttk.Button(f, text=text, command=lambda: self._jog(axis, sign), width=18, padding=8)
            b.grid(row=row, column=col, padx=padx, pady=4)
            b.bind("<Enter>", lambda e, el=element: self.view3d.set_highlight(el), add="+")
            b.bind("<Leave>", lambda e: self.view3d.set_highlight(None), add="+")
        jog("◄  Head left", "X", -1, "head", 3, 0)
        jog("Head right  ►", "X", +1, "head", 3, 2)
        jog("Bed away  ▲", "Y", -1, "bed", 2, 1)
        jog("Bed towards me  ▼", "Y", +1, "bed", 4, 1)
        jog("Gantry up  ▲", "Z", +1, "gantry", 2, 4, 20)
        jog("Gantry down  ▼", "Z", -1, "gantry", 4, 4, 20)
        ttk.Label(f, text="The bed is what moves front to back; 'towards me' brings the plate forward, so the nozzle ends up nearer the back of the plate.",
                  wraplength=640).grid(row=5, column=0, columnspan=6, sticky="w", pady=(0, 6))
        ttk.Label(f, text="Keyboard: arrows move the head and bed, Page Up / Page Down the gantry, by the chosen step (click the picture first).",
                  foreground="#666", wraplength=640).grid(row=6, column=0, columnspan=6, sticky="w", pady=(0, 8))

        hf = ttk.LabelFrame(f, text="Home", padding=8)
        hf.grid(row=7, column=0, columnspan=6, sticky="w", pady=6)
        ttk.Button(hf, text="Home everything", command=lambda: self.run("home", {"axes": ""})).grid(row=0, column=0, padx=4)
        ttk.Button(hf, text="Home head (X)", command=lambda: self.run("home", {"axes": "X"})).grid(row=0, column=1, padx=4)
        ttk.Button(hf, text="Home bed (Y)", command=lambda: self.run("home", {"axes": "Y"})).grid(row=0, column=2, padx=4)
        ttk.Button(hf, text="Home gantry (Z)", command=lambda: self.run("home", {"axes": "Z"})).grid(row=0, column=3, padx=4)
        ttk.Button(hf, text="Motors off (push by hand)", command=lambda: self.run("motors_off")).grid(row=0, column=4, padx=16)

        ef = ttk.LabelFrame(f, text="Extruder (nozzle must be hot)", padding=8)
        ef.grid(row=8, column=0, columnspan=6, sticky="w", pady=6)
        ttk.Label(ef, text="Length (mm)").grid(row=0, column=0)
        self.e_extrude = ttk.Spinbox(ef, from_=1, to=200, width=6)
        self.e_extrude.set(self.prefs["extrude_mm"])
        self.e_extrude.grid(row=0, column=1, padx=4)
        ttk.Button(ef, text="Extrude", command=lambda: self.run("extrude", {"dist": float(self.e_extrude.get())})).grid(row=0, column=2, padx=4)
        ttk.Button(ef, text="Retract", command=lambda: self.run("extrude", {"dist": -float(self.e_extrude.get())})).grid(row=0, column=3, padx=4)
        ttk.Button(ef, text="Load filament", command=lambda: self.run("filament", {"what": "load"})).grid(row=0, column=4, padx=16)
        ttk.Button(ef, text="Unload filament", command=lambda: self.run("filament", {"what": "unload"})).grid(row=0, column=5, padx=4)

    def _build_steps(self):
        for w in self.step_frame.winfo_children():
            w.destroy()
        for i, s in enumerate(self.prefs["steps_mm"]):
            ttk.Radiobutton(self.step_frame, text=f"{s:g}", value=f"{s:g}", variable=self.step).grid(row=0, column=i, padx=(0, 10))
        n = len(self.prefs["steps_mm"])
        ttk.Radiobutton(self.step_frame, text="custom", value="custom", variable=self.step).grid(row=0, column=n, padx=(10, 2))
        self.step_custom = ttk.Entry(self.step_frame, width=6)
        self.step_custom.insert(0, "5")
        self.step_custom.grid(row=0, column=n + 1)
        if self.step.get() not in [f"{s:g}" for s in self.prefs["steps_mm"]] + ["custom"]:
            self.step.set(f"{self.prefs['steps_mm'][0]:g}")

    def _step_value(self):
        if self.step.get() == "custom":
            try:
                return abs(float(self.step_custom.get()))
            except ValueError:
                return 1.0
        return float(self.step.get())

    def _jog(self, axis, sign):
        d = sign * self._step_value()
        if all(self.p.state["homed"].values()):      # show it at once; the printer's report corrects it
            k = axis.lower()
            nv = self.view3d.target[k] + d
            if k == "z":
                nv = max(0.0, nv)
            self.view3d.target[k] = nv
        self.run("move", {"axis": axis, "dist": d})

    def _prepare(self):
        m = self.prep_material.get()
        if not m:
            return
        pre = self.prefs["presets"][m]
        self.run("prepare", {"material": m},
                 confirm=f"Prepare for {m}: bed to {pre['bed']} °C, home, level with the hot bed, nozzle to {pre['nozzle']} °C. About five minutes; the printer moves by itself. Start?")

    def _zcheck(self):
        self.run("zcheck_start", confirm="The nozzle goes to the plate centre at height 0 (homing first if needed). Then use the Z offset nudge buttons on the Level tab with a sheet of paper under the nozzle until it just drags, and press Save nudges. Start?",
                 then=lambda r: self.nb.select(self.level_tab_index))

    # ----- Heat -----
    def _tab_heat(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Heat")
        self.preset_frame = ttk.LabelFrame(f, text="Presets (nozzle / bed)", padding=8)
        self.preset_frame.grid(row=0, column=0, sticky="w")
        self._build_presets()
        cf = ttk.LabelFrame(f, text="Custom", padding=8)
        cf.grid(row=1, column=0, sticky="w", pady=8)
        self.e_nozzle = ttk.Spinbox(cf, from_=0, to=320, width=6)
        self.e_nozzle.set(200)
        self.e_bed = ttk.Spinbox(cf, from_=0, to=120, width=6)
        self.e_bed.set(60)
        self.lab_nozzle_lim = ttk.Label(cf, text="Nozzle")
        self.lab_nozzle_lim.grid(row=0, column=0)
        self.e_nozzle.grid(row=0, column=1, padx=4)
        ttk.Button(cf, text="Set nozzle", command=lambda: self.run("heat", {"nozzle": self.e_nozzle.get()})).grid(row=0, column=2, padx=4)
        self.lab_bed_lim = ttk.Label(cf, text="Bed")
        self.lab_bed_lim.grid(row=0, column=3, padx=(16, 0))
        self.e_bed.grid(row=0, column=4, padx=4)
        ttk.Button(cf, text="Set bed", command=lambda: self.run("heat", {"bed": self.e_bed.get()})).grid(row=0, column=5, padx=4)
        ttk.Button(cf, text="Save as preset...", command=self._save_preset).grid(row=0, column=6, padx=16)
        sf = ttk.LabelFrame(f, text="Fan, speed and flow (work during a print too)", padding=8)
        sf.grid(row=2, column=0, sticky="w", pady=8)
        self._slider(sf, 0, "Part fan %", 0, 100, 0, lambda v: self.run("fan", {"percent": v}))
        self._slider(sf, 1, "Print speed %", 25, 200, 100, lambda v: self.run("speed", {"percent": v}))
        self._slider(sf, 2, "Flow %", 50, 150, 100, lambda v: self.run("flow", {"percent": v}))
        gf = ttk.LabelFrame(f, text="Last 10 minutes", padding=8)
        gf.grid(row=0, column=1, rowspan=3, sticky="n", padx=16)
        self.graph = tk.Canvas(gf, width=520, height=300, bg="#1e1e1e", highlightthickness=0)
        self.graph.pack()

    def _build_presets(self):
        for w in self.preset_frame.winfo_children():
            w.destroy()
        for i, (name, pr) in enumerate(self.prefs["presets"].items()):
            b = ttk.Button(self.preset_frame, text=f"{name}  {pr['nozzle']} / {pr['bed']}", width=16,
                           command=lambda n=name: self.run("preset", {"name": n}))
            b.grid(row=i // 5, column=i % 5, padx=4, pady=2)
            Tooltip(b, f"Sets the nozzle to {pr['nozzle']} °C and the bed to {pr['bed']} °C. Heating starts at once.")
        cool = ttk.Button(self.preset_frame, text="Cool down everything", command=lambda: self.run("cooldown"))
        cool.grid(row=(len(self.prefs["presets"]) // 5) + 1, column=0, columnspan=2, pady=(8, 0), sticky="w")
        if hasattr(self, "prep_material"):
            self.prep_material["values"] = list(self.prefs["presets"])
        if hasattr(self, "pref_preset_list"):
            self._fill_pref_presets()

    def _save_preset(self):
        name = simpledialog.askstring("Save preset", "Material name:", parent=self)
        if not name:
            return
        try:
            self.prefs["presets"][name.strip()] = {"nozzle": int(float(self.e_nozzle.get())), "bed": int(float(self.e_bed.get()))}
            self.prefs.save()
        except ValueError:
            return
        self._build_presets()

    def _slider(self, parent, row, label, lo, hi, init, cb):
        ttk.Label(parent, text=label, width=14).grid(row=row, column=0, sticky="w")
        var = tk.IntVar(value=init)
        s = ttk.Scale(parent, from_=lo, to=hi, orient="horizontal", length=300, variable=var,
                      command=lambda v: var.set(int(float(v))))
        s.grid(row=row, column=1, padx=6)
        ttk.Label(parent, textvariable=var, width=4).grid(row=row, column=2)
        ttk.Button(parent, text="Apply", command=lambda: cb(var.get())).grid(row=row, column=3, padx=6)

    def _refresh_graph(self):
        c = self.graph
        c.delete("all")
        w, h = int(c["width"]), int(c["height"])
        data = list(self.p.temps)
        now = time.time()
        span = 600.0
        vals = [v for d in data for v in (d[1], d[3]) if v is not None]
        top = max(120, (int(max(vals + [d[2] for d in data] + [d[4] for d in data]) / 50) + 1) * 50) if data else 300
        for yv in range(0, top + 1, 50):
            y = h - 20 - (h - 40) * yv / top
            c.create_line(40, y, w - 10, y, fill="#333")
            c.create_text(34, y, text=str(yv), fill="#888", anchor="e", font=font(8))
        for m in range(0, 11, 2):
            x = 40 + (w - 50) * (1 - m * 60 / span)
            c.create_text(x, h - 8, text=f"-{m} min" if m else "now", fill="#888", font=font(8))

        def pts(idx):
            out = []
            for d in data:
                if d[idx] is None or now - d[0] > span:
                    continue
                x = 40 + (w - 50) * (1 - (now - d[0]) / span)
                y = h - 20 - (h - 40) * d[idx] / top
                out += [x, y]
            return out
        for idx, col, width in ((2, "#8a5a2a", 1), (4, "#2a4a7a", 1), (1, "#e07b2a", 2), (3, "#4a7fd6", 2)):
            p = pts(idx)
            if len(p) >= 4:
                c.create_line(*p, fill=col, width=width)
        c.create_text(w - 12, 10, text="nozzle", fill="#e07b2a", anchor="ne", font=font(8))
        c.create_text(w - 12, 24, text="bed", fill="#4a7fd6", anchor="ne", font=font(8))
        self.lab_nozzle_lim.config(text=f"Nozzle (max {self.p.nozzle_limit()})")
        self.lab_bed_lim.config(text=f"Bed (max {self.p.bed_limit()})")

    # ----- Level -----
    def _tab_level(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Level")
        self.level_tab_index = nb.index("end") - 1
        lf = ttk.LabelFrame(f, text="Bed mesh", padding=8)
        lf.grid(row=0, column=0, sticky="nw")
        ttk.Button(lf, text="Level now (homes, probes the grid, saves)", command=self._level).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Label(lf, text="Heat the bed to printing temperature first; a cold mesh is off by a tenth or two.", wraplength=420).grid(row=1, column=0, sticky="w")
        self.mesh_frame = ttk.Frame(lf)
        self.mesh_frame.grid(row=2, column=0, pady=8)
        self.mesh_cells = []
        self.v_meshstats = tk.StringVar()
        ttk.Label(lf, textvariable=self.v_meshstats, justify="left").grid(row=3, column=0, sticky="w")
        ttk.Label(lf, text="Front of the plate at the bottom, head's left on the left. mm, + is high.", foreground="#666").grid(row=4, column=0, sticky="w")

        zf = ttk.LabelFrame(f, text="Z offset", padding=8)
        zf.grid(row=0, column=1, sticky="nw", padx=16)
        ttk.Label(zf, text="More negative = nozzle closer to the plate.", wraplength=360).grid(row=0, column=0, columnspan=4, sticky="w")
        step = self.prefs["zoffset_step"]
        ttk.Button(zf, text="closer", command=lambda: self._zoff_nudge(-step)).grid(row=1, column=0)
        self.zoff_entry = ttk.Entry(zf, textvariable=self.v_zoff, width=8, justify="center")
        self.zoff_entry.grid(row=1, column=1, padx=4, pady=6)
        ttk.Button(zf, text="further", command=lambda: self._zoff_nudge(+step)).grid(row=1, column=2)
        ttk.Button(zf, text="Apply and save", command=lambda: self.run("zoffset", {"value": self.v_zoff.get()})).grid(row=1, column=3, padx=8)
        ttk.Label(zf, text=f"The buttons step {step:g} mm. Between prints they write the offset; during a print they nudge live.", wraplength=360, foreground="#666").grid(row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(zf, textvariable=self.v_babysteps, foreground="#c77700").grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Button(zf, text="Save nudges", command=self._save_nudges).grid(row=3, column=3, padx=8, pady=4)
        ttk.Button(zf, text="Auto Z offset (one-key: nozzle presses the plate)",
                   command=lambda: self.run("auto_zoffset", confirm="Same step the screen's Level runs first: the nozzle is pressed onto the plate to measure the offset. The nozzle tip must be clean. Continue?")).grid(row=4, column=0, columnspan=4, sticky="w", pady=6)

        sf = ttk.LabelFrame(f, text="Switches and probe", padding=8)
        sf.grid(row=1, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Button(sf, text="Read switches now", command=lambda: self.run("endstops")).grid(row=0, column=0, padx=4)
        ttk.Button(sf, text="Switch test (30 s live)", command=self._switch_test).grid(row=0, column=1, padx=4)
        ttk.Label(sf, textvariable=self.v_switchtest, foreground="#1f6fb0").grid(row=0, column=2, columnspan=3, padx=8, sticky="w")
        for i, (lbl, what) in enumerate((("Probe pin down", "deploy"), ("Probe pin up", "stow"),
                                         ("Probe self-test", "selftest"), ("Probe reset", "reset"))):
            ttk.Button(sf, text=lbl, command=lambda w=what: self.run("probe", {"what": w})).grid(row=1, column=i, padx=4, pady=4)
        ttk.Button(sf, text="Probe repeatability test", command=lambda: self.run("probe_repeat", {"count": self.probe_n.get()})).grid(row=1, column=4, padx=(16, 4))
        self.probe_n = ttk.Spinbox(sf, from_=3, to=20, width=4)
        self.probe_n.set(self.prefs["probe_repeat_n"])
        self.probe_n.grid(row=1, column=5)
        ttk.Label(sf, text="touches").grid(row=1, column=6)
        rf = ttk.LabelFrame(f, text="Last report", padding=8)
        rf.grid(row=2, column=0, columnspan=2, sticky="we", pady=4)
        self._report_box(rf)

    def _report_box(self, parent, width=96, height=7):
        """The printer's answer to the last probe test or PID tune. Shown on Level and on Tools."""
        if not hasattr(self, "report_boxes"):
            self.report_boxes, self._report_shown = [], None
        title = tk.StringVar(value="nothing yet: run a probe repeatability test or a PID tune")
        ttk.Label(parent, textvariable=title, foreground="#1f6fb0", wraplength=width * 7).pack(anchor="w")
        t = tk.Text(parent, height=height, width=width, font=mono(9), state="disabled", relief="flat", bg="#fafafa", wrap="word")
        t.pack(fill="x")
        self.report_boxes.append((title, t))

    def _refresh_report(self):
        st = self.p.state
        key = (st["report_title"], len(st["report"]), st["report"][-1] if st["report"] else "")
        if key == self._report_shown:
            return
        self._report_shown = key
        for title, t in self.report_boxes:
            title.set(st["report_title"] or "nothing yet: run a probe repeatability test or a PID tune")
            t.config(state="normal")
            t.delete("1.0", "end")
            t.insert("1.0", "\n".join(st["report"]) or "(waiting for the printer's answer)" if st["report_title"] else "")
            t.see("end")
            t.config(state="disabled")

    def _zoff_nudge(self, d):
        if self.p.is_printing() or self.p.state["task"].startswith("nozzle at Z 0"):
            self.run("babystep", {"dist": d})
            return
        try:
            v = float(self.v_zoff.get()) + d
        except ValueError:
            return
        self.v_zoff.set(f"{v:.2f}")
        self.run("zoffset", {"value": v})

    def _save_nudges(self):
        if self.p.state["task"].startswith("nozzle at Z 0"):
            self.run("zcheck_finish")
        else:
            self.run("save_settings")

    def _level(self):
        bt = self.p.state["bed_target"] or 0
        bed = self.p.state["bed"] or 0
        msg = "Probe the whole plate and save the mesh. Takes a few minutes."
        if bt < self.prefs["level_min_bed_c"] or bed < bt - 5:
            msg = f"Bed is at {bed:.0f} °C (target {bt:.0f}). Level anyway with a cold bed?"
        self.run("level", confirm=msg)

    def _switch_test(self):
        self._switch_test_until = time.time() + 30
        self.v_switchtest.set("press each switch by hand; states update live for 30 s")

    def _refresh_mesh(self):
        mesh = self.p.state["mesh"]
        if not mesh:
            return
        ny, nx = len(mesh), len(mesh[0])
        if len(self.mesh_cells) != ny * nx:
            for w in self.mesh_frame.winfo_children():
                w.destroy()
            self.mesh_cells = []
            for j in range(ny):
                for i in range(nx):
                    lab = tk.Label(self.mesh_frame, width=8, relief="ridge", font=mono(10))
                    lab.grid(row=ny - 1 - j, column=i, padx=1, pady=1)
                    self.mesh_cells.append((j, i, lab))
        vals = [v for row in mesh for v in row if v is not None]
        lo, hi = (min(vals), max(vals)) if vals else (0, 0)
        for j, i, lab in self.mesh_cells:
            v = mesh[j][i]
            if v is None:
                lab.config(text="", bg="#ddd")
                continue
            k = 0.5 if hi == lo else (v - lo) / (hi - lo)
            r, b = int(255 * k), int(255 * (1 - k))
            g = int(120 + 60 * (1 - abs(k - 0.5) * 2))
            lab.config(text=f"{v:+.2f}", bg=f"#{r:02x}{g:02x}{b:02x}", fg="white")
        if vals:
            left = sum(row[0] for row in mesh) / ny
            right = sum(row[-1] for row in mesh) / ny
            front = sum(mesh[0]) / nx
            back = sum(mesh[-1]) / nx
            verdict = "flat enough" if hi - lo < 0.3 else ("usable, the mesh compensates" if hi - lo < 0.6 else "large: check the gantry is level on its two Z screws")
            self.v_meshstats.set(f"range {hi - lo:.2f} mm ({lo:+.2f} to {hi:+.2f})   left→right {right - left:+.2f}   front→back {back - front:+.2f}   {verdict}")

    # ----- Print -----
    def _tab_print(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Print")
        hf = ttk.LabelFrame(f, text="Print from this computer", padding=8)
        hf.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 8))
        ttk.Button(hf, text="Choose gcode and print...", command=self._host_print).grid(row=0, column=0, padx=4, sticky="w")
        self.host_bar = ttk.Progressbar(hf, length=420, maximum=100)
        self.host_bar.grid(row=0, column=1, padx=8)
        self.v_host = tk.StringVar(value="no print from this computer")
        ttk.Label(hf, textvariable=self.v_host).grid(row=0, column=2, padx=4, sticky="w")
        self.v_host_note = tk.StringVar(value="")
        ttk.Label(hf, textvariable=self.v_host_note, foreground="#c77700", wraplength=900).grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(hf, text="Sends the file over the USB cable line by line; nothing is copied to the card, so it starts at once. "
                           "Keep this window open and the computer on until it ends: the panel stops the computer sleeping, "
                           "but closing the window or pulling the cable stops the print.",
                  foreground="#666", wraplength=900).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        cf = ttk.LabelFrame(f, text="Running print", padding=8)
        cf.grid(row=1, column=1, sticky="nw", padx=10)
        ttk.Button(cf, text="Pause", command=lambda: self.run("pause")).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Button(cf, text="Resume", command=lambda: self.run("resume")).grid(row=1, column=0, sticky="w", pady=2)
        ttk.Button(cf, text="Cancel print (and cool down)", command=lambda: self.run("cancel", confirm="Stop the running print?")).grid(row=2, column=0, sticky="w", pady=2)
        ttk.Button(cf, text="Change filament (M600)", command=lambda: self.run("filament_change", confirm="Park the head and unload for a filament change?")).grid(row=3, column=0, sticky="w", pady=2)
        ttk.Label(cf, text="These work on whichever print runs: from this computer, from the card, or started on the printer's screen.",
                  foreground="#666", wraplength=260).grid(row=4, column=0, sticky="w", pady=(6, 0))

        sf = ttk.LabelFrame(f, text="Print from the card", padding=8)
        sf.grid(row=1, column=0, sticky="nw")
        self.sd_list = ttk.Treeview(sf, columns=("size",), show="tree headings", height=11)
        self.sd_list.heading("#0", text="File on the card")
        self.sd_list.heading("size", text="Size")
        self.sd_list.column("#0", width=300)
        self.sd_list.column("size", width=90, anchor="e")
        self.sd_list.grid(row=0, column=0, rowspan=4, sticky="nw")
        ttk.Button(sf, text="Refresh file list", command=lambda: self.run("sd_list", then=self._fill_sd)).grid(row=0, column=1, sticky="nw", padx=10)
        ttk.Button(sf, text="Print selected", command=self._sd_print).grid(row=1, column=1, sticky="nw", padx=10)
        ttk.Button(sf, text="Delete selected", command=self._sd_delete).grid(row=2, column=1, sticky="nw", padx=10)
        ttk.Label(f, text="Fan, speed and flow (Heat tab) and Z nudges (Level tab) work during any print. For a card print, load the file on the Plate tab to see layer numbers in the progress.",
                  wraplength=900).grid(row=7, column=0, columnspan=2, sticky="w", pady=8)
        uf = ttk.LabelFrame(f, text="Upload gcode to the card in the printer", padding=8)
        uf.grid(row=8, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(uf, text="Choose gcode and upload...", command=self._sd_upload).grid(row=0, column=0, padx=4)
        self.v_upload = tk.StringVar(value="")
        self.upload_bar = ttk.Progressbar(uf, length=320, maximum=100)
        self.upload_bar.grid(row=0, column=1, padx=8)
        ttk.Label(uf, textvariable=self.v_upload).grid(row=0, column=2, padx=4)
        ttk.Label(uf, text="Not while printing. About 5 minutes per 2 MB; the printer checks every line.", foreground="#666").grid(row=1, column=0, columnspan=3, sticky="w")

    def _fill_sd(self, files):
        self.sd_list.delete(*self.sd_list.get_children())
        sizes = self.p.state["sd_sizes"]
        for fn in files:
            sz = sizes.get(fn.upper())
            self.sd_list.insert("", "end", text=fn, values=(f"{sz / 1024:.0f} KB" if sz else "",))

    def _host_print(self):
        if not self.p.state["connected"]:
            messagebox.showwarning("Not connected", "Connect the printer first.")
            return
        path = filedialog.askopenfilename(title="Gcode to print from this computer", filetypes=[("gcode", "*.gcode *.gco *.g"), ("all", "*.*")])
        if not path:
            return
        msg = (f"Print {os.path.basename(path)} from this computer?\n\n"
               "The file goes to the printer line by line over the USB cable. Keep this window open and the "
               "computer on until the print ends. The panel stops the computer going to sleep while it prints.")
        if not messagebox.askyesno("Print from this computer", msg):
            return
        try:
            self.plate.load_path(path)            # the Plate tab follows the print
        except OSError:
            pass
        self.run("host_print", {"path": path})

    def _refresh_host(self):
        h = self.p.state["host"]
        if not h:
            return
        pct, elapsed, left = self._host_numbers(h)
        self.host_bar["value"] = pct
        layer = f", layer {max(1, h['layer'])} / {h['layers']}" if h["layers"] else ""
        if self.p.host_active():
            word = {"starting": "starting", "pausing": "pausing", "paused": "PAUSED", "resuming": "resuming"}.get(h["state"], "printing")
            self.v_host.set(f"{h['file']}: {word}, {pct:.0f}%{layer}, {self._dur(elapsed)} so far, {self._dur(left)} left")
        else:
            word = {"done": "finished", "cancelled": "cancelled", "failed": "FAILED"}.get(h["state"], h["state"])
            self.v_host.set(f"{h['file']}: {word} after {self._dur(elapsed)} ({h['sent']} / {h['total']} lines)")
        note = h["note"] if self.p.host_active() else h["error"]
        if h["resends"] and self.p.host_active():
            note = (note + "   " if note else "") + f"{h['resends']} lines resent after a transmission error"
        self.v_host_note.set(note)

    def _print_ended(self, fin):
        """Sound, a message window that does not block the panel, and a desktop notification (Linux)."""
        if not fin or not self.prefs["alert_when_done"]:
            return
        if fin["how"] == "cancelled":
            return                                  # the person who cancelled already knows
        where = "from this computer" if fin["kind"] == "host" else "from the card"
        took = f" in {self._dur(fin['elapsed'])}" if fin["elapsed"] else ""
        if fin["how"] == "done":
            title, text = "Print finished", f"{fin['file']} finished{took} ({where})."
        else:
            title, text = "Print stopped", f"{fin['file']} stopped ({where}): {fin['detail'] or fin['how']}"
        desktop.alert(self, title, text)
        w = tk.Toplevel(self)
        w.title(title)
        w.attributes("-topmost", True)
        w.resizable(False, False)
        ttk.Label(w, text=text, wraplength=420, padding=16, font=font(11)).pack()
        ttk.Button(w, text="OK", command=w.destroy).pack(pady=(0, 12))
        w.after(100, w.lift)
        self.status_msg.set(f"{title}: {text}")

    def _reconnect(self):
        if self.p.host_active():
            messagebox.showwarning("Printing", "A print is running from this computer; reconnecting would stop it.")
            return

        def again():
            self.p.disconnect()                     # our own open port would otherwise read as "in use"
            self.p.connect()
        threading.Thread(target=again, daemon=True).start()

    def _sd_selected(self):
        sel = self.sd_list.focus()
        return self.sd_list.item(sel, "text") if sel else None

    def _sd_print(self):
        fn = self._sd_selected()
        if fn:
            self.run("sd_print", {"file": fn}, confirm=f"Start printing {fn}?")

    def _sd_delete(self):
        fn = self._sd_selected()
        if fn:
            self.run("sd_delete", {"file": fn}, confirm=f"Delete {fn} from the card?", then=lambda r: self.run("sd_list", then=self._fill_sd))

    def _sd_upload(self):
        path = filedialog.askopenfilename(title="Gcode to upload", filetypes=[("gcode", "*.gcode *.gco *.g"), ("all", "*.*")])
        if not path:
            return
        default = self.p.sd_name(path)
        name = simpledialog.askstring("Name on the card", "8 letters or digits, then .GCO:", initialvalue=default, parent=self)
        if not name:
            return
        name = name.strip().upper()
        if name in [x.upper() for x in self.p.state["sd_files"]] and not messagebox.askyesno("Overwrite", f"{name} is already on the card. Overwrite it?"):
            return
        self.run("sd_upload", {"path": path, "name": name}, then=lambda r: self.run("sd_list", then=self._fill_sd))

    def _refresh_upload(self):
        up = self.p.state.get("upload")
        if not up:
            return
        pct = 100.0 * up["sent"] / up["total"] if up["total"] else 0
        self.upload_bar["value"] = pct
        if up["error"]:
            self.v_upload.set(f"{up['file']}: FAILED, {up['error']}")
        elif up["done"]:
            self.v_upload.set(f"{up['file']}: done, {up['sent']} lines")
        else:
            self.v_upload.set(f"{up['file']}: {up['sent']} / {up['total']} lines ({pct:.0f}%)")

    # ----- Plate -----
    def _tab_plate(self, nb):
        self.plate = PlateView(nb, padding=6)
        nb.add(self.plate, text="Plate")
        self.plate_tab_index = nb.index("end") - 1

    # ----- Stored settings -----
    def _tab_settings(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Stored settings")
        self.tree = ttk.Treeview(f, columns=("value",), show="tree headings", height=26)
        self.tree.heading("#0", text="Setting")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=440)
        self.tree.column("value", width=140)
        self.tree.grid(row=0, column=0, rowspan=8, sticky="nw")
        self.tree.bind("<Double-1>", self._edit_setting)
        ttk.Label(f, text="Double-click a value to change it. Changes are saved to the printer at once.", wraplength=320).grid(row=0, column=1, sticky="nw", padx=10)
        ttk.Button(f, text="Re-read from printer", command=lambda: self.run("reload")).grid(row=1, column=1, sticky="w", padx=10, pady=2)
        ttk.Button(f, text="Backup to file...", command=self._backup).grid(row=2, column=1, sticky="w", padx=10, pady=2)
        ttk.Button(f, text="Restore from file...", command=self._restore).grid(row=3, column=1, sticky="w", padx=10, pady=2)
        ttk.Button(f, text="Restore firmware defaults",
                   command=lambda: self.run("defaults", confirm="Reset EVERY stored setting to the firmware defaults: Z offset becomes 0 (nozzle higher), mesh cleared, PID and speeds reset. You will need to level and set the offset again. Continue?")).grid(row=4, column=1, sticky="w", padx=10, pady=(16, 2))
        self._tree_rows = {}
        for g, k, label, editable in SETTING_ROWS:
            iid = self.tree.insert("", "end", text=label, values=("",))
            self._tree_rows[iid] = (g, k, editable)
        for i, name in enumerate(("Preheat preset 1 (PLA on screen)", "Preheat preset 2 (ABS on screen)")):
            iid = self.tree.insert("", "end", text=name + ", nozzle / bed", values=("",))
            self._tree_rows[iid] = ("M145", i, 0)

    def _backup(self):
        path = filedialog.asksaveasfilename(title="Save printer settings", defaultextension=".txt",
                                            initialfile=time.strftime("v3se-settings-%Y%m%d.txt"), filetypes=[("text", "*.txt")])
        if path:
            self.run("backup", {"path": path})

    def _restore(self):
        path = filedialog.askopenfilename(title="Settings backup to restore", filetypes=[("text", "*.txt"), ("all", "*.*")])
        if path:
            self.run("restore", {"path": path}, confirm=f"Send every setting in {os.path.basename(path)} to the printer and save?")

    def _refresh_settings(self):
        s = self.p.state["settings"]
        if not s:
            return
        for iid, (g, k, _) in self._tree_rows.items():
            if g == "M145":
                lst = s.get("M145", [])
                if isinstance(k, int) and k < len(lst):
                    self.tree.set(iid, "value", f"{lst[k].get('H', 0):.0f} / {lst[k].get('B', 0):.0f}")
                continue
            v = s.get(g, {}).get(k)
            self.tree.set(iid, "value", "" if v is None else (f"{v:g}" if isinstance(v, float) else str(v)))

    def _edit_setting(self, _ev):
        iid = self.tree.focus()
        if iid not in self._tree_rows:
            return
        g, k, editable = self._tree_rows[iid]
        if not editable:
            return
        cur = self.tree.set(iid, "value")
        new = simpledialog.askstring("Change setting", f"{self.tree.item(iid, 'text')}\n{g} {k}  current {cur}\nNew value:", parent=self)
        if new is None:
            return
        try:
            float(new)
        except ValueError:
            messagebox.showwarning("Not a number", new)
            return
        self.run("set", {"gcode": g, "params": {k: new}})

    # ----- Tools -----
    def _tab_tools(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Tools")
        self._tool_fields = []                  # (entry, gcode, letter, index in a list setting or None)
        pf = ttk.LabelFrame(f, text="PID tuning (heats, cycles 8 times, saves; several minutes)", padding=8)
        pf.grid(row=0, column=0, sticky="nw")
        self.pid_nz = ttk.Combobox(pf, width=5, state="readonly")
        self.pid_bd = ttk.Combobox(pf, width=5, state="readonly")
        self._fill_pid_choices()
        ttk.Button(pf, text="Tune nozzle", command=lambda: self.run("pid_nozzle", {"temp": self.pid_nz.get()}, confirm=f"Tune the nozzle heater at {self.pid_nz.get()} °C? About 3 minutes. Tune with the part fan as it prints.")).grid(row=0, column=0, padx=4)
        ttk.Label(pf, text="at").grid(row=0, column=1)
        self.pid_nz.grid(row=0, column=2)
        ttk.Label(pf, text="°C").grid(row=0, column=3, padx=(2, 16))
        ttk.Button(pf, text="Tune bed", command=lambda: self.run("pid_bed", {"temp": self.pid_bd.get()}, confirm=f"Tune the bed heater at {self.pid_bd.get()} °C? About 10 minutes.")).grid(row=0, column=4, padx=4)
        ttk.Label(pf, text="at").grid(row=0, column=5)
        self.pid_bd.grid(row=0, column=6)
        ttk.Label(pf, text="°C").grid(row=0, column=7, padx=2)

        mf = ttk.LabelFrame(f, text="Motion features (saved on Apply)", padding=8)
        mf.grid(row=1, column=0, sticky="nw", pady=8)
        ttk.Label(mf, text="The boxes show what the printer has now.", foreground="#666").grid(row=0, column=0, columnspan=5, sticky="w")
        ttk.Label(mf, text="Input shaping X: frequency / damping").grid(row=1, column=0, sticky="w")
        self.is_x, self.is_xd = self._tool_entry(mf, 1, 1, "M593", "F", "X"), self._tool_entry(mf, 1, 2, "M593", "D", "X")
        ttk.Button(mf, text="Apply X", command=lambda: self.run("set", {"gcode": "M593", "params": {"X": 1, "F": self.is_x.get(), "D": self.is_xd.get()}})).grid(row=1, column=3, padx=4)
        ttk.Label(mf, text="Input shaping Y: frequency / damping").grid(row=2, column=0, sticky="w")
        self.is_y, self.is_yd = self._tool_entry(mf, 2, 1, "M593", "F", "Y"), self._tool_entry(mf, 2, 2, "M593", "D", "Y")
        ttk.Button(mf, text="Apply Y", command=lambda: self.run("set", {"gcode": "M593", "params": {"Y": 1, "F": self.is_y.get(), "D": self.is_yd.get()}})).grid(row=2, column=3, padx=4)
        ttk.Button(mf, text="Shaping off", command=lambda: self.run("set", {"gcode": "M593", "params": {"F": 0}}, confirm="Switch input shaping off on both axes?")).grid(row=1, column=4, rowspan=2, padx=8)
        ttk.Label(mf, text="Linear advance K").grid(row=3, column=0, sticky="w")
        self.la_k = self._tool_entry(mf, 3, 1, "M900", "K", None)
        ttk.Button(mf, text="Apply", command=lambda: self.run("set", {"gcode": "M900", "params": {"K": self.la_k.get()}})).grid(row=3, column=3, padx=4)
        ttk.Button(mf, text="Linear advance off", command=lambda: self.run("set", {"gcode": "M900", "params": {"K": 0}})).grid(row=3, column=4, padx=8)

        sf = ttk.LabelFrame(f, text="Sensors and screen", padding=8)
        sf.grid(row=2, column=0, sticky="nw", pady=8)
        self._switches = []
        swf = ttk.Frame(sf)
        swf.grid(row=0, column=0, columnspan=3, sticky="w")
        for i, (label, g) in enumerate((("Filament runout sensor", "M412"), ("Power-loss recovery", "M413"),
                                        ("Bed levelling (mesh compensation)", "M420"))):
            var = tk.IntVar(value=0)
            cb = ttk.Checkbutton(swf, text=label, variable=var, command=lambda g=g, v=var: self.run("set", {"gcode": g, "params": {"S": v.get()}}))
            cb.grid(row=0, column=i, padx=(0, 18), sticky="w")
            self._switches.append((cb, var, g))
        ttk.Label(sf, text="Screen brightness").grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.v_bright = tk.IntVar(value=255)
        br = ttk.Scale(sf, from_=10, to=255, orient="horizontal", length=260, variable=self.v_bright,
                       command=lambda v: self.v_bright.set(int(float(v))))
        br.grid(row=1, column=1, sticky="w", pady=(10, 0))
        br.bind("<ButtonRelease-1>", lambda e: self.run("set", {"gcode": "M256", "params": {"B": self.v_bright.get()}}))
        ttk.Label(sf, textvariable=self.v_bright, width=4).grid(row=1, column=2, sticky="w", pady=(10, 0))
        ttk.Button(sf, text="Beep", command=lambda: self.run("beep")).grid(row=2, column=0, sticky="w", pady=(10, 0))
        ttk.Label(sf, text="Brightness takes effect when you let go of the slider (M256; a firmware without it answers 'Unknown command' in the Console).",
                  foreground="#666", wraplength=640).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))

        rf = ttk.LabelFrame(f, text="Last report", padding=8)
        rf.grid(row=0, column=1, rowspan=3, sticky="nw", padx=16)
        self._report_box(rf, width=58, height=16)
        ttk.Label(f, text="Not offered: emergency stop. M112 is removed in the community firmware; use the power switch.", foreground="#a00").grid(row=3, column=0, columnspan=2, sticky="w", pady=10)

    def _tool_entry(self, parent, row, col, g, letter, axis):
        e = ttk.Entry(parent, width=7)
        e.grid(row=row, column=col, padx=2)
        self._tool_fields.append((e, g, letter, axis))
        return e

    def _fill_pid_choices(self):
        """Readonly dropdowns: the material presets' temperatures plus round numbers, within the limits."""
        noz = {int(pr["nozzle"]) for pr in self.prefs["presets"].values()} | set(range(200, 290, 10)) | {int(self.prefs["pid_nozzle_c"])}
        bed = {int(pr["bed"]) for pr in self.prefs["presets"].values()} | set(range(50, 111, 10)) | {int(self.prefs["pid_bed_c"])}
        self.pid_nz["values"] = [str(t) for t in sorted(noz) if t <= self.p.nozzle_limit()]
        self.pid_bd["values"] = [str(t) for t in sorted(bed) if t <= self.p.bed_limit()]
        for box, want in ((self.pid_nz, self.prefs["pid_nozzle_c"]), (self.pid_bd, self.prefs["pid_bed_c"])):
            vals = list(box["values"])
            box.set(str(int(want)) if str(int(want)) in vals else (vals[-1] if vals else ""))

    def _refresh_tools(self):
        """Put the printer's current values into the Tools boxes and switches, unless being edited."""
        s = self.p.state["settings"]
        if not s:
            return
        limits = (self.p.nozzle_limit(), self.p.bed_limit())
        if limits != getattr(self, "_pid_limits", None):
            self._pid_limits = limits
            self._fill_pid_choices()
        focus = self.focus_get()
        for e, g, letter, axis in self._tool_fields:
            if e is focus:
                continue
            v = s.get(g)
            if isinstance(v, list):             # M593 comes as one line per axis: "M593 X F.. D..", "M593 Y F.. D.."
                v = next((d for d in v if axis in d), v[0] if v else None)
            val = v.get(letter) if isinstance(v, dict) else None
            txt = "" if val is None else (f"{val:g}" if isinstance(val, float) else str(val))
            if getattr(e, "_last", None) != txt:     # only overwrite when the printer's value changed
                e.delete(0, "end")
                e.insert(0, txt)
                e._last = txt
        for cb, var, g in self._switches:
            val = (s.get(g) or {}).get("S") if isinstance(s.get(g), dict) else None
            if val is None:
                cb.state(["alternate"])               # the printer did not report it
            else:
                cb.state(["!alternate"])
                var.set(1 if float(val) else 0)

    # ----- Preferences -----
    def _tab_prefs(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Preferences")
        self.v_tips = tk.BooleanVar(value=bool(self.prefs["tooltips"]))
        ttk.Checkbutton(f, text="Show hints on hover", variable=self.v_tips, command=self._toggle_tips).grid(row=0, column=0, columnspan=2, sticky="w")

        cf = ttk.LabelFrame(f, text="Connection", padding=8)
        cf.grid(row=1, column=0, sticky="w", pady=8)
        ttk.Label(cf, text="Port").grid(row=0, column=0)
        self.port_box = ttk.Combobox(cf, width=34)
        self.port_box.grid(row=0, column=1, padx=4)
        ttk.Button(cf, text="Rescan", command=self._fill_ports).grid(row=0, column=2, padx=4)
        ttk.Label(cf, text="Speed").grid(row=0, column=3, padx=(12, 0))
        self.baud_box = ttk.Combobox(cf, width=10, values=["auto", "115200", "150000", "250000"])
        self.baud_box.set(str(self.prefs["baud"]) if self.prefs["baud"] else "auto")
        self.baud_box.grid(row=0, column=4, padx=4)
        ttk.Button(cf, text="Connect", command=self._connect_from_prefs).grid(row=0, column=5, padx=8)
        self._fill_ports()

        nf = ttk.LabelFrame(f, text="Numbers", padding=8)
        nf.grid(row=2, column=0, sticky="w", pady=8)
        self.pref_fields = {}
        rows = [("steps_mm", "Jog steps (mm, comma separated)", 28), ("feed_xy", "Jog speed head/bed (mm/min)", 8),
                ("feed_z", "Jog speed gantry (mm/min)", 8), ("feed_e", "Extrude speed (mm/min)", 8),
                ("extrude_mm", "Default extrude length (mm)", 8), ("extrude_min_c", "Cold-extrusion limit (°C)", 8),
                ("nozzle_max", "Nozzle limit offered (°C, firmware may cap lower)", 8), ("bed_max", "Bed limit offered (°C)", 8),
                ("pid_nozzle_c", "PID tune temperature, nozzle", 8), ("pid_bed_c", "PID tune temperature, bed", 8),
                ("probe_repeat_n", "Probe repeatability touches", 8), ("zoffset_step", "Z offset button step (mm)", 8),
                ("level_min_bed_c", "Warn when levelling with the bed below (°C)", 8)]
        for i, (key, label, width) in enumerate(rows):
            ttk.Label(nf, text=label).grid(row=i, column=0, sticky="w", pady=1)
            e = ttk.Entry(nf, width=width)
            v = self.prefs[key]
            e.insert(0, ", ".join(f"{x:g}" for x in v) if isinstance(v, list) else f"{v:g}" if isinstance(v, float) else str(v))
            e.grid(row=i, column=1, sticky="w", padx=8)
            self.pref_fields[key] = e
        self.v_logfile = tk.BooleanVar(value=bool(self.prefs["log_to_file"]))
        logname = os.path.join("logs", "session-<date>.log")
        ttk.Checkbutton(nf, text=f"Write a session log ({logname}: actions, errors, temperatures)", variable=self.v_logfile).grid(row=len(rows), column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.v_alert = tk.BooleanVar(value=bool(self.prefs["alert_when_done"]))
        ttk.Checkbutton(nf, text="Alert when a print ends (sound and a message)", variable=self.v_alert).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w")

        pf = ttk.LabelFrame(f, text="Material presets", padding=8)
        pf.grid(row=1, column=1, rowspan=2, sticky="nw", padx=16, pady=8)
        self.pref_preset_list = ttk.Treeview(pf, columns=("nozzle", "bed"), show="tree headings", height=8)
        self.pref_preset_list.heading("#0", text="Material")
        self.pref_preset_list.heading("nozzle", text="Nozzle")
        self.pref_preset_list.heading("bed", text="Bed")
        self.pref_preset_list.column("#0", width=120)
        self.pref_preset_list.column("nozzle", width=70, anchor="e")
        self.pref_preset_list.column("bed", width=70, anchor="e")
        self.pref_preset_list.grid(row=0, column=0, columnspan=4)
        self.pref_preset_list.bind("<<TreeviewSelect>>", self._pick_pref_preset)
        ttk.Label(pf, text="Name").grid(row=1, column=0, pady=(6, 0))
        self.pp_name = ttk.Entry(pf, width=10)
        self.pp_name.grid(row=1, column=1, pady=(6, 0))
        ttk.Label(pf, text="Nozzle").grid(row=2, column=0)
        self.pp_nozzle = ttk.Entry(pf, width=6)
        self.pp_nozzle.grid(row=2, column=1, sticky="w")
        ttk.Label(pf, text="Bed").grid(row=3, column=0)
        self.pp_bed = ttk.Entry(pf, width=6)
        self.pp_bed.grid(row=3, column=1, sticky="w")
        ttk.Button(pf, text="Add / update preset", command=self._pref_preset_add).grid(row=4, column=0, columnspan=2, pady=6, sticky="w")
        ttk.Button(pf, text="Remove preset", command=self._pref_preset_remove).grid(row=4, column=2, columnspan=2, pady=6, sticky="w")
        self._fill_pref_presets()

        bf = ttk.Frame(f)
        bf.grid(row=3, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Button(bf, text="Save preferences", command=self._save_prefs).grid(row=0, column=0, padx=4)
        ttk.Button(bf, text="Reset to defaults", command=self._reset_prefs).grid(row=0, column=1, padx=4)
        ttk.Label(bf, text=f"Stored in {self.prefs.path}", foreground="#666").grid(row=0, column=2, padx=12)

    def _toggle_tips(self):
        Tooltip.set_enabled(self.v_tips.get())
        self.prefs["tooltips"] = bool(self.v_tips.get())
        self.prefs.save()

    def _fill_ports(self):
        ports = list_serial_ports()
        values = ["auto"] + [f"{d}  {desc}" for d, desc in ports]
        self.port_box["values"] = values
        cur = self.prefs["port"]
        self.port_box.set(next((v for v in values if v.startswith(cur + " ")), "auto") if cur else "auto")

    def _connect_from_prefs(self):
        if self.p.host_active():
            messagebox.showwarning("Printing", "A print is running from this computer; reconnecting would stop it.")
            return
        sel = self.port_box.get().strip()
        port = "" if sel in ("", "auto") else sel.split()[0]
        baud = self.baud_box.get().strip()
        baud = 0 if baud in ("", "auto") else int(baud)
        self.prefs["port"], self.prefs["baud"] = port, baud
        self.prefs.save()
        self.p.disconnect()
        threading.Thread(target=lambda: self.p.connect(port or "auto", baud or None), daemon=True).start()

    def _fill_pref_presets(self):
        self.pref_preset_list.delete(*self.pref_preset_list.get_children())
        for name, pr in self.prefs["presets"].items():
            self.pref_preset_list.insert("", "end", text=name, values=(pr["nozzle"], pr["bed"]))

    def _pick_pref_preset(self, _e):
        iid = self.pref_preset_list.focus()
        if not iid:
            return
        name = self.pref_preset_list.item(iid, "text")
        pr = self.prefs["presets"].get(name, {})
        for e, v in ((self.pp_name, name), (self.pp_nozzle, pr.get("nozzle", "")), (self.pp_bed, pr.get("bed", ""))):
            e.delete(0, "end")
            e.insert(0, str(v))

    def _pref_preset_add(self):
        name = self.pp_name.get().strip()
        try:
            nz, bd = int(float(self.pp_nozzle.get())), int(float(self.pp_bed.get()))
        except ValueError:
            messagebox.showwarning("Preset", "Nozzle and bed must be numbers.")
            return
        if not name:
            return
        self.prefs["presets"][name] = {"nozzle": nz, "bed": bd}
        self.prefs.save()
        self._build_presets()

    def _pref_preset_remove(self):
        iid = self.pref_preset_list.focus()
        if not iid:
            return
        name = self.pref_preset_list.item(iid, "text")
        if name in self.prefs["presets"] and messagebox.askyesno("Remove", f"Remove the {name} preset?"):
            del self.prefs["presets"][name]
            self.prefs.save()
            self._build_presets()

    def _save_prefs(self):
        try:
            for key, e in self.pref_fields.items():
                txt = e.get().strip()
                if key == "steps_mm":
                    vals = sorted({abs(float(x)) for x in txt.replace(";", ",").split(",") if x.strip()})
                    if not vals:
                        raise ValueError("steps")
                    self.prefs[key] = vals
                elif key == "zoffset_step":
                    self.prefs[key] = abs(float(txt))
                else:
                    self.prefs[key] = int(float(txt))
        except ValueError as e:
            messagebox.showwarning("Preferences", f"Could not read a number: {e}")
            return
        self.prefs["log_to_file"] = bool(self.v_logfile.get())
        self.prefs["alert_when_done"] = bool(self.v_alert.get())
        self.prefs.save()
        self._build_steps()
        self._build_presets()
        self.e_extrude.set(self.prefs["extrude_mm"])
        self._fill_pid_choices()
        self.probe_n.set(self.prefs["probe_repeat_n"])
        self.status_msg.set("Preferences saved.")

    def _reset_prefs(self):
        if not messagebox.askyesno("Reset", "Put every preference back to the shipped values?"):
            return
        self.prefs.reset()
        self.prefs.save()
        for key, e in self.pref_fields.items():
            v = self.prefs[key]
            e.delete(0, "end")
            e.insert(0, ", ".join(f"{x:g}" for x in v) if isinstance(v, list) else f"{v:g}" if isinstance(v, float) else str(v))
        self.v_tips.set(True)
        self.v_logfile.set(bool(self.prefs["log_to_file"]))
        self.v_alert.set(bool(self.prefs["alert_when_done"]))
        self._toggle_tips()
        self._build_steps()
        self._build_presets()

    # ----- Console -----
    def _tab_console(self, nb):
        f = ttk.Frame(nb, padding=6)
        nb.add(f, text="Console")
        self.log_text = tk.Text(f, height=30, width=130, font=mono(9), state="disabled")
        self.log_text.pack(fill="both", expand=True)
        row = ttk.Frame(f)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Gcode:").pack(side="left")
        self.gcode_entry = ttk.Combobox(row, width=60, values=["M503  (print all stored settings)", "M119  (switch states)", "M115  (firmware)",
                                                                "M114  (position)", "M105  (temperatures)", "M420 V  (show the mesh)", "M48 P5 V2  (probe repeatability)",
                                                                "M20  (card files)", "M27  (print progress)"])
        self.gcode_entry.pack(side="left", padx=6)
        self.gcode_entry.bind("<Return>", lambda e: self._send_raw())
        self.gcode_entry.bind("<Up>", self._hist_prev)
        ttk.Button(row, text="Send", command=self._send_raw).pack(side="left")
        ttk.Label(row, text="Up arrow recalls earlier commands. Text after two spaces is ignored.", foreground="#666").pack(side="left", padx=10)
        self._history = []

    def _hist_prev(self, _e):
        if self._history:
            self.gcode_entry.set(self._history[-1])
            self._history.insert(0, self._history.pop())

    def _send_raw(self):
        g = self.gcode_entry.get().split("  ")[0].strip()
        if g:
            self._history.append(g)
            self.gcode_entry.set("")
            self.run("gcode", {"gcode": g})

    def _refresh_log(self):
        log = list(self.p.log)
        last = log[-1] if log else None
        if len(log) == self._log_len and last is self._last_entry:
            return
        self._log_len, self._last_entry = len(log), last
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        for e in log:
            arrow = {"tx": ">>", "rx": "  ", "sys": "##"}[e["k"]]
            self.log_text.insert("end", f"{e['t']} {arrow} {e['s']}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    # ----- Help -----
    def _tab_help(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Help")
        t = tk.Text(f, wrap="word", font=font(10), padx=12, pady=10, relief="flat", bg="#fafafa")
        t.insert("1.0", GLOSSARY)
        t.config(state="disabled")
        t.pack(fill="both", expand=True)


def main():
    prefs = Prefs()
    p = Printer(prefs)
    threading.Thread(target=p.connect, daemon=True).start()
    App(p).mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
