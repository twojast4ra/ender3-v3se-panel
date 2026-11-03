"""Tooltips and the Help tab text for the control panel, written for someone new to printing.
attach_tooltips(root) walks the widget tree and hangs a tooltip on every button, radio button,
check box, label and group frame whose text appears in TOOLTIPS. Tooltip.enabled switches them all.
"""
import tkinter as tk
from tkinter import ttk

from desktop import font


class Tooltip:
    """Small yellow note that appears half a second after the mouse rests on a widget."""

    enabled = True
    _open = []

    def __init__(self, widget, text, delay=500):
        self.widget, self.text, self.delay = widget, text, delay
        self.tip = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        if Tooltip.enabled:
            self.after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self):
        if self.tip or not Tooltip.enabled or not self.widget.winfo_exists():
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tip, text=self.text, justify="left", bg="#fff8c8", fg="#222", relief="solid",
                 borderwidth=1, wraplength=400, padx=8, pady=5, font=font(9)).pack()
        Tooltip._open.append(self)

    def _hide(self, _e=None):
        self._cancel()
        if self.tip:
            self.tip.destroy()
            self.tip = None
            if self in Tooltip._open:
                Tooltip._open.remove(self)

    @classmethod
    def set_enabled(cls, on):
        cls.enabled = bool(on)
        for t in list(cls._open):
            t._hide()


