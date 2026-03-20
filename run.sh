#!/usr/bin/env bash

set -e

# create venv if not exists
if [ ! -d "venv" ]; then
    echo "Creating venv"
    python3 -m venv venv
fi

# activate venv
echo "Activating venv"
source venv/bin/activate

# install deps (only first time / when changed)
if [ ! -f venv/.deps_installed ] || [ requirements.txt -nt venv/.deps_installed ]; then
    echo "Installing requirements.txt"
    pip install -r requirements.txt
    touch venv/.deps_installed
fi

# run script
echo "Start tool"
echo "================"
python bt_tool.py "$@"