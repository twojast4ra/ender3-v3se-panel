"""Runs on the gaming PC: set the nozzle target and report how tightly it holds over N seconds."""
import re
import sys
import time

import serial

PORT, TEMP, SECS = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
ser = serial.Serial(PORT, 115200, timeout=0.5)
time.sleep(1.5)
ser.reset_input_buffer()
ser.write(f"M104 S{TEMP}\nM155 S1\n".encode())
t0 = time.time()
v = []
while time.time() - t0 < SECS:
    line = ser.readline().decode("utf-8", "replace")
    m = re.search(r"T:\s*([\d.]+)", line)
    if m:
        v.append((time.time() - t0, float(m.group(1))))
ser.write(b"M155 S0\n")
ser.close()
half = [x for x in v if x[0] >= SECS / 2]
print(f"{len(v)} samples; first {v[0][1]:.1f}, last {v[-1][1]:.1f}")
print(f"second half: min {min(x[1] for x in half):.2f}  max {max(x[1] for x in half):.2f}  target {TEMP}")
print("trace:", " ".join(f"{x[1]:.1f}" for x in v[::4]))
