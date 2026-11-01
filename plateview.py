"""Plate view: the sliced paths of a gcode file, one layer at a time, with the head's
reported position on top. Layer follows the printer's Z unless the slider is moved.
"""
import re
import tkinter as tk
from tkinter import filedialog, ttk

BED = 220
NUM = re.compile(r"([XYZEF])(-?\d*\.?\d+)")


def parse_gcode(path):
    """Return a list of layers: (z, [(x0, y0, x1, y1, extruding), ...]) in file order."""
    x = y = z = 0.0
    e = 0.0
    abs_xyz, abs_e = True, True
    layers = []            # list of [z, segs]
    cur = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            w = line.split()[0].upper()
            if w == "G90":
                abs_xyz = True
                abs_e = True
            elif w == "G91":
                abs_xyz = False
                abs_e = False
            elif w == "M82":
                abs_e = True
            elif w == "M83":
                abs_e = False
            elif w == "G92":
                for k, v in NUM.findall(line.upper()):
                    if k == "E":
                        e = float(v)
                    elif k == "X":
                        x = float(v)
                    elif k == "Y":
                        y = float(v)
                    elif k == "Z":
                        z = float(v)
            elif w in ("G0", "G1", "G2", "G3"):
                nx, ny, nz, ne = x, y, z, e
                for k, v in NUM.findall(line.upper()):
                    v = float(v)
                    if k == "X":
                        nx = v if abs_xyz else x + v
                    elif k == "Y":
                        ny = v if abs_xyz else y + v
                    elif k == "Z":
                        nz = v if abs_xyz else z + v
                    elif k == "E":
                        ne = v if abs_e else e + v
                extruding = ne > e + 1e-6 and (nx != x or ny != y)
                if extruding:
                    if cur is None or abs(cur[0] - nz) > 1e-3:
                        cur = [nz, []]
                        layers.append(cur)
                    cur[1].append((x, y, nx, ny))
                x, y, z, e = nx, ny, nz, ne
    # merge layers that share a z (z-hops split them)
    merged = {}
    order = []
    for zz, segs in layers:
        key = round(zz, 3)
        if key not in merged:
            merged[key] = []
            order.append(key)
        merged[key].extend(segs)
    order.sort()
    return [(k, merged[k]) for k in order]


class PlateView(ttk.Frame):
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self.layers = []
        self.follow = tk.BooleanVar(value=True)
        self.layer_idx = tk.IntVar(value=0)
        self.pos = {}
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Button(top, text="Load gcode...", command=self._load).pack(side="left", padx=4)
        self.v_file = tk.StringVar(value="no file")
        ttk.Label(top, textvariable=self.v_file).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="follow the printer's Z", variable=self.follow).pack(side="left", padx=12)
        self.slider = ttk.Scale(top, from_=0, to=0, orient="horizontal", length=260, variable=self.layer_idx,
                                command=lambda v: (self.follow.set(False), self.layer_idx.set(int(float(v))), self.redraw()))
        self.slider.pack(side="left", padx=6)
        self.v_layer = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.v_layer, width=28).pack(side="left")
        self.s = 2.0
        self.canvas = tk.Canvas(self, width=int(BED * self.s) + 40, height=int(BED * self.s) + 40, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(pady=6)
        self.redraw()

    def _load(self):
        path = filedialog.askopenfilename(title="Gcode", filetypes=[("gcode", "*.gcode *.gco *.g"), ("all", "*.*")])
        if not path:
            return
        self.layers = parse_gcode(path)
        self.v_file.set(f"{path.split('/')[-1]}  ({len(self.layers)} layers)")
        self.slider.configure(to=max(0, len(self.layers) - 1))
        self.layer_idx.set(0)
        self.follow.set(True)
        self.redraw()

    def set_position(self, pos):
        self.pos = pos or {}
        if self.follow.get() and self.layers and "z" in self.pos:
            zc = self.pos["z"]
            idx = 0
            for i, (zl, _) in enumerate(self.layers):
                if zl <= zc + 0.02:
                    idx = i
                else:
                    break
            self.layer_idx.set(idx)
        self.redraw()

    def C(self, x, y):
        # plate: x right, y towards the back = up on screen
        return (20 + x * self.s, 20 + (BED - y) * self.s)

    def redraw(self):
        c = self.canvas
        c.delete("all")
        c.create_rectangle(*self.C(0, BED), *self.C(BED, 0), fill="#2b2b2b", outline="#777")
        for g in range(0, BED + 1, 55):
            c.create_line(*self.C(g, 0), *self.C(g, BED), fill="#3a3a3a")
            c.create_line(*self.C(0, g), *self.C(BED, g), fill="#3a3a3a")
        c.create_text(*self.C(BED / 2, -6), text="front", fill="#aaa", font=("Segoe UI", 8))
        c.create_text(*self.C(-6, BED / 2), text="left", fill="#aaa", font=("Segoe UI", 8), angle=90)
        if self.layers:
            i = min(self.layer_idx.get(), len(self.layers) - 1)
            z, segs = self.layers[i]
            if i > 0:   # previous layer faint, for context
                for x0, y0, x1, y1 in self.layers[i - 1][1][::2]:
                    c.create_line(*self.C(x0, y0), *self.C(x1, y1), fill="#4a4a4a")
            for x0, y0, x1, y1 in segs:
                c.create_line(*self.C(x0, y0), *self.C(x1, y1), fill="#e0a040", width=1)
            self.v_layer.set(f"layer {i + 1} / {len(self.layers)}   z = {z:.2f}")
        if "x" in self.pos and "y" in self.pos:
            px, py = self.C(self.pos["x"], self.pos["y"])
            c.create_oval(px - 5, py - 5, px + 5, py + 5, outline="#ff4040", width=2)
            c.create_line(px - 9, py, px + 9, py, fill="#ff4040")
            c.create_line(px, py - 9, px, py + 9, fill="#ff4040")
