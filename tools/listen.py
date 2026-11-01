"""Runs on the gaming PC: listen on the printer's serial port for N seconds and print what it says."""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
SECS = float(sys.argv[2]) if len(sys.argv) > 2 else 12
ser = serial.Serial(PORT, 115200, timeout=0.3)
time.sleep(1.5)
ser.reset_input_buffer()
ser.write(b"M105\n")
t0 = time.time()
while time.time() - t0 < SECS:
    line = ser.readline().decode("utf-8", "replace").rstrip()
    if line:
        print(f"{time.time() - t0:5.1f}s  {line}", flush=True)
ser.close()
