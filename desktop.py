"""Platform helpers for Windows and Linux: fonts, keeping the computer awake while a print streams
from it, and the print-finished alert (sound, desktop notification, taskbar flash).
Every helper does nothing when the tool it needs is missing; none of them can stop the panel.
"""
import os
import shutil
import subprocess
import sys

WINDOWS = sys.platform.startswith("win")
UI_FONT = "Segoe UI" if WINDOWS else "DejaVu Sans"
MONO_FONT = "Consolas" if WINDOWS else "DejaVu Sans Mono"
APP_NAME = "Ender-3 V3 SE panel"


def font(size, *style):
    return (UI_FONT, size) + style


def mono(size, *style):
    return (MONO_FONT, size) + style


def _child_env():
    """Environment for helper programs. A PyInstaller build on Linux points LD_LIBRARY_PATH at its
    own bundled libraries; system programs started with that can fail, so give them the original."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False) and not WINDOWS:
        orig = env.get("LD_LIBRARY_PATH_ORIG")
        if orig is not None:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def _spawn(cmd):
    try:
        kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "env": _child_env()}
        if WINDOWS:
            kw["creationflags"] = 0x08000000          # CREATE_NO_WINDOW
        return subprocess.Popen(cmd, **kw)
    except OSError:
        return None


class KeepAwake:
    """Stops the computer going to sleep while a print streams from it.
    Windows: SetThreadExecutionState, which belongs to the calling thread, so start() and stop()
    must be called from the same thread, one that lives for the whole print.
    Linux: a systemd-inhibit child process held for the duration, where systemd-inhibit exists."""

    def __init__(self):
        self._proc = None
        self.active = False

    def start(self, why="a print is streaming from this computer"):
        if self.active:
            return
        self.active = True
        if WINDOWS:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM_REQUIRED
            except Exception:  # noqa: BLE001
                pass
            return
        exe = shutil.which("systemd-inhibit")
        if exe:
            self._proc = _spawn([exe, "--what=sleep:idle", f"--who={APP_NAME}", f"--why={why}", "--mode=block",
                                 "sleep", "infinity"])

    def stop(self):
        if not self.active:
            return
        self.active = False
        if WINDOWS:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)            # CONTINUOUS: back to normal
            except Exception:  # noqa: BLE001
                pass
            return
        p, self._proc = self._proc, None
        if p:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass


def play_sound(root):
    if WINDOWS:
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
            return
        except Exception:  # noqa: BLE001
            pass
    else:
        sound = "/usr/share/sounds/freedesktop/stereo/complete.oga"
        if shutil.which("paplay") and os.path.exists(sound) and _spawn(["paplay", sound]):
            return
        if shutil.which("canberra-gtk-play") and _spawn(["canberra-gtk-play", "-i", "complete"]):
            return
    try:
        root.bell()
    except Exception:  # noqa: BLE001
        pass


def flash_taskbar(root):
    """Windows only: flash the panel's taskbar button until the window gets focus."""
    if not WINDOWS:
        return
    try:
        import ctypes
        from ctypes import wintypes

        class FLASHWINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                        ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]
        hwnd = int(root.wm_frame(), 16)
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0x3 | 0xC, 0, 0)   # FLASHW_ALL | FLASHW_TIMERNOFG
        ctypes.windll.user32.FlashWindowEx(ctypes.byref(info))
    except Exception:  # noqa: BLE001
        pass


def desktop_notification(title, text):
    """Linux: a desktop notification through notify-send (libnotify) when it is installed.
    Windows gets the panel's own message window and the taskbar flash instead."""
    if WINDOWS:
        return False
    exe = shutil.which("notify-send")
    if not exe:
        return False
    return _spawn([exe, "-a", APP_NAME, title, text]) is not None


def alert(root, title, text):
    play_sound(root)
    flash_taskbar(root)
    desktop_notification(title, text)