# key: the widget's label text (buttons, radios, check boxes, labels, group frames)
TOOLTIPS = {
    # start here
    "Start here": "The sequence for a cold printer, in one go: heat, home, level with a hot bed, bring the nozzle to temperature. About five minutes. Watch it the first time.",
    "Prepare to print": "Runs: bed to the material's temperature with the nozzle kept soft at 150, home all axes, wait for the bed, probe the plate (36 points), save the mesh, nozzle to printing temperature, park. Then print from the card.",
    "Check Z offset (paper test)": "Guided: homes, puts the nozzle over the plate centre at height 0. Slide a sheet of paper under it and use the nudge buttons until the paper just drags, then Save. This is the single number that decides a good first layer.",
    # move
    "◄  Head left": "Moves the print head left along the gantry by the chosen step. The printer must be homed first, so it knows where the head is.",
    "Head right  ►": "Moves the print head right along the gantry by the chosen step. Needs homing first.",
    "Bed away  ▲": "Slides the bed away from you. The nozzle then sits nearer the FRONT of the plate (the bed moves, not the head).",
    "Bed towards me  ▼": "Slides the bed towards you. The nozzle then sits nearer the BACK of the plate.",
    "Gantry up  ▲": "Raises the whole X gantry (with the head on it) by the step. Safe direction: away from the plate.",
    "Gantry down  ▼": "Lowers the gantry towards the plate by the step. The panel will not go below Z 0 once homed; with the arrow keys you can hold a direction.",
    "Step (mm):": "How far each move button goes. 0.1 for fine adjustment at the plate, 10 or 50 to get somewhere quickly. Edit the choices in Preferences.",
    "custom": "Type your own step in the box and this radio uses it.",
    "Home": "Homing drives each axis to its end switch and sets that as zero. Do it after every power-on; until then the printer does not know where anything is and refuses moves.",
    "Home everything": "Head to the left stop, bed to its switch, then the probe measures the plate at the centre to set zero height. Takes about 15 seconds. Required after power-on.",
    "Home head (X)": "Only the head: drives left until the switch on the head's left side meets the stop.",
    "Home bed (Y)": "Only the bed: slides until its switch trips.",
    "Home gantry (Z)": "Only the height: moves the probe over the plate centre and touches down. Homes head and bed first if they are not.",
    "Motors off (push by hand)": "Cuts power to the stepper motors so you can push the head and bed by hand. The printer forgets its position: home again before printing.",
    "Extruder (nozzle must be hot)": "Feeding filament by hand. The printer refuses to push cold plastic (below about 180 °C) because that would strip the filament or jam the gear.",
    "Extrude": "Pushes the length in the box through the nozzle. Use it to purge old colour or check the flow.",
    "Retract": "Pulls the length in the box back out of the nozzle.",
    "Load filament": "The printer's own load routine: feeds filament in and purges. Insert the filament into the extruder first, nozzle hot.",
    "Unload filament": "Heats if needed, then pulls the filament out so you can swap spools.",
    "Keyboard: arrows move the head and bed, Page Up / Page Down the gantry, by the chosen step (click the picture first).": "Click on the picture to give it focus, then use the keys. Same rules as the buttons: homed first, never below Z 0.",
    # heat
    "Presets (nozzle / bed)": "One press sets both targets for a material. Heating starts immediately and keeps the temperature until you cool down. Add or change presets in Preferences.",
    "Cool down everything": "Sets nozzle and bed to 0 and stops the part fan. The hotend takes a few minutes to drop.",
    "Custom": "Type a temperature and press Set. The upper limits are the firmware's for your build (shown in brackets).",
    "Set nozzle": "Starts heating the nozzle to the number on the left.",
    "Set bed": "Starts heating the bed to the number on the left.",
    "Save as preset...": "Stores the two numbers above under a material name, so they become a button.",
    "Fan, speed and flow (work during a print too)": "These three can be changed while a print runs, including a print started from the printer's screen.",
    "Part fan %": "The fan that blows on the plastic just laid down. Helps PLA and overhangs; keep it OFF for ABS or the layers crack apart.",
    "Print speed %": "Scales every movement of a running print. 100 = as sliced. 60 = slower and gentler; the file is not changed.",
    "Flow %": "Scales how much plastic is pushed out. 100 = as sliced. Only change it when walls are visibly too thin or too fat.",
    "Last 10 minutes": "Nozzle (orange) and bed (blue) temperatures against their targets (thin lines). A steady line is good; a saw-tooth around the target means the heater controller needs tuning (Tools → PID).",
    # level
    "Bed mesh": "The plate is never perfectly flat or level. Levelling measures it at 36 points and the printer bends the first 10 mm of every print to follow that shape.",
    "Level now (homes, probes the grid, saves)": "Homes, then probes 36 points across the plate and saves the result. Heat the bed to printing temperature first: the plate changes shape by a tenth or two between cold and hot, and that is the whole margin a first layer has.",
    "Z offset": "The gap between where the probe says 'zero' and where the nozzle tip really touches the plate. More negative = nozzle closer. During a print the buttons nudge live (babysteps) and you save when it looks right.",
    "closer": "Nozzle 0.05 mm closer to the plate. Use while watching a first layer that looks like loose strands.",
    "further": "Nozzle 0.05 mm further from the plate. Use when the first layer is transparent, rough, or the nozzle ploughs.",
    "Apply and save": "Writes the Z offset shown into the printer's memory so it survives power-off.",
    "Save nudges": "Makes the live nudges of this print permanent (writes the adjusted offset to the printer's memory).",
    "Auto Z offset (one-key: nozzle presses the plate)": "The printer's own routine: it presses the nozzle tip onto the plate and measures the offset itself. Same thing the Level icon on the screen does first. Nozzle must be clean of plastic or the result is off by the blob.",
    "Switches and probe": "The end switches tell the printer where zero is. The probe (the pin next to the nozzle) measures the plate height.",
    "Read switches now": "Asks the printer for the state of its switches. 'open' = not pressed. The head switch should only read TRIGGERED when the head sits at the left stop.",
    "Switch test (30 s live)": "Shows the switch states live for 30 seconds. Press each switch by hand and watch it flip; a head or bed switch that reads TRIGGERED with nothing touching it is the classic cause of prints landing in the wrong place. The probe is the exception: it reads TRIGGERED while its pin is up.",
    "Probe pin down": "Deploys the probe pin. It should drop and the light turn blue.",
    "Probe pin up": "Retracts the probe pin.",
    "Probe self-test": "The probe cycles its pin a few times by itself. Good first check when levelling fails.",
    "Probe reset": "Clears a probe alarm (flashing red light).",
    "Probe repeatability test": "Touches the same spot several times and reports how much the readings differ. Under 0.02 mm is good; more means a dirty or worn probe pin.",
    # print
    "Refresh file list": "Reads the list of files on the card in the printer, with sizes.",
    "Print selected": "Starts the selected file from the card, as if you had picked it on the screen. The printer heats first, then homes, then prints.",
    "Print from this computer": "Prints a gcode file straight from this computer over the USB cable, without copying it to the card first. The computer must stay on and the window open until the end.",
    "Choose gcode and print...": "Pick a sliced .gcode file and start it at once. The Plate tab loads the same file and follows the layer being sent. Progress, layer and time left show here and in the top bar.",
    "Running print": "Controls for the print that is running, wherever it was started.",
    "Print from the card": "Files on the card inside the printer. A card print carries on if this computer sleeps or the cable comes out.",
    "Pause": "Pauses the running print. From this computer: the moves already sent finish, the filament is pulled back 2 mm, the head lifts 10 mm and moves to the front left; heaters stay on. From the card: the printer's own pause.",
    "Resume": "Continues a paused print. From this computer: the head goes back to where it stopped, the filament is pushed forward again and the print carries on. Refuses when the nozzle heater was switched off meanwhile.",
    "Cancel print (and cool down)": "Stops the print and switches the heaters and fan off. A print from this computer also lifts the head and moves it clear. Cannot be undone.",
    "Delete selected": "Removes the selected file from the card. Cannot be undone.",
    "Change filament (M600)": "Parks the head and unloads so you can swap filament mid-print, then resume.",
    "Upload gcode to the card in the printer": "Sends a sliced file over the USB cable onto the card inside the printer, so the card can stay in. Slow (about 5 minutes per 2 MB) because the printer checks every line. Uploaded files show no time or filament estimate on the screen.",
    "Choose gcode and upload...": "Pick a .gcode file on this PC. You can set the name it gets on the card (8 letters, .GCO).",
    # settings
    "Re-read from printer": "Reads all stored settings again from the printer.",
    "Backup to file...": "Saves every stored setting (steps, speeds, PID, Z offset, mesh) to a text file. Do this before a firmware flash: flashing wipes them.",
    "Restore from file...": "Sends a backup file back to the printer and saves. Only the known setting lines are sent.",
    "Restore firmware defaults": "Resets every stored value to what the firmware was compiled with. Afterwards the Z offset is 0 (nozzle high, safe but will not stick), the mesh is gone, and PID is untuned: level, set the offset and retune PID before printing.",
    # tools
    "PID tuning (heats, cycles 8 times, saves; several minutes)": "The heater controller has to be matched to the heater. A bad match makes the temperature swing up and down and the print never starts (it waits for a steady temperature). Tune after changing the hotend or heater.",
    "Tune nozzle": "Heats to the temperature in the box, swings around it 8 times to measure the heater, saves the new controller values. About 3 minutes. Nothing moves.",
    "Tune bed": "Same for the bed heater. Slower, about 10 minutes.",
    "Motion features (saved on Apply)": "Advanced motion settings. Leave them unless you are chasing a specific print defect.",
    "Apply X": "Input shaping cancels the ringing (wavy echoes after corners) at the frame's resonance frequency. Needs a measured frequency; wrong values make it worse.",
    "Apply Y": "Same for the bed direction.",
    "Linear advance K": "Compensates the pressure lag in the nozzle so corners are sharp and walls even. 0 = off. Typical 0.02 to 0.1 for a direct-drive printer; needs a calibration print.",
    "Shaping off": "Switches input shaping off on both axes (frequency 0). Use when a wrong frequency makes things worse.",
    "Linear advance off": "Sets K to 0, which switches linear advance off.",
    "Sensors and screen": "Switches for the printer's safety features and the display. A tick shows what the printer has now; a grey box means the printer did not report that setting.",
    "Filament runout sensor": "Ticked: the printer pauses when the filament runs out (the switch the filament passes through). Untick only if it gives false alarms.",
    "Power-loss recovery": "Ticked: the printer saves its progress during card prints so they can continue after a power cut. Costs some card writes every layer.",
    "Bed levelling (mesh compensation)": "Ticked: the printer follows the stored mesh. Unticked: it prints as if the plate were flat. This firmware switches it back on after homing.",
    "Screen brightness": "The printer's own display, 10 (dim) to 255 (full). Takes effect when you let go of the slider.",
    "Last report": "What the printer answered to the last probe repeatability test or PID tune, with the time it started.",
    "Beep": "Makes the printer beep once. Handy to check it is listening.",
    # preferences
    "Show hints on hover": "These yellow notes. Switch them off once you know the panel.",
    "Alert when a print ends (sound and a message)": "When a print finishes or stops on its own: a sound, a message window, a flashing taskbar button on Windows and a desktop notification on Linux. Not after you cancel.",
    "Connection": "Which USB port and speed. Auto finds the printer's CH340 chip (COM port on Windows, /dev/ttyUSB0 on Linux) and tries the usual speeds (115200, 150000, 250000).",
    "Connect": "Opens the connection with the port and speed chosen here, and remembers them.",
    "Save preferences": "Writes everything on this tab to config.json next to the program. Presets and steps on the other tabs update at once.",
    "Reset to defaults": "Puts every preference back to the shipped values (not the printer's settings, only this panel's).",
    "Add / update preset": "Adds the material with its two temperatures, or changes it if the name exists.",
    "Remove preset": "Deletes the selected material from the list.",
    "Reconnect": "Re-opens the USB connection. Use after the printer was off, or if another program (Pronterface) had the port.",
}

