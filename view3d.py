"""Oblique 3D sketch of the Ender-3 V3 SE that follows the reported position.
Frame coordinates in mm: X to the right (head travel), Y towards the back, Z up,
origin at the plate's left-front corner when the bed is at Y = 0 under the nozzle.
The bed slides in Y; the nozzle's Y in the frame is fixed under the gantry.
Layout after Creality's exploded view: base box with the screen at the front right,
two Z uprights at the back carrying the X gantry, head in front of the gantry.
"""
import tkinter as tk

BED = 220
Y_NOZZLE = 150          # gantry plane in frame Y (uprights sit just behind it)
Y_UPRIGHT = 176         # front face of the Z uprights
GANTRY_ABOVE = 45       # X extrusion centre above the nozzle tip
Z_TOP = 330             # top of the uprights
COL = {"frame": "#9a9a9a", "gantry": "#4a7fd6", "head": "#e07b2a", "bed": "#555555",
       "plate": "#2b2b2b", "hl": "#ffd400", "text": "#ddd", "base": "#333333", "screen": "#1f6fb0"}


class PrinterView(tk.Canvas):
    def __init__(self, master, width=470, height=440, **kw):
        super().__init__(master, width=width, height=height, bg="#1e1e1e", highlightthickness=0, **kw)
        self.w, self.h = width, height
        # fit: x spans -40..260 plus half of y (-80..260), z spans -45..Z_TOP+12 plus half of y
        self.scale = 0.78
        self.ox, self.oy = 70, height - 70
        self.disp = {"x": 110.0, "y": 110.0, "z": 60.0}     # eased display position
        self.target = dict(self.disp)
        self.homed = False
        self.highlight = None
        self.redraw()
        self.after(50, self._ease)

    # (x, y, z) mm -> canvas pixels; cabinet projection, depth recedes up-right at half scale
    def P(self, x, y, z):
        return (self.ox + (x + 0.5 * y) * self.scale, self.oy - (z + 0.5 * y) * self.scale)

    def set_position(self, pos, homed):
        if homed != self.homed:
            self.homed = homed
            self.redraw()
        if pos:
            self.target = {"x": pos.get("x", self.target["x"]), "y": pos.get("y", self.target["y"]),
                           "z": pos.get("z", self.target["z"])}

    def set_highlight(self, name):
        self.highlight = name
        self.redraw()

    def _ease(self):
        moved = False
        for k in ("x", "y", "z"):
            d = self.target[k] - self.disp[k]
            if abs(d) > 0.05:
                self.disp[k] += d * 0.3
                moved = True
        if moved:
            self.redraw()
        self.after(50, self._ease)

    def _poly(self, pts, **kw):
        flat = [c for p in pts for c in p]
        return self.create_polygon(*flat, **kw)

    def _box(self, x0, x1, y0, y1, z0, z1, fill, outline, dash=None):
        kw = {"outline": outline, "width": 1}
        if dash:
            kw["dash"] = dash
        # visible faces in this projection: front (y0), top (z1), right (x1)
        self._poly([self.P(x0, y0, z0), self.P(x1, y0, z0), self.P(x1, y0, z1), self.P(x0, y0, z1)], fill=fill, **kw)
        self._poly([self.P(x0, y0, z1), self.P(x1, y0, z1), self.P(x1, y1, z1), self.P(x0, y1, z1)], fill=self._shade(fill, 1.25), **kw)
        self._poly([self.P(x1, y0, z0), self.P(x1, y1, z0), self.P(x1, y1, z1), self.P(x1, y0, z1)], fill=self._shade(fill, 0.7), **kw)

    @staticmethod
    def _shade(col, f):
        r, g, b = int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16)
        r, g, b = (max(0, min(255, int(c * f))) for c in (r, g, b))
        return f"#{r:02x}{g:02x}{b:02x}"

    def redraw(self):
        self.delete("all")
        x, y, z = self.disp["x"], self.disp["y"], self.disp["z"]
        dash = None if self.homed else (4, 3)
        c_g = COL["hl"] if self.highlight == "gantry" else COL["gantry"]
        c_h = COL["hl"] if self.highlight == "head" else COL["head"]
        c_b = COL["hl"] if self.highlight == "bed" else COL["bed"]
        fr = COL["frame"]

        # base box, with the Y rails on top and the screen at the front right
        self._box(-40, 260, -80, 260, -45, -15, COL["base"], fr)
        for rx in (70, 150):
            self._box(rx - 4, rx + 4, -70, 250, -15, -9, "#505050", fr)
        self._box(185, 250, -78, -44, -15, 8, "#2a2a2a", fr)
        self._poly([self.P(190, -78, -10), self.P(245, -78, -10), self.P(245, -78, 4), self.P(190, -78, 4)], fill=COL["screen"], outline="")
        self.create_text(*self.P(100, -78, -30), text="CREALITY", fill="#888", font=("Segoe UI", 7, "bold"))

        # bed carriage and plate: plate top at z = 0, front edge at frame Y = Y_NOZZLE - y
        yf = Y_NOZZLE - y
        self._box(0, BED, yf, yf + BED, -9, 0, c_b, fr, dash)
        self._poly([self.P(3, yf + 3, 0.1), self.P(BED - 3, yf + 3, 0.1), self.P(BED - 3, yf + BED - 3, 0.1), self.P(3, yf + BED - 3, 0.1)],
                   fill=COL["plate"], outline="")
        self.create_text(*self.P(BED / 2, yf - 16, 1), text="bed", fill=COL["text"], font=("Segoe UI", 8))
        px, py = self.P(x, Y_NOZZLE, 0.2)
        self.create_oval(px - 3, py - 3, px + 3, py + 3, fill=c_h, outline="")

        # Z uprights at the back and the top beam
        for ux in (-30, 236):
            self._box(ux, ux + 14, Y_UPRIGHT, Y_UPRIGHT + 14, -15, Z_TOP, "#3a3a3a", fr)
        self._box(-30, 250, Y_UPRIGHT, Y_UPRIGHT + 14, Z_TOP, Z_TOP + 14, "#3a3a3a", fr)
        # lead screws
        for sx in (-23, 243):
            a, b = self.P(sx, Y_UPRIGHT - 6, -10), self.P(sx, Y_UPRIGHT - 6, Z_TOP - 10)
            self.create_line(a, b, fill="#777")

        # gantry: X extrusion in front of the uprights, end blocks wrapping them
        zg = z + GANTRY_ABOVE
        for bx in (-38, 226):
            self._box(bx, bx + 32, Y_UPRIGHT - 30, Y_UPRIGHT + 18, zg - 18, zg + 18, self._shade(c_g, 0.8), fr, dash)
        self._box(-30, 250, Y_NOZZLE - 4, Y_NOZZLE + 16, zg - 10, zg + 10, c_g, fr, dash)
        self.create_text(*self.P(254, Y_NOZZLE, zg + 26), text="gantry", fill=COL["text"], anchor="w", font=("Segoe UI", 8))

        # head on the gantry's front face, down to the nozzle tip
        self._box(x - 17, x + 17, Y_NOZZLE - 20, Y_NOZZLE - 4, z + 6, zg + 16, c_h, fr, dash)
        tx, ty = self.P(x, Y_NOZZLE - 12, z)
        self.create_polygon(tx - 4, ty - 7, tx + 4, ty - 7, tx, ty, fill="#bbb", outline="")
        self.create_text(*self.P(x, Y_NOZZLE - 36, z + 30), text="head", fill=COL["text"], font=("Segoe UI", 8))
        self.create_line(tx, ty, px, py, fill="#666", dash=(2, 3))

        # readout
        txt = f"head X {x:.1f}   bed Y {y:.1f}   gantry Z {z:.2f}" if self.homed else "not homed: positions are a guess"
        self.create_text(8, 8, text=txt, fill=COL["text"], anchor="nw", font=("Consolas", 9))
