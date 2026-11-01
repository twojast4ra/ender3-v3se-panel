# Ender-3 V3 SE control panel

A Windows desktop panel for the Creality Ender-3 V3 SE over the USB cable. Buttons are named for
what moves (head, bed, gantry), every control has a plain-language hint, and the things that
usually need a terminal (levelling, Z offset, PID tuning, settings backup, sending a file to the
card) are one click each. No server, no browser, no account: a Python window talking to the
printer's serial port.

Works with the stock Creality firmware and with the community Marlin builds
([navaismo](https://github.com/navaismo/Ender-3V3-SE) and forks). The panel reads the firmware
name on connect and sets the temperature limits accordingly.

## What it does

- **Move**: head left/right, bed towards/away, gantry up/down in chosen steps, keyboard jogging,
  homing per axis, motors off, extrude/retract, load/unload. A 3D sketch of the printer follows
  the real position; hovering a button lights the part it drives.
- **Start here**: *Prepare to print* heats, homes, levels with the hot bed and brings the nozzle
  to temperature in one go. *Check Z offset* puts the nozzle at height zero over the plate centre
  for the paper test, with nudge buttons and a save.
- **Heat**: material presets (editable), custom targets, part fan, print speed and flow (also
  during a print), and a 10-minute temperature graph that shows at a glance whether the heaters
  hold steady.
- **Level**: probe the plate and save the mesh, see it as a coloured grid with range and tilt
  numbers, set the Z offset (live nudges during a print, saved when it looks right), the
  printer's one-key auto Z offset, probe pin tests, repeatability test, and a 30-second live
  switch test for prints that land in the wrong place.
- **Print (SD card)**: list, print, pause, resume, cancel, delete, filament change, and **upload a
  gcode file onto the card in the printer** over USB, so the card never has to come out.
- **Plate**: the sliced paths of a gcode file layer by layer with the head's position on top;
  follows the printer's Z during a print.
- **Stored settings**: every value the printer keeps, with readable names and double-click edit;
  backup to a file and restore from it (do this before a firmware flash).
- **Tools**: PID tuning for nozzle and bed, input shaping, linear advance, runout sensor,
  power-loss recovery, screen brightness.
- **Preferences**: port and speed, jog steps and speeds, presets, limits, and a switch for the
  hints. **Console**: raw gcode with history and a log of everything sent and received.
  **Help**: a one-page primer for someone new to printing.

## Install

1. Install Python 3.10 or newer from https://www.python.org/downloads/ and tick
   *Add python.exe to PATH*.
2. Download this repository (Code → Download ZIP) and unpack it anywhere.
3. Run `install.cmd` once. It installs `pyserial`, the only extra package.
4. Plug the printer into the PC with the USB-C cable, switch it on, run `start.cmd`.

Windows installs the printer's USB driver (CH340) by itself; if the panel says *printer not found
on USB*, check Device Manager for a COM port.

Only one program can hold the serial port: close Pronterface, Cura's monitor or OctoPrint's
connection before starting the panel, and the panel before using them.

## First run

Preferences → Connection: *auto* finds the printer and tries the usual speeds. The top bar shows
the firmware it found and the temperature limits that go with it. Then Move → *Start here* →
*Prepare to print*, and watch what it does the first time.

## Notes on the firmware

- Stock Creality firmware caps the nozzle at 260 °C and the bed at 100 °C; the community builds
  allow 300 / 110. The panel uses the lower of the firmware's cap and your preference.
- Uploading to the card uses Marlin's M28/M29. The firmware demands a line number and checksum
  on every line while writing and strips comments, so the upload drops comments, which means
  uploaded files show no time or filament estimate on the printer's screen. Printing is unaffected.
  Expect about 5 minutes per 2 MB.
- The community build removes M112 (emergency stop). The panel offers none; the power switch is
  at the back right.
- During a print the panel only allows speed, flow, fan, Z nudges, pause, resume and cancel.

## Files

`app.py` the window · `printer.py` serial backend and the action table · `prefs.py` preferences
(`config.json`, created on first run) · `ui_help.py` hints and the Help text · `view3d.py` the
printer sketch · `plateview.py` the gcode plate view · `tools/` small command-line helpers
(read-only gcode, PID tune, temperature hold check) · `tests/smoke_test.py` builds the window
against a fake printer. A session log is written to `logs\` (switch off in Preferences).

`build_exe.cmd` makes a single `.exe` with PyInstaller for machines without Python.

## Safety

The panel refuses moves before homing, cold extrusion, jogs below Z 0, temperatures above the
firmware's limits and anything but print controls while a card print runs. It cannot stop the
printer in an emergency; nothing over USB can on this firmware. Stay within reach of the power
switch during first-layer work.

## Licence

MIT. Not affiliated with Creality.
