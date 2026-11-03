#!/bin/sh
# One-time setup on Debian, Ubuntu and their relatives, for running the panel from source:
# Tk and pyserial from the distribution, and permission to open the printer's USB port
# (the dialout group). The ready-to-run binary from the releases page needs only the group.
set -e
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is not installed. Install it with your package manager, then run this again."
  exit 1
fi
need=""
python3 -c "import tkinter" 2>/dev/null || need="$need python3-tk"
python3 -c "import serial" 2>/dev/null || need="$need python3-serial"
if [ -n "$need" ]; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "Installing:$need (sudo asks for your password)"
    sudo apt-get install -y $need
  else
    echo "Install Tk and pyserial for Python 3 with your package manager (Fedora: python3-tkinter python3-pyserial),"
    echo "then run ./start.sh"
    exit 1
  fi
fi
if ! id -nG "$USER" | grep -qw dialout; then
  echo "Adding $USER to the dialout group so the panel may open /dev/ttyUSB0 (sudo asks for your password)"
  sudo usermod -aG dialout "$USER"
  echo "Log out and back in once for that to take effect."
fi
echo "Done. Plug the printer in, switch it on, and run ./start.sh"
