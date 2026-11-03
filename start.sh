#!/bin/sh
# Ender-3 V3 SE control panel. Close Pronterface or OctoPrint's connection to the printer first.
cd "$(dirname "$0")"
exec python3 app.py "$@"
