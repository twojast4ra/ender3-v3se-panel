"""Serial backend for the Creality Ender-3 V3 SE (stock Marlin or the navaismo community build).
One thread owns the USB serial port; commands run one at a time and wait for 'ok'.
Temperatures arrive by auto-report (M155). Human actions live in Printer.act().
"""
import os
import re
import threading
import time
from collections import deque

import serial
from serial.tools import list_ports

from prefs import Prefs

HERE = os.path.dirname(os.path.abspath(__file__))
BED_X, BED_Y, Z_MAX = 220, 220, 250
LONG_CMDS = ("G28", "G29", "M8015", "M303", "M48", "M701", "M702", "M600", "M190", "M109")
BAUDS = (115200, 150000, 250000)

# Firmware families seen on this printer. 'caps' are what the firmware itself refuses above.
FIRMWARE = {
    "community": {"label": "community build (navaismo / forks)", "nozzle_cap": 300, "bed_cap": 110},
    "stock": {"label": "Creality stock", "nozzle_cap": 260, "bed_cap": 100},
    "unknown": {"label": "unknown firmware, limits set conservatively", "nozzle_cap": 260, "bed_cap": 100},
}

# Lines of an M503 dump that may be sent back to restore settings.
RESTORE_OK = ("G21", "M92", "M203", "M201", "M204", "M205", "M206", "M420", "G29", "M145", "M301", "M304",
              "M413", "M851", "M852", "M906", "M913", "M569", "M593", "M900", "M603", "M412", "M200")


def list_serial_ports():
    return [(p.device, p.description or "") for p in list_ports.comports()]


def find_port():
    for p in list_ports.comports():
        if "CH340" in (p.description or "") or "1A86:7523" in (p.hwid or ""):
            return p.device
    return None


