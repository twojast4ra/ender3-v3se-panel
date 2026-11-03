#!/bin/sh
# Builds the single-file Linux binary and the release tar.gz with PyInstaller.
# Run it on the OLDEST distribution the binary should start on (Debian 12 for the releases):
# the binary needs that system's C library (glibc) or a newer one.
# Needs python3, python3-venv, python3-tk and binutils. VENV= picks an existing virtualenv.
# Output in dist/: Ender3V3SE-panel, and Ender3V3SE-panel-linux-x86_64.tar.gz (binary, README.md, LICENSE).
set -e
cd "$(dirname "$0")/.."
VENV="${VENV:-.build-venv}"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q pyinstaller pyserial
fi
"$VENV/bin/python" -m PyInstaller --noconfirm --onefile --name Ender3V3SE-panel app.py
rm -rf dist/pkg
mkdir -p dist/pkg/Ender3V3SE-panel
cp dist/Ender3V3SE-panel README.md LICENSE dist/pkg/Ender3V3SE-panel/
tar -C dist/pkg -czf dist/Ender3V3SE-panel-linux-x86_64.tar.gz Ender3V3SE-panel
rm -rf dist/pkg
ldd --version | head -n 1
sha256sum dist/Ender3V3SE-panel dist/Ender3V3SE-panel-linux-x86_64.tar.gz