GLOSSARY = """A short primer, in the order you meet things.

FIRST TIME. Preferences: check the port (Auto is fine) and press Connect. The top bar shows the firmware it found and the temperature limits that go with it. Then Move → Start here → Prepare to print, and watch what it does.

HOMING. After power-on the printer does not know where its head, bed and gantry are. Homing drives each to its switch and calls that zero. Nothing moves before that, and the picture on the Move tab is only a guess until it is done.

HEAD, BED, GANTRY. On this printer the head moves left and right along a horizontal bar (the gantry). The gantry moves up and down on the two uprights at the back. The bed moves front to back, so when a print "moves" in that direction it is the plate sliding under a nozzle that stays put.

LEVELLING and the MESH. The plate is not flat to a hundredth of a millimetre, and the first layer of a print is only 0.2 mm thick. Levelling probes 36 points and stores the plate's shape; the printer then follows that shape for the first 10 mm of every print. Level with the bed hot, because the plate changes shape with temperature. Level again after moving the printer or changing the plate. The numbers beside the grid tell you how far the plate is from flat and from level; a tilt above about 0.5 mm is worth fixing at the gantry.

Z OFFSET. The probe sits next to the nozzle and triggers a little above the plate. The Z offset is the correction from "probe triggered" to "nozzle touching". It decides the first layer: too high and the lines lie loose and peel; too low and the nozzle ploughs. Use the paper test to set it, then adjust in 0.05 steps while watching a first layer, not more.

TEMPERATURES. Nozzle: where the plastic melts. Bed: keeps the first layers stuck to the plate. Each material has its pair; the presets hold yours. The part fan cools the plastic just laid down; PLA likes it, ABS hates it (layers split). The graph on the Heat tab shows whether the heaters hold steady.

PID. The controller that keeps a heater at its target. It has to be tuned to the heater; untuned it swings and the print waits forever for a steady temperature. Retune after changing hotend or heater (Tools).

STARTING A PRINT. Slice on the PC, then either print it straight from this computer (Print tab, it starts at once but the computer has to stay on), or upload it to the card or put the card in and print from the card. The printer heats, homes, draws a purge line along the left edge, then starts. Watch the first layer; it tells you everything. Nudge the Z offset live from the Level tab if it needs it.

WHEN SOMETHING LOOKS WRONG. Pause from the Print tab, look, decide. Cancel switches the heaters off. There is no emergency stop in this firmware; the power switch is at the back right. Prints landing off-centre or the probe hunting at one edge: run the switch test.

BACKUPS. Stored settings → Backup to file before any firmware flash. PID values, the Z offset and the mesh are lost on flashing and take an hour to rebuild.

WHAT THE PANEL WILL NOT LET YOU DO. Move before homing. Push filament through a cold nozzle. Move or heat differently while a print runs (speed, flow, fan, Z nudges, pause and cancel are allowed). Heat beyond the firmware's limits. Go below Z 0 with a jog."""


def attach_tooltips(root):
    """Hang a Tooltip on every widget whose text is in TOOLTIPS. Call once after building."""
    count = 0
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            text = w.cget("text") if isinstance(w, (ttk.Button, ttk.Radiobutton, ttk.Checkbutton, ttk.Label, ttk.LabelFrame, tk.Button)) else None
        except tk.TclError:
            text = None
        if text and text in TOOLTIPS:
            Tooltip(w, TOOLTIPS[text])
            count += 1
        stack.extend(w.winfo_children())
    return count
