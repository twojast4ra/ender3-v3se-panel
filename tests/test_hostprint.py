"""Printing from this computer against a fake Marlin. Not shipped.
The fake checks line numbers and checksums the way Marlin's queue.cpp does: a bad checksum or an
out-of-order number gets 'Error:...', 'Resend: <last+1>', 'ok'. It can lose oks and corrupt lines
on purpose. Every test asserts that each line of the file ran exactly once, in order.
Run: python tests/test_hostprint.py   (or pytest)
"""
import os
import queue
import re
import sys
import tempfile
import threading
import time
import types

if "serial" not in sys.modules:            # the backend imports pyserial; a stub is enough here
    m = types.ModuleType("serial")
    m.Serial = object
    m.SerialException = Exception
    t = types.ModuleType("serial.tools")
    lp = types.ModuleType("serial.tools.list_ports")
    lp.comports = lambda: []
    sys.modules.update({"serial": m, "serial.tools": t, "serial.tools.list_ports": lp})
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import prefs as P  # noqa: E402
import printer  # noqa: E402
from hostprint import Job  # noqa: E402


def xor(b):
    cs = 0
    for ch in b:
        cs ^= ch
    return cs


class FakeMarlin:
    def __init__(self, lose_ok_every=0, corrupt_every=0, delay=0.0):
        self.out = queue.Queue()
        self.last_n = 0
        self.ran = []            # every command run, numbered or not
        self.numbered = []       # the numbered ones, as run
        self.lose_ok_every, self.corrupt_every, self.delay = lose_ok_every, corrupt_every, delay
        self.count = 0
        self.corrupted = set()
        self.lost = set()
        self.in_waiting = 0

    def emit(self, s):
        self.out.put((s + "\n").encode())

    def write(self, data):
        for raw in data.decode().splitlines():
            self._line(raw.strip())
        return len(data)

    def _resend(self, why):
        self.emit(f"Error:{why}, Last Line: {self.last_n}")
        self.emit(f"Resend: {self.last_n + 1}")
        self.emit("ok")

    def _line(self, s):
        if not s:
            return
        if s.startswith("N"):
            body, _, cs = s.rpartition("*")
            m = re.match(r"N(\d+) (.*)$", body)
            n, cmd = int(m.group(1)), m.group(2)
            self.count += 1
            if self.corrupt_every and self.count % self.corrupt_every == 0 and n not in self.corrupted:
                self.corrupted.add(n)
                return self._resend("checksum mismatch")
            if int(cs) != xor(body.encode()):
                return self._resend("checksum mismatch")
            if n != self.last_n + 1:
                return self._resend("Line Number is not Last Line Number+1")
            self.last_n = n
            self.numbered.append(cmd)
            lose = self.lose_ok_every and self.count % self.lose_ok_every == 0 and n not in self.lost
            if lose:
                self.lost.add(n)
            self._run(cmd, ok=not lose)
        else:
            if s.startswith("M110"):
                self.last_n = int(re.search(r"N(\d+)", s).group(1))
            self._run(s)

    def _run(self, cmd, ok=True):
        self.ran.append(cmd)
        if self.delay:
            time.sleep(self.delay)
        word = cmd.split()[0].upper()
        if word == "M114":
            self.emit("X:12.00 Y:34.00 Z:5.60 E:0.00 Count X:0 Y:0 Z:0")
        elif word == "M27":
            self.emit("Not SD printing")
        if word in ("G28", "M109"):
            self.emit("echo:busy: processing")
            threading.Timer(0.3, lambda: self.emit("ok")).start()
            return
        if ok:
            self.emit("ok")

    def readline(self):
        try:
            return self.out.get(timeout=0.2)
        except queue.Empty:
            return b""

    def close(self):
        pass


