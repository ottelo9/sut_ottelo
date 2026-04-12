#!/usr/bin/env bash

set -e

# Make sure that user is in dialout group.
if ! groups | grep -q "\bdialout\b"; then
    echo "❌ User $USER is not in the dialout group. Please add with:"
    echo "   sudo usermod -a -G dialout $USER"
    exit 1
fi

# Try to get the Python 3 version
if command -v python3 &>/dev/null; then
    PYVER=$(python3 -c 'import sys; print("{}.{}".format(sys.version_info[0], sys.version_info[1]))')
    MIN_VER="3.8"

    # Use Python for comparison
    if ! python3 -c "import sys; sys.exit(0) if sys.version_info >= (3,8) else sys.exit(1)"; then
        echo "❌ Python 3 version $PYVER is too old. Requires 3.8+"
        exit 1
    fi
else
    echo "❌ Python 3 is not installed"
    exit 1
fi

DEVICE="/dev/serial0"

# Check if the device exists
if [ ! -e "$DEVICE" ]; then
    echo "❌ $DEVICE does not exist"
    exit 1
fi

# Check read and write permissions for the current user
if ! ([ -r "$DEVICE" ] && [ -w "$DEVICE" ]); then
    echo "❌ You do NOT have sufficient permissions on $DEVICE"

    # Optional: show useful debug info
    ls -l "$DEVICE"
    id

    exit 1
fi

## /dev/serial0 tests
# socat -d -d pty,raw,echo=0 pty,raw,echo=0
# sudo ln -s /dev/pts/3 /dev/serial0

# create venv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating venv"
    python3 -m venv .venv
fi

# activate venv
echo "Activating venv"
source .venv/bin/activate

# install deps (only first time / when changed)
if [ ! -f .venv/.deps_installed ] || [ requirements.txt -nt .venv/.deps_installed ]; then
    echo "Installing requirements.txt"
    pip install -r requirements.txt
    touch .venv/.deps_installed
fi

# install pigpio if not available (needed for dual-channel sniffing)
if ! command -v pigpiod &>/dev/null; then
    echo "Installing pigpio..."
    if sudo apt-get install -y pigpio 2>/dev/null; then
        echo "pigpio installed via apt"
    else
        echo "apt failed, building from source..."
        PIGPIO_TMP=$(mktemp -d)
        wget -q -O "$PIGPIO_TMP/pigpio.zip" https://github.com/joan2937/pigpio/archive/refs/heads/master.zip
        unzip -q "$PIGPIO_TMP/pigpio.zip" -d "$PIGPIO_TMP"
        make -C "$PIGPIO_TMP/pigpio-master" -j$(nproc)
        sudo make -C "$PIGPIO_TMP/pigpio-master" install
        rm -rf "$PIGPIO_TMP"
        echo "pigpio installed from source"
    fi
fi

# run script
echo "Start tool"
echo "================"
python sut.py "$@"