class Printer:
    """One thread owns the serial port. Commands run one at a time, each waits for 'ok'."""

    TEMP_RE = re.compile(r"T:\s*([\d.]+)\s*/\s*([\d.]+)\s*B:\s*([\d.]+)\s*/\s*([\d.]+)")
    POS_RE = re.compile(r"X:\s*(-?[\d.]+)\s*Y:\s*(-?[\d.]+)\s*Z:\s*(-?[\d.]+)\s*E:\s*(-?[\d.]+)")

    def __init__(self, prefs=None):
        self.prefs = prefs or Prefs()
        self.ser = None
        self.port = self.prefs["port"] or None
        self.baud = int(self.prefs["baud"] or 0)
        self.lock = threading.Lock()          # one command at a time
        self.log = deque(maxlen=600)
        self.temps = deque(maxlen=1200)       # (time, nozzle, nozzle_target, bed, bed_target), ~10 min at 2 Hz
        self.state = {
            "connected": False, "port": "", "baud": 0, "firmware": "", "firmware_kind": "unknown",
            "nozzle_cap": 260, "bed_cap": 100, "busy": False,
            "nozzle": None, "nozzle_target": None, "bed": None, "bed_target": None,
            "pos": {}, "homed": {"x": False, "y": False, "z": False},
            "endstops": {}, "printing": False, "print_progress": "", "print_bytes": (0, 0),
            "sd_files": [], "sd_sizes": {}, "settings": {}, "settings_raw": [], "mesh": [],
            "last_error": "", "fan": 0, "speed": 100, "flow": 100, "upload": None,
            "task": "",                   # progress text of a multi-step action (prepare, z check)
            "babysteps": 0.0,             # unsaved Z babysteps during a print
        }
        self._pending = None
        self._ok = threading.Event()
        self._last_busy = 0.0
        self._hk_count = 0
        self._logfile = None
        self._last_temp_log = 0.0
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._housekeeping, daemon=True).start()

    # ---------- logging ----------
    def _log(self, kind, text):
        entry = {"t": time.strftime("%H:%M:%S"), "k": kind, "s": text}
        self.log.append(entry)
        if self.prefs["log_to_file"] and kind != "rx":
            self._file_log(f"{entry['t']} {kind:3} {text}")

    def _file_log(self, line):
        try:
            if self._logfile is None:
                d = os.path.join(HERE, "logs")
                os.makedirs(d, exist_ok=True)
                self._logfile = open(os.path.join(d, time.strftime("session-%Y%m%d.log")), "a", buffering=1, encoding="utf-8")
            self._logfile.write(line + "\n")
        except OSError:
            pass

    # ---------- connection ----------
    def connect(self, port=None, baud=None):
        """Open the port (given, preferred, or auto-found) and find the baud rate the printer answers at."""
        if port:
            self.port = port
        if baud:
            self.baud = int(baud)
        try:
            if not self.port or self.port == "auto":
                self.port = find_port()
            if not self.port:
                raise RuntimeError("printer not found on USB (off, unplugged, or no CH340 driver)")
            bauds = [self.baud] if self.baud else list(BAUDS)
            last = ""
            for b in bauds:
                ser = serial.Serial(self.port, b, timeout=0.2, write_timeout=2)
                time.sleep(2.0)
                ser.reset_input_buffer()
                ser.write(b"\nM115\n")
                t0 = time.time()
                text = ""
                while time.time() - t0 < 4 and "FIRMWARE_NAME" not in text:
                    text += ser.read(ser.in_waiting or 1).decode("utf-8", "replace")
                if "FIRMWARE_NAME" in text:
                    self.ser = ser
                    self.state["connected"] = True
                    self.state["port"], self.state["baud"] = self.port, b
                    self.state["last_error"] = ""
                    self._log("sys", f"connected {self.port}@{b}")
                    self._apply_firmware(text)
                    time.sleep(0.3)
                    self.send("M155 S2")              # temperature auto-report every 2 s
                    self.refresh_all()
                    return True
                ser.close()
                last = text.strip()[:60]
            raise RuntimeError(f"no answer on {self.port} at {bauds} (got: {last!r})")
        except Exception as e:  # noqa: BLE001
            self.state["connected"] = False
            self.state["last_error"] = f"{e}"
            self._log("sys", f"connect failed: {e}")
            return False

    def _apply_firmware(self, text):
        line = next((l for l in text.splitlines() if "FIRMWARE_NAME" in l), "")
        fw = line.split("SOURCE_CODE_URL")[0].replace("FIRMWARE_NAME:", "").strip()
        self.state["firmware"] = fw
        low = line.lower()
        if "navaismo" in low or "_sd" in fw.lower() or "sukharev" in low or "community" in low:
            kind = "community"
        elif "creality" in low or "marlin 2.0.8" in low or "ender-3 v3 se" in low and "github" not in low:
            kind = "stock"
        else:
            kind = "unknown"
        self.state["firmware_kind"] = kind
        self.state["nozzle_cap"] = FIRMWARE[kind]["nozzle_cap"]
        self.state["bed_cap"] = FIRMWARE[kind]["bed_cap"]
        self._log("sys", f"firmware: {fw} -> {FIRMWARE[kind]['label']}")

    def nozzle_limit(self):
        return min(int(self.prefs["nozzle_max"]), self.state["nozzle_cap"])

    def bed_limit(self):
        return min(int(self.prefs["bed_max"]), self.state["bed_cap"])

    def disconnect(self):
        s, self.ser = self.ser, None
        self.state["connected"] = False
        if s:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
        self._log("sys", "disconnected")

    # ---------- reader ----------
    def _reader(self):
        while True:
            ser = self.ser
            if not ser:
                time.sleep(0.2)
                continue
            try:
                raw = ser.readline()
            except Exception as e:  # noqa: BLE001
                if self.ser is ser:
                    self.state["connected"] = False
                    self.state["last_error"] = f"serial lost: {e}"
                    self._log("sys", self.state["last_error"])
                    self.ser = None
                continue
            if raw:
                line = raw.decode("utf-8", "replace").rstrip()
                if line:
                    self._handle_line(line)

    def _handle_line(self, line):
        m = self.TEMP_RE.search(line)
        if m:
            st = self.state
            st["nozzle"], st["nozzle_target"] = float(m.group(1)), float(m.group(2))
            st["bed"], st["bed_target"] = float(m.group(3)), float(m.group(4))
            now = time.time()
            self.temps.append((now, st["nozzle"], st["nozzle_target"], st["bed"], st["bed_target"]))
            if now - self._last_temp_log > 10 and self.prefs["log_to_file"]:
                self._last_temp_log = now
                self._file_log(f"{time.strftime('%H:%M:%S')} tmp nozzle {st['nozzle']:.1f}/{st['nozzle_target']:.0f} bed {st['bed']:.1f}/{st['bed_target']:.0f}")
            if not line.startswith("ok") and self._pending is None:
                return                      # silent auto-report
        if "busy: processing" in line or "busy: paused" in line:
            self._last_busy = time.time()
            self.state["busy"] = True
            return
        self._log("rx", line)
        p = self.POS_RE.search(line)
        if p:
            self.state["pos"] = {"x": float(p.group(1)), "y": float(p.group(2)), "z": float(p.group(3))}
        if self._pending is not None:
            self._pending.append(line)
        if line.startswith("ok") or line.startswith("Error") or line.startswith("error"):
            self.state["busy"] = False
            self._ok.set()

    # ---------- sending ----------
    def send(self, gcode, timeout=None):
        """Send one line, return its reply lines (up to and including ok)."""
        if not self.ser:
            raise RuntimeError("not connected")
        with self.lock:
            return self._send_locked(gcode, timeout)

    def _send_locked(self, gcode, timeout=None, quiet=False):
        word = gcode.split()[0].upper()
        if timeout is None:
            timeout = 900 if word in LONG_CMDS else 15
        self._pending = []
        self._ok.clear()
        if not quiet:
            self._log("tx", gcode)
        self.ser.write((gcode.strip() + "\n").encode())
        deadline = time.time() + timeout
        while not self._ok.wait(0.2):
            if time.time() - self._last_busy < 10:          # a long move keeps saying busy
                deadline = max(deadline, time.time() + 10)
            if time.time() > deadline:
                self._log("sys", f"timeout waiting for ok after {gcode}")
                break
        reply = self._pending
        self._pending = None
        return reply

    def send_many(self, cmds):
        out = []
        for c in cmds:
            out += self.send(c)
        return out

    # ---------- readers ----------
    def refresh_endstops(self):
        r = self.send("M119")
        es = {}
        for l in r:
            if ":" in l and ("_min" in l or "filament" in l or "_max" in l):
                k, v = l.split(":", 1)
                es[k.strip()] = v.strip()
            mm = re.match(r"test_axis_known_([xyz])_flag\s*=\s*(true|false)", l)
            if mm:
                self.state["homed"][mm.group(1)] = mm.group(2) == "true"
        self.state["endstops"] = es
        return es

    def refresh_position(self):
        self.send("M114")
        return self.state["pos"]

    def refresh_settings(self):
        r = self.send("M503")
        s, mesh, raw = {}, {}, []
        for l in r:
            l = l.replace("echo:", "").strip()
            if not l or l.startswith("ok"):
                continue
            raw.append(l)
            g = re.match(r"G29 W I(\d+) J(\d+) Z(-?[\d.]+)", l)
            if g:
                mesh[(int(g.group(1)), int(g.group(2)))] = float(g.group(3))
                continue
            w = l.split()
            key = w[0]
            if key in ("M92", "M203", "M201", "M204", "M205", "M206", "M420", "M145", "M301", "M304",
                       "M413", "M851", "M852", "M906", "M913", "M593", "M900", "M603", "M412", "M200"):
                vals = {}
                for tok in w[1:]:
                    if tok[0].isalpha() and len(tok) > 1:
                        try:
                            vals[tok[0]] = float(tok[1:])
                        except ValueError:
                            vals[tok[0]] = tok[1:]
                    elif tok[0].isalpha():
                        vals[tok] = True
                if key in ("M145", "M593", "M906", "M913"):
                    s.setdefault(key, []).append(vals)
                else:
                    s[key] = vals
        if mesh:
            nx = max(i for i, _ in mesh) + 1
            ny = max(j for _, j in mesh) + 1
            self.state["mesh"] = [[mesh.get((i, j)) for i in range(nx)] for j in range(ny)]
        self.state["settings"] = s
        self.state["settings_raw"] = raw
        return s

    def refresh_print(self):
        r = self.send("M27")
        for l in r:
            if "SD printing byte" in l:
                self.state["printing"] = True
                prog = l.replace("SD printing byte", "").strip()
                self.state["print_progress"] = prog
                try:
                    a, b = prog.split("/")
                    self.state["print_bytes"] = (int(a), int(b))
                except ValueError:
                    pass
                return
            if "Not SD printing" in l:
                if self.state["printing"]:
                    self._log("sys", "print finished or stopped")
                self.state["printing"] = False
                self.state["print_progress"] = ""
                self.state["print_bytes"] = (0, 0)

    def refresh_sd(self):
        r = self.send("M20")
        files, sizes, grab = [], {}, False
        for l in r:
            if l.startswith("Begin file list"):
                grab = True
                continue
            if l.startswith("End file list"):
                break
            if grab and l.strip():
                parts = l.split()
                files.append(parts[0])
                if len(parts) > 1 and parts[1].isdigit():
                    sizes[parts[0].upper()] = int(parts[1])
        self.state["sd_files"] = files
        self.state["sd_sizes"] = sizes
        return files

    def refresh_all(self):
        for f in (self.refresh_endstops, self.refresh_position, self.refresh_settings, self.refresh_print):
            try:
                f()
            except Exception as e:  # noqa: BLE001
                self._log("sys", f"{f.__name__}: {e}")

    def _housekeeping(self):
        while True:
            time.sleep(2)
            if not self.ser:
                if (self.prefs["port"] or find_port()) and not self.state["last_error"].startswith("no answer"):
                    self.connect()                  # printer just came on
                continue
            if self.lock.locked():
                continue
            try:
                self.refresh_position()
                self._hk_count += 1
                if self._hk_count % 3 == 0:
                    self.refresh_print()
            except Exception:  # noqa: BLE001
                pass

    # ---------- SD upload ----------
    @staticmethod
    def sd_name(path):
        """8.3 name for the card: letters and digits of the file's stem, upper case, max 8, plus .GCO"""
        stem = os.path.splitext(os.path.basename(path))[0]
        stem = "".join(ch for ch in stem if ch.isalnum()).upper()[:8] or "PRINT"
        return stem + ".GCO"

    def upload_sd(self, path, card_name=None):
        """Write a local gcode file onto the printer's SD card over serial (M28 .. M29).
        While Marlin saves to the card it REQUIRES a line number and checksum on every line
        (queue.cpp: 'No Checksum' error otherwise), strips comments from serial input, and
        writes each command plus CRLF. So comments and blank lines are dropped here, each line
        goes as 'N<n> <cmd>*<xor>', and a 'Resend: <n>' reply restarts from n."""
        if self.state["printing"]:
            raise ValueError("printing; the card is in use")
        name = (card_name or self.sd_name(path)).upper()
        cmds = []
        with open(path, "rb") as f:
            for raw in f.read().splitlines():
                c = raw.split(b";", 1)[0].strip()
                if c:
                    cmds.append(c)
        total = len(cmds)
        up = {"file": name, "sent": 0, "total": total, "done": False, "error": ""}
        self.state["upload"] = up

        def framed(n, cmd):
            body = b"N%d " % n + cmd
            cs = 0
            for ch in body:
                cs ^= ch
            return body + b"*%d\n" % cs

        t0 = time.time()
        resends = 0
        with self.lock:
            self._send_locked("M110 N0", 10)
            r = self._send_locked(f"M28 {name}", 20)
            if not any("Writing to file" in l for l in r):
                up["error"] = "printer refused M28: " + " | ".join(r)
                self._log("sys", up["error"])
                return up
            i = 0
            try:
                while i < total:
                    self._pending = []
                    self._ok.clear()
                    self.ser.write(framed(i + 1, cmds[i]))
                    if not self._ok.wait(10):
                        up["error"] = f"no ok after line {i + 1}"
                        break
                    if any(l.startswith("Error") for l in self._pending) and not any(l.startswith("ok") for l in self._pending):
                        self._ok.clear()
                        self._ok.wait(5)
                    resend = [l for l in self._pending if l.startswith("Resend:")]
                    if resend:
                        n = int(resend[-1].split(":", 1)[1].strip())
                        i = max(0, n - 1)
                        resends += 1
                        if resends > 50:
                            up["error"] = "too many resends"
                            break
                        continue
                    i += 1
                    up["sent"] = i
            finally:
                self._pending = None
                r = self._send_locked("M29", 20)
        self._log("sys", f"upload {name}: {up['sent']}/{total} lines, {resends} resends, {time.time() - t0:.0f} s; " + " | ".join(r))
        up["done"] = not up["error"] and up["sent"] == total
        self.refresh_sd()
        expected = sum(len(c) + 2 for c in cmds)
        listed = self.state["sd_sizes"].get(name)
        if up["done"] and listed is not None and listed != expected:
            up["error"] = f"size on card {listed} differs from {expected} expected"
            up["done"] = False
            self._log("sys", up["error"])
        return up

    # ---------- settings backup / restore ----------
    def backup_settings(self, path):
        self.refresh_settings()
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"; {self.state['firmware']}\n; saved {time.strftime('%Y-%m-%d %H:%M')}\n")
            for l in self.state["settings_raw"]:
                f.write(l + "\n")
        return len(self.state["settings_raw"])

    def restore_settings(self, path):
        sent = 0
        with open(path, "r", encoding="utf-8") as f:
            for raw in f:
                l = raw.replace("echo:", "").strip()
                if not l or l.startswith(";") or l.startswith("DISPLAY") or ":" in l.split()[0]:
                    continue
                if l.split()[0] in RESTORE_OK:
                    self.send(l)
                    sent += 1
        self.send("M500")
        self.refresh_settings()
        return sent

    # ---------- human actions ----------
    def act(self, action, p):
        """Translate a UI action into gcode. Returns reply lines. Raises ValueError on refusal."""
        st = self.state
        pr = self.prefs
        printing = st["printing"]

        def need_idle():
            if printing:
                raise ValueError("printing from SD; only speed, flow, fan, Z babysteps, pause, resume and cancel are allowed")

        def need_homed(*axes):
            missing = [a for a in axes if not st["homed"].get(a)]
            if missing:
                raise ValueError("home first (" + ", ".join(missing).upper() + " not homed)")

        def hot_enough():
            if (st["nozzle"] or 0) < pr["extrude_min_c"]:
                raise ValueError(f"nozzle below {pr['extrude_min_c']} C; heat it first")

        if action == "home":
            need_idle()
            which = p.get("axes", "")
            r = self.send("G28 " + which if which else "G28")
            self.refresh_endstops()
            self.refresh_position()
            return r
        if action == "move":
            need_idle()
            axis, dist = p["axis"].upper(), float(p["dist"])
            need_homed(axis.lower())
            if axis == "Z" and dist < 0 and st["pos"]:
                floor = -float(st["pos"].get("z", 0))
                if dist < floor:
                    dist = floor
                    if dist > -0.01:
                        raise ValueError("gantry is already at Z 0")
                    self._log("sys", f"gantry down clamped to Z 0 ({dist:+.2f})")
            feed = pr["feed_z"] if axis == "Z" else pr["feed_xy"]
            r = self.send_many(["G91", f"G0 {axis}{dist:.2f} F{feed}", "G90"])
            self.refresh_position()
            return r
        if action == "goto":
            need_idle()
            need_homed("x", "y", "z")
            parts = " ".join(f"{a.upper()}{float(v):.2f}" for a, v in p.items() if a in ("x", "y", "z"))
            r = self.send_many(["G90", f"G0 {parts} F{pr['feed_xy']}"])
            self.refresh_position()
            return r
        if action == "extrude":
            need_idle()
            hot_enough()
            dist = float(p["dist"])
            return self.send_many(["M83", f"G1 E{dist:.1f} F{pr['feed_e']}", "M82"])
        if action == "motors_off":
            need_idle()
            r = self.send("M84")
            st["homed"] = {"x": False, "y": False, "z": False}
            return r
        if action == "heat":
            cmds = []
            if p.get("nozzle") is not None:
                nz = int(float(p["nozzle"]))
                if not 0 <= nz <= self.nozzle_limit():
                    raise ValueError(f"nozzle must be 0..{self.nozzle_limit()} on this firmware")
                cmds.append(f"M104 S{nz}")
            if p.get("bed") is not None:
                bd = int(float(p["bed"]))
                if not 0 <= bd <= self.bed_limit():
                    raise ValueError(f"bed must be 0..{self.bed_limit()} on this firmware")
                cmds.append(f"M140 S{bd}")
            return self.send_many(cmds)
        if action == "preset":
            pre = pr["presets"][p["name"]]
            return self.act("heat", {"nozzle": pre["nozzle"], "bed": pre["bed"]})
        if action == "cooldown":
            return self.send_many(["M104 S0", "M140 S0", "M106 S0"])
        if action == "fan":
            v = int(p["percent"])
            st["fan"] = v
            return self.send(f"M106 S{round(v * 2.55)}")
        if action == "speed":
            v = int(p["percent"])
            st["speed"] = v
            return self.send(f"M220 S{v}")
        if action == "flow":
            v = int(p["percent"])
            st["flow"] = v
            return self.send(f"M221 S{v}")
        if action == "level":
            need_idle()
            cmds = [] if all(st["homed"].values()) else ["G28"]
            cmds += ["G29", "M500"]
            r = self.send_many(cmds)
            self.refresh_settings()
            self.refresh_endstops()
            self.refresh_position()
            return r
        if action == "auto_zoffset":
            need_idle()
            r = self.send("M8015")
            self.refresh_settings()
            return r
        if action == "zoffset":
            v = float(p["value"])
            if not -5 <= v <= 2:
                raise ValueError("Z offset outside -5..2")
            r = self.send_many([f"M851 Z{v:.2f}", "M500"])
            self.refresh_settings()
            return r
        if action == "babystep":
            # live nudge during a print; with BABYSTEP_ZPROBE_OFFSET the firmware folds it into the offset
            d = float(p["dist"])
            st["babysteps"] = round(st["babysteps"] + d, 3)
            return self.send(f"M290 Z{d:.3f}")
        if action == "save_settings":
            st["babysteps"] = 0.0
            r = self.send("M500")
            self.refresh_settings()
            return r
        if action == "prepare":
            # heat, home, level hot, then bring the nozzle to temperature
            need_idle()
            pre = pr["presets"][p["material"]]
            bed, noz = int(pre["bed"]), int(pre["nozzle"])
            if bed > self.bed_limit() or noz > self.nozzle_limit():
                raise ValueError("preset above this firmware's limits")
            steps = [
                ("heating the bed to %d and the nozzle to 150 (soft, no dripping)" % bed, [f"M140 S{bed}", "M104 S150"]),
                ("homing", ["G28"]),
                ("waiting for the bed to reach %d" % bed, [f"M190 S{bed}"]),
                ("levelling the plate (36 points, hot)", ["G29", "M500"]),
                ("nozzle to %d, parking" % noz, [f"M104 S{noz}", "G0 Z30 F300", "G0 X0 Y200 F3000"]),
            ]
            for text, cmds in steps:
                st["task"] = text
                self.send_many(cmds)
            self.refresh_settings()
            self.refresh_endstops()
            self.refresh_position()
            st["task"] = "ready to print: mesh saved, nozzle heating to %d" % noz
            return ["prepared"]
        if action == "zcheck_start":
            # guided Z offset: nozzle over the plate centre at Z 0, then babystep until a paper drags
            need_idle()
            cmds = [] if all(st["homed"].values()) else ["G28"]
            cmds += ["G90", "G0 Z5 F300", f"G0 X{BED_X / 2:.0f} Y{BED_Y / 2:.0f} F3000", "G0 Z0 F300"]
            st["babysteps"] = 0.0
            r = self.send_many(cmds)
            self.refresh_position()
            st["task"] = "nozzle at Z 0 over the centre: slide a sheet of paper under it and nudge until it just drags"
            return r
        if action == "zcheck_finish":
            r = self.send_many(["M500", "G0 Z10 F300"])
            st["babysteps"] = 0.0
            st["task"] = "Z offset saved"
            self.refresh_settings()
            self.refresh_position()
            return r
        if action == "set":
            need_idle()
            g = p["gcode"].upper()
            allowed = {"M92", "M203", "M201", "M204", "M205", "M206", "M420", "M145", "M301", "M304",
                       "M413", "M851", "M593", "M900", "M603", "M412", "M255", "M256"}
            if g not in allowed:
                raise ValueError(f"{g} not editable here")
            parts = [g] + [f"{k.upper()}{v}" for k, v in p["params"].items()]
            r = self.send_many([" ".join(parts), "M500"])
            self.refresh_settings()
            return r
        if action == "reload":
            r = self.send("M501")
            self.refresh_settings()
            return r
        if action == "defaults":
            need_idle()
            r = self.send_many(["M502", "M500"])
            self.refresh_settings()
            return r
        if action == "backup":
            return [f"{self.backup_settings(p['path'])} lines saved"]
        if action == "restore":
            need_idle()
            return [f"{self.restore_settings(p['path'])} settings restored and saved"]
        if action == "probe":
            need_idle()
            code = {"deploy": "M280 P0 S10", "stow": "M280 P0 S90", "selftest": "M280 P0 S120", "reset": "M280 P0 S160"}[p["what"]]
            return self.send(code)
        if action == "probe_repeat":
            need_idle()
            need_homed("x", "y", "z")
            return self.send(f"M48 P{int(p.get('count', pr['probe_repeat_n']))} V2")
        if action == "pid_nozzle":
            need_idle()
            t = int(p.get("temp", pr["pid_nozzle_c"]))
            if t > self.nozzle_limit():
                raise ValueError(f"above the nozzle limit {self.nozzle_limit()}")
            r = self.send_many([f"M303 E0 S{t} C8 U1", "M500"])
            self.refresh_settings()
            return r
        if action == "pid_bed":
            need_idle()
            t = int(p.get("temp", pr["pid_bed_c"]))
            if t > self.bed_limit():
                raise ValueError(f"above the bed limit {self.bed_limit()}")
            r = self.send_many([f"M303 E-1 S{t} C8 U1", "M500"])
            self.refresh_settings()
            return r
        if action == "filament":
            need_idle()
            hot_enough()
            return self.send("M701" if p["what"] == "load" else "M702")
        if action == "sd_list":
            return self.refresh_sd()
        if action == "sd_print":
            need_idle()
            r = self.send_many([f"M23 {p['file']}", "M24"])
            self.refresh_print()
            return r
        if action == "sd_pause":
            r = self.send("M25")
            self.refresh_print()
            return r
        if action == "sd_resume":
            r = self.send("M24")
            self.refresh_print()
            return r
        if action == "sd_cancel":
            r = self.send_many(["M524", "M104 S0", "M140 S0", "M106 S0"])
            self.refresh_print()
            return r
        if action == "sd_delete":
            need_idle()
            r = self.send(f"M30 {p['file']}")
            self.refresh_sd()
            return r
        if action == "sd_upload":
            need_idle()
            up = self.upload_sd(p["path"], p.get("name"))
            if up["error"]:
                raise ValueError(up["error"])
            return [f"{up['file']} written, {up['sent']} lines"]
        if action == "filament_change":
            return self.send("M600")
        if action == "beep":
            return self.send("M300 S880 P200")
        if action == "endstops":
            return list(self.refresh_endstops().items())
        if action == "refresh":
            self.refresh_all()
            return ["ok"]
        if action == "gcode":
            g = p["gcode"].strip()
            if not g:
                raise ValueError("empty")
            if g.upper().startswith("M112"):
                raise ValueError("M112 is removed in this firmware; use the power switch")
            r = self.send(g)
            if g.upper().startswith(("G28", "G0", "G1", "M84", "M18")):
                self.refresh_endstops()
                self.refresh_position()
            return r
        raise ValueError(f"unknown action {action}")