def make_file(n_layers=20, per_layer=60):
    lines = ["; generated test file", ";TIME:1234", "M82", "M140 S60", "M104 S200", "G28", "M109 S200", "G92 E0", "G1 Z0.2 F600"]
    e = 0.0
    for L in range(n_layers):
        lines.append(";LAYER_CHANGE")
        lines.append(f"G1 Z{0.2 + 0.2 * L:.2f} F600")
        for k in range(per_layer):
            e += 0.05
            lines.append(f"G1 X{50 + k % 40} Y{60 + (k * 7) % 40} E{e:.4f} F1800 ; wall")
    lines += ["M104 S0", "M140 S0", "M84"]
    fd, path = tempfile.mkstemp(suffix=".gcode")
    with os.fdopen(fd, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def make_printer(fake):
    cfg = os.path.join(tempfile.gettempdir(), "v3se_test_config.json")
    pr = P.Prefs(cfg)
    pr["log_to_file"] = False
    p = printer.Printer(pr)
    p.line_timeout = 0.5
    p.ser = fake
    p.state.update({"connected": True, "nozzle": 210.0, "nozzle_target": 210.0})
    return p


def wait_for(cond, timeout=60):
    t_end = time.time() + timeout
    while time.time() < t_end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def run_print(fake, path):
    p = make_printer(fake)
    job = Job(path)
    p.host_start(path)
    assert wait_for(lambda: not p.host_active()), "print did not end"
    return p, job


def test_job_reading():
    path = make_file(3, 5)
    job = Job(path)
    assert job.layers == 3 and job.estimate_s == 1234.0
    assert all(";" not in c for c in job.cmds)
    assert job.layer_of[-1] == 3 and job.layer_of[0] == 0
    os.remove(path)


def test_clean_print():
    path = make_file()
    fake = FakeMarlin()
    p, job = run_print(fake, path)
    h = p.state["host"]
    assert h["state"] == "done", h
    assert fake.numbered == job.cmds
    assert p.state["finished"]["how"] == "done"
    os.remove(path)


def test_resends_and_lost_oks():
    path = make_file()
    fake = FakeMarlin(lose_ok_every=97, corrupt_every=53)
    p, job = run_print(fake, path)
    h = p.state["host"]
    assert h["state"] == "done", h
    assert fake.numbered == job.cmds, "a line ran twice or was skipped"
    # a corrupted repeat of a line whose ok was lost is answered with the next line's number, not counted as a resend
    assert fake.corrupted and fake.lost and h["resends"] > 0
    os.remove(path)


def test_pause_resume():
    path = make_file()
    fake = FakeMarlin(delay=0.001)
    p = make_printer(fake)
    job = Job(path)
    p.host_start(path)
    assert wait_for(lambda: p.state["host"]["sent"] > 200)
    p.act("pause", {})
    assert wait_for(lambda: p.state["host"]["state"] == "paused")
    feed = None
    for c in job.cmds[:p.state["host"]["sent"]]:
        m = re.search(r"F(\d+)", c)
        if m and c.startswith(("G0", "G1")):
            feed = int(m.group(1))
    mark = len(fake.ran)
    sent_at_pause = p.state["host"]["sent"]
    time.sleep(0.3)
    assert p.state["host"]["sent"] == sent_at_pause, "lines went out while paused"
    p.act("fan", {"percent": 50})            # a button works while paused
    p.act("resume", {})
    assert wait_for(lambda: not p.host_active())
    after = fake.ran[mark:]
    i = after.index("G0 X12.000 Y34.000 F3000")
    assert after[i + 1] == "G0 Z5.600 F600" and after[i + 2] == "M83" and after[i + 3] == "G1 E2.0 F1800"
    assert after[i + 4] == "M82" and after[i + 5] == f"G1 F{feed}", after[i:i + 6]
    before = fake.ran[:mark]
    assert "G1 E-2.0 F1800" in before and "G0 Z10.00 F600" in before and "G0 X0 Y200 F3000" in before
    assert p.state["host"]["state"] == "done" and fake.numbered == job.cmds
    os.remove(path)


def test_cancel():
    path = make_file()
    fake = FakeMarlin(delay=0.001)
    p = make_printer(fake)
    p.host_start(path)
    assert wait_for(lambda: p.state["host"]["sent"] > 100)
    p.act("cancel", {})
    assert wait_for(lambda: not p.host_active())
    assert p.state["host"]["state"] == "cancelled"
    tail = fake.ran[-12:]
    for c in ("M104 S0", "M140 S0", "M106 S0", "G91", "G90", "G0 X0 Y200 F3000"):
        assert c in tail, (c, tail)
    assert p.state["finished"]["how"] == "cancelled"
    os.remove(path)


def test_set_skips_empty_boxes():
    fake = FakeMarlin()
    p = make_printer(fake)
    p.refresh_settings = lambda: {}
    p.act("set", {"gcode": "M593", "params": {"X": 1, "F": "", "D": "0.15"}})
    assert "M593 X1 D0.15" in fake.ran, fake.ran
    try:
        p.act("set", {"gcode": "M593", "params": {"X": 1, "F": "", "D": ""}})
        raise AssertionError("empty boxes were sent")
    except ValueError:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            t0 = time.time()
            fn()
            print(f"{name}: ok ({time.time() - t0:.1f} s)")
    print("all host print tests passed")
    os._exit(0)
