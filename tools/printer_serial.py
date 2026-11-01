"""Runs on the gaming PC: talk to the Ender-3 V3 SE over USB serial.
Usage: python printer_serial.py [--port COMx] [--baud N] CMD [CMD ...]
Sends each gcode, prints every reply line until 'ok'. Tries 115200, 150000, 250000
when no --baud is given. Lists ports when none are found. Never sends motion.
"""
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("pyserial missing: python -m pip install --user pyserial")
    sys.exit(2)

SAFE = ("M115", "M119", "M503", "M114", "M420 V", "M851", "M206", "M211", "M92")


def ports():
    out = []
    for p in list_ports.comports():
        out.append((p.device, p.description, p.hwid))
    return out


def read_until_ok(ser, timeout=8.0):
    lines = []
    t0 = time.time()
    while time.time() - t0 < timeout:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("utf-8", "replace").rstrip()
        lines.append(line)
        if line.startswith("ok") or line.startswith("Error"):
            break
    return lines


def try_open(port, baud):
    ser = serial.Serial(port, baud, timeout=0.5, write_timeout=2)
    time.sleep(2.0)  # board may reset on DTR
    ser.reset_input_buffer()
    ser.write(b"\nM115\n")
    lines = read_until_ok(ser, 5.0)
    if any("FIRMWARE_NAME" in l or l.startswith("ok") for l in lines):
        return ser, lines
    ser.close()
    return None, lines


def main():
    args = sys.argv[1:]
    port = baud = None
    if "--port" in args:
        i = args.index("--port"); port = args[i + 1]; del args[i:i + 2]
    if "--baud" in args:
        i = args.index("--baud"); baud = int(args[i + 1]); del args[i:i + 2]
    cmds = args or ["M115", "M119"]
    for c in cmds:
        if not c.upper().startswith(SAFE):
            print("refusing non-readonly command:", c)
            return 3
    avail = ports()
    print("ports:", avail)
    if not port:
        if not avail:
            print("no serial ports")
            return 1
        port = avail[0][0]
    bauds = [baud] if baud else [115200, 150000, 250000]
    ser = None
    for b in bauds:
        try:
            ser, first = try_open(port, b)
        except Exception as e:  # noqa: BLE001
            print(f"{port}@{b}: {e}")
            continue
        if ser:
            print(f"connected {port}@{b}")
            print("\n".join(first))
            break
        print(f"{port}@{b}: no sane reply: {first[:3]}")
    if not ser:
        return 1
    for c in cmds:
        ser.reset_input_buffer()
        ser.write((c + "\n").encode())
        print(f"\n>>> {c}")
        print("\n".join(read_until_ok(ser, 10.0)))
    ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
