"""Runs on the gaming PC: nozzle PID autotune at a temperature, then save. Prints progress."""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
TEMP = int(sys.argv[2]) if len(sys.argv) > 2 else 270
import os
LOG = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "pidtune.log"), "a", buffering=1)
_print = print


def print(msg, flush=True):  # noqa: A001
    _print(msg, flush=True)
    LOG.write(msg + "\n")


ser = serial.Serial(PORT, 115200, timeout=0.5)
print(f"tune started {time.strftime('%H:%M:%S')} target {TEMP}")
time.sleep(1.5)
ser.reset_input_buffer()
ser.write(f"M303 E0 S{TEMP} C8 U1\n".encode())
t0 = time.time()
done = False
while time.time() - t0 < 900:
    line = ser.readline().decode("utf-8", "replace").rstrip()
    if not line:
        continue
    if line.startswith(("ok", " T:", "T:")) and "W:" not in line and time.time() - t0 > 3 and "/" in line:
        # throttle the temperature spam: print every ~10 s
        if int(time.time() - t0) % 10 == 0:
            print(f"{time.time() - t0:5.0f}s  {line.strip()}", flush=True)
        continue
    print(f"{time.time() - t0:5.0f}s  {line}", flush=True)
    if "PID Autotune finished" in line or "#define DEFAULT_Kd" in line:
        done = True
    if done and line.startswith("ok"):
        break
    if "PID Autotune failed" in line:
        break
if done:
    time.sleep(0.5)
    ser.reset_input_buffer()
    ser.write(b"M500\n")
    time.sleep(1.0)
    print("saved: " + " | ".join(l.strip() for l in ser.read_all().decode("utf-8", "replace").splitlines() if l.strip()), flush=True)
    ser.write(b"M503\n")
    time.sleep(2.0)
    for l in ser.read_all().decode("utf-8", "replace").splitlines():
        if "M301" in l:
            print("stored: " + l.strip(), flush=True)
ser.close()